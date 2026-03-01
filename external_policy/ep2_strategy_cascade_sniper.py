"""
EP-2 Strategy: Cascade Sniper (Liquidation Proximity)

Uses Hyperliquid liquidation proximity data to anticipate cascades
and enter positions with sniper timing.

Authority:
- Hyperliquid Position Tracker (proximity data)
- Liquidation Stream (cascade confirmation)
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

from collections import deque
from dataclasses import dataclass, field
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
    AbsorptionConfirmationTracker,
    TrendRegimeContext,
    TrendDirection,
)
# Cascade types - stub implementations pending node adapter redesign
# See docs/NODE_ADAPTER_REDESIGN.md
from runtime.cascade import (
    OrganicFlowDetector,
    CascadeDirection,
    AbsorptionSignal,
    CapitulationTracker,
    CapitulationMetrics,
)

from runtime.liquidations.rolling_volume_tracker import RollingFadeSignal

if TYPE_CHECKING:
    from observation.types import M4PrimitiveBundle
    from memory.m4_cascade_proximity import LiquidationCascadeProximity
    from memory.m4_cascade_state import CascadeStateObservation, CascadePhase


# ==============================================================================
# Running Pivot Detector (sub-second, per-fill)
# ==============================================================================

@dataclass
class _RunningPivotState:
    """Per-symbol running pivot state."""
    trades: deque = field(default_factory=lambda: deque(maxlen=20))
    prev_delta: float = 0.0
    pivot_detected: bool = False
    pivot_timestamp: float = 0.0


class RunningPivotDetector:
    """Sub-second pivot detection via running counters.

    Called on EVERY fill. Fires when selling → buying transition detected.
    Uses delta zero-cross as anchor signal + supporting confirmation.

    During cascades at 10-20 fills/sec, 20 trades = 1-2s of history.
    Detection fires within 1-2 trades of actual momentum shift.
    """
    MIN_TRADES = 8  # Need at least 8 trades to split into halves

    def __init__(self):
        self._state: Dict[str, _RunningPivotState] = {}

    def on_trade(self, symbol: str, price: float, size: float,
                 is_sell: bool, timestamp: float) -> bool:
        """Process a fill. Returns True if pivot just detected."""
        if symbol not in self._state:
            self._state[symbol] = _RunningPivotState()
        state = self._state[symbol]

        state.trades.append((timestamp, price, size, is_sell))

        if len(state.trades) < self.MIN_TRADES:
            return False

        trades = list(state.trades)
        mid_idx = len(trades) // 2
        first_half = trades[:mid_idx]
        second_half = trades[mid_idx:]

        # 1. Cumulative delta: buy_vol - sell_vol
        delta = sum(s for _, _, s, sell in trades if not sell) - \
                sum(s for _, _, s, sell in trades if sell)
        delta_crossed = delta > 0 and state.prev_delta <= 0
        state.prev_delta = delta

        if not delta_crossed:
            # No zero-cross = no new pivot
            # BUT: don't reset existing pivot_detected flag —
            # it must persist until consumed by regime cycle
            return False

        # 2. Buy acceleration: more buy volume in second half
        first_buy = sum(s for _, _, s, sell in first_half if not sell) or 0.001
        second_buy = sum(s for _, _, s, sell in second_half if not sell)
        buy_accelerating = second_buy > first_buy * 1.2

        # 3. Sell deceleration: less sell volume in second half
        first_sell = sum(s for _, _, s, sell in first_half if sell) or 0.001
        second_sell = sum(s for _, _, s, sell in second_half if sell)
        sell_decelerating = second_sell < first_sell * 0.8

        # 4. Price floor: second half low >= first half low
        first_sell_prices = [p for _, p, _, sell in first_half if sell]
        second_sell_prices = [p for _, p, _, sell in second_half if sell]
        price_floor = False
        if first_sell_prices and second_sell_prices:
            price_floor = min(second_sell_prices) >= min(first_sell_prices)

        # Pivot: delta crossed zero + at least 1 supporting signal
        signals = sum([buy_accelerating, sell_decelerating, price_floor])
        if signals >= 1:
            state.pivot_detected = True
            state.pivot_timestamp = timestamp
            return True

        return False

    def consume_pivot(self, symbol: str) -> bool:
        """Check and consume fast pivot flag. Called by regime cycle."""
        state = self._state.get(symbol)
        if state and state.pivot_detected:
            state.pivot_detected = False  # Consume
            return True
        return False

    def reset(self, symbol: str):
        """Reset state for symbol (on cascade state reset)."""
        self._state.pop(symbol, None)


# ==============================================================================
# Configuration
# ==============================================================================

# Per-coin liquidation trigger thresholds (P95 from research)
# These represent the 95th percentile of typical burst sizes per coin
# Bursts exceeding these values are statistically significant
COIN_LIQUIDATION_THRESHOLDS = {
    # HL liquidation fills are $11-$376 each. In a 10s burst window with a real
    # cascade (5-15 fills), total is $100-$5,000. Thresholds set at meaningful
    # burst level (was 100x higher, calibrated for Binance).
    'BTC': 500.0,
    'ETH': 300.0,
    'BNB': 200.0,

    'HYPE': 200.0,
    'SOL': 100.0,
    'DOGE': 50.0,
    'XRP': 100.0,
    'PEPE': 50.0,
    'WIF': 50.0,
    'BONK': 30.0,

    'AVAX': 100.0,
    'LINK': 80.0,
    'ARB': 50.0,
    'OP': 50.0,
    'SUI': 80.0,
    'APT': 80.0,
}

# Default threshold for coins not in the list
DEFAULT_LIQUIDATION_THRESHOLD = 100.0

# Post-liquidation exhaustion fade requires a stronger burst than trigger-only entry.
# These are per-coin minimum burst values (USD) calibrated for major symbols.
EXHAUSTION_FADE_MIN_BURST_BY_COIN = {
    "BTC": 2_500.0,
    "ETH": 1_500.0,
    "SOL": 600.0,
}

# Per-coin minimum liquidation COUNT for exhaustion fade quality filter.
# Backtest: counter-trend + liqs>=5 is the quality tier with strongest edge.
# BTC/ETH have higher liq frequency, alts have fewer but each more meaningful.
EXHAUSTION_FADE_MIN_LIQ_COUNT = {
    "BTC": 5,
    "ETH": 5,
    "SOL": 5,
    "HYPE": 5,
}
EXHAUSTION_FADE_DEFAULT_MIN_LIQ_COUNT = 3  # Alts: fewer liqs are still meaningful

# Coins excluded from exhaustion/rolling fade (backtest: fading doesn't work — cascade continues)
# XRP: 40% WR, ARB: 0% WR (3 trades all losers), TRX: too few events, ATOM: single trade loser
# OP: 0% WR in cascade (3 trades, all TRAILING_STOP_LOSS)
EXHAUSTION_FADE_EXCLUDED_COINS = {"XRP", "SUI", "TRX", "ATOM", "ARB", "OP"}

# Per-coin trailing stop config for exhaustion fade exits.
# Activation-threshold trailing: price must move activation_bps in your favor,
# then trail by trail_bps. Hard stop at sl_bps from entry.
# Calibrated from TP/SL grid backtest (11 days, 3889 cascades).
EXHAUSTION_FADE_TRAIL_CONFIG = {
    "BTC":  {"activation_bps": 10, "trail_bps": 5,  "sl_bps": 30},
    "ETH":  {"activation_bps": 15, "trail_bps": 8,  "sl_bps": 30},
    "SOL":  {"activation_bps": 20, "trail_bps": 10, "sl_bps": 30},
    "HYPE": {"activation_bps": 15, "trail_bps": 8,  "sl_bps": 30},
}
EXHAUSTION_FADE_DEFAULT_TRAIL = {"activation_bps": 15, "trail_bps": 8, "sl_bps": 30}

# ROLLING_FADE trailing stop config
# SOL 2026-02-28: tight trail (20bp activation, 15bp trail) exited at +$0.15
# on a 2.6% move. Trail activated too early, then tiny pullback triggered exit.
# Wide trail: let the trade run, accept overshoot (50bp SL survives momentum).
# Cascade bounces are 1-3% — need room to hold through initial volatility.
ROLLING_FADE_TRAIL_CONFIG = {
    "activation_pct": 0.008,   # 0.80% = 80 bps (let trade develop before trailing)
    "trail_pct": 0.004,        # 0.40% = 40 bps (give room for bounce volatility)
    "sl_pct": 0.005,           # 0.50% = 50 bps (unchanged — caps loss on bad entries)
}

# Cascade fuel gate: block ROLLING_FADE when too many positions remain at risk
ROLLING_FADE_FUEL_MIN_POSITIONS = 15   # Min positions at risk to block
ROLLING_FADE_FUEL_MIN_VALUE = 500_000  # Min notional at risk ($) to block


@dataclass(frozen=True)
class CascadeSniperConfig:
    """Configuration for cascade sniper strategy."""
    # Proximity threshold (0.5% = 0.005)
    proximity_threshold_pct: float = 0.005

    # Minimum value at risk to consider a cluster ($USD)
    min_cluster_value: float = 5_000.0

    # Minimum positions to form a cluster
    min_cluster_positions: int = 5  # Restored from testing value of 2

    # Dominance ratio - how much more one side must have
    # e.g., 0.7 means 70% of value must be on one side
    dominance_ratio: float = 0.65

    # Liquidation trigger threshold (DEPRECATED - use per-coin thresholds)
    # Kept for backwards compatibility, used as fallback
    liquidation_trigger_volume: float = 50_000.0

    # Use per-coin liquidation thresholds (research-backed P95 values)
    use_per_coin_thresholds: bool = True

    # Liquidation lookback window (seconds)
    liquidation_window_sec: float = 10.0

    # H6-A: Maximum delay for momentum entries (seconds since trigger)
    # Prevents late entries into cascades with poor risk/reward
    max_momentum_entry_delay: float = 10.0

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

    # Organic flow detection (research-backed absorption detection)
    # Replaces static orderbook depth with dynamic organic flow analysis
    use_organic_flow_detection: bool = True

    # Organic flow window (seconds)
    organic_flow_window_sec: float = 10.0

    # Minimum organic volume to confirm absorption ($USD)
    min_organic_volume: float = 500.0

    # Minimum quiet time since last liquidation (seconds)
    organic_quiet_time_sec: float = 2.0

    # Minimum organic ratio (|net|/total) for conviction
    organic_ratio_threshold: float = 0.3

    # Warmup gate configuration (Gate A)
    # Blocks entries until minimum flow data is collected
    use_warmup_gate: bool = True

    # Minimum fills tracked before allowing entry (per symbol)
    # HL taker fills are sparse for alts (~1/min). 15 fills in 60s window is enough
    # for meaningful orderflow. Other gates (ATR, absorption) provide real filtering.
    warmup_min_fills: int = 15

    # Minimum liquidation events tracked before allowing entry (per symbol)
    warmup_min_liqs: int = 3

    # Minimum elapsed time since session start (seconds)
    warmup_min_elapsed_sec: float = 120.0  # 2 minutes

    # Warmup logic: elapsed >= T_min AND (fills >= N_min OR liqs >= L_min)
    # This allows entry if we have time AND either sufficient fills or liquidations

    # Trend gate configuration (Gate B)
    # Blocks counter-trend entries during short-term moves
    use_trend_gate: bool = True

    # Return thresholds for blocking (as decimals, e.g., 0.0015 = 0.15%)
    # LONG blocked if ret_1m <= -threshold OR ret_3m <= -threshold_3m
    # SHORT blocked if ret_1m >= +threshold OR ret_3m >= +threshold_3m
    trend_gate_ret_1m_threshold: float = 0.0015  # 0.15%
    trend_gate_ret_3m_threshold: float = 0.0030  # 0.30%

    # Allow counter-trend if absorption is dominant (escape hatch)
    trend_gate_absorption_override: float = 0.65  # buy_ratio > 0.65 allows entry

    # Strict block when price data unavailable (both ret_1m and ret_3m are None)
    # Override requires BOTH high absorption AND extreme burst
    trend_gate_no_data_absorption_override: float = 0.75  # Higher threshold for no-data
    trend_gate_no_data_min_burst_value: float = 5_000.0  # Minimum cascade value for override

    # Cascade confirmation gate (Gate C)
    # Requires multiple bursts before triggering to avoid single-burst false positives
    use_cascade_confirmation_gate: bool = True

    # Minimum burst count to confirm cascade (within confirmation window)
    cascade_min_burst_count: int = 2

    # Time window for burst counting (seconds)
    cascade_confirmation_window_sec: float = 60.0

    # Refractory period between bursts (ignore bursts within this period)
    # Prevents one continuous cascade from counting as multiple bursts
    cascade_burst_refractory_sec: float = 10.0

    # Override: Allow immediate entry if absorption ratio is very high
    cascade_confirmation_absorption_override: float = 0.70  # buy_ratio > 0.70 allows entry

    # ATR-based stops (Gate D) - DISABLED by default, requires backtest validation
    # When enabled, replaces fixed % stop with ATR-scaled stop
    use_atr_stop: bool = False  # Disabled by default - enable after backtest

    # ATR multiplier for stop distance: stop = entry ± (k * ATR)
    atr_stop_multiplier: float = 1.5  # 1.5x ATR

    # Minimum stop distance as percentage (floor for very low ATR)
    atr_stop_min_pct: float = 0.002  # 0.2% minimum

    # Maximum stop distance as percentage (cap for tail loss protection)
    atr_stop_max_pct: float = 0.01  # 1.0% maximum

    # Grace period before stop activates (seconds)
    # Avoids instant churn from noise at entry
    atr_stop_grace_period_sec: float = 20.0

    # Absorption-aware stop: exit quickly if absorption collapses
    atr_stop_absorption_exit_threshold: float = 0.30  # Exit if buy_ratio < 0.30

    # Exhaustion fade mode: stricter burst confirmation
    # For non-overridden symbols, required_burst = max(default, trigger_threshold * multiplier)
    exhaustion_fade_default_min_burst_value: float = 500.0
    exhaustion_fade_burst_multiplier: float = 4.0


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
    EXHAUSTION_FADE = "EXHAUSTION_FADE"          # Fade only after strong burst + absorption (selective)
    ROLLING_FADE = "ROLLING_FADE"                # Fade 30m rolling liq spikes (no state machine)


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
    Recent liquidation activity.

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

        # Trigger burst: snapshot of burst that caused TRIGGERED transition
        # (10s window expires before EXHAUSTED state, so we preserve it here)
        self._trigger_burst: Dict[str, 'LiquidationBurst'] = {}

        # Gate C: Burst history for cascade confirmation
        # Per symbol: list of (timestamp, volume) tuples for each qualifying burst
        self._burst_history: Dict[str, List[tuple]] = {}

        # Per-symbol liq_z (set before update() by proposal generator)
        self._liq_z: Dict[str, float] = {}

        # Organic flow detector (research-backed absorption detection)
        self._organic_detector: Optional[OrganicFlowDetector] = None
        if config.use_organic_flow_detection:
            self._organic_detector = OrganicFlowDetector(
                window_sec=config.organic_flow_window_sec,
                min_organic_volume=config.min_organic_volume,
                min_quiet_time=config.organic_quiet_time_sec,
                organic_ratio_threshold=config.organic_ratio_threshold,
            )

        # Last absorption signal per symbol (for diagnostics)
        self._last_absorption_signal: Dict[str, AbsorptionSignal] = {}

        # Structural absorption tracker (8 signals, adaptive window)
        self._absorption_tracker = AbsorptionConfirmationTracker()

        # Running pivot detector (sub-second, per-fill)
        self._fast_pivot = RunningPivotDetector()

        # Gate B override flag: True when structural/fast pivot confirmed
        self._structural_pivot: Dict[str, bool] = {}

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
                self._burst_history.pop(symbol, None)  # Gate C: Clear burst history
                # Clear cascade direction to prevent stale data
                if self._organic_detector:
                    self._organic_detector.clear_cascade(symbol)
                self._fast_pivot.reset(symbol)
                self._structural_pivot.pop(symbol, None)
                new_state = CascadeState.NONE

            # Check for liquidation trigger (Gate C: cascade confirmation)
            elif self._is_cascade_triggered(liquidations, symbol, timestamp):
                self._states[symbol] = CascadeState.TRIGGERED
                self._triggered_at[symbol] = timestamp
                if liquidations:
                    self._trigger_burst[symbol] = liquidations
                    # Score burst exhaustion shape (signals 1 & 2)
                    if _exhaustion_scorer is not None:
                        _exhaustion_scorer.on_triggered(symbol, liquidations, timestamp)
                new_state = CascadeState.TRIGGERED

                # Set cascade direction for organic flow detector
                if self._organic_detector:
                    dominant = self.get_dominant_side(symbol)
                    primed_data = self._primed_data.get(symbol)
                    cluster_value = primed_data.total_value_at_risk if primed_data else 0
                    if dominant == "LONG":
                        # Long liqs → price dropping → DOWN cascade
                        self._organic_detector.set_cascade_active(
                            symbol, CascadeDirection.DOWN, cluster_value
                        )
                    elif dominant == "SHORT":
                        # Short liqs → price rising → UP cascade
                        self._organic_detector.set_cascade_active(
                            symbol, CascadeDirection.UP, cluster_value
                        )

                # FAST PATH: Check absorption immediately in the same cycle.
                # Don't wait for next cycle — pivots are delay-sensitive.
                if self._is_absorption_detected(symbol, liquidations, proximity, timestamp):
                    self._states[symbol] = CascadeState.ABSORBING
                    new_state = CascadeState.ABSORBING
            else:
                # Update primed data
                if proximity:
                    self._primed_data[symbol] = proximity

        # State: TRIGGERED -> Check for absorption or exhaustion
        elif old_state == CascadeState.TRIGGERED:
            trigger_time = self._triggered_at.get(symbol, 0)
            elapsed = timestamp - trigger_time

            # Check for absorption using organic flow (primary) or orderbook depth (fallback)
            if self._is_absorption_detected(symbol, liquidations, proximity, timestamp):
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
                self._burst_history.pop(symbol, None)  # Gate C: Clear burst history
                self._trigger_burst.pop(symbol, None)
                # Clear exhaustion scorer state
                if _exhaustion_scorer is not None:
                    _exhaustion_scorer.on_reset(symbol)
                # Clear cascade direction to prevent stale data
                if self._organic_detector:
                    self._organic_detector.clear_cascade(symbol)
                # Clear pivot detection state
                self._fast_pivot.reset(symbol)
                self._structural_pivot.pop(symbol, None)
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

    def _is_cascade_triggered(
        self,
        liquidations: Optional[LiquidationBurst],
        symbol: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> bool:
        """
        Check if liquidation activity indicates cascade start.

        Gate C: Cascade Confirmation
        - Requires burst_count >= min_burst_count within confirmation window
        - Uses refractory period to avoid counting continuous cascade as multiple bursts
        - Override: Allow immediate if absorption ratio > threshold

        Uses per-coin thresholds if enabled (research-backed P95 values).
        """
        if liquidations is None:
            return False

        if symbol is None:
            symbol = liquidations.symbol

        # Get per-coin threshold if enabled
        if self._config.use_per_coin_thresholds and symbol:
            # Extract coin from symbol (e.g., "BTCUSDT" -> "BTC")
            coin = symbol.replace('USDT', '').replace('USD', '')
            threshold = COIN_LIQUIDATION_THRESHOLDS.get(coin, DEFAULT_LIQUIDATION_THRESHOLD)
        else:
            threshold = self._config.liquidation_trigger_volume

        # Check if current liquidation volume meets threshold
        if liquidations.total_volume < threshold:
            return False

        # If cascade confirmation gate disabled, trigger immediately
        if not self._config.use_cascade_confirmation_gate:
            return True

        # Fast path: liq_z >= 2.5 already proves statistically significant cascade.
        # Skip the 2-burst requirement (10s+ delay) — the z-score IS the confirmation.
        liq_z = self._liq_z.get(symbol, 0.0)
        if liq_z >= 2.5:
            print(f"[CASCADE CONF] {symbol}: liq_z={liq_z:.2f} confirms cascade (skipping burst count)")
            return True

        # Get current timestamp (use window_end from burst if not provided)
        if timestamp is None:
            timestamp = liquidations.window_end

        # Initialize burst history for symbol if needed
        if symbol not in self._burst_history:
            self._burst_history[symbol] = []

        # Prune old bursts outside confirmation window
        cutoff = timestamp - self._config.cascade_confirmation_window_sec
        self._burst_history[symbol] = [
            (ts, vol) for ts, vol in self._burst_history[symbol]
            if ts > cutoff
        ]

        # Check refractory period - is this a new distinct burst?
        is_new_burst = True
        if self._burst_history[symbol]:
            last_burst_time = self._burst_history[symbol][-1][0]
            if timestamp - last_burst_time < self._config.cascade_burst_refractory_sec:
                is_new_burst = False

        # Record new burst
        if is_new_burst:
            self._burst_history[symbol].append((timestamp, liquidations.total_volume))
            print(f"[CASCADE CONF] {symbol}: Burst recorded (#{len(self._burst_history[symbol])}, ${liquidations.total_volume:,.0f})")

        # Check if we have enough bursts
        burst_count = len(self._burst_history[symbol])
        if burst_count >= self._config.cascade_min_burst_count:
            print(f"[CASCADE CONF] {symbol}: Confirmed with {burst_count} bursts")
            return True

        # Check absorption override - high absorption allows immediate entry
        # NOTE: cascade direction not set yet, so we use primed_data to determine direction
        # and compute ratio directly from detector state
        if self._organic_detector:
            # Determine expected cascade direction from primed data
            primed = self._primed_data.get(symbol)
            if primed:
                # Determine which side has more exposure (will be liquidated)
                is_long_dominant = primed.long_positions_value > primed.short_positions_value
                # Temporarily set cascade direction for absorption check
                from runtime.cascade import CascadeDirection
                temp_direction = CascadeDirection.DOWN if is_long_dominant else CascadeDirection.UP
                # Set direction, check absorption, then clear
                self._organic_detector.set_cascade_active(symbol, temp_direction, primed.total_value_at_risk)
                signal = self._organic_detector.check_absorption(symbol, timestamp)
                self._organic_detector.clear_cascade(symbol)  # Clear to avoid stale direction

                if signal.buying_ratio > self._config.cascade_confirmation_absorption_override:
                    print(f"[CASCADE CONF] {symbol}: Override - absorption ratio {signal.buying_ratio:.2f} > {self._config.cascade_confirmation_absorption_override}")
                    return True

        # Not enough bursts yet
        print(f"[CASCADE CONF] {symbol}: Waiting for confirmation ({burst_count}/{self._config.cascade_min_burst_count} bursts)")
        return False

    def _is_absorption_detected(
        self,
        symbol: str,
        liquidations: Optional[LiquidationBurst],
        proximity: Optional[ProximityData],
        timestamp: Optional[float] = None
    ) -> bool:
        """
        Layered pivot detection for cascade absorption.

        Detection layers (fastest first):
        1. FAST PIVOT: Running counters evaluated per-fill (~0.5s)
        2. STRUCTURAL: AbsorptionConfirmationTracker (2-15s adaptive)
        3. ORGANIC FLOW: OrganicFlowDetector ratio (10s window, existing)
        4. ORDERBOOK: Static absorption ratio (existing fallback)

        Layers 1-2 set structural_pivot flag → Gate B override.
        Layers 3-4 preserve existing behavior (no Gate B override).
        """
        primed = self._primed_data.get(symbol)
        if primed is None:
            return False

        structural_pivot = False
        detection_path = None

        # === LAYER 1: Fast pivot (running counters, evaluated per-fill) ===
        if self._fast_pivot.consume_pivot(symbol):
            coin = symbol.replace('USDT', '').replace('USD', '')
            combined = self._absorption_tracker.get_combined_observation(coin, timestamp)
            total = combined.total_signals

            if total >= 1:
                structural_pivot = True
                detection_path = f"FAST+STRUCTURAL:total_signals={total}"
            else:
                structural_pivot = True
                detection_path = "FAST_PIVOT:no_structural_yet"

        # === LAYER 2: Structural pivot (AbsorptionConfirmationTracker) ===
        if not structural_pivot:
            coin = symbol.replace('USDT', '').replace('USD', '')
            combined = self._absorption_tracker.get_combined_observation(coin, timestamp)
            abs_signals = combined.absorption.signals_confirmed
            ctrl_signals = combined.control_shift.control_signals_confirmed

            # Path A: Full structural (absorption + control shift confirmed)
            if combined.base_exhaustion_confirmed:
                structural_pivot = True
                detection_path = f"STRUCTURAL:abs={abs_signals},ctrl={ctrl_signals}"

            # Path B: Partial structural + organic flow supporting
            elif abs_signals >= 1 and ctrl_signals >= 1:
                if self._organic_detector:
                    signal = self._organic_detector.check_absorption(symbol, timestamp)
                    if signal.buying_ratio > 0.45:
                        structural_pivot = True
                        detection_path = f"PARTIAL+ORGANIC:abs={abs_signals},ctrl={ctrl_signals},ratio={signal.buying_ratio:.2f}"

        # === LAYER 2.5: Capitulation boost ===
        # When capitulation confidence >= 0.7 AND any structural signal exists,
        # promote to structural_pivot (strongest confidence = gate bypass).
        if not structural_pivot and _capitulation_tracker is not None:
            coin = symbol.replace('USDT', '').replace('USD', '')
            cap = _capitulation_tracker.get_metrics(coin, timestamp)
            if cap.confidence >= 0.7 and cap.total_fills >= 10:
                # Check if we have at least partial structural evidence
                combined = self._absorption_tracker.get_combined_observation(coin, timestamp)
                if combined.total_signals >= 1:
                    structural_pivot = True
                    detection_path = (
                        f"CAPITULATION+STRUCTURAL:cap={cap.confidence:.2f},"
                        f"close_ratio={cap.close_ratio:.2f},loss=${cap.cumulative_loss:.0f},"
                        f"flips={cap.flip_count},signals={combined.total_signals}"
                    )

        # === LAYER 3: Organic flow (existing, 10s window) ===
        if detection_path is None and self._organic_detector and self._config.use_organic_flow_detection:
            signal = self._organic_detector.check_absorption(symbol, timestamp)
            self._last_absorption_signal[symbol] = signal
            if signal.is_absorbing:
                detection_path = f"ORGANIC:ratio={signal.buying_ratio:.2f}"
                # NO Gate B override for organic-only

        # === LAYER 4: Orderbook absorption fallback ===
        if detection_path is None:
            absorption = self._absorption_data.get(symbol)
            if absorption is not None:
                dominant = self.get_dominant_side(symbol)
                if dominant == "LONG" and absorption.absorption_ratio_longs >= self._config.min_absorption_ratio_for_reversal:
                    detection_path = f"ORDERBOOK:ratio={absorption.absorption_ratio_longs:.2f}"
                elif dominant == "SHORT" and absorption.absorption_ratio_shorts >= self._config.min_absorption_ratio_for_reversal:
                    detection_path = f"ORDERBOOK:ratio={absorption.absorption_ratio_shorts:.2f}"

        if detection_path:
            print(f"[PIVOT] {symbol}: {detection_path}")
            self._structural_pivot[symbol] = structural_pivot
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
            return False  # No absorption data → no evidence for thesis → block entry

        dominant_side = self.get_dominant_side(symbol)
        if dominant_side is None:
            return False  # No dominant side → can't determine absorption context → block

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
        elif entry_mode == EntryMode.EXHAUSTION_FADE:
            # Exhaustion fade enters at EXHAUSTED state — absorption is implicit
            return True
        elif entry_mode == EntryMode.ROLLING_FADE:
            # Rolling fade bypasses state machine entirely — no absorption check
            return True

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

    def feed_liquidation(
        self,
        symbol: str,
        side: str,  # "long" or "short"
        value: float,
        timestamp: float
    ):
        """
        Feed a liquidation event to the organic flow detector.

        Should be called for every liquidation event detected.
        """
        if not self._organic_detector:
            return

        # Create a minimal LiquidationEvent for the detector
        from runtime.cascade import LiquidationEvent
        event = LiquidationEvent(
            symbol=symbol,
            wallet_address="",  # Not needed for flow detection
            liquidated_size=0,  # Not needed
            liquidation_price=0,  # Not needed
            side=side,
            value=value,
            timestamp=timestamp,
        )
        self._organic_detector.add_liquidation(event)

        # Feed structural tracker
        coin = symbol.replace('USDT', '').replace('USD', '')
        self._absorption_tracker.record_liquidation(coin, side, value, timestamp)

    def feed_orderbook(
        self,
        symbol: str,
        bids: List[Dict],
        asks: List[Dict],
        timestamp: float
    ):
        """
        Feed L2 orderbook to structural absorption tracker for regime context.

        Provides bid/ask depth, mid price, spread for adaptive threshold computation.
        """
        if not bids or not asks:
            return
        coin = symbol.replace('USDT', '').replace('USD', '')
        total_bid = sum(b['size'] * b['price'] for b in bids[:10])
        total_ask = sum(a['size'] * a['price'] for a in asks[:10])
        mid = (bids[0]['price'] + asks[0]['price']) / 2
        spread = asks[0]['price'] - bids[0]['price']
        self._absorption_tracker.record_orderbook(coin, total_bid, total_ask, mid, spread, timestamp)

    def feed_organic_trade(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        value: float,
        timestamp: float,
        wallet_address: Optional[str] = None,
        price: Optional[float] = None,
        size: Optional[float] = None
    ):
        """
        Feed an organic (non-liquidation) trade to detectors.

        Routes to:
        1. OrganicFlowDetector (existing, 10s window)
        2. RunningPivotDetector (per-fill, sub-second)
        3. AbsorptionConfirmationTracker (structural, 2-15s adaptive)
        """
        if self._organic_detector:
            self._organic_detector.add_organic_trade(
                symbol=symbol,
                timestamp=timestamp,
                side=side,
                value=value,
                wallet_address=wallet_address,
            )

        # Feed running pivot detector and structural tracker (need price/size)
        if price is not None and size is not None:
            is_sell = side.upper() == "SELL"
            self._fast_pivot.on_trade(symbol, price, size, is_sell, timestamp)

            coin = symbol.replace('USDT', '').replace('USD', '')
            self._absorption_tracker.record_trade(coin, price, size, is_sell, timestamp)

    def get_absorption_signal(self, symbol: str) -> Optional[AbsorptionSignal]:
        """Get the last absorption signal for a symbol (for diagnostics)."""
        return self._last_absorption_signal.get(symbol)

    def get_organic_flow_metrics(self) -> Optional[Dict]:
        """Get organic flow detector metrics."""
        if self._organic_detector:
            return self._organic_detector.get_metrics()
        return None


# ==============================================================================
# EP-2 Strategy: Cascade Sniper
# ==============================================================================

# Global state machine and entry quality scorer (stateful across calls)
_state_machine: Optional[CascadeStateMachine] = None
_entry_quality_scorer: Optional[EntryQualityScorer] = None
_config: Optional[CascadeSniperConfig] = None
_session_start_time: Optional[float] = None  # Gate A: Session start for warmup
_capitulation_tracker: Optional[CapitulationTracker] = None  # Capitulation detection
_exhaustion_scorer = None  # ExhaustionScorer — set via set_exhaustion_scorer()


def _get_state_machine() -> CascadeStateMachine:
    """Get or create the state machine singleton."""
    global _state_machine, _config, _session_start_time
    if _state_machine is None:
        _config = CascadeSniperConfig()
        _state_machine = CascadeStateMachine(_config)
        # Initialize session start time on first call
        import time
        _session_start_time = time.time()
    return _state_machine


def set_capitulation_tracker(tracker: CapitulationTracker):
    """Inject capitulation tracker for absorption confidence boosting."""
    global _capitulation_tracker
    _capitulation_tracker = tracker


def set_exhaustion_scorer(scorer):
    """Inject per-burst exhaustion scorer for EXHAUSTION_FADE quality gating."""
    global _exhaustion_scorer
    _exhaustion_scorer = scorer


def _check_warmup_gate(symbol: str, timestamp: float) -> tuple[bool, str]:
    """
    Gate A: Check if warmup conditions are met for entry.

    Warmup logic: elapsed >= T_min AND (fills >= N_min OR liqs >= L_min)
    This allows entry if we have sufficient time AND either fills or liquidations.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timestamp: Current timestamp

    Returns:
        (is_ready, reason) - True if warmup met, reason string for logging
    """
    global _config, _session_start_time

    if _config is None or not _config.use_warmup_gate:
        return True, "warmup_disabled"

    if _session_start_time is None:
        return False, "session_not_started"

    sm = _get_state_machine()
    if sm._organic_detector is None:
        return True, "no_detector"  # Can't check warmup without detector

    # Get warmup status for symbol
    status = sm._organic_detector.get_warmup_status(symbol)

    # Check elapsed time
    elapsed = timestamp - _session_start_time
    time_ok = elapsed >= _config.warmup_min_elapsed_sec

    # Check data conditions (either fills OR liqs sufficient)
    fills_ok = status['fill_count'] >= _config.warmup_min_fills
    liqs_ok = status['liq_count'] >= _config.warmup_min_liqs
    data_ok = fills_ok or liqs_ok

    # Warmup met if time AND data conditions satisfied
    if time_ok and data_ok:
        return True, f"warmup_ok:elapsed={elapsed:.0f}s,fills={status['fill_count']},liqs={status['liq_count']}"

    # Not ready - return detailed reason
    reasons = []
    if not time_ok:
        reasons.append(f"elapsed={elapsed:.0f}s<{_config.warmup_min_elapsed_sec:.0f}s")
    if not data_ok:
        reasons.append(f"fills={status['fill_count']}<{_config.warmup_min_fills},liqs={status['liq_count']}<{_config.warmup_min_liqs}")

    return False, f"warmup_not_met:{';'.join(reasons)}"


def _check_trend_gate(
    symbol: str,
    entry_direction: str,
    price_returns: Optional[Dict[str, Optional[float]]],
    absorption_ratio: Optional[float] = None,
    cascade_value: Optional[float] = None
) -> tuple[bool, str]:
    """
    Gate B: Check if trend conditions allow entry.

    Blocks counter-trend entries during short-term directional moves.
    - LONG blocked if ret_1m <= -0.15% OR ret_3m <= -0.30%
    - SHORT blocked if ret_1m >= +0.15% OR ret_3m >= +0.30%

    Escape hatch: Allow if absorption_ratio > threshold (dominant absorption).

    STRICT BLOCK: If both ret_1m and ret_3m are None (no price data), block entry
    unless BOTH conditions are met:
    - absorption_ratio > 0.75 (very high absorption)
    - cascade_value > threshold (extreme burst magnitude)

    Args:
        symbol: Trading symbol
        entry_direction: "LONG" or "SHORT"
        price_returns: Dict with ret_1m and ret_3m (from observation.get_hl_price_returns)
        absorption_ratio: Optional buy_ratio for escape hatch
        cascade_value: Optional cascade value at risk for no-data override

    Returns:
        (is_allowed, reason) - True if entry allowed, reason string for logging
    """
    global _config

    if _config is None or not _config.use_trend_gate:
        return True, "trend_gate_disabled"

    # Extract returns from dict (or None if dict is None)
    ret_1m = price_returns.get('ret_1m') if price_returns else None
    ret_3m = price_returns.get('ret_3m') if price_returns else None

    # STRICT BLOCK: No price data available
    # Block unless BOTH high absorption AND extreme burst
    if ret_1m is None and ret_3m is None:
        # Check override conditions
        absorption_ok = (
            absorption_ratio is not None and
            absorption_ratio > _config.trend_gate_no_data_absorption_override
        )
        burst_ok = (
            cascade_value is not None and
            cascade_value >= _config.trend_gate_no_data_min_burst_value
        )

        if absorption_ok and burst_ok:
            return True, (
                f"no_data_override:absorption={absorption_ratio:.2f}>"
                f"{_config.trend_gate_no_data_absorption_override},"
                f"cascade=${cascade_value:,.0f}>=${_config.trend_gate_no_data_min_burst_value:,.0f}"
            )

        # Block - no data and override conditions not met
        reasons = []
        if not absorption_ok:
            ratio_str = f"{absorption_ratio:.2f}" if absorption_ratio else "None"
            reasons.append(f"absorption={ratio_str}<={_config.trend_gate_no_data_absorption_override}")
        if not burst_ok:
            value_str = f"${cascade_value:,.0f}" if cascade_value else "None"
            reasons.append(f"cascade={value_str}<${_config.trend_gate_no_data_min_burst_value:,.0f}")

        return False, f"no_price_data_blocked:{';'.join(reasons)}"

    # Check escape hatch first - dominant absorption overrides trend block
    if absorption_ratio is not None and absorption_ratio > _config.trend_gate_absorption_override:
        return True, f"absorption_override:ratio={absorption_ratio:.2f}>{_config.trend_gate_absorption_override}"

    # Check trend conditions based on entry direction
    blocked = False
    block_reason = ""

    if entry_direction == "LONG":
        # Block LONG if price dropping
        if ret_1m is not None and ret_1m <= -_config.trend_gate_ret_1m_threshold:
            blocked = True
            block_reason = f"ret_1m={ret_1m*100:.2f}%<=-{_config.trend_gate_ret_1m_threshold*100:.2f}%"
        elif ret_3m is not None and ret_3m <= -_config.trend_gate_ret_3m_threshold:
            blocked = True
            block_reason = f"ret_3m={ret_3m*100:.2f}%<=-{_config.trend_gate_ret_3m_threshold*100:.2f}%"

    elif entry_direction == "SHORT":
        # Block SHORT if price rising
        if ret_1m is not None and ret_1m >= _config.trend_gate_ret_1m_threshold:
            blocked = True
            block_reason = f"ret_1m={ret_1m*100:.2f}%>={_config.trend_gate_ret_1m_threshold*100:.2f}%"
        elif ret_3m is not None and ret_3m >= _config.trend_gate_ret_3m_threshold:
            blocked = True
            block_reason = f"ret_3m={ret_3m*100:.2f}%>={_config.trend_gate_ret_3m_threshold*100:.2f}%"

    if blocked:
        return False, f"trend_blocked:{block_reason}"

    # Format return info for logging
    ret_info = []
    if ret_1m is not None:
        ret_info.append(f"ret_1m={ret_1m*100:.2f}%")
    if ret_3m is not None:
        ret_info.append(f"ret_3m={ret_3m*100:.2f}%")

    return True, f"trend_ok:{','.join(ret_info)}"


def calculate_atr_stop_distance(
    entry_price: float,
    direction: str,
    atr_value: Optional[float],
) -> tuple[float, str]:
    """
    Gate D: Calculate ATR-based stop distance.

    DISABLED BY DEFAULT - requires backtest validation before enabling.
    Use use_atr_stop=True in config to enable.

    Args:
        entry_price: Entry price
        direction: "LONG" or "SHORT"
        atr_value: Current ATR value (1-minute timeframe recommended)

    Returns:
        (stop_price, reason) - Stop price and calculation details
    """
    global _config

    if _config is None or not _config.use_atr_stop:
        # Fallback to fixed 0.25% stop (current default behavior)
        default_pct = 0.0025
        if direction == "LONG":
            stop_price = entry_price * (1 - default_pct)
        else:
            stop_price = entry_price * (1 + default_pct)
        return stop_price, f"fixed_pct:{default_pct*100:.2f}%"

    # Calculate ATR-based distance
    if atr_value is None or atr_value <= 0:
        # No ATR data - use minimum
        distance_pct = _config.atr_stop_min_pct
        reason = f"no_atr:using_min={distance_pct*100:.2f}%"
    else:
        # ATR-based distance: k * ATR / price
        distance_pct = (_config.atr_stop_multiplier * atr_value) / entry_price

        # Apply floor and ceiling
        if distance_pct < _config.atr_stop_min_pct:
            distance_pct = _config.atr_stop_min_pct
            reason = f"atr_floor:{distance_pct*100:.2f}%"
        elif distance_pct > _config.atr_stop_max_pct:
            distance_pct = _config.atr_stop_max_pct
            reason = f"atr_ceiling:{distance_pct*100:.2f}%"
        else:
            reason = f"atr_based:{distance_pct*100:.2f}% (atr={atr_value:.2f},k={_config.atr_stop_multiplier})"

    # Calculate stop price
    if direction == "LONG":
        stop_price = entry_price * (1 - distance_pct)
    else:
        stop_price = entry_price * (1 + distance_pct)

    return stop_price, reason


def check_atr_stop_grace_period(entry_time: float, current_time: float) -> bool:
    """
    Check if stop should be active based on grace period.

    Returns True if grace period has passed (stop should be active).
    Returns False if still in grace period (stop should be ignored).
    """
    global _config

    if _config is None or not _config.use_atr_stop:
        return True  # Grace period only applies when ATR stops enabled

    elapsed = current_time - entry_time
    return elapsed >= _config.atr_stop_grace_period_sec


def check_absorption_exit(symbol: str, timestamp: float) -> tuple[bool, str]:
    """
    Gate D: Check if absorption has collapsed and quick exit is needed.

    When absorption ratio drops below threshold, exit quickly to limit losses.
    This is an "absorption-aware stop" that reacts to flow conditions.

    Returns:
        (should_exit, reason) - True if exit triggered, reason for logging
    """
    global _config

    if _config is None or not _config.use_atr_stop:
        return False, "atr_stop_disabled"

    sm = _get_state_machine()
    if sm._organic_detector is None:
        return False, "no_detector"

    signal = sm._organic_detector.check_absorption(symbol, timestamp)

    if signal.buying_ratio < _config.atr_stop_absorption_exit_threshold:
        return True, f"absorption_collapsed:ratio={signal.buying_ratio:.2f}<{_config.atr_stop_absorption_exit_threshold}"

    return False, f"absorption_ok:ratio={signal.buying_ratio:.2f}"


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

    MUST be called for each liquidation event from the liquidation stream.
    This feeds the exhaustion reversal detection.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        side: "BUY" (short liquidated) or "SELL" (long liquidated)
        value: USD value of liquidation
        timestamp: Event timestamp
    """
    scorer = _get_entry_quality_scorer()
    scorer.record_liquidation(symbol, side, value, timestamp)

    # Also feed to organic flow detector for absorption detection
    # Convert "BUY"/"SELL" to "short"/"long" (opposite mapping)
    liq_side = "short" if side == "BUY" else "long"
    sm = _get_state_machine()
    sm.feed_liquidation(symbol, liq_side, value, timestamp)


def record_organic_trade(
    symbol: str,
    side: str,  # "BUY" or "SELL"
    value: float,
    timestamp: float,
    wallet_address: Optional[str] = None,
    price: Optional[float] = None,
    size: Optional[float] = None
):
    """
    Record an organic (non-liquidation) trade for absorption detection.

    Call this for regular trades to track organic flow.
    Routes to OrganicFlowDetector, RunningPivotDetector, and AbsorptionConfirmationTracker.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        side: "BUY" or "SELL"
        value: USD value of trade
        timestamp: Event timestamp
        wallet_address: Optional wallet for liquidator filtering
        price: Trade price (for structural pivot detection)
        size: Trade size in base units (for structural pivot detection)
    """
    sm = _get_state_machine()
    sm.feed_organic_trade(symbol, side, value, timestamp, wallet_address,
                          price=price, size=size)


def record_orderbook_update(
    symbol: str,
    bids: List[Dict],
    asks: List[Dict],
    timestamp: float
):
    """
    Feed L2 orderbook to cascade sniper for structural absorption detection.

    Provides regime context (bid/ask depth, spread) for adaptive thresholds.
    """
    sm = _get_state_machine()
    sm.feed_orderbook(symbol, bids, asks, timestamp)


def get_absorption_signal(symbol: str) -> Optional[AbsorptionSignal]:
    """
    Get the last absorption signal for a symbol.

    Useful for diagnostics and monitoring absorption detection.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")

    Returns:
        AbsorptionSignal with detection details, or None
    """
    sm = _get_state_machine()
    return sm.get_absorption_signal(symbol)


def get_organic_flow_metrics() -> Optional[Dict]:
    """
    Get organic flow detector metrics.

    Returns:
        Dict with detector statistics, or None if not enabled
    """
    sm = _get_state_machine()
    return sm.get_organic_flow_metrics()


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
    trend_context: Optional[TrendRegimeContext] = None,
    price_returns: Optional[Dict[str, Optional[float]]] = None,  # Gate B: {ret_1m, ret_3m}
    trade_burst=None,  # TradeBurst | None (B4 - cascade trading intensity)
    liquidation_density=None,  # LiquidationDensity | None (B3 - cluster quality)
    liquidation_zscore: Optional[float] = None,  # Z-score of liquidation rate (from regime metrics)
    rolling_fade_signal: Optional[RollingFadeSignal] = None,  # Rolling 30m liq spike signal
    orderflow_imbalance: Optional[float] = None  # Taker buy ratio 0-1 (from regime_metrics)
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
        liquidations: Recent liquidation burst
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

    # Determine symbol from proximity, liquidation, or rolling fade data
    symbol = None
    if proximity:
        symbol = proximity.coin + "USDT"  # Convert "BTC" -> "BTCUSDT"
    elif liquidations:
        symbol = liquidations.symbol
    elif rolling_fade_signal:
        symbol = rolling_fade_signal.symbol

    if symbol is None:
        return None

    # Gate A: Warmup gate - block entries until sufficient data collected
    warmup_ok, warmup_reason = _check_warmup_gate(symbol, context.timestamp)
    if not warmup_ok:
        print(f"[WARMUP GATE] {symbol}: Entry blocked - {warmup_reason}")
        return None

    # Set liq_z on state machine for Gate C fast-path
    if liquidation_zscore is not None:
        sm._liq_z[symbol] = liquidation_zscore

    # Update state machine with absorption data
    state = sm.update(symbol, proximity, liquidations, context.timestamp, absorption)

    # Get entry quality scorer
    eq_scorer = _get_entry_quality_scorer()

    # Rule 3: Generate entry proposal based on state and mode
    if entry_mode == EntryMode.ABSORPTION_REVERSAL:
        # FAST ENTRY: When liq_z confirms massive cascade AND pivot detected,
        # enter from TRIGGERED state without waiting for ABSORBING.
        # At pivots, the sharpest price move happens in the first 1-2 seconds.
        if state == CascadeState.TRIGGERED:
            liq_z_confirmed = (liquidation_zscore is not None and liquidation_zscore >= 2.5)
            structural_pivot = sm._structural_pivot.get(symbol, False)
            if liq_z_confirmed and structural_pivot:
                # Promote to ABSORBING immediately and fall through
                sm._states[symbol] = CascadeState.ABSORBING
                state = CascadeState.ABSORBING
                print(f"[FAST ENTRY] {symbol}: TRIGGERED → ABSORBING (liq_z={liquidation_zscore:.2f} + structural pivot)")

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
                # Reversal entries are DANGEROUS during strong trends — UNLESS
                # a statistically significant liquidation cascade is in progress.
                # liq_z >= 2.5 means current liquidation rate is 2.5σ above baseline,
                # which IS the catalyst that reverses the trend. Blocking here would
                # defeat the entire purpose of cascade sniper.
                if trend_context is not None:
                    if _is_reversal_blocked_by_trend(entry_direction, trend_context):
                        structural_pivot = sm._structural_pivot.get(symbol, False)
                        liq_z_override = (liquidation_zscore is not None and liquidation_zscore >= 2.5)
                        if structural_pivot and liq_z_override:
                            print(f"[TREND KILL-SWITCH] {symbol}: {entry_direction} OVERRIDDEN — "
                                  f"liq_z={liquidation_zscore:.2f} + structural pivot during {trend_context.direction.name}")
                        else:
                            reasons = []
                            if not structural_pivot:
                                reasons.append("no_structural_pivot")
                            if not liq_z_override:
                                lz = f"{liquidation_zscore:.2f}" if liquidation_zscore is not None else "None"
                                reasons.append(f"liq_z={lz}<2.5")
                            print(f"[TREND KILL-SWITCH] {symbol}: {entry_direction} reversal blocked - "
                                  f"{trend_context.direction.name} ({', '.join(reasons)})")
                            return None

                # Gate B: Short-term trend gate (price returns)
                # OVERRIDE: Skip Gate B when structural/fast pivot confirmed
                # (structural signals already validate the reversal is real)
                structural_pivot = sm._structural_pivot.get(symbol, False)
                if structural_pivot:
                    print(f"[TREND GATE] {symbol}: OVERRIDDEN by structural pivot")
                else:
                    absorption_signal = sm.get_absorption_signal(symbol)
                    absorption_ratio = absorption_signal.buying_ratio if absorption_signal else None
                    cascade_value = primed.total_value_at_risk if primed else None
                    trend_ok, trend_reason = _check_trend_gate(
                        symbol, entry_direction, price_returns, absorption_ratio, cascade_value
                    )
                    if not trend_ok:
                        print(f"[TREND GATE] {symbol}: {entry_direction} blocked - {trend_reason}")
                        return None

                # Rule 3b: Check entry quality based on liquidation exhaustion
                # This uses the data-driven scoring from analysis of 759 trades
                # Pass trend context for additional filtering
                #
                # OVERRIDE: When liq_z >= 2.5, the aggregate liquidation signal proves
                # "significant liquidation context" even if individual HL liqs are small
                # (HL captures micro-liqs at $42-$7k that fail the $10k individual threshold)
                liq_z_significant = (liquidation_zscore is not None and liquidation_zscore >= 2.5)
                if _config and _config.use_entry_quality_filter and not liq_z_significant:
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
                    # No filter OR liq_z override — get score for logging only
                    eq_score = eq_scorer.score_entry(symbol, entry_direction, context.timestamp, trend_context)
                    if liq_z_significant:
                        print(f"[EQ FILTER] {symbol}: OVERRIDDEN — liq_z={liquidation_zscore:.2f} proves aggregate liquidation significance")

                # Include absorption ratio and entry quality in justification
                absorption_data = sm.get_absorption_data(symbol)
                ratio_str = ""
                if absorption_data:
                    ratio = absorption_data.absorption_ratio_longs if dominant_side == "LONG" else absorption_data.absorption_ratio_shorts
                    ratio_str = f"|ABSORB:{ratio:.2f}"

                eq_str = f"|EQ:{eq_score.quality.value}:{eq_score.score:.2f}"

                # Enrich with trade burst intensity and liquidation cluster density
                burst_str = ""
                if trade_burst is not None:
                    burst_str = f"|BURST:{trade_burst.trades_per_second:.1f}tps"
                density_str = ""
                if liquidation_density is not None:
                    density_str = f"|LDENSITY:{liquidation_density.density_score:.2f}"

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="ABSORPTION_REVERSAL",
                    justification_ref=f"HL_PROX|ABSORB|{primed.total_positions_at_risk}pos|${primed.total_value_at_risk:.0f}{ratio_str}{eq_str}{burst_str}{density_str}",
                    timestamp=context.timestamp
                )

    elif entry_mode == EntryMode.CASCADE_MOMENTUM:
        # Enter on trigger (momentum play)
        if state == CascadeState.TRIGGERED:
            dominant_side = sm.get_dominant_side(symbol)
            primed = sm.get_primed_data(symbol)

            if dominant_side and primed:
                # H6-A: Check cascade age - reject late entries
                trigger_time = sm._triggered_at.get(symbol, 0)
                elapsed_since_trigger = context.timestamp - trigger_time
                if elapsed_since_trigger > _config.max_momentum_entry_delay:
                    print(f"[H6-A LATE ENTRY] {symbol}: Momentum entry blocked - {elapsed_since_trigger:.1f}s since trigger (max {_config.max_momentum_entry_delay}s)")
                    return None

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

                # Enrich with trade burst intensity and liquidation cluster density
                burst_str = ""
                if trade_burst is not None:
                    burst_str = f"|BURST:{trade_burst.trades_per_second:.1f}tps"
                density_str = ""
                if liquidation_density is not None:
                    density_str = f"|LDENSITY:{liquidation_density.density_score:.2f}"

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="CASCADE_MOMENTUM",
                    justification_ref=f"HL_PROX|TRIGGER|{primed.total_positions_at_risk}pos|${primed.total_value_at_risk:.0f}{ratio_str}{eq_str}{burst_str}{density_str}",
                    timestamp=context.timestamp
                )

    elif entry_mode == EntryMode.EXHAUSTION_FADE:
        # EXHAUSTION FADE: Enter immediately at TRIGGERED to fade the liquidation burst.
        # Backtest (11 days, 3889 cascades): counter-trend + liqs>=5 = -7.5bp mean, 72% win.
        # Enter at TRIGGERED (not EXHAUSTED) — every second of delay costs edge.
        if state == CascadeState.TRIGGERED:
            dominant_side = sm.get_dominant_side(symbol)
            primed = sm.get_primed_data(symbol)

            # Use the trigger burst stored at TRIGGERED transition
            trigger_burst = sm._trigger_burst.get(symbol)
            if dominant_side and primed and trigger_burst:
                coin = symbol.replace('USDT', '').replace('USD', '')

                # Gate: Exclude coins where fading doesn't work (cascade continues)
                if coin in EXHAUSTION_FADE_EXCLUDED_COINS:
                    return None

                # Gate: Minimum liquidation count (quality filter)
                min_liqs = EXHAUSTION_FADE_MIN_LIQ_COUNT.get(coin, EXHAUSTION_FADE_DEFAULT_MIN_LIQ_COUNT)
                if trigger_burst.liquidation_count < min_liqs:
                    return None  # Too few liquidations — not a real cascade

                # Gate: Minimum burst volume (per-coin)
                abs_burst = trigger_burst.total_volume
                min_burst = EXHAUSTION_FADE_MIN_BURST_BY_COIN.get(
                    coin, _config.exhaustion_fade_default_min_burst_value
                )
                if abs_burst < min_burst:
                    return None  # Burst too small for fade

                # Gate: Counter-trend momentum (strongest edge in backtest)
                # We WANT the cascade to go against prior price trend (exhaustion).
                # If price was falling and longs get liquidated (cascade DOWN), that's
                # trend-following — weaker fade. If price was RISING and longs get
                # liquidated, that's counter-trend — strongest fade.
                # Fade direction: same as dominant_side (LONG liqs → fade LONG = buy)
                entry_direction = dominant_side

                # Check 1m return: cascade should be AGAINST prior trend
                # LONG fade (buy) → want ret_1m > 0 (price was rising, then longs liquidated = reversal)
                # SHORT fade (sell) → want ret_1m < 0 (price was falling, then shorts liquidated = reversal)
                ret_1m = price_returns.get('ret_1m') if price_returns else None
                if ret_1m is not None:
                    if entry_direction == "LONG" and ret_1m > 0:
                        # Price was rising, longs liquidated = cascade against trend ✓
                        pass
                    elif entry_direction == "SHORT" and ret_1m < 0:
                        # Price was falling, shorts liquidated = cascade against trend ✓
                        pass
                    elif abs(ret_1m) < 0.0005:
                        # Near-zero momentum — allow (neutral)
                        pass
                    else:
                        # Cascade goes WITH the trend — weaker edge, skip
                        print(f"[EXHAUST FADE] {symbol}: {entry_direction} blocked — "
                              f"cascade is trend-following (ret_1m={ret_1m*100:+.2f}%)")
                        return None

                # Entry quality filter (optional)
                if _config and _config.use_entry_quality_filter:
                    should_enter, eq_score = eq_scorer.get_entry_recommendation(
                        symbol=symbol,
                        intended_side=entry_direction,
                        min_quality=_config.min_entry_quality,
                        require_large_liq=_config.require_large_liquidations,
                        trend_context=trend_context
                    )
                    if not should_enter:
                        print(f"[EQ FILTER] {symbol}: {entry_direction} exhaustion fade blocked - {eq_score.reason}")
                        return None
                else:
                    eq_score = eq_scorer.score_entry(symbol, entry_direction, context.timestamp, trend_context)

                eq_str = f"|EQ:{eq_score.quality.value}:{eq_score.score:.2f}"
                ret_str = f"|ret1m={ret_1m*100:+.1f}%" if ret_1m is not None else ""
                trail_cfg = EXHAUSTION_FADE_TRAIL_CONFIG.get(coin, EXHAUSTION_FADE_DEFAULT_TRAIL)

                return StrategyProposal(
                    strategy_id="EP2-CASCADE-SNIPER-V1",
                    action_type="ENTRY",
                    direction=entry_direction,
                    confidence="EXHAUSTION_FADE",
                    justification_ref=(
                        f"HL_PROX|FADE|{trigger_burst.liquidation_count}liqs"
                        f"|${abs_burst:.0f}burst{ret_str}{eq_str}"
                        f"|trail:act={trail_cfg['activation_bps']}t={trail_cfg['trail_bps']}sl={trail_cfg['sl_bps']}"
                    ),
                    timestamp=context.timestamp
                )

    elif entry_mode == EntryMode.ROLLING_FADE:
        # ROLLING_FADE: Skip state machine entirely. Uses 30m rolling window spike detection.
        # Backtest (11 days, 114M lines): z>=1.5, 30s confirm, activated trailing = 91% WR, +0.56% mean.
        if rolling_fade_signal is not None:
            entry_direction = rolling_fade_signal.fade_direction
            coin = symbol.replace('USDT', '').replace('USD', '')

            # Gate: Exclude coins where fading doesn't work
            if coin in EXHAUSTION_FADE_EXCLUDED_COINS:
                return None

            # Gate: Minimum liquidation count (quality filter — same as EXHAUSTION_FADE)
            min_liqs = EXHAUSTION_FADE_MIN_LIQ_COUNT.get(coin, EXHAUSTION_FADE_DEFAULT_MIN_LIQ_COUNT)
            if rolling_fade_signal.liq_count < min_liqs:
                print(f"[ROLL FADE] {symbol}: blocked — liq count "
                      f"{rolling_fade_signal.liq_count} < {min_liqs}")
                return None

            # Gate: Minimum burst volume (reuse EXHAUSTION_FADE thresholds)
            min_burst = EXHAUSTION_FADE_MIN_BURST_BY_COIN.get(
                coin, _config.exhaustion_fade_default_min_burst_value
            )
            if rolling_fade_signal.spike_volume < min_burst:
                print(f"[ROLL FADE] {symbol}: blocked — burst volume "
                      f"${rolling_fade_signal.spike_volume:.0f} < ${min_burst:.0f}")
                return None

            # Counter-trend and orderflow gates REMOVED for ROLLING_FADE.
            # During a cascade, ret_1m is negative (crash) and OF is selling —
            # that's the SETUP, not a reason to block. The burst signal (10x+ ratio,
            # concentration, exhaustion) + 60s confirmation delay is sufficient evidence.
            # SOL 2026-02-28: BTC/ETH blocked by these gates while all coins bounced 2%+.
            ret_1m = price_returns.get('ret_1m') if price_returns else None

            # Cascade fuel gate: block when many positions remain at risk on cascade side
            if proximity is not None:
                if entry_direction == "LONG":
                    fuel_count = proximity.long_positions_count
                    fuel_value = proximity.long_positions_value
                else:
                    fuel_count = proximity.short_positions_count
                    fuel_value = proximity.short_positions_value

                if fuel_count >= ROLLING_FADE_FUEL_MIN_POSITIONS and fuel_value >= ROLLING_FADE_FUEL_MIN_VALUE:
                    print(f"[ROLL FADE] {symbol}: blocked — cascade fuel remaining "
                          f"({fuel_count} positions, ${fuel_value:,.0f} at risk)")
                    return None

            # Entry quality: score for logging but do NOT block.
            # ROLLING_FADE's own signal quality (z-score, volume, confirmation delay)
            # provides sufficient filtering. The EQ filter conflicts with ROLLING_FADE's
            # counter-trend nature (it blocks buys during selloffs, which is exactly when
            # we want to fade).
            eq_scorer = _get_entry_quality_scorer()
            eq_score = eq_scorer.score_entry(symbol, entry_direction, context.timestamp, trend_context)

            eq_str = f"|EQ:{eq_score.quality.value}:{eq_score.score:.2f}"
            ret_str = f"|ret1m={ret_1m*100:+.1f}%" if ret_1m is not None else ""

            fuel_str = ""
            if proximity is not None:
                if entry_direction == "LONG":
                    fuel_str = f"|fuel:{proximity.long_positions_count}pos/${proximity.long_positions_value:,.0f}"
                else:
                    fuel_str = f"|fuel:{proximity.short_positions_count}pos/${proximity.short_positions_value:,.0f}"

            return StrategyProposal(
                strategy_id="EP2-CASCADE-SNIPER-V1",
                action_type="ENTRY",
                direction=entry_direction,
                confidence="ROLLING_FADE",
                justification_ref=(
                    f"ROLL_FADE|ratio={rolling_fade_signal.z_score:.1f}x"
                    f"|${rolling_fade_signal.spike_volume:.0f}"
                    f"|{rolling_fade_signal.liq_count}liqs{ret_str}{eq_str}{fuel_str}"
                ),
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
    global _state_machine, _entry_quality_scorer, _capitulation_tracker, _exhaustion_scorer
    _state_machine = None
    _entry_quality_scorer = None
    _capitulation_tracker = None
    _exhaustion_scorer = None


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
    trend_context: Optional[TrendRegimeContext] = None,
    price_returns: Optional[Dict[str, Optional[float]]] = None  # Gate B: {ret_1m, ret_3m}
) -> Optional[StrategyProposal]:
    """
    Generate cascade sniper proposal from M4PrimitiveBundle WITH TREND KILL-SWITCH.

    This is the constitutional flow - data comes from M4 primitives via M5,
    not directly injected from HyperliquidCollector.

    TREND KILL-SWITCH:
    - Reversal entries are blocked during strong directional moves
    - Momentum entries benefit from trend alignment (bonus applied)

    TREND GATE (Gate B):
    - Blocks counter-trend entries based on short-term price returns

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
    # DATA SOURCE CONTRACT NOTE: cascade_state comes from HL which has direct LONG/SHORT
    # side information. The 50/50 split here is a TEMPORARY APPROXIMATION pending proper
    # side tracking in cascade_state. This does NOT violate data contracts because we're
    # working within HL's native data.
    # TODO: Add long_value/short_value to cascade_state when HL breakdown is available
    liquidations = None
    if cascade_state and cascade_state.liquidations_30s > 0:
        # Approximate side split - cascade_state tracks total, not per-side
        liquidations = LiquidationBurst(
            symbol=cascade_state.symbol + "USDT",
            total_volume=cascade_state.cascade_value_liquidated,
            long_liquidations=cascade_state.cascade_value_liquidated / 2,  # Approximation (see note above)
            short_liquidations=cascade_state.cascade_value_liquidated / 2,  # Approximation (see note above)
            liquidation_count=cascade_state.liquidations_30s,
            window_start=cascade_state.timestamp - 30.0,
            window_end=cascade_state.timestamp
        )

    # Delegate to existing function with trend context and price returns
    return generate_cascade_sniper_proposal(
        permission=permission,
        proximity=proximity,
        liquidations=liquidations,
        context=context,
        position_state=position_state,
        entry_mode=entry_mode,
        trend_context=trend_context,
        price_returns=price_returns
    )
