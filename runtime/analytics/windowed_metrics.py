"""
Time-windowed metrics collection.

Tracks metric values within configurable time windows for
latency instrumentation and decay detection.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TimeWindow:
    """Definition of a time window."""
    name: str
    duration_ns: int


# Standard time windows for metrics collection
STANDARD_WINDOWS = (
    TimeWindow("1min", 60 * 1_000_000_000),
    TimeWindow("5min", 5 * 60 * 1_000_000_000),
    TimeWindow("15min", 15 * 60 * 1_000_000_000),
    TimeWindow("1hour", 60 * 60 * 1_000_000_000),
    TimeWindow("24hour", 24 * 60 * 60 * 1_000_000_000),
)


@dataclass(frozen=True)
class PercentileStats:
    """Statistics computed from a time window."""
    window_name: str
    sample_count: int
    mean: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    p95: Optional[float]
    p99: Optional[float]
    max_value: Optional[float]
    min_value: Optional[float]


class WindowedMetric:
    """Tracks metric values within a single time window."""

    def __init__(self, window: TimeWindow, max_samples: int = 10000):
        self._window = window
        self._max_samples = max_samples
        self._values: deque = deque(maxlen=max_samples)
        self._lock = RLock()

    @property
    def window(self) -> TimeWindow:
        return self._window

    def add(self, ts_ns: int, value: float) -> None:
        """Add a value with timestamp."""
        with self._lock:
            self._values.append((ts_ns, value))

    def prune_expired(self, now_ns: int) -> int:
        """Remove values older than window duration. Returns count removed."""
        cutoff = now_ns - self._window.duration_ns
        removed = 0
        with self._lock:
            while self._values and self._values[0][0] < cutoff:
                self._values.popleft()
                removed += 1
        return removed

    def get_values(self, now_ns: int) -> List[float]:
        """Get all values within the window, pruning expired first."""
        self.prune_expired(now_ns)
        with self._lock:
            return [v for _, v in self._values]

    def count(self, now_ns: int) -> int:
        """Get count of values within the window."""
        self.prune_expired(now_ns)
        with self._lock:
            return len(self._values)

    def percentile(self, p: int, now_ns: int) -> Optional[float]:
        """Compute percentile of values within the window."""
        values = self.get_values(now_ns)
        if not values:
            return None
        sorted_values = sorted(values)
        n = len(sorted_values)
        idx = int(n * p / 100)
        idx = min(idx, n - 1)
        return sorted_values[idx]

    def mean(self, now_ns: int) -> Optional[float]:
        """Compute mean of values within the window."""
        values = self.get_values(now_ns)
        if not values:
            return None
        return sum(values) / len(values)

    def compute_stats(self, now_ns: int) -> PercentileStats:
        """Compute full statistics for the window."""
        values = self.get_values(now_ns)
        if not values:
            return PercentileStats(
                window_name=self._window.name,
                sample_count=0,
                mean=None,
                p50=None,
                p75=None,
                p95=None,
                p99=None,
                max_value=None,
                min_value=None,
            )

        sorted_values = sorted(values)
        n = len(sorted_values)

        def pct(p: int) -> float:
            idx = int(n * p / 100)
            idx = min(idx, n - 1)
            return sorted_values[idx]

        return PercentileStats(
            window_name=self._window.name,
            sample_count=n,
            mean=sum(values) / n,
            p50=pct(50),
            p75=pct(75),
            p95=pct(95),
            p99=pct(99),
            max_value=sorted_values[-1],
            min_value=sorted_values[0],
        )


class WindowedMetricsCollector:
    """
    Collects metrics across multiple time windows.

    Each metric is tracked in all configured windows simultaneously.
    """

    def __init__(
        self,
        windows: Tuple[TimeWindow, ...] = STANDARD_WINDOWS,
        max_samples_per_window: int = 10000,
    ):
        self._windows = windows
        self._max_samples = max_samples_per_window
        # metric_name -> window_name -> WindowedMetric
        self._metrics: Dict[str, Dict[str, WindowedMetric]] = {}
        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _ensure_metric(self, name: str) -> Dict[str, WindowedMetric]:
        """Ensure metric storage exists for all windows."""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = {
                    w.name: WindowedMetric(w, self._max_samples)
                    for w in self._windows
                }
            return self._metrics[name]

    def record(self, name: str, value: float, ts_ns: int = None) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name (e.g., "detection_to_fill_latency_ns")
            value: Metric value
            ts_ns: Timestamp in nanoseconds (uses current time if None)
        """
        if ts_ns is None:
            ts_ns = self._now_ns()

        windows = self._ensure_metric(name)
        for window_metric in windows.values():
            window_metric.add(ts_ns, value)

    def get_stats(
        self,
        name: str,
        window_name: str,
        now_ns: int = None,
    ) -> Optional[PercentileStats]:
        """
        Get statistics for a metric in a specific window.

        Args:
            name: Metric name
            window_name: Window name (e.g., "1min", "5min")
            now_ns: Current timestamp (uses current time if None)

        Returns:
            PercentileStats or None if metric doesn't exist
        """
        if now_ns is None:
            now_ns = self._now_ns()

        with self._lock:
            if name not in self._metrics:
                return None
            if window_name not in self._metrics[name]:
                return None
            return self._metrics[name][window_name].compute_stats(now_ns)

    def get_all_window_stats(
        self,
        name: str,
        now_ns: int = None,
    ) -> Dict[str, PercentileStats]:
        """
        Get statistics for a metric across all windows.

        Args:
            name: Metric name
            now_ns: Current timestamp

        Returns:
            Dict mapping window_name to PercentileStats
        """
        if now_ns is None:
            now_ns = self._now_ns()

        result = {}
        with self._lock:
            if name not in self._metrics:
                return result
            for window_name, window_metric in self._metrics[name].items():
                result[window_name] = window_metric.compute_stats(now_ns)
        return result

    def get_metric_names(self) -> List[str]:
        """Get list of all tracked metric names."""
        with self._lock:
            return list(self._metrics.keys())

    def get_value(
        self,
        name: str,
        window_name: str,
        stat: str,
        now_ns: int = None,
    ) -> Optional[float]:
        """
        Get a specific statistic value.

        Args:
            name: Metric name
            window_name: Window name
            stat: Statistic name ("mean", "p50", "p75", "p95", "p99", "max_value")
            now_ns: Current timestamp

        Returns:
            Value or None
        """
        stats = self.get_stats(name, window_name, now_ns)
        if stats is None:
            return None
        return getattr(stats, stat, None)

    def compare_windows(
        self,
        name: str,
        recent_window: str,
        baseline_window: str,
        stat: str = "mean",
        now_ns: int = None,
    ) -> Optional[Tuple[float, float, float]]:
        """
        Compare a metric between two windows.

        Args:
            name: Metric name
            recent_window: Recent window name (e.g., "1hour")
            baseline_window: Baseline window name (e.g., "24hour")
            stat: Statistic to compare ("mean", "p50", "p95", etc.)
            now_ns: Current timestamp

        Returns:
            Tuple of (recent_value, baseline_value, change_pct) or None
        """
        recent_val = self.get_value(name, recent_window, stat, now_ns)
        baseline_val = self.get_value(name, baseline_window, stat, now_ns)

        if recent_val is None or baseline_val is None:
            return None
        if baseline_val == 0:
            return None

        change_pct = ((recent_val - baseline_val) / abs(baseline_val)) * 100
        return (recent_val, baseline_val, change_pct)

    def prune_all(self, now_ns: int = None) -> int:
        """
        Prune expired values from all metrics.

        Returns:
            Total count of values removed
        """
        if now_ns is None:
            now_ns = self._now_ns()

        total_removed = 0
        with self._lock:
            for windows in self._metrics.values():
                for window_metric in windows.values():
                    total_removed += window_metric.prune_expired(now_ns)
        return total_removed
