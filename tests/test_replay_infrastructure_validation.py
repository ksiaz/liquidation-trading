"""
Replay Infrastructure Validation Tests (V1-V5)

Tests verify replay engine infrastructure ONLY.
No strategy logic. No SLBRS. No EFFCS. No regime classifier.

CRITICAL: If ANY test fails, DO NOT proceed with simulation tests.
"""

import pytest
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.replay import Event, SimulationClock, EventLoop, ReplayController
from masterframe.replay.feed_adapters import (
    OrderbookFeedAdapter, TradeFeedAdapter,
    LiquidationFeedAdapter, get_next_event
)
from masterframe.replay.synchronizer import ReplayDataSync
from masterframe.replay.system_wrapper import ReplaySystemWrapper
from masterframe.data_ingestion import (
    OrderbookSnapshot, AggressiveTrade, LiquidationEvent, Kline
)


# ==============================================
# V1: TIME INTEGRITY VALIDATION
# ==============================================

class TestV1TimeIntegrity:
    """Prove simulation time advances deterministically."""
    
    def test_time_never_moves_backwards(self):
        """Time never moves backwards."""
        clock = SimulationClock(0.0)
        
        # Advance forward
        clock.advance_to(10.0)
        assert clock.get_time() == 10.0
        
        clock.advance_to(20.0)
        assert clock.get_time() == 20.0
        
        # Cannot go backwards
        with pytest.raises(ValueError, match="backwards"):
            clock.advance_to(15.0)
    
    def test_time_advances_only_via_events(self):
        """Time only advances when events are processed."""
        loop = EventLoop(start_time=0.0)
        
        # No events = time stays at 0
        initial_time = loop.get_current_time()
        assert initial_time == 0.0
        
        # Schedule event at t=10
        loop.schedule_event(Event(10.0, 'test', None))
        
        # Before running, time still 0
        assert loop.get_current_time() == 0.0
        
        # Register handler
        processed_times = []
        def handler(event):
            processed_times.append(loop.get_current_time())
        
        loop.register_handler('test', handler)
        
        # Run - time advances to 10
        loop.run()
        assert loop.get_current_time() == 10.0
        assert processed_times == [10.0]
    
    def test_no_implicit_time_jumps(self):
        """No skipped timestamps unless data absent (explicit gaps OK)."""
        loop = EventLoop(start_time=0.0)
        
        times_seen = []
        def handler(event):
            times_seen.append(loop.get_current_time())
        
        loop.register_handler('test', handler)
        
        # Events at t=10, t=30 (gap at 20 is explicit)
        loop.schedule_event(Event(10.0, 'test', None))
        loop.schedule_event(Event(30.0, 'test', None))
        
        loop.run()
        
        # Time: 10 → 30 (skip is explicit, not implicit)
        assert times_seen == [10.0, 30.0]
        assert loop.get_current_time() == 30.0


# ==============================================
# V2: EVENT ORDERING VALIDATION
# ==============================================

class TestV2EventOrdering:
    """Prove strict event ordering."""
    
    def test_strict_timestamp_ordering(self):
        """Events processed strictly by timestamp."""
        loop = EventLoop(start_time=0.0)
        
        processed_order = []
        def handler(event):
            processed_order.append(event.timestamp)
        
        loop.register_handler('test', handler)
        
        # Schedule out of order
        loop.schedule_event(Event(30.0, 'test', None))
        loop.schedule_event(Event(10.0, 'test', None))
        loop.schedule_event(Event(20.0, 'test', None))
        
        loop.run()
        
        # EXPECT: Processed in timestamp order
        assert processed_order == [10.0, 20.0, 30.0]
    
    def test_same_timestamp_fifo(self):
        """Equal timestamps processed in FIFO order."""
        loop = EventLoop(start_time=0.0)
        
        processed_data = []
        def handler(event):
            processed_data.append(event.data)
        
        loop.register_handler('test', handler)
        
        # Same timestamp, different data
        loop.schedule_event(Event(10.0, 'test', 'A'))
        loop.schedule_event(Event(10.0, 'test', 'B'))
        loop.schedule_event(Event(10.0, 'test', 'C'))
        
        loop.run()
        
        # EXPECT: FIFO order preserved
        assert processed_data == ['A', 'B', 'C']
    
    def test_interleaved_streams_ordered(self):
        """Interleaved streams maintain timestamp order."""
        trades = [AggressiveTrade(20.0, 100.0, 1.0, True)]
        liqs = [LiquidationEvent(10.0, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)]
        obs = [OrderbookSnapshot(30.0, ((100.0, 1.0),), ((101.0, 1.0),), 100.5)]
        
        adapters = [
            TradeFeedAdapter(trades),
            LiquidationFeedAdapter(liqs),
            OrderbookFeedAdapter(obs),
        ]
        
        # Get events in order
        events = []
        while True:
            event = get_next_event(adapters)
            if event is None:
                break
            events.append((event.timestamp, event.event_type))
        
        # EXPECT: Timestamp order maintained
        assert events == [
            (10.0, 'liquidation'),
            (20.0, 'trade'),
            (30.0, 'orderbook'),
        ]


# ==============================================
# V3: NO LOOKAHEAD GUARANTEE
# ==============================================

class TestV3NoLookahead:
    """Prove replay cannot access future data."""
    
    def test_no_future_access(self):
        """Only current/past events accessible."""
        trades = [
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(20.0, 100.0, 1.0, True),
            AggressiveTrade(30.0, 100.0, 1.0, True),
        ]
        
        adapter = TradeFeedAdapter(trades)
        
        # At start, can only see first timestamp
        assert adapter.peek_next_timestamp() == 10.0
        
        # Emit first
        adapter.emit_next()
        
        # Now can only see second timestamp
        assert adapter.peek_next_timestamp() == 20.0
        
        # Cannot see t=30 yet
        # (Would need to emit t=20 first)
    
    def test_peek_does_not_allow_skip(self):
        """peek_next_timestamp() doesn't allow skipping events."""
        trades = [
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(20.0, 100.0, 1.0, True),
        ]
        
        adapter = TradeFeedAdapter(trades)
        
        # Peek at next
        ts = adapter.peek_next_timestamp()
        assert ts == 10.0
        
        # Peek again
        ts = adapter.peek_next_timestamp()
        assert ts == 10.0  # Same event
        
        # Must emit to advance
        event = adapter.emit_next()
        assert event.timestamp == 10.0
        
        # Now peek shows next
        assert adapter.peek_next_timestamp() == 20.0
    
    def test_iterator_forward_only(self):
        """After emit_next(), cannot go back."""
        trades = [
            AggressiveTrade(10.0, 100.0, 1.0, True),
            AggressiveTrade(20.0, 100.0, 1.0, True),
        ]
        
        adapter = TradeFeedAdapter(trades)
        
        # Emit first
        e1 = adapter.emit_next()
        assert e1.timestamp == 10.0
        
        # Emit second
        e2 = adapter.emit_next()
        assert e2.timestamp == 20.0
        
        # No way to go back to t=10
        # No more events
        assert not adapter.has_more()


# ==============================================
# V4: LIVE/REPLAY INTERFACE PARITY
# ==============================================

class TestV4InterfaceParity:
    """Verify replay uses same interfaces as live."""
    
    def test_synchronizer_interface_parity(self):
        """ReplayDataSync uses DataSynchronizer (same interface)."""
        sync = ReplayDataSync()
        
        # Same methods as live
        assert hasattr(sync.sync, 'push_orderbook')
        assert hasattr(sync.sync, 'push_trade')
        assert hasattr(sync.sync, 'push_liquidation')
        assert hasattr(sync.sync, 'push_kline')
        assert hasattr(sync.sync, 'get_aligned_snapshot')
        
        # No replay-specific methods
        assert not hasattr(sync, 'replay_mode')
        assert not hasattr(sync, 'is_simulation')
    
    def test_controller_interface_parity(self):
        """ReplaySystemWrapper uses MasterController (same interface)."""
        wrapper = ReplaySystemWrapper()
        
        # Uses standard MasterController
        assert hasattr(wrapper.controller, 'update')
        assert hasattr(wrapper.controller, 'get_current_regime')
        assert hasattr(wrapper.controller, 'get_active_strategy')
        
        # No replay-specific fields in controller
        assert not hasattr(wrapper.controller, 'replay_mode')
        assert not hasattr(wrapper.controller, 'is_simulation')
    
    def test_no_replay_flags(self):
        """No conditional logic based on replay/live mode."""
        # The wrapper and sync don't have mode flags
        wrapper = ReplaySystemWrapper()
        sync = ReplayDataSync()
        
        # No "is_replay" or "replay_mode" attributes
        assert not hasattr(wrapper, 'is_replay')
        assert not hasattr(wrapper, 'replay_mode')
        assert not hasattr(sync, 'is_replay')
        assert not hasattr(sync, 'replay_mode')


# ==============================================
# V5: DETERMINISM VALIDATION
# ==============================================

class TestV5Determinism:
    """Prove replay determinism."""
    
    def test_deterministic_event_processing(self):
        """Same data → same event sequence."""
        def create_and_run():
            trades = [
                AggressiveTrade(10.0, 100.0, 1.0, True),
                AggressiveTrade(20.0, 100.0, 1.0, True),
            ]
            
            adapter = TradeFeedAdapter(trades)
            loop = EventLoop(start_time=0.0)
            
            order = []
            def handler(event):
                order.append(event.timestamp)
            
            loop.register_handler('trade', handler)
            
            while adapter.has_more():
                loop.schedule_event(adapter.emit_next())
            
            loop.run()
            return order
        
        # Run twice
        order1 = create_and_run()
        order2 = create_and_run()
        
        # EXPECT: Identical
        assert order1 == order2
    
    def test_deterministic_outputs(self):
        """Run replay twice → identical results."""
        def create_data():
            return (
                [OrderbookSnapshot(i, ((100.0, 1.0),), ((101.0, 1.0),), 100.5) for i in range(30)],
                [AggressiveTrade(i, 100.0, 1.0, True) for i in range(30)],
                [LiquidationEvent(i, "BTCUSDT", "SELL", 0.1, 100.0, 10.0) for i in range(30)],
                [Kline(i, 100.0, 101.0, 99.0, 100.5, 1000.0, '1m') for i in range(30)],
                [Kline(i*5, 100.0, 101.0, 99.0, 100.5, 5000.0, '5m') for i in range(6)],
            )
        
        # Run replay twice
        controller1 = ReplayController()
        obs1, trades1, liqs1, k1m1, k5m1 = create_data()
        summary1 = controller1.run_replay(obs1, trades1, liqs1, k1m1, k5m1)
        
        controller2 = ReplayController()
        obs2, trades2, liqs2, k1m2, k5m2 = create_data()
        summary2 = controller2.run_replay(obs2, trades2, liqs2, k1m2, k5m2)
        
        # EXPECT: Identical results
        assert summary1['events_processed'] == summary2['events_processed']
        assert summary1['executions'] == summary2['executions']
        assert summary1['final_time'] == summary2['final_time']
    
    def test_no_environmental_dependencies(self):
        """No random, system time, or environment dependencies."""
        # Replay uses only event timestamps
        loop = EventLoop(start_time=1000.0)
        
        # Clock is explicit, not system time
        assert loop.get_current_time() == 1000.0
        
        # Process event
        loop.schedule_event(Event(1001.0, 'test', None))
        loop.register_handler('test', lambda e: None)
        loop.run()
        
        # Time is event-driven
        assert loop.get_current_time() == 1001.0


# ==============================================
# VALIDATION SUMMARY
# ==============================================

def test_all_validation_tests_must_pass():
    """
    This test serves as a reminder.
    
    If ANY V1-V5 test fails:
    - STOP
    - DO NOT implement simulation tests
    - Fix infrastructure
    - Re-run validation
    """
    # This always passes, it's just documentation
    assert True, "All V1-V5 tests must pass before simulation tests"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
