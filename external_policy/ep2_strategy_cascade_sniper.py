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
from typing import Optional, Dict, List, TYPE_CHECKING
from enum import Enum
from runtime.position.types import PositionState
from runtime.validation.entry_quality import (
    EntryQualityScorer,
    EntryScore,
    EntryQuality,
    EntryMode as EQEntryMode  # Alias to avoid conflict with local EntryMode
)
from memory.m4_absorption_confirmation import (
    TrendRegimeContext,
    TrendDirection,
)

if TYPE_CHECKING:
    from observation.types import M4PrimitiveBundle
    from memory.m4_cascade_proximity import LiquidationCascadeProximity
    from memory.m4_cascade_state import CascadeStateObservation, CascadePhase


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
    min_cluster_positions: int = 2  # Lowered for testing (was 5)

    # Dominance ratio - how much more one side must have
    # e.g., 0.7 means 70% of value must be on one side
    dominance_ratio: float = 0.65

    # Liquidation trigger threshold
    # How much liquidation volume confirms cascade start ($USD)
    liquidation_trigger_volume: float = 50_000.0

    # Liquidation lookback window (seconds)
    liquidation_window_sec: float = 10.0

    # Absorption analysis thresholds
    # absorption_ratio = book_depth / liquidation_value
    # >1.0 means book can absorb, <1.0 means cascade continues

    # For ABSORPTION_REVERSAL: only enter if ratio > this (book absorbed)
    min_absorption_ratio_for_reversal: float = 1.5

    # For CASCADE_MOMENTUM: only enter if ratio < this (cascade will continue)
    max_absorption_ratio_for_momentum: float = 0.8

    # Use absorption filter (if False, ignore absorption data)
    use_absorption_filter: bool = True

    # Entry quality scoring (data-driven from analysis of 759 trades)
    # Minimum entry quality to allow entry
    min_entry_quality: EntryQuality = EntryQuality.NEUTRAL

    # Require large liquidations for entry (>$50k)
    require_large_liquidations: bool = False

    # Use entry quality scoring (if False, skip quality check)
    use_entry_quality_filter: bool = True


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


@dataclass(frozen=True)
class AbsorptionAnalysis:
    """
    Order book absorption analysis.

    Compares liquidation volume vs book depth to determine
    if cascades can be absorbed.

    Structural observation - no interpretation.
    """
    coin: str
    mid_price: float

    # Book depth (cumulative value at levels near current price)
    bid_depth_2pct: float        # Cumulative bid depth within 2% of mid
    ask_depth_2pct: float        # Cumulative ask depth within 2% of mid

    # Liquidation value at risk (from proximity data)
    long_liq_value: float        # Value of longs at risk of liquidation
    short_liq_value: float       # Value of shorts at risk of liquidation

    # Absorption ratios (>1.0 = book can absorb, <1.0 = cascade continues)
    # Long liquidations sell into bids → ratio = bid_depth / long_liq_value
    # Short liquidations buy into asks → ratio = ask_depth / short_liq_value
    absorption_ratio_longs: float
    absorption_ratio_shorts: float

    timestamp: float


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
        self._absorption_data: Dict[str, AbsorptionAnalysis] = {}

    def update(
        self,
        symbol: str,
        proximity: Optional[ProximityData],
        liquidations: Optional[LiquidationBurst],
        timestamp: float,
        absorption: Optional[AbsorptionAnalysis] = None
    ) -> CascadeState:
        """
        Update cascade state based on new data.

        Returns:
            Current cascade state for symbol
        """
        old_state = self._states.get(symbol, CascadeState.NONE)
        new_state = old_state  # Track new state for transition logging

        # Store absorption data if provided
        if absorption is not None:
            self._absorption_data[symbol] = absorption

        # State: NONE -> Check for cluster formation
        if old_state == CascadeState.NONE:
            if self._is_cluster_formed(proximity):
                self._states[symbol] = CascadeState.PRIMED
                self._primed_data[symbol] = proximity
                new_state = CascadeState.PRIMED

        # State: PRIMED -> Check for trigger or decay
        elif old_state == CascadeState.PRIMED:
            # Check if cluster still exists
            if not self._is_cluster_formed(proximity):
                self._states[symbol] = CascadeState.NONE
                self._primed_data.pop(symbol, None)
                new_state = CascadeState.NONE

            # Check for liquidation trigger
            elif self._is_cascade_triggered(liquidations):
                self._states[symbol] = CascadeState.TRIGGERED
                self._triggered_at[symbol] = timestamp
                new_state = CascadeState.TRIGGERED
            else:
                # Update primed data
                if proximity:
                    self._primed_data[symbol] = proximity

        # State: TRIGGERED -> Check for absorption or exhaustion
        elif old_state == CascadeState.TRIGGERED:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Check for absorption using orderbook depth analysis
            if self._is_absorption_detected(symbol, liquidations, proximity):
                self._states[symbol] = CascadeState.ABSORBING
                new_state = CascadeState.ABSORBING
            # Timeout: cascade exhausted after 30 seconds
            elif elapsed > 30.0:
                self._states[symbol] = CascadeState.EXHAUSTED
                new_state = CascadeState.EXHAUSTED

        # State: ABSORBING -> Short window for entry, then exhausted
        elif old_state == CascadeState.ABSORBING:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Absorption window is 10 seconds
            if elapsed > 40.0:  # 30s cascade + 10s absorption
                self._states[symbol] = CascadeState.EXHAUSTED
                new_state = CascadeState.EXHAUSTED

        # State: EXHAUSTED -> Reset after cooldown
        elif old_state == CascadeState.EXHAUSTED:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Cooldown: 60 seconds before re-priming
            if elapsed > 60.0:
                self._states[symbol] = CascadeState.NONE
                self._primed_data.pop(symbol, None)
                self._triggered_at.pop(symbol, None)
                self._absorption_data.pop(symbol, None)
                new_state = CascadeState.NONE

        # Log state transitions
        if old_state != new_state:
            self._log_transition(symbol, old_state, new_state, proximity, liquidations, absorption)

        return self._states.get(symbol, CascadeState.NONE)

    def _log_transition(
        self,
        symbol: str,
        old_state: CascadeState,
        new_state: CascadeState,
        proximity: Optional[ProximityData],
        liquidations: Optional[LiquidationBurst],
        absorption: Optional[AbsorptionAnalysis]
    ):
        """Log state transition with trigger details."""
        print(f"\n[STATE] {symbol}: {old_state.value} -> {new_state.value}")

        # Log transition trigger reason
        if old_state == CascadeState.NONE and new_state == CascadeState.PRIMED:
            if proximity:
                dominant = "LONG" if proximity.long_positions_value > proximity.short_positions_value else "SHORT"
                print(f"  Trigger: Cluster formed - {proximity.total_positions_at_risk} positions, ${proximity.total_value_at_risk:,.0f}")
                print(f"  Dominant: {dominant} (L=${proximity.long_positions_value:,.0f}, S=${proximity.short_positions_value:,.0f})")

        elif old_state == CascadeState.PRIMED and new_state == CascadeState.TRIGGERED:
            if liquidations:
                print(f"  Trigger: Liquidation burst - ${liquidations.total_volume:,.0f} in {liquidations.liquidation_count} events")
                print(f"  Direction: L=${liquidations.long_liquidations:,.0f}, S=${liquidations.short_liquidations:,.0f}")

        elif old_state == CascadeState.PRIMED and new_state == CascadeState.NONE:
            print(f"  Trigger: Cluster dissolved - positions moved away from liquidation")

        elif old_state == CascadeState.TRIGGERED and new_state == CascadeState.ABSORBING:
            if absorption:
                print(f"  Trigger: Absorption detected - book depth sufficient")
                print(f"  Ratio: longs={absorption.absorption_ratio_longs:.2f}x, shorts={absorption.absorption_ratio_shorts:.2f}x")
            else:
                print(f"  Trigger: Position count dropped significantly")

        elif old_state == CascadeState.TRIGGERED and new_state == CascadeState.EXHAUSTED:
            print(f"  Trigger: Cascade timeout (30s) without absorption")

        elif old_state == CascadeState.ABSORBING and new_state == CascadeState.EXHAUSTED:
            print(f"  Trigger: Absorption window expired (40s total)")

        elif old_state == CascadeState.EXHAUSTED and new_state == CascadeState.NONE:
            print(f"  Trigger: Cooldown complete (60s) - ready for new cycle")

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
        symbol: str,
        liquidations: Optional[LiquidationBurst],
        proximity: Optional[ProximityData]
    ) -> bool:
        """
        Check if cascade is being absorbed.

        Absorption detection uses orderbook depth analysis:
        - If absorption_ratio > threshold, book can absorb remaining liquidations
        - Fallback: positions at risk decreased significantly

        Absorption indicators:
        1. Order book depth > liquidation value (primary)
        2. Positions at risk count dropping (fallback)
        """
        primed = self._primed_data.get(symbol)
        if primed is None:
            return False

        # PRIMARY: Check orderbook absorption if data available
        absorption = self._absorption_data.get(symbol)
        if absorption is not None:
            # Determine which side is being liquidated
            dominant_side = self.get_dominant_side(symbol)
            if dominant_side == "LONG":
                # Longs liquidating → selling into bids → check bid absorption
                if absorption.absorption_ratio_longs >= self._config.min_absorption_ratio_for_reversal:
                    return True
            elif dominant_side == "SHORT":
                # Shorts liquidating → buying into asks → check ask absorption
                if absorption.absorption_ratio_shorts >= self._config.min_absorption_ratio_for_reversal:
                    return True

        # FALLBACK: Positions at risk decreased significantly
        if proximity is not None:
            if proximity.total_positions_at_risk < primed.total_positions_at_risk * 0.5:
                return True

        return False

    def get_absorption_data(self, symbol: str) -> Optional[AbsorptionAnalysis]:
        """Get the current absorption data for a symbol."""
        return self._absorption_data.get(symbol)

    def check_absorption_filter(
        self,
        symbol: str,
        entry_mode: 'EntryMode'
    ) -> bool:
        """
        Check if absorption filter allows entry.

        For ABSORPTION_REVERSAL: book must be able to absorb (ratio > threshold)
        For CASCADE_MOMENTUM: book must be thin (ratio < threshold)

        Returns:
            True if filter passes, False if entry should be blocked
        """
        if not self._config.use_absorption_filter:
            return True  # Filter disabled

        absorption = self._absorption_data.get(symbol)
        if absorption is None:
            return True  # No data, allow entry (conservative)

        dominant_side = self.get_dominant_side(symbol)
        if dominant_side is None:
            return True  # No dominant side, allow entry

        # Get relevant absorption ratio
        if dominant_side == "LONG":
            ratio = absorption.absorption_ratio_longs
        else:
            ratio = absorption.absorption_ratio_shorts

        # Check based on entry mode
        if entry_mode == EntryMode.ABSORPTION_REVERSAL:
            # Need thick book to absorb (ratio > threshold)
            return ratio >= self._config.min_absorption_ratio_for_reversal
        elif entry_mode == EntryMode.CASCADE_MOMENTUM:
            # Need thin book for cascade to continue (ratio < threshold)
            return ratio <= self._config.max_absorption_ratio_for_momentum

        return True

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

# Global state machine and entry quality scorer (stateful across calls)
_state_machine: Optional[CascadeStateMachine] = None
_entry_quality_scorer: Optional[EntryQualityScorer] = None
_config: Optional[CascadeSniperConfig] = None


def _get_state_machine() -> CascadeStateMachine:
    """Get or create the state machine singleton."""
    global _state_machine, _config
    if _state_machine is None:
        _config = CascadeSniperConfig()
        _state_machine = CascadeStateMachine(_config)
    return _state_machine


def _get_entry_quality_scorer() -> EntryQualityScorer:
    """Get or create the entry quality scorer singleton."""
    global _entry_quality_scorer
    if _entry_quality_scorer is None:
        _entry_quality_scorer = EntryQualityScorer()
    return _entry_quality_scorer


def record_liquidation_event(
    symbol: str,
    side: str,  # "BUY" or "SELL"
    value: float,
    timestamp: float
):
    """
    Record a liquidation event for entry quality scoring.

    MUST be called for each liquidation event from Binance forceOrder stream.
    This feeds the exhaustion reversal detection.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        side: "BUY" (short liquidated) or "SELL" (long liquidated)
        value: USD value of liquidation
        timestamp: Event timestamp
    """
    scorer = _get_entry_quality_scorer()
    scorer.record_liquidation(symbol, side, value, timestamp)


# Trend strength threshold for blocking reversal entries
TREND_STRENGTH_BLOCK_THRESHOLD = 0.7


def _is_reversal_blocked_by_trend(
    entry_direction: str,
    trend: TrendRegimeContext
) -> bool:
    """
    Check if reversal entry should be BLOCKED by trend context.

    BLOCKS reversal when:
    1. LONG reversal during STRONG_DOWN with aligned delta (distribution phase)
    2. SHORT reversal during STRONG_UP with aligned delta (accumulation phase)
    3. High trend strength (>70%) with entry fading the trend

    Reversal entries during strong directional moves are dangerous because:
    - Absorption during strong trend = reload/pause, not exhaustion
    - Delta alignment = dominant side is actively distributing/accumulating
    - High trend strength = clear directional move, likely to continue

    Args:
        entry_direction: "LONG" or "SHORT"
        trend: Trend regime context

    Returns:
        True if entry should be blocked, False if allowed
    """
    # LONG reversal blocked during strong downtrend
    if entry_direction == "LONG":
        if trend.direction == TrendDirection.STRONG_DOWN:
            # Delta aligned = sellers are in control (distribution)
            if trend.delta_direction_aligned:
                return True
            # High trend strength = clear downtrend, dangerous to fade
            if trend.trend_strength >= TREND_STRENGTH_BLOCK_THRESHOLD:
                return True

    # SHORT reversal blocked during strong uptrend
    if entry_direction == "SHORT":
        if trend.direction == TrendDirection.STRONG_UP:
            # Delta aligned = buyers are in control (accumulation)
            if trend.delta_direction_aligned:
                return True
            # High trend strength = clear uptrend, dangerous to fade
            if trend.trend_strength >= TREND_STRENGTH_BLOCK_THRESHOLD:
                return True

    return False


def generate_cascade_sniper_proposal(
    *,
    permission: PermissionOutput,
    proximity: Optional[ProximityData],
    liquidations: Optional[LiquidationBurst],
    context: StrategyContext,
    position_state: Optional[PositionState] = None,
    entry_mode: EntryMode = EntryMode.ABSORPTION_REVERSAL,
    absorption: Optional[AbsorptionAnalysis] = None,
    trend_context: Optional[TrendRegimeContext] = None
) -> Optional[StrategyProposal]:
    """
    Generate cascade sniper entry proposal WITH TREND KILL-SWITCH.

    Strategy:
    1. Monitor Hyperliquid proximity for position clusters
    2. CHECK TREND KILL-SWITCH (blocks dangerous entries)
    3. When cluster detected (PRIMED), wait for liquidation trigger
    4. On ABSORPTION, enter reversal opposite to cascade direction
    5. Apply absorption filter based on orderbook depth vs liquidation volume
    6. Apply entry quality filter with trend context

    TREND KILL-SWITCH:
    - ABSORPTION_REVERSAL entries are BLOCKED when fading strong trends
    - CASCADE_MOMENTUM entries are allowed during strong trends (aligned)

    For ABSORPTION_REVERSAL mode:
    - If longs were liquidated (cascade DOWN), enter LONG (reversal UP)
    - If shorts were liquidated (cascade UP), enter SHORT (reversal DOWN)
    - REQUIRES: absorption_ratio > threshold (book absorbed cascade)
    - BLOCKED: if trend is STRONG_DOWN with aligned delta (distribution)

    For CASCADE_MOMENTUM mode:
    - If longs being liquidated, enter SHORT (ride cascade)
    - If shorts being liquidated, enter LONG (ride cascade)
    - REQUIRES: absorption_ratio < threshold (thin book, cascade continues)
    - ALLOWED: during strong trends (momentum aligned)

    Args:
        permission: M6 permission result
        proximity: Current Hyperliquid proximity data
        liquidations: Recent Binance liquidation burst
        context: Strategy execution context
        position_state: Current position state
        entry_mode: Entry timing mode
        absorption: Order book absorption analysis
        trend_context: Optional trend regime context for kill-switch

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

    # Update state machine with absorption data
    state = sm.update(symbol, proximity, liquidations, context.timestamp, absorption)

    # Get entry quality scorer
    eq_scorer = _get_entry_quality_scorer()

    # Rule 3: Generate entry proposal based on state and mode
    if entry_mode == EntryMode.ABSORPTION_REVERSAL:
        # Enter on absorption (reversal play)
        if state == CascadeState.ABSORBING:
            dominant_side = sm.get_dominant_side(symbol)
            primed = sm.get_primed_data(symbol)

            if dominant_side and primed:
                # Rule 3a: Check absorption filter
                # For reversal, need thick book (ratio > threshold)
                if not sm.check_absorption_filter(symbol, entry_mode):
                    # Book too thin for reversal - skip entry
                    return None

                # Reversal: enter opposite to liquidated side
                # If LONGS were liquidated (cascade DOWN) -> enter LONG
                # If SHORTS were liquidated (cascade UP) -> enter SHORT
                entry_direction = dominant_side  # Same as liquidated side = reversal

                # Rule 3a-TREND: TREND KILL-SWITCH for reversal entries
                # Reversal entries are DANGEROUS during strong trends
                if trend_context is not None:
                    if _is_reversal_blocked_by_trend(entry_direction, trend_context):
                        print(f"[TREND KILL-SWITCH] {symbol}: {entry_direction} reversal blocked - {trend_context.direction.name}")
                        return None

                # Rule 3b: Check entry quality based on liquidation exhaustion
                # This uses the data-driven scoring from analysis of 759 trades
                # Pass trend context for additional filtering
                if _config and _config.use_entry_quality_filter:
                    should_enter, eq_score = eq_scorer.get_entry_recommendation(
                        symbol=symbol,
                        intended_side=entry_direction,
                        min_quality=_config.min_entry_quality,
                        require_large_liq=_config.require_large_liquidations,
                        trend_context=trend_context
                    )

                    if not should_enter:
                        # Entry quality too low or trend blocked - skip
                        print(f"[EQ FILTER] {symbol}: {entry_direction} blocked - {eq_score.reason}")
                        return None
                else:
                    # No filter, get score for logging only (with trend context)
                    eq_score = eq_scorer.score_entry(symbol, entry_direction, context.timestamp, trend_context)

                # Include absorption ratio and entry quality in justification
                absorption_data = sm.get_absorption_data(symbol)
                ratio_str = ""
                if absorption_data:
                    ratio = absorption_data.absorption_ratio_longs if dominant_side == "LONG" else absorption_data.absorption_ratio_shorts
                    ratio_str = f"|ABSORB:{ratio:.2f}"

                eq_str = f"|EQ:{eq_score.quality.value}:{eq_score.score:.2f}"

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="ABSORPTION_REVERSAL",
                    justification_ref=f"HL_PROX|ABSORB|{primed.total_positions_at_risk}pos|${primed.total_value_at_risk:.0f}{ratio_str}{eq_str}",
                    timestamp=context.timestamp
                )

    elif entry_mode == EntryMode.CASCADE_MOMENTUM:
        # Enter on trigger (momentum play)
        if state == CascadeState.TRIGGERED:
            dominant_side = sm.get_dominant_side(symbol)
            primed = sm.get_primed_data(symbol)

            if dominant_side and primed:
                # Rule 3a: Check absorption filter
                # For momentum, need thin book (ratio < threshold)
                if not sm.check_absorption_filter(symbol, entry_mode):
                    # Book too thick - cascade will be absorbed, skip momentum entry
                    return None

                # Momentum: enter same direction as cascade
                # If LONGS being liquidated -> cascade DOWN -> enter SHORT
                # If SHORTS being liquidated -> cascade UP -> enter LONG
                entry_direction = "SHORT" if dominant_side == "LONG" else "LONG"

                # Note: NO trend kill-switch for momentum mode
                # Momentum entries are ALIGNED with strong trends, so trend context
                # actually helps (provides bonus via entry quality scorer)
                # The entry quality scorer will apply trend bonus for aligned entries

                # Rule 3b: Check entry quality based on liquidation exhaustion
                # Pass trend context for bonus calculation (momentum = trend-aligned)
                if _config and _config.use_entry_quality_filter:
                    should_enter, eq_score = eq_scorer.get_entry_recommendation(
                        symbol=symbol,
                        intended_side=entry_direction,
                        min_quality=_config.min_entry_quality,
                        require_large_liq=_config.require_large_liquidations,
                        trend_context=trend_context
                    )

                    if not should_enter:
                        # Entry quality too low - skip
                        print(f"[EQ FILTER] {symbol}: {entry_direction} blocked - {eq_score.reason}")
                        return None
                else:
                    # No filter, get score for logging only (with trend context)
                    eq_score = eq_scorer.score_entry(symbol, entry_direction, context.timestamp, trend_context)

                # Include absorption ratio and entry quality in justification
                absorption_data = sm.get_absorption_data(symbol)
                ratio_str = ""
                if absorption_data:
                    ratio = absorption_data.absorption_ratio_longs if dominant_side == "LONG" else absorption_data.absorption_ratio_shorts
                    ratio_str = f"|THIN:{ratio:.2f}"

                eq_str = f"|EQ:{eq_score.quality.value}:{eq_score.score:.2f}"

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="CASCADE_MOMENTUM",
                    justification_ref=f"HL_PROX|TRIGGER|{primed.total_positions_at_risk}pos|${primed.total_value_at_risk:.0f}{ratio_str}{eq_str}",
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
    """Reset state machine and entry quality scorer (for testing)."""
    global _state_machine, _entry_quality_scorer
    _state_machine = None
    _entry_quality_scorer = None


def get_entry_quality_score(symbol: str, direction: str) -> Optional[EntryScore]:
    """
    Get entry quality score for a symbol and direction.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        direction: "LONG" or "SHORT"

    Returns:
        EntryScore with quality assessment
    """
    scorer = _get_entry_quality_scorer()
    return scorer.score_entry(symbol, direction)


def get_best_entry_opportunity(symbols: List[str]) -> Optional[EntryScore]:
    """
    Find the best entry opportunity across multiple symbols.

    Scans all symbols for exhaustion reversal setups and returns
    the highest scoring opportunity.

    Args:
        symbols: List of symbols to scan

    Returns:
        Best EntryScore if any HIGH quality setups found, else None
    """
    scorer = _get_entry_quality_scorer()
    return scorer.get_best_entry_opportunity(symbols)


def get_entry_quality_stats() -> dict:
    """Get statistics from entry quality scorer."""
    scorer = _get_entry_quality_scorer()
    return scorer.get_stats()


# ==============================================================================
# M4 Primitive Bundle Integration (Constitutional Flow)
# ==============================================================================

def generate_cascade_sniper_proposal_from_primitives(
    *,
    permission: PermissionOutput,
    primitives: 'M4PrimitiveBundle',
    context: StrategyContext,
    position_state: Optional[PositionState] = None,
    entry_mode: EntryMode = EntryMode.ABSORPTION_REVERSAL,
    trend_context: Optional[TrendRegimeContext] = None
) -> Optional[StrategyProposal]:
    """
    Generate cascade sniper proposal from M4PrimitiveBundle WITH TREND KILL-SWITCH.

    This is the constitutional flow - data comes from M4 primitives via M5,
    not directly injected from HyperliquidCollector.

    TREND KILL-SWITCH:
    - Reversal entries are blocked during strong directional moves
    - Momentum entries benefit from trend alignment (bonus applied)

    Args:
        permission: M6 permission result
        primitives: M4PrimitiveBundle containing cascade primitives
        context: Strategy execution context
        position_state: Current position state
        entry_mode: Entry timing mode
        trend_context: Optional trend regime context for kill-switch

    Returns:
        StrategyProposal if conditions warrant entry, None otherwise
    """
    # Extract cascade primitives from bundle
    cascade_proximity = primitives.liquidation_cascade_proximity
    cascade_state = primitives.cascade_state

    if cascade_proximity is None and cascade_state is None:
        return None

    # Convert M4 primitive to ProximityData (internal type)
    proximity = None
    if cascade_proximity:
        proximity = ProximityData(
            coin=cascade_proximity.symbol,
            current_price=cascade_proximity.price_level,
            threshold_pct=cascade_proximity.threshold_pct,
            long_positions_count=cascade_proximity.long_positions_count,
            long_positions_value=cascade_proximity.long_positions_value,
            long_closest_liquidation=cascade_proximity.long_closest_price,
            short_positions_count=cascade_proximity.short_positions_count,
            short_positions_value=cascade_proximity.short_positions_value,
            short_closest_liquidation=cascade_proximity.short_closest_price,
            total_positions_at_risk=cascade_proximity.positions_at_risk_count,
            total_value_at_risk=cascade_proximity.aggregate_position_value,
            timestamp=cascade_proximity.timestamp
        )

    # Convert cascade state to LiquidationBurst (for state machine compatibility)
    liquidations = None
    if cascade_state and cascade_state.liquidations_30s > 0:
        # Approximate liquidation burst from cascade state
        liquidations = LiquidationBurst(
            symbol=cascade_state.symbol + "USDT",
            total_volume=cascade_state.cascade_value_liquidated,
            long_liquidations=cascade_state.cascade_value_liquidated / 2,  # Approximate
            short_liquidations=cascade_state.cascade_value_liquidated / 2,
            liquidation_count=cascade_state.liquidations_30s,
            window_start=cascade_state.timestamp - 30.0,
            window_end=cascade_state.timestamp
        )

    # Delegate to existing function with trend context
    return generate_cascade_sniper_proposal(
        permission=permission,
        proximity=proximity,
        liquidations=liquidations,
        context=context,
        position_state=position_state,
        entry_mode=entry_mode,
        trend_context=trend_context
    )
