"""
HLP19: Metrics Collector.

Collects and stores system metrics:
- Health metrics (data staleness, heartbeats, connections)
- Operational metrics (CPU, memory, latency)
- Business metrics (capital, exposure)
"""

import time
import logging
import psutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from threading import RLock
from collections import deque

from .types import MetricValue, MetricCategory


@dataclass
class MetricsConfig:
    """Configuration for metrics collection."""
    # Health thresholds
    data_staleness_warning_ms: int = 500
    data_staleness_critical_ms: int = 1000
    heartbeat_timeout_ms: int = 3000

    # Resource thresholds
    cpu_warning_pct: float = 70.0
    cpu_critical_pct: float = 90.0
    memory_warning_pct: float = 75.0
    memory_critical_pct: float = 85.0

    # Latency thresholds
    latency_warning_ms: float = 10.0
    latency_critical_ms: float = 50.0

    # Storage
    max_metrics_per_name: int = 1000  # Keep in memory


class MetricsCollector:
    """
    Collects and stores system metrics.

    Categories:
    - HEALTH: Data freshness, component status
    - OPERATIONAL: CPU, memory, disk, network
    - PERFORMANCE: Latency, throughput
    - BUSINESS: Capital, exposure
    """

    def __init__(
        self,
        config: MetricsConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or MetricsConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Metric storage: name -> deque of values
        self._metrics: Dict[str, deque] = {}

        # Component heartbeats: component -> last heartbeat ns
        self._heartbeats: Dict[str, int] = {}

        # Data timestamps: source -> last update ns
        self._data_timestamps: Dict[str, int] = {}

        # Latency tracking
        self._latencies: Dict[str, deque] = {}

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def record(
        self,
        name: str,
        value: float,
        category: MetricCategory,
        tags: Dict[str, str] = None,
        unit: str = ""
    ):
        """
        Record a metric value.

        Args:
            name: Metric name
            value: Metric value
            category: Metric category
            tags: Optional tags (e.g., symbol, strategy)
            unit: Unit of measurement
        """
        metric = MetricValue(
            name=name,
            value=value,
            category=category,
            timestamp_ns=self._now_ns(),
            tags=tags or {},
            unit=unit
        )

        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = deque(maxlen=self._config.max_metrics_per_name)
            self._metrics[name].append(metric)

    def record_heartbeat(self, component: str):
        """Record component heartbeat."""
        with self._lock:
            self._heartbeats[component] = self._now_ns()

    def record_data_update(self, source: str):
        """Record data source update timestamp."""
        with self._lock:
            self._data_timestamps[source] = self._now_ns()

    def record_latency(self, name: str, latency_ms: float):
        """Record a latency measurement."""
        with self._lock:
            if name not in self._latencies:
                self._latencies[name] = deque(maxlen=1000)
            self._latencies[name].append(latency_ms)

        self.record(
            name=f"latency_{name}",
            value=latency_ms,
            category=MetricCategory.OPERATIONAL,
            unit="ms"
        )

    def get_data_staleness_ms(self, source: str) -> float:
        """Get data staleness for a source in milliseconds."""
        with self._lock:
            if source not in self._data_timestamps:
                return float('inf')
            age_ns = self._now_ns() - self._data_timestamps[source]
            return age_ns / 1_000_000

    def get_heartbeat_age_ms(self, component: str) -> float:
        """Get heartbeat age for a component in milliseconds."""
        with self._lock:
            if component not in self._heartbeats:
                return float('inf')
            age_ns = self._now_ns() - self._heartbeats[component]
            return age_ns / 1_000_000

    def check_component_health(self, component: str) -> str:
        """Check health status of a component."""
        age_ms = self.get_heartbeat_age_ms(component)
        if age_ms == float('inf'):
            return "UNKNOWN"
        elif age_ms > self._config.heartbeat_timeout_ms:
            return "UNHEALTHY"
        else:
            return "HEALTHY"

    def check_data_health(self, source: str) -> str:
        """Check health status of a data source."""
        staleness = self.get_data_staleness_ms(source)
        if staleness == float('inf'):
            return "UNKNOWN"
        elif staleness > self._config.data_staleness_critical_ms:
            return "CRITICAL"
        elif staleness > self._config.data_staleness_warning_ms:
            return "WARNING"
        else:
            return "HEALTHY"

    def collect_system_metrics(self):
        """Collect current system resource metrics."""
        try:
            # CPU
            cpu_pct = psutil.cpu_percent(interval=0.1)
            self.record(
                name="cpu_usage",
                value=cpu_pct,
                category=MetricCategory.OPERATIONAL,
                unit="%"
            )

            # Memory
            memory = psutil.virtual_memory()
            self.record(
                name="memory_usage",
                value=memory.percent,
                category=MetricCategory.OPERATIONAL,
                unit="%"
            )
            self.record(
                name="memory_available_mb",
                value=memory.available / (1024 * 1024),
                category=MetricCategory.OPERATIONAL,
                unit="MB"
            )

            # Disk
            disk = psutil.disk_usage('/')
            self.record(
                name="disk_usage",
                value=disk.percent,
                category=MetricCategory.OPERATIONAL,
                unit="%"
            )

        except Exception as e:
            self._logger.debug(f"System metrics collection error: {e}")

    def get_cpu_usage(self) -> float:
        """Get current CPU usage."""
        try:
            return psutil.cpu_percent(interval=0.1)
        except:
            return 0.0

    def get_memory_usage(self) -> float:
        """Get current memory usage percentage."""
        try:
            return psutil.virtual_memory().percent
        except:
            return 0.0

    def get_latency_stats(self, name: str) -> Dict:
        """Get latency statistics for a metric."""
        with self._lock:
            if name not in self._latencies or not self._latencies[name]:
                return {'p50': 0, 'p95': 0, 'p99': 0, 'max': 0, 'avg': 0}

            values = sorted(self._latencies[name])
            n = len(values)

            return {
                'p50': values[int(n * 0.50)] if n > 0 else 0,
                'p95': values[int(n * 0.95)] if n > 1 else values[-1],
                'p99': values[int(n * 0.99)] if n > 1 else values[-1],
                'max': values[-1],
                'avg': sum(values) / n,
                'count': n,
            }

    def get_metric_history(
        self,
        name: str,
        limit: int = 100
    ) -> List[MetricValue]:
        """Get historical values for a metric."""
        with self._lock:
            if name not in self._metrics:
                return []
            values = list(self._metrics[name])
            return values[-limit:]

    def get_latest(self, name: str) -> Optional[MetricValue]:
        """Get latest value for a metric."""
        with self._lock:
            if name not in self._metrics or not self._metrics[name]:
                return None
            return self._metrics[name][-1]

    def get_all_components(self) -> Dict[str, str]:
        """Get health status of all components."""
        with self._lock:
            return {
                component: self.check_component_health(component)
                for component in self._heartbeats
            }

    def get_all_data_sources(self) -> Dict[str, str]:
        """Get health status of all data sources."""
        with self._lock:
            return {
                source: self.check_data_health(source)
                for source in self._data_timestamps
            }

    def get_health_summary(self) -> Dict:
        """Get overall health summary."""
        components = self.get_all_components()
        data_sources = self.get_all_data_sources()

        unhealthy_components = [c for c, s in components.items() if s != "HEALTHY"]
        unhealthy_sources = [s for s, status in data_sources.items() if status != "HEALTHY"]

        cpu = self.get_cpu_usage()
        memory = self.get_memory_usage()

        resource_status = "HEALTHY"
        if cpu > self._config.cpu_critical_pct or memory > self._config.memory_critical_pct:
            resource_status = "CRITICAL"
        elif cpu > self._config.cpu_warning_pct or memory > self._config.memory_warning_pct:
            resource_status = "WARNING"

        overall = "HEALTHY"
        if unhealthy_components or unhealthy_sources or resource_status == "CRITICAL":
            overall = "UNHEALTHY"
        elif resource_status == "WARNING":
            overall = "DEGRADED"

        return {
            'overall': overall,
            'components': components,
            'data_sources': data_sources,
            'unhealthy_components': unhealthy_components,
            'unhealthy_sources': unhealthy_sources,
            'cpu_pct': cpu,
            'memory_pct': memory,
            'resource_status': resource_status,
        }

    def check_resource_thresholds(self) -> Dict[str, str]:
        """Check resource metrics against thresholds."""
        issues = {}

        cpu = self.get_cpu_usage()
        memory = self.get_memory_usage()

        if cpu > self._config.cpu_critical_pct:
            issues['cpu'] = 'CRITICAL'
        elif cpu > self._config.cpu_warning_pct:
            issues['cpu'] = 'WARNING'

        if memory > self._config.memory_critical_pct:
            issues['memory'] = 'CRITICAL'
        elif memory > self._config.memory_warning_pct:
            issues['memory'] = 'WARNING'

        return issues
