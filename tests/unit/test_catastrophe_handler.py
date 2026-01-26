"""Unit tests for catastrophe_handler.py."""

import pytest
from runtime.risk.catastrophe_handler import (
    CatastropheHandler,
    CatastropheState,
    CatastropheEvent,
    FailureType,
    FailureCounter,
)


class TestCatastropheState:
    """Tests for CatastropheState enum."""

    def test_states_defined(self):
        """All states should be defined."""
        assert CatastropheState.NORMAL.value == "NORMAL"
        assert CatastropheState.DEGRADED.value == "DEGRADED"
        assert CatastropheState.CRITICAL.value == "CRITICAL"
        assert CatastropheState.HALTED.value == "HALTED"


class TestFailureCounter:
    """Tests for FailureCounter class."""

    def test_increment_within_window(self):
        """Should increment count within window."""
        counter = FailureCounter(failure_type="test", window_ns=1_000_000_000)

        ts = 1_000_000_000_000
        assert counter.increment(ts) == 1
        assert counter.increment(ts + 100) == 2
        assert counter.increment(ts + 200) == 3

    def test_reset_on_window_expiry(self):
        """Should reset count when window expires."""
        counter = FailureCounter(failure_type="test", window_ns=1000)  # 1 microsecond

        ts = 1_000_000_000_000
        counter.increment(ts)
        counter.increment(ts + 100)

        # After window
        assert counter.increment(ts + 5000) == 1  # Reset to 1


class TestCatastropheHandler:
    """Tests for CatastropheHandler class."""

    @pytest.fixture
    def handler(self):
        """Create fresh handler for each test."""
        return CatastropheHandler()

    def test_initial_state_is_normal(self, handler):
        """Handler should start in NORMAL state."""
        assert handler.state == CatastropheState.NORMAL

    def test_websocket_disconnect_degrades(self, handler):
        """WebSocket disconnect should transition to DEGRADED."""
        new_state = handler.report_failure(
            FailureType.WEBSOCKET_DISCONNECT,
            "Connection lost",
        )

        assert new_state == CatastropheState.DEGRADED
        assert handler.state == CatastropheState.DEGRADED

    def test_exchange_halt_goes_to_halted(self, handler):
        """Exchange halt should transition directly to HALTED."""
        new_state = handler.report_failure(
            FailureType.EXCHANGE_HALT,
            "Exchange maintenance",
        )

        assert new_state == CatastropheState.HALTED
        assert handler.state == CatastropheState.HALTED

    def test_cascading_failures_escalate(self, handler):
        """Multiple failures should escalate state."""
        # First failure
        handler.report_failure(FailureType.WEBSOCKET_DISCONNECT)
        assert handler.state == CatastropheState.DEGRADED

        # Second failure escalates
        handler.report_failure(FailureType.WEBSOCKET_DISCONNECT)
        assert handler.state == CatastropheState.CRITICAL

        # Third failure
        handler.report_failure(FailureType.WEBSOCKET_DISCONNECT)
        assert handler.state == CatastropheState.HALTED

    def test_can_enter_position_only_in_normal(self, handler):
        """Position entry should only be allowed in NORMAL."""
        assert handler.can_enter_position() is True

        handler.report_failure(FailureType.API_RATE_LIMIT)
        assert handler.can_enter_position() is False

    def test_can_exit_except_halted(self, handler):
        """Position exit should be allowed except in HALTED."""
        assert handler.can_exit_position() is True

        handler.report_failure(FailureType.WEBSOCKET_DISCONNECT)
        assert handler.can_exit_position() is True  # DEGRADED

        handler.report_failure(FailureType.POSITION_MISMATCH)
        # After position mismatch from DEGRADED, should be HALTED
        assert handler.can_exit_position() is False

    def test_rejection_storm_detection(self, handler):
        """Should detect rejection storm from multiple rejections."""
        ts = 1_000_000_000_000

        # Report rejections below threshold
        for i in range(4):
            handler.report_rejection("rejection", ts + i * 100)

        assert handler.state == CatastropheState.NORMAL

        # Fifth rejection triggers storm
        handler.report_rejection("rejection", ts + 500)
        assert handler.state == CatastropheState.DEGRADED

    def test_rate_limit_storm_detection(self, handler):
        """Should detect rate limit storm."""
        ts = 1_000_000_000_000

        for i in range(2):
            handler.report_rate_limit("429", ts + i * 100)

        assert handler.state == CatastropheState.NORMAL

        # Third triggers storm
        handler.report_rate_limit("429", ts + 300)
        assert handler.state == CatastropheState.DEGRADED

    def test_recovery_from_degraded(self, handler):
        """Should recover from DEGRADED with conditions met."""
        handler.report_failure(FailureType.API_RATE_LIMIT)
        assert handler.state == CatastropheState.DEGRADED

        # Attempt recovery with conditions
        success = handler.attempt_recovery({"api_ok": True})
        assert success is True
        assert handler.state == CatastropheState.NORMAL

    def test_no_recovery_from_halted(self, handler):
        """Should not auto-recover from HALTED."""
        handler.report_failure(FailureType.EXCHANGE_HALT)
        assert handler.state == CatastropheState.HALTED

        success = handler.attempt_recovery({"all_ok": True})
        assert success is False
        assert handler.state == CatastropheState.HALTED

    def test_force_reset_requires_confirmation(self, handler):
        """Force reset should require exact phrase."""
        handler.report_failure(FailureType.EXCHANGE_HALT)

        # Wrong phrase
        success = handler.force_reset("wrong phrase")
        assert success is False
        assert handler.state == CatastropheState.HALTED

        # Correct phrase
        success = handler.force_reset("CONFIRM RESET")
        assert success is True
        assert handler.state == CatastropheState.NORMAL

    def test_events_are_recorded(self, handler):
        """Should record events."""
        handler.report_failure(FailureType.WEBSOCKET_DISCONNECT, "test")

        events = handler.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == "websocket_disconnect"
        assert events[0].new_state == CatastropheState.DEGRADED

    def test_state_summary(self, handler):
        """Should provide state summary."""
        summary = handler.get_state_summary()

        assert "state" in summary
        assert summary["state"] == "NORMAL"
        assert "event_count" in summary

    def test_state_change_callback(self):
        """Should call callback on state change."""
        changes = []

        def callback(old, new):
            changes.append((old, new))

        handler = CatastropheHandler(on_state_change=callback)
        handler.report_failure(FailureType.WEBSOCKET_DISCONNECT)

        assert len(changes) == 1
        assert changes[0] == (CatastropheState.NORMAL, CatastropheState.DEGRADED)
