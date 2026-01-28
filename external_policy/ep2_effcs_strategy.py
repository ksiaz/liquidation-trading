"""
EP-2 Strategy: EFFCS (Expansion & Forced Flow Continuation System)

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)

Purpose:
Exploits liquidation cascades, stop-runs, and forced participation in expansion conditions.

Strategy Logic (from OB-SLBRSorderblockstrat.md):
1. Detect impulse (displacement ≥ 0.5 × ATR(5m), liquidation spike)
2. Filter pullback (retracement ≤ 30%, volume decreased)
3. Enter on continuation (pullback complete, liquidations resume)
4. Exit when liquidations stop, orderbook replenishes, or volatility contracts

Thresholds from Market Mechanics (NOT backtest optimization):
- 0.5 ATR displacement: Volatility-adjusted significance threshold
- 30% retracement: Geometric pullback limit
- 2.5 liquidation Z-score: Statistical significance (in regime classifier)

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
    """Regime state for EFFCS gating."""
    regime: str  # "SIDEWAYS_ACTIVE", "EXPANSION_ACTIVE", "DISABLED"
    vwap_distance: float
    atr_5m: float
    atr_30m: float


# ==============================================================================
# EFFCS Internal State
# ==============================================================================

class EFFCSState(Enum):
    """EFFCS state machine states."""
    IDLE = auto()  # No impulse detected
    IMPULSE_DETECTED = auto()  # Displacement observed
    PULLBACK_FILTERING = auto()  # Monitoring pullback validity
    CONTINUATION_ARMED = auto()  # Ready for continuation entry
    IN_POSITION = auto()  # Position open


@dataclass
class ImpulseObservation:
    """Records impulse characteristics for pullback/continuation tracking."""
    impulse_start_price: float  # Price at impulse start
    impulse_end_price: float  # Price at impulse completion
    impulse_displacement: float  # Total displacement
    impulse_high: float  # Highest price during impulse
    impulse_low: float  # Lowest price during impulse
    timestamp: float


@dataclass
class PullbackObservation:
    """Records pullback characteristics for continuation entry."""
    pullback_start_price: float  # Price when pullback began
    pullback_current_price: float  # Current price during pullback
    pullback_low: float  # Lowest price during pullback (for stop placement)
    timestamp: float


# ==============================================================================
# EFFCS Strategy Implementation
# ==============================================================================

class EFFCSStrategy:
    """
    Stateful EFFCS strategy implementation.

    Maintains internal state for impulse, pullback, and continuation logic.

    Constitutional Compliance:
    - Thresholds from market mechanics (not backtest optimization)
    - Acknowledges outcome divergence (P12)
    - No confidence scoring
    - No certainty claims
    """

    def __init__(self):
        """Initialize EFFCS strategy with empty state."""
        self._state: Dict[str, EFFCSState] = {}  # symbol -> state
        self._impulse: Dict[str, Optional[ImpulseObservation]] = {}  # symbol -> impulse
        self._pullback: Dict[str, Optional[PullbackObservation]] = {}  # symbol -> pullback

    def generate_proposal(
        self,
        *,
        symbol: str,
        regime_state: Optional[RegimeState],
        price_velocity,  # PriceTraversalVelocity | None
        displacement,  # DisplacementOriginAnchor | None (or calculated from velocity)
        liquidation_zscore: float,  # From regime metrics
        price: float,
        price_high: float,  # Recent high
        price_low: float,  # Recent low
        context: StrategyContext,
        permission: PermissionOutput,
        position_state: Optional[PositionState] = None
    ) -> Optional[StrategyProposal]:
        """
        Generate EFFCS proposal based on current market structure.

        Constitutional Compliance:
        - Conditional execution: "When structure X, do action Y"
        - No claim about outcome probability
        - Acknowledges: Same structure may lead to different outcomes

        Args:
            symbol: Trading symbol
            regime_state: Current regime (must be EXPANSION_ACTIVE for EFFCS)
            price_velocity: A3 primitive (price movement rate)
            displacement: Displacement magnitude
            liquidation_zscore: Liquidation Z-score (from regime classifier)
            price: Current price
            price_high: Recent high price
            price_low: Recent low price
            context: Strategy execution context
            permission: M6 permission result
            position_state: Current position state

        Returns:
            StrategyProposal if conditions met, None otherwise
        """
        # Initialize symbol state if needed
        if symbol not in self._state:
            self._state[symbol] = EFFCSState.IDLE
            self._impulse[symbol] = None
            self._pullback[symbol] = None

        # Rule 1: M6 DENIED -> no proposal
        if permission.result == "DENIED":
            return None

        # Rule 2: Regime gate - EFFCS only active in EXPANSION regime
        if regime_state is None or regime_state.regime != "EXPANSION_ACTIVE":
            # Regime not expansion -> EFFCS disabled
            # If position open, exit due to regime change
            if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
                return self._generate_exit_proposal(
                    reason="REGIME_CHANGE",
                    context=context
                )
            return None

        # Rule 3: Check position state and generate appropriate action
        if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
            # Position exists - check for exit conditions
            return self._check_exit(
                symbol=symbol,
                regime_state=regime_state,
                liquidation_zscore=liquidation_zscore,
                price=price,
                context=context
            )

        # Rule 4: Position FLAT - check for entry opportunity
        if position_state == PositionState.FLAT or position_state is None:
            return self._check_entry(
                symbol=symbol,
                regime_state=regime_state,
                price_velocity=price_velocity,
                displacement=displacement,
                liquidation_zscore=liquidation_zscore,
                price=price,
                price_high=price_high,
                price_low=price_low,
                context=context
            )

        # No action
        return None

    def _check_entry(
        self,
        symbol: str,
        regime_state: RegimeState,
        price_velocity,
        displacement,
        liquidation_zscore: float,
        price: float,
        price_high: float,
        price_low: float,
        context: StrategyContext
    ) -> Optional[StrategyProposal]:
        """
        Check for EFFCS entry opportunity (impulse + pullback + continuation).

        Entry conditions (from research):
        1. Impulse detection: displacement ≥ 0.5 × ATR(5m) AND liquidation spike
        2. Pullback filter: retracement ≤ 30% AND volume decreased
        3. Continuation: pullback completes, liquidations resume

        Returns:
            ENTRY proposal if continuation conditions met, None otherwise
        """
        # Check if primitives available
        if price_velocity is None:
            return None

        # Calculate displacement magnitude
        # (Using velocity as proxy; real implementation would use displacement primitive)
        displacement_magnitude = abs(price_velocity.velocity) if hasattr(price_velocity, 'velocity') else 0

        # Impulse Condition 1: Displacement ≥ 0.5 × ATR(5m)
        displacement_threshold = 0.5 * regime_state.atr_5m
        impulse_present = displacement_magnitude >= displacement_threshold

        # Impulse Condition 2: Liquidation spike (Z-score ≥ 2.5)
        # (Already checked by regime classifier for EXPANSION_ACTIVE)
        liquidation_spike = liquidation_zscore >= 2.5

        if not impulse_present or not liquidation_spike:
            # No impulse detected
            self._state[symbol] = EFFCSState.IDLE
            return None

        # Impulse detected - record it
        if self._state[symbol] == EFFCSState.IDLE:
            self._impulse[symbol] = ImpulseObservation(
                impulse_start_price=price,  # Simplified: use current price as start
                impulse_end_price=price,
                impulse_displacement=displacement_magnitude,
                impulse_high=price_high,
                impulse_low=price_low,
                timestamp=context.timestamp
            )
            self._state[symbol] = EFFCSState.IMPULSE_DETECTED
            return None  # No entry on impulse detection

        # Pullback filtering
        if self._state[symbol] == EFFCSState.IMPULSE_DETECTED:
            impulse = self._impulse[symbol]
            if impulse is None:
                return None

            # Check if pullback is occurring
            # Pullback = price retracing from impulse direction
            impulse_direction = 1 if impulse.impulse_high > impulse.impulse_low else -1

            if impulse_direction > 0:
                # Bullish impulse - pullback is price moving down
                retracement = (impulse.impulse_high - price) / impulse.impulse_displacement
            else:
                # Bearish impulse - pullback is price moving up
                retracement = (price - impulse.impulse_low) / impulse.impulse_displacement

            # Pullback Condition: Retracement ≤ 30%
            if retracement > 0.30:
                # Pullback too deep - invalidate impulse
                self._state[symbol] = EFFCSState.IDLE
                self._impulse[symbol] = None
                return None

            # Valid pullback - record it
            if self._pullback[symbol] is None:
                self._pullback[symbol] = PullbackObservation(
                    pullback_start_price=price,
                    pullback_current_price=price,
                    pullback_low=price_low if impulse_direction > 0 else price_high,
                    timestamp=context.timestamp
                )
                self._state[symbol] = EFFCSState.PULLBACK_FILTERING

            # Check for continuation (pullback complete, price resuming impulse direction)
            # Simplified: if liquidations still elevated and displacement continues
            if liquidation_zscore >= 2.5 and retracement < 0.25:
                # Continuation conditions met -> propose ENTRY
                self._state[symbol] = EFFCSState.CONTINUATION_ARMED

                return StrategyProposal(
                    strategy_id="EP2-EFFCS-V1",
                    action_type="ENTRY",
                    confidence="CONTINUATION_CONDITIONS_MET",  # Structural observation
                    justification_ref="IMPULSE_DISPLACEMENT|LIQUIDATION_SPIKE|PULLBACK_VALID",
                    timestamp=context.timestamp
                )

        # No entry conditions met
        return None

    def _check_exit(
        self,
        symbol: str,
        regime_state: RegimeState,
        liquidation_zscore: float,
        price: float,
        context: StrategyContext
    ) -> Optional[StrategyProposal]:
        """
        Check for EFFCS exit conditions.

        Exit conditions (from research):
        1. Liquidations stop accelerating (Z-score < 2.0)
        2. Orderbook replenishes (not directly observable, use volume decrease)
        3. Volatility contracts (ATR ratio < 0.90)

        Returns:
            EXIT proposal if exit conditions met, None otherwise
        """
        # Exit Condition 1: Liquidations stopped
        if liquidation_zscore < 2.0:
            return self._generate_exit_proposal(
                reason="LIQUIDATIONS_STOPPED",
                context=context
            )

        # Exit Condition 2: Volatility contraction
        if regime_state.atr_30m > 0:
            atr_ratio = regime_state.atr_5m / regime_state.atr_30m
            if atr_ratio < 0.90:
                # Volatility contracting
                return self._generate_exit_proposal(
                    reason="VOLATILITY_CONTRACTION",
                    context=context
                )

        # Exit Condition 3: Orderbook replenishment
        # (Would need orderbook refill primitive; not implemented yet)

        # No exit conditions met -> HOLD
        return None

    def _generate_exit_proposal(
        self,
        reason: str,
        context: StrategyContext
    ) -> StrategyProposal:
        """
        Generate EXIT proposal with reason.

        Constitutional Compliance:
        - Exit based on structural change
        - No claim about outcome quality
        - Reason is observational, not interpretive

        Args:
            reason: Structural reason for exit
            context: Strategy context

        Returns:
            EXIT proposal
        """
        return StrategyProposal(
            strategy_id="EP2-EFFCS-V1",
            action_type="EXIT",
            confidence="INVALIDATED",  # Structural invalidation
            justification_ref=f"EFFCS_EXIT|{reason}",
            timestamp=context.timestamp
        )

    def reset_state(self, symbol: str):
        """Reset EFFCS state for symbol (after exit or failure)."""
        if symbol in self._state:
            self._state[symbol] = EFFCSState.IDLE
            self._impulse[symbol] = None
            self._pullback[symbol] = None


# ==============================================================================
# Global Strategy Instance (Stateful)
# ==============================================================================

# Global instance maintains state across cycles
_effcs_strategy = EFFCSStrategy()


def generate_effcs_proposal(
    *,
    symbol: str,
    regime_state: Optional[RegimeState],
    price_velocity,
    displacement,
    liquidation_zscore: float,
    price: float,
    price_high: float,
    price_low: float,
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None
) -> Optional[StrategyProposal]:
    """
    Generate EFFCS proposal (function interface for policy adapter).

    Constitutional Authority:
    - EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
    - Conditional execution: "When structure X, execute action Y"
    - Acknowledges outcome divergence (P12)

    Thresholds from Market Mechanics:
    - 0.5 ATR displacement: Volatility-adjusted significance
    - 30% pullback: Geometric retracement limit
    - 2.5 liquidation Z-score: Statistical significance

    This function does NOT:
    - Assign confidence scores (numeric probabilities)
    - Claim certainty about outcomes
    - Predict future price movement
    - Rank primitive importance

    Args:
        symbol: Trading symbol
        regime_state: Current regime (must be EXPANSION_ACTIVE)
        price_velocity: A3 primitive
        displacement: Displacement magnitude
        liquidation_zscore: Liquidation Z-score
        price: Current price
        price_high: Recent high
        price_low: Recent low
        context: Strategy context
        permission: M6 permission
        position_state: Current position state

    Returns:
        StrategyProposal if conditions met, None otherwise
    """
    return _effcs_strategy.generate_proposal(
        symbol=symbol,
        regime_state=regime_state,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=liquidation_zscore,
        price=price,
        price_high=price_high,
        price_low=price_low,
        context=context,
        permission=permission,
        position_state=position_state
    )
