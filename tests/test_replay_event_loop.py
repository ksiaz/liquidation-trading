"""
Unit Tests for Event Loop & Clock Module

Tests verify:
- Clock monotonicity (no backwards time)
- Event ordering (timestamp sort)
- Deterministic execution (same events → same result)
- Handler invocation (correct handler called)
- Time advancement (clock advances per event)
- No system time dependency

RULE: All tests are deterministic.
"""

import pytest
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.replay import Event, SimulationClock, EventLoop


class TestSimulationClock:
    """Test monotonic simulation clock."""
    
    def test_initial_time(self):
        """Clock starts at specified time."""
        start = 1704196800.0
        clock = SimulationClock(start)
        assert clock.get_time() == start
    
    def test_advance_time_forward(self):
        """Clock advances forward in time."""
        clock = SimulationClock(0.0)
        
        clock.advance_to(10.0)
        assert clock.get_time() == 10.0
        
        clock.advance_to(20.0)
        assert clock.get_time() == 20.0
    
    def test_advance_same_time(self):
        """Clock can stay at same time."""
        clock = SimulationClock(10.0)
        clock.advance_to(10.0)
        assert clock.get_time() == 10.0
    
    def test_no_backwards_time_travel(self):
        """Clock cannot move backwards."""
        clock = SimulationClock(10.0)
        
        with pytest.raises(ValueError, match="backwards"):
            clock.advance_to(5.0)
    
    def test_monotonicity(self):
        """Clock is strictly monotonic."""
        clock = SimulationClock(0.0)
        times = [1.0, 5.0, 10.0, 15.0, 20.0]
        
        for t in times:
            clock.advance_to(t)
            assert clock.get_time() == t


class TestEvent:
    """Test event structure."""
    
    def test_event_creation(self):
        """Events can be created with timestamp and data."""
        event = Event(
            timestamp=100.0,
            event_type='orderbook',
            data={'mid': 50000.0}
        )
        
        assert event.timestamp == 100.0
        assert event.event_type == 'orderbook'
        assert event.data['mid'] == 50000.0
    
    def test_event_ordering(self):
        """Events are ordered by timestamp."""
        e1 = Event(100.0, 'a', None)
        e2 = Event(200.0, 'b', None)
        e3 = Event(150.0, 'c', None)
        
        assert e1 < e2
        assert e1 < e3
        assert e3 < e2


class TestEventLoop:
    """Test deterministic event loop."""
    
    def test_initial_state(self):
        """Event loop starts at specified time."""
        loop = EventLoop(start_time=1000.0)
        assert loop.get_current_time() == 1000.0
        assert loop.get_events_processed() == 0
        assert loop.get_pending_events() == 0
    
    def test_event_scheduling(self):
        """Events can be scheduled."""
        loop = EventLoop()
        
        loop.schedule_event(Event(10.0, 'test', None))
        loop.schedule_event(Event(20.0, 'test', None))
        
        assert loop.get_pending_events() == 2
    
    def test_events_processed_in_order(self):
        """Events processed in timestamp order."""
        loop = EventLoop(0.0)
        processed_times = []
        
        def handler(event: Event):
            processed_times.append(event.timestamp)
        
        loop.register_handler('test', handler)
        
        # Schedule out of order
        loop.schedule_event(Event(30.0, 'test', None))
        loop.schedule_event(Event(10.0, 'test', None))
        loop.schedule_event(Event(20.0, 'test', None))
        
        loop.run()
        
        # EXPECT: Processed in timestamp order
        assert processed_times == [10.0, 20.0, 30.0]
    
    def test_clock_advances_per_event(self):
        """Simulation clock advances to each event timestamp."""
        loop = EventLoop(0.0)
        clock_times = []
        
        def handler(event: Event):
            clock_times.append(loop.get_current_time())
        
        loop.register_handler('test', handler)
        
        loop.schedule_event(Event(5.0, 'test', None))
        loop.schedule_event(Event(10.0, 'test', None))
        loop.schedule_event(Event(15.0, 'test', None))
        
        loop.run()
        
        # EXPECT: Clock advanced to each event timestamp
        assert clock_times == [5.0, 10.0, 15.0]
        assert loop.get_current_time() == 15.0
    
    def test_handler_invocation(self):
        """Correct handler invoked for event type."""
        loop = EventLoop()
        
        received_events = {'type_a': [], 'type_b': []}
        
        def handler_a(event: Event):
            received_events['type_a'].append(event)
        
        def handler_b(event: Event):
            received_events['type_b'].append(event)
        
        loop.register_handler('type_a', handler_a)
        loop.register_handler('type_b', handler_b)
        
        loop.schedule_event(Event(1.0, 'type_a', 'data1'))
        loop.schedule_event(Event(2.0, 'type_b', 'data2'))
        loop.schedule_event(Event(3.0, 'type_a', 'data3'))
        
        loop.run()
        
        # EXPECT: Correct handlers called
        assert len(received_events['type_a']) == 2
        assert len(received_events['type_b']) == 1
    
    def test_deterministic_execution(self):
        """Same events produce same results."""
        def create_and_run():
            loop = EventLoop(0.0)
            results = []
            
            def handler(event: Event):
                results.append((event.timestamp, event.data))
            
            loop.register_handler('test', handler)
            
            # Schedule events
            loop.schedule_event(Event(1.0, 'test', 'a'))
            loop.schedule_event(Event(2.0, 'test', 'b'))
            loop.schedule_event(Event(3.0, 'test', 'c'))
            
            loop.run()
            return results
        
        # Run twice
        results1 = create_and_run()
        results2 = create_and_run()
        
        # EXPECT: Identical results
        assert results1 == results2
    
    def test_fifo_for_same_timestamp(self):
        """Events with same timestamp processed in FIFO order."""
        loop = EventLoop(0.0)
        order = []
        
        def handler(event: Event):
            order.append(event.data)
        
        loop.register_handler('test', handler)
        
        # Schedule multiple events at same timestamp
        loop.schedule_event(Event(10.0, 'test', 'first'))
        loop.schedule_event(Event(10.0, 'test', 'second'))
        loop.schedule_event(Event(10.0, 'test', 'third'))
        
        loop.run()
        
        # EXPECT: FIFO order preserved
        assert order == ['first', 'second', 'third']
    
    def test_no_system_time_dependency(self):
        """Event loop uses only simulation time, not system time."""
        # This is implicitly tested by all other tests,
        # but we verify explicitly that clock is independent
        
        loop = EventLoop(1704196800.0)  # Fixed start time
        
        def handler(event: Event):
            # Handler sees simulation time, not system time
            assert loop.get_current_time() == event.timestamp
        
        loop.register_handler('test', handler)
        loop.schedule_event(Event(1704196850.0, 'test', None))
        loop.run()
        
        # Final time is last event time, not system time
        assert loop.get_current_time() == 1704196850.0
    
    def test_event_processing_count(self):
        """Event loop tracks number of processed events."""
        loop = EventLoop()
        
        loop.register_handler('test', lambda e: None)
        
        for i in range(10):
            loop.schedule_event(Event(float(i), 'test', None))
        
        loop.run()
        
        assert loop.get_events_processed() == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
