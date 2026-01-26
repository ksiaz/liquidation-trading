"""Unit tests for windowed_metrics.py."""

import pytest
import time
from runtime.analytics.windowed_metrics import (
    TimeWindow,
    WindowedMetric,
    WindowedMetricsCollector,
    PercentileStats,
    STANDARD_WINDOWS,
)


class TestTimeWindow:
    """Tests for TimeWindow dataclass."""

    def test_window_is_frozen(self):
        """TimeWindow should be immutable."""
        w = TimeWindow("test", 1000)
        with pytest.raises(AttributeError):
            w.name = "changed"

    def test_standard_windows_defined(self):
        """Standard windows should be defined."""
        assert len(STANDARD_WINDOWS) >= 4
        names = [w.name for w in STANDARD_WINDOWS]
        assert "1min" in names
        assert "5min" in names
        assert "1hour" in names


class TestWindowedMetric:
    """Tests for WindowedMetric class."""

    def test_add_and_count(self):
        """Should add values and count them."""
        w = WindowedMetric(TimeWindow("test", 1_000_000_000_000))  # Large window
        now = int(time.time() * 1_000_000_000)

        w.add(now, 1.0)
        w.add(now + 1, 2.0)
        w.add(now + 2, 3.0)

        assert w.count(now + 100) == 3

    def test_prune_expired(self):
        """Should prune values outside window."""
        w = WindowedMetric(TimeWindow("test", 1000))  # 1 microsecond window
        base_ts = 1_000_000_000_000

        w.add(base_ts, 1.0)
        w.add(base_ts + 500, 2.0)

        # After window, old values pruned
        now = base_ts + 2000
        removed = w.prune_expired(now)
        assert removed == 2
        assert w.count(now) == 0

    def test_percentile_calculation(self):
        """Should compute percentiles correctly."""
        w = WindowedMetric(TimeWindow("test", 1_000_000_000_000))
        now = int(time.time() * 1_000_000_000)

        # Add 100 values from 1 to 100
        for i in range(1, 101):
            w.add(now + i, float(i))

        assert w.percentile(50, now + 200) == pytest.approx(50.0, rel=0.1)
        assert w.percentile(95, now + 200) == pytest.approx(95.0, rel=0.1)
        assert w.percentile(99, now + 200) == pytest.approx(99.0, rel=0.1)

    def test_mean_calculation(self):
        """Should compute mean correctly."""
        w = WindowedMetric(TimeWindow("test", 1_000_000_000_000))
        now = int(time.time() * 1_000_000_000)

        w.add(now, 10.0)
        w.add(now + 1, 20.0)
        w.add(now + 2, 30.0)

        assert w.mean(now + 100) == 20.0

    def test_empty_returns_none(self):
        """Should return None for empty metric."""
        w = WindowedMetric(TimeWindow("test", 1000))
        now = int(time.time() * 1_000_000_000)

        assert w.mean(now) is None
        assert w.percentile(50, now) is None

    def test_compute_stats(self):
        """Should compute full statistics."""
        w = WindowedMetric(TimeWindow("test", 1_000_000_000_000))
        now = int(time.time() * 1_000_000_000)

        for i in range(1, 51):
            w.add(now + i, float(i))

        stats = w.compute_stats(now + 100)

        assert stats.window_name == "test"
        assert stats.sample_count == 50
        assert stats.mean == pytest.approx(25.5, rel=0.01)
        assert stats.min_value == 1.0
        assert stats.max_value == 50.0


class TestWindowedMetricsCollector:
    """Tests for WindowedMetricsCollector class."""

    def test_record_and_retrieve(self):
        """Should record values and retrieve stats."""
        collector = WindowedMetricsCollector()
        now = int(time.time() * 1_000_000_000)

        for i in range(10):
            collector.record("latency", float(i * 10), now + i)

        stats = collector.get_stats("latency", "1min", now + 100)

        assert stats is not None
        assert stats.sample_count == 10
        assert stats.mean == pytest.approx(45.0, rel=0.01)

    def test_multiple_metrics(self):
        """Should track multiple metrics independently."""
        collector = WindowedMetricsCollector()
        now = int(time.time() * 1_000_000_000)

        collector.record("latency", 100.0, now)
        collector.record("slippage", 5.0, now)

        lat_stats = collector.get_stats("latency", "1min", now + 1)
        slip_stats = collector.get_stats("slippage", "1min", now + 1)

        assert lat_stats.mean == 100.0
        assert slip_stats.mean == 5.0

    def test_get_all_window_stats(self):
        """Should retrieve stats from all windows."""
        collector = WindowedMetricsCollector()
        now = int(time.time() * 1_000_000_000)

        collector.record("test_metric", 42.0, now)

        all_stats = collector.get_all_window_stats("test_metric", now + 1)

        assert "1min" in all_stats
        assert "5min" in all_stats
        assert "1hour" in all_stats

    def test_compare_windows(self):
        """Should compare values between windows."""
        collector = WindowedMetricsCollector()
        now = int(time.time() * 1_000_000_000)

        # Add same value to all windows
        for i in range(10):
            collector.record("metric", 100.0, now + i)

        result = collector.compare_windows(
            "metric", "1min", "5min", "mean", now + 100
        )

        assert result is not None
        recent, baseline, change = result
        assert recent == 100.0
        assert baseline == 100.0
        assert change == pytest.approx(0.0, abs=0.01)

    def test_nonexistent_metric_returns_none(self):
        """Should return None for unknown metric."""
        collector = WindowedMetricsCollector()
        now = int(time.time() * 1_000_000_000)

        stats = collector.get_stats("nonexistent", "1min", now)
        assert stats is None

    def test_get_metric_names(self):
        """Should return list of tracked metrics."""
        collector = WindowedMetricsCollector()
        now = int(time.time() * 1_000_000_000)

        collector.record("metric_a", 1.0, now)
        collector.record("metric_b", 2.0, now)

        names = collector.get_metric_names()
        assert "metric_a" in names
        assert "metric_b" in names

    def test_prune_all(self):
        """Should prune all expired values."""
        # Use small windows for testing
        small_windows = (
            TimeWindow("tiny", 1000),  # 1 microsecond
        )
        collector = WindowedMetricsCollector(windows=small_windows)
        base_ts = 1_000_000_000_000

        collector.record("metric", 1.0, base_ts)
        collector.record("metric", 2.0, base_ts + 500)

        # After window expires
        now = base_ts + 5000
        removed = collector.prune_all(now)

        assert removed == 2
