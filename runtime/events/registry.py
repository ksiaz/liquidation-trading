"""
HLP14: Event Registry.

Central registry for tracking all active market events.

Provides:
- Event storage and retrieval
- Lifecycle state management
- Automatic expiration cleanup
- Query by symbol, type, or state
- Actionable event filtering

Usage:
    registry = EventRegistry()

    # Register new event
    event = LifecycleEvent(
        event_id="cascade_001",
        event_type=EventType.CASCADE,
        symbol="BTC-PERP",
    )
    await registry.register_event(event)

    # Transition event
    await registry.transition_event("cascade_001", LifecycleState.TRIGGERED)

    # Get actionable events (entry window open)
    actionable = await registry.get_actionable_events()

    # Cleanup expired events
    await registry.cleanup_expired()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
import uuid

from .types import EventType, EventSeverity
from .lifecycle import LifecycleEvent, LifecycleState


@dataclass
class RegistryStats:
    """Statistics about the event registry."""

    total_events: int = 0
    active_events: int = 0
    completed_events: int = 0
    expired_events: int = 0
    actionable_events: int = 0
    events_by_type: Dict[str, int] = field(default_factory=dict)
    events_by_state: Dict[str, int] = field(default_factory=dict)


class EventRegistry:
    """
    Central registry for tracking market events.

    Thread-safe event storage with lifecycle management.
    """

    def __init__(
        self,
        cleanup_interval_sec: float = 1.0,
        max_events: int = 1000,
        logger: logging.Logger = None,
    ):
        """
        Initialize registry.

        Args:
            cleanup_interval_sec: How often to run expiration cleanup
            max_events: Maximum events to store
            logger: Logger instance
        """
        self._events: Dict[str, LifecycleEvent] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval_sec
        self._max_events = max_events
        self._logger = logger or logging.getLogger(__name__)

        # Indexes for fast lookup
        self._by_symbol: Dict[str, Set[str]] = {}
        self._by_type: Dict[EventType, Set[str]] = {}
        self._by_state: Dict[LifecycleState, Set[str]] = {}

        # Stats
        self._total_registered: int = 0
        self._total_completed: int = 0
        self._total_expired: int = 0

    async def register_event(self, event: LifecycleEvent) -> bool:
        """
        Register a new event.

        Args:
            event: Event to register

        Returns:
            True if registered, False if duplicate
        """
        async with self._lock:
            if event.event_id in self._events:
                self._logger.warning(f"Duplicate event ID: {event.event_id}")
                return False

            # Enforce max events
            if len(self._events) >= self._max_events:
                await self._evict_oldest_completed()

            self._events[event.event_id] = event

            # Update indexes
            self._add_to_indexes(event)

            self._total_registered += 1
            self._logger.debug(f"Registered event: {event}")

            return True

    async def get_event(self, event_id: str) -> Optional[LifecycleEvent]:
        """Get event by ID."""
        async with self._lock:
            return self._events.get(event_id)

    async def transition_event(
        self,
        event_id: str,
        new_state: LifecycleState,
        reason: str = "",
        metrics: Dict = None,
    ) -> bool:
        """
        Transition an event to a new state.

        Args:
            event_id: Event to transition
            new_state: Target state
            reason: Transition reason
            metrics: Metrics at transition

        Returns:
            True if transition succeeded
        """
        async with self._lock:
            event = self._events.get(event_id)
            if not event:
                self._logger.warning(f"Event not found: {event_id}")
                return False

            old_state = event.state
            success = event.transition_to(new_state, reason, metrics, self._logger)

            if success:
                # Update state index
                self._update_state_index(event, old_state)

                # Track completions
                if new_state == LifecycleState.COMPLETED:
                    self._total_completed += 1
                elif new_state == LifecycleState.EXPIRED:
                    self._total_expired += 1

            return success

    async def get_actionable_events(
        self,
        symbol: str = None,
        event_type: EventType = None,
    ) -> List[LifecycleEvent]:
        """
        Get events where entry window is open.

        Args:
            symbol: Filter by symbol (optional)
            event_type: Filter by type (optional)

        Returns:
            List of actionable events
        """
        async with self._lock:
            # Get events in COMPLETING state
            completing_ids = self._by_state.get(LifecycleState.COMPLETING, set())

            actionable = []
            for event_id in completing_ids:
                event = self._events.get(event_id)
                if not event:
                    continue

                # Check filters
                if symbol and event.symbol != symbol:
                    continue
                if event_type and event.event_type != event_type:
                    continue

                # Check entry window
                if event.entry_window_open:
                    actionable.append(event)

            return actionable

    async def get_events_by_symbol(self, symbol: str) -> List[LifecycleEvent]:
        """Get all active events for a symbol."""
        async with self._lock:
            event_ids = self._by_symbol.get(symbol, set())
            return [
                self._events[eid] for eid in event_ids
                if eid in self._events and self._events[eid].is_active
            ]

    async def get_events_by_type(self, event_type: EventType) -> List[LifecycleEvent]:
        """Get all active events of a type."""
        async with self._lock:
            event_ids = self._by_type.get(event_type, set())
            return [
                self._events[eid] for eid in event_ids
                if eid in self._events and self._events[eid].is_active
            ]

    async def get_events_by_state(self, state: LifecycleState) -> List[LifecycleEvent]:
        """Get all events in a state."""
        async with self._lock:
            event_ids = self._by_state.get(state, set())
            return [
                self._events[eid] for eid in event_ids
                if eid in self._events
            ]

    async def get_active_events(self) -> List[LifecycleEvent]:
        """Get all active (non-terminal) events."""
        async with self._lock:
            return [e for e in self._events.values() if e.is_active]

    async def cleanup_expired(self) -> int:
        """
        Check all events for expiration and clean up.

        Returns:
            Number of events expired
        """
        expired_count = 0

        async with self._lock:
            for event_id, event in list(self._events.items()):
                if event.is_terminal:
                    continue

                if event.check_expiration(self._logger):
                    old_state = LifecycleState.EXPIRED  # Will be EXPIRED now
                    self._update_state_index(event, event.state)
                    expired_count += 1
                    self._total_expired += 1

        if expired_count > 0:
            self._logger.debug(f"Expired {expired_count} events")

        return expired_count

    async def remove_event(self, event_id: str) -> bool:
        """
        Remove an event from the registry.

        Args:
            event_id: Event to remove

        Returns:
            True if removed
        """
        async with self._lock:
            event = self._events.pop(event_id, None)
            if event:
                self._remove_from_indexes(event)
                return True
            return False

    async def get_stats(self) -> RegistryStats:
        """Get registry statistics."""
        async with self._lock:
            active = sum(1 for e in self._events.values() if e.is_active)
            actionable = sum(1 for e in self._events.values() if e.entry_window_open)

            by_type = {}
            for event_type, ids in self._by_type.items():
                by_type[event_type.value] = len(ids)

            by_state = {}
            for state, ids in self._by_state.items():
                by_state[state.value] = len(ids)

            return RegistryStats(
                total_events=len(self._events),
                active_events=active,
                completed_events=self._total_completed,
                expired_events=self._total_expired,
                actionable_events=actionable,
                events_by_type=by_type,
                events_by_state=by_state,
            )

    async def clear(self):
        """Clear all events from registry."""
        async with self._lock:
            self._events.clear()
            self._by_symbol.clear()
            self._by_type.clear()
            self._by_state.clear()

    # === Index management ===

    def _add_to_indexes(self, event: LifecycleEvent):
        """Add event to all indexes."""
        # Symbol index
        if event.symbol not in self._by_symbol:
            self._by_symbol[event.symbol] = set()
        self._by_symbol[event.symbol].add(event.event_id)

        # Type index
        if event.event_type not in self._by_type:
            self._by_type[event.event_type] = set()
        self._by_type[event.event_type].add(event.event_id)

        # State index
        if event.state not in self._by_state:
            self._by_state[event.state] = set()
        self._by_state[event.state].add(event.event_id)

    def _remove_from_indexes(self, event: LifecycleEvent):
        """Remove event from all indexes."""
        if event.symbol in self._by_symbol:
            self._by_symbol[event.symbol].discard(event.event_id)

        if event.event_type in self._by_type:
            self._by_type[event.event_type].discard(event.event_id)

        if event.state in self._by_state:
            self._by_state[event.state].discard(event.event_id)

    def _update_state_index(self, event: LifecycleEvent, old_state: LifecycleState):
        """Update state index after transition."""
        if old_state in self._by_state:
            self._by_state[old_state].discard(event.event_id)

        if event.state not in self._by_state:
            self._by_state[event.state] = set()
        self._by_state[event.state].add(event.event_id)

    async def _evict_oldest_completed(self):
        """Evict oldest completed/expired events when at capacity."""
        # Find completed/expired events sorted by completion time
        terminal = [
            e for e in self._events.values()
            if e.is_terminal
        ]

        if not terminal:
            # No completed events, evict oldest active
            oldest = min(
                self._events.values(),
                key=lambda e: e.detected_at,
                default=None,
            )
            if oldest:
                self._remove_from_indexes(oldest)
                del self._events[oldest.event_id]
                self._logger.warning(f"Evicted active event due to capacity: {oldest.event_id}")
        else:
            # Evict oldest completed
            oldest = min(
                terminal,
                key=lambda e: e.completed_at or e.detected_at,
            )
            self._remove_from_indexes(oldest)
            del self._events[oldest.event_id]

    # === Factory methods ===

    def create_event(
        self,
        event_type: EventType,
        symbol: str,
        ttl_ms: int = None,
        metrics: Dict = None,
    ) -> LifecycleEvent:
        """
        Create a new event with unique ID.

        Args:
            event_type: Type of event
            symbol: Trading symbol
            ttl_ms: Time to live (optional)
            metrics: Initial metrics (optional)

        Returns:
            New LifecycleEvent
        """
        event_id = f"{event_type.value}_{symbol}_{uuid.uuid4().hex[:8]}"

        event = LifecycleEvent(
            event_id=event_id,
            event_type=event_type,
            symbol=symbol,
            ttl_ms=ttl_ms or 300_000,
            current_metrics=metrics or {},
        )

        return event
