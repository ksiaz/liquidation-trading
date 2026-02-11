"""
EP-2 Strategy: SLBRS (Sideways Liquidity Block Reaction System)

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)

Purpose:
Exploits absorption, negotiation, and inventory rebalancing in range-bound conditions.

Strategy Logic (from OB-SLBRSorderblockstrat.md):
1. Detect liquidity blocks (zone_liquidity ≥ 2.5 × avg, persistence ≥ 30s)
2. Observe first test (price enters, volume increases, price rejects)
3. Enter on retest (reduced volume, absorption_ratio ≥ 0.65, near block edge)
4. Exit on invalidation (volatility expands, orderflow one-sided, price accepts)

Thresholds from Market Mechanics (NOT backtest optimization):
- 0.75 resting imbalance: One side ≥ 75% of top-5 depth (directional wall, not MM noise)
- 60s persistence: Minimum block stability
- 0.65-0.95 absorption ratio: Orders consumed but block still standing (100% = broke through)
- 0.30 block width: Proximity threshold for retest
- 0.3% ATR floor: No entry when ATR < 0.3% of price (no volatility = no block)
- ALL primitives required: zone_penetration, structural_persistence, resting_size, order_consumption
- No fallbacks: missing any primitive → no entry
- Max 3 concurrent SLBRS positions

CRITICAL: This strategy acknowledges outcome divergence (P12).
Same structure may lead to different outcomes. No confidence scoring.
"""

from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum, auto

from runtime.position.types import PositionState


# ==============================================================================
# Input/Output Types
# ==============================================================================

@dataclass(frozen=True)
class StrategyContext:
    """Immutable context for strategy execution."""
    context_id: str
    timestamp: float


@dataclass(frozen=True)
class PermissionOutput:
    """M6 permission result (from M6 scaffolding)."""
    result: str  # "ALLOWED" | "DENIED"
    mandate_id: str
    action_id: str
    reason_code: str
    timestamp: float


@dataclass(frozen=True)
class StrategyProposal:
    """Immutable strategy proposal for EP-3 arbitration."""
    strategy_id: str
    action_type: str  # ENTRY, EXIT, HOLD, REDUCE, BLOCK
    confidence: str  # Opaque label (NOT numeric) - per constitutional constraint
    justification_ref: str  # Reference ID only
    timestamp: float
    direction: str = None  # "LONG" | "SHORT" for ENTRY


@dataclass(frozen=True)
class RegimeState:
    """Regime state for SLBRS gating."""
    regime: str  # "SIDEWAYS_ACTIVE", "EXPANSION_ACTIVE", "DISABLED"
    vwap_distance: float
    atr_5m: float
    atr_30m: float


# ==============================================================================
# SLBRS Internal State
# ==============================================================================

class SLBRSState(Enum):
    """SLBRS state machine states."""
    IDLE = auto()  # No liquidity block detected
    FIRST_TEST_OBSERVED = auto()  # Block tested, rejection observed
    RETEST_ARMED = auto()  # Entry proposed, awaiting acceptance


@dataclass
class FirstTestObservation:
    """Records first test characteristics for retest comparison."""
    block_edge: float  # Block boundary price
    block_width: float  # Block price range
    test_volume: float  # Volume during first test
    test_price_impact: float  # Price movement during test
    timestamp: float


# ==============================================================================
# SLBRS Strategy Implementation
# ==============================================================================

class SLBRSStrategy:
    """
    Stateful SLBRS strategy implementation.

    Maintains internal state for first test observation and retest logic.

    Constitutional Compliance:
    - Thresholds from market mechanics (not backtest optimization)
    - Acknowledges outcome divergence (P12)
    - No confidence scoring
    - No certainty claims
    """

    # Max concurrent SLBRS positions — level-retest strategy shouldn't be in 10 positions
    MAX_CONCURRENT_POSITIONS = 3

    # Minimum cycles with valid order_consumption before allowing entry.
    # Ensures L2 data has converged (not just 1-2 snapshots after startup).
    # At ~3s regime cycle, 20 observations = ~60s of real L2 comparison data.
    MIN_OC_OBSERVATIONS = 20

    # Diagnostic logging interval — log rejection reason every N cycles per symbol.
    # At 5Hz (200ms cycle), 150 cycles = ~30s between diagnostics per symbol.
    _DIAG_INTERVAL = 150

    # Maximum age (seconds) for a cached order_consumption value.
    # OC is inherently transient — only non-None when L2 book decreased between
    # consecutive snapshots. Most cycles have no decrease (MM refill, stable book).
    # Caching with 30s window lets a single consumption event satisfy the gate
    # across multiple evaluation cycles without requiring real-time coincidence.
    _OC_CACHE_MAX_AGE_SEC = 30.0

    # Capitulation confidence threshold: below this, capitulation gate blocks entry.
    # 0.5 is intentionally softer than cascade sniper's 0.7 — SLBRS uses it as
    # additional confirmation rather than primary signal. Debated 2026-02-11.
    CAPITULATION_MIN_CONFIDENCE = 0.5

    def __init__(self):
        """Initialize SLBRS strategy with empty state."""
        self._state: Dict[str, SLBRSState] = {}  # symbol -> state
        self._first_test: Dict[str, Optional[FirstTestObservation]] = {}  # symbol -> first test
        self._sideways_streak: Dict[str, int] = {}  # symbol -> consecutive SIDEWAYS cycles
        self._last_exit_ts: Dict[str, float] = {}  # symbol -> timestamp of last exit/reset
        self._open_symbols: set = set()  # symbols with open SLBRS positions
        self._oc_seen: Dict[str, int] = {}  # symbol -> count of valid order_consumption cycles
        self._diag_counter: Dict[str, int] = {}  # symbol -> cycle counter for diagnostics
        self._oc_cache: Dict[str, tuple] = {}  # symbol -> (order_consumption, timestamp)
        self._sp_cache: Dict[str, tuple] = {}  # symbol -> (structural_persistence, timestamp)
        # Gate rejection frequency: gate_name -> count (across all symbols)
        self._gate_rejections: Dict[str, int] = {}
        self._gate_rejections_total: int = 0
        self._last_gate_log_ts: float = 0.0

    def generate_proposal(
        self,
        *,
        symbol: str,
        regime_state: Optional[RegimeState],
        zone_penetration,  # ZonePenetrationDepth | None
        resting_size,  # RestingSize | None (bid/ask orderbook depth)
        order_consumption,  # OrderConsumption | None
        structural_persistence,  # StructuralPersistence | None
        price: float,
        context: StrategyContext,
        permission: PermissionOutput,
        position_state: Optional[PositionState] = None,
        absorption_event=None,  # AbsorptionEvent | None (B2.1 - orderbook absorption)
        directional_continuity=None,  # DirectionalContinuity | None (B4 - trade flow direction)
        orderflow_imbalance: Optional[float] = None,  # Taker buy ratio 0-1 (0=all selling, 1=all buying)
        orderflow_fill_count: int = 0,  # Number of fills in orderflow window
        capitulation_confidence: float = 0.0  # CapitulationTracker confidence 0-1
    ) -> Optional[StrategyProposal]:
        """
        Generate SLBRS proposal based on current market structure.

        Constitutional Compliance:
        - Conditional execution: "When structure X, do action Y"
        - No claim about outcome probability
        - Acknowledges: Same structure may lead to different outcomes

        Args:
            symbol: Trading symbol
            regime_state: Current regime (must be SIDEWAYS_ACTIVE for SLBRS)
            zone_penetration: A6 primitive (zone interaction)
            resting_size: Orderbook depth primitive
            order_consumption: Order consumption primitive
            structural_persistence: B2.1 primitive (block persistence)
            price: Current price
            context: Strategy execution context
            permission: M6 permission result
            position_state: Current position state

        Returns:
            StrategyProposal if conditions met, None otherwise
        """
        # Initialize symbol state if needed
        if symbol not in self._state:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            self._sideways_streak[symbol] = 0
            self._last_exit_ts[symbol] = 0.0

        # Periodic gate rejection summary (every ~5 minutes)
        if (self._gate_rejections_total > 0 and
                context.timestamp - self._last_gate_log_ts >= 300.0):
            self._last_gate_log_ts = context.timestamp
            sorted_gates = sorted(self._gate_rejections.items(), key=lambda x: -x[1])
            top = " ".join(f"{g}={c}" for g, c in sorted_gates[:8])
            print(f"[SLBRS-GATES] total={self._gate_rejections_total} {top}", flush=True)

        # Rule 1: M6 DENIED -> no proposal
        if permission.result == "DENIED":
            return None

        # Rule 2: Regime gate - SLBRS only active in SIDEWAYS regime
        if regime_state is None or regime_state.regime != "SIDEWAYS_ACTIVE":
            self._sideways_streak[symbol] = 0
            return None

        # Track consecutive SIDEWAYS cycles for regime stability
        self._sideways_streak[symbol] = self._sideways_streak.get(symbol, 0) + 1

        # Rule 3: Check position state and generate appropriate action
        if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
            self._open_symbols.add(symbol)  # Track open position
            # Position accepted — reset SLBRS state so it's ready after exit
            if self._state[symbol] == SLBRSState.RETEST_ARMED:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
            # Check for invalidation (currently returns None — trailing stop handles exits)
            return self._check_invalidation(
                symbol=symbol,
                regime_state=regime_state,
                zone_penetration=zone_penetration,
                price=price,
                context=context
            )

        # Rule 4: Position FLAT - check for entry opportunity
        if position_state == PositionState.FLAT or position_state is None:
            self._open_symbols.discard(symbol)  # No longer open
            # If we were RETEST_ARMED but position is now FLAT, entry was rejected
            # or position already exited — reset with cooldown
            if self._state[symbol] == SLBRSState.RETEST_ARMED:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
                self._last_exit_ts[symbol] = context.timestamp

            return self._check_entry(
                symbol=symbol,
                regime_state=regime_state,
                zone_penetration=zone_penetration,
                resting_size=resting_size,
                order_consumption=order_consumption,
                structural_persistence=structural_persistence,
                price=price,
                context=context,
                directional_continuity=directional_continuity,
                orderflow_imbalance=orderflow_imbalance,
                orderflow_fill_count=orderflow_fill_count,
                capitulation_confidence=capitulation_confidence
            )

        # No action
        return None

    def _check_entry(
        self,
        symbol: str,
        regime_state: RegimeState,
        zone_penetration,
        resting_size,
        order_consumption,
        structural_persistence,
        price: float,
        context: StrategyContext,
        directional_continuity=None,
        orderflow_imbalance: Optional[float] = None,
        orderflow_fill_count: int = 0,
        capitulation_confidence: float = 0.0
    ) -> Optional[StrategyProposal]:
        """
        Check for SLBRS entry opportunity (retest logic).

        Entry requires ALL of (no fallbacks, no exceptions):
        1. ALL primitives present: zone_penetration, structural_persistence,
           resting_size, order_consumption (missing any → no entry)
        2. ATR > 0.3% of price (real volatility required)
        3. Zone penetration > 10% of ATR (meaningful interaction)
        4. Structural persistence ≥ 60s (block stability)
        5. Resting size imbalance ≥ 75/25 (directional wall, filters MM noise)
        6. First test: block detected, no entry on first test
        7. Retest: price near block edge (30% of ATR width)
        8. Absorption: 65% ≤ order_consumption ≤ 95% (absorbed but block standing)
        9. Directional continuity: trade flow not contradicting wall direction
        10. Orderflow confirmation: taker flow must confirm direction
        11. Regime stable (4+ consecutive SIDEWAYS cycles)
        12. Max 3 concurrent positions, 120s post-exit cooldown

        Returns:
            ENTRY proposal if ALL conditions met, None otherwise
        """
        # Diagnostic logging: track which gate blocks, log every N cycles
        self._diag_counter[symbol] = self._diag_counter.get(symbol, 0) + 1
        _diag = self._diag_counter[symbol] % self._DIAG_INTERVAL == 0
        _reject = None  # Set to gate name if rejected

        # Log capitulation confidence periodically (data collection, not a gate)
        if _diag and capitulation_confidence > 0.0:
            print(f"[SLBRS-DIAG] {symbol}: cap={capitulation_confidence:.2f}", flush=True)

        def _count_reject(gate_name: str):
            """Record gate rejection for frequency analysis."""
            self._gate_rejections[gate_name] = self._gate_rejections.get(gate_name, 0) + 1
            self._gate_rejections_total += 1

        # ======================================================================
        # TRANSIENT PRIMITIVE CACHE: OC and SP are computed from point-in-time
        # state that flickers between cycles. OC requires L2 book to decrease;
        # SP requires raw_trades window to overlap M2 node intervals. Both can
        # be None in any given cycle despite the underlying condition persisting.
        # Cache recent values (30s) to avoid blocking on timing coincidence.
        # ======================================================================
        if order_consumption is not None:
            self._oc_cache[symbol] = (order_consumption, context.timestamp)
        elif symbol in self._oc_cache:
            cached_oc, cached_ts = self._oc_cache[symbol]
            if context.timestamp - cached_ts <= self._OC_CACHE_MAX_AGE_SEC:
                order_consumption = cached_oc
            else:
                del self._oc_cache[symbol]

        if structural_persistence is not None:
            self._sp_cache[symbol] = (structural_persistence, context.timestamp)
        elif symbol in self._sp_cache:
            cached_sp, cached_ts = self._sp_cache[symbol]
            if context.timestamp - cached_ts <= self._OC_CACHE_MAX_AGE_SEC:
                structural_persistence = cached_sp
            else:
                del self._sp_cache[symbol]

        # ======================================================================
        # PRIMITIVE REQUIREMENTS: ALL must be present. No fallbacks.
        # Missing any primitive = incomplete picture = no entry.
        # ======================================================================
        if zone_penetration is None:
            _reject = "zone_pen=None"
        elif structural_persistence is None:
            _reject = "struct_persist=None"
        elif resting_size is None:
            _reject = "resting_sz=None"
        elif order_consumption is None:
            _reject = "order_cons=None"

        if _reject:
            _count_reject("primitives_missing")
            if _diag:
                _missing = []
                if zone_penetration is None: _missing.append("zp")
                if structural_persistence is None: _missing.append("sp")
                if resting_size is None: _missing.append("rs")
                if order_consumption is None: _missing.append("oc")
                print(f"[SLBRS-DIAG] {symbol}: primitives_missing={'+'.join(_missing)}")
            return None

        # ======================================================================
        # DATA QUALITY GATE: L2 data must have converged before trusting OC.
        # After startup, first few order_consumption values are noise (1-2 snapshots).
        # Require MIN_OC_OBSERVATIONS cycles with valid OC before allowing entry.
        # ======================================================================
        self._oc_seen[symbol] = self._oc_seen.get(symbol, 0) + 1
        if self._oc_seen[symbol] < self.MIN_OC_OBSERVATIONS:
            _count_reject("oc_warmup")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: oc_warmup={self._oc_seen[symbol]}/{self.MIN_OC_OBSERVATIONS}")
            return None

        # ======================================================================
        # ATR GATE: Require real measured volatility. No fallbacks.
        # If ATR is zero or trivially small, there's no meaningful price action
        # for a block retest strategy. Fallback to price*X defeats the gate.
        # ======================================================================
        atr_width = regime_state.atr_5m
        min_meaningful_atr = price * 0.003  # 0.3% of price — real volatility required
        if atr_width < min_meaningful_atr:
            _count_reject("atr_low")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: atr_low={atr_width:.4f}<{min_meaningful_atr:.4f}")
            return None

        # ======================================================================
        # BLOCK DETECTION: All conditions from strategy spec.
        # 1. Zone penetration must be meaningful (> 10% of ATR, not just > 0)
        # 2. Structural persistence ≥ 60s (block stability)
        # 3. Resting size shows significant depth imbalance (bid/ask ratio)
        # ======================================================================
        # Gate: penetration must be meaningful relative to ATR
        if zone_penetration.penetration_depth < atr_width * 0.1:
            _count_reject("pen_depth")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: pen_depth={zone_penetration.penetration_depth:.4f}<{atr_width*0.1:.4f}")
            return None

        # Gate: block must have persisted at least 60s
        if structural_persistence.total_persistence_duration < 60.0:
            _count_reject("persist_low")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: persist={structural_persistence.total_persistence_duration:.1f}s<60s")
            return None

        # Gate: resting orders must show meaningful depth on at least one side
        bid_sz = getattr(resting_size, 'bid_size', 0) or 0
        ask_sz = getattr(resting_size, 'ask_size', 0) or 0
        total_resting = bid_sz + ask_sz
        if total_resting <= 0:
            _count_reject("resting_empty")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: resting_empty")
            return None
        # Imbalance: one side must dominate (directional wall).
        # 0.75 = 75/25 split. Normal MM noise is 55-65%, so 0.75 filters it out.
        resting_ratio = max(bid_sz, ask_sz) / total_resting if total_resting > 0 else 0
        if resting_ratio < 0.75:  # 75/25 minimum — below this is normal book asymmetry
            _count_reject("resting_ratio")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: resting_ratio={resting_ratio:.2f}<0.75 bid={bid_sz:.1f} ask={ask_sz:.1f}")
            return None

        # Gate: Minor side must have meaningful dollar value (not just thin book gap).
        # A high ratio (0.96) with $640 minor side = book gap, not directional conviction.
        # $5k minimum filters thin-book noise while allowing real walls on any asset.
        MIN_MINOR_SIDE_USD = 5000.0
        minor_side_usd = min(bid_sz, ask_sz) * price
        if minor_side_usd < MIN_MINOR_SIDE_USD:
            _count_reject("minor_usd")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: minor_usd=${minor_side_usd:.0f}<${MIN_MINOR_SIDE_USD:.0f}")
            return None

        block_exists = True

        # State: IDLE → detect first block interaction
        if self._state[symbol] == SLBRSState.IDLE:
            if not block_exists:
                return None

            # Gate: Regime must be stable (4+ consecutive SIDEWAYS cycles)
            if self._sideways_streak.get(symbol, 0) < 4:
                _count_reject("sideways_streak")
                if _diag:
                    print(f"[SLBRS-DIAG] {symbol}: sideways_streak={self._sideways_streak.get(symbol, 0)}<4")
                return None

            # Gate: Max concurrent SLBRS positions
            if len(self._open_symbols) >= self.MAX_CONCURRENT_POSITIONS:
                _count_reject("max_positions")
                if _diag:
                    print(f"[SLBRS-DIAG] {symbol}: max_positions={len(self._open_symbols)}>={self.MAX_CONCURRENT_POSITIONS}")
                return None

            # Gate: Post-exit cooldown (120s)
            last_exit = self._last_exit_ts.get(symbol, 0.0)
            if last_exit > 0 and context.timestamp - last_exit < 120.0:
                _count_reject("cooldown")
                if _diag:
                    print(f"[SLBRS-DIAG] {symbol}: cooldown={context.timestamp - last_exit:.0f}s<120s")
                return None

            # First time seeing block - record as first test
            # Capture actual consumed volume if available for retest comparison
            first_consumed = 0.0
            if order_consumption is not None:
                first_consumed = getattr(order_consumption, 'consumed_size', 0) or 0.0
            self._first_test[symbol] = FirstTestObservation(
                block_edge=price,
                block_width=atr_width,
                test_volume=first_consumed,
                test_price_impact=zone_penetration.penetration_depth,
                timestamp=context.timestamp
            )
            self._state[symbol] = SLBRSState.FIRST_TEST_OBSERVED
            return None  # No entry on first test

        # State: FIRST_TEST_OBSERVED → check for retest entry
        # Block was already validated on first test. Don't require full block_exists
        # again (structural_persistence/order_consumption flicker between cycles).
        if self._state[symbol] == SLBRSState.FIRST_TEST_OBSERVED:
            first_test = self._first_test[symbol]
            if first_test is None:
                self._state[symbol] = SLBRSState.IDLE
                return None

            # Timeout: reset if no retest within 120s of first test
            if context.timestamp - first_test.timestamp > 120.0:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
                return None

            # Retest Condition 1: Price near block edge
            distance_to_block = abs(price - first_test.block_edge)
            proximity_threshold = 0.30 * first_test.block_width  # 30% of block width

            if distance_to_block > proximity_threshold:
                _count_reject("retest_proximity")
                return None

            # Gate: Max concurrent SLBRS positions (check again at retest)
            if len(self._open_symbols) >= self.MAX_CONCURRENT_POSITIONS:
                _count_reject("max_positions")
                return None

            # Retest Condition 2: Absorption evidence (order_consumption required)
            # Absorption = orders consumed while block holds. NOT full consumption.
            # - consumed/initial ≥ 0.65: meaningful absorption happening
            # - consumed/initial ≤ 0.95: block still standing (100% = block broke through)
            # No fallbacks — order_consumption was required at top of method.
            initial = getattr(order_consumption, 'initial_size', 0) or 0
            consumed = getattr(order_consumption, 'consumed_size', 0) or 0
            if initial <= 0:
                _count_reject("absorption_no_initial")
                return None  # No initial orders to absorb
            absorption_pct = consumed / initial
            if absorption_pct < 0.65 or absorption_pct > 0.95:
                _count_reject("absorption_range")
                return None  # Too little absorption OR block broken through

            # Direction from orderbook depth imbalance (resting_size required at top)
            # More resting on bid side = buy wall = price supported = LONG
            # More resting on ask side = sell wall = price capped = SHORT
            direction = "LONG"
            if ask_sz > bid_sz:
                direction = "SHORT"

            # Directional continuity gate: trade flow must not contradict resting_size direction
            if directional_continuity is not None and directional_continuity.total_trades > 0:
                buy_ratio = directional_continuity.buy_trades / directional_continuity.total_trades
                if direction == "LONG" and buy_ratio < 0.4:
                    _count_reject("dir_continuity")
                    return None  # Block says LONG but selling dominates — contradicted
                if direction == "SHORT" and buy_ratio > 0.6:
                    _count_reject("dir_continuity")
                    return None  # Block says SHORT but buying dominates — contradicted

            # Orderflow data quality gate: require sufficient fills for reliable ratio.
            # With sparse HL fills, a 60s window may have 10-15 fills for alts →
            # extreme ratios like 0.06 (1 buy / 15 total) that look directional but
            # are noise. 25 fills minimum ensures ratio has statistical meaning.
            MIN_ORDERFLOW_FILLS = 25
            if orderflow_fill_count < MIN_ORDERFLOW_FILLS:
                _count_reject("orderflow_fills")
                return None  # Insufficient fills for reliable orderflow

            # Orderflow extremity guard: near-0 or near-1 values are unreliable.
            # of=0.06 with 15 fills = 1 buyer among 14 sellers — not conviction.
            # Require ratio in [0.10, 0.90] to filter sparse-data extremes.
            if orderflow_imbalance is not None:
                if orderflow_imbalance < 0.10 or orderflow_imbalance > 0.90:
                    _count_reject("orderflow_extreme")
                    return None  # Extreme reading = unreliable data

            # Orderflow confirmation gate: taker flow must confirm entry direction.
            # 75% win rate with confirming flow vs 12% against (12-trade sample, 2026-02-08).
            # LONG requires buy ratio > 0.38 (at least 38% buying — not overwhelmed by sellers).
            # SHORT requires buy ratio < 0.62 (at least 38% selling).
            if orderflow_imbalance is not None:
                if direction == "LONG" and orderflow_imbalance < 0.38:
                    _count_reject("orderflow_confirm")
                    return None  # Dominant selling pressure contradicts LONG
                if direction == "SHORT" and orderflow_imbalance > 0.62:
                    _count_reject("orderflow_confirm")
                    return None  # Dominant buying pressure contradicts SHORT

            # Capitulation: logged at entry for data collection, NOT a blocking gate.
            # Sideways regime has low close ratios by nature — 0.5 threshold would
            # effectively disable SLBRS. Collect data first, gate later if warranted.
            # Original threshold: CAPITULATION_MIN_CONFIDENCE = 0.5 (preserved in class).
            # Debated 2026-02-11: pony-alpha + claude agreed — regime mismatch.

            # All retest conditions met -> propose ENTRY
            self._state[symbol] = SLBRSState.RETEST_ARMED

            # Diagnostic: log all gate values at entry time
            of_str = f"{orderflow_imbalance:.3f}" if orderflow_imbalance is not None else "None"
            print(f"[SLBRS-ENTRY-DIAG] {symbol}: atr={atr_width:.6f} min_atr={min_meaningful_atr:.6f} "
                  f"pen={zone_penetration.penetration_depth:.6f} persist={structural_persistence.total_persistence_duration:.1f}s "
                  f"bid=${bid_sz*price:,.0f} ask=${ask_sz*price:,.0f} minor=${minor_side_usd:,.0f} ratio={resting_ratio:.3f} "
                  f"oc_init={initial:.2f} oc_cons={consumed:.2f} abs_pct={absorption_pct*100:.1f}% "
                  f"of={of_str} fills={orderflow_fill_count} dir={direction} price={price:.4f} "
                  f"cap={capitulation_confidence:.2f}", flush=True)

            return StrategyProposal(
                strategy_id="EP2-SLBRS-V1",
                action_type="ENTRY",
                confidence="RETEST_CONDITIONS_MET",
                justification_ref="BLOCK_PERSISTENCE|ORDER_ABSORPTION|PROXIMITY",
                timestamp=context.timestamp,
                direction=direction
            )

        # No entry conditions met
        return None

    def _check_invalidation(
        self,
        symbol: str,
        regime_state: RegimeState,
        zone_penetration,
        price: float,
        context: StrategyContext
    ) -> Optional[StrategyProposal]:
        """
        Check for SLBRS invalidation (exit logic).

        Currently returns None (HOLD) — all exits handled by trailing stop
        and regime change. Kept as hook for future structural invalidation.

        Returns:
            None (HOLD) — no strategy-level exit conditions
        """
        # No strategy-level invalidation — exits are handled by:
        # 1. Trailing stop (registered on entry, follows price, PnL-based exit)
        # 2. Regime change → SLBRS stops proposing → trailing stop still active
        #
        # Previous PRICE_ACCEPTANCE check was removed: zone_penetration_depth measures
        # total depth in zone (always large at entry), not price movement since entry.
        # ATR invalidation was removed: redundant with regime classifier.
        return None

    def _generate_exit_proposal(
        self,
        reason: str,
        context: StrategyContext
    ) -> StrategyProposal:
        """
        Generate EXIT proposal with reason.

        Constitutional Compliance:
        - Exit based on structural invalidation
        - No claim about outcome quality
        - Reason is observational, not interpretive

        Args:
            reason: Structural reason for exit (REGIME_CHANGE, VOLATILITY_EXPANSION, etc.)
            context: Strategy context

        Returns:
            EXIT proposal
        """
        return StrategyProposal(
            strategy_id="EP2-SLBRS-V1",
            action_type="EXIT",
            confidence="INVALIDATED",  # Structural invalidation, not confidence
            justification_ref=f"SLBRS_EXIT|{reason}",
            timestamp=context.timestamp
        )

    def reset_state(self, symbol: str, timestamp: float = 0.0):
        """Reset SLBRS state for symbol (after exit or failure)."""
        if symbol in self._state:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            if timestamp > 0:
                self._last_exit_ts[symbol] = timestamp


# ==============================================================================
# Global Strategy Instance (Stateful)
# ==============================================================================

# Global instance maintains state across cycles
_slbrs_strategy = SLBRSStrategy()


def generate_slbrs_proposal(
    *,
    symbol: str,
    regime_state: Optional[RegimeState],
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence,
    price: float,
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None,
    absorption_event=None,  # AbsorptionEvent | None (B2.1 - orderbook absorption fallback)
    directional_continuity=None,  # DirectionalContinuity | None (B4 - trade flow validation)
    orderflow_imbalance: Optional[float] = None,  # Taker buy ratio 0-1 (from regime metrics)
    orderflow_fill_count: int = 0,  # Number of fills in orderflow window
    capitulation_confidence: float = 0.0  # CapitulationTracker confidence 0-1
) -> Optional[StrategyProposal]:
    """
    Generate SLBRS proposal (function interface for policy adapter).

    Constitutional Authority:
    - EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
    - Conditional execution: "When structure X, execute action Y"
    - Acknowledges outcome divergence (P12)

    Thresholds from Market Mechanics:
    - 30s persistence: Minimum block stability
    - 0.30 block width: Proximity threshold
    - Absorption requirement: Orderbook consumption indicator

    This function does NOT:
    - Assign confidence scores (numeric probabilities)
    - Claim certainty about outcomes
    - Predict future price movement
    - Rank primitive importance

    Args:
        symbol: Trading symbol
        regime_state: Current regime (must be SIDEWAYS_ACTIVE)
        zone_penetration: A6 primitive
        resting_size: Orderbook depth primitive
        order_consumption: Order consumption primitive
        structural_persistence: B2.1 primitive
        price: Current price
        context: Strategy context
        permission: M6 permission
        position_state: Current position state

    Returns:
        StrategyProposal if conditions met, None otherwise
    """
    return _slbrs_strategy.generate_proposal(
        symbol=symbol,
        regime_state=regime_state,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=price,
        context=context,
        permission=permission,
        position_state=position_state,
        absorption_event=absorption_event,
        directional_continuity=directional_continuity,
        orderflow_imbalance=orderflow_imbalance,
        orderflow_fill_count=orderflow_fill_count,
        capitulation_confidence=capitulation_confidence
    )
