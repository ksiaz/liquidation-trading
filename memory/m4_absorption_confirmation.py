"""
M4 Primitive: Absorption Confirmation (Hardened)

THREE-PHASE CONFIRMATION WITH HARDENINGS:
1. ABSORPTION: Sellers trying AND failing to move price
2. CONTROL SHIFT: Buyers actually taking over (not just pause)
3. CONTEXT VALIDATION: Trend regime + persistence checks

HARDENINGS APPLIED:
1. TREND REGIME FILTER
   - Prevents fading strong directional moves
   - Delta flattening during distribution ≠ exhaustion
   - Requires trend context to interpret absorption

2. WHALE FLOW WEIGHTING
   - Large trades weighted higher than small trades
   - 1 whale exhausting > 100 retail prints
   - Volume-weighted metrics separate meaningful from noise

3. PERSISTENCE TRACKING
   - Depth survival: how long do bids persist after appearing?
   - Control shift duration: does buyer activity persist?
   - Flash bids and brief buyer activity filtered out

ABSORPTION SIGNALS:
1. Bid absorption - large sells eaten without price drop
2. Orderbook replenishment - bid depth rebuilds after sweeps
3. Aggressor failure - high sell volume, shrinking downside range
4. Delta divergence - cumulative delta flattening while sells continue

CONTROL SHIFT SIGNALS:
1. Bid aggression increase - buyers crossing spread (lifting asks)
2. Buy volume acceleration - buy volume increasing post-absorption
3. Price floor establishment - higher lows forming
4. Imbalance flip - transition from sell-heavy to buy-heavy

REGIME-ADAPTIVE DESIGN:
- All thresholds are RELATIVE to current market context
- Volatility-normalized metrics
- Liquidity-relative thresholds (percentile, not absolute)
- Adaptive time windows based on trade rate

Constitutional compliance:
- Observable metrics only (trades, orderbook, price)
- No prediction of future behavior
- Reports what IS happening, not what WILL happen

Cannot imply: reversal incoming, safe to buy, exhaustion complete
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple
from collections import deque
import time
import math


class AbsorptionPhase(Enum):
    """
    Observable absorption states.

    Describes what IS happening, not what WILL happen.
    """
    NONE = auto()              # No absorption detected
    WEAK = auto()              # Some absorption, not conclusive
    MODERATE = auto()          # Clear absorption activity
    STRONG = auto()            # Multiple confirmation signals


class ControlShiftPhase(Enum):
    """
    Observable control shift states.

    Absorption = sellers failing
    Control shift = buyers actually taking over

    Without control shift, absorption may just be a pause before continuation.
    """
    NONE = auto()              # No control shift detected
    EMERGING = auto()          # Early signs of buyer activity
    CONFIRMED = auto()         # Clear buyer takeover
    STRONG = auto()            # Multiple confirmation signals


class TrendDirection(Enum):
    """
    Observable trend direction.

    Determined from price structure, NOT prediction.
    """
    STRONG_DOWN = auto()       # Clear downtrend (lower highs, lower lows)
    WEAK_DOWN = auto()         # Mild downward drift
    NEUTRAL = auto()           # No clear direction
    WEAK_UP = auto()           # Mild upward drift
    STRONG_UP = auto()         # Clear uptrend (higher highs, higher lows)


@dataclass(frozen=True)
class RegimeContext:
    """
    Current market regime metrics for adaptive thresholds.

    All metrics are rolling observations, not predictions.
    """
    # Volatility context
    rolling_range_bps: float      # Price range over lookback (basis points)
    atr_proxy: float              # Average true range proxy (rolling high-low)

    # Liquidity context
    median_trade_size: float      # Median trade size in window
    total_volume_30s: float       # Total volume over 30s
    trade_rate_per_sec: float     # Trades per second

    # Spread context
    avg_spread_bps: float         # Average spread in basis points
    spread_volatility: float      # Spread standard deviation

    # Adaptive window
    adaptive_window_sec: float    # Computed adaptive window length


@dataclass(frozen=True)
class TrendRegimeContext:
    """
    Trend regime context for filtering exhaustion signals.

    CRITICAL: Absorption during strong trend may be reload, not reversal.

    All metrics are rolling observations over longer timeframes.
    """
    # Price structure (60-second window)
    direction: TrendDirection
    price_change_pct: float           # Net price change over window
    higher_highs_count: int           # Count of higher highs
    lower_lows_count: int             # Count of lower lows

    # Directional strength
    trend_strength: float             # 0.0 to 1.0, how clear is the trend
    consecutive_direction: int        # Consecutive moves in same direction

    # Liquidation context
    long_liq_volume: float            # Long liquidations in window
    short_liq_volume: float           # Short liquidations in window
    liq_imbalance: float              # (long - short) / total, negative = shorts squeezed

    # Cumulative delta direction
    delta_60s: float                  # Cumulative delta over 60s
    delta_direction_aligned: bool     # Delta matches price direction


@dataclass(frozen=True)
class WhaleFlowMetrics:
    """
    Whale vs retail flow distinction.

    1 whale exhausting = meaningful
    100 retail prints = noise

    Large trades weighted higher in exhaustion calculations.
    """
    # Trade size distribution
    whale_threshold: float            # Size above which = whale (90th percentile)
    whale_volume: float               # Total whale volume in window
    retail_volume: float              # Total retail volume in window
    whale_ratio: float                # whale / total volume

    # Whale-weighted metrics
    whale_weighted_delta: float       # Delta weighted by trade size
    whale_buy_volume: float           # Whale buy volume
    whale_sell_volume: float          # Whale sell volume
    whale_exhaustion_ratio: float     # Whale sells absorbed / whale sell volume

    # Is exhaustion driven by whales or retail?
    whale_driven: bool                # True if whale volume > 50% of exhaustion

    # H5-A: Whale reload detection
    whale_reload_detected: bool = False  # True if whale sell volume increased after absorption


@dataclass(frozen=True)
class PersistenceMetrics:
    """
    Persistence tracking for depth and control shift.

    Filters out:
    - Flash bids (spoofing)
    - Brief buyer activity (fakeouts)
    """
    # Depth persistence
    bid_survival_rate: float          # % of bid levels surviving > N seconds
    avg_bid_lifetime_sec: float       # Average time bids persist
    flash_bid_ratio: float            # % of bids that disappeared quickly

    # Control shift persistence
    control_shift_windows: int        # How many consecutive windows show control shift
    control_shift_consistency: float  # % of recent windows with buyer activity
    buyer_persistence_score: float    # 0.0 to 1.0, how persistent is buyer activity

    # Combined persistence
    depth_persistent: bool            # Bids are real, not flash
    control_persistent: bool          # Buyer activity persists


@dataclass(frozen=True)
class AbsorptionObservation:
    """
    Factual observation of absorption activity.

    All metrics are derived from observable market data.
    Cannot imply: reversal, safety, exhaustion complete.
    """
    coin: str
    phase: AbsorptionPhase
    timestamp: float

    # Regime context used for this observation
    regime: RegimeContext

    # Core absorption metrics (NORMALIZED)
    absorption_ratio: float           # Consumed / movement (volatility-adjusted)
    absorption_ratio_percentile: float  # Percentile vs recent history

    # Replenishment (NORMALIZED)
    bid_replenishment_rate: float     # Size added per second
    replenishment_vs_consumed: float  # Replenishment / consumed ratio

    # Aggressor failure metrics (NORMALIZED)
    sell_volume_window: float         # Total sell volume in adaptive window
    sell_volume_percentile: float     # Percentile vs recent history
    downside_range_bps: float         # Price range on downside
    range_vs_volatility: float        # Range / rolling volatility (< 1 = absorbed)
    aggressor_failure: bool           # High volume + range < volatility

    # Delta divergence (NORMALIZED)
    cumulative_delta: float           # Buy volume - sell volume
    delta_slope: float                # Rate of delta change
    delta_slope_normalized: float     # Slope / total volume
    delta_diverging: bool             # Delta flattening while sells continue

    # Confirmation count
    signals_confirmed: int            # How many signals are active (0-4)


@dataclass(frozen=True)
class ControlShiftObservation:
    """
    Factual observation of control shift activity.

    Absorption = sellers failing to move price
    Control shift = buyers actually taking over

    Both required for meaningful exhaustion confirmation.
    """
    coin: str
    phase: ControlShiftPhase
    timestamp: float

    # Bid aggression (buyers crossing spread)
    buy_aggression_ratio: float       # Buy-initiated / total volume
    buy_aggression_delta: float       # Change in aggression from first to second half
    bid_lifting: bool                 # Buyers actively lifting asks

    # Buy volume acceleration
    buy_volume_first_half: float      # Buy volume in first half of window
    buy_volume_second_half: float     # Buy volume in second half
    buy_acceleration: float           # (second - first) / first, positive = accelerating
    volume_accelerating: bool         # Buy volume increasing

    # Price floor establishment (higher lows)
    low_price_first_half: float       # Lowest price in first half
    low_price_second_half: float      # Lowest price in second half
    higher_low_formed: bool           # Second half low > first half low
    floor_strength: float             # How much higher (normalized)

    # Imbalance flip
    imbalance_first_half: float       # (buy - sell) / total in first half
    imbalance_second_half: float      # (buy - sell) / total in second half
    imbalance_delta: float            # Change in imbalance
    imbalance_flipped: bool           # Went from sell-heavy to buy-heavy

    # Confirmation count
    control_signals_confirmed: int    # How many signals active (0-4)


@dataclass(frozen=True)
class CombinedExhaustionObservation:
    """
    Combined absorption + control shift observation WITH HARDENINGS.

    This is the complete exhaustion confirmation:
    - Absorption confirmed: sellers tried and failed
    - Control shift confirmed: buyers took over
    - Trend context validated: not fading a strong move
    - Whale flow validated: meaningful participants exhausting
    - Persistence validated: not flash bids or brief activity

    Without ALL validations passing, exhaustion is UNSAFE to act on.
    """
    coin: str
    timestamp: float

    # Component observations
    absorption: AbsorptionObservation
    control_shift: ControlShiftObservation

    # Hardening contexts
    trend_context: TrendRegimeContext
    whale_metrics: WhaleFlowMetrics
    persistence: PersistenceMetrics

    # Base confirmation (before hardenings)
    absorption_confirmed: bool        # Absorption signals >= threshold
    control_shift_confirmed: bool     # Control signals >= threshold
    base_exhaustion_confirmed: bool   # Both absorption + control shift

    # Hardening validations
    trend_safe: bool                  # Not fading strong directional move
    whale_validated: bool             # Exhaustion driven by meaningful flow
    persistence_validated: bool       # Depth + control shift persist

    # FINAL confirmation (all checks pass)
    full_exhaustion_confirmed: bool   # Base + all hardenings pass

    # Total signal strength (includes hardening quality)
    total_signals: int                # Sum of all signals (0-8)
    hardening_score: float            # 0.0 to 1.0, hardening quality
    confirmation_strength: float      # 0.0 to 1.0 overall confidence


class AbsorptionConfirmationTracker:
    """
    Tracks absorption confirmation signals from observable market data.

    REGIME-ADAPTIVE: All thresholds adjust to current market context.

    Requires:
    - Trade stream (price, volume, side)
    - Orderbook snapshots (bid/ask sizes, spread)

    Produces:
    - AbsorptionObservation with regime-normalized metrics
    """

    # RELATIVE thresholds (not absolute)
    # Absorption ratio must be in top X percentile of recent observations
    ABSORPTION_RATIO_PERCENTILE_THRESHOLD = 70  # Top 30%

    # Volume must be in top X percentile to evaluate aggressor failure
    VOLUME_PERCENTILE_THRESHOLD = 60  # Above median

    # Range must be less than X% of rolling volatility for "failure"
    RANGE_VS_VOLATILITY_THRESHOLD = 0.5  # Range < 50% of normal volatility

    # Delta slope must be within X of zero (normalized) for "divergence"
    DELTA_SLOPE_NORMALIZED_THRESHOLD = 0.15  # Flat = within 15% of volume

    # Replenishment must exceed X% of consumed to count
    REPLENISHMENT_RATIO_THRESHOLD = 0.3  # Refill 30% of what was eaten

    # Adaptive window bounds
    MIN_WINDOW_SEC = 2.0
    MAX_WINDOW_SEC = 15.0
    TARGET_TRADES_PER_WINDOW = 50  # Aim for ~50 trades per window

    # Control shift thresholds
    # Bid aggression: buyers must be > X% of volume to count as lifting
    BID_LIFTING_THRESHOLD = 0.55  # >55% buy-initiated = lifting

    # Aggression delta: must increase by X to count as emerging control
    AGGRESSION_DELTA_THRESHOLD = 0.1  # 10% increase in buy aggression

    # Buy acceleration: must increase by X% to count as accelerating
    BUY_ACCELERATION_THRESHOLD = 0.2  # 20% increase in buy volume

    # Higher low: must be X% higher (normalized by volatility)
    HIGHER_LOW_THRESHOLD = 0.1  # 10% of expected range

    # Imbalance flip: must swing by X to count as flipped
    IMBALANCE_FLIP_THRESHOLD = 0.15  # 15% swing from sell to buy heavy

    # Combined confirmation
    MIN_ABSORPTION_SIGNALS = 2  # Minimum absorption signals
    MIN_CONTROL_SIGNALS = 2     # Minimum control shift signals

    # =========================================================================
    # HARDENING THRESHOLDS
    # =========================================================================

    # Trend regime thresholds
    TREND_WINDOW_SEC = 60.0           # Window for trend detection
    STRONG_TREND_THRESHOLD = 0.7      # Trend strength above this = strong
    TREND_PRICE_CHANGE_THRESHOLD = 0.005  # 0.5% move = directional

    # Whale flow thresholds
    WHALE_PERCENTILE = 90             # Top 10% of trades = whale
    MIN_WHALE_RATIO = 0.3             # Need 30% whale volume for validation
    WHALE_EXHAUSTION_THRESHOLD = 0.5  # 50% of whale sells absorbed

    # Persistence thresholds
    BID_SURVIVAL_THRESHOLD = 0.6      # 60% of bids must survive > N seconds
    MIN_BID_LIFETIME_SEC = 5.0        # H4-A: Extended from 3.0 to 5.0 seconds
    FLASH_BID_MAX_RATIO = 0.3         # Max 30% flash bids allowed
    CONTROL_PERSISTENCE_WINDOWS = 3   # Need 3 consecutive windows
    CONTROL_CONSISTENCY_THRESHOLD = 0.6  # 60% of windows must show control

    def __init__(self):
        # Per-coin trade buffers: deque of (timestamp, price, volume, is_sell)
        self._trades: Dict[str, deque] = {}

        # Per-coin orderbook state: (timestamp, bid_size, ask_size, mid_price, spread)
        self._orderbook_history: Dict[str, deque] = {}

        # Per-coin absorption events: deque of (timestamp, consumed, price_move)
        self._absorption_events: Dict[str, deque] = {}

        # Per-coin refill events: deque of (timestamp, added_size)
        self._refill_events: Dict[str, deque] = {}

        # Per-coin absorption ratio history for percentile calculation
        self._absorption_ratio_history: Dict[str, deque] = {}

        # Per-coin volume history for percentile calculation
        self._volume_history: Dict[str, deque] = {}

        # Max buffer size (120 seconds at high frequency)
        self._max_events = 2000

        # Percentile history size
        self._percentile_history_size = 100

        # =====================================================================
        # HARDENING STATE
        # =====================================================================

        # Per-coin liquidation tracking: (timestamp, side, volume)
        # side: 'long' or 'short'
        self._liquidations: Dict[str, deque] = {}

        # Per-coin bid level tracking for persistence: {price_level: first_seen_ts}
        self._bid_levels: Dict[str, Dict[float, float]] = {}

        # Per-coin bid level history: (timestamp, level, appeared/disappeared)
        self._bid_level_events: Dict[str, deque] = {}

        # Per-coin control shift history: deque of (timestamp, confirmed)
        self._control_shift_history: Dict[str, deque] = {}

        # Per-coin trade size history for whale threshold calculation
        self._trade_sizes: Dict[str, deque] = {}

        # H5-A: Per-coin whale sell volume history for reload detection
        # Tracks (timestamp, whale_sell_volume) to detect increases
        self._whale_sell_history: Dict[str, deque] = {}

    def record_trade(
        self,
        coin: str,
        price: float,
        volume: float,
        is_sell: bool,
        timestamp: Optional[float] = None
    ) -> None:
        """Record a trade event."""
        ts = timestamp or time.time()

        if coin not in self._trades:
            self._trades[coin] = deque(maxlen=self._max_events)

        self._trades[coin].append((ts, price, volume, is_sell))

        # Track trade sizes for whale threshold calculation
        if coin not in self._trade_sizes:
            self._trade_sizes[coin] = deque(maxlen=self._max_events)
        self._trade_sizes[coin].append(volume)

    def record_liquidation(
        self,
        coin: str,
        side: str,
        volume: float,
        timestamp: Optional[float] = None
    ) -> None:
        """
        Record a liquidation event.

        Args:
            coin: Asset symbol
            side: 'long' or 'short'
            volume: Liquidation volume
            timestamp: Event time
        """
        ts = timestamp or time.time()

        if coin not in self._liquidations:
            self._liquidations[coin] = deque(maxlen=self._max_events)

        self._liquidations[coin].append((ts, side, volume))

    def record_bid_level(
        self,
        coin: str,
        price_level: float,
        appeared: bool,
        timestamp: Optional[float] = None
    ) -> None:
        """
        Record bid level appearance/disappearance for persistence tracking.

        Args:
            coin: Asset symbol
            price_level: Bid price level
            appeared: True if level appeared, False if disappeared
            timestamp: Event time
        """
        ts = timestamp or time.time()

        if coin not in self._bid_levels:
            self._bid_levels[coin] = {}
        if coin not in self._bid_level_events:
            self._bid_level_events[coin] = deque(maxlen=self._max_events)

        if appeared:
            # Track when this level first appeared
            if price_level not in self._bid_levels[coin]:
                self._bid_levels[coin][price_level] = ts
        else:
            # Level disappeared - record lifetime
            if price_level in self._bid_levels[coin]:
                appeared_at = self._bid_levels[coin].pop(price_level)
                lifetime = ts - appeared_at
                self._bid_level_events[coin].append((ts, price_level, lifetime))
            else:
                # Level disappeared without us tracking its appearance
                self._bid_level_events[coin].append((ts, price_level, 0.0))

    def record_orderbook(
        self,
        coin: str,
        bid_size: float,
        ask_size: float,
        mid_price: float,
        spread: float = 0.0,
        timestamp: Optional[float] = None
    ) -> None:
        """
        Record orderbook snapshot.

        Args:
            coin: Asset symbol
            bid_size: Total bid depth
            ask_size: Total ask depth
            mid_price: Current mid price
            spread: Bid-ask spread (absolute, not bps)
            timestamp: Snapshot time
        """
        ts = timestamp or time.time()

        if coin not in self._orderbook_history:
            self._orderbook_history[coin] = deque(maxlen=self._max_events)

        self._orderbook_history[coin].append((ts, bid_size, ask_size, mid_price, spread))

    def record_absorption(
        self,
        coin: str,
        consumed_size: float,
        price_movement_pct: float,
        timestamp: Optional[float] = None
    ) -> None:
        """Record an absorption event."""
        ts = timestamp or time.time()

        if coin not in self._absorption_events:
            self._absorption_events[coin] = deque(maxlen=self._max_events)

        self._absorption_events[coin].append((ts, consumed_size, price_movement_pct))

    def record_refill(
        self,
        coin: str,
        added_size: float,
        timestamp: Optional[float] = None
    ) -> None:
        """Record a refill event."""
        ts = timestamp or time.time()

        if coin not in self._refill_events:
            self._refill_events[coin] = deque(maxlen=self._max_events)

        self._refill_events[coin].append((ts, added_size))

    def _compute_regime_context(
        self,
        coin: str,
        current_time: float
    ) -> RegimeContext:
        """
        Compute current regime context for adaptive thresholds.

        Uses 30-second lookback for regime estimation.
        """
        trades = self._trades.get(coin, [])
        orderbook = self._orderbook_history.get(coin, [])

        # 30-second lookback for regime
        regime_cutoff = current_time - 30.0

        recent_trades = [
            (ts, price, vol, is_sell)
            for ts, price, vol, is_sell in trades
            if ts > regime_cutoff
        ]

        recent_orderbook = [
            (ts, bid, ask, mid, spread)
            for ts, bid, ask, mid, spread in orderbook
            if ts > regime_cutoff
        ]

        # Volatility: rolling price range
        if recent_trades:
            prices = [price for _, price, _, _ in recent_trades]
            high = max(prices)
            low = min(prices)
            mid = (high + low) / 2 if high != low else high
            rolling_range_bps = ((high - low) / mid * 10000) if mid > 0 else 0.0

            # ATR proxy: average of per-second high-low
            atr_proxy = rolling_range_bps / 30.0  # Normalize to per-second
        else:
            rolling_range_bps = 0.0
            atr_proxy = 0.0

        # Liquidity: trade sizes and volume
        if recent_trades:
            volumes = sorted([vol for _, _, vol, _ in recent_trades])
            median_idx = len(volumes) // 2
            median_trade_size = volumes[median_idx] if volumes else 0.0
            total_volume_30s = sum(volumes)
            trade_rate = len(recent_trades) / 30.0
        else:
            median_trade_size = 0.0
            total_volume_30s = 0.0
            trade_rate = 0.0

        # Spread context
        if recent_orderbook:
            spreads_bps = []
            for ts, bid, ask, mid, spread in recent_orderbook:
                if mid > 0 and spread > 0:
                    spread_bps = (spread / mid) * 10000
                    spreads_bps.append(spread_bps)

            if spreads_bps:
                avg_spread_bps = sum(spreads_bps) / len(spreads_bps)
                mean = avg_spread_bps
                variance = sum((s - mean) ** 2 for s in spreads_bps) / len(spreads_bps)
                spread_volatility = math.sqrt(variance)
            else:
                avg_spread_bps = 0.0
                spread_volatility = 0.0
        else:
            avg_spread_bps = 0.0
            spread_volatility = 0.0

        # Adaptive window: aim for TARGET_TRADES_PER_WINDOW trades
        if trade_rate > 0:
            ideal_window = self.TARGET_TRADES_PER_WINDOW / trade_rate
            adaptive_window = max(
                self.MIN_WINDOW_SEC,
                min(self.MAX_WINDOW_SEC, ideal_window)
            )
        else:
            adaptive_window = self.MAX_WINDOW_SEC  # Default to max if no trades

        return RegimeContext(
            rolling_range_bps=rolling_range_bps,
            atr_proxy=atr_proxy,
            median_trade_size=median_trade_size,
            total_volume_30s=total_volume_30s,
            trade_rate_per_sec=trade_rate,
            avg_spread_bps=avg_spread_bps,
            spread_volatility=spread_volatility,
            adaptive_window_sec=adaptive_window
        )

    def _compute_percentile(self, value: float, history: deque) -> float:
        """Compute percentile of value within history."""
        if not history or len(history) < 5:
            return 50.0  # Default to median if insufficient history

        sorted_history = sorted(history)
        count_below = sum(1 for h in sorted_history if h < value)
        return (count_below / len(sorted_history)) * 100

    def _compute_absorption_ratio(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float]:
        """
        Compute VOLATILITY-ADJUSTED absorption ratio.

        Returns:
            (absorption_ratio, percentile_vs_history)
        """
        events = self._absorption_events.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window

        recent = [(ts, consumed, move) for ts, consumed, move in events if ts > cutoff]

        if not recent:
            return 0.0, 0.0

        total_consumed = sum(consumed for _, consumed, _ in recent)
        total_movement = sum(move for _, _, move in recent)

        # SPREAD-ADJUSTED: Add half spread to movement (noise floor)
        # Movement less than spread is noise, not real price change
        spread_adjustment = regime.avg_spread_bps / 2 / 10000  # Convert to pct
        adjusted_movement = total_movement + spread_adjustment * len(recent)

        # VOLATILITY-NORMALIZED: Divide by rolling volatility
        # This makes ratio comparable across regimes
        if regime.rolling_range_bps > 0:
            volatility_factor = regime.rolling_range_bps / 100  # Normalize
        else:
            volatility_factor = 1.0

        if adjusted_movement < 0.001:
            # No movement = high absorption (but cap it)
            ratio = min(total_consumed / volatility_factor, 100.0) if total_consumed > 0 else 0.0
        else:
            ratio = (total_consumed / adjusted_movement) / volatility_factor

        # Track history for percentile
        if coin not in self._absorption_ratio_history:
            self._absorption_ratio_history[coin] = deque(maxlen=self._percentile_history_size)
        self._absorption_ratio_history[coin].append(ratio)

        percentile = self._compute_percentile(ratio, self._absorption_ratio_history[coin])

        return ratio, percentile

    def _compute_replenishment_metrics(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float]:
        """
        Compute replenishment rate and ratio vs consumed.

        Returns:
            (replenishment_rate, replenishment_vs_consumed_ratio)
        """
        refill_events = self._refill_events.get(coin, [])
        absorption_events = self._absorption_events.get(coin, [])

        window = regime.adaptive_window_sec
        cutoff = current_time - window

        recent_refills = [(ts, added) for ts, added in refill_events if ts > cutoff]
        recent_absorption = [(ts, consumed, _) for ts, consumed, _ in absorption_events if ts > cutoff]

        total_added = sum(added for _, added in recent_refills)
        total_consumed = sum(consumed for _, consumed, _ in recent_absorption)

        rate = total_added / window if window > 0 else 0.0

        if total_consumed > 0:
            ratio = total_added / total_consumed
        else:
            ratio = 1.0 if total_added > 0 else 0.0

        return rate, ratio

    def _compute_aggressor_metrics(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float, float, float]:
        """
        Compute REGIME-RELATIVE aggressor failure metrics.

        Returns:
            (sell_volume, sell_volume_percentile, downside_range_bps, range_vs_volatility)
        """
        trades = self._trades.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0, 0.0, 0.0

        # Sum sell volume
        sell_volume = sum(vol for _, _, vol, is_sell in recent if is_sell)

        # Track volume history for percentile
        if coin not in self._volume_history:
            self._volume_history[coin] = deque(maxlen=self._percentile_history_size)
        self._volume_history[coin].append(sell_volume)

        volume_percentile = self._compute_percentile(sell_volume, self._volume_history[coin])

        # Compute price range on sell trades only
        sell_prices = [price for _, price, _, is_sell in recent if is_sell]

        if len(sell_prices) < 2:
            return sell_volume, volume_percentile, 0.0, 0.0

        high = max(sell_prices)
        low = min(sell_prices)
        mid = (high + low) / 2

        if mid == 0:
            return sell_volume, volume_percentile, 0.0, 0.0

        range_bps = ((high - low) / mid) * 10000

        # VOLATILITY-RELATIVE: Compare range to rolling volatility
        if regime.rolling_range_bps > 0:
            # Scale by window ratio (our window vs 30s regime window)
            window_scale = window / 30.0
            expected_range = regime.rolling_range_bps * window_scale
            range_vs_volatility = range_bps / expected_range
        else:
            range_vs_volatility = 1.0  # No volatility data = neutral

        return sell_volume, volume_percentile, range_bps, range_vs_volatility

    def _compute_delta_metrics(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float, float]:
        """
        Compute VOLUME-NORMALIZED delta metrics.

        Returns:
            (cumulative_delta, delta_slope, delta_slope_normalized)
        """
        trades = self._trades.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0, 0.0

        # Cumulative delta
        buy_volume = sum(vol for _, _, vol, is_sell in recent if not is_sell)
        sell_volume = sum(vol for _, _, vol, is_sell in recent if is_sell)
        delta = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume

        # Delta slope (compare first half to second half)
        mid_time = cutoff + window / 2

        first_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts <= mid_time]
        second_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts > mid_time]

        if not first_half or not second_half:
            return delta, 0.0, 0.0

        delta_1 = sum(vol if not is_sell else -vol for _, vol, is_sell in first_half)
        delta_2 = sum(vol if not is_sell else -vol for _, vol, is_sell in second_half)

        slope = delta_2 - delta_1

        # VOLUME-NORMALIZED slope
        if total_volume > 0:
            slope_normalized = slope / (total_volume / 2)
        else:
            slope_normalized = 0.0

        return delta, slope, slope_normalized

    # =========================================================================
    # CONTROL SHIFT DETECTION
    # =========================================================================

    def _compute_bid_aggression(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float, bool]:
        """
        Compute bid aggression metrics (buyers crossing spread).

        Returns:
            (buy_aggression_ratio, aggression_delta, bid_lifting)
        """
        trades = self._trades.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window
        mid_time = cutoff + window / 2

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0, False

        # Split into halves
        first_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts <= mid_time]
        second_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts > mid_time]

        # Calculate buy aggression ratio (buy-initiated / total)
        total_volume = sum(vol for _, _, vol, _ in recent)
        buy_volume = sum(vol for _, _, vol, is_sell in recent if not is_sell)

        if total_volume > 0:
            buy_aggression_ratio = buy_volume / total_volume
        else:
            buy_aggression_ratio = 0.5  # Neutral

        # Calculate aggression delta (change from first to second half)
        first_total = sum(vol for _, vol, _ in first_half) if first_half else 0
        first_buy = sum(vol for _, vol, is_sell in first_half if not is_sell) if first_half else 0
        second_total = sum(vol for _, vol, _ in second_half) if second_half else 0
        second_buy = sum(vol for _, vol, is_sell in second_half if not is_sell) if second_half else 0

        first_ratio = first_buy / first_total if first_total > 0 else 0.5
        second_ratio = second_buy / second_total if second_total > 0 else 0.5

        aggression_delta = second_ratio - first_ratio

        # Bid lifting = buyers are > threshold of volume
        bid_lifting = buy_aggression_ratio > self.BID_LIFTING_THRESHOLD

        return buy_aggression_ratio, aggression_delta, bid_lifting

    def _compute_buy_acceleration(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float, float, bool]:
        """
        Compute buy volume acceleration.

        Returns:
            (buy_volume_first, buy_volume_second, acceleration, volume_accelerating)
        """
        trades = self._trades.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window
        mid_time = cutoff + window / 2

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0, 0.0, False

        # Split into halves
        first_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts <= mid_time]
        second_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts > mid_time]

        # Buy volume in each half
        buy_first = sum(vol for _, vol, is_sell in first_half if not is_sell)
        buy_second = sum(vol for _, vol, is_sell in second_half if not is_sell)

        # Acceleration = (second - first) / first
        if buy_first > 0:
            acceleration = (buy_second - buy_first) / buy_first
        else:
            acceleration = 1.0 if buy_second > 0 else 0.0

        # Volume accelerating = acceleration > threshold
        volume_accelerating = acceleration > self.BUY_ACCELERATION_THRESHOLD

        return buy_first, buy_second, acceleration, volume_accelerating

    def _compute_price_floor(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float, bool, float]:
        """
        Compute price floor establishment (higher lows).

        Returns:
            (low_first, low_second, higher_low_formed, floor_strength)
        """
        trades = self._trades.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window
        mid_time = cutoff + window / 2

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0, False, 0.0

        # Split into halves
        first_half_prices = [price for ts, price, _, _ in recent if ts <= mid_time]
        second_half_prices = [price for ts, price, _, _ in recent if ts > mid_time]

        if not first_half_prices or not second_half_prices:
            return 0.0, 0.0, False, 0.0

        low_first = min(first_half_prices)
        low_second = min(second_half_prices)

        # Higher low formed if second low > first low
        higher_low_formed = low_second > low_first

        # Floor strength = how much higher, normalized by expected range
        if regime.rolling_range_bps > 0 and low_first > 0:
            # Convert price difference to bps
            price_diff_bps = ((low_second - low_first) / low_first) * 10000
            # Normalize by expected volatility
            window_scale = window / 30.0
            expected_range = regime.rolling_range_bps * window_scale
            floor_strength = price_diff_bps / expected_range if expected_range > 0 else 0.0
        else:
            floor_strength = 0.0

        return low_first, low_second, higher_low_formed, floor_strength

    def _compute_imbalance_flip(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> Tuple[float, float, float, bool]:
        """
        Compute order flow imbalance flip.

        Imbalance = (buy - sell) / total
        Flip = went from sell-heavy (negative) to buy-heavy (positive)

        Returns:
            (imbalance_first, imbalance_second, imbalance_delta, imbalance_flipped)
        """
        trades = self._trades.get(coin, [])
        window = regime.adaptive_window_sec
        cutoff = current_time - window
        mid_time = cutoff + window / 2

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0, 0.0, False

        # Split into halves
        first_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts <= mid_time]
        second_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts > mid_time]

        def compute_imbalance(trades_list):
            if not trades_list:
                return 0.0
            buy = sum(vol for _, vol, is_sell in trades_list if not is_sell)
            sell = sum(vol for _, vol, is_sell in trades_list if is_sell)
            total = buy + sell
            if total > 0:
                return (buy - sell) / total
            return 0.0

        imbalance_first = compute_imbalance(first_half)
        imbalance_second = compute_imbalance(second_half)
        imbalance_delta = imbalance_second - imbalance_first

        # Imbalance flipped = was sell-heavy, now buy-heavy (or significant positive swing)
        imbalance_flipped = (
            imbalance_first < 0 and imbalance_second > 0
        ) or imbalance_delta > self.IMBALANCE_FLIP_THRESHOLD

        return imbalance_first, imbalance_second, imbalance_delta, imbalance_flipped

    # =========================================================================
    # HARDENING: TREND REGIME FILTER
    # =========================================================================

    def _compute_trend_regime_context(
        self,
        coin: str,
        current_time: float
    ) -> TrendRegimeContext:
        """
        Compute trend regime context for filtering exhaustion signals.

        CRITICAL: Absorption during strong trend may be reload, not reversal.

        Uses 60-second window to detect directional movement.
        """
        trades = self._trades.get(coin, [])
        liquidations = self._liquidations.get(coin, [])

        # 60-second lookback for trend
        trend_cutoff = current_time - self.TREND_WINDOW_SEC

        recent_trades = [
            (ts, price, vol, is_sell)
            for ts, price, vol, is_sell in trades
            if ts > trend_cutoff
        ]

        recent_liqs = [
            (ts, side, vol)
            for ts, side, vol in liquidations
            if ts > trend_cutoff
        ]

        if len(recent_trades) < 10:
            # Not enough data for trend detection
            return TrendRegimeContext(
                direction=TrendDirection.NEUTRAL,
                price_change_pct=0.0,
                higher_highs_count=0,
                lower_lows_count=0,
                trend_strength=0.0,
                consecutive_direction=0,
                long_liq_volume=0.0,
                short_liq_volume=0.0,
                liq_imbalance=0.0,
                delta_60s=0.0,
                delta_direction_aligned=False
            )

        # Price structure analysis
        prices = [price for _, price, _, _ in recent_trades]
        first_price = prices[0]
        last_price = prices[-1]
        price_change_pct = (last_price - first_price) / first_price if first_price > 0 else 0.0

        # Count higher highs and lower lows (using 10-trade segments)
        segment_size = max(len(prices) // 6, 2)
        segments = [prices[i:i + segment_size] for i in range(0, len(prices), segment_size)]

        higher_highs = 0
        lower_lows = 0
        consecutive = 0
        last_direction = 0

        for i in range(1, len(segments)):
            prev_high = max(segments[i - 1])
            curr_high = max(segments[i])
            prev_low = min(segments[i - 1])
            curr_low = min(segments[i])

            if curr_high > prev_high:
                higher_highs += 1
                if last_direction >= 0:
                    consecutive += 1
                else:
                    consecutive = 1
                last_direction = 1

            if curr_low < prev_low:
                lower_lows += 1
                if last_direction <= 0:
                    consecutive += 1
                else:
                    consecutive = 1
                last_direction = -1

        # Trend strength: how clear is the direction?
        total_signals = higher_highs + lower_lows
        if total_signals > 0:
            trend_strength = abs(higher_highs - lower_lows) / total_signals
        else:
            trend_strength = 0.0

        # Determine direction
        if abs(price_change_pct) < self.TREND_PRICE_CHANGE_THRESHOLD:
            direction = TrendDirection.NEUTRAL
        elif price_change_pct > 0:
            if trend_strength >= self.STRONG_TREND_THRESHOLD:
                direction = TrendDirection.STRONG_UP
            else:
                direction = TrendDirection.WEAK_UP
        else:
            if trend_strength >= self.STRONG_TREND_THRESHOLD:
                direction = TrendDirection.STRONG_DOWN
            else:
                direction = TrendDirection.WEAK_DOWN

        # Liquidation context
        long_liq = sum(vol for _, side, vol in recent_liqs if side == 'long')
        short_liq = sum(vol for _, side, vol in recent_liqs if side == 'short')
        total_liq = long_liq + short_liq
        liq_imbalance = (long_liq - short_liq) / total_liq if total_liq > 0 else 0.0

        # Cumulative delta over 60s
        buy_vol = sum(vol for _, _, vol, is_sell in recent_trades if not is_sell)
        sell_vol = sum(vol for _, _, vol, is_sell in recent_trades if is_sell)
        delta_60s = buy_vol - sell_vol

        # Is delta direction aligned with price direction?
        delta_direction_aligned = (
            (price_change_pct > 0 and delta_60s > 0) or
            (price_change_pct < 0 and delta_60s < 0)
        )

        return TrendRegimeContext(
            direction=direction,
            price_change_pct=price_change_pct,
            higher_highs_count=higher_highs,
            lower_lows_count=lower_lows,
            trend_strength=trend_strength,
            consecutive_direction=consecutive,
            long_liq_volume=long_liq,
            short_liq_volume=short_liq,
            liq_imbalance=liq_imbalance,
            delta_60s=delta_60s,
            delta_direction_aligned=delta_direction_aligned
        )

    def _is_trend_safe(self, trend: TrendRegimeContext) -> bool:
        """
        Check if current trend context is safe for exhaustion entry.

        BLOCKS entry if:
        - Strong downtrend with delta aligned (distribution, not exhaustion)
        - High trend strength with consistent direction

        ALLOWS entry if:
        - Neutral trend
        - Weak trend
        - Delta diverging from price (accumulation during selloff)
        """
        # Strong directional moves are dangerous to fade
        if trend.direction == TrendDirection.STRONG_DOWN:
            # Only safe if delta is diverging (buyers accumulating)
            if trend.delta_direction_aligned:
                return False  # Distribution phase, not safe

        if trend.direction == TrendDirection.STRONG_UP:
            # In uptrend, exhaustion detection doesn't apply
            return True

        # Weak trends or neutral = safe to look for exhaustion
        return True

    # =========================================================================
    # HARDENING: WHALE FLOW WEIGHTING
    # =========================================================================

    def _compute_whale_flow_metrics(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> WhaleFlowMetrics:
        """
        Compute whale vs retail flow distinction.

        1 whale exhausting = meaningful
        100 retail prints = noise
        """
        trades = self._trades.get(coin, [])
        trade_sizes = self._trade_sizes.get(coin, [])

        window = regime.adaptive_window_sec
        cutoff = current_time - window

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent or len(trade_sizes) < 10:
            return WhaleFlowMetrics(
                whale_threshold=0.0,
                whale_volume=0.0,
                retail_volume=0.0,
                whale_ratio=0.0,
                whale_weighted_delta=0.0,
                whale_buy_volume=0.0,
                whale_sell_volume=0.0,
                whale_exhaustion_ratio=0.0,
                whale_driven=False,
                whale_reload_detected=False
            )

        # Calculate whale threshold (90th percentile of recent trade sizes)
        sorted_sizes = sorted(trade_sizes)
        whale_idx = int(len(sorted_sizes) * self.WHALE_PERCENTILE / 100)
        whale_threshold = sorted_sizes[min(whale_idx, len(sorted_sizes) - 1)]

        # Separate whale and retail trades
        whale_trades = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in recent if vol >= whale_threshold]
        retail_trades = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in recent if vol < whale_threshold]

        whale_volume = sum(vol for _, _, vol, _ in whale_trades)
        retail_volume = sum(vol for _, _, vol, _ in retail_trades)
        total_volume = whale_volume + retail_volume

        whale_ratio = whale_volume / total_volume if total_volume > 0 else 0.0

        # Whale-weighted metrics
        whale_buy = sum(vol for _, _, vol, is_sell in whale_trades if not is_sell)
        whale_sell = sum(vol for _, _, vol, is_sell in whale_trades if is_sell)
        whale_weighted_delta = whale_buy - whale_sell

        # Whale exhaustion ratio: how much of whale selling was absorbed?
        # (Approximated by looking at price impact of whale sells)
        if whale_sell > 0:
            # Look at price movement during whale sell window
            whale_sell_times = [ts for ts, _, _, is_sell in whale_trades if is_sell]
            if whale_sell_times:
                min_whale_ts = min(whale_sell_times)
                max_whale_ts = max(whale_sell_times)

                prices_during = [price for ts, price, _, _ in recent if min_whale_ts <= ts <= max_whale_ts]
                if len(prices_during) >= 2:
                    price_drop_pct = abs(min(prices_during) - max(prices_during)) / max(prices_during)
                    # Low price drop during high whale sell = absorption
                    # Expected drop would be proportional to volume
                    expected_drop = whale_sell / total_volume if total_volume > 0 else 0.1
                    whale_exhaustion_ratio = max(0, 1 - (price_drop_pct / max(expected_drop, 0.001)))
                else:
                    whale_exhaustion_ratio = 0.0
            else:
                whale_exhaustion_ratio = 0.0
        else:
            whale_exhaustion_ratio = 0.0

        # Is exhaustion driven by whales?
        whale_driven = whale_ratio >= self.MIN_WHALE_RATIO

        # H5-A: Whale reload detection
        # Compare current whale sell volume to previous observation
        # If whale sells increased after initial absorption, it's a reload trap
        whale_reload_detected = False
        if coin not in self._whale_sell_history:
            self._whale_sell_history[coin] = deque(maxlen=10)

        # Check if whale sell volume increased vs recent observations
        recent_whale_sells = list(self._whale_sell_history[coin])
        if len(recent_whale_sells) >= 2 and whale_sell > 0:
            # Get the minimum recent whale sell (representing post-absorption low)
            min_recent_sell = min(ws for _, ws in recent_whale_sells[-5:])
            # Reload = current whale sell > 1.5x the minimum (significant increase)
            if min_recent_sell > 0 and whale_sell > min_recent_sell * 1.5:
                whale_reload_detected = True

        # Record current whale sell for future comparison
        self._whale_sell_history[coin].append((current_time, whale_sell))

        return WhaleFlowMetrics(
            whale_threshold=whale_threshold,
            whale_volume=whale_volume,
            retail_volume=retail_volume,
            whale_ratio=whale_ratio,
            whale_weighted_delta=whale_weighted_delta,
            whale_buy_volume=whale_buy,
            whale_sell_volume=whale_sell,
            whale_exhaustion_ratio=whale_exhaustion_ratio,
            whale_driven=whale_driven,
            whale_reload_detected=whale_reload_detected
        )

    def _is_whale_validated(self, whale: WhaleFlowMetrics) -> bool:
        """
        Check if exhaustion is driven by meaningful (whale) flow.

        VALIDATES if:
        - Sufficient whale participation (>30% of volume)
        - Whale sells are being absorbed (>50% absorption ratio)
        - No whale reload detected (H5-A)

        REJECTS if:
        - Exhaustion is retail-driven (whales may still be selling)
        - H5-A: Whale reload detected (whale sell volume increased)
        """
        # Need meaningful whale participation
        if not whale.whale_driven:
            return False

        # Whale sells should be absorbed
        if whale.whale_exhaustion_ratio < self.WHALE_EXHAUSTION_THRESHOLD:
            return False

        # H5-A: Reject if whale reload detected
        if whale.whale_reload_detected:
            return False

        return True

    # =========================================================================
    # HARDENING: PERSISTENCE TRACKING
    # =========================================================================

    def _compute_persistence_metrics(
        self,
        coin: str,
        current_time: float,
        regime: RegimeContext
    ) -> PersistenceMetrics:
        """
        Compute persistence metrics for depth and control shift.

        Filters out:
        - Flash bids (spoofing)
        - Brief buyer activity (fakeouts)
        """
        bid_events = self._bid_level_events.get(coin, [])
        control_history = self._control_shift_history.get(coin, [])

        window = regime.adaptive_window_sec
        cutoff = current_time - window
        persistence_cutoff = current_time - (window * 3)  # Look at 3 windows

        # Bid persistence analysis
        recent_bid_events = [(ts, level, lifetime) for ts, level, lifetime in bid_events if ts > cutoff]

        if recent_bid_events:
            total_bids = len(recent_bid_events)
            surviving_bids = sum(1 for _, _, lifetime in recent_bid_events if lifetime >= self.MIN_BID_LIFETIME_SEC)
            flash_bids = sum(1 for _, _, lifetime in recent_bid_events if lifetime < self.MIN_BID_LIFETIME_SEC)

            bid_survival_rate = surviving_bids / total_bids if total_bids > 0 else 0.0
            avg_lifetime = sum(lifetime for _, _, lifetime in recent_bid_events) / total_bids if total_bids > 0 else 0.0
            flash_ratio = flash_bids / total_bids if total_bids > 0 else 0.0
        else:
            bid_survival_rate = 1.0  # No data = assume persistent
            avg_lifetime = self.MIN_BID_LIFETIME_SEC
            flash_ratio = 0.0

        # Control shift persistence analysis
        recent_control = [(ts, confirmed) for ts, confirmed in control_history if ts > persistence_cutoff]

        if recent_control:
            total_windows = len(recent_control)
            confirmed_windows = sum(1 for _, confirmed in recent_control if confirmed)

            # Count consecutive confirmed windows at the end
            consecutive = 0
            for _, confirmed in reversed(recent_control):
                if confirmed:
                    consecutive += 1
                else:
                    break

            control_consistency = confirmed_windows / total_windows if total_windows > 0 else 0.0
        else:
            consecutive = 0
            control_consistency = 0.0

        # Buyer persistence score
        buyer_persistence = min(consecutive / self.CONTROL_PERSISTENCE_WINDOWS, 1.0)

        # Depth persistent = survival rate high, flash ratio low
        depth_persistent = (
            bid_survival_rate >= self.BID_SURVIVAL_THRESHOLD and
            flash_ratio <= self.FLASH_BID_MAX_RATIO
        )

        # Control persistent = enough consecutive windows or consistency
        control_persistent = (
            consecutive >= self.CONTROL_PERSISTENCE_WINDOWS or
            control_consistency >= self.CONTROL_CONSISTENCY_THRESHOLD
        )

        return PersistenceMetrics(
            bid_survival_rate=bid_survival_rate,
            avg_bid_lifetime_sec=avg_lifetime,
            flash_bid_ratio=flash_ratio,
            control_shift_windows=consecutive,
            control_shift_consistency=control_consistency,
            buyer_persistence_score=buyer_persistence,
            depth_persistent=depth_persistent,
            control_persistent=control_persistent
        )

    def _is_persistence_validated(self, persistence: PersistenceMetrics) -> bool:
        """
        Check if depth and control shift are persistent (not flash/fakeout).

        VALIDATES if:
        - Bids are persistent (not flash/spoof)
        - Control shift persists over multiple windows

        REJECTS if:
        - High flash bid ratio (spoofing likely)
        - Control shift is brief (fakeout likely)
        """
        # For now, require at least one of the persistence checks
        # (We may not have bid level data in all cases)
        return persistence.depth_persistent or persistence.control_persistent

    def _record_control_shift_result(
        self,
        coin: str,
        confirmed: bool,
        timestamp: float
    ) -> None:
        """Record control shift observation for persistence tracking."""
        if coin not in self._control_shift_history:
            self._control_shift_history[coin] = deque(maxlen=20)  # Keep last 20 observations

        self._control_shift_history[coin].append((timestamp, confirmed))

    def get_control_shift_observation(
        self,
        coin: str,
        timestamp: Optional[float] = None
    ) -> ControlShiftObservation:
        """
        Compute current control shift observation.

        Control shift = buyers taking over from sellers.
        Absorption without control shift = pause, not reversal.
        """
        ts = timestamp or time.time()

        # Get regime context
        regime = self._compute_regime_context(coin, ts)

        # Compute all control shift metrics
        buy_aggression, aggression_delta, bid_lifting = self._compute_bid_aggression(coin, ts, regime)
        buy_first, buy_second, acceleration, volume_accelerating = self._compute_buy_acceleration(coin, ts, regime)
        low_first, low_second, higher_low, floor_strength = self._compute_price_floor(coin, ts, regime)
        imb_first, imb_second, imb_delta, imb_flipped = self._compute_imbalance_flip(coin, ts, regime)

        # Count confirmed signals
        signals = sum([
            bid_lifting,
            volume_accelerating,
            higher_low,
            imb_flipped
        ])

        # Determine phase
        if signals >= 3:
            phase = ControlShiftPhase.STRONG
        elif signals >= 2:
            phase = ControlShiftPhase.CONFIRMED
        elif signals >= 1:
            phase = ControlShiftPhase.EMERGING
        else:
            phase = ControlShiftPhase.NONE

        return ControlShiftObservation(
            coin=coin,
            phase=phase,
            timestamp=ts,
            buy_aggression_ratio=buy_aggression,
            buy_aggression_delta=aggression_delta,
            bid_lifting=bid_lifting,
            buy_volume_first_half=buy_first,
            buy_volume_second_half=buy_second,
            buy_acceleration=acceleration,
            volume_accelerating=volume_accelerating,
            low_price_first_half=low_first,
            low_price_second_half=low_second,
            higher_low_formed=higher_low,
            floor_strength=floor_strength,
            imbalance_first_half=imb_first,
            imbalance_second_half=imb_second,
            imbalance_delta=imb_delta,
            imbalance_flipped=imb_flipped,
            control_signals_confirmed=signals
        )

    def get_combined_observation(
        self,
        coin: str,
        timestamp: Optional[float] = None
    ) -> CombinedExhaustionObservation:
        """
        Get combined absorption + control shift observation WITH HARDENINGS.

        This is the COMPLETE exhaustion confirmation:
        - Absorption confirmed: sellers tried and failed
        - Control shift confirmed: buyers took over
        - Trend safe: not fading a strong directional move
        - Whale validated: exhaustion driven by meaningful flow
        - Persistence validated: not flash bids or brief activity

        Without ALL validations, exhaustion is UNSAFE to act on.
        """
        ts = timestamp or time.time()

        # Get both base observations
        absorption = self.get_observation(coin, ts)
        control_shift = self.get_control_shift_observation(coin, ts)

        # Record control shift result for persistence tracking
        control_confirmed = control_shift.control_signals_confirmed >= self.MIN_CONTROL_SIGNALS
        self._record_control_shift_result(coin, control_confirmed, ts)

        # Compute hardening contexts
        trend_context = self._compute_trend_regime_context(coin, ts)
        whale_metrics = self._compute_whale_flow_metrics(coin, ts, absorption.regime)
        persistence = self._compute_persistence_metrics(coin, ts, absorption.regime)

        # Base confirmation (before hardenings)
        absorption_confirmed = absorption.signals_confirmed >= self.MIN_ABSORPTION_SIGNALS
        base_exhaustion = absorption_confirmed and control_confirmed

        # Hardening validations
        trend_safe = self._is_trend_safe(trend_context)
        whale_validated = self._is_whale_validated(whale_metrics)
        persistence_validated = self._is_persistence_validated(persistence)

        # FINAL confirmation: base + all hardenings must pass
        full_exhaustion = (
            base_exhaustion and
            trend_safe and
            whale_validated and
            persistence_validated
        )

        # Total signal strength
        total_signals = absorption.signals_confirmed + control_shift.control_signals_confirmed

        # Hardening score: how many hardenings pass (0.0 to 1.0)
        hardening_checks = [trend_safe, whale_validated, persistence_validated]
        hardening_score = sum(hardening_checks) / len(hardening_checks)

        # Confirmation strength: base signals + hardening quality
        base_strength = min(total_signals / 6.0, 1.0)  # 6 signals = 100%
        confirmation_strength = base_strength * (0.5 + 0.5 * hardening_score)

        return CombinedExhaustionObservation(
            coin=coin,
            timestamp=ts,
            absorption=absorption,
            control_shift=control_shift,
            trend_context=trend_context,
            whale_metrics=whale_metrics,
            persistence=persistence,
            absorption_confirmed=absorption_confirmed,
            control_shift_confirmed=control_confirmed,
            base_exhaustion_confirmed=base_exhaustion,
            trend_safe=trend_safe,
            whale_validated=whale_validated,
            persistence_validated=persistence_validated,
            full_exhaustion_confirmed=full_exhaustion,
            total_signals=total_signals,
            hardening_score=hardening_score,
            confirmation_strength=confirmation_strength
        )

    def is_full_exhaustion_confirmed(
        self,
        coin: str,
        timestamp: Optional[float] = None,
        require_hardenings: bool = True
    ) -> bool:
        """
        Check if FULL exhaustion is confirmed WITH HARDENINGS.

        This is the key function: returns True only when:
        1. Sellers tried and failed (absorption)
        2. Buyers took over (control shift)
        3. Trend context is safe (not fading strong move)
        4. Whale flow is validated (meaningful participants)
        5. Persistence is validated (not flash/fakeout)

        Args:
            coin: Asset symbol
            timestamp: Observation time
            require_hardenings: If True, all hardenings must pass.
                                If False, only base confirmation required.

        Absorption without control shift = PAUSE, not REVERSAL.
        Base confirmation without hardenings = RISKY.
        """
        combined = self.get_combined_observation(coin, timestamp)

        if require_hardenings:
            return combined.full_exhaustion_confirmed
        else:
            return combined.base_exhaustion_confirmed

    def get_observation(
        self,
        coin: str,
        timestamp: Optional[float] = None
    ) -> AbsorptionObservation:
        """
        Compute current absorption observation with REGIME-ADAPTIVE thresholds.

        All metrics are normalized to current market context.
        """
        ts = timestamp or time.time()

        # Compute regime context first
        regime = self._compute_regime_context(coin, ts)

        # Compute all metrics with regime context
        absorption_ratio, absorption_percentile = self._compute_absorption_ratio(coin, ts, regime)
        replenishment_rate, replenishment_ratio = self._compute_replenishment_metrics(coin, ts, regime)
        sell_volume, volume_percentile, range_bps, range_vs_vol = self._compute_aggressor_metrics(coin, ts, regime)
        delta, delta_slope, delta_slope_norm = self._compute_delta_metrics(coin, ts, regime)

        # Evaluate signals with RELATIVE thresholds

        # Signal 1: Absorption ratio in top percentile
        absorption_signal = absorption_percentile >= self.ABSORPTION_RATIO_PERCENTILE_THRESHOLD

        # Signal 2: Replenishment exceeds threshold ratio of consumed
        replenishment_signal = replenishment_ratio >= self.REPLENISHMENT_RATIO_THRESHOLD

        # Signal 3: Aggressor failure = high volume percentile + range < volatility
        aggressor_failure = (
            volume_percentile >= self.VOLUME_PERCENTILE_THRESHOLD and
            range_vs_vol < self.RANGE_VS_VOLATILITY_THRESHOLD
        )

        # Signal 4: Delta divergence = selling continues but delta slope is flat
        delta_diverging = (
            volume_percentile >= self.VOLUME_PERCENTILE_THRESHOLD and
            abs(delta_slope_norm) < self.DELTA_SLOPE_NORMALIZED_THRESHOLD
        )

        # Count confirmed signals
        signals = sum([
            absorption_signal,
            replenishment_signal,
            aggressor_failure,
            delta_diverging
        ])

        # Determine phase
        if signals >= 3:
            phase = AbsorptionPhase.STRONG
        elif signals >= 2:
            phase = AbsorptionPhase.MODERATE
        elif signals >= 1:
            phase = AbsorptionPhase.WEAK
        else:
            phase = AbsorptionPhase.NONE

        return AbsorptionObservation(
            coin=coin,
            phase=phase,
            timestamp=ts,
            regime=regime,
            absorption_ratio=absorption_ratio,
            absorption_ratio_percentile=absorption_percentile,
            bid_replenishment_rate=replenishment_rate,
            replenishment_vs_consumed=replenishment_ratio,
            sell_volume_window=sell_volume,
            sell_volume_percentile=volume_percentile,
            downside_range_bps=range_bps,
            range_vs_volatility=range_vs_vol,
            aggressor_failure=aggressor_failure,
            cumulative_delta=delta,
            delta_slope=delta_slope,
            delta_slope_normalized=delta_slope_norm,
            delta_diverging=delta_diverging,
            signals_confirmed=signals
        )

    def is_absorption_confirmed(
        self,
        coin: str,
        min_signals: int = 2,
        timestamp: Optional[float] = None
    ) -> bool:
        """
        Check if absorption is confirmed (enough signals active).

        Uses regime-adaptive thresholds.
        """
        obs = self.get_observation(coin, timestamp)
        return obs.signals_confirmed >= min_signals

    def get_all_observations(self) -> Dict[str, AbsorptionObservation]:
        """Get current observations for all tracked coins."""
        ts = time.time()
        return {
            coin: self.get_observation(coin, ts)
            for coin in set(self._trades.keys()) | set(self._orderbook_history.keys())
        }

    def get_regime_context(
        self,
        coin: str,
        timestamp: Optional[float] = None
    ) -> RegimeContext:
        """Get current regime context for a coin (for debugging/display)."""
        ts = timestamp or time.time()
        return self._compute_regime_context(coin, ts)

    def get_trend_regime_context(
        self,
        coin: str,
        timestamp: Optional[float] = None
    ) -> TrendRegimeContext:
        """
        Get trend regime context for a coin.

        PUBLIC INTERFACE for trend-aware entry filtering.

        This context is used by:
        - Entry Quality Scorer: Kill-switch for entries against strong trends
        - Cascade Sniper: Mode selection (reversal vs momentum)
        - Policy Adapter: Pass trend context through pipeline

        The context reports WHAT IS, not WHAT WILL BE:
        - Current trend direction (observed from price structure)
        - Trend strength (how clear is the direction)
        - Liquidation imbalance (which side is being liquidated)
        - Delta alignment (is order flow matching price direction)

        Cannot imply: trend will continue, reversal imminent, safe to fade
        """
        ts = timestamp or time.time()
        return self._compute_trend_regime_context(coin, ts)
