"""
Historical Data Feed Adapters

Wraps historical data streams to behave like live feeds.

INVARIANTS:
- Events emitted in strict time order
- No lookahead (forward-only iteration)
- No buffering future events
- One event at a time

GOAL:
Make historical replay behave IDENTICALLY to live trading.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from masterframe.data_ingestion import (
    OrderbookEvent, TradeEvent,
    LiquidationEvent, CandleEvent
)
from .event_loop import Event


class BaseFeedAdapter(ABC):
    """
    Base adapter for historical data feeds.
    
    INVARIANT: Events emitted in strict time order.
    INVARIANT: No lookahead - iterator based.
    INVARIANT: Forward-only progression.
    """
    
    def __init__(self, data: List):
        """
        Initialize adapter with historical data.
        
        Args:
            data: List of data items (must have .timestamp attribute)
        """
        # Sort by timestamp (defensive - ensures time order)
        self.data = sorted(data, key=lambda x: x.timestamp)
        self._index = 0
    
    @abstractmethod
    def get_event_type(self) -> str:
        """Get event type for this feed."""
        pass
    
    def has_more(self) -> bool:
        """
        Check if more events available.
        
        Returns:
            True if more events, False otherwise
        """
        return self._index < len(self.data)
    
    def peek_next_timestamp(self) -> float:
        """
        Peek at next event timestamp without consuming.
        
        RULE: Only used for cross-feed synchronization.
        RULE: Cannot skip this event.
        
        Returns:
            Next event timestamp, or inf if no more events
        """
        if not self.has_more():
            return float('inf')
        return self.data[self._index].timestamp
    
    def emit_next(self) -> Event:
        """
        Emit next event.
        
        RULE: Forward-only progression.
        RULE: No going back.
        
        Returns:
            Next event
            
        Raises:
            StopIteration: If no more events
        """
        if not self.has_more():
            raise StopIteration("No more events in feed")
        
        item = self.data[self._index]
        self._index += 1
        
        return Event(
            timestamp=item.timestamp,
            event_type=self.get_event_type(),
            data=item
        )
    
    def reset(self) -> None:
        """Reset iterator to beginning (for testing/replay)."""
        self._index = 0
    
    def get_progress(self) -> tuple[int, int]:
        """
        Get current progress.
        
        Returns:
            (current_index, total_events)
        """
        return (self._index, len(self.data))
    
    def __repr__(self) -> str:
        current, total = self.get_progress()
        return f"{self.__class__.__name__}({current}/{total})"


class OrderbookFeedAdapter(BaseFeedAdapter):
    """
    Adapter for historical orderbook snapshots.
    
    Emits 'orderbook' events.
    """
    
    def get_event_type(self) -> str:
        return 'orderbook'


class TradeFeedAdapter(BaseFeedAdapter):
    """
    Adapter for historical aggressive trades.
    
    Emits 'trade' events.
    """
    
    def get_event_type(self) -> str:
        return 'trade'


class LiquidationFeedAdapter(BaseFeedAdapter):
    """
    Adapter for historical liquidation events.
    
    Emits 'liquidation' events.
    """
    
    def get_event_type(self) -> str:
        return 'liquidation'


class BookTickerFeedAdapter(BaseFeedAdapter):
    """
    Adapter for historical book ticker events.
    
    Emits 'bookticker' events.
    """
    
    def get_event_type(self) -> str:
        return 'bookticker'


class KlineFeedAdapter(BaseFeedAdapter):
    """
    Adapter for historical kline/candle data.
    
    Emits 'kline_{interval}' events.
    """
    
    def __init__(self, data: List[CandleEvent], interval: str):
        """
        Initialize kline adapter.
        
        Args:
            data: List of candles
            interval: Kline interval (e.g., '1m', '5m', '30m')
        """
        super().__init__(data)
        self.interval = interval
    
    def get_event_type(self) -> str:
        return f'kline_{self.interval}'


def get_next_event(adapters: List[BaseFeedAdapter]) -> Optional[Event]:
    """
    Get next event across all feeds in time order.
    
    RULE: No buffering - select and emit immediately.
    RULE: Events emitted in strict chronological order.
    
    Args:
        adapters: List of feed adapters
        
    Returns:
        Next event across all feeds, or None if all exhausted
    """
    # Filter to adapters with remaining events
    active_adapters = [a for a in adapters if a.has_more()]
    
    if not active_adapters:
        return None
    
    # Find feed with earliest next timestamp
    next_adapter = min(active_adapters, key=lambda a: a.peek_next_timestamp())
    
    # Emit from that feed
    return next_adapter.emit_next()


def schedule_all_events(adapters: List[BaseFeedAdapter], event_loop) -> int:
    """
    Schedule all events from adapters into event loop.
    
    Events are scheduled in strict chronological order across all feeds.
    
    Args:
        adapters: List of feed adapters
        event_loop: EventLoop to schedule events into
        
    Returns:
        Number of events scheduled
    """
    count = 0
    
    while True:
        event = get_next_event(adapters)
        if event is None:
            break
        
        event_loop.schedule_event(event)
        count += 1
    
    return count
