"""
M4 Primitive: Absorption Confirmation (Regime-Adaptive)

Detects PRESENCE of absorption, not ABSENCE of activity.

Absorption = sellers trying AND failing to move price.

Observable signals:
1. Bid absorption - large sells eaten without price drop
2. Orderbook replenishment - bid depth rebuilds after sweeps
3. Aggressor failure - high sell volume, shrinking downside range
4. Delta divergence - cumulative delta flattening while sells continue

REGIME-ADAPTIVE DESIGN:
- All thresholds are RELATIVE to current market context
- Volatility-normalized absorption ratio
- Liquidity-relative volume thresholds (percentile, not absolute)
- Spread-adjusted movement calculation
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
