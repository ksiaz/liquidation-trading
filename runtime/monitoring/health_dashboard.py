"""
HLP19: Health Dashboard.

Real-time system health monitoring with thresholds and alerting.

Monitors:
- Data staleness (time since last market update)
- Component heartbeats (are all components alive)
- Event registry status (active/stale events)
- Position reconciliation (local vs exchange)
- Stop order status (are stops active)
- WebSocket connection status
- Memory and CPU usage

Thresholds:
- Normal: All metrics within bounds
- Warning: Some metrics degraded
- Critical: Trading should be halted
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Any, Callable


class HealthLevel(Enum):
    """System health level."""
    NORMAL = 0
    WARNING = 1
    CRITICAL = 2

    def __lt__(self, other):
        if isinstance(other, HealthLevel):
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, HealthLevel):
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, HealthLevel):
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, HealthLevel):
            return self.value >= other.value
        return NotImplemented


@dataclass
class HealthThresholds:
    """Thresholds for health monitoring."""
    # Data staleness
    data_staleness_normal_ms: int = 500
    data_staleness_warning_ms: int = 1000
    data_staleness_critical_ms: int = 2000

    # Component heartbeat
    heartbeat_warning_sec: int = 3
    heartbeat_critical_sec: int = 10

    # Event registry
    max_active_events: int = 100
    max_stale_events: int = 50

    # Memory
    memory_warning_pct: float = 0.70
    memory_critical_pct: float = 0.85

    # CPU
    cpu_warning_pct: float = 0.70
    cpu_critical_pct: float = 0.90

    # Latency
    order_latency_warning_ms: int = 100
    order_latency_critical_ms: int = 500


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    level: HealthLevel
    last_heartbeat: datetime
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_alive(self) -> bool:
        """Check if component has heartbeat within threshold."""
        age = (datetime.now() - self.last_heartbeat).total_seconds()
        return age < 10  # 10 second default


@dataclass
class HealthStatus:
    """Complete health status snapshot."""
    timestamp: datetime
    overall_level: HealthLevel
    trading_allowed: bool

    # Individual checks
    data_staleness_ms: int
    websocket_connected: bool
    position_reconciled: bool
    stops_active: bool

    # Component health
    components: Dict[str, ComponentHealth] = field(default_factory=dict)

    # Event registry
    active_events: int = 0
    stale_events: int = 0

    # Resource usage
    memory_pct: float = 0.0
    cpu_pct: float = 0.0

    # Issues
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'overall_level': self.overall_level.name,
            'trading_allowed': self.trading_allowed,
            'data_staleness_ms': self.data_staleness_ms,
            'websocket_connected': self.websocket_connected,
            'position_reconciled': self.position_reconciled,
            'stops_active': self.stops_active,
            'active_events': self.active_events,
            'stale_events': self.stale_events,
            'memory_pct': self.memory_pct,
            'cpu_pct': self.cpu_pct,
            'issues': self.issues,
            'components': {
                name: {
                    'level': c.level.name,
                    'last_heartbeat': c.last_heartbeat.isoformat(),
                    'message': c.message,
                }
                for name, c in self.components.items()
            },
        }


class HealthDashboard:
    """
    Real-time system health monitoring.

    Aggregates health from all system components and determines
    if trading should continue.
    """

    def __init__(
        self,
        thresholds: HealthThresholds = None,
        logger: logging.Logger = None,
    ):
        self._thresholds = thresholds or HealthThresholds()
        self._logger = logger or logging.getLogger(__name__)

        # Component tracking
        self._components: Dict[str, ComponentHealth] = {}
        self._lock = asyncio.Lock()

        # Data tracking
        self._last_market_data_time: datetime = datetime.now()
        self._websocket_connected: bool = False
        self._position_reconciled: bool = True
        self._stops_active: bool = True

        # Event tracking
        self._active_events: int = 0
        self._stale_events: int = 0

        # Resource tracking
        self._memory_pct: float = 0.0
        self._cpu_pct: float = 0.0

        # Alert callbacks
        self._alert_callbacks: List[Callable] = []

    async def register_component(self, name: str):
        """Register a component for health tracking."""
        async with self._lock:
            self._components[name] = ComponentHealth(
                name=name,
                level=HealthLevel.NORMAL,
                last_heartbeat=datetime.now(),
            )
            self._logger.debug(f"Registered component: {name}")

    async def heartbeat(self, component_name: str, metrics: Dict[str, Any] = None):
        """Record heartbeat from a component."""
        async with self._lock:
            if component_name in self._components:
                comp = self._components[component_name]
                comp.last_heartbeat = datetime.now()
                comp.level = HealthLevel.NORMAL
                if metrics:
                    comp.metrics = metrics

    async def report_issue(self, component_name: str, message: str, level: HealthLevel = HealthLevel.WARNING):
        """Report an issue from a component."""
        async with self._lock:
            if component_name in self._components:
                comp = self._components[component_name]
                comp.level = level
                comp.message = message
                self._logger.warning(f"Health issue from {component_name}: {message}")

    def update_market_data_time(self, timestamp: datetime = None):
        """Update last market data timestamp."""
        self._last_market_data_time = timestamp or datetime.now()

    def set_websocket_status(self, connected: bool):
        """Update WebSocket connection status."""
        old = self._websocket_connected
        self._websocket_connected = connected
        if old and not connected:
            self._logger.warning("WebSocket disconnected")
        elif not old and connected:
            self._logger.info("WebSocket connected")

    def set_position_reconciled(self, reconciled: bool):
        """Update position reconciliation status."""
        self._position_reconciled = reconciled

    def set_stops_active(self, active: bool):
        """Update stop orders status."""
        self._stops_active = active

    def update_event_counts(self, active: int, stale: int):
        """Update event registry counts."""
        self._active_events = active
        self._stale_events = stale

    def update_resource_usage(self, memory_pct: float, cpu_pct: float):
        """Update resource usage metrics."""
        self._memory_pct = memory_pct
        self._cpu_pct = cpu_pct

    async def get_status(self) -> HealthStatus:
        """
        Get current health status.

        Evaluates all health checks and returns comprehensive status.
        """
        async with self._lock:
            issues = []
            overall_level = HealthLevel.NORMAL

            # Check data staleness
            data_staleness_ms = int(
                (datetime.now() - self._last_market_data_time).total_seconds() * 1000
            )

            if data_staleness_ms > self._thresholds.data_staleness_critical_ms:
                issues.append(f"Data stale: {data_staleness_ms}ms")
                overall_level = HealthLevel.CRITICAL
            elif data_staleness_ms > self._thresholds.data_staleness_warning_ms:
                issues.append(f"Data delayed: {data_staleness_ms}ms")
                overall_level = max(overall_level, HealthLevel.WARNING)

            # Check WebSocket
            if not self._websocket_connected:
                issues.append("WebSocket disconnected")
                overall_level = HealthLevel.CRITICAL

            # Check position reconciliation
            if not self._position_reconciled:
                issues.append("Position mismatch with exchange")
                overall_level = HealthLevel.CRITICAL

            # Check stops
            if not self._stops_active:
                issues.append("Stop orders not active")
                overall_level = max(overall_level, HealthLevel.WARNING)

            # Check component heartbeats
            now = datetime.now()
            for name, comp in self._components.items():
                age = (now - comp.last_heartbeat).total_seconds()

                if age > self._thresholds.heartbeat_critical_sec:
                    issues.append(f"Component {name} unresponsive")
                    comp.level = HealthLevel.CRITICAL
                    overall_level = HealthLevel.CRITICAL
                elif age > self._thresholds.heartbeat_warning_sec:
                    issues.append(f"Component {name} slow")
                    comp.level = HealthLevel.WARNING
                    overall_level = max(overall_level, HealthLevel.WARNING)

                # Check component's own reported level
                if comp.level == HealthLevel.CRITICAL:
                    overall_level = HealthLevel.CRITICAL
                elif comp.level == HealthLevel.WARNING:
                    overall_level = max(overall_level, HealthLevel.WARNING)

            # Check event counts
            if self._stale_events > self._thresholds.max_stale_events:
                issues.append(f"Too many stale events: {self._stale_events}")
                overall_level = max(overall_level, HealthLevel.WARNING)

            if self._active_events > self._thresholds.max_active_events:
                issues.append(f"Too many active events: {self._active_events}")
                overall_level = max(overall_level, HealthLevel.WARNING)

            # Check resources
            if self._memory_pct > self._thresholds.memory_critical_pct:
                issues.append(f"Memory critical: {self._memory_pct:.0%}")
                overall_level = HealthLevel.CRITICAL
            elif self._memory_pct > self._thresholds.memory_warning_pct:
                issues.append(f"Memory high: {self._memory_pct:.0%}")
                overall_level = max(overall_level, HealthLevel.WARNING)

            if self._cpu_pct > self._thresholds.cpu_critical_pct:
                issues.append(f"CPU critical: {self._cpu_pct:.0%}")
                overall_level = HealthLevel.CRITICAL
            elif self._cpu_pct > self._thresholds.cpu_warning_pct:
                issues.append(f"CPU high: {self._cpu_pct:.0%}")
                overall_level = max(overall_level, HealthLevel.WARNING)

            # Determine if trading allowed
            trading_allowed = (
                overall_level != HealthLevel.CRITICAL and
                self._websocket_connected and
                self._position_reconciled
            )

            status = HealthStatus(
                timestamp=datetime.now(),
                overall_level=overall_level,
                trading_allowed=trading_allowed,
                data_staleness_ms=data_staleness_ms,
                websocket_connected=self._websocket_connected,
                position_reconciled=self._position_reconciled,
                stops_active=self._stops_active,
                components=self._components.copy(),
                active_events=self._active_events,
                stale_events=self._stale_events,
                memory_pct=self._memory_pct,
                cpu_pct=self._cpu_pct,
                issues=issues,
            )

            # Trigger alerts if needed
            if overall_level == HealthLevel.CRITICAL:
                await self._trigger_alerts(status)

            return status

    def add_alert_callback(self, callback: Callable):
        """Add callback for health alerts."""
        self._alert_callbacks.append(callback)

    async def _trigger_alerts(self, status: HealthStatus):
        """Trigger alert callbacks."""
        for callback in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(status)
                else:
                    callback(status)
            except Exception as e:
                self._logger.error(f"Alert callback failed: {e}")

    def is_trading_allowed(self) -> bool:
        """Quick check if trading is allowed."""
        return (
            self._websocket_connected and
            self._position_reconciled and
            (datetime.now() - self._last_market_data_time).total_seconds() * 1000
            < self._thresholds.data_staleness_critical_ms
        )
