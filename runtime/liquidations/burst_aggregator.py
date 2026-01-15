"""
Liquidation Burst Aggregator

Tracks recent liquidation activity in sliding windows for cascade detection.
Used by the Cascade Sniper strategy to detect when liquidations are firing.

Constitutional compliance:
- Only factual observations (volumes, counts, timestamps)
- No predictions or interpretations
- Pure aggregation
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional, Deque, Tuple


@dataclass
class LiquidationEvent:
    """Single liquidation event from Binance forceOrder stream."""
    timestamp: float
    symbol: str
    side: str  # "BUY" or "SELL" - the liquidated side
    price: float
    quantity: float
    value: float  # quantity * price


@dataclass(frozen=True)
class LiquidationBurst:
    """
    Aggregated liquidation activity in a time window.

    Structural observation - no interpretation.
    """
    symbol: str
    total_volume: float          # Total liquidation volume in window
    long_liquidations: float     # Volume of long liquidations (SELL orders)
    short_liquidations: float    # Volume of short liquidations (BUY orders)
    liquidation_count: int       # Number of liquidation events
    window_start: float          # Window start timestamp
    window_end: float            # Window end timestamp


class LiquidationBurstAggregator:
    """
    Aggregates liquidation events into bursts for cascade detection.

    Maintains sliding windows of liquidation activity per symbol.
    """

    def __init__(self, window_seconds: float = 10.0, max_events: int = 1000):
        """
        Initialize aggregator.

        Args:
            window_seconds: Sliding window duration
            max_events: Maximum events to store per symbol
        """
        self._window_sec = window_seconds
        self._max_events = max_events

        # Event buffer: symbol -> deque of LiquidationEvent
        self._events: Dict[str, Deque[LiquidationEvent]] = {}

        # Cache of last computed burst
        self._burst_cache: Dict[str, Tuple[float, LiquidationBurst]] = {}

    def add_event(
        self,
        timestamp: float,
        symbol: str,
        side: str,
        price: float,
        quantity: float
    ):
        """
        Add a liquidation event.

        Args:
            timestamp: Event timestamp
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: Liquidated side - "SELL" means long was liquidated, "BUY" means short
            price: Liquidation price
            quantity: Liquidation quantity
        """
        # Normalize symbol
        symbol = symbol.upper()

        # Create event
        event = LiquidationEvent(
            timestamp=timestamp,
            symbol=symbol,
            side=side.upper(),
            price=price,
            quantity=quantity,
            value=price * quantity
        )

        # Get or create buffer for symbol
        if symbol not in self._events:
            self._events[symbol] = deque(maxlen=self._max_events)

        self._events[symbol].append(event)

        # Invalidate cache
        self._burst_cache.pop(symbol, None)

    def get_burst(self, symbol: str, current_time: Optional[float] = None) -> Optional[LiquidationBurst]:
        """
        Get liquidation burst for a symbol.

        Args:
            symbol: Trading symbol
            current_time: Current timestamp (defaults to now)

        Returns:
            LiquidationBurst if events exist, None otherwise
        """
        symbol = symbol.upper()
        current_time = current_time or time.time()

        # Check cache (valid for 0.5 seconds)
        if symbol in self._burst_cache:
            cache_time, cached_burst = self._burst_cache[symbol]
            if current_time - cache_time < 0.5:
                return cached_burst

        # Get events for symbol
        events = self._events.get(symbol)
        if not events:
            return None

        # Filter to window
        window_start = current_time - self._window_sec
        window_events = [e for e in events if e.timestamp >= window_start]

        if not window_events:
            return None

        # Aggregate
        total_volume = 0.0
        long_liquidations = 0.0  # SELL orders = long liquidations
        short_liquidations = 0.0  # BUY orders = short liquidations

        for event in window_events:
            total_volume += event.value
            if event.side == "SELL":
                long_liquidations += event.value
            else:  # BUY
                short_liquidations += event.value

        burst = LiquidationBurst(
            symbol=symbol,
            total_volume=total_volume,
            long_liquidations=long_liquidations,
            short_liquidations=short_liquidations,
            liquidation_count=len(window_events),
            window_start=window_start,
            window_end=current_time
        )

        # Cache result
        self._burst_cache[symbol] = (current_time, burst)

        return burst

    def get_all_bursts(self, current_time: Optional[float] = None) -> Dict[str, LiquidationBurst]:
        """
        Get liquidation bursts for all symbols with activity.

        Returns:
            Dict of symbol -> LiquidationBurst
        """
        current_time = current_time or time.time()
        bursts = {}

        for symbol in self._events.keys():
            burst = self.get_burst(symbol, current_time)
            if burst and burst.liquidation_count > 0:
                bursts[symbol] = burst

        return bursts

    def prune_old_events(self, max_age_seconds: float = 300.0):
        """
        Remove events older than max_age.

        Args:
            max_age_seconds: Maximum event age to keep
        """
        cutoff = time.time() - max_age_seconds

        for symbol, events in self._events.items():
            # Deque doesn't support efficient pruning, so filter in place
            while events and events[0].timestamp < cutoff:
                events.popleft()

    def get_summary(self) -> Dict:
        """Get aggregator summary."""
        return {
            'symbols_tracked': len(self._events),
            'total_events': sum(len(e) for e in self._events.values()),
            'events_per_symbol': {
                symbol: len(events)
                for symbol, events in self._events.items()
            }
        }
