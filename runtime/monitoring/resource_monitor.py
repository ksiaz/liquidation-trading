"""
Resource Monitor - Memory and System Health Tracking

Lightweight monitoring to detect resource issues before OOM conditions.
Logs every 60 seconds with component-level memory estimates.

Usage:
    monitor = ResourceMonitor(warn_pct=70, critical_pct=85)
    monitor.register_component("collector", collector_service)
    await monitor.start()

Integration points:
    - CollectorService
    - PositionStateManager
    - OrganicFlowDetector
    - ObservationBridge
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """System health status levels."""
    HEALTHY = "HEALTHY"      # < 70% memory
    WARNING = "WARNING"      # 70-85% memory
    CRITICAL = "CRITICAL"    # > 85% memory
    UNKNOWN = "UNKNOWN"


@dataclass
class MemorySnapshot:
    """Point-in-time memory measurement."""
    timestamp: float
    rss_mb: float           # Resident Set Size (actual RAM used)
    vms_mb: float           # Virtual Memory Size
    heap_mb: float          # Python heap estimate
    percent: float          # % of system RAM
    available_mb: float     # Available system RAM


@dataclass
class ComponentMetrics:
    """Memory metrics for a registered component."""
    name: str
    estimated_mb: float
    item_count: int
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceReport:
    """Complete resource status report."""
    timestamp: float
    status: HealthStatus
    memory: MemorySnapshot
    components: List[ComponentMetrics]
    alerts: List[str]


def get_memory_snapshot() -> MemorySnapshot:
    """Get current memory usage snapshot."""
    import gc

    rss_mb = 0.0
    vms_mb = 0.0
    percent = 0.0
    available_mb = 0.0

    # Try psutil first (most accurate)
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        rss_mb = mem_info.rss / (1024 * 1024)
        vms_mb = mem_info.vms / (1024 * 1024)
        percent = process.memory_percent()
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
    except ImportError:
        # Fallback to /proc on Linux
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        rss_mb = int(line.split()[1]) / 1024
                    elif line.startswith('VmSize:'):
                        vms_mb = int(line.split()[1]) / 1024
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemAvailable:'):
                        available_mb = int(line.split()[1]) / 1024
                    elif line.startswith('MemTotal:'):
                        total_mb = int(line.split()[1]) / 1024
            if total_mb > 0:
                percent = (rss_mb / total_mb) * 100
        except Exception:
            pass

    # Estimate Python heap from gc
    gc.collect()
    heap_mb = 0.0
    try:
        # Sum sizes of tracked objects (rough estimate)
        for obj in gc.get_objects():
            try:
                heap_mb += sys.getsizeof(obj)
            except (TypeError, AttributeError):
                pass
        heap_mb /= (1024 * 1024)
    except Exception:
        heap_mb = rss_mb * 0.7  # Rough estimate

    return MemorySnapshot(
        timestamp=time.time(),
        rss_mb=rss_mb,
        vms_mb=vms_mb,
        heap_mb=min(heap_mb, rss_mb),  # Cap at RSS
        percent=percent,
        available_mb=available_mb,
    )


def estimate_dict_size(d: dict, sample_value_size: int = 100) -> int:
    """Estimate memory size of a dictionary."""
    if not d:
        return 0
    # Dict overhead + keys + estimated values
    base_size = sys.getsizeof(d)
    key_size = sum(sys.getsizeof(k) for k in list(d.keys())[:100])
    avg_key = key_size / min(len(d), 100)
    # Sample value sizes
    sample_values = list(d.values())[:10]
    if sample_values:
        try:
            avg_value = sum(sys.getsizeof(v) for v in sample_values) / len(sample_values)
        except TypeError:
            avg_value = sample_value_size
    else:
        avg_value = sample_value_size
    return int(base_size + len(d) * (avg_key + avg_value))


def estimate_list_size(lst: list, sample_item_size: int = 50) -> int:
    """Estimate memory size of a list."""
    if not lst:
        return 0
    base_size = sys.getsizeof(lst)
    sample = lst[:20]
    if sample:
        try:
            avg_item = sum(sys.getsizeof(item) for item in sample) / len(sample)
        except TypeError:
            avg_item = sample_item_size
    else:
        avg_item = sample_item_size
    return int(base_size + len(lst) * avg_item)


class ComponentSizer:
    """
    Extracts memory estimates from registered components.

    Each component should implement get_memory_estimate() or we use introspection.
    """

    @staticmethod
    def size_organic_flow_detector(detector) -> ComponentMetrics:
        """Size the OrganicFlowDetector component."""
        if detector is None:
            return ComponentMetrics("organic_flow_detector", 0.0, 0)

        windows = getattr(detector, '_windows', {})
        cascades = getattr(detector, '_cascade_directions', {})

        total_events = 0
        window_size = 0
        for symbol, window in windows.items():
            events = getattr(window, 'events', [])
            total_events += len(events)
            window_size += estimate_list_size(events)

        total_bytes = (
            estimate_dict_size(windows) +
            estimate_dict_size(cascades) +
            window_size
        )

        return ComponentMetrics(
            name="organic_flow_detector",
            estimated_mb=total_bytes / (1024 * 1024),
            item_count=len(windows),
            details={
                "symbols_tracked": len(windows),
                "active_cascades": len(cascades),
                "total_events": total_events,
            }
        )

    @staticmethod
    def size_position_state_manager(psm) -> ComponentMetrics:
        """Size the PositionStateManager component."""
        if psm is None:
            return ComponentMetrics("position_state_manager", 0.0, 0)

        cache = getattr(psm, '_cache', {})
        prices = getattr(psm, '_prices', {})
        by_tier = getattr(psm, '_by_tier', {})

        # Count positions
        position_count = sum(len(coins) for coins in cache.values())
        wallet_count = len(cache)

        # Estimate sizes
        cache_size = 0
        for wallet_positions in cache.values():
            cache_size += estimate_dict_size(wallet_positions, sample_value_size=500)

        tier_size = sum(
            sys.getsizeof(s) + len(s) * 60  # tuple overhead
            for s in by_tier.values()
        )

        total_bytes = (
            estimate_dict_size(cache) +
            cache_size +
            estimate_dict_size(prices) +
            tier_size
        )

        return ComponentMetrics(
            name="position_state_manager",
            estimated_mb=total_bytes / (1024 * 1024),
            item_count=position_count,
            details={
                "wallets": wallet_count,
                "positions": position_count,
                "prices_tracked": len(prices),
                "tier_entries": sum(len(s) for s in by_tier.values()),
            }
        )

    @staticmethod
    def size_collector_service(service) -> ComponentMetrics:
        """Size the CollectorService calculators."""
        if service is None:
            return ComponentMetrics("collector_service", 0.0, 0)

        vwap = getattr(service, '_vwap_calculators', {})
        atr = getattr(service, '_atr_calculators', {})
        orderflow = getattr(service, '_orderflow_calculators', {})
        liq_calc = getattr(service, '_liquidation_calculators', {})
        prices = getattr(service, '_current_prices', {})
        regimes = getattr(service, '_regime_states', {})

        # Rough size estimates per calculator type
        vwap_size = len(vwap) * 10_000  # ~10KB per VWAP calculator
        atr_size = len(atr) * 20_000    # ~20KB per ATR calculator
        orderflow_size = len(orderflow) * 15_000  # ~15KB per orderflow
        liq_size = len(liq_calc) * 5_000  # ~5KB per liq calculator

        total_bytes = (
            vwap_size + atr_size + orderflow_size + liq_size +
            estimate_dict_size(prices) +
            estimate_dict_size(regimes, sample_value_size=100)
        )

        return ComponentMetrics(
            name="collector_service",
            estimated_mb=total_bytes / (1024 * 1024),
            item_count=len(vwap),
            details={
                "vwap_calculators": len(vwap),
                "atr_calculators": len(atr),
                "orderflow_calculators": len(orderflow),
                "liquidation_calculators": len(liq_calc),
                "prices_tracked": len(prices),
                "regime_states": len(regimes),
            }
        )

    @staticmethod
    def size_observation_bridge(bridge) -> ComponentMetrics:
        """Size the ObservationBridge burst aggregator."""
        if bridge is None:
            return ComponentMetrics("observation_bridge", 0.0, 0)

        aggregator = getattr(bridge, '_burst_aggregator', None)
        if aggregator is None:
            return ComponentMetrics("observation_bridge", 0.0, 0)

        events = getattr(aggregator, '_events', {})

        total_events = sum(len(lst) for lst in events.values())
        events_size = sum(estimate_list_size(lst) for lst in events.values())

        total_bytes = estimate_dict_size(events) + events_size

        return ComponentMetrics(
            name="observation_bridge",
            estimated_mb=total_bytes / (1024 * 1024),
            item_count=len(events),
            details={
                "symbols_tracked": len(events),
                "total_events": total_events,
            }
        )

    @staticmethod
    def size_cascade_state_machine(sm) -> ComponentMetrics:
        """Size the CascadeStateMachine."""
        if sm is None:
            return ComponentMetrics("cascade_state_machine", 0.0, 0)

        states = getattr(sm, '_states', {})
        primed = getattr(sm, '_primed_data', {})
        triggered = getattr(sm, '_triggered_at', {})
        absorption = getattr(sm, '_absorption_data', {})
        signals = getattr(sm, '_last_absorption_signal', {})

        # Also check organic detector within state machine
        organic = getattr(sm, '_organic_detector', None)
        organic_metrics = ComponentSizer.size_organic_flow_detector(organic)

        total_bytes = (
            estimate_dict_size(states) +
            estimate_dict_size(primed, sample_value_size=200) +
            estimate_dict_size(triggered) +
            estimate_dict_size(absorption, sample_value_size=200) +
            estimate_dict_size(signals, sample_value_size=300) +
            int(organic_metrics.estimated_mb * 1024 * 1024)
        )

        return ComponentMetrics(
            name="cascade_state_machine",
            estimated_mb=total_bytes / (1024 * 1024),
            item_count=len(states),
            details={
                "symbols_tracked": len(states),
                "primed_symbols": len(primed),
                "triggered_symbols": len(triggered),
                "organic_detector": organic_metrics.details,
            }
        )


class ResourceMonitor:
    """
    Central resource monitoring with alerting.

    Tracks memory usage and component sizes, logs regularly,
    and alerts when thresholds are exceeded.
    """

    def __init__(
        self,
        warn_pct: float = 70.0,
        critical_pct: float = 85.0,
        log_interval_sec: float = 60.0,
        enable_gc_on_warning: bool = True,
    ):
        self._warn_pct = warn_pct
        self._critical_pct = critical_pct
        self._log_interval = log_interval_sec
        self._enable_gc_on_warning = enable_gc_on_warning

        # Registered components
        self._components: Dict[str, Any] = {}
        self._sizers: Dict[str, Callable] = {}

        # History for trend detection
        self._history: List[ResourceReport] = []
        self._max_history = 60  # Keep 1 hour at 60s intervals

        # Callbacks
        self._on_warning: Optional[Callable] = None
        self._on_critical: Optional[Callable] = None

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Register default sizers
        self._register_default_sizers()

    def _register_default_sizers(self):
        """Register built-in component sizers."""
        self._sizers['organic_flow_detector'] = ComponentSizer.size_organic_flow_detector
        self._sizers['position_state_manager'] = ComponentSizer.size_position_state_manager
        self._sizers['collector_service'] = ComponentSizer.size_collector_service
        self._sizers['observation_bridge'] = ComponentSizer.size_observation_bridge
        self._sizers['cascade_state_machine'] = ComponentSizer.size_cascade_state_machine

    def register_component(self, name: str, component: Any, sizer: Optional[Callable] = None):
        """
        Register a component for monitoring.

        Args:
            name: Component identifier
            component: The component instance
            sizer: Optional custom sizing function(component) -> ComponentMetrics
        """
        self._components[name] = component
        if sizer:
            self._sizers[name] = sizer

    def set_warning_callback(self, callback: Callable[[ResourceReport], None]):
        """Set callback for warning threshold."""
        self._on_warning = callback

    def set_critical_callback(self, callback: Callable[[ResourceReport], None]):
        """Set callback for critical threshold."""
        self._on_critical = callback

    def get_report(self) -> ResourceReport:
        """Generate current resource report."""
        memory = get_memory_snapshot()

        # Determine status
        if memory.percent >= self._critical_pct:
            status = HealthStatus.CRITICAL
        elif memory.percent >= self._warn_pct:
            status = HealthStatus.WARNING
        elif memory.percent > 0:
            status = HealthStatus.HEALTHY
        else:
            status = HealthStatus.UNKNOWN

        # Size components
        components = []
        for name, component in self._components.items():
            sizer = self._sizers.get(name)
            if sizer:
                try:
                    metrics = sizer(component)
                    components.append(metrics)
                except Exception as e:
                    logger.debug(f"Failed to size {name}: {e}")
                    components.append(ComponentMetrics(name, 0.0, 0, {"error": str(e)}))

        # Generate alerts
        alerts = []
        if status == HealthStatus.WARNING:
            alerts.append(f"Memory usage at {memory.percent:.1f}% (warn threshold: {self._warn_pct}%)")
        elif status == HealthStatus.CRITICAL:
            alerts.append(f"CRITICAL: Memory usage at {memory.percent:.1f}% (critical threshold: {self._critical_pct}%)")

        # Check for rapid growth
        if len(self._history) >= 5:
            recent = self._history[-5:]
            growth_rate = (memory.rss_mb - recent[0].memory.rss_mb) / 5  # MB per minute
            if growth_rate > 10:  # >10 MB/min
                alerts.append(f"Rapid memory growth: {growth_rate:.1f} MB/min")

        return ResourceReport(
            timestamp=memory.timestamp,
            status=status,
            memory=memory,
            components=components,
            alerts=alerts,
        )

    def _log_report(self, report: ResourceReport):
        """Log resource report."""
        # Summary line
        component_summary = ", ".join(
            f"{c.name}={c.estimated_mb:.1f}MB({c.item_count})"
            for c in report.components
        )

        log_msg = (
            f"[RESOURCES] {report.status.value} | "
            f"RSS={report.memory.rss_mb:.1f}MB ({report.memory.percent:.1f}%) | "
            f"Available={report.memory.available_mb:.0f}MB | "
            f"Components: {component_summary}"
        )

        if report.status == HealthStatus.CRITICAL:
            logger.error(log_msg)
        elif report.status == HealthStatus.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Log alerts
        for alert in report.alerts:
            logger.warning(f"[RESOURCE ALERT] {alert}")

        # Log component details at debug level
        for comp in report.components:
            if comp.details:
                logger.debug(f"[RESOURCES] {comp.name} details: {comp.details}")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        logger.info(f"[RESOURCES] Monitor started (warn={self._warn_pct}%, critical={self._critical_pct}%)")

        while self._running:
            try:
                report = self.get_report()

                # Log
                self._log_report(report)

                # Store history
                self._history.append(report)
                if len(self._history) > self._max_history:
                    self._history.pop(0)

                # Trigger callbacks
                if report.status == HealthStatus.CRITICAL:
                    if self._on_critical:
                        try:
                            self._on_critical(report)
                        except Exception as e:
                            logger.error(f"Critical callback failed: {e}")

                    # Force GC on critical
                    if self._enable_gc_on_warning:
                        import gc
                        gc.collect()
                        logger.warning("[RESOURCES] Forced garbage collection on CRITICAL status")

                elif report.status == HealthStatus.WARNING:
                    if self._on_warning:
                        try:
                            self._on_warning(report)
                        except Exception as e:
                            logger.error(f"Warning callback failed: {e}")

                    # Trigger GC on warning
                    if self._enable_gc_on_warning:
                        import gc
                        gc.collect()

            except Exception as e:
                logger.error(f"[RESOURCES] Monitor error: {e}")

            await asyncio.sleep(self._log_interval)

    async def start(self):
        """Start the monitoring loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[RESOURCES] Monitor stopped")

    def get_history(self) -> List[ResourceReport]:
        """Get historical reports."""
        return list(self._history)

    def get_trend(self) -> Dict[str, float]:
        """Get memory trend statistics."""
        if len(self._history) < 2:
            return {"growth_rate_mb_per_min": 0.0, "samples": len(self._history)}

        first = self._history[0]
        last = self._history[-1]
        duration_min = (last.timestamp - first.timestamp) / 60

        if duration_min > 0:
            growth_rate = (last.memory.rss_mb - first.memory.rss_mb) / duration_min
        else:
            growth_rate = 0.0

        return {
            "growth_rate_mb_per_min": growth_rate,
            "samples": len(self._history),
            "duration_min": duration_min,
            "start_mb": first.memory.rss_mb,
            "current_mb": last.memory.rss_mb,
        }


# Singleton instance for easy access
_monitor: Optional[ResourceMonitor] = None


def get_monitor() -> ResourceMonitor:
    """Get or create the global resource monitor."""
    global _monitor
    if _monitor is None:
        _monitor = ResourceMonitor()
    return _monitor


def reset_monitor():
    """Reset the global monitor (for testing)."""
    global _monitor
    _monitor = None
