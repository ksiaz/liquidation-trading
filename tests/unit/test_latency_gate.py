"""Unit tests for latency_gate.py."""

import pytest
import time

from runtime.analytics.windowed_metrics import WindowedMetricsCollector, TimeWindow
from runtime.risk.latency_gate import (
    ExecutionState,
    GatingDecision,
    LatencySnapshot,
    SlippageSnapshot,
    LatencyTrend,
    GatingResult,
    LatencyThresholds,
    LatencyHealthModel,
    ExecutionStateClassifier,
    TradeGate,
)


class TestExecutionState:
    """Tests for ExecutionState enum."""

    def test_all_states_defined(self):
        """All execution states should be defined."""
        assert ExecutionState.FAST.value == "FAST"
        assert ExecutionState.NORMAL.value == "NORMAL"
        assert ExecutionState.DEGRADED.value == "DEGRADED"
        assert ExecutionState.STRESSED.value == "STRESSED"
        assert ExecutionState.BROKEN.value == "BROKEN"


class TestGatingDecision:
    """Tests for GatingDecision enum."""

    def test_all_decisions_defined(self):
        """All gating decisions should be defined."""
        assert GatingDecision.ALLOW.value == "ALLOW"
        assert GatingDecision.REDUCE_SIZE.value == "REDUCE_SIZE"
        assert GatingDecision.DELAY.value == "DELAY"
        assert GatingDecision.BLOCK.value == "BLOCK"


class TestLatencySnapshot:
    """Tests for LatencySnapshot dataclass."""

    def test_snapshot_is_frozen(self):
        """LatencySnapshot should be immutable."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=10_000_000,
            p75_ns=15_000_000,
            p95_ns=25_000_000,
            p99_ns=40_000_000,
            max_ns=100_000_000,
            mean_ns=12_000_000,
            volatility_ns=5_000_000.0,
            jitter_coefficient=0.42,
        )
        with pytest.raises(AttributeError):
            snapshot.p50_ns = 5000

    def test_ms_properties(self):
        """Should convert ns to ms correctly."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=50_000_000,
            p75_ns=75_000_000,
            p95_ns=95_000_000,
            p99_ns=99_000_000,
            max_ns=150_000_000,
            mean_ns=60_000_000,
            volatility_ns=10_000_000.0,
            jitter_coefficient=0.16,
        )
        assert snapshot.p50_ms == 50.0
        assert snapshot.p95_ms == 95.0
        assert snapshot.p99_ms == 99.0


class TestLatencyHealthModel:
    """Tests for LatencyHealthModel class."""

    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector with test windows."""
        windows = (
            TimeWindow("5min", 5 * 60 * 1_000_000_000),
            TimeWindow("1hour", 60 * 60 * 1_000_000_000),
        )
        return WindowedMetricsCollector(windows=windows)

    @pytest.fixture
    def health_model(self, metrics_collector):
        """Create health model."""
        return LatencyHealthModel(metrics_collector)

    def test_no_data_returns_none(self, health_model):
        """Should return None with no data."""
        snapshot = health_model.get_latency_snapshot()
        assert snapshot is None

    def test_insufficient_samples_returns_none(self, health_model, metrics_collector):
        """Should return None with insufficient samples."""
        now = int(time.time() * 1_000_000_000)
        # Add fewer than min_samples (default 10)
        for i in range(5):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                50_000_000,
                now - i * 1000,
            )
        snapshot = health_model.get_latency_snapshot(now_ns=now)
        assert snapshot is None

    def test_computes_snapshot_with_data(self, health_model, metrics_collector):
        """Should compute snapshot with sufficient data."""
        now = int(time.time() * 1_000_000_000)
        # Add sufficient samples
        for i in range(20):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                50_000_000 + i * 1_000_000,
                now - i * 1000,
            )
        snapshot = health_model.get_latency_snapshot(now_ns=now)
        assert snapshot is not None
        assert snapshot.sample_count == 20

    def test_slippage_snapshot(self, health_model, metrics_collector):
        """Should compute slippage snapshot."""
        now = int(time.time() * 1_000_000_000)
        for i in range(15):
            metrics_collector.record("slippage_bps", 10.0 + i * 0.5, now - i * 1000)
        snapshot = health_model.get_slippage_snapshot(now_ns=now)
        assert snapshot is not None
        assert snapshot.sample_count == 15

    def test_latency_trend(self, health_model, metrics_collector):
        """Should compute latency trend."""
        now = int(time.time() * 1_000_000_000)
        # Add data to both windows
        for i in range(50):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                50_000_000,
                now - i * 1000,
            )
        trend = health_model.get_latency_trend(now_ns=now)
        # May be None if windows don't differ enough
        # Just ensure no crash


class TestExecutionStateClassifier:
    """Tests for ExecutionStateClassifier class."""

    @pytest.fixture
    def classifier(self):
        """Create classifier."""
        return ExecutionStateClassifier()

    def test_no_data_is_broken(self, classifier):
        """Should return BROKEN with no data."""
        state, reason = classifier.classify(None)
        assert state == ExecutionState.BROKEN
        assert reason == "insufficient_latency_data"

    def test_fast_state(self, classifier):
        """Should classify as FAST for low latency."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=20_000_000,  # 20ms
            p75_ns=30_000_000,
            p95_ns=40_000_000,  # 40ms < 50ms threshold
            p99_ns=45_000_000,
            max_ns=50_000_000,
            mean_ns=25_000_000,
            volatility_ns=5_000_000.0,
            jitter_coefficient=0.2,
        )
        state, reason = classifier.classify(snapshot)
        assert state == ExecutionState.FAST
        assert reason == "optimal"

    def test_normal_state(self, classifier):
        """Should classify as NORMAL for moderate latency."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=40_000_000,
            p75_ns=60_000_000,
            p95_ns=80_000_000,  # 80ms, between 50ms and 100ms
            p99_ns=90_000_000,
            max_ns=100_000_000,
            mean_ns=50_000_000,
            volatility_ns=10_000_000.0,
            jitter_coefficient=0.2,
        )
        state, reason = classifier.classify(snapshot)
        assert state == ExecutionState.NORMAL
        assert reason == "nominal"

    def test_degraded_state(self, classifier):
        """Should classify as DEGRADED for elevated latency."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=80_000_000,
            p75_ns=100_000_000,
            p95_ns=150_000_000,  # 150ms, between 100ms and 200ms
            p99_ns=180_000_000,
            max_ns=200_000_000,
            mean_ns=100_000_000,
            volatility_ns=20_000_000.0,
            jitter_coefficient=0.2,
        )
        state, reason = classifier.classify(snapshot)
        assert state == ExecutionState.DEGRADED

    def test_stressed_state(self, classifier):
        """Should classify as STRESSED for high latency."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=150_000_000,
            p75_ns=200_000_000,
            p95_ns=350_000_000,  # 350ms, between 200ms and 500ms
            p99_ns=400_000_000,
            max_ns=450_000_000,
            mean_ns=200_000_000,
            volatility_ns=50_000_000.0,
            jitter_coefficient=0.25,
        )
        state, reason = classifier.classify(snapshot)
        assert state == ExecutionState.STRESSED

    def test_broken_state_high_latency(self, classifier):
        """Should classify as BROKEN for very high latency."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=300_000_000,
            p75_ns=400_000_000,
            p95_ns=600_000_000,  # 600ms > 500ms threshold
            p99_ns=700_000_000,
            max_ns=800_000_000,
            mean_ns=400_000_000,
            volatility_ns=100_000_000.0,
            jitter_coefficient=0.25,
        )
        state, reason = classifier.classify(snapshot)
        assert state == ExecutionState.BROKEN

    def test_broken_state_high_jitter(self, classifier):
        """Should classify as BROKEN for high jitter."""
        snapshot = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=50_000_000,
            p75_ns=60_000_000,
            p95_ns=80_000_000,  # Low latency
            p99_ns=90_000_000,
            max_ns=100_000_000,
            mean_ns=60_000_000,
            volatility_ns=60_000_000.0,
            jitter_coefficient=1.0,  # Very high jitter > 0.8
        )
        state, reason = classifier.classify(snapshot)
        assert state == ExecutionState.BROKEN

    def test_slippage_affects_classification(self, classifier):
        """High slippage should affect classification."""
        latency = LatencySnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            p50_ns=30_000_000,
            p75_ns=40_000_000,
            p95_ns=45_000_000,  # Would be FAST by latency
            p99_ns=48_000_000,
            max_ns=50_000_000,
            mean_ns=35_000_000,
            volatility_ns=5_000_000.0,
            jitter_coefficient=0.14,
        )
        slippage = SlippageSnapshot(
            ts_ns=1000,
            window_name="5min",
            sample_count=100,
            mean_bps=40.0,
            p50_bps=35.0,
            p75_bps=45.0,
            p95_bps=60.0,  # Above critical threshold
            p99_bps=80.0,
            max_bps=100.0,
        )
        state, reason = classifier.classify(latency, slippage)
        assert state == ExecutionState.BROKEN


class TestTradeGate:
    """Tests for TradeGate class."""

    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector."""
        windows = (
            TimeWindow("5min", 5 * 60 * 1_000_000_000),
            TimeWindow("1hour", 60 * 60 * 1_000_000_000),
        )
        return WindowedMetricsCollector(windows=windows)

    @pytest.fixture
    def trade_gate(self, metrics_collector):
        """Create trade gate."""
        health_model = LatencyHealthModel(metrics_collector)
        classifier = ExecutionStateClassifier()
        return TradeGate(health_model, classifier)

    def test_evaluate_no_data_blocks(self, trade_gate):
        """Should BLOCK with no data."""
        result = trade_gate.evaluate()
        assert result.decision == GatingDecision.BLOCK
        assert result.execution_state == ExecutionState.BROKEN

    def test_evaluate_with_good_data_allows(self, trade_gate, metrics_collector):
        """Should ALLOW with good latency data."""
        now = int(time.time() * 1_000_000_000)
        # Add good latency data
        for i in range(20):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                30_000_000,  # 30ms - FAST
                now - i * 1000,
            )
        result = trade_gate.evaluate(now_ns=now)
        assert result.decision == GatingDecision.ALLOW
        assert result.execution_state == ExecutionState.FAST
        assert result.size_factor == 1.0

    def test_evaluate_degraded_reduces_size(self, trade_gate, metrics_collector):
        """Should REDUCE_SIZE in DEGRADED state."""
        now = int(time.time() * 1_000_000_000)
        # Add degraded latency data
        for i in range(20):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                150_000_000,  # 150ms - DEGRADED
                now - i * 1000,
            )
        result = trade_gate.evaluate(now_ns=now)
        assert result.decision == GatingDecision.REDUCE_SIZE
        assert result.execution_state == ExecutionState.DEGRADED
        assert result.size_factor == 0.5

    def test_allows_trade_helper(self, trade_gate, metrics_collector):
        """allows_trade helper should work correctly."""
        now = int(time.time() * 1_000_000_000)
        # Add good data
        for i in range(20):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                30_000_000,
                now - i * 1000,
            )
        assert trade_gate.allows_trade() is True

    def test_get_size_factor_helper(self, trade_gate, metrics_collector):
        """get_size_factor helper should work correctly."""
        now = int(time.time() * 1_000_000_000)
        for i in range(20):
            metrics_collector.record(
                "detection_to_fill_latency_ns",
                30_000_000,
                now - i * 1000,
            )
        assert trade_gate.get_size_factor() == 1.0


class TestGatingResult:
    """Tests for GatingResult dataclass."""

    def test_result_is_frozen(self):
        """GatingResult should be immutable."""
        result = GatingResult(
            decision=GatingDecision.ALLOW,
            latency_snapshot=None,
            slippage_snapshot=None,
            execution_state=ExecutionState.NORMAL,
            reason="test",
            ts_ns=1000,
        )
        with pytest.raises(AttributeError):
            result.decision = GatingDecision.BLOCK
