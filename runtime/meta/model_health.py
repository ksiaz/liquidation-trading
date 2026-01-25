"""
Model Health Tracker.

Detects when calibrated parameters drift from their expected distributions.
Monitors whether the statistical properties the system was designed around
still hold in current market conditions.

Philosophy:
- Calibrated parameters assume underlying distributions are stable
- Markets are non-stationary; distributions shift over time
- Detect drift before it causes systematic losses
"""

import time
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from threading import RLock
from collections import deque

from .types import (
    CalibratedParameter,
    DistributionSnapshot,
    ModelHealthStatus,
)


@dataclass
class ModelHealthConfig:
    """Configuration for model health tracking."""
    # Drift detection
    drift_warning_pct: float = 0.15      # 15% drift = warning
    drift_critical_pct: float = 0.30     # 30% drift = critical

    # Statistical tests
    min_samples_for_test: int = 30       # Minimum samples for comparison
    ks_test_threshold: float = 0.10      # KS statistic threshold

    # Windows
    baseline_window_days: int = 30       # Days for baseline distribution
    comparison_window_days: int = 7      # Days for comparison distribution
    observation_window_size: int = 1000  # Max observations per parameter

    # Recalibration
    recalibration_cooldown_ns: int = 24 * 3600 * 1_000_000_000  # 24 hours


class ModelHealthTracker:
    """
    Tracks health of calibrated model parameters.

    Monitors for:
    - Mean drift: Parameter mean shifting from calibration
    - Variance drift: Parameter variance changing
    - Distribution drift: Overall distribution shape changing (KS test)

    Usage:
        tracker = ModelHealthTracker()

        # Register calibrated parameter
        tracker.register_parameter(CalibratedParameter(
            name="cascade_oi_drop_threshold",
            value=0.10,
            expected_mean=0.12,
            expected_std=0.03,
        ))

        # Feed observations
        for cascade in cascades:
            tracker.observe("cascade_oi_drop_threshold", cascade.oi_drop_pct)

        # Check health
        health = tracker.check_health("cascade_oi_drop_threshold")
    """

    def __init__(
        self,
        config: ModelHealthConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or ModelHealthConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Parameter storage
        self._parameters: Dict[str, CalibratedParameter] = {}

        # Observation storage: parameter -> deque of (timestamp_ns, value)
        self._observations: Dict[str, deque] = {}

        # Baseline snapshots (from calibration period)
        self._baselines: Dict[str, DistributionSnapshot] = {}

        # Health history
        self._health_history: Dict[str, List[Tuple[int, ModelHealthStatus]]] = {}

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def register_parameter(self, param: CalibratedParameter):
        """Register a calibrated parameter for monitoring."""
        with self._lock:
            self._parameters[param.name] = param
            self._observations[param.name] = deque(
                maxlen=self._config.observation_window_size
            )
            self._health_history[param.name] = []

            self._logger.info(
                f"Registered parameter: {param.name} "
                f"(expected_mean={param.expected_mean}, expected_std={param.expected_std})"
            )

    def unregister_parameter(self, name: str):
        """Unregister a parameter."""
        with self._lock:
            self._parameters.pop(name, None)
            self._observations.pop(name, None)
            self._baselines.pop(name, None)
            self._health_history.pop(name, None)

    def set_baseline(self, name: str, snapshot: DistributionSnapshot):
        """Set baseline distribution for a parameter."""
        with self._lock:
            self._baselines[name] = snapshot

    def observe(self, name: str, value: float, timestamp_ns: int = None):
        """
        Record an observation for a parameter.

        Args:
            name: Parameter name
            value: Observed value
            timestamp_ns: Observation timestamp (default: now)
        """
        timestamp_ns = timestamp_ns or self._now_ns()

        with self._lock:
            if name not in self._observations:
                self._logger.debug(f"Unknown parameter: {name}")
                return

            self._observations[name].append((timestamp_ns, value))

    def observe_batch(self, name: str, values: List[Tuple[int, float]]):
        """Record multiple observations."""
        with self._lock:
            if name not in self._observations:
                return
            for timestamp_ns, value in values:
                self._observations[name].append((timestamp_ns, value))

    def check_health(self, name: str) -> ModelHealthStatus:
        """
        Check health of a parameter.

        Returns:
            ModelHealthStatus indicating current health
        """
        with self._lock:
            if name not in self._parameters:
                return ModelHealthStatus.UNKNOWN

            param = self._parameters[name]
            observations = list(self._observations.get(name, []))

            if len(observations) < self._config.min_samples_for_test:
                return ModelHealthStatus.UNKNOWN

            # Get recent values
            values = [v for _, v in observations]

            # Calculate observed statistics
            observed_mean = sum(values) / len(values)
            variance = sum((v - observed_mean) ** 2 for v in values) / len(values)
            observed_std = math.sqrt(variance) if variance > 0 else 0

            # Update parameter
            param.observed_mean = observed_mean
            param.observed_std = observed_std

            # Calculate drift
            status = self._assess_drift(param, observed_mean, observed_std)

            # Record history
            self._health_history[name].append((self._now_ns(), status))
            param.health_status = status

            return status

    def _assess_drift(
        self,
        param: CalibratedParameter,
        observed_mean: float,
        observed_std: float
    ) -> ModelHealthStatus:
        """Assess drift from expected distribution."""
        if param.expected_mean is None:
            return ModelHealthStatus.UNKNOWN

        # Mean drift as percentage of expected mean
        if param.expected_mean != 0:
            mean_drift = abs(observed_mean - param.expected_mean) / abs(param.expected_mean)
        else:
            mean_drift = abs(observed_mean - param.expected_mean)

        param.drift_pct = mean_drift

        # Check thresholds
        if mean_drift > self._config.drift_critical_pct:
            self._logger.warning(
                f"CRITICAL drift for {param.name}: "
                f"{mean_drift*100:.1f}% (threshold: {self._config.drift_critical_pct*100:.0f}%)"
            )
            return ModelHealthStatus.BROKEN

        if mean_drift > self._config.drift_warning_pct:
            self._logger.info(
                f"Drift warning for {param.name}: "
                f"{mean_drift*100:.1f}% (threshold: {self._config.drift_warning_pct*100:.0f}%)"
            )
            return ModelHealthStatus.DRIFTING

        # Also check variance drift if expected_std is set
        if param.expected_std is not None and param.expected_std > 0:
            std_drift = abs(observed_std - param.expected_std) / param.expected_std
            if std_drift > self._config.drift_critical_pct:
                self._logger.warning(
                    f"Variance drift for {param.name}: {std_drift*100:.1f}%"
                )
                return ModelHealthStatus.DRIFTING

        return ModelHealthStatus.HEALTHY

    def check_all(self) -> Dict[str, ModelHealthStatus]:
        """Check health of all registered parameters."""
        results = {}
        with self._lock:
            for name in self._parameters:
                results[name] = self.check_health(name)
        return results

    def get_snapshot(self, name: str) -> Optional[DistributionSnapshot]:
        """Get current distribution snapshot for a parameter."""
        with self._lock:
            if name not in self._observations:
                return None

            observations = list(self._observations[name])
            if len(observations) < self._config.min_samples_for_test:
                return None

            values = sorted([v for _, v in observations])
            n = len(values)

            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / n
            std = math.sqrt(variance) if variance > 0 else 0

            return DistributionSnapshot(
                name=name,
                timestamp_ns=self._now_ns(),
                sample_count=n,
                mean=mean,
                std=std,
                min_val=values[0],
                max_val=values[-1],
                p25=values[int(n * 0.25)],
                p50=values[int(n * 0.50)],
                p75=values[int(n * 0.75)],
                p95=values[int(n * 0.95)] if n > 1 else values[-1],
            )

    def compare_distributions(
        self,
        name: str,
        baseline: DistributionSnapshot = None
    ) -> Optional[Dict]:
        """
        Compare current distribution to baseline using simplified KS-like test.

        Returns comparison metrics or None if insufficient data.
        """
        with self._lock:
            current = self.get_snapshot(name)
            if current is None:
                return None

            baseline = baseline or self._baselines.get(name)
            if baseline is None:
                return None

            # Simplified comparison (actual KS test would need raw baseline data)
            mean_diff = abs(current.mean - baseline.mean)
            mean_diff_pct = mean_diff / abs(baseline.mean) if baseline.mean != 0 else mean_diff

            std_diff = abs(current.std - baseline.std)
            std_diff_pct = std_diff / baseline.std if baseline.std > 0 else std_diff

            # Percentile shifts
            p50_diff = abs(current.p50 - baseline.p50)
            p95_diff = abs(current.p95 - baseline.p95)

            return {
                'mean_diff': mean_diff,
                'mean_diff_pct': mean_diff_pct,
                'std_diff': std_diff,
                'std_diff_pct': std_diff_pct,
                'p50_diff': p50_diff,
                'p95_diff': p95_diff,
                'current_samples': current.sample_count,
                'baseline_samples': baseline.sample_count,
                'significant_drift': mean_diff_pct > self._config.drift_warning_pct,
            }

    def get_unhealthy_parameters(self) -> List[CalibratedParameter]:
        """Get all parameters with health issues."""
        with self._lock:
            return [
                p for p in self._parameters.values()
                if p.health_status in (ModelHealthStatus.DRIFTING, ModelHealthStatus.BROKEN)
            ]

    def get_parameters_needing_recalibration(self) -> List[str]:
        """Get parameters that need recalibration."""
        now_ns = self._now_ns()
        needing = []

        with self._lock:
            for name, param in self._parameters.items():
                # Check if validity expired
                if param.valid_until_ns and now_ns > param.valid_until_ns:
                    needing.append(name)
                    continue

                # Check if broken
                if param.health_status == ModelHealthStatus.BROKEN:
                    needing.append(name)

        return needing

    def get_parameter(self, name: str) -> Optional[CalibratedParameter]:
        """Get a parameter by name."""
        with self._lock:
            return self._parameters.get(name)

    def get_all_parameters(self) -> List[CalibratedParameter]:
        """Get all registered parameters."""
        with self._lock:
            return list(self._parameters.values())

    def get_summary(self) -> Dict:
        """Get tracker summary."""
        with self._lock:
            by_status = {}
            for param in self._parameters.values():
                status = param.health_status.name
                by_status[status] = by_status.get(status, 0) + 1

            unhealthy = self.get_unhealthy_parameters()
            needing_recal = self.get_parameters_needing_recalibration()

            return {
                'total_parameters': len(self._parameters),
                'by_status': by_status,
                'unhealthy_count': len(unhealthy),
                'unhealthy_names': [p.name for p in unhealthy],
                'needing_recalibration': needing_recal,
                'total_observations': sum(
                    len(obs) for obs in self._observations.values()
                ),
            }

    def clear_observations(self, name: str = None):
        """Clear observations for a parameter or all parameters."""
        with self._lock:
            if name:
                if name in self._observations:
                    self._observations[name].clear()
            else:
                for obs in self._observations.values():
                    obs.clear()
