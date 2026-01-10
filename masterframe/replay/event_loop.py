"""
Event Loop & Clock Module

Implements deterministic event loop with explicit time control for historical replay.

INVARIANTS:
- Time only advances via events (no system time)
- Single-threaded execution
- One event at a time
- No batching
- Monotonic clock

GOAL:
Make historical replay behave IDENTICALLY to live trading.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
import heapq


@dataclass(order=True)
class Event:
    """
    Simulation event with timestamp.
    
    INVARIANT: Events are comparable by timestamp.
    """
    timestamp: float
    event_type: str = field(compare=False)
    data: Any = field(compare=False)
    
    def __repr__(self) -> str:
        return f"Event(ts={self.timestamp}, type={self.event_type})"


class SimulationClock:
    """
    Monotonic simulation clock.
    
    INVARIANT: Time only advances via events.
    INVARIANT: No system time access during simulation.
    INVARIANT: No backwards time travel.
    """
    
    def __init__(self, start_time: float = 0.0):
        """
        Initialize clock at start_time.
        
        Args:
            start_time: Initial simulation time (unix timestamp)
        """
        self._current_time = start_time
    
    def advance_to(self, timestamp: float) -> None:
        """
        Advance clock to timestamp.
        
        Args:
            timestamp: Target time
            
        Raises:
            ValueError: If timestamp < current_time (backwards time travel)
        """
        if timestamp < self._current_time:
            raise ValueError(
                f"Cannot move backwards in time: {timestamp} < {self._current_time}"
            )
        self._current_time = timestamp
    
    def get_time(self) -> float:
        """
        Get current simulation time.
        
        Returns:
            Current simulation timestamp
        """
        return self._current_time
    
    def __repr__(self) -> str:
        return f"SimulationClock(t={self._current_time})"


class EventLoop:
    """
    Deterministic event loop for historical replay.
    
    INVARIANTS:
    - Single-threaded execution
    - One event at a time
    - No batching
    - Events processed in timestamp order
    
    RULES:
    - Strategy logic only executes when event processed
    - No polling
    - No sleeping
    """
    
    def __init__(self, start_time: float = 0.0):
        """
        Initialize event loop.
        
        Args:
            start_time: Initial simulation time
        """
        self.clock = SimulationClock(start_time)
        self._event_queue: list[Event] = []  # Min-heap by timestamp
        self._event_handlers: Dict[str, Callable[[Event], None]] = {}
        self._running = False
        self._events_processed = 0
    
    def schedule_event(self, event: Event) -> None:
        """
        Schedule event for processing.
        
        Events are processed in timestamp order.
        For same timestamp, FIFO order preserved.
        
        Args:
            event: Event to schedule
        """
        heapq.heappush(self._event_queue, event)
    
    def register_handler(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """
        Register handler for event type.
        
        Args:
            event_type: Type of event to handle
            handler: Function to call when event processed
        """
        self._event_handlers[event_type] = handler
    
    def run(self) -> None:
        """
        Run event loop until queue empty.
        
        RULE: Process events in timestamp order.
        RULE: Advance clock to each event timestamp.
        RULE: Execute handler synchronously.
        
        No threading. No async. Sequential execution only.
        """
        self._running = True
        
        while self._running and self._event_queue:
            # Get next event (earliest timestamp)
            event = heapq.heappop(self._event_queue)
            
            # Advance simulation clock
            self.clock.advance_to(event.timestamp)
            
            # Process event
            handler = self._event_handlers.get(event.event_type)
            if handler:
                handler(event)
            
            self._events_processed += 1
    
    def stop(self) -> None:
        """Stop event loop after current event."""
        self._running = False
    
    def get_current_time(self) -> float:
        """
        Get current simulation time.
        
        Returns:
            Current simulation timestamp
        """
        return self.clock.get_time()
    
    def get_events_processed(self) -> int:
        """Get number of events processed."""
        return self._events_processed
    
    def get_pending_events(self) -> int:
        """Get number of pending events in queue."""
        return len(self._event_queue)
    
    def __repr__(self) -> str:
        return (
            f"EventLoop(time={self.get_current_time()}, "
            f"processed={self._events_processed}, "
            f"pending={self.get_pending_events()})"
        )
