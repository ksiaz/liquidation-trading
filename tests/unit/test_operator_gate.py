"""Unit tests for operator_gate.py."""

import pytest
from runtime.governance.operator_gate import (
    OperatorGate,
    OperatorConfirmation,
    DangerousAction,
    DEFAULT_DANGEROUS_ACTIONS,
)


class TestOperatorConfirmation:
    """Tests for OperatorConfirmation dataclass."""

    def test_confirmation_is_frozen(self):
        """OperatorConfirmation should be immutable."""
        conf = OperatorConfirmation(
            ts_ns=1000,
            action="test",
            operator_input="phrase",
            success=True,
        )
        with pytest.raises(AttributeError):
            conf.action = "changed"


class TestDangerousAction:
    """Tests for DangerousAction dataclass."""

    def test_default_actions_defined(self):
        """Default dangerous actions should be defined."""
        assert len(DEFAULT_DANGEROUS_ACTIONS) > 0
        assert "reset_kill_switch" in DEFAULT_DANGEROUS_ACTIONS
        assert "override_circuit_breaker" in DEFAULT_DANGEROUS_ACTIONS


class TestOperatorGate:
    """Tests for OperatorGate class."""

    @pytest.fixture
    def gate(self):
        """Create fresh gate for each test."""
        return OperatorGate()

    def test_is_dangerous(self, gate):
        """Should identify dangerous actions."""
        assert gate.is_dangerous("reset_kill_switch") is True
        assert gate.is_dangerous("unknown_action") is False

    def test_get_required_phrase(self, gate):
        """Should return required confirmation phrase."""
        phrase = gate.get_required_phrase("reset_kill_switch")
        assert phrase == "CONFIRM KILL SWITCH RESET"

        assert gate.get_required_phrase("unknown") is None

    def test_request_confirmation(self, gate):
        """Should mark action as pending."""
        result = gate.request_confirmation("reset_kill_switch")
        assert result is True

        pending = gate.get_pending_actions()
        assert "reset_kill_switch" in pending

    def test_request_unknown_action_fails(self, gate):
        """Should fail for unknown actions."""
        result = gate.request_confirmation("unknown_action")
        assert result is False

    def test_verify_correct_confirmation(self, gate):
        """Should verify correct confirmation phrase."""
        gate.request_confirmation("reset_kill_switch")

        result = gate.verify_confirmation(
            "reset_kill_switch",
            "CONFIRM KILL SWITCH RESET",
        )

        assert result is True
        assert "reset_kill_switch" not in gate.get_pending_actions()

    def test_verify_wrong_confirmation(self, gate):
        """Should reject wrong confirmation phrase."""
        gate.request_confirmation("reset_kill_switch")

        result = gate.verify_confirmation(
            "reset_kill_switch",
            "wrong phrase",
        )

        assert result is False

    def test_confirmation_history(self, gate):
        """Should record confirmation attempts."""
        gate.request_confirmation("reset_kill_switch")
        gate.verify_confirmation("reset_kill_switch", "wrong")
        gate.request_confirmation("reset_kill_switch")
        gate.verify_confirmation("reset_kill_switch", "CONFIRM KILL SWITCH RESET")

        history = gate.get_confirmation_history()

        assert len(history) == 2
        assert history[0].success is False
        assert history[1].success is True

    def test_cooldown_blocks_rapid_confirms(self, gate):
        """Should enforce cooldown between confirmations."""
        # First confirmation
        gate.request_confirmation("reset_kill_switch")
        gate.verify_confirmation("reset_kill_switch", "CONFIRM KILL SWITCH RESET")

        # Immediate second request should be blocked by cooldown
        result = gate.request_confirmation("reset_kill_switch")
        # Cooldown is 60 seconds, so this should fail
        assert result is False

    def test_cancel_pending(self, gate):
        """Should cancel pending confirmation."""
        gate.request_confirmation("reset_kill_switch")
        assert "reset_kill_switch" in gate.get_pending_actions()

        result = gate.cancel_pending("reset_kill_switch")
        assert result is True
        assert "reset_kill_switch" not in gate.get_pending_actions()

    def test_cancel_non_pending_returns_false(self, gate):
        """Should return False when cancelling non-pending action."""
        result = gate.cancel_pending("reset_kill_switch")
        assert result is False

    def test_get_status(self, gate):
        """Should return status summary."""
        gate.request_confirmation("reset_kill_switch")

        status = gate.get_status()

        assert status["pending_count"] == 1
        assert "reset_kill_switch" in status["pending_actions"]
        assert "registered_actions" in status

    def test_custom_dangerous_actions(self):
        """Should accept custom dangerous actions."""
        custom_actions = {
            "custom_action": DangerousAction(
                name="custom_action",
                confirmation_phrase="CUSTOM PHRASE",
                description="Custom action",
                cooldown_ns=0,  # No cooldown for testing
            ),
        }

        gate = OperatorGate(dangerous_actions=custom_actions)

        assert gate.is_dangerous("custom_action") is True
        assert gate.is_dangerous("reset_kill_switch") is False

        gate.request_confirmation("custom_action")
        result = gate.verify_confirmation("custom_action", "CUSTOM PHRASE")
        assert result is True

    def test_get_cooldown_remaining(self, gate):
        """Should track remaining cooldown time."""
        # Before any confirmation, cooldown is 0
        remaining = gate.get_cooldown_remaining("reset_kill_switch")
        assert remaining == 0

        # After confirmation, cooldown should be active
        gate.request_confirmation("reset_kill_switch")
        gate.verify_confirmation("reset_kill_switch", "CONFIRM KILL SWITCH RESET")

        remaining = gate.get_cooldown_remaining("reset_kill_switch")
        assert remaining > 0  # Should have remaining cooldown
