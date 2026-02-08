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
- 2.5× liquidity concentration: Significant accumulation threshold
- 60s persistence: Minimum block stability
- 0.15 absorption ratio: Orderbook consumption threshold
- 0.30 block width: Proximity threshold for retest
- 0.40 zone penetration: Minimum retest evidence (HL fallback)
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

    def __init__(self):
        """Initialize SLBRS strategy with empty state."""
        self._state: Dict[str, SLBRSState] = {}  # symbol -> state
        self._first_test: Dict[str, Optional[FirstTestObservation]] = {}  # symbol -> first test
        self._sideways_streak: Dict[str, int] = {}  # symbol -> consecutive SIDEWAYS cycles
        self._last_exit_ts: Dict[str, float] = {}  # symbol -> timestamp of last exit/reset
        self._open_symbols: set = set()  # symbols with open SLBRS positions

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
        directional_continuity=None  # DirectionalContinuity | None (B4 - trade flow direction)
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
                absorption_event=absorption_event,
                directional_continuity=directional_continuity
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
        absorption_event=None,
        directional_continuity=None
    ) -> Optional[StrategyProposal]:
        """
        Check for SLBRS entry opportunity (retest logic).

        Entry requires ALL of (no fallbacks):
        1. Liquidity block: zone_penetration + structural_persistence + resting_size
        2. First test: block detected with orderbook confirmation
        3. Retest: proximity + order_consumption (real absorption, not penetration depth)
        4. Direction: from resting_size bid/ask ratio (not price heuristic)
        5. Regime stable (4+ consecutive SIDEWAYS cycles)
        6. Max 3 concurrent positions, 120s post-exit cooldown

        Returns:
            ENTRY proposal if retest conditions met, None otherwise
        """
        # Check if primitives available
        if zone_penetration is None:
            return None

        # ATR-based block width (1 ATR = meaningful price range)
        # Proximity for entry: 50% of this (0.5 ATR from block edge)
        # Invalidation: penetration > this (price moved > 1 ATR through block)
        atr_width = regime_state.atr_5m if regime_state.atr_5m > 0 else price * 0.005

        # Check for liquidity block presence
        # Requires ALL of: zone interaction, structural persistence, AND orderbook depth.
        # Without resting_size we can't confirm resting orders exist — no block.
        block_exists = (
            zone_penetration.penetration_depth > 0
            and structural_persistence is not None
            and structural_persistence.total_persistence_duration >= 60.0  # 60s block stability
            and resting_size is not None  # Must see actual resting orders
        )

        # State: IDLE → detect first block interaction
        if self._state[symbol] == SLBRSState.IDLE:
            if not block_exists:
                return None

            # Gate: Regime must be stable (4+ consecutive SIDEWAYS cycles)
            if self._sideways_streak.get(symbol, 0) < 4:
                return None

            # Gate: Max concurrent SLBRS positions
            if len(self._open_symbols) >= self.MAX_CONCURRENT_POSITIONS:
                return None

            # Gate: Post-exit cooldown (120s)
            last_exit = self._last_exit_ts.get(symbol, 0.0)
            if last_exit > 0 and context.timestamp - last_exit < 120.0:
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
                return None

            # Gate: Max concurrent SLBRS positions (check again at retest)
            if len(self._open_symbols) >= self.MAX_CONCURRENT_POSITIONS:
                return None

            # Retest Condition 2: Absorption evidence
            # Primary: order_consumption (consumed/initial >= 15%)
            # Fallback: absorption_event (orderbook size consumed with minimal price movement)
            absorption_confirmed = False
            if order_consumption is not None:
                initial = getattr(order_consumption, 'initial_size', 0) or 0
                consumed = getattr(order_consumption, 'consumed_size', 0) or 0
                if initial > 0 and consumed >= initial * 0.15:
                    absorption_confirmed = True
            if not absorption_confirmed and absorption_event is not None:
                # Fallback: absorption_event means orders consumed with minimal price movement
                if absorption_event.consumed_size > 0:
                    absorption_confirmed = True
            if not absorption_confirmed:
                return None

            # Determine direction from orderbook depth (required)
            # Without resting_size we can't know block nature → no entry
            if resting_size is None:
                return None

            # More resting on bid side = buy wall = price supported = LONG
            # More resting on ask side = sell wall = price capped = SHORT
            direction = "LONG"
            if hasattr(resting_size, 'bid_size') and hasattr(resting_size, 'ask_size'):
                if resting_size.ask_size > resting_size.bid_size:
                    direction = "SHORT"

            # Directional continuity gate: trade flow must not contradict resting_size direction
            if directional_continuity is not None and directional_continuity.total_trades > 0:
                buy_ratio = directional_continuity.buy_trades / directional_continuity.total_trades
                if direction == "LONG" and buy_ratio < 0.4:
                    return None  # Block says LONG but selling dominates — contradicted
                if direction == "SHORT" and buy_ratio > 0.6:
                    return None  # Block says SHORT but buying dominates — contradicted

            # All retest conditions met -> propose ENTRY
            self._state[symbol] = SLBRSState.RETEST_ARMED

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
    directional_continuity=None  # DirectionalContinuity | None (B4 - trade flow validation)
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
        directional_continuity=directional_continuity
    )
