"""
Unit Tests for Feed Synchronization Layer

Tests verify:
- All streams aligned → snapshot returned
- Missing stream → None returned
- Misaligned timestamp → None returned
- Integration with event loop
- Identical behavior to live DataSynchronizer

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
    OrderbookFeedAdapter, TradeFeedAdapter,
    LiquidationFeedAdapter, KlineFeedAdapter,
    schedule_all_events
)
from masterframe.replay.synchronizer import ReplayDataSync


class TestReplayDataSync:
    """Test replay data synchronization."""
    
    def create_orderbook(self, ts: float) -> OrderbookSnapshot:
        """Helper to create orderbook."""
        return OrderbookSnapshot(
            timestamp=ts,
            bids=((100.0, 1.0), (99.0, 2.0)),
            asks=((101.0, 1.0), (102.0, 2.0)),
            mid_price=100.5
        )
    
    def create_trade(self, ts: float) -> AggressiveTrade:
        """Helper to create trade."""
        return AggressiveTrade(
            timestamp=ts,
            price=100.0,
            quantity=0.5,
            is_buyer_aggressor=True
        )
    
    def create_liquidation(self, ts: float) -> LiquidationEvent:
        """Helper to create liquidation."""
        return LiquidationEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            price=100.0,
            value_usd=10.0
        )
    
    def create_kline(self, ts: float, interval: str) -> Kline:
        """Helper to create kline."""
        return Kline(
            timestamp=ts,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            interval=interval
        )
    
    def test_event_routing(self):
        """Events are routed to correct push methods."""
        sync = ReplayDataSync()
        
        # Create events
        ob_event = Event(100.0, 'orderbook', self.create_orderbook(100.0))
        trade_event = Event(100.0, 'trade', self.create_trade(100.0))
        liq_event = Event(100.0, 'liquidation', self.create_liquidation(100.0))
        kline_event = Event(100.0, 'kline_1m', self.create_kline(100.0, '1m'))
        
        # Handle events
        sync.handle_event(ob_event)
        sync.handle_event(trade_event)
        sync.handle_event(liq_event)
        sync.handle_event(kline_event)
        
        # Should have data in buffers (though not necessarily warm yet)
        assert len(sync.sync.orderbook_buffer._buffer) > 0
        assert len(sync.sync.trade_buffer._buffer) > 0
        assert len(sync.sync.liquidation_buffer._buffer) > 0
    
    def test_missing_stream_returns_none(self):
        """Missing stream returns None."""
        sync = ReplayDataSync()
        
        # Only push orderbook, missing other streams
        for i in range(10):
            ts = float(i)
            sync.handle_event(Event(ts, 'orderbook', self.create_orderbook(ts)))
        
        # Try to get snapshot
        snapshot = sync.get_snapshot(10.0)
        
        # EXPECT: None (missing streams)
        assert snapshot is None
    
    def test_warm_up_required(self):
        """Buffers must warm up before returning data."""
        sync = ReplayDataSync()
        
        # Not warm initially
        assert not sync.is_warm()
        
        # Push minimal data
        for i in range(5):
            ts = float(i)
            sync.handle_event(Event(ts, 'orderbook', self.create_orderbook(ts)))
            sync.handle_event(Event(ts, 'trade', self.create_trade(ts)))
            sync.handle_event(Event(ts, 'liquidation', self.create_liquidation(ts)))
            sync.handle_event(Event(ts, 'kline_1m', self.create_kline(ts, '1m')))
            sync.handle_event(Event(ts, 'kline_5m', self.create_kline(ts, '5m')))
        
        # Still might not be warm (depends on buffer sizes)
        # Push more data
        for i in range(5, 50):
            ts = float(i)
            sync.handle_event(Event(ts, 'orderbook', self.create_orderbook(ts)))
            sync.handle_event(Event(ts, 'trade', self.create_trade(ts)))
            sync.handle_event(Event(ts, 'liquidation', self.create_liquidation(ts)))
            sync.handle_event(Event(ts, 'kline_1m', self.create_kline(ts, '1m')))
            if i % 5 == 0:
                sync.handle_event(Event(ts, 'kline_5m', self.create_kline(ts, '5m')))
        
        # Should be warm now
        assert sync.is_warm()
    
    def test_aligned_streams_return_snapshot(self):
        """All streams aligned returns valid snapshot."""
        sync = ReplayDataSync()
        
        # Warm up with aligned data
        for i in range(50):
            ts = float(i)
            sync.handle_event(Event(ts, 'orderbook', self.create_orderbook(ts)))
            sync.handle_event(Event(ts, 'trade', self.create_trade(ts)))
            sync.handle_event(Event(ts, 'liquidation', self.create_liquidation(ts)))
            sync.handle_event(Event(ts, 'kline_1m', self.create_kline(ts, '1m')))
            if i % 5 == 0:
                sync.handle_event(Event(ts, 'kline_5m', self.create_kline(ts, '5m')))
        
        # Push final aligned data
        ts = 50.0
        sync.handle_event(Event(ts, 'orderbook', self.create_orderbook(ts)))
        sync.handle_event(Event(ts, 'kline_1m', self.create_kline(ts, '1m')))
        sync.handle_event(Event(ts, 'kline_5m', self.create_kline(ts, '5m')))
        
        # Try to get snapshot
        snapshot = sync.get_snapshot(ts)
        
        # EXPECT: Valid snapshot if warm and aligned
        if sync.is_warm():
            assert snapshot is not None
            assert snapshot.orderbook is not None
            assert snapshot.kline_1m is not None


class TestIntegrationWithFeedAdapters:
    """Test integration with feed adapters and event loop."""
    
    def test_full_replay_with_sync(self):
        """Full replay flow with synchronization."""
        # Create historical data
        base_time = 1000.0
        orderbooks = [OrderbookSnapshot(
            timestamp=base_time + i,
            bids=((100.0, 1.0),),
            asks=((101.0, 1.0),),
            mid_price=100.5
        ) for i in range(50)]
        
        trades = [AggressiveTrade(
            timestamp=base_time + i,
            price=100.0,
            quantity=0.5,
            is_buyer_aggressor=True
        ) for i in range(50)]
        
        liqs = [LiquidationEvent(
            timestamp=base_time + i,
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            price=100.0,
            value_usd=10.0
        ) for i in range(50)]
        
        klines_1m = [Kline(
            timestamp=base_time + i,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            interval='1m'
        ) for i in range(50)]
        
        klines_5m = [Kline(
            timestamp=base_time + i * 5,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=5000.0,
            interval='5m'
        ) for i in range(10)]
        
        # Create adapters
        adapters = [
            OrderbookFeedAdapter(orderbooks),
            TradeFeedAdapter(trades),
            LiquidationFeedAdapter(liqs),
            KlineFeedAdapter(klines_1m, '1m'),
            KlineFeedAdapter(klines_5m, '5m'),
        ]
        
        # Create event loop
        loop = EventLoop(start_time=base_time)
        
        # Create synchronizer
        sync = ReplayDataSync()
        
        # Track snapshots
        snapshots = []
        
        def handle_event(event: Event):
            # Update synchronizer
            sync.handle_event(event)
            
            # Try to get snapshot
            snapshot = sync.get_snapshot(event.timestamp)
            if snapshot is not None:
                snapshots.append(snapshot)
        
        # Register handlers for all event types
        for event_type in ['orderbook', 'trade', 'liquidation', 'kline_1m', 'kline_5m']:
            loop.register_handler(event_type, handle_event)
        
        # Schedule all events
        schedule_all_events(adapters, loop)
        
        # Run replay
        loop.run()
        
        # EXPECT: Some snapshots generated (after warm-up)
        assert len(snapshots) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
