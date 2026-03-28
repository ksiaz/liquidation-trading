"""
EP-2 Strategy: SLBRS (Sideways Liquidity Block Reaction System)

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)

Purpose:
Exploits absorption, negotiation, and inventory rebalancing in range-bound conditions.

Strategy Logic (from OB-SLBRSorderblockstrat.md):
1. Detect liquidity blocks (persistence ≥ 60s, resting imbalance ≥ 65%)
2. Observe first test (price enters block, aggressive volume, price rejects)
3. Wait for rejection displacement ≥ max(8 bps, 0.25 × ATR)
4. Enter on retest (reduced volume < 70%, reduced impact, absorption 65-95%)
5. Exit on invalidation (volatility expands, adverse orderflow, price acceptance)

State Machine: IDLE → FIRST_TEST_OBSERVED → REJECTION_CONFIRMED → ENTRY
- FIRST_TEST_OBSERVED: price tested block, waiting for rejection bounce
- REJECTION_CONFIRMED: price bounced away, waiting for return to block
- Entry requires: volume reduction, impact reduction, absorption, R:R ≥ 1.5

Thresholds from Market Mechanics (NOT backtest optimization):
- 0.55 resting imbalance: One side ≥ 55% of top-5 depth (directional wall)
- 120s persistence: Minimum block stability
- 0.65-0.95 absorption ratio: Orders consumed but block still standing
- 0.30 block width: Proximity threshold for retest
- 0.1% ATR floor: No entry when ATR < 0.1% of price
- $3k OC notional minimum: consumed_size × price_level must be significant
- $2k resting minor side minimum: filter microstructure noise
- 10s primitive cache + timestamp coherence: prevent mixed-age false confluence
- ALL primitives required: zone_penetration, structural_persistence, resting_size, order_consumption
- Max 3 concurrent SLBRS positions
- 5-minute post-exit cooldown, hard kill on ≥2 consecutive losses

CRITICAL: This strategy acknowledges outcome divergence (P12).
Same structure may lead to different outcomes. No confidence scoring.
"""

from collections import deque
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
    vwap_z: float = 0.0  # Signed z-score: (price - VWAP) / σ


# ==============================================================================
# SLBRS Internal State
# ==============================================================================

class SLBRSState(Enum):
    """SLBRS state machine states."""
    IDLE = auto()                    # No liquidity block detected
    FIRST_TEST_OBSERVED = auto()     # Block tested, waiting for rejection
    REJECTION_CONFIRMED = auto()     # Price bounced away, waiting for retest
    RETEST_ARMED = auto()            # Entry proposed, awaiting acceptance


@dataclass
class FirstTestObservation:
    """Records first test characteristics for retest comparison."""
    block_edge: float       # Block boundary price
    block_width: float      # Block price range (ATR at detection)
    test_volume: float      # Consumed volume during first test
    test_price_impact: float  # Zone penetration depth during test
    timestamp: float
    direction: str          # "LONG" or "SHORT" (from resting size)
    max_rejection: float = 0.0  # Max displacement in rejection direction
    beyond_block_since: Optional[float] = None  # When price first went beyond block
    non_sideways_accumulated: float = 0.0  # Total non-SIDEWAYS time (subtracted from wall-clock)
    last_regime_ts: float = 0.0            # Last time any processing happened (SIDEWAYS or not)


# ==============================================================================
# SLBRS Strategy Implementation
# ==============================================================================

class SLBRSStrategy:
    """
    Stateful SLBRS strategy implementation.

    Constitutional Compliance:
    - Thresholds from market mechanics (not backtest optimization)
    - Acknowledges outcome divergence (P12)
    - No confidence scoring
    - No certainty claims
    """

    # Max concurrent SLBRS positions
    MAX_CONCURRENT_POSITIONS = 3

    # Minimum cycles with valid order_consumption before allowing entry.
    MIN_OC_OBSERVATIONS = 20

    # Diagnostic logging interval (~30s at 5Hz)
    _DIAG_INTERVAL = 150

    # Maximum age (seconds) for cached OC/SP values.
    _OC_CACHE_MAX_AGE_SEC = 10.0

    # Maximum age gap (seconds) between OC and SP for timestamp coherence.
    _PRIMITIVE_COHERENCE_SEC = 10.0

    # Minimum notional consumed (consumed_size × price_level) for OC significance.
    # HL top-5 L2: meaningful test consumes $1k-$5k (Binance was $10k with deeper books).
    _MIN_OC_NOTIONAL_USD = 3_000.0

    # Capitulation confidence threshold (softer than cascade sniper's 0.7)
    CAPITULATION_MIN_CONFIDENCE = 0.5

    # ── A3: Rejection displacement ──────────────────────────────────
    # Design: abs(price − block_edge) ≥ max(25 bps, 0.75 × ATR(5m))
    # Must be a REAL bounce, not noise. At $87 SOL, 25bps = $0.22.
    # Previous 15bps let $0.14 rejections through → instant reversals.
    _REJECTION_MIN_BPS = 0.0025   # 25 basis points
    _REJECTION_ATR_MULT = 0.75    # 0.75 × ATR

    # ── A3: Price acceptance ────────────────────────────────────────
    # Block broken if price stays beyond for this long.
    # Raised from 10s: in sideways, 10s excursion at 3bps is noise.
    _ACCEPTANCE_TIMEOUT_SEC = 30.0

    # ── A4: Retest volume reduction ─────────────────────────────────
    # Retest consumed volume must be < 70% of first test volume.
    _RETEST_VOLUME_RATIO = 0.70

    # ── A5: Risk parameters ─────────────────────────────────────────
    _STOP_MIN_BPS = 0.0006   # 6 basis points
    _STOP_ATR_MULT = 0.30    # 0.30 × ATR
    _MIN_RR = 1.5            # Minimum reward:risk ratio

    # ── Timing ──────────────────────────────────────────────────────
    _FIRST_TEST_TIMEOUT_SEC = 60.0   # Max wait for rejection after first test
    _ENTRY_TIMEOUT_SEC = 120.0       # Max time from first test to entry
    _COOLDOWN_SEC = 300.0            # 5 minutes post-exit cooldown (design spec)

    # ── Section 7: Fail-safes ───────────────────────────────────────
    _MAX_CONSECUTIVE_LOSSES = 3      # Hard kill per symbol (raised from 2: with wider thresholds, allow more attempts)
    _MAX_GLOBAL_CONSECUTIVE_LOSSES = 5  # Hard kill across all symbols
    _MIN_WINRATE = 0.35              # Structural failure threshold
    _WINRATE_SAMPLE_SIZE = 20        # Sample window for winrate check

    # ── A6: Invalidation thresholds ─────────────────────────────────
    # Matches classifier SIDEWAYS hold threshold — if classifier would exit
    # SIDEWAYS, invalidate immediately (faster than regime debounce).
    _INVALIDATION_ATR_RATIO = 0.95

    # ── Regime grace period ────────────────────────────────────────
    # Non-SIDEWAYS blip shorter than this preserves state machine progress.
    # BTC flickers SIDEWAYS↔DISABLED every ~10s — 30s survives that.
    _REGIME_GRACE_SEC = 30.0

    def __init__(self):
        """Initialize SLBRS strategy with empty state."""
        self._state: Dict[str, SLBRSState] = {}
        self._first_test: Dict[str, Optional[FirstTestObservation]] = {}
        self._sideways_streak: Dict[str, int] = {}
        self._last_exit_ts: Dict[str, float] = {}
        self._open_symbols: set = set()
        self._oc_seen: Dict[str, int] = {}
        self._diag_counter: Dict[str, int] = {}
        self._oc_cache: Dict[str, tuple] = {}
        self._sp_cache: Dict[str, tuple] = {}
        # Gate rejection tracking
        self._gate_rejections: Dict[str, int] = {}
        self._gate_rejections_total: int = 0
        self._last_gate_log_ts: float = 0.0
        # Position tracking for invalidation (A6)
        self._entry_info: Dict[str, dict] = {}     # Set when ENTRY proposed
        self._position_info: Dict[str, dict] = {}   # Set when position first OPEN
        # Trade result tracking (Section 7)
        self._consecutive_losses: Dict[str, int] = {}
        self._global_consecutive_losses: int = 0
        self._trade_results: deque = deque(maxlen=20)
        # Last SIDEWAYS timestamp per symbol (for regime grace period)
        self._last_sideways_ts: Dict[str, float] = {}

    def _count_reject(self, gate_name: str):
        """Record gate rejection for frequency analysis."""
        self._gate_rejections[gate_name] = self._gate_rejections.get(gate_name, 0) + 1
        self._gate_rejections_total += 1

    def generate_proposal(
        self,
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
        absorption_event=None,
        directional_continuity=None,
        orderflow_imbalance: Optional[float] = None,
        orderflow_fill_count: int = 0,
        capitulation_confidence: float = 0.0,
        wall_status=None
    ) -> Optional[StrategyProposal]:
        """
        Generate SLBRS proposal based on current market structure.

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
            # Grace period: preserve state machine if SIDEWAYS was recent
            current_state = self._state.get(symbol, SLBRSState.IDLE)
            if current_state in (SLBRSState.FIRST_TEST_OBSERVED,
                                 SLBRSState.REJECTION_CONFIRMED):
                last_sw = self._last_sideways_ts.get(symbol, 0.0)
                if last_sw > 0 and (context.timestamp - last_sw) <= self._REGIME_GRACE_SEC:
                    # Within grace — preserve state, accumulate non-SIDEWAYS time
                    ft = self._first_test.get(symbol)
                    if ft is not None and ft.last_regime_ts > 0:
                        ft.non_sideways_accumulated += (context.timestamp - ft.last_regime_ts)
                        ft.last_regime_ts = context.timestamp
                    return None
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
            return None

        # Track consecutive SIDEWAYS cycles for regime stability
        self._sideways_streak[symbol] = self._sideways_streak.get(symbol, 0) + 1
        self._last_sideways_ts[symbol] = context.timestamp

        # Track position transitions
        was_open = symbol in self._open_symbols

        # Rule 3: Check position state
        if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
            self._open_symbols.add(symbol)

            # Record position info on first observation of open position
            if symbol not in self._position_info and symbol in self._entry_info:
                self._position_info[symbol] = {
                    **self._entry_info.pop(symbol),
                    'entry_price': price,
                    'beyond_block_since': None,
                }

            # Reset state machine so it's ready after exit
            if self._state[symbol] == SLBRSState.RETEST_ARMED:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None

            return self._check_invalidation(
                symbol=symbol,
                regime_state=regime_state,
                price=price,
                context=context,
                orderflow_imbalance=orderflow_imbalance,
            )

        # Rule 4: Position FLAT - check for entry opportunity
        if position_state == PositionState.FLAT or position_state is None:
            # Detect exit: was open, now flat
            if was_open:
                self._record_exit(symbol, price, context.timestamp)

            self._open_symbols.discard(symbol)

            # Clean up stale entry info
            if self._state[symbol] == SLBRSState.RETEST_ARMED:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
                self._entry_info.pop(symbol, None)
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

        return None

    def _record_exit(self, symbol: str, exit_price: float, timestamp: float):
        """Record trade result on position exit for fail-safe tracking."""
        info = self._position_info.pop(symbol, None)
        if info is None:
            return

        direction = info.get('direction', 'LONG')
        entry_price = info.get('entry_price', exit_price)

        if direction == "LONG":
            is_win = exit_price > entry_price
        else:
            is_win = exit_price < entry_price

        if is_win:
            self._consecutive_losses[symbol] = 0
            self._global_consecutive_losses = 0
        else:
            self._consecutive_losses[symbol] = self._consecutive_losses.get(symbol, 0) + 1
            self._global_consecutive_losses += 1

        self._trade_results.append(is_win)
        self._last_exit_ts[symbol] = timestamp

    def rebuild_from_history(self, exit_rows):
        """Rebuild kill-switch state from ghost_trades exit rows.

        Called at startup to persist kill-switch across restarts.

        Args:
            exit_rows: List of (symbol, pnl) tuples, ordered oldest->newest.
        """
        self._consecutive_losses.clear()
        self._global_consecutive_losses = 0
        self._trade_results.clear()

        for symbol, pnl in exit_rows:
            is_win = pnl is not None and pnl > 0
            if is_win:
                self._consecutive_losses[symbol] = 0
                self._global_consecutive_losses = 0
            else:
                self._consecutive_losses[symbol] = self._consecutive_losses.get(symbol, 0) + 1
                self._global_consecutive_losses += 1
            self._trade_results.append(is_win)

        if exit_rows:
            total = len(exit_rows)
            wins = sum(1 for _, p in exit_rows if p and p > 0)
            per_sym = {s: c for s, c in self._consecutive_losses.items() if c > 0}
            print(f"[SLBRS] Rebuilt kill-switch from {total} trades: "
                  f"{wins}W/{total-wins}L, global_consec={self._global_consecutive_losses}, "
                  f"per_sym={per_sym}")

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
        Check for SLBRS entry opportunity.

        State machine:
        - IDLE: detect block, record first test → FIRST_TEST_OBSERVED
        - FIRST_TEST_OBSERVED: wait for rejection bounce → REJECTION_CONFIRMED
        - REJECTION_CONFIRMED: wait for retest with reduced volume/impact → ENTRY
        """
        # Diagnostic counter
        self._diag_counter[symbol] = self._diag_counter.get(symbol, 0) + 1
        _diag = self._diag_counter[symbol] % self._DIAG_INTERVAL == 0

        if _diag and capitulation_confidence > 0.0:
            print(f"[SLBRS-DIAG] {symbol}: cap={capitulation_confidence:.2f}", flush=True)

        # ======================================================================
        # TRANSIENT PRIMITIVE CACHE: OC and SP flicker between cycles.
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

        # OC warmup tracking (count cycles with valid OC for data convergence)
        if order_consumption is not None:
            self._oc_seen[symbol] = self._oc_seen.get(symbol, 0) + 1

        # ======================================================================
        # NON-IDLE STATE HANDLING (before primitive gates)
        # These states only need price for rejection/proximity tracking.
        # ======================================================================
        current_state = self._state.get(symbol, SLBRSState.IDLE)

        if current_state == SLBRSState.FIRST_TEST_OBSERVED:
            return self._track_rejection(symbol, price, context)

        if current_state == SLBRSState.REJECTION_CONFIRMED:
            return self._check_retest_entry(
                symbol, price, context, order_consumption, zone_penetration,
                regime_state, directional_continuity, orderflow_imbalance,
                orderflow_fill_count, wall_status=wall_status
            )

        # ======================================================================
        # IDLE STATE: full primitive check + block detection
        # ======================================================================

        # Primitive presence: ALL must be present. No fallbacks.
        _reject = None
        if zone_penetration is None:
            _reject = "zone_pen=None"
        elif structural_persistence is None:
            _reject = "struct_persist=None"
        elif resting_size is None:
            _reject = "resting_sz=None"
        elif order_consumption is None:
            _reject = "order_cons=None"

        if _reject:
            self._count_reject("primitives_missing")
            if _diag:
                _missing = []
                if zone_penetration is None: _missing.append("zp")
                if structural_persistence is None: _missing.append("sp")
                if resting_size is None: _missing.append("rs")
                if order_consumption is None: _missing.append("oc")
                print(f"[SLBRS-DIAG] {symbol}: primitives_missing={'+'.join(_missing)}")
            return None

        # Data quality gate: L2 data must have converged
        if self._oc_seen.get(symbol, 0) < self.MIN_OC_OBSERVATIONS:
            self._count_reject("oc_warmup")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: oc_warmup={self._oc_seen.get(symbol, 0)}/{self.MIN_OC_OBSERVATIONS}")
            return None

        # ATR gate: use atr_30m (stable session measure) for pass/fail
        min_meaningful_atr = price * 0.001
        if regime_state.atr_30m < min_meaningful_atr:
            self._count_reject("atr_low")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: atr_low atr30={regime_state.atr_30m:.4f}<{min_meaningful_atr:.4f} (atr5={regime_state.atr_5m:.4f})")
            return None
        # Sizing: floor atr_5m at 30% of atr_30m to prevent meaningless block widths
        atr_width = max(regime_state.atr_5m, regime_state.atr_30m * 0.3)

        # Block detection gates
        if structural_persistence.total_persistence_duration < 120.0:
            self._count_reject("persist_low")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: persist={structural_persistence.total_persistence_duration:.1f}s<120s")
            return None

        # Resting size: directional wall
        bid_sz = getattr(resting_size, 'bid_size', 0) or 0
        ask_sz = getattr(resting_size, 'ask_size', 0) or 0
        total_resting = bid_sz + ask_sz
        if total_resting <= 0:
            self._count_reject("resting_empty")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: resting_empty")
            return None

        resting_ratio = max(bid_sz, ask_sz) / total_resting
        if resting_ratio < 0.55:
            self._count_reject("resting_ratio")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: resting_ratio={resting_ratio:.2f}<0.55 bid={bid_sz:.1f} ask={ask_sz:.1f}")
            return None

        MIN_MINOR_SIDE_USD = 2000.0
        minor_side_usd = min(bid_sz, ask_sz) * price
        if minor_side_usd < MIN_MINOR_SIDE_USD:
            self._count_reject("minor_usd")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: minor_usd=${minor_side_usd:.0f}<${MIN_MINOR_SIDE_USD:.0f}")
            return None

        # Direction from resting size imbalance
        direction = "LONG" if bid_sz > ask_sz else "SHORT"

        # Regime stability gate (4+ consecutive SIDEWAYS cycles)
        if self._sideways_streak.get(symbol, 0) < 4:
            self._count_reject("sideways_streak")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: sideways_streak={self._sideways_streak.get(symbol, 0)}<4")
            return None

        # Max concurrent SLBRS positions
        if len(self._open_symbols) >= self.MAX_CONCURRENT_POSITIONS:
            self._count_reject("max_positions")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: max_positions={len(self._open_symbols)}>={self.MAX_CONCURRENT_POSITIONS}")
            return None

        # Post-exit cooldown (5 minutes — design spec Section 7)
        last_exit = self._last_exit_ts.get(symbol, 0.0)
        if last_exit > 0 and context.timestamp - last_exit < self._COOLDOWN_SEC:
            self._count_reject("cooldown")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: cooldown={context.timestamp - last_exit:.0f}s<{self._COOLDOWN_SEC:.0f}s")
            return None

        # Hard kill: consecutive losses per symbol (Section 7)
        if self._consecutive_losses.get(symbol, 0) >= self._MAX_CONSECUTIVE_LOSSES:
            self._count_reject("consecutive_losses")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: consecutive_losses={self._consecutive_losses[symbol]}>={self._MAX_CONSECUTIVE_LOSSES}")
            return None

        # Hard kill: global consecutive losses across all symbols (Section 7)
        if self._global_consecutive_losses >= self._MAX_GLOBAL_CONSECUTIVE_LOSSES:
            self._count_reject("global_consecutive_losses")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: global_consecutive_losses={self._global_consecutive_losses}>={self._MAX_GLOBAL_CONSECUTIVE_LOSSES}")
            return None

        # Structural failure: winrate check (Section 7)
        if len(self._trade_results) >= self._WINRATE_SAMPLE_SIZE:
            winrate = sum(self._trade_results) / len(self._trade_results)
            if winrate < self._MIN_WINRATE:
                self._count_reject("winrate_low")
                if _diag:
                    print(f"[SLBRS-DIAG] {symbol}: winrate={winrate:.2f}<{self._MIN_WINRATE}")
                return None

        # Timestamp coherence: OC and SP must be from similar times
        oc_ts = getattr(order_consumption, 'timestamp', 0) or 0
        sp_ts = getattr(structural_persistence, 'timestamp', 0) or 0
        if oc_ts > 0 and sp_ts > 0 and abs(oc_ts - sp_ts) > self._PRIMITIVE_COHERENCE_SEC:
            self._count_reject("coherence_gap")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: coherence_gap OC-SP={abs(oc_ts - sp_ts):.1f}s>{self._PRIMITIVE_COHERENCE_SEC}s")
            return None

        # Test volume required (for retest comparison) — notional minimum
        first_consumed = getattr(order_consumption, 'consumed_size', 0) or 0.0
        oc_price = getattr(order_consumption, 'price_level', 0) or price
        first_consumed_notional = first_consumed * oc_price
        if first_consumed <= 0 or first_consumed_notional < self._MIN_OC_NOTIONAL_USD:
            self._count_reject("no_test_volume")
            if _diag:
                print(f"[SLBRS-DIAG] {symbol}: no_test_volume (notional=${first_consumed_notional:.0f}<${self._MIN_OC_NOTIONAL_USD:.0f})")
            return None

        # ======================================================================
        # RECORD FIRST TEST → FIRST_TEST_OBSERVED
        # A3: Price has entered block. Record metrics for retest comparison.
        # No entry on first test — wait for rejection displacement.
        # ======================================================================
        self._first_test[symbol] = FirstTestObservation(
            block_edge=price,
            block_width=atr_width,
            test_volume=first_consumed,
            test_price_impact=zone_penetration.penetration_depth,
            timestamp=context.timestamp,
            direction=direction,
            non_sideways_accumulated=0.0,
            last_regime_ts=context.timestamp,
        )
        self._state[symbol] = SLBRSState.FIRST_TEST_OBSERVED

        if _diag:
            print(f"[SLBRS-DIAG] {symbol}: FIRST_TEST dir={direction} "
                  f"edge={price:.4f} vol={first_consumed:.1f} "
                  f"impact={zone_penetration.penetration_depth:.4f}", flush=True)

        return None  # No entry on first test

    def _track_rejection(
        self,
        symbol: str,
        price: float,
        context: StrategyContext
    ) -> Optional[StrategyProposal]:
        """
        FIRST_TEST_OBSERVED state: track rejection displacement.

        Design A3: Price must bounce away by max(8 bps, 0.25 × ATR).
        If price accepts through block (>10s beyond), block is broken → IDLE.
        """
        first_test = self._first_test.get(symbol)
        if first_test is None:
            self._state[symbol] = SLBRSState.IDLE
            return None

        # Update regime tracking timestamp
        first_test.last_regime_ts = context.timestamp

        # Effective elapsed = wall-clock minus accumulated non-SIDEWAYS time
        wall_elapsed = context.timestamp - first_test.timestamp
        effective_elapsed = wall_elapsed - first_test.non_sideways_accumulated

        if effective_elapsed > self._FIRST_TEST_TIMEOUT_SEC:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            self._count_reject("rejection_timeout")
            return None

        # Safety: 3× wall-clock cap prevents zombie observations
        if wall_elapsed > self._FIRST_TEST_TIMEOUT_SEC * 3:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            self._count_reject("wall_clock_timeout")
            return None

        # Displacement in rejection direction
        if first_test.direction == "LONG":
            # LONG: block is support below. Rejection = price bounces UP.
            rejection_disp = price - first_test.block_edge
            beyond = price < first_test.block_edge * (1 - 0.0015)
        else:
            # SHORT: block is resistance above. Rejection = price bounces DOWN.
            rejection_disp = first_test.block_edge - price
            beyond = price > first_test.block_edge * (1 + 0.0015)

        # Track max rejection displacement
        if rejection_disp > first_test.max_rejection:
            first_test.max_rejection = rejection_disp

        # Price acceptance detection (block broken)
        if beyond:
            if first_test.beyond_block_since is None:
                first_test.beyond_block_since = context.timestamp
            elif context.timestamp - first_test.beyond_block_since >= self._ACCEPTANCE_TIMEOUT_SEC:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
                self._count_reject("block_accepted")
                return None
        else:
            first_test.beyond_block_since = None

        # Check rejection threshold: max(25 bps, 0.75 × ATR)
        # BOTH conditions: peak displacement exceeded threshold AND price is
        # currently displaced (not a one-tick spike that already reversed).
        rejection_threshold = max(
            first_test.block_edge * self._REJECTION_MIN_BPS,
            self._REJECTION_ATR_MULT * first_test.block_width
        )

        if (first_test.max_rejection >= rejection_threshold
                and rejection_disp >= rejection_threshold * 0.5):
            self._state[symbol] = SLBRSState.REJECTION_CONFIRMED
            print(f"[SLBRS-REJECTION] {symbol}: dir={first_test.direction} "
                  f"displacement={first_test.max_rejection:.6f} "
                  f"current={rejection_disp:.6f} "
                  f"threshold={rejection_threshold:.6f} "
                  f"elapsed={effective_elapsed:.1f}s", flush=True)

        return None

    def _check_retest_entry(
        self,
        symbol: str,
        price: float,
        context: StrategyContext,
        order_consumption,
        zone_penetration,
        regime_state: RegimeState,
        directional_continuity,
        orderflow_imbalance: Optional[float],
        orderflow_fill_count: int,
        wall_status=None
    ) -> Optional[StrategyProposal]:
        """
        REJECTION_CONFIRMED state: check for retest entry.

        Design A4: Volume reduction, impact reduction, absorption, R:R ≥ 1.5.
        """
        first_test = self._first_test.get(symbol)
        if first_test is None:
            self._state[symbol] = SLBRSState.IDLE
            return None

        # Update regime tracking timestamp
        first_test.last_regime_ts = context.timestamp

        # Effective elapsed = wall-clock minus accumulated non-SIDEWAYS time
        wall_elapsed = context.timestamp - first_test.timestamp
        effective_elapsed = wall_elapsed - first_test.non_sideways_accumulated

        if effective_elapsed > self._ENTRY_TIMEOUT_SEC:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            self._count_reject("retest_timeout")
            return None

        # Safety: 3× wall-clock cap prevents zombie observations
        if wall_elapsed > self._ENTRY_TIMEOUT_SEC * 3:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            self._count_reject("wall_clock_timeout")
            return None

        # Price acceptance check (block broken during retest wait)
        if first_test.direction == "LONG":
            beyond = price < first_test.block_edge * (1 - 0.0015)
        else:
            beyond = price > first_test.block_edge * (1 + 0.0015)

        if beyond:
            if first_test.beyond_block_since is None:
                first_test.beyond_block_since = context.timestamp
            elif context.timestamp - first_test.beyond_block_since >= self._ACCEPTANCE_TIMEOUT_SEC:
                self._state[symbol] = SLBRSState.IDLE
                self._first_test[symbol] = None
                self._count_reject("block_accepted_retest")
                return None
        else:
            first_test.beyond_block_since = None

        # Max concurrent positions
        if len(self._open_symbols) >= self.MAX_CONCURRENT_POSITIONS:
            self._count_reject("max_positions")
            return None

        # A4: Proximity — price near block edge (30% of block width)
        distance_to_block = abs(price - first_test.block_edge)
        proximity_threshold = 0.30 * first_test.block_width
        if distance_to_block > proximity_threshold:
            return None  # Not near block yet — wait

        # Need OC data for volume comparison and absorption
        if order_consumption is None:
            self._count_reject("retest_no_oc")
            return None

        initial = getattr(order_consumption, 'initial_size', 0) or 0
        consumed = getattr(order_consumption, 'consumed_size', 0) or 0

        if initial <= 0:
            self._count_reject("retest_no_initial")
            return None

        # A4: Volume reduction — consumed < 70% of first test volume
        # Also require minimum retest volume (>5% of first test) to filter
        # "ghost retests" where price drifts back with zero aggression.
        if first_test.test_volume > 0:
            vol_ratio = consumed / first_test.test_volume
            if vol_ratio >= self._RETEST_VOLUME_RATIO:
                self._count_reject("volume_reduction")
                return None
            if vol_ratio < 0.05:
                self._count_reject("retest_vol_too_low")
                return None

        # A4: Impact reduction — penetration < first test impact
        if zone_penetration is not None and first_test.test_price_impact > 0:
            if zone_penetration.penetration_depth >= first_test.test_price_impact:
                self._count_reject("impact_reduction")
                return None

        # A4: Absorption 65-95% (block holding but orders consumed)
        absorption_pct = consumed / initial
        if absorption_pct < 0.65 or absorption_pct > 0.95:
            self._count_reject("absorption_range")
            return None

        # A5: R:R ≥ 1.5 (stop vs VWAP target)
        atr_5m = regime_state.atr_5m if regime_state else first_test.block_width
        stop_distance = max(price * self._STOP_MIN_BPS, self._STOP_ATR_MULT * atr_5m)
        target_distance = regime_state.vwap_distance if regime_state else stop_distance * 2
        if stop_distance > 0 and target_distance / stop_distance < self._MIN_RR:
            self._count_reject("rr_low")
            return None

        direction = first_test.direction

        # Directional continuity gate
        if directional_continuity is not None and directional_continuity.total_trades > 0:
            buy_ratio = directional_continuity.buy_trades / directional_continuity.total_trades
            if direction == "LONG" and buy_ratio < 0.4:
                self._count_reject("dir_continuity")
                return None
            if direction == "SHORT" and buy_ratio > 0.6:
                self._count_reject("dir_continuity")
                return None

        # Orderflow gates
        MIN_ORDERFLOW_FILLS = 25
        if orderflow_fill_count < MIN_ORDERFLOW_FILLS:
            self._count_reject("orderflow_fills")
            return None

        if orderflow_imbalance is not None:
            if orderflow_imbalance < 0.10 or orderflow_imbalance > 0.90:
                self._count_reject("orderflow_extreme")
                return None
            if direction == "LONG" and orderflow_imbalance < 0.38:
                self._count_reject("orderflow_confirm")
                return None
            if direction == "SHORT" and orderflow_imbalance > 0.62:
                self._count_reject("orderflow_confirm")
                return None

        # ======================================================================
        # ALL RETEST CONDITIONS MET → ENTRY
        # ======================================================================
        self._state[symbol] = SLBRSState.RETEST_ARMED
        self._entry_info[symbol] = {
            'block_edge': first_test.block_edge,
            'direction': direction,
        }

        # Entry diagnostic
        vol_ratio_str = f"{consumed/first_test.test_volume:.2f}" if first_test.test_volume > 0 else "N/A"
        impact_str = ""
        if zone_penetration and first_test.test_price_impact > 0:
            impact_str = f"impact={zone_penetration.penetration_depth:.4f}/{first_test.test_price_impact:.4f} "
        of_str = f"{orderflow_imbalance:.3f}" if orderflow_imbalance is not None else "None"
        rr = target_distance / stop_distance if stop_distance > 0 else 0
        vwap_z_val = regime_state.vwap_z if regime_state else 0.0
        # Wall status shadow logging
        _wall_info = "none"
        _wall_gold = False
        if wall_status:
            _wall_info = (f"consec={wall_status.consecutive_reversals} "
                         f"ob={wall_status.is_ob} prior={wall_status.prior_reversals} "
                         f"gold={wall_status.gold_signal} grav={wall_status.total_gravity:,.0f}")
            _wall_gold = wall_status.gold_signal

        print(f"[SLBRS-WALL] {symbol}: {_wall_info}", flush=True)

        # TODO: When ready to gate, uncomment:
        # if not _wall_gold:
        #     self._count_reject("wall_not_gold")
        #     return None

        print(f"[SLBRS-ENTRY-DIAG] {symbol}: dir={direction} "
              f"block_edge={first_test.block_edge:.4f} "
              f"rejection={first_test.max_rejection:.6f} "
              f"vol_ratio={vol_ratio_str} {impact_str}"
              f"abs={absorption_pct*100:.1f}% of={of_str} fills={orderflow_fill_count} "
              f"rr={rr:.2f} vwap_z={vwap_z_val:+.2f} price={price:.4f}", flush=True)

        return StrategyProposal(
            strategy_id="EP2-SLBRS-V1",
            action_type="ENTRY",
            confidence="RETEST_CONDITIONS_MET",
            justification_ref="BLOCK_REJECTION|VOLUME_REDUCTION|ORDER_ABSORPTION",
            timestamp=context.timestamp,
            direction=direction
        )

    def _check_invalidation(
        self,
        symbol: str,
        regime_state: RegimeState,
        price: float,
        context: StrategyContext,
        orderflow_imbalance: Optional[float] = None,
    ) -> Optional[StrategyProposal]:
        """
        Check A6 invalidation conditions for open positions.

        Exit immediately if:
        - Volatility expands (ATR ratio ≥ 0.95 — matches classifier hold threshold)
        - Adverse orderflow (strong flow against position direction)
        - Price accepts through block (beyond block edge for >10s)
        """
        info = self._position_info.get(symbol)

        # A6: Volatility expansion (no position info needed)
        if regime_state and regime_state.atr_5m > 0 and regime_state.atr_30m > 0:
            if regime_state.atr_5m / regime_state.atr_30m >= self._INVALIDATION_ATR_RATIO:
                print(f"[SLBRS-INVALIDATION] {symbol}: VOLATILITY_EXPANSION "
                      f"atr_ratio={regime_state.atr_5m/regime_state.atr_30m:.2f}", flush=True)
                return self._generate_exit_proposal("VOLATILITY_EXPANSION", context)

        if info is None:
            return None

        direction = info.get('direction', 'LONG')

        # A6: Adverse orderflow (strong flow against position)
        if orderflow_imbalance is not None:
            if direction == "LONG" and orderflow_imbalance < 0.10:
                print(f"[SLBRS-INVALIDATION] {symbol}: ORDERFLOW_ADVERSE "
                      f"of={orderflow_imbalance:.3f} dir={direction}", flush=True)
                return self._generate_exit_proposal("ORDERFLOW_ADVERSE", context)
            if direction == "SHORT" and orderflow_imbalance > 0.90:
                print(f"[SLBRS-INVALIDATION] {symbol}: ORDERFLOW_ADVERSE "
                      f"of={orderflow_imbalance:.3f} dir={direction}", flush=True)
                return self._generate_exit_proposal("ORDERFLOW_ADVERSE", context)

        # A6: Price accepts through block (beyond block edge for >10s)
        block_edge = info.get('block_edge')
        if block_edge:
            if direction == "LONG":
                beyond = price < block_edge * (1 - 0.0015)
            else:
                beyond = price > block_edge * (1 + 0.0015)

            if beyond:
                if info.get('beyond_block_since') is None:
                    info['beyond_block_since'] = context.timestamp
                elif context.timestamp - info['beyond_block_since'] >= self._ACCEPTANCE_TIMEOUT_SEC:
                    print(f"[SLBRS-INVALIDATION] {symbol}: PRICE_ACCEPTANCE "
                          f"block_edge={block_edge:.4f} price={price:.4f} "
                          f"dir={direction}", flush=True)
                    return self._generate_exit_proposal("PRICE_ACCEPTANCE", context)
            else:
                info['beyond_block_since'] = None

        return None

    def _generate_exit_proposal(
        self,
        reason: str,
        context: StrategyContext
    ) -> StrategyProposal:
        """Generate EXIT proposal with structural reason."""
        return StrategyProposal(
            strategy_id="EP2-SLBRS-V1",
            action_type="EXIT",
            confidence="INVALIDATED",
            justification_ref=f"SLBRS_EXIT|{reason}",
            timestamp=context.timestamp
        )

    def reset_state(self, symbol: str, timestamp: float = 0.0):
        """Reset SLBRS state for symbol (after exit or failure)."""
        if symbol in self._state:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None
            self._entry_info.pop(symbol, None)
            if timestamp > 0:
                self._last_exit_ts[symbol] = timestamp


# ==============================================================================
# Global Strategy Instance (Stateful)
# ==============================================================================

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
    absorption_event=None,
    directional_continuity=None,
    orderflow_imbalance: Optional[float] = None,
    orderflow_fill_count: int = 0,
    capitulation_confidence: float = 0.0,
    wall_status=None
) -> Optional[StrategyProposal]:
    """
    Generate SLBRS proposal (function interface for policy adapter).

    Constitutional Authority:
    - EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
    - Conditional execution: "When structure X, execute action Y"
    - Acknowledges outcome divergence (P12)
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
        capitulation_confidence=capitulation_confidence,
        wall_status=wall_status
    )
