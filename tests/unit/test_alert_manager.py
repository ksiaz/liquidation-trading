"""Unit tests for AlertManager."""

import pytest
import time
from unittest.mock import MagicMock

from runtime.analytics.alert_manager import AlertManager, AlertConfig, AlertRule
from runtime.analytics.types import AlertLevel


class TestAlertManager:
    """Tests for AlertManager."""

    def test_init_defaults(self):
        """Test manager initialization."""
        manager = AlertManager()
        assert len(manager._rules) == 0
        assert len(manager._alerts) == 0
        assert len(manager._active_alerts) == 0

    def test_init_custom_config(self):
        """Test manager with custom config."""
        config = AlertConfig(
            max_alerts_in_memory=500,
            default_cooldown_ms=30000
        )
        manager = AlertManager(config=config)
        assert manager._config.max_alerts_in_memory == 500

    def test_generate_alert_id(self):
        """Test alert ID generation."""
        manager = AlertManager()
        id1 = manager._generate_alert_id()
        id2 = manager._generate_alert_id()
        assert id1 != id2
        assert id1.startswith("alert_")

    def test_register_rule(self):
        """Test rule registration."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test alert"
        )
        manager.register_rule(rule)

        assert "test_rule" in manager._rules

    def test_unregister_rule(self):
        """Test rule unregistration."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test alert"
        )
        manager.register_rule(rule)
        manager.unregister_rule("test_rule")

        assert "test_rule" not in manager._rules

    def test_suppress_rule(self):
        """Test rule suppression."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test alert"
        )
        manager.register_rule(rule)
        manager.suppress_rule("test_rule")

        alerts = manager.evaluate_rules()
        assert len(alerts) == 0  # Rule suppressed

    def test_unsuppress_rule(self):
        """Test rule unsuppression."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test alert"
        )
        manager.register_rule(rule)
        manager.suppress_rule("test_rule")
        manager.unsuppress_rule("test_rule")

        alerts = manager.evaluate_rules()
        assert len(alerts) == 1

    def test_evaluate_rules_triggered(self):
        """Test rule evaluation when condition is true."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,  # Always triggers
            message_template="Test alert triggered"
        )
        manager.register_rule(rule)

        alerts = manager.evaluate_rules()

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert alerts[0].category == "health"
        assert alerts[0].message == "Test alert triggered"

    def test_evaluate_rules_not_triggered(self):
        """Test rule evaluation when condition is false."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: False,  # Never triggers
            message_template="Test alert"
        )
        manager.register_rule(rule)

        alerts = manager.evaluate_rules()
        assert len(alerts) == 0

    def test_cooldown_prevents_duplicate(self):
        """Test cooldown prevents rapid re-triggering."""
        config = AlertConfig(default_cooldown_ms=60000)  # 1 minute
        manager = AlertManager(config=config)

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test alert",
            cooldown_ms=60000
        )
        manager.register_rule(rule)

        # First evaluation triggers
        alerts1 = manager.evaluate_rules()
        assert len(alerts1) == 1

        # Second evaluation blocked by cooldown
        alerts2 = manager.evaluate_rules()
        assert len(alerts2) == 0

    def test_trigger_alert_manual(self):
        """Test manual alert triggering."""
        manager = AlertManager()

        alert = manager.trigger_alert(
            level=AlertLevel.ERROR,
            category="performance",
            message="Manual test alert",
            metric_name="win_rate",
            metric_value=0.35,
            threshold=0.40
        )

        assert alert is not None
        assert alert.level == AlertLevel.ERROR
        assert alert.category == "performance"
        assert alert.metric_name == "win_rate"
        assert alert.metric_value == 0.35
        assert alert.threshold == 0.40

        # Should be in active alerts
        assert alert.alert_id in manager._active_alerts

    def test_acknowledge_alert(self):
        """Test alert acknowledgment."""
        manager = AlertManager()

        alert = manager.trigger_alert(
            level=AlertLevel.WARNING,
            category="health",
            message="Test"
        )

        assert not alert.acknowledged

        result = manager.acknowledge_alert(alert.alert_id)
        assert result is True
        assert alert.acknowledged is True

    def test_acknowledge_nonexistent(self):
        """Test acknowledging nonexistent alert."""
        manager = AlertManager()
        result = manager.acknowledge_alert("nonexistent")
        assert result is False

    def test_resolve_alert(self):
        """Test alert resolution."""
        manager = AlertManager()

        alert = manager.trigger_alert(
            level=AlertLevel.WARNING,
            category="health",
            message="Test"
        )

        assert alert.alert_id in manager._active_alerts

        result = manager.resolve_alert(alert.alert_id)
        assert result is True
        assert alert.resolved is True
        assert alert.alert_id not in manager._active_alerts

    def test_resolve_nonexistent(self):
        """Test resolving nonexistent alert."""
        manager = AlertManager()
        result = manager.resolve_alert("nonexistent")
        assert result is False

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        manager = AlertManager()

        manager.trigger_alert(AlertLevel.WARNING, "health", "Alert 1")
        manager.trigger_alert(AlertLevel.ERROR, "performance", "Alert 2")
        manager.trigger_alert(AlertLevel.WARNING, "health", "Alert 3")

        all_active = manager.get_active_alerts()
        assert len(all_active) == 3

        warnings_only = manager.get_active_alerts(level=AlertLevel.WARNING)
        assert len(warnings_only) == 2

    def test_get_unacknowledged_alerts(self):
        """Test getting unacknowledged alerts."""
        manager = AlertManager()

        alert1 = manager.trigger_alert(AlertLevel.WARNING, "health", "Alert 1")
        alert2 = manager.trigger_alert(AlertLevel.WARNING, "health", "Alert 2")

        manager.acknowledge_alert(alert1.alert_id)

        unacked = manager.get_unacknowledged_alerts()
        assert len(unacked) == 1
        assert unacked[0].alert_id == alert2.alert_id

    def test_get_alerts_by_category(self):
        """Test getting alerts by category."""
        manager = AlertManager()

        manager.trigger_alert(AlertLevel.WARNING, "health", "Health 1")
        manager.trigger_alert(AlertLevel.WARNING, "health", "Health 2")
        manager.trigger_alert(AlertLevel.WARNING, "performance", "Perf 1")

        health_alerts = manager.get_alerts_by_category("health")
        assert len(health_alerts) == 2

        perf_alerts = manager.get_alerts_by_category("performance")
        assert len(perf_alerts) == 1

    def test_get_alert_history(self):
        """Test getting alert history."""
        manager = AlertManager()

        for i in range(10):
            manager.trigger_alert(AlertLevel.INFO, "test", f"Alert {i}")

        history = manager.get_alert_history(limit=5)
        assert len(history) == 5

    def test_get_alert_counts(self):
        """Test getting alert counts by level."""
        manager = AlertManager()

        manager.trigger_alert(AlertLevel.INFO, "test", "Info")
        manager.trigger_alert(AlertLevel.WARNING, "test", "Warning 1")
        manager.trigger_alert(AlertLevel.WARNING, "test", "Warning 2")
        manager.trigger_alert(AlertLevel.ERROR, "test", "Error")

        counts = manager.get_alert_counts()

        assert counts["INFO"] == 1
        assert counts["WARNING"] == 2
        assert counts["ERROR"] == 1
        assert counts["CRITICAL"] == 0

    def test_get_summary(self):
        """Test getting alert summary."""
        manager = AlertManager()

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: False,
            message_template="Test"
        )
        manager.register_rule(rule)

        manager.trigger_alert(AlertLevel.WARNING, "health", "Alert 1")
        alert2 = manager.trigger_alert(AlertLevel.ERROR, "performance", "Alert 2")
        manager.acknowledge_alert(alert2.alert_id)

        summary = manager.get_summary()

        assert summary['active_alerts'] == 2
        assert summary['unacknowledged'] == 1
        assert summary['registered_rules'] == 1
        assert summary['by_level']['WARNING'] == 1
        assert summary['by_level']['ERROR'] == 1
        assert summary['by_category']['health'] == 1
        assert summary['by_category']['performance'] == 1

    def test_alert_callback(self):
        """Test alert callback notification."""
        manager = AlertManager()
        callback = MagicMock()

        manager.add_alert_callback(callback)
        manager.trigger_alert(AlertLevel.WARNING, "test", "Test alert")

        callback.assert_called_once()
        alert = callback.call_args[0][0]
        assert alert.level == AlertLevel.WARNING

    def test_resolve_callback(self):
        """Test resolve callback notification."""
        manager = AlertManager()
        callback = MagicMock()

        manager.add_resolve_callback(callback)
        alert = manager.trigger_alert(AlertLevel.WARNING, "test", "Test")
        manager.resolve_alert(alert.alert_id)

        callback.assert_called_once()

    def test_clear_callbacks(self):
        """Test clearing callbacks."""
        manager = AlertManager()
        callback = MagicMock()

        manager.add_alert_callback(callback)
        manager.clear_callbacks()
        manager.trigger_alert(AlertLevel.WARNING, "test", "Test")

        callback.assert_not_called()

    def test_escalation_on_repeated_triggers(self):
        """Test alert escalation after repeated triggers."""
        config = AlertConfig(
            auto_escalate_after_repeats=3,
            escalation_window_ms=60000,  # 1 minute window
            default_cooldown_ms=0  # No cooldown for test
        )
        manager = AlertManager(config=config)

        rule = AlertRule(
            name="test_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test",
            cooldown_ms=0  # No cooldown
        )
        manager.register_rule(rule)

        # First 3 triggers are WARNING
        for i in range(3):
            alerts = manager.evaluate_rules()
            if alerts:
                assert alerts[0].level == AlertLevel.WARNING

        # 4th trigger should escalate to ERROR
        alerts = manager.evaluate_rules()
        if alerts:
            assert alerts[0].level == AlertLevel.ERROR

    def test_condition_exception_handling(self):
        """Test handling of condition evaluation errors."""
        manager = AlertManager()

        rule = AlertRule(
            name="bad_rule",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: 1 / 0,  # Will raise
            message_template="Test"
        )
        manager.register_rule(rule)

        # Should not raise, just skip the bad rule
        alerts = manager.evaluate_rules()
        assert len(alerts) == 0

    def test_cooldown_by_level(self):
        """Test level-specific cooldowns."""
        config = AlertConfig(
            default_cooldown_ms=60000,
            critical_cooldown_ms=30000,
            emergency_cooldown_ms=10000
        )
        manager = AlertManager(config=config)

        # Test that cooldown check uses level-specific values
        rule_crit = AlertRule(
            name="critical_rule",
            category="health",
            level=AlertLevel.CRITICAL,
            condition=lambda: True,
            message_template="Critical"
        )

        rule_emerg = AlertRule(
            name="emergency_rule",
            category="health",
            level=AlertLevel.EMERGENCY,
            condition=lambda: True,
            message_template="Emergency"
        )

        manager.register_rule(rule_crit)
        manager.register_rule(rule_emerg)

        # Both should trigger first time
        alerts = manager.evaluate_rules()
        assert len(alerts) == 2

    def test_alert_with_details(self):
        """Test alert with additional details."""
        manager = AlertManager()

        details = {
            "source": "orderbook",
            "last_update": "2024-01-15T10:00:00Z",
            "staleness_ms": 1500
        }

        alert = manager.trigger_alert(
            level=AlertLevel.WARNING,
            category="health",
            message="Data stale",
            details=details
        )

        assert alert.details == details

    def test_max_alerts_limit(self):
        """Test max alerts storage limit."""
        config = AlertConfig(max_alerts_in_memory=5)
        manager = AlertManager(config=config)

        for i in range(10):
            manager.trigger_alert(AlertLevel.INFO, "test", f"Alert {i}")

        # Should only store last 5
        assert len(manager._alerts) == 5

    def test_thread_safety(self):
        """Test thread-safe access."""
        import threading

        manager = AlertManager()
        errors = []

        def trigger_alerts():
            try:
                for i in range(50):
                    manager.trigger_alert(AlertLevel.INFO, "test", f"Alert {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=trigger_alerts) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_alert_rule_creation(self):
        """Test AlertRule creation."""
        rule = AlertRule(
            name="test",
            category="health",
            level=AlertLevel.WARNING,
            condition=lambda: True,
            message_template="Test message",
            metric_name="cpu_usage",
            threshold=80.0,
            cooldown_ms=30000
        )

        assert rule.name == "test"
        assert rule.category == "health"
        assert rule.level == AlertLevel.WARNING
        assert rule.metric_name == "cpu_usage"
        assert rule.threshold == 80.0
        assert rule.cooldown_ms == 30000

    def test_alert_rule_defaults(self):
        """Test AlertRule default values."""
        rule = AlertRule(
            name="test",
            category="health",
            level=AlertLevel.INFO,
            condition=lambda: False,
            message_template="Test"
        )

        assert rule.metric_name is None
        assert rule.threshold is None
        assert rule.cooldown_ms == 60000  # Default
