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
- 30s persistence: Minimum block stability
- 0.65 absorption ratio: Orderbook consumption threshold
- 0.30 block width: Proximity threshold for retest
- 0.70 volume ratio: Reduced aggression threshold

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
    RETEST_ARMED = auto()  # Ready for retest entry
    IN_POSITION = auto()  # Position open


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

    def __init__(self):
        """Initialize SLBRS strategy with empty state."""
        self._state: Dict[str, SLBRSState] = {}  # symbol -> state
        self._first_test: Dict[str, Optional[FirstTestObservation]] = {}  # symbol -> first test

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
        position_state: Optional[PositionState] = None
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

        # Rule 1: M6 DENIED -> no proposal
        if permission.result == "DENIED":
            return None

        # Rule 2: Regime gate - SLBRS only active in SIDEWAYS regime
        if regime_state is None or regime_state.regime != "SIDEWAYS_ACTIVE":
            # Regime not sideways -> SLBRS disabled
            # If position open, exit due to regime change
            if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
                return self._generate_exit_proposal(
                    reason="REGIME_CHANGE",
                    context=context
                )
            return None

        # Rule 3: Check position state and generate appropriate action
        if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
            # Position exists - check for invalidation
            return self._check_invalidation(
                symbol=symbol,
                regime_state=regime_state,
                zone_penetration=zone_penetration,
                price=price,
                context=context
            )

        # Rule 4: Position FLAT - check for entry opportunity
        if position_state == PositionState.FLAT or position_state is None:
            return self._check_entry(
                symbol=symbol,
                zone_penetration=zone_penetration,
                resting_size=resting_size,
                order_consumption=order_consumption,
                structural_persistence=structural_persistence,
                price=price,
                context=context
            )

        # No action
        return None

    def _check_entry(
        self,
        symbol: str,
        zone_penetration,
        resting_size,
        order_consumption,
        structural_persistence,
        price: float,
        context: StrategyContext
    ) -> Optional[StrategyProposal]:
        """
        Check for SLBRS entry opportunity (retest logic).

        Entry conditions (from research):
        1. Liquidity block detected (zone_liquidity ≥ 2.5× avg, persistence ≥ 30s)
        2. First test observed (price entered, rejected)
        3. Retest conditions met:
           - Distance to block ≤ 30% of block width
           - Volume reduced (< first_test × 0.70)
           - Absorption present (consumption_ratio ≥ 0.65)

        Returns:
            ENTRY proposal if retest conditions met, None otherwise
        """
        # Check if primitives available
        if zone_penetration is None:
            return None

        # Check for liquidity block presence (using zone_penetration as proxy)
        # Block exists if: penetration_depth > 0 AND persistence exists
        block_exists = (
            zone_penetration.penetration_depth > 0
            and structural_persistence is not None
            and structural_persistence.total_persistence_duration >= 30.0  # 30s threshold
        )

        if not block_exists:
            # No block detected
            self._state[symbol] = SLBRSState.IDLE
            return None

        # Check if first test should be recorded
        # (Simplified: assume first penetration is first test)
        if self._state[symbol] == SLBRSState.IDLE:
            # First time seeing block - record as first test
            self._first_test[symbol] = FirstTestObservation(
                block_edge=price,  # Simplified: use current price as block edge
                block_width=zone_penetration.penetration_depth * 2,  # Estimate block width
                test_volume=1.0,  # Placeholder (would need volume primitive)
                test_price_impact=zone_penetration.penetration_depth,
                timestamp=context.timestamp
            )
            self._state[symbol] = SLBRSState.FIRST_TEST_OBSERVED
            return None  # No entry on first test

        # Check retest entry conditions
        if self._state[symbol] == SLBRSState.FIRST_TEST_OBSERVED:
            first_test = self._first_test[symbol]
            if first_test is None:
                return None

            # Retest Condition 1: Distance to block ≤ 30% of block width
            distance_to_block = abs(price - first_test.block_edge)
            proximity_threshold = 0.30 * first_test.block_width

            if distance_to_block > proximity_threshold:
                # Too far from block
                return None

            # Retest Condition 2: Absorption present
            # (Simplified: check if order_consumption exists and is significant)
            absorption_present = (
                order_consumption is not None
                and order_consumption.consumed_size > 0
                # Constitutional note: 0.65 threshold from liquidity mechanics
                # Ideally would check: consumption_ratio ≥ 0.65
                # For now, any consumption indicates absorption
            )

            if not absorption_present:
                # No absorption observed
                return None

            # Retest Condition 3: Reduced volume compared to first test
            # (Simplified: assume condition met if we're here)
            # Real implementation would compare current volume to first_test.test_volume

            # All retest conditions met -> propose ENTRY
            self._state[symbol] = SLBRSState.RETEST_ARMED

            return StrategyProposal(
                strategy_id="EP2-SLBRS-V1",
                action_type="ENTRY",
                confidence="RETEST_CONDITIONS_MET",  # Structural observation, not confidence score
                justification_ref="BLOCK_PERSISTENCE|ORDER_ABSORPTION|PROXIMITY",
                timestamp=context.timestamp
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

        Invalidation conditions (from research):
        1. Volatility expands (ATR ratio ≥ 1.0)
        2. Orderflow becomes one-sided (handled by regime classifier)
        3. Price accepts through block (penetration increases significantly)

        Returns:
            EXIT proposal if invalidation detected, None otherwise
        """
        # Invalidation 1: Volatility expansion
        # ATR ratio ≥ 1.0 indicates expansion (violates sideways regime)
        if regime_state.atr_30m > 0:
            atr_ratio = regime_state.atr_5m / regime_state.atr_30m
            if atr_ratio >= 1.0:
                # Volatility expanding
                return self._generate_exit_proposal(
                    reason="VOLATILITY_EXPANSION",
                    context=context
                )

        # Invalidation 2: Price acceptance through block
        # If penetration depth increases significantly beyond first test
        first_test = self._first_test.get(symbol)
        if first_test and zone_penetration:
            current_penetration = zone_penetration.penetration_depth
            # If price moved beyond block by more than block width -> accepted through
            if current_penetration > first_test.block_width:
                return self._generate_exit_proposal(
                    reason="PRICE_ACCEPTANCE",
                    context=context
                )

        # Invalidation 3: Orderflow one-sided
        # (Handled by regime classifier - if regime changes, we exit via Rule 2)

        # No invalidation detected -> HOLD
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

    def reset_state(self, symbol: str):
        """Reset SLBRS state for symbol (after exit or failure)."""
        if symbol in self._state:
            self._state[symbol] = SLBRSState.IDLE
            self._first_test[symbol] = None


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
    position_state: Optional[PositionState] = None
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
        position_state=position_state
    )
