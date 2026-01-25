"""Unit tests for MetricsCollector."""

import pytest
import time
from unittest.mock import patch, MagicMock

from runtime.analytics.metrics_collector import MetricsCollector, MetricsConfig
from runtime.analytics.types import MetricCategory


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_init_defaults(self):
        """Test collector initialization."""
        collector = MetricsCollector()
        assert len(collector._metrics) == 0
        assert len(collector._heartbeats) == 0
        assert len(collector._data_timestamps) == 0

    def test_init_custom_config(self):
        """Test collector with custom config."""
        config = MetricsConfig(
            data_staleness_warning_ms=1000,
            cpu_warning_pct=80.0
        )
        collector = MetricsCollector(config=config)
        assert collector._config.data_staleness_warning_ms == 1000
        assert collector._config.cpu_warning_pct == 80.0

    def test_record_metric(self):
        """Test recording a metric."""
        collector = MetricsCollector()

        collector.record(
            name="test_metric",
            value=42.0,
            category=MetricCategory.OPERATIONAL,
            tags={"symbol": "BTC"},
            unit="count"
        )

        assert "test_metric" in collector._metrics
        assert len(collector._metrics["test_metric"]) == 1

        metric = collector._metrics["test_metric"][0]
        assert metric.value == 42.0
        assert metric.category == MetricCategory.OPERATIONAL
        assert metric.tags == {"symbol": "BTC"}
        assert metric.unit == "count"

    def test_record_metric_respects_max(self):
        """Test metric storage respects max limit."""
        config = MetricsConfig(max_metrics_per_name=5)
        collector = MetricsCollector(config=config)

        # Record 10 values
        for i in range(10):
            collector.record(
                name="test",
                value=float(i),
                category=MetricCategory.OPERATIONAL
            )

        # Should only keep last 5
        assert len(collector._metrics["test"]) == 5
        assert collector._metrics["test"][0].value == 5.0  # First is 5
        assert collector._metrics["test"][-1].value == 9.0  # Last is 9

    def test_record_heartbeat(self):
        """Test recording heartbeat."""
        collector = MetricsCollector()

        collector.record_heartbeat("data_fetcher")

        assert "data_fetcher" in collector._heartbeats
        assert collector._heartbeats["data_fetcher"] > 0

    def test_record_data_update(self):
        """Test recording data update."""
        collector = MetricsCollector()

        collector.record_data_update("orderbook")

        assert "orderbook" in collector._data_timestamps
        assert collector._data_timestamps["orderbook"] > 0

    def test_record_latency(self):
        """Test recording latency."""
        collector = MetricsCollector()

        collector.record_latency("api_call", 15.5)

        assert "api_call" in collector._latencies
        assert 15.5 in collector._latencies["api_call"]

        # Also recorded as metric
        assert "latency_api_call" in collector._metrics

    def test_get_data_staleness_unknown(self):
        """Test staleness for unknown source."""
        collector = MetricsCollector()
        staleness = collector.get_data_staleness_ms("unknown")
        assert staleness == float('inf')

    def test_get_data_staleness(self):
        """Test staleness calculation."""
        collector = MetricsCollector()

        collector.record_data_update("orderbook")
        time.sleep(0.01)  # Small delay

        staleness = collector.get_data_staleness_ms("orderbook")
        assert staleness >= 10  # At least 10ms
        assert staleness < 1000  # Less than 1 second

    def test_get_heartbeat_age_unknown(self):
        """Test heartbeat age for unknown component."""
        collector = MetricsCollector()
        age = collector.get_heartbeat_age_ms("unknown")
        assert age == float('inf')

    def test_get_heartbeat_age(self):
        """Test heartbeat age calculation."""
        collector = MetricsCollector()

        collector.record_heartbeat("worker")
        time.sleep(0.01)

        age = collector.get_heartbeat_age_ms("worker")
        assert age >= 10
        assert age < 1000

    def test_check_component_health_unknown(self):
        """Test health check for unknown component."""
        collector = MetricsCollector()
        status = collector.check_component_health("unknown")
        assert status == "UNKNOWN"

    def test_check_component_health_healthy(self):
        """Test health check for healthy component."""
        collector = MetricsCollector()
        collector.record_heartbeat("worker")
        status = collector.check_component_health("worker")
        assert status == "HEALTHY"

    def test_check_component_health_unhealthy(self):
        """Test health check for unhealthy component."""
        config = MetricsConfig(heartbeat_timeout_ms=1)  # 1ms timeout
        collector = MetricsCollector(config=config)

        collector.record_heartbeat("worker")
        time.sleep(0.01)  # Wait longer than timeout

        status = collector.check_component_health("worker")
        assert status == "UNHEALTHY"

    def test_check_data_health_unknown(self):
        """Test data health for unknown source."""
        collector = MetricsCollector()
        status = collector.check_data_health("unknown")
        assert status == "UNKNOWN"

    def test_check_data_health_healthy(self):
        """Test data health for fresh data."""
        collector = MetricsCollector()
        collector.record_data_update("orderbook")
        status = collector.check_data_health("orderbook")
        assert status == "HEALTHY"

    def test_check_data_health_warning(self):
        """Test data health warning state."""
        config = MetricsConfig(
            data_staleness_warning_ms=1,
            data_staleness_critical_ms=100
        )
        collector = MetricsCollector(config=config)

        collector.record_data_update("orderbook")
        time.sleep(0.01)  # Past warning, before critical

        status = collector.check_data_health("orderbook")
        assert status == "WARNING"

    def test_check_data_health_critical(self):
        """Test data health critical state."""
        config = MetricsConfig(
            data_staleness_warning_ms=1,
            data_staleness_critical_ms=5
        )
        collector = MetricsCollector(config=config)

        collector.record_data_update("orderbook")
        time.sleep(0.02)  # Past critical

        status = collector.check_data_health("orderbook")
        assert status == "CRITICAL"

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_collect_system_metrics(self, mock_psutil):
        """Test system metrics collection."""
        mock_psutil.cpu_percent.return_value = 45.0
        mock_psutil.virtual_memory.return_value = MagicMock(
            percent=60.0,
            available=8_000_000_000
        )
        mock_psutil.disk_usage.return_value = MagicMock(percent=50.0)

        collector = MetricsCollector()
        collector.collect_system_metrics()

        assert "cpu_usage" in collector._metrics
        assert "memory_usage" in collector._metrics
        assert "memory_available_mb" in collector._metrics
        assert "disk_usage" in collector._metrics

        assert collector._metrics["cpu_usage"][-1].value == 45.0
        assert collector._metrics["memory_usage"][-1].value == 60.0

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_get_cpu_usage(self, mock_psutil):
        """Test CPU usage retrieval."""
        mock_psutil.cpu_percent.return_value = 75.0

        collector = MetricsCollector()
        cpu = collector.get_cpu_usage()

        assert cpu == 75.0

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_get_memory_usage(self, mock_psutil):
        """Test memory usage retrieval."""
        mock_psutil.virtual_memory.return_value = MagicMock(percent=65.0)

        collector = MetricsCollector()
        memory = collector.get_memory_usage()

        assert memory == 65.0

    def test_get_latency_stats_no_data(self):
        """Test latency stats with no data."""
        collector = MetricsCollector()
        stats = collector.get_latency_stats("nonexistent")

        assert stats['p50'] == 0
        assert stats['p95'] == 0
        assert stats['avg'] == 0

    def test_get_latency_stats(self):
        """Test latency statistics calculation."""
        collector = MetricsCollector()

        # Record various latencies
        for lat in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            collector.record_latency("api", float(lat))

        stats = collector.get_latency_stats("api")

        # p50 uses index int(10 * 0.50) = 5, value at index 5 in sorted list
        assert stats['p50'] == 60.0
        assert stats['max'] == 100.0
        assert stats['avg'] == 55.0
        assert stats['count'] == 10

    def test_get_metric_history(self):
        """Test getting metric history."""
        collector = MetricsCollector()

        for i in range(10):
            collector.record(
                name="test",
                value=float(i),
                category=MetricCategory.OPERATIONAL
            )

        history = collector.get_metric_history("test", limit=5)
        assert len(history) == 5
        assert history[0].value == 5.0  # Starts from 5 (last 5)
        assert history[-1].value == 9.0

    def test_get_latest(self):
        """Test getting latest metric value."""
        collector = MetricsCollector()

        collector.record("test", 1.0, MetricCategory.OPERATIONAL)
        collector.record("test", 2.0, MetricCategory.OPERATIONAL)
        collector.record("test", 3.0, MetricCategory.OPERATIONAL)

        latest = collector.get_latest("test")
        assert latest is not None
        assert latest.value == 3.0

    def test_get_latest_nonexistent(self):
        """Test getting latest for nonexistent metric."""
        collector = MetricsCollector()
        assert collector.get_latest("nonexistent") is None

    def test_get_all_components(self):
        """Test getting all component health."""
        collector = MetricsCollector()

        collector.record_heartbeat("worker_1")
        collector.record_heartbeat("worker_2")

        components = collector.get_all_components()

        assert "worker_1" in components
        assert "worker_2" in components
        assert components["worker_1"] == "HEALTHY"
        assert components["worker_2"] == "HEALTHY"

    def test_get_all_data_sources(self):
        """Test getting all data source health."""
        collector = MetricsCollector()

        collector.record_data_update("orderbook")
        collector.record_data_update("trades")

        sources = collector.get_all_data_sources()

        assert "orderbook" in sources
        assert "trades" in sources
        assert sources["orderbook"] == "HEALTHY"

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_get_health_summary_healthy(self, mock_psutil):
        """Test health summary when all healthy."""
        mock_psutil.cpu_percent.return_value = 30.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=40.0)

        collector = MetricsCollector()
        collector.record_heartbeat("worker")
        collector.record_data_update("orderbook")

        summary = collector.get_health_summary()

        assert summary['overall'] == "HEALTHY"
        assert summary['resource_status'] == "HEALTHY"
        assert len(summary['unhealthy_components']) == 0
        assert len(summary['unhealthy_sources']) == 0

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_get_health_summary_degraded(self, mock_psutil):
        """Test health summary when resources degraded."""
        mock_psutil.cpu_percent.return_value = 75.0  # Warning level
        mock_psutil.virtual_memory.return_value = MagicMock(percent=40.0)

        collector = MetricsCollector()
        summary = collector.get_health_summary()

        assert summary['resource_status'] == "WARNING"
        assert summary['overall'] == "DEGRADED"

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_get_health_summary_unhealthy(self, mock_psutil):
        """Test health summary when critical."""
        mock_psutil.cpu_percent.return_value = 95.0  # Critical
        mock_psutil.virtual_memory.return_value = MagicMock(percent=40.0)

        collector = MetricsCollector()
        summary = collector.get_health_summary()

        assert summary['resource_status'] == "CRITICAL"
        assert summary['overall'] == "UNHEALTHY"

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_check_resource_thresholds(self, mock_psutil):
        """Test resource threshold checking."""
        mock_psutil.cpu_percent.return_value = 75.0  # Warning
        mock_psutil.virtual_memory.return_value = MagicMock(percent=90.0)  # Critical

        collector = MetricsCollector()
        issues = collector.check_resource_thresholds()

        assert issues.get('cpu') == 'WARNING'
        assert issues.get('memory') == 'CRITICAL'

    @patch('runtime.analytics.metrics_collector.psutil')
    def test_check_resource_thresholds_healthy(self, mock_psutil):
        """Test resource threshold when healthy."""
        mock_psutil.cpu_percent.return_value = 30.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=40.0)

        collector = MetricsCollector()
        issues = collector.check_resource_thresholds()

        assert len(issues) == 0

    def test_thread_safety(self):
        """Test thread-safe access."""
        import threading

        collector = MetricsCollector()
        errors = []

        def record_metrics():
            try:
                for i in range(100):
                    collector.record("test", float(i), MetricCategory.OPERATIONAL)
                    collector.record_heartbeat(f"worker_{i % 3}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_metrics) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
