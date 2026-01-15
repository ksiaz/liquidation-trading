"""
EP-2 Strategy: Cascade Sniper (Liquidation Proximity)

Uses Hyperliquid liquidation proximity data to anticipate cascades
and enter positions with sniper timing.

Authority:
- Hyperliquid Position Tracker (proximity data)
- Binance Liquidation Stream (cascade confirmation)
- M6 Scaffolding v1.0
- EP-3 Arbitration & Risk Gate v1.0

Strategy Logic:
1. PRIME: Monitor positions within 0.5% of liquidation (Hyperliquid)
2. DETECT: Watch for cascade trigger (liquidations firing)
3. ENTER: Sniper entry on reversal (absorption) or cascade momentum

Constitutional compliance:
- Only factual observations (position counts, values, distances)
- No predictions - structural conditions only
- Proposals only - no execution decisions

CRITICAL: This module makes no decisions. It only proposes.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum
from runtime.position.types import PositionState


# ==============================================================================
# Configuration
# ==============================================================================

@dataclass(frozen=True)
class CascadeSniperConfig:
    """Configuration for cascade sniper strategy."""
    # Proximity threshold (0.5% = 0.005)
    proximity_threshold_pct: float = 0.005

    # Minimum value at risk to consider a cluster ($USD)
    min_cluster_value: float = 100_000.0

    # Minimum positions to form a cluster
    min_cluster_positions: int = 5

    # Dominance ratio - how much more one side must have
    # e.g., 0.7 means 70% of value must be on one side
    dominance_ratio: float = 0.65

    # Liquidation trigger threshold
    # How much liquidation volume confirms cascade start ($USD)
    liquidation_trigger_volume: float = 50_000.0

    # Liquidation lookback window (seconds)
    liquidation_window_sec: float = 10.0


# ==============================================================================
# Types
# ==============================================================================

class CascadeState(Enum):
    """Cascade lifecycle states."""
    NONE = "NONE"                    # No significant cluster detected
    PRIMED = "PRIMED"                # Cluster detected, waiting for trigger
    TRIGGERED = "TRIGGERED"          # Cascade started (liquidations firing)
    ABSORBING = "ABSORBING"          # Cascade absorbed, reversal likely
    EXHAUSTED = "EXHAUSTED"          # Cascade complete


class EntryMode(Enum):
    """Entry timing modes."""
    ABSORPTION_REVERSAL = "ABSORPTION_REVERSAL"  # Enter on reversal (conservative)
    CASCADE_MOMENTUM = "CASCADE_MOMENTUM"        # Ride the cascade (aggressive)


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
    action_type: str  # "ENTRY" | "EXIT"
    direction: str    # "LONG" | "SHORT"
    confidence: str   # Opaque label
    justification_ref: str
    timestamp: float


@dataclass(frozen=True)
class ProximityData:
    """
    Liquidation proximity data from Hyperliquid.

    Structural observation - no interpretation.
    """
    coin: str
    current_price: float
    threshold_pct: float

    # Long positions at risk
    long_positions_count: int
    long_positions_value: float
    long_closest_liquidation: Optional[float]

    # Short positions at risk
    short_positions_count: int
    short_positions_value: float
    short_closest_liquidation: Optional[float]

    # Totals
    total_positions_at_risk: int
    total_value_at_risk: float

    timestamp: float


@dataclass(frozen=True)
class LiquidationBurst:
    """
    Recent liquidation activity from Binance.

    Structural observation - no interpretation.
    """
    symbol: str
    total_volume: float          # Total liquidation volume in window
    long_liquidations: float     # Volume of long liquidations
    short_liquidations: float    # Volume of short liquidations
    liquidation_count: int       # Number of liquidation events
    window_start: float          # Window start timestamp
    window_end: float            # Window end timestamp


# ==============================================================================
# Cascade State Machine
# ==============================================================================

class CascadeStateMachine:
    """
    Tracks cascade lifecycle per symbol.

    State transitions are based on structural observations only.
    """

    def __init__(self, config: CascadeSniperConfig):
        self._config = config
        self._states: Dict[str, CascadeState] = {}
        self._primed_data: Dict[str, ProximityData] = {}
        self._triggered_at: Dict[str, float] = {}

    def update(
        self,
        symbol: str,
        proximity: Optional[ProximityData],
        liquidations: Optional[LiquidationBurst],
        timestamp: float
    ) -> CascadeState:
        """
        Update cascade state based on new data.

        Returns:
            Current cascade state for symbol
        """
        current_state = self._states.get(symbol, CascadeState.NONE)

        # State: NONE -> Check for cluster formation
        if current_state == CascadeState.NONE:
            if self._is_cluster_formed(proximity):
                self._states[symbol] = CascadeState.PRIMED
                self._primed_data[symbol] = proximity
                return CascadeState.PRIMED

        # State: PRIMED -> Check for trigger or decay
        elif current_state == CascadeState.PRIMED:
            # Check if cluster still exists
            if not self._is_cluster_formed(proximity):
                self._states[symbol] = CascadeState.NONE
                self._primed_data.pop(symbol, None)
                return CascadeState.NONE

            # Check for liquidation trigger
            if self._is_cascade_triggered(liquidations):
                self._states[symbol] = CascadeState.TRIGGERED
                self._triggered_at[symbol] = timestamp
                return CascadeState.TRIGGERED

            # Update primed data
            if proximity:
                self._primed_data[symbol] = proximity

        # State: TRIGGERED -> Check for absorption or exhaustion
        elif current_state == CascadeState.TRIGGERED:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Check for absorption (liquidation velocity decreasing)
            if liquidations and self._is_absorption_detected(liquidations, proximity):
                self._states[symbol] = CascadeState.ABSORBING
                return CascadeState.ABSORBING

            # Timeout: cascade exhausted after 30 seconds
            if elapsed > 30.0:
                self._states[symbol] = CascadeState.EXHAUSTED
                return CascadeState.EXHAUSTED

        # State: ABSORBING -> Short window for entry, then exhausted
        elif current_state == CascadeState.ABSORBING:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Absorption window is 10 seconds
            if elapsed > 40.0:  # 30s cascade + 10s absorption
                self._states[symbol] = CascadeState.EXHAUSTED
                return CascadeState.EXHAUSTED

        # State: EXHAUSTED -> Reset after cooldown
        elif current_state == CascadeState.EXHAUSTED:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Cooldown: 60 seconds before re-priming
            if elapsed > 60.0:
                self._states[symbol] = CascadeState.NONE
                self._primed_data.pop(symbol, None)
                self._triggered_at.pop(symbol, None)
                return CascadeState.NONE

        return self._states.get(symbol, CascadeState.NONE)

    def _is_cluster_formed(self, proximity: Optional[ProximityData]) -> bool:
        """Check if proximity data indicates a liquidation cluster."""
        if proximity is None:
            return False

        # Must have minimum positions
        if proximity.total_positions_at_risk < self._config.min_cluster_positions:
            return False

        # Must have minimum value
        if proximity.total_value_at_risk < self._config.min_cluster_value:
            return False

        # Must have clear dominance (one side has most exposure)
        total = proximity.total_value_at_risk
        if total == 0:
            return False

        long_ratio = proximity.long_positions_value / total
        short_ratio = proximity.short_positions_value / total

        if max(long_ratio, short_ratio) < self._config.dominance_ratio:
            return False

        return True

    def _is_cascade_triggered(self, liquidations: Optional[LiquidationBurst]) -> bool:
        """Check if liquidation activity indicates cascade start."""
        if liquidations is None:
            return False

        return liquidations.total_volume >= self._config.liquidation_trigger_volume

    def _is_absorption_detected(
        self,
        liquidations: LiquidationBurst,
        proximity: Optional[ProximityData]
    ) -> bool:
        """
        Check if cascade is being absorbed.

        Absorption indicators:
        - Liquidation velocity decreasing
        - Positions at risk count dropping
        """
        if proximity is None:
            return False

        primed = self._primed_data.get(liquidations.symbol)
        if primed is None:
            return False

        # Positions at risk decreased significantly (absorbed)
        if proximity.total_positions_at_risk < primed.total_positions_at_risk * 0.5:
            return True

        return False

    def get_primed_data(self, symbol: str) -> Optional[ProximityData]:
        """Get the proximity data from when cluster was primed."""
        return self._primed_data.get(symbol)

    def get_state(self, symbol: str) -> CascadeState:
        """Get current cascade state for symbol."""
        return self._states.get(symbol, CascadeState.NONE)

    def get_dominant_side(self, symbol: str) -> Optional[str]:
        """Get which side has more exposure in the primed cluster."""
        primed = self._primed_data.get(symbol)
        if primed is None:
            return None

        if primed.long_positions_value > primed.short_positions_value:
            return "LONG"
        elif primed.short_positions_value > primed.long_positions_value:
            return "SHORT"
        return None


# ==============================================================================
# EP-2 Strategy: Cascade Sniper
# ==============================================================================

# Global state machine (stateful across calls)
_state_machine: Optional[CascadeStateMachine] = None
_config: Optional[CascadeSniperConfig] = None


def _get_state_machine() -> CascadeStateMachine:
    """Get or create the state machine singleton."""
    global _state_machine, _config
    if _state_machine is None:
        _config = CascadeSniperConfig()
        _state_machine = CascadeStateMachine(_config)
    return _state_machine


def generate_cascade_sniper_proposal(
    *,
    permission: PermissionOutput,
    proximity: Optional[ProximityData],
    liquidations: Optional[LiquidationBurst],
    context: StrategyContext,
    position_state: Optional[PositionState] = None,
    entry_mode: EntryMode = EntryMode.ABSORPTION_REVERSAL
) -> Optional[StrategyProposal]:
    """
    Generate cascade sniper entry proposal.

    Strategy:
    1. Monitor Hyperliquid proximity for position clusters
    2. When cluster detected (PRIMED), wait for liquidation trigger
    3. On ABSORPTION, enter reversal opposite to cascade direction

    For ABSORPTION_REVERSAL mode:
    - If longs were liquidated (cascade DOWN), enter LONG (reversal UP)
    - If shorts were liquidated (cascade UP), enter SHORT (reversal DOWN)

    For CASCADE_MOMENTUM mode:
    - If longs being liquidated, enter SHORT (ride cascade)
    - If shorts being liquidated, enter LONG (ride cascade)

    Args:
        permission: M6 permission result
        proximity: Current Hyperliquid proximity data
        liquidations: Recent Binance liquidation burst
        context: Strategy execution context
        position_state: Current position state
        entry_mode: Entry timing mode

    Returns:
        StrategyProposal if conditions warrant entry, None otherwise
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None

    # Rule 2: Already in position -> check for exit
    if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
        # For now, exit logic is handled by other strategies
        # Cascade sniper is entry-focused
        return None

    # Get state machine
    sm = _get_state_machine()

    # Determine symbol from proximity or liquidation data
    symbol = None
    if proximity:
        symbol = proximity.coin + "USDT"  # Convert "BTC" -> "BTCUSDT"
    elif liquidations:
        symbol = liquidations.symbol

    if symbol is None:
        return None

    # Update state machine
    state = sm.update(symbol, proximity, liquidations, context.timestamp)

    # Rule 3: Generate entry proposal based on state and mode
    if entry_mode == EntryMode.ABSORPTION_REVERSAL:
        # Enter on absorption (reversal play)
        if state == CascadeState.ABSORBING:
            dominant_side = sm.get_dominant_side(symbol)
            primed = sm.get_primed_data(symbol)

            if dominant_side and primed:
                # Reversal: enter opposite to liquidated side
                # If LONGS were liquidated (cascade DOWN) -> enter LONG
                # If SHORTS were liquidated (cascade UP) -> enter SHORT
                entry_direction = dominant_side  # Same as liquidated side = reversal

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="ABSORPTION_REVERSAL",
                    justification_ref=f"HL_PROX|ABSORB|{primed.total_positions_at_risk}pos|${primed.total_value_at_risk:.0f}",
                    timestamp=context.timestamp
                )

    elif entry_mode == EntryMode.CASCADE_MOMENTUM:
        # Enter on trigger (momentum play)
        if state == CascadeState.TRIGGERED:
            dominant_side = sm.get_dominant_side(symbol)
            primed = sm.get_primed_data(symbol)

            if dominant_side and primed:
                # Momentum: enter same direction as cascade
                # If LONGS being liquidated -> cascade DOWN -> enter SHORT
                # If SHORTS being liquidated -> cascade UP -> enter LONG
                entry_direction = "SHORT" if dominant_side == "LONG" else "LONG"

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="CASCADE_MOMENTUM",
                    justification_ref=f"HL_PROX|TRIGGER|{primed.total_positions_at_risk}pos|${primed.total_value_at_risk:.0f}",
                    timestamp=context.timestamp
                )

    # No action warranted
    return None


def get_cascade_state(symbol: str) -> CascadeState:
    """Get current cascade state for a symbol (for monitoring)."""
    sm = _get_state_machine()
    return sm.get_state(symbol)


def get_primed_symbols() -> List[str]:
    """Get list of symbols currently in PRIMED or higher state."""
    sm = _get_state_machine()
    return [
        symbol for symbol, state in sm._states.items()
        if state not in (CascadeState.NONE, CascadeState.EXHAUSTED)
    ]


def reset_state():
    """Reset state machine (for testing)."""
    global _state_machine
    _state_machine = None
