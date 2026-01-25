"""
M4 Primitive: Absorption Confirmation

Detects PRESENCE of absorption, not ABSENCE of activity.

Absorption = sellers trying AND failing to move price.

Observable signals:
1. Bid absorption - large sells eaten without price drop
2. Orderbook replenishment - bid depth rebuilds after sweeps
3. Aggressor failure - high sell volume, shrinking downside range
4. Delta divergence - cumulative delta flattening while sells continue

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
class AbsorptionObservation:
    """
    Factual observation of absorption activity.

    All metrics are derived from observable market data.
    Cannot imply: reversal, safety, exhaustion complete.
    """
    coin: str
    phase: AbsorptionPhase
    timestamp: float

    # Core absorption metrics
    absorption_ratio: float       # Consumed size / price movement (higher = more absorption)
    bid_replenishment_rate: float # Bid size added per second

    # Aggressor failure metrics
    sell_volume_5s: float         # Total sell volume in 5s window
    downside_range_5s: float      # Price range on downside (bps)
    aggressor_failure: bool       # High volume + shrinking range

    # Delta divergence
    cumulative_delta_5s: float    # Buy volume - sell volume
    delta_slope: float            # Rate of delta change
    delta_diverging: bool         # Delta flattening while sells continue

    # Confirmation count
    signals_confirmed: int        # How many signals are active (0-4)


class AbsorptionConfirmationTracker:
    """
    Tracks absorption confirmation signals from observable market data.

    Requires:
    - Trade stream (price, volume, side)
    - Orderbook snapshots (bid/ask sizes)

    Produces:
    - AbsorptionObservation with multiple confirmation signals
    """

    # Thresholds for signal detection
    MIN_ABSORPTION_RATIO = 0.5       # Minimum ratio to count as absorption
    MIN_REPLENISHMENT_RATE = 0.1     # Minimum bid rebuild rate (size/sec)
    AGGRESSOR_FAILURE_THRESHOLD = 5  # bps - max range for "failure"
    MIN_SELL_VOLUME = 1000           # Minimum sell volume to evaluate
    DELTA_DIVERGENCE_THRESHOLD = 0.3 # Delta slope threshold

    def __init__(self):
        # Per-coin trade buffers: deque of (timestamp, price, volume, is_sell)
        self._trades: Dict[str, deque] = {}

        # Per-coin orderbook state: (timestamp, bid_size, ask_size, mid_price)
        self._orderbook_history: Dict[str, deque] = {}

        # Per-coin absorption events: deque of (timestamp, consumed, price_move)
        self._absorption_events: Dict[str, deque] = {}

        # Per-coin refill events: deque of (timestamp, added_size)
        self._refill_events: Dict[str, deque] = {}

        # Max buffer size (60 seconds at high frequency)
        self._max_events = 1000

    def record_trade(
        self,
        coin: str,
        price: float,
        volume: float,
        is_sell: bool,
        timestamp: Optional[float] = None
    ) -> None:
        """
        Record a trade event.

        Args:
            coin: Asset symbol
            price: Trade price
            volume: Trade volume
            is_sell: True if taker sold (aggressor sell)
            timestamp: Event time (defaults to now)
        """
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
        timestamp: Optional[float] = None
    ) -> None:
        """
        Record orderbook snapshot.

        Args:
            coin: Asset symbol
            bid_size: Total bid depth
            ask_size: Total ask depth
            mid_price: Current mid price
            timestamp: Snapshot time (defaults to now)
        """
        ts = timestamp or time.time()

        if coin not in self._orderbook_history:
            self._orderbook_history[coin] = deque(maxlen=self._max_events)

        self._orderbook_history[coin].append((ts, bid_size, ask_size, mid_price))

    def record_absorption(
        self,
        coin: str,
        consumed_size: float,
        price_movement_pct: float,
        timestamp: Optional[float] = None
    ) -> None:
        """
        Record an absorption event (from m4_orderbook_primitives).

        Args:
            coin: Asset symbol
            consumed_size: Size consumed
            price_movement_pct: Price movement magnitude
            timestamp: Event time
        """
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
        """
        Record a refill event (from m4_orderbook_primitives).

        Args:
            coin: Asset symbol
            added_size: Size added to book
            timestamp: Event time
        """
        ts = timestamp or time.time()

        if coin not in self._refill_events:
            self._refill_events[coin] = deque(maxlen=self._max_events)

        self._refill_events[coin].append((ts, added_size))

    def get_observation(
        self,
        coin: str,
        timestamp: Optional[float] = None
    ) -> AbsorptionObservation:
        """
        Compute current absorption observation for a coin.

        Args:
            coin: Asset symbol
            timestamp: Current time (defaults to now)

        Returns:
            AbsorptionObservation with all computed metrics
        """
        ts = timestamp or time.time()

        # Compute all metrics
        absorption_ratio = self._compute_absorption_ratio(coin, ts)
        replenishment_rate = self._compute_replenishment_rate(coin, ts)
        sell_volume, downside_range = self._compute_aggressor_metrics(coin, ts)
        delta_5s, delta_slope = self._compute_delta_metrics(coin, ts)

        # Evaluate signals
        aggressor_failure = (
            sell_volume >= self.MIN_SELL_VOLUME and
            downside_range <= self.AGGRESSOR_FAILURE_THRESHOLD
        )

        delta_diverging = (
            sell_volume >= self.MIN_SELL_VOLUME and
            abs(delta_slope) < self.DELTA_DIVERGENCE_THRESHOLD
        )

        # Count confirmed signals
        signals = 0
        if absorption_ratio >= self.MIN_ABSORPTION_RATIO:
            signals += 1
        if replenishment_rate >= self.MIN_REPLENISHMENT_RATE:
            signals += 1
        if aggressor_failure:
            signals += 1
        if delta_diverging:
            signals += 1

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
            absorption_ratio=absorption_ratio,
            bid_replenishment_rate=replenishment_rate,
            sell_volume_5s=sell_volume,
            downside_range_5s=downside_range,
            aggressor_failure=aggressor_failure,
            cumulative_delta_5s=delta_5s,
            delta_slope=delta_slope,
            delta_diverging=delta_diverging,
            signals_confirmed=signals
        )

    def _compute_absorption_ratio(self, coin: str, current_time: float) -> float:
        """
        Compute absorption ratio from recent events.

        Ratio = total_consumed / total_price_movement
        Higher = more absorption (size eaten, price stable)
        """
        events = self._absorption_events.get(coin, [])
        cutoff = current_time - 5.0

        recent = [(ts, consumed, move) for ts, consumed, move in events if ts > cutoff]

        if not recent:
            return 0.0

        total_consumed = sum(consumed for _, consumed, _ in recent)
        total_movement = sum(move for _, _, move in recent)

        if total_movement < 0.001:  # Avoid division by near-zero
            # If no movement but consumption, that's high absorption
            return total_consumed if total_consumed > 0 else 0.0

        return total_consumed / total_movement

    def _compute_replenishment_rate(self, coin: str, current_time: float) -> float:
        """
        Compute bid replenishment rate (size added per second).
        """
        events = self._refill_events.get(coin, [])
        cutoff = current_time - 5.0

        recent = [(ts, added) for ts, added in events if ts > cutoff]

        if not recent:
            return 0.0

        total_added = sum(added for _, added in recent)
        return total_added / 5.0  # Rate per second

    def _compute_aggressor_metrics(
        self,
        coin: str,
        current_time: float
    ) -> Tuple[float, float]:
        """
        Compute sell volume and downside range.

        Returns:
            (sell_volume_5s, downside_range_bps)
        """
        trades = self._trades.get(coin, [])
        cutoff = current_time - 5.0

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0

        # Sum sell volume
        sell_volume = sum(vol for _, _, vol, is_sell in recent if is_sell)

        # Compute price range on sell trades only
        sell_prices = [price for _, price, _, is_sell in recent if is_sell]

        if len(sell_prices) < 2:
            return sell_volume, 0.0

        high = max(sell_prices)
        low = min(sell_prices)
        mid = (high + low) / 2

        if mid == 0:
            return sell_volume, 0.0

        range_bps = ((high - low) / mid) * 10000

        return sell_volume, range_bps

    def _compute_delta_metrics(
        self,
        coin: str,
        current_time: float
    ) -> Tuple[float, float]:
        """
        Compute cumulative delta and its slope.

        Delta = buy_volume - sell_volume
        Slope = rate of delta change

        Returns:
            (cumulative_delta_5s, delta_slope)
        """
        trades = self._trades.get(coin, [])
        cutoff = current_time - 5.0

        recent = [(ts, price, vol, is_sell) for ts, price, vol, is_sell in trades if ts > cutoff]

        if not recent:
            return 0.0, 0.0

        # Cumulative delta
        buy_volume = sum(vol for _, _, vol, is_sell in recent if not is_sell)
        sell_volume = sum(vol for _, _, vol, is_sell in recent if is_sell)
        delta = buy_volume - sell_volume

        # Delta slope (compare first half to second half)
        mid_time = cutoff + 2.5

        first_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts <= mid_time]
        second_half = [(ts, vol, is_sell) for ts, _, vol, is_sell in recent if ts > mid_time]

        if not first_half or not second_half:
            return delta, 0.0

        delta_1 = sum(vol if not is_sell else -vol for _, vol, is_sell in first_half)
        delta_2 = sum(vol if not is_sell else -vol for _, vol, is_sell in second_half)

        # Normalize by volume to get rate
        total_vol = buy_volume + sell_volume
        if total_vol == 0:
            return delta, 0.0

        slope = (delta_2 - delta_1) / (total_vol / 2)

        return delta, slope

    def is_absorption_confirmed(
        self,
        coin: str,
        min_signals: int = 2,
        timestamp: Optional[float] = None
    ) -> bool:
        """
        Check if absorption is confirmed (enough signals active).

        Args:
            coin: Asset symbol
            min_signals: Minimum signals required (default: 2)
            timestamp: Current time

        Returns:
            True if absorption confirmed, False otherwise
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
