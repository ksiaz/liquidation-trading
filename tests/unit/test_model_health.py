"""Unit tests for ModelHealthTracker."""

import pytest
import time

from runtime.meta.model_health import (
    ModelHealthTracker,
    ModelHealthConfig,
)
from runtime.meta.types import (
    CalibratedParameter,
    DistributionSnapshot,
    ModelHealthStatus,
)


class TestModelHealthTracker:
    """Tests for ModelHealthTracker."""

    def test_init_defaults(self):
        """Test tracker initialization."""
        tracker = ModelHealthTracker()
        assert len(tracker._parameters) == 0
        assert len(tracker._observations) == 0

    def test_register_parameter(self):
        """Test registering a parameter."""
        tracker = ModelHealthTracker()

        param = CalibratedParameter(
            name="threshold_a",
            value=0.15,
            expected_mean=0.12,
            expected_std=0.03
        )
        tracker.register_parameter(param)

        assert "threshold_a" in tracker._parameters
        assert "threshold_a" in tracker._observations

    def test_unregister_parameter(self):
        """Test unregistering a parameter."""
        tracker = ModelHealthTracker()

        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)
        tracker.unregister_parameter("test")

        assert "test" not in tracker._parameters

    def test_observe(self):
        """Test recording observations."""
        tracker = ModelHealthTracker()

        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)

        tracker.observe("test", 1.1)
        tracker.observe("test", 1.2)
        tracker.observe("test", 0.9)

        assert len(tracker._observations["test"]) == 3

    def test_observe_unknown_parameter(self):
        """Test observing unknown parameter does nothing."""
        tracker = ModelHealthTracker()
        tracker.observe("unknown", 1.0)  # Should not raise

    def test_observe_batch(self):
        """Test batch observations."""
        tracker = ModelHealthTracker()

        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)

        now = int(time.time() * 1_000_000_000)
        values = [(now + i, float(i)) for i in range(5)]
        tracker.observe_batch("test", values)

        assert len(tracker._observations["test"]) == 5

    def test_check_health_insufficient_data(self):
        """Test health check with insufficient data."""
        config = ModelHealthConfig(min_samples_for_test=30)
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(name="test", value=1.0, expected_mean=1.0)
        tracker.register_parameter(param)

        # Only 10 observations
        for i in range(10):
            tracker.observe("test", 1.0)

        health = tracker.check_health("test")
        assert health == ModelHealthStatus.UNKNOWN

    def test_check_health_healthy(self):
        """Test health check when parameter is healthy."""
        config = ModelHealthConfig(
            min_samples_for_test=10,
            drift_warning_pct=0.15
        )
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(
            name="test",
            value=1.0,
            expected_mean=1.0,
            expected_std=None  # Don't check variance drift
        )
        tracker.register_parameter(param)

        # Observations around expected mean
        for i in range(30):
            tracker.observe("test", 1.0 + (i % 3 - 1) * 0.05)  # 0.95, 1.0, 1.05

        health = tracker.check_health("test")
        assert health == ModelHealthStatus.HEALTHY

    def test_check_health_drifting(self):
        """Test health check when parameter is drifting."""
        config = ModelHealthConfig(
            min_samples_for_test=10,
            drift_warning_pct=0.15,
            drift_critical_pct=0.30
        )
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(
            name="test",
            value=1.0,
            expected_mean=1.0,
            expected_std=0.1
        )
        tracker.register_parameter(param)

        # Observations ~20% above expected (drift warning)
        for i in range(30):
            tracker.observe("test", 1.2)

        health = tracker.check_health("test")
        assert health == ModelHealthStatus.DRIFTING

    def test_check_health_broken(self):
        """Test health check when parameter is broken."""
        config = ModelHealthConfig(
            min_samples_for_test=10,
            drift_warning_pct=0.15,
            drift_critical_pct=0.30
        )
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(
            name="test",
            value=1.0,
            expected_mean=1.0,
            expected_std=0.1
        )
        tracker.register_parameter(param)

        # Observations ~50% above expected (broken)
        for i in range(30):
            tracker.observe("test", 1.5)

        health = tracker.check_health("test")
        assert health == ModelHealthStatus.BROKEN

    def test_check_all(self):
        """Test checking all parameters."""
        config = ModelHealthConfig(min_samples_for_test=5)
        tracker = ModelHealthTracker(config=config)

        for name in ["param_a", "param_b"]:
            param = CalibratedParameter(
                name=name,
                value=1.0,
                expected_mean=1.0
            )
            tracker.register_parameter(param)

            for i in range(10):
                tracker.observe(name, 1.0)

        results = tracker.check_all()

        assert "param_a" in results
        assert "param_b" in results

    def test_get_snapshot(self):
        """Test getting distribution snapshot."""
        config = ModelHealthConfig(min_samples_for_test=5)
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)

        for i in range(1, 11):  # 1-10
            tracker.observe("test", float(i))

        snapshot = tracker.get_snapshot("test")

        assert snapshot is not None
        assert snapshot.sample_count == 10
        assert snapshot.mean == 5.5
        assert snapshot.min_val == 1.0
        assert snapshot.max_val == 10.0

    def test_get_snapshot_insufficient_data(self):
        """Test snapshot with insufficient data."""
        config = ModelHealthConfig(min_samples_for_test=100)
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)

        for i in range(5):
            tracker.observe("test", float(i))

        snapshot = tracker.get_snapshot("test")
        assert snapshot is None

    def test_set_baseline(self):
        """Test setting baseline distribution."""
        tracker = ModelHealthTracker()

        baseline = DistributionSnapshot(
            name="test",
            timestamp_ns=int(time.time() * 1_000_000_000),
            sample_count=100,
            mean=1.0,
            std=0.1,
            min_val=0.8,
            max_val=1.2,
            p25=0.95,
            p50=1.0,
            p75=1.05,
            p95=1.15
        )
        tracker.set_baseline("test", baseline)

        assert tracker._baselines["test"] == baseline

    def test_compare_distributions(self):
        """Test distribution comparison."""
        config = ModelHealthConfig(min_samples_for_test=5)
        tracker = ModelHealthTracker(config=config)

        # Set baseline
        baseline = DistributionSnapshot(
            name="test",
            timestamp_ns=int(time.time() * 1_000_000_000),
            sample_count=100,
            mean=1.0,
            std=0.1,
            min_val=0.8,
            max_val=1.2,
            p25=0.95,
            p50=1.0,
            p75=1.05,
            p95=1.15
        )
        tracker.set_baseline("test", baseline)

        # Register and observe
        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)

        # Drift 20% higher
        for i in range(30):
            tracker.observe("test", 1.2)

        comparison = tracker.compare_distributions("test")

        assert comparison is not None
        assert comparison['mean_diff_pct'] == pytest.approx(0.2, rel=0.01)
        assert comparison['significant_drift'] is True

    def test_get_unhealthy_parameters(self):
        """Test getting unhealthy parameters."""
        config = ModelHealthConfig(
            min_samples_for_test=5,
            drift_critical_pct=0.30
        )
        tracker = ModelHealthTracker(config=config)

        # Healthy parameter
        healthy = CalibratedParameter(
            name="healthy",
            value=1.0,
            expected_mean=1.0
        )
        tracker.register_parameter(healthy)
        for _ in range(10):
            tracker.observe("healthy", 1.0)

        # Broken parameter
        broken = CalibratedParameter(
            name="broken",
            value=1.0,
            expected_mean=1.0
        )
        tracker.register_parameter(broken)
        for _ in range(10):
            tracker.observe("broken", 2.0)  # 100% drift

        tracker.check_all()

        unhealthy = tracker.get_unhealthy_parameters()
        assert len(unhealthy) == 1
        assert unhealthy[0].name == "broken"

    def test_get_parameters_needing_recalibration(self):
        """Test getting parameters needing recalibration."""
        config = ModelHealthConfig(
            min_samples_for_test=5,
            drift_critical_pct=0.30
        )
        tracker = ModelHealthTracker(config=config)

        # Broken parameter
        broken = CalibratedParameter(
            name="broken",
            value=1.0,
            expected_mean=1.0
        )
        tracker.register_parameter(broken)
        for _ in range(10):
            tracker.observe("broken", 2.0)
        tracker.check_health("broken")

        # Expired parameter
        expired = CalibratedParameter(
            name="expired",
            value=1.0,
            valid_until_ns=1  # Already expired
        )
        tracker.register_parameter(expired)

        needing = tracker.get_parameters_needing_recalibration()

        assert "broken" in needing
        assert "expired" in needing

    def test_get_summary(self):
        """Test getting tracker summary."""
        config = ModelHealthConfig(min_samples_for_test=5)
        tracker = ModelHealthTracker(config=config)

        param = CalibratedParameter(
            name="test",
            value=1.0,
            expected_mean=1.0
        )
        tracker.register_parameter(param)

        for _ in range(10):
            tracker.observe("test", 1.0)

        tracker.check_health("test")

        summary = tracker.get_summary()

        assert summary['total_parameters'] == 1
        assert summary['total_observations'] == 10
        assert 'by_status' in summary

    def test_clear_observations(self):
        """Test clearing observations."""
        tracker = ModelHealthTracker()

        param = CalibratedParameter(name="test", value=1.0)
        tracker.register_parameter(param)

        for _ in range(10):
            tracker.observe("test", 1.0)

        assert len(tracker._observations["test"]) == 10

        tracker.clear_observations("test")

        assert len(tracker._observations["test"]) == 0

    def test_clear_all_observations(self):
        """Test clearing all observations."""
        tracker = ModelHealthTracker()

        for name in ["a", "b", "c"]:
            param = CalibratedParameter(name=name, value=1.0)
            tracker.register_parameter(param)
            tracker.observe(name, 1.0)

        tracker.clear_observations()

        for name in ["a", "b", "c"]:
            assert len(tracker._observations[name]) == 0


class TestCalibratedParameter:
    """Tests for CalibratedParameter dataclass."""

    def test_creation(self):
        """Test parameter creation."""
        param = CalibratedParameter(
            name="threshold",
            value=0.15,
            unit="%",
            expected_mean=0.12,
            expected_std=0.03
        )

        assert param.name == "threshold"
        assert param.value == 0.15
        assert param.unit == "%"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        param = CalibratedParameter(
            name="test",
            value=1.0,
            expected_mean=1.0,
            health_status=ModelHealthStatus.HEALTHY
        )

        d = param.to_dict()

        assert d['name'] == "test"
        assert d['value'] == 1.0
        assert d['health_status'] == "HEALTHY"


class TestDistributionSnapshot:
    """Tests for DistributionSnapshot dataclass."""

    def test_creation(self):
        """Test snapshot creation."""
        snapshot = DistributionSnapshot(
            name="test",
            timestamp_ns=1000,
            sample_count=100,
            mean=1.0,
            std=0.1,
            min_val=0.5,
            max_val=1.5,
            p25=0.9,
            p50=1.0,
            p75=1.1,
            p95=1.3
        )

        assert snapshot.name == "test"
        assert snapshot.mean == 1.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        snapshot = DistributionSnapshot(
            name="test",
            timestamp_ns=1000,
            sample_count=50,
            mean=2.0,
            std=0.5,
            min_val=1.0,
            max_val=3.0,
            p25=1.5,
            p50=2.0,
            p75=2.5,
            p95=2.9
        )

        d = snapshot.to_dict()

        assert d['name'] == "test"
        assert d['sample_count'] == 50
        assert d['mean'] == 2.0
