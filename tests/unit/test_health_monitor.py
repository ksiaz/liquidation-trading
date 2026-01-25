"""
Unit tests for HLP16 Health Monitor.

Tests component health tracking, heartbeats, and alerting.
"""

import pytest
import time

from runtime.risk import (
    HealthMonitor,
    HealthConfig,
    ComponentHealth,
    AlertSeverity,
)


class TestHealthMonitor:
    """Tests for HealthMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create monitor with test config."""
        config = HealthConfig(
            heartbeat_timeout_ms=1000,  # 1 second
            heartbeat_warning_ms=500,  # 0.5 seconds
            cpu_warning_pct=80.0,
            cpu_critical_pct=95.0,
            alert_cooldown_ms=100  # Fast for testing
        )
        return HealthMonitor(config)

    def test_register_component(self, monitor):
        """Components can be registered."""
        monitor.register_component("test_component")
        status = monitor.get_component_status("test_component")
        assert status is not None
        assert status.name == "test_component"
        assert status.health == ComponentHealth.UNKNOWN

    def test_heartbeat_updates_status(self, monitor):
        """Heartbeat updates component status."""
        monitor.register_component("test")
        monitor.heartbeat("test")
        status = monitor.get_component_status("test")
        assert status.last_heartbeat is not None

    def test_check_health_returns_healthy(self, monitor):
        """Fresh heartbeat results in healthy status."""
        monitor.register_component("test")
        monitor.heartbeat("test")
        health = monitor.check_health()
        assert health["test"].health == ComponentHealth.HEALTHY

    def test_missing_heartbeat_is_unhealthy(self, monitor):
        """Missing heartbeat results in unhealthy status."""
        monitor.register_component("test")
        # Manually set an old heartbeat
        ts = int(time.time() * 1_000_000_000)
        monitor._components["test"].last_heartbeat = ts - 2_000_000_000  # 2 sec ago
        health = monitor.check_health()
        assert health["test"].health == ComponentHealth.UNHEALTHY

    def test_stale_heartbeat_is_degraded(self, monitor):
        """Stale but recent heartbeat is degraded."""
        monitor.register_component("test")
        ts = int(time.time() * 1_000_000_000)
        monitor._components["test"].last_heartbeat = ts - 700_000_000  # 0.7 sec ago
        health = monitor.check_health()
        assert health["test"].health == ComponentHealth.DEGRADED

    def test_is_system_healthy_all_healthy(self, monitor):
        """System is healthy when all components healthy."""
        monitor.register_component("a")
        monitor.register_component("b")
        monitor.heartbeat("a")
        monitor.heartbeat("b")
        monitor.check_health()
        assert monitor.is_system_healthy()

    def test_is_system_healthy_one_unhealthy(self, monitor):
        """System is unhealthy when any component unhealthy."""
        monitor.register_component("a")
        monitor.register_component("b")
        monitor.heartbeat("a")
        # b has no heartbeat
        ts = int(time.time() * 1_000_000_000)
        monitor._components["b"].last_heartbeat = ts - 2_000_000_000
        monitor.check_health()
        assert not monitor.is_system_healthy()

    def test_get_unhealthy_components(self, monitor):
        """Can get list of unhealthy components."""
        monitor.register_component("healthy")
        monitor.register_component("unhealthy")
        monitor.heartbeat("healthy")
        ts = int(time.time() * 1_000_000_000)
        monitor._components["unhealthy"].last_heartbeat = ts - 2_000_000_000
        monitor.check_health()
        unhealthy = monitor.get_unhealthy_components()
        assert "unhealthy" in unhealthy
        assert "healthy" not in unhealthy

    def test_resource_warning_generates_alert(self, monitor):
        """Resource warning generates alert."""
        monitor.check_resources(cpu_pct=85.0, memory_pct=50.0)
        alerts = monitor.get_alerts(severity=AlertSeverity.WARNING)
        assert len(alerts) > 0
        assert "CPU" in alerts[0].message

    def test_resource_critical_generates_alert(self, monitor):
        """Critical resource usage generates critical alert."""
        monitor.check_resources(cpu_pct=98.0, memory_pct=50.0)
        alerts = monitor.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(alerts) > 0

    def test_acknowledge_alert(self, monitor):
        """Alerts can be acknowledged."""
        monitor.check_resources(cpu_pct=98.0, memory_pct=50.0)
        alerts = monitor.get_alerts(unacknowledged_only=True)
        assert len(alerts) > 0
        monitor.acknowledge_alert(alerts[0].alert_id)
        alerts = monitor.get_alerts(unacknowledged_only=True)
        assert len(alerts) == 0

    def test_dependency_affects_health(self, monitor):
        """Component health affected by unhealthy dependencies."""
        monitor.register_component("upstream")
        monitor.register_component("downstream", dependencies=["upstream"])
        monitor.heartbeat("downstream")
        # upstream is unhealthy
        ts = int(time.time() * 1_000_000_000)
        monitor._components["upstream"].last_heartbeat = ts - 2_000_000_000
        monitor.check_health()
        # downstream should be degraded due to dependency
        assert monitor._components["downstream"].health == ComponentHealth.DEGRADED

    def test_get_summary(self, monitor):
        """Summary provides overview."""
        monitor.register_component("a")
        monitor.register_component("b")
        monitor.heartbeat("a")
        monitor.heartbeat("b")
        monitor.check_health()
        summary = monitor.get_summary()
        assert summary['total_components'] == 2
        assert summary['is_healthy'] is True

    def test_unregister_component(self, monitor):
        """Components can be unregistered."""
        monitor.register_component("test")
        monitor.unregister_component("test")
        status = monitor.get_component_status("test")
        assert status is None

    def test_heartbeat_metadata_latency(self, monitor):
        """Heartbeat can include latency metadata."""
        monitor.register_component("test")
        monitor.heartbeat("test", metadata={'latency_ms': 25.5})
        status = monitor.get_component_status("test")
        assert status.latency_ms == 25.5
