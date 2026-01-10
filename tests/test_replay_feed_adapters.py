"""
Unit Tests for Historical Data Feed Adapters

Tests verify:
- Events emitted in time order
- No lookahead (iterator validation)
- Forward-only progression
- Multi-feed synchronization
- Empty feed handling
- Timestamp sorting

RULE: All tests are deterministic.
"""

import pytest
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.data_ingestion import (
    OrderbookSnapshot, AggressiveTrade, 
    LiquidationEvent, Kline
)
from masterframe.replay import Event, EventLoop
from masterframe.replay.feed_adapters import (
    OrderbookFeedAdapter,
    TradeFeedAdapter,
    LiquidationFeedAdapter,
    KlineFeedAdapter,
    get_next_event,
    schedule_all_events,
)


class TestBaseFeedAdapter:
    """Test base feed adapter behavior."""
    
    def test_events_emitted_in_time_order(self):
        """Events are emitted in timestamp order."""
        # Create unsorted data
        trades = [
            AggressiveTrade(30.0, 100.0, 1.0, True),
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(20.0, 100.0, 1.0, True),
        ]
        
        adapter = TradeFeedAdapter(trades)
        
        # Emit all events
        timestamps = []
        while adapter.has_more():
            event = adapter.emit_next()
            timestamps.append(event.timestamp)
        
        # EXPECT: Sorted order
        assert timestamps == [10.0, 20.0, 30.0]
    
    def test_forward_only_progression(self):
        """Adapter progresses forward only, no backtracking."""
        trades = [
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(20.0, 100.0, 1.0, True),
        ]
        
        adapter = TradeFeedAdapter(trades)
        
        # Emit first
        event1 = adapter.emit_next()
        assert event1.timestamp == 10.0
        
        # Cannot go back
        event2 = adapter.emit_next()
        assert event2.timestamp == 20.0
        
        # No more events
        assert not adapter.has_more()
    
    def test_peek_does_not_consume(self):
        """Peek does not consume event."""
        trades = [AggressiveTrade(10.0, 100.0, 1.0, True)]
        adapter = TradeFeedAdapter(trades)
        
        # Peek multiple times
        assert adapter.peek_next_timestamp() == 10.0
        assert adapter.peek_next_timestamp() == 10.0
        
        # Still has event
        assert adapter.has_more()
        
        # Emit actually consumes
        event = adapter.emit_next()
        assert event.timestamp == 10.0
        assert not adapter.has_more()
    
    def test_empty_feed_handling(self):
        """Empty feed handled gracefully."""
        adapter = TradeFeedAdapter([])
        
        assert not adapter.has_more()
        assert adapter.peek_next_timestamp() == float('inf')
        
        with pytest.raises(StopIteration):
            adapter.emit_next()
    
    def test_reset(self):
        """Adapter can be reset to beginning."""
        trades = [
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(20.0, 100.0, 1.0, True),
        ]
        
        adapter = TradeFeedAdapter(trades)
        
        # Emit all
        adapter.emit_next()
        adapter.emit_next()
        assert not adapter.has_more()
        
        # Reset
        adapter.reset()
        assert adapter.has_more()
        assert adapter.peek_next_timestamp() == 10.0


class TestStreamSpecificAdapters:
    """Test stream-specific adapter implementations."""
    
    def test_orderbook_adapter(self):
        """OrderbookAdapter emits orderbook events."""
        ob = OrderbookSnapshot(
            timestamp=100.0,
            bids=((100.0, 1.0),),
            asks=((101.0, 1.0),),
            mid_price=100.5
        )
        
        adapter = OrderbookFeedAdapter([ob])
        event = adapter.emit_next()
        
        assert event.event_type == 'orderbook'
        assert event.timestamp == 100.0
        assert event.data == ob
    
    def test_trade_adapter(self):
        """TradeAdapter emits trade events."""
        trade = AggressiveTrade(100.0, 50000.0, 1.0, True)
        
        adapter = TradeFeedAdapter([trade])
        event = adapter.emit_next()
        
        assert event.event_type == 'trade'
        assert event.data == trade
    
    def test_liquidation_adapter(self):
        """LiquidationAdapter emits liquidation events."""
        liq = LiquidationEvent(
            timestamp=100.0,
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            price=50000.0,
            value_usd=5000.0
        )
        
        adapter = LiquidationFeedAdapter([liq])
        event = adapter.emit_next()
        
        assert event.event_type == 'liquidation'
        assert event.data == liq
    
    def test_kline_adapter(self):
        """KlineAdapter emits kline events with interval."""
        kline = Kline(
            timestamp=100.0,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=1000.0,
            interval='1m'
        )
        
        adapter = KlineFeedAdapter([kline], interval='1m')
        event = adapter.emit_next()
        
        assert event.event_type == 'kline_1m'
        assert event.data == kline


class TestMultiFeedSynchronization:
    """Test multi-feed synchronization."""
    
    def test_get_next_event_time_order(self):
        """get_next_event returns earliest event across feeds."""
        trades = [
            AggressiveTrade(20.0, 100.0, 1.0, True),
            AggressiveTrade(40.0, 100.0, 1.0, True),
        ]
        
        liqs = [
            LiquidationEvent(10.0, "BTCUSDT", "SELL", 0.1, 100.0, 10.0),
            LiquidationEvent(30.0, "BTCUSDT", "SELL", 0.1, 100.0, 10.0),
        ]
        
        trade_adapter = TradeFeedAdapter(trades)
        liq_adapter = LiquidationFeedAdapter(liqs)
        
        adapters = [trade_adapter, liq_adapter]
        
        # Get events in time order
        e1 = get_next_event(adapters)
        assert e1.timestamp == 10.0
        assert e1.event_type == 'liquidation'
        
        e2 = get_next_event(adapters)
        assert e2.timestamp == 20.0
        assert e2.event_type == 'trade'
        
        e3 = get_next_event(adapters)
        assert e3.timestamp == 30.0
        assert e3.event_type == 'liquidation'
        
        e4 = get_next_event(adapters)
        assert e4.timestamp == 40.0
        assert e4.event_type == 'trade'
        
        # No more events
        assert get_next_event(adapters) is None
    
    def test_schedule_all_events(self):
        """schedule_all_events schedules in time order."""
        trades = [AggressiveTrade(20.0, 100.0, 1.0, True)]
        liqs = [LiquidationEvent(10.0, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)]
        
        trade_adapter = TradeFeedAdapter(trades)
        liq_adapter = LiquidationFeedAdapter(liqs)
        
        loop = EventLoop(start_time=0.0)
        
        # Schedule all
        count = schedule_all_events([trade_adapter, liq_adapter], loop)
        
        assert count == 2
        assert loop.get_pending_events() == 2
    
    def test_all_feeds_exhausted(self):
        """get_next_event returns None when all feeds exhausted."""
        adapter1 = TradeFeedAdapter([])
        adapter2 = LiquidationFeedAdapter([])
        
        event = get_next_event([adapter1, adapter2])
        assert event is None


class TestIntegrationWithEventLoop:
    """Test integration with event loop."""
    
    def test_full_replay_flow(self):
        """Full replay flow with adapters and event loop."""
        # Create historical data
        trades = [
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(30.0, 100.0, 1.0, False),
        ]
        
        liqs = [
            LiquidationEvent(20.0, "BTCUSDT", "SELL", 0.1, 100.0, 10.0),
        ]
        
        # Create adapters
        trade_adapter = TradeFeedAdapter(trades)
        liq_adapter = LiquidationFeedAdapter(liqs)
        
        # Create event loop
        loop = EventLoop(start_time=0.0)
        
        # Track processed events
        processed = []
        
        def handle_trade(event: Event):
            processed.append(('trade', event.timestamp))
        
        def handle_liq(event: Event):
            processed.append(('liquidation', event.timestamp))
        
        loop.register_handler('trade', handle_trade)
        loop.register_handler('liquidation', handle_liq)
        
        # Schedule all events
        schedule_all_events([trade_adapter, liq_adapter], loop)
        
        # Run replay
        loop.run()
        
        # EXPECT: Events processed in time order
        assert processed == [
            ('trade', 10.0),
            ('liquidation', 20.0),
            ('trade', 30.0),
        ]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
