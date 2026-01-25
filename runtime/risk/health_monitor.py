"""
HLP16: Health Monitor.

Component health tracking with heartbeat-based liveness detection.

Health monitoring:
1. Heartbeat tracking - Components report liveness
2. Dependency checking - Verify upstream services
3. Resource monitoring - CPU, memory, latency
4. Alert generation - Surface problems early
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Set
from enum import Enum, auto
from threading import RLock


class ComponentHealth(Enum):
    """Health state of a component."""
    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    UNKNOWN = auto()


class AlertSeverity(Enum):
    """Severity of health alerts."""
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class HealthConfig:
    """Configuration for health monitoring."""
    # Heartbeat settings
    heartbeat_timeout_ms: int = 30_000  # 30 seconds
    heartbeat_warning_ms: int = 15_000  # 15 seconds

    # Resource thresholds
    cpu_warning_pct: float = 80.0
    cpu_critical_pct: float = 95.0
    memory_warning_pct: float = 75.0
    memory_critical_pct: float = 90.0
    latency_warning_multiplier: float = 3.0
    latency_critical_multiplier: float = 10.0

    # Check intervals
    check_interval_ms: int = 5_000  # 5 seconds

    # Alert settings
    alert_cooldown_ms: int = 60_000  # 1 minute between same alerts


@dataclass
class Heartbeat:
    """Record of a component heartbeat."""
    component_name: str
    timestamp: int  # nanoseconds
    metadata: Dict = field(default_factory=dict)


@dataclass
class HealthAlert:
    """Health alert record."""
    alert_id: str
    component_name: str
    severity: AlertSeverity
    message: str
    timestamp: int  # nanoseconds
    details: Dict = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class ComponentStatus:
    """Status of a monitored component."""
    name: str
    health: ComponentHealth
    last_heartbeat: Optional[int]  # nanoseconds
    latency_ms: Optional[float]
    error_count: int = 0
    details: Dict = field(default_factory=dict)


class HealthMonitor:
    """
    Health monitoring system with heartbeat tracking.

    Components register and send heartbeats.
    Monitor detects missing heartbeats and degraded components.
    """

    def __init__(
        self,
        config: HealthConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or HealthConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Component tracking
        self._components: Dict[str, ComponentStatus] = {}
        self._heartbeats: Dict[str, List[Heartbeat]] = {}
        self._dependencies: Dict[str, Set[str]] = {}  # component -> dependencies

        # Alert tracking
        self._alerts: List[HealthAlert] = []
        self._alert_cooldowns: Dict[str, int] = {}  # alert_key -> last_alert_ts
        self._alert_counter = 0

        # Resource baselines
        self._baseline_latencies: Dict[str, float] = {}

        self._lock = RLock()  # Reentrant lock to allow nested calls

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def register_component(
        self,
        name: str,
        dependencies: List[str] = None
    ):
        """Register a component for monitoring."""
        with self._lock:
            self._components[name] = ComponentStatus(
                name=name,
                health=ComponentHealth.UNKNOWN,
                last_heartbeat=None,
                latency_ms=None
            )
            self._heartbeats[name] = []
            if dependencies:
                self._dependencies[name] = set(dependencies)

            self._logger.info(f"Registered component: {name}")

    def unregister_component(self, name: str):
        """Unregister a component."""
        with self._lock:
            self._components.pop(name, None)
            self._heartbeats.pop(name, None)
            self._dependencies.pop(name, None)
            self._logger.info(f"Unregistered component: {name}")

    def heartbeat(
        self,
        component_name: str,
        metadata: Dict = None
    ):
        """Record a heartbeat from a component."""
        ts = self._now_ns()

        with self._lock:
            if component_name not in self._components:
                self._logger.warning(
                    f"Heartbeat from unregistered component: {component_name}"
                )
                return

            hb = Heartbeat(
                component_name=component_name,
                timestamp=ts,
                metadata=metadata or {}
            )

            self._heartbeats[component_name].append(hb)

            # Keep only recent heartbeats (last 10 minutes)
            cutoff = ts - 600_000_000_000
            self._heartbeats[component_name] = [
                h for h in self._heartbeats[component_name]
                if h.timestamp > cutoff
            ]

            # Update component status
            status = self._components[component_name]
            status.last_heartbeat = ts

            # Calculate latency if provided in metadata
            if 'latency_ms' in (metadata or {}):
                status.latency_ms = metadata['latency_ms']

    def check_health(self) -> Dict[str, ComponentStatus]:
        """Check health of all components."""
        ts = self._now_ns()

        with self._lock:
            for name, status in self._components.items():
                old_health = status.health
                status.health = self._evaluate_health(name, ts)

                # Generate alerts on health transitions
                if status.health != old_health:
                    self._handle_health_transition(name, old_health, status.health, ts)

            return dict(self._components)

    def _evaluate_health(self, component_name: str, ts: int) -> ComponentHealth:
        """Evaluate health of a single component."""
        status = self._components[component_name]

        # Check heartbeat
        if status.last_heartbeat is None:
            return ComponentHealth.UNKNOWN

        time_since_hb_ms = (ts - status.last_heartbeat) / 1_000_000

        if time_since_hb_ms > self._config.heartbeat_timeout_ms:
            return ComponentHealth.UNHEALTHY

        if time_since_hb_ms > self._config.heartbeat_warning_ms:
            return ComponentHealth.DEGRADED

        # Check latency
        if status.latency_ms is not None and component_name in self._baseline_latencies:
            baseline = self._baseline_latencies[component_name]
            if baseline > 0:
                multiplier = status.latency_ms / baseline
                if multiplier > self._config.latency_critical_multiplier:
                    return ComponentHealth.UNHEALTHY
                if multiplier > self._config.latency_warning_multiplier:
                    return ComponentHealth.DEGRADED

        # Check dependencies
        deps = self._dependencies.get(component_name, set())
        for dep in deps:
            if dep in self._components:
                dep_health = self._components[dep].health
                if dep_health == ComponentHealth.UNHEALTHY:
                    return ComponentHealth.DEGRADED

        return ComponentHealth.HEALTHY

    def _handle_health_transition(
        self,
        component_name: str,
        old_health: ComponentHealth,
        new_health: ComponentHealth,
        ts: int
    ):
        """Handle component health state transition."""
        # Determine severity
        if new_health == ComponentHealth.UNHEALTHY:
            severity = AlertSeverity.CRITICAL
        elif new_health == ComponentHealth.DEGRADED:
            severity = AlertSeverity.WARNING
        elif new_health == ComponentHealth.HEALTHY and old_health != ComponentHealth.UNKNOWN:
            severity = AlertSeverity.INFO
        else:
            return  # No alert needed

        message = f"{component_name}: {old_health.name} -> {new_health.name}"
        self._create_alert(component_name, severity, message, ts)

    def _create_alert(
        self,
        component_name: str,
        severity: AlertSeverity,
        message: str,
        ts: int,
        details: Dict = None
    ):
        """Create a health alert with cooldown."""
        alert_key = f"{component_name}:{severity.name}:{message}"

        # Check cooldown
        last_alert = self._alert_cooldowns.get(alert_key, 0)
        if (ts - last_alert) / 1_000_000 < self._config.alert_cooldown_ms:
            return

        self._alert_counter += 1
        alert = HealthAlert(
            alert_id=f"alert_{self._alert_counter}",
            component_name=component_name,
            severity=severity,
            message=message,
            timestamp=ts,
            details=details or {}
        )

        self._alerts.append(alert)
        self._alert_cooldowns[alert_key] = ts

        # Log based on severity
        if severity == AlertSeverity.CRITICAL:
            self._logger.error(f"HEALTH ALERT: {message}")
        elif severity == AlertSeverity.WARNING:
            self._logger.warning(f"Health warning: {message}")
        else:
            self._logger.info(f"Health info: {message}")

    def set_baseline_latency(self, component_name: str, latency_ms: float):
        """Set baseline latency for a component."""
        with self._lock:
            self._baseline_latencies[component_name] = latency_ms

    def check_resources(self, cpu_pct: float, memory_pct: float):
        """Check system resource usage."""
        ts = self._now_ns()

        with self._lock:
            # CPU alerts
            if cpu_pct > self._config.cpu_critical_pct:
                self._create_alert(
                    "system",
                    AlertSeverity.CRITICAL,
                    f"CPU critical: {cpu_pct:.1f}%",
                    ts,
                    {'cpu_pct': cpu_pct}
                )
            elif cpu_pct > self._config.cpu_warning_pct:
                self._create_alert(
                    "system",
                    AlertSeverity.WARNING,
                    f"CPU warning: {cpu_pct:.1f}%",
                    ts,
                    {'cpu_pct': cpu_pct}
                )

            # Memory alerts
            if memory_pct > self._config.memory_critical_pct:
                self._create_alert(
                    "system",
                    AlertSeverity.CRITICAL,
                    f"Memory critical: {memory_pct:.1f}%",
                    ts,
                    {'memory_pct': memory_pct}
                )
            elif memory_pct > self._config.memory_warning_pct:
                self._create_alert(
                    "system",
                    AlertSeverity.WARNING,
                    f"Memory warning: {memory_pct:.1f}%",
                    ts,
                    {'memory_pct': memory_pct}
                )

    def get_alerts(
        self,
        severity: AlertSeverity = None,
        unacknowledged_only: bool = False
    ) -> List[HealthAlert]:
        """Get alerts, optionally filtered."""
        with self._lock:
            alerts = list(self._alerts)

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        return alerts

    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    break

    def get_component_status(self, name: str) -> Optional[ComponentStatus]:
        """Get status of a specific component."""
        with self._lock:
            return self._components.get(name)

    def is_system_healthy(self) -> bool:
        """Check if overall system is healthy."""
        with self._lock:
            for status in self._components.values():
                if status.health == ComponentHealth.UNHEALTHY:
                    return False
            return True

    def get_unhealthy_components(self) -> List[str]:
        """Get list of unhealthy component names."""
        with self._lock:
            return [
                name for name, status in self._components.items()
                if status.health == ComponentHealth.UNHEALTHY
            ]

    def get_summary(self) -> Dict:
        """Get health summary for all components."""
        with self._lock:
            by_health = {}
            for health in ComponentHealth:
                by_health[health.name] = []

            for name, status in self._components.items():
                by_health[status.health.name].append(name)

            return {
                'total_components': len(self._components),
                'by_health': by_health,
                'unacknowledged_alerts': len([
                    a for a in self._alerts if not a.acknowledged
                ]),
                'is_healthy': self.is_system_healthy()
            }
