"""
Unit Tests for System Execution Wrapper

Tests verify:
- Execute with valid snapshot
- State capture correctness
- Deterministic execution
- Integration with sync layer

RULE: All tests are deterministic.
"""

import pytest
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.data_ingestion import (
    OrderbookSnapshot, AggressiveTrade, 
    LiquidationEvent, Kline, SynchronizedData
)
from masterframe.replay.system_wrapper import ReplaySystemWrapper


class TestReplaySystemWrapper:
    """Test system execution wrapper."""
    
    def create_snapshot(self, ts: float) -> SynchronizedData:
        """Helper to create synchronized snapshot."""
        return SynchronizedData(
            timestamp=ts,
            orderbook=OrderbookSnapshot(
                timestamp=ts,
                bids=((100.0, 1.0),),
                asks=((101.0, 1.0),),
                mid_price=100.5
            ),
            trades=[AggressiveTrade(ts, 100.0, 0.5, True)],
            liquidations=[LiquidationEvent(ts, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)],
            kline_1m=Kline(ts, 100.0, 101.0, 99.0, 100.5, 1000.0, '1m'),
            kline_5m=Kline(ts, 100.0, 101.0, 99.0, 100.5, 5000.0, '5m'),
        )
    
    def test_execute_with_snapshot(self):
        """Execute system with valid snapshot."""
        wrapper = ReplaySystemWrapper()
        
        snapshot = self.create_snapshot(100.0)
        result = wrapper.execute(snapshot, 100.0)
        
        # EXPECT: Result dict with state
        assert result['timestamp'] == 100.0
        assert 'regime' in result
        assert 'active_strategy' in result
        assert 'in_cooldown' in result
        assert 'slbrs_state' in result
        assert 'effcs_state' in result
        assert result['execution_count'] == 1
    
    def test_execution_count_increments(self):
        """Execution count increments with each call."""
        wrapper = ReplaySystemWrapper()
        
        for i in range(5):
            snapshot = self.create_snapshot(float(i))
            result = wrapper.execute(snapshot, float(i))
            assert result['execution_count'] == i + 1
        
        assert wrapper.get_execution_count() == 5
    
    def test_state_capture(self):
        """System state is correctly captured."""
        wrapper = ReplaySystemWrapper()
        
        snapshot = self.create_snapshot(100.0)
        result = wrapper.execute(snapshot, 100.0)
        
        # State should be captured
        assert isinstance(result['regime'], str)
        assert isinstance(result['in_cooldown'], bool)
        assert isinstance(result['slbrs_state'], str)
        assert isinstance(result['effcs_state'], str)
    
    def test_deterministic_execution(self):
        """Same inputs produce same results."""
        wrapper1 = ReplaySystemWrapper()
        wrapper2 = ReplaySystemWrapper()
        
        # Same snapshot
        snapshot1 = self.create_snapshot(100.0)
        snapshot2 = self.create_snapshot(100.0)
        
        result1 = wrapper1.execute(snapshot1, 100.0)
        result2 = wrapper2.execute(snapshot2, 100.0)
        
        # EXPECT: Same state (excluding execution_count which increments)
        assert result1['regime'] == result2['regime']
        assert result1['slbrs_state'] == result2['slbrs_state']
        assert result1['effcs_state'] == result2['effcs_state']
    
    def test_get_controller_access(self):
        """Can access underlying controller."""
        wrapper = ReplaySystemWrapper()
        
        controller = wrapper.get_controller()
        assert controller is not None
        assert controller == wrapper.controller


class TestIntegrationWithReplay:
    """Test integration with full replay stack."""
    
    def test_full_stack_execution(self):
        """Full replay stack: events → sync → wrapper."""
        from masterframe.replay import Event, EventLoop
        from masterframe.replay.feed_adapters import (
            OrderbookFeedAdapter, TradeFeedAdapter,
            LiquidationFeedAdapter, KlineFeedAdapter,
            schedule_all_events
        )
        from masterframe.replay.synchronizer import ReplayDataSync
        
        # Create historical data
        base_time = 1000.0
        orderbooks = [OrderbookSnapshot(
            timestamp=base_time + i,
            bids=((100.0, 1.0),),
            asks=((101.0, 1.0),),
            mid_price=100.5
        ) for i in range(30)]
        
        trades = [AggressiveTrade(
            timestamp=base_time + i,
            price=100.0,
            quantity=0.5,
            is_buyer_aggressor=True
        ) for i in range(30)]
        
        liqs = [LiquidationEvent(
            timestamp=base_time + i,
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            price=100.0,
            value_usd=10.0
        ) for i in range(30)]
        
        klines_1m = [Kline(
            timestamp=base_time + i,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            interval='1m'
        ) for i in range(30)]
        
        klines_5m = [Kline(
            timestamp=base_time + i * 5,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=5000.0,
            interval='5m'
        ) for i in range(6)]
        
        # Create adapters
        adapters = [
            OrderbookFeedAdapter(orderbooks),
            TradeFeedAdapter(trades),
            LiquidationFeedAdapter(liqs),
            KlineFeedAdapter(klines_1m, '1m'),
            KlineFeedAdapter(klines_5m, '5m'),
        ]
        
        # Create components
        loop = EventLoop(start_time=base_time)
        sync = ReplayDataSync()
        wrapper = ReplaySystemWrapper()
        
        # Track executions
        executions = []
        
        def handle_event(event: Event):
            # Update synchronizer
            sync.handle_event(event)
            
            # Get snapshot
            snapshot = sync.get_snapshot(event.timestamp)
            
            if snapshot is not None:
                # Execute system
                result = wrapper.execute(snapshot, event.timestamp)
                executions.append(result)
        
        # Register handlers
        for event_type in ['orderbook', 'trade', 'liquidation', 'kline_1m', 'kline_5m']:
            loop.register_handler(event_type, handle_event)
        
        # Schedule and run
        schedule_all_events(adapters, loop)
        loop.run()
        
        # EXPECT: Some executions (after warm-up)
        assert len(executions) > 0
        
        # All executions have required fields
        for result in executions:
            assert 'timestamp' in result
            assert 'regime' in result
            assert 'execution_count' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
