"""
Unit tests for event lifecycle (HLP14).

Tests:
- LifecycleState transitions
- LifecycleEvent creation and management
- EventRegistry operations
- Expiration handling
- Entry window logic
"""

import pytest
from datetime import datetime, timedelta
import asyncio

from runtime.events.types import EventType, EventSeverity, get_event_info
from runtime.events.lifecycle import (
    LifecycleState,
    LifecycleEvent,
    LifecycleTransition,
    VALID_TRANSITIONS,
)
from runtime.events.registry import EventRegistry, RegistryStats


# =============================================================================
# Event Type Tests
# =============================================================================

class TestEventTypes:
    """Tests for event types."""

    def test_all_event_types_exist(self):
        """Verify all expected event types are defined."""
        assert EventType.CASCADE
        assert EventType.HUNT_FAILED
        assert EventType.OI_COLLAPSE
        assert EventType.DEPTH_THIN
        assert EventType.VOLUME_SPIKE
        assert EventType.RANGE_BREAKOUT

    def test_event_severity_levels(self):
        """Verify severity levels are ordered."""
        assert EventSeverity.LOW.value < EventSeverity.MEDIUM.value
        assert EventSeverity.MEDIUM.value < EventSeverity.HIGH.value
        assert EventSeverity.HIGH.value < EventSeverity.CRITICAL.value

    def test_get_event_info(self):
        """Test getting event metadata."""
        info = get_event_info(EventType.CASCADE)

        assert 'typical_duration_sec' in info
        assert 'entry_window_pct' in info
        assert 'severity' in info
        assert info['severity'] == EventSeverity.CRITICAL

    def test_get_event_info_default(self):
        """Test default info for unknown event."""
        # Test with a type that has no metadata
        info = get_event_info(EventType.SETUP_COMPLETE)

        assert 'typical_duration_sec' in info
        assert info['severity'] == EventSeverity.MEDIUM


# =============================================================================
# Lifecycle State Tests
# =============================================================================

class TestLifecycleState:
    """Tests for lifecycle states."""

    def test_all_states_exist(self):
        """Verify all lifecycle states are defined."""
        assert LifecycleState.DETECTED
        assert LifecycleState.TRIGGERED
        assert LifecycleState.ACTIVE
        assert LifecycleState.COMPLETING
        assert LifecycleState.COMPLETED
        assert LifecycleState.EXPIRED

    def test_valid_transitions_defined(self):
        """Verify valid transitions are defined for all states."""
        for state in LifecycleState:
            assert state in VALID_TRANSITIONS

    def test_detected_transitions(self):
        """Test valid transitions from DETECTED."""
        valid = VALID_TRANSITIONS[LifecycleState.DETECTED]
        assert LifecycleState.TRIGGERED in valid
        assert LifecycleState.EXPIRED in valid
        assert LifecycleState.ACTIVE not in valid  # Can't skip

    def test_terminal_states_have_no_transitions(self):
        """Test that terminal states have no valid transitions."""
        assert len(VALID_TRANSITIONS[LifecycleState.COMPLETED]) == 0
        assert len(VALID_TRANSITIONS[LifecycleState.EXPIRED]) == 0


# =============================================================================
# Lifecycle Event Tests
# =============================================================================

class TestLifecycleEvent:
    """Tests for LifecycleEvent."""

    @pytest.fixture
    def cascade_event(self):
        """Create a cascade event for testing."""
        return LifecycleEvent(
            event_id="cascade_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
            ttl_ms=60000,  # 1 minute
        )

    def test_event_creation(self, cascade_event):
        """Test event creation."""
        assert cascade_event.event_id == "cascade_001"
        assert cascade_event.event_type == EventType.CASCADE
        assert cascade_event.symbol == "BTC-PERP"
        assert cascade_event.state == LifecycleState.DETECTED
        assert cascade_event.detected_at is not None

    def test_initial_state_recorded(self, cascade_event):
        """Test initial state is recorded in history."""
        assert len(cascade_event.metrics_history) == 1
        state, timestamp, metrics = cascade_event.metrics_history[0]
        assert state == LifecycleState.DETECTED

    def test_entry_window_closed_initially(self, cascade_event):
        """Test entry window is closed in DETECTED state."""
        assert not cascade_event.entry_window_open

    def test_entry_window_opens_in_completing(self, cascade_event):
        """Test entry window opens in COMPLETING state."""
        cascade_event.transition_to(LifecycleState.TRIGGERED, "test")
        cascade_event.transition_to(LifecycleState.ACTIVE, "test")
        cascade_event.transition_to(LifecycleState.COMPLETING, "test")

        assert cascade_event.entry_window_open

    def test_valid_transition_succeeds(self, cascade_event):
        """Test valid state transition."""
        result = cascade_event.transition_to(
            LifecycleState.TRIGGERED,
            reason="Liquidation started",
            metrics={'oi_drop': 0.05},
        )

        assert result
        assert cascade_event.state == LifecycleState.TRIGGERED
        assert cascade_event.triggered_at is not None
        assert len(cascade_event.transitions) == 1

    def test_invalid_transition_fails(self, cascade_event):
        """Test invalid state transition is rejected."""
        # Can't skip from DETECTED to ACTIVE
        result = cascade_event.transition_to(LifecycleState.ACTIVE, "test")

        assert not result
        assert cascade_event.state == LifecycleState.DETECTED
        assert len(cascade_event.transitions) == 0

    def test_transition_history_recorded(self, cascade_event):
        """Test transition history is recorded."""
        cascade_event.transition_to(LifecycleState.TRIGGERED, "trigger reason")
        cascade_event.transition_to(LifecycleState.ACTIVE, "active reason")

        assert len(cascade_event.transitions) == 2
        assert cascade_event.transitions[0].from_state == LifecycleState.DETECTED
        assert cascade_event.transitions[0].to_state == LifecycleState.TRIGGERED
        assert cascade_event.transitions[0].reason == "trigger reason"

    def test_metrics_history_updated(self, cascade_event):
        """Test metrics history is updated on transition."""
        cascade_event.transition_to(
            LifecycleState.TRIGGERED,
            metrics={'velocity': 0.002},
        )

        assert len(cascade_event.metrics_history) == 2
        state, timestamp, metrics = cascade_event.metrics_history[1]
        assert state == LifecycleState.TRIGGERED
        assert metrics.get('velocity') == 0.002

    def test_is_active_property(self, cascade_event):
        """Test is_active property."""
        assert cascade_event.is_active

        cascade_event.transition_to(LifecycleState.TRIGGERED, "test")
        cascade_event.transition_to(LifecycleState.ACTIVE, "test")
        cascade_event.transition_to(LifecycleState.COMPLETING, "test")
        cascade_event.transition_to(LifecycleState.COMPLETED, "test")

        assert not cascade_event.is_active
        assert cascade_event.is_terminal

    def test_is_expired_property(self):
        """Test is_expired property."""
        event = LifecycleEvent(
            event_id="test",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
            detected_at=datetime.now() - timedelta(seconds=120),
            ttl_ms=60000,  # 1 minute TTL
        )

        assert event.is_expired

    def test_check_expiration(self):
        """Test check_expiration method."""
        event = LifecycleEvent(
            event_id="test",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
            detected_at=datetime.now() - timedelta(seconds=120),
            ttl_ms=60000,
        )

        result = event.check_expiration()

        assert result
        assert event.state == LifecycleState.EXPIRED

    def test_get_metrics_at_state(self, cascade_event):
        """Test getting metrics at a specific state."""
        cascade_event.transition_to(
            LifecycleState.TRIGGERED,
            metrics={'velocity': 0.002},
        )

        metrics = cascade_event.get_metrics_at_state(LifecycleState.TRIGGERED)

        assert metrics is not None
        assert metrics.get('velocity') == 0.002

    def test_to_dict(self, cascade_event):
        """Test serialization."""
        cascade_event.transition_to(LifecycleState.TRIGGERED, "test")

        data = cascade_event.to_dict()

        assert data['event_id'] == "cascade_001"
        assert data['event_type'] == "cascade"
        assert data['state'] == "triggered"
        assert 'detected_at' in data
        assert 'triggered_at' in data

    def test_severity(self, cascade_event):
        """Test event severity."""
        assert cascade_event.severity == EventSeverity.CRITICAL


# =============================================================================
# Event Registry Tests
# =============================================================================

class TestEventRegistry:
    """Tests for EventRegistry."""

    @pytest.fixture
    def registry(self):
        """Create a registry for testing."""
        return EventRegistry(max_events=100)

    @pytest.fixture
    def sample_event(self):
        """Create a sample event."""
        return LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )

    @pytest.mark.asyncio
    async def test_register_event(self, registry, sample_event):
        """Test registering an event."""
        result = await registry.register_event(sample_event)

        assert result
        event = await registry.get_event("event_001")
        assert event is not None
        assert event.event_id == "event_001"

    @pytest.mark.asyncio
    async def test_register_duplicate_fails(self, registry, sample_event):
        """Test registering duplicate event fails."""
        await registry.register_event(sample_event)
        result = await registry.register_event(sample_event)

        assert not result

    @pytest.mark.asyncio
    async def test_transition_event(self, registry, sample_event):
        """Test transitioning an event."""
        await registry.register_event(sample_event)

        result = await registry.transition_event(
            "event_001",
            LifecycleState.TRIGGERED,
            reason="Test trigger",
        )

        assert result
        event = await registry.get_event("event_001")
        assert event.state == LifecycleState.TRIGGERED

    @pytest.mark.asyncio
    async def test_transition_nonexistent_fails(self, registry):
        """Test transitioning nonexistent event fails."""
        result = await registry.transition_event(
            "nonexistent",
            LifecycleState.TRIGGERED,
        )

        assert not result

    @pytest.mark.asyncio
    async def test_get_actionable_events(self, registry):
        """Test getting actionable events."""
        # Create and register events in different states
        event1 = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        event2 = LifecycleEvent(
            event_id="event_002",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )

        await registry.register_event(event1)
        await registry.register_event(event2)

        # Advance event1 to COMPLETING
        await registry.transition_event("event_001", LifecycleState.TRIGGERED)
        await registry.transition_event("event_001", LifecycleState.ACTIVE)
        await registry.transition_event("event_001", LifecycleState.COMPLETING)

        actionable = await registry.get_actionable_events()

        assert len(actionable) == 1
        assert actionable[0].event_id == "event_001"

    @pytest.mark.asyncio
    async def test_get_actionable_events_filtered(self, registry):
        """Test filtering actionable events."""
        # Create events for different symbols
        event1 = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        event2 = LifecycleEvent(
            event_id="event_002",
            event_type=EventType.CASCADE,
            symbol="ETH-PERP",
        )

        await registry.register_event(event1)
        await registry.register_event(event2)

        # Advance both to COMPLETING
        for eid in ["event_001", "event_002"]:
            await registry.transition_event(eid, LifecycleState.TRIGGERED)
            await registry.transition_event(eid, LifecycleState.ACTIVE)
            await registry.transition_event(eid, LifecycleState.COMPLETING)

        actionable = await registry.get_actionable_events(symbol="BTC-PERP")

        assert len(actionable) == 1
        assert actionable[0].symbol == "BTC-PERP"

    @pytest.mark.asyncio
    async def test_get_events_by_symbol(self, registry):
        """Test getting events by symbol."""
        event1 = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        event2 = LifecycleEvent(
            event_id="event_002",
            event_type=EventType.VOLUME_SPIKE,
            symbol="BTC-PERP",
        )
        event3 = LifecycleEvent(
            event_id="event_003",
            event_type=EventType.CASCADE,
            symbol="ETH-PERP",
        )

        await registry.register_event(event1)
        await registry.register_event(event2)
        await registry.register_event(event3)

        btc_events = await registry.get_events_by_symbol("BTC-PERP")

        assert len(btc_events) == 2

    @pytest.mark.asyncio
    async def test_get_events_by_type(self, registry):
        """Test getting events by type."""
        event1 = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        event2 = LifecycleEvent(
            event_id="event_002",
            event_type=EventType.CASCADE,
            symbol="ETH-PERP",
        )
        event3 = LifecycleEvent(
            event_id="event_003",
            event_type=EventType.VOLUME_SPIKE,
            symbol="BTC-PERP",
        )

        await registry.register_event(event1)
        await registry.register_event(event2)
        await registry.register_event(event3)

        cascade_events = await registry.get_events_by_type(EventType.CASCADE)

        assert len(cascade_events) == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, registry):
        """Test expiration cleanup."""
        # Create an already expired event
        old_event = LifecycleEvent(
            event_id="old_event",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
            detected_at=datetime.now() - timedelta(minutes=10),
            ttl_ms=60000,  # 1 minute TTL
        )

        await registry.register_event(old_event)

        expired_count = await registry.cleanup_expired()

        assert expired_count == 1
        event = await registry.get_event("old_event")
        assert event.state == LifecycleState.EXPIRED

    @pytest.mark.asyncio
    async def test_remove_event(self, registry, sample_event):
        """Test removing an event."""
        await registry.register_event(sample_event)

        result = await registry.remove_event("event_001")

        assert result
        event = await registry.get_event("event_001")
        assert event is None

    @pytest.mark.asyncio
    async def test_get_stats(self, registry):
        """Test getting registry statistics."""
        event1 = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        event2 = LifecycleEvent(
            event_id="event_002",
            event_type=EventType.VOLUME_SPIKE,
            symbol="ETH-PERP",
        )

        await registry.register_event(event1)
        await registry.register_event(event2)

        stats = await registry.get_stats()

        assert stats.total_events == 2
        assert stats.active_events == 2
        assert 'cascade' in stats.events_by_type
        assert 'volume_spike' in stats.events_by_type

    @pytest.mark.asyncio
    async def test_create_event_factory(self, registry):
        """Test event factory method."""
        event = registry.create_event(
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
            ttl_ms=120000,
            metrics={'velocity': 0.001},
        )

        assert event.event_type == EventType.CASCADE
        assert event.symbol == "BTC-PERP"
        assert event.ttl_ms == 120000
        assert event.current_metrics.get('velocity') == 0.001
        assert event.event_id.startswith("cascade_BTC-PERP_")

    @pytest.mark.asyncio
    async def test_max_events_eviction(self):
        """Test eviction when max events reached."""
        registry = EventRegistry(max_events=5)

        # Register 5 events
        for i in range(5):
            event = LifecycleEvent(
                event_id=f"event_{i:03d}",
                event_type=EventType.CASCADE,
                symbol="BTC-PERP",
            )
            await registry.register_event(event)

        # Complete one event
        await registry.transition_event("event_000", LifecycleState.TRIGGERED)
        await registry.transition_event("event_000", LifecycleState.ACTIVE)
        await registry.transition_event("event_000", LifecycleState.COMPLETING)
        await registry.transition_event("event_000", LifecycleState.COMPLETED)

        # Register a new event (should evict completed one)
        new_event = LifecycleEvent(
            event_id="event_005",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        await registry.register_event(new_event)

        stats = await registry.get_stats()
        assert stats.total_events == 5

    @pytest.mark.asyncio
    async def test_clear(self, registry):
        """Test clearing the registry."""
        event = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        await registry.register_event(event)

        await registry.clear()

        stats = await registry.get_stats()
        assert stats.total_events == 0

    @pytest.mark.asyncio
    async def test_get_active_events(self, registry):
        """Test getting active events."""
        event1 = LifecycleEvent(
            event_id="event_001",
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        event2 = LifecycleEvent(
            event_id="event_002",
            event_type=EventType.CASCADE,
            symbol="ETH-PERP",
        )

        await registry.register_event(event1)
        await registry.register_event(event2)

        # Complete event1
        await registry.transition_event("event_001", LifecycleState.TRIGGERED)
        await registry.transition_event("event_001", LifecycleState.ACTIVE)
        await registry.transition_event("event_001", LifecycleState.COMPLETING)
        await registry.transition_event("event_001", LifecycleState.COMPLETED)

        active = await registry.get_active_events()

        assert len(active) == 1
        assert active[0].event_id == "event_002"


# =============================================================================
# Integration Tests
# =============================================================================

class TestEventLifecycleIntegration:
    """Integration tests for event lifecycle."""

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self):
        """Test event through complete lifecycle."""
        registry = EventRegistry()

        # Create and register event
        event = registry.create_event(
            event_type=EventType.CASCADE,
            symbol="BTC-PERP",
        )
        await registry.register_event(event)

        # Transition through lifecycle
        transitions = [
            (LifecycleState.TRIGGERED, {'velocity': 0.001}),
            (LifecycleState.ACTIVE, {'depth_drop': 0.5}),
            (LifecycleState.COMPLETING, {'exhaustion': 0.3}),
            (LifecycleState.COMPLETED, {'total_pnl': 100}),
        ]

        for state, metrics in transitions:
            result = await registry.transition_event(
                event.event_id,
                state,
                metrics=metrics,
            )
            assert result

        # Verify final state
        final_event = await registry.get_event(event.event_id)
        assert final_event.state == LifecycleState.COMPLETED
        assert final_event.triggered_at is not None
        assert final_event.completed_at is not None
        assert len(final_event.transitions) == 4

    @pytest.mark.asyncio
    async def test_multiple_symbols_concurrent(self):
        """Test handling multiple symbols concurrently."""
        registry = EventRegistry()

        symbols = ["BTC-PERP", "ETH-PERP", "SOL-PERP"]

        # Register events for each symbol
        for symbol in symbols:
            event = registry.create_event(
                event_type=EventType.CASCADE,
                symbol=symbol,
            )
            await registry.register_event(event)

        # All should be active
        active = await registry.get_active_events()
        assert len(active) == 3

        # Check each symbol can be queried
        for symbol in symbols:
            events = await registry.get_events_by_symbol(symbol)
            assert len(events) == 1
