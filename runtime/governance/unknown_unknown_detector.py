"""
Pillar 5: Unknown-Unknown Detector.

Detects anomalous conditions that don't fit known patterns.
Uses statistical methods to identify when metrics deviate beyond
expected bounds.

Detection Methods:
- Z-score based anomaly detection (3-sigma threshold)
- Multi-metric joint probability
- Correlation breakdown detection

Response:
- If unknown threats detected → UNKNOWN_THREAT state
- Minimal capital allocation (10%)
"""

import time
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from collections import deque


@dataclass(frozen=True)
class UnknownThreatSignal:
    """Detected unknown threat."""
    ts_ns: int
    metric_name: str
    observed_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    description: str


@dataclass(frozen=True)
class ThreatAssessment:
    """Overall threat assessment."""
    ts_ns: int
    has_unknown_threats: bool
    threat_count: int
    max_z_score: float
    signals: List[UnknownThreatSignal]
    joint_probability: float  # Probability of seeing this many anomalies together


@dataclass
class MetricBaseline:
    """Baseline statistics for a metric."""
    metric_name: str
    mean: float = 0.0
    std: float = 0.0
    sample_count: int = 0
    min_value: float = float('inf')
    max_value: float = float('-inf')

    # Running statistics (Welford's algorithm)
    _m2: float = 0.0  # Sum of squared deviations


@dataclass
class UnknownThreatThresholds:
    """Configurable thresholds for threat detection."""
    # Z-score threshold for single metric
    z_score_threshold: float = 3.0  # 3 sigma

    # Minimum samples for valid baseline
    min_samples_for_baseline: int = 100

    # Joint anomaly thresholds
    min_anomalies_for_threat: int = 2  # At least 2 metrics anomalous
    joint_probability_threshold: float = 0.001  # 0.1% chance

    # Correlation breakdown threshold
    correlation_change_threshold: float = 0.5  # |new_corr - baseline_corr| > 0.5

    # Baseline window (nanoseconds)
    baseline_window_ns: int = 24 * 60 * 60 * 1_000_000_000  # 24 hours


class BaselineTracker:
    """
    Tracks baseline statistics for metrics.

    Uses Welford's online algorithm for numerically stable
    running mean and variance computation.
    """

    def __init__(self, window_size: int = 10000):
        self._baselines: Dict[str, MetricBaseline] = {}
        self._recent_values: Dict[str, deque] = {}
        self._window_size = window_size

    def update(self, metric_name: str, value: float) -> None:
        """
        Update baseline statistics with new value.

        Args:
            metric_name: Name of the metric
            value: Observed value
        """
        if metric_name not in self._baselines:
            self._baselines[metric_name] = MetricBaseline(metric_name=metric_name)
            self._recent_values[metric_name] = deque(maxlen=self._window_size)

        baseline = self._baselines[metric_name]
        self._recent_values[metric_name].append(value)

        # Welford's online algorithm
        baseline.sample_count += 1
        n = baseline.sample_count

        delta = value - baseline.mean
        baseline.mean += delta / n
        delta2 = value - baseline.mean
        baseline._m2 += delta * delta2

        # Compute standard deviation
        if n > 1:
            baseline.std = math.sqrt(baseline._m2 / (n - 1))

        # Track min/max
        baseline.min_value = min(baseline.min_value, value)
        baseline.max_value = max(baseline.max_value, value)

    def get_baseline(self, metric_name: str) -> Optional[MetricBaseline]:
        """Get baseline for metric."""
        return self._baselines.get(metric_name)

    def compute_z_score(self, metric_name: str, value: float) -> Optional[float]:
        """
        Compute z-score for a value against baseline.

        Args:
            metric_name: Name of the metric
            value: Observed value

        Returns:
            Z-score or None if insufficient data
        """
        baseline = self._baselines.get(metric_name)
        if baseline is None or baseline.sample_count < 10 or baseline.std <= 0:
            return None

        return (value - baseline.mean) / baseline.std

    def reset_metric(self, metric_name: str) -> None:
        """Reset baseline for a metric."""
        if metric_name in self._baselines:
            del self._baselines[metric_name]
        if metric_name in self._recent_values:
            del self._recent_values[metric_name]

    def get_all_baselines(self) -> Dict[str, MetricBaseline]:
        """Get all baseline statistics."""
        return dict(self._baselines)


class UnknownThreatDetector:
    """
    Detects unknown threats through statistical anomaly detection.

    Monitors:
    - Individual metric deviations (z-score > 3)
    - Joint probability of multiple anomalies
    - Expected correlation breakdowns

    State: Maintains baseline statistics and correlation history
    """

    def __init__(self, thresholds: Optional[UnknownThreatThresholds] = None):
        self._thresholds = thresholds or UnknownThreatThresholds()
        self._baseline_tracker = BaselineTracker()

        # Correlation tracking
        self._correlation_baselines: Dict[Tuple[str, str], float] = {}

        # Recent signals for debouncing
        self._recent_signals: List[UnknownThreatSignal] = []
        self._signal_cooldown_ns: int = 5 * 60 * 1_000_000_000  # 5 minutes

    def update_metric(self, metric_name: str, value: float) -> None:
        """
        Update baseline with new metric observation.

        Args:
            metric_name: Name of the metric
            value: Observed value
        """
        self._baseline_tracker.update(metric_name, value)

    def evaluate(
        self,
        observations: Dict[str, float],
        now_ns: Optional[int] = None,
    ) -> ThreatAssessment:
        """
        Evaluate observations for unknown threats.

        Args:
            observations: Current metric values {metric_name: value}
            now_ns: Current timestamp

        Returns:
            Threat assessment
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        t = self._thresholds

        signals: List[UnknownThreatSignal] = []
        max_z_score = 0.0

        # Check each metric for anomalies
        for metric_name, value in observations.items():
            baseline = self._baseline_tracker.get_baseline(metric_name)

            # Skip if insufficient baseline data
            if baseline is None or baseline.sample_count < t.min_samples_for_baseline:
                continue

            # Skip if std is zero or very small
            if baseline.std <= 1e-10:
                continue

            z_score = (value - baseline.mean) / baseline.std
            abs_z = abs(z_score)

            if abs_z > t.z_score_threshold:
                # Anomaly detected
                signal = UnknownThreatSignal(
                    ts_ns=now_ns,
                    metric_name=metric_name,
                    observed_value=value,
                    baseline_mean=baseline.mean,
                    baseline_std=baseline.std,
                    z_score=z_score,
                    description=self._describe_anomaly(metric_name, z_score, baseline),
                )
                signals.append(signal)
                max_z_score = max(max_z_score, abs_z)

        # Compute joint probability
        joint_prob = self._compute_joint_probability(signals)

        # Determine if unknown threat
        has_unknown_threat = (
            len(signals) >= t.min_anomalies_for_threat or
            joint_prob < t.joint_probability_threshold
        )

        # Update recent signals
        self._recent_signals = signals

        return ThreatAssessment(
            ts_ns=now_ns,
            has_unknown_threats=has_unknown_threat,
            threat_count=len(signals),
            max_z_score=max_z_score,
            signals=signals,
            joint_probability=joint_prob,
        )

    def _describe_anomaly(
        self,
        metric_name: str,
        z_score: float,
        baseline: MetricBaseline,
    ) -> str:
        """Generate description for anomaly."""
        direction = "above" if z_score > 0 else "below"
        sigma_count = abs(z_score)
        return f"{metric_name} is {sigma_count:.1f} sigma {direction} baseline (mean={baseline.mean:.4f}, std={baseline.std:.4f})"

    def _compute_joint_probability(self, signals: List[UnknownThreatSignal]) -> float:
        """
        Compute probability of seeing this many anomalies together.

        Assumes independence (conservative for correlated metrics).
        """
        if not signals:
            return 1.0

        # P(|Z| > z) for normal distribution
        # Using approximation: P(|Z| > 3) ≈ 0.0027
        # P(|Z| > 4) ≈ 0.00006
        # P(|Z| > 5) ≈ 0.0000006

        joint_prob = 1.0
        for signal in signals:
            abs_z = abs(signal.z_score)
            # Approximate tail probability using error function approximation
            individual_prob = 2 * self._normal_tail_prob(abs_z)
            joint_prob *= individual_prob

        return joint_prob

    def _normal_tail_prob(self, z: float) -> float:
        """Approximate P(Z > z) for standard normal."""
        # Using Abramowitz and Stegun approximation
        # Good for z > 0
        if z <= 0:
            return 0.5

        # Constants for approximation
        p = 0.2316419
        b1 = 0.319381530
        b2 = -0.356563782
        b3 = 1.781477937
        b4 = -1.821255978
        b5 = 1.330274429

        t = 1.0 / (1.0 + p * z)
        t_powers = [t ** i for i in range(1, 6)]

        # Standard normal PDF at z
        pdf = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)

        # Approximate CDF using polynomial
        cdf = 1 - pdf * (b1 * t_powers[0] + b2 * t_powers[1] + b3 * t_powers[2] +
                         b4 * t_powers[3] + b5 * t_powers[4])

        return 1 - cdf

    def set_correlation_baseline(
        self,
        metric1: str,
        metric2: str,
        correlation: float,
    ) -> None:
        """
        Set expected correlation between two metrics.

        Args:
            metric1: First metric name
            metric2: Second metric name
            correlation: Expected correlation (-1 to 1)
        """
        key = tuple(sorted([metric1, metric2]))
        self._correlation_baselines[key] = correlation

    def check_correlation_breakdown(
        self,
        metric1: str,
        metric2: str,
        observed_correlation: float,
    ) -> Optional[UnknownThreatSignal]:
        """
        Check if correlation between metrics has broken down.

        Args:
            metric1: First metric name
            metric2: Second metric name
            observed_correlation: Current observed correlation

        Returns:
            UnknownThreatSignal if breakdown detected, None otherwise
        """
        t = self._thresholds
        now_ns = int(time.time() * 1_000_000_000)

        key = tuple(sorted([metric1, metric2]))
        baseline_corr = self._correlation_baselines.get(key)

        if baseline_corr is None:
            return None

        change = abs(observed_correlation - baseline_corr)
        if change > t.correlation_change_threshold:
            return UnknownThreatSignal(
                ts_ns=now_ns,
                metric_name=f"correlation_{metric1}_{metric2}",
                observed_value=observed_correlation,
                baseline_mean=baseline_corr,
                baseline_std=0.1,  # Approximate
                z_score=change / 0.1,  # Approximate
                description=f"Correlation between {metric1} and {metric2} changed from {baseline_corr:.2f} to {observed_correlation:.2f}",
            )

        return None

    def get_recent_signals(self) -> List[UnknownThreatSignal]:
        """Get most recent threat signals."""
        return list(self._recent_signals)

    def reset_baseline(self, metric_name: str = None) -> None:
        """
        Reset baseline statistics.

        Args:
            metric_name: Specific metric to reset, or None for all
        """
        if metric_name:
            self._baseline_tracker.reset_metric(metric_name)
        else:
            self._baseline_tracker = BaselineTracker()

    def get_baseline_stats(self) -> Dict[str, Dict]:
        """Get all baseline statistics."""
        result = {}
        for name, baseline in self._baseline_tracker.get_all_baselines().items():
            result[name] = {
                "mean": baseline.mean,
                "std": baseline.std,
                "sample_count": baseline.sample_count,
                "min_value": baseline.min_value,
                "max_value": baseline.max_value,
            }
        return result
