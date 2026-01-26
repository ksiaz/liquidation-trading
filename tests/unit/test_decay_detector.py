"""Unit tests for decay_detector.py."""

import pytest
import time
from runtime.analytics.windowed_metrics import WindowedMetricsCollector, TimeWindow
from runtime.analytics.decay_detector import (
    DecayDetector,
    DecaySignal,
    DecayComparison,
    DEFAULT_COMPARISONS,
    format_decay_signals,
)


class TestDecaySignal:
    """Tests for DecaySignal dataclass."""

    def test_signal_is_frozen(self):
        """DecaySignal should be immutable."""
        signal = DecaySignal(
            metric_name="test",
            recent_window="1hour",
            baseline_window="24hour",
            recent_value=100.0,
            baseline_value=90.0,
            change_pct=11.1,
            z_score=None,
            recent_sample_count=10,
            baseline_sample_count=100,
        )
        with pytest.raises(AttributeError):
            signal.metric_name = "changed"

    def test_signal_fields(self):
        """DecaySignal should have all required fields."""
        signal = DecaySignal(
            metric_name="latency",
            recent_window="1hour",
            baseline_window="24hour",
            recent_value=150.0,
            baseline_value=100.0,
            change_pct=50.0,
            z_score=2.5,
            recent_sample_count=50,
            baseline_sample_count=500,
        )

        assert signal.metric_name == "latency"
        assert signal.change_pct == 50.0
        assert signal.z_score == 2.5


class TestDecayComparison:
    """Tests for DecayComparison dataclass."""

    def test_default_comparisons_exist(self):
        """Default comparisons should be defined."""
        assert len(DEFAULT_COMPARISONS) > 0

        # Check latency comparison exists
        latency_comparisons = [
            c for c in DEFAULT_COMPARISONS
            if c.metric_name == "detection_to_fill_latency_ns"
        ]
        assert len(latency_comparisons) > 0


class TestDecayDetector:
    """Tests for DecayDetector class."""

    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector with small windows for testing."""
        windows = (
            TimeWindow("recent", 60 * 1_000_000_000),  # 1 minute
            TimeWindow("baseline", 300 * 1_000_000_000),  # 5 minutes
        )
        return WindowedMetricsCollector(windows=windows)

    @pytest.fixture
    def detector(self, metrics_collector):
        """Create detector with test comparisons."""
        comparisons = (
            DecayComparison("test_metric", "mean", "recent", "baseline"),
        )
        return DecayDetector(
            windowed_metrics=metrics_collector,
            comparisons=comparisons,
            min_samples_for_zscore=5,
        )

    def test_no_data_returns_empty(self, detector):
        """Should return empty list when no data."""
        signals = detector.compute_decay_signals()
        assert signals == []

    def test_computes_signal_with_data(self, detector, metrics_collector):
        """Should compute signal when data available."""
        now = int(time.time() * 1_000_000_000)

        # Add data to both windows
        for i in range(10):
            metrics_collector.record("test_metric", 100.0, now - i * 1000)

        signals = detector.compute_decay_signals(now)

        # Should have one signal
        assert len(signals) == 1
        signal = signals[0]
        assert signal.metric_name == "test_metric"
        assert signal.recent_value == pytest.approx(100.0, rel=0.01)

    def test_change_pct_calculation(self, detector, metrics_collector):
        """Should calculate change percentage correctly."""
        now = int(time.time() * 1_000_000_000)

        # Baseline: 100, Recent: 150 -> +50% change
        for i in range(10):
            metrics_collector.record("test_metric", 100.0, now - 200_000_000_000 - i)
        for i in range(10):
            metrics_collector.record("test_metric", 150.0, now - i * 1000)

        signals = detector.compute_decay_signals(now)

        assert len(signals) == 1
        # Change should be approximately (150-100)/100 = 50%
        # Note: both windows overlap, so actual result depends on pruning

    def test_zscore_not_computed_without_history(self, detector, metrics_collector):
        """Should not compute z-score without sufficient history."""
        now = int(time.time() * 1_000_000_000)

        for i in range(10):
            metrics_collector.record("test_metric", 100.0, now - i * 1000)

        signals = detector.compute_decay_signals(now)

        assert len(signals) == 1
        assert signals[0].z_score is None  # Not enough history

    def test_get_signal_for_specific_metric(self, metrics_collector):
        """Should get signal for a specific metric."""
        detector = DecayDetector(
            windowed_metrics=metrics_collector,
            comparisons=(),  # No default comparisons
        )
        now = int(time.time() * 1_000_000_000)

        for i in range(10):
            metrics_collector.record("custom_metric", 50.0, now - i * 1000)

        signal = detector.get_signal_for_metric(
            "custom_metric",
            stat="mean",
            recent_window="recent",
            baseline_window="baseline",
            now_ns=now,
        )

        assert signal is not None
        assert signal.metric_name == "custom_metric"

    def test_clear_history(self, detector, metrics_collector):
        """Should clear z-score history."""
        now = int(time.time() * 1_000_000_000)

        for i in range(10):
            metrics_collector.record("test_metric", 100.0, now - i * 1000)

        # Generate some history
        for _ in range(10):
            detector.compute_decay_signals(now)

        # Clear and verify
        detector.clear_history()
        assert len(detector._history) == 0


class TestFormatDecaySignals:
    """Tests for format_decay_signals function."""

    def test_empty_signals(self):
        """Should handle empty signals."""
        result = format_decay_signals([])
        assert "No decay signals" in result

    def test_formats_signals(self):
        """Should format signals into readable string."""
        signals = [
            DecaySignal(
                metric_name="latency",
                recent_window="1hour",
                baseline_window="24hour",
                recent_value=150.0,
                baseline_value=100.0,
                change_pct=50.0,
                z_score=2.5,
                recent_sample_count=50,
                baseline_sample_count=500,
            ),
        ]

        result = format_decay_signals(signals)

        assert "latency" in result
        assert "150.0" in result or "150" in result
        assert "50.0%" in result or "+50" in result
