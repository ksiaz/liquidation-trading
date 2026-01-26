"""
Decay Detector - Statistical decay detection.

Computes statistical comparisons between recent and baseline windows
to detect changes in execution quality metrics.

Constitutional: Produces factual statistical comparisons only.
No interpretation of "decay detected" or "edge weakening" claims.
"""

import time
import math
from dataclasses import dataclass
from typing import List, Optional, Dict
from threading import RLock

from .windowed_metrics import WindowedMetricsCollector, PercentileStats


@dataclass(frozen=True)
class DecaySignal:
    """
    Observable decay indicator - factual statistical comparison only.

    Does NOT interpret whether decay is "good" or "bad".
    Does NOT claim edge is weakening.
    Reports only: recent vs baseline values and their difference.
    """
    metric_name: str
    recent_window: str
    baseline_window: str
    recent_value: float
    baseline_value: float
    change_pct: float
    z_score: Optional[float]  # None if insufficient samples for z-score
    recent_sample_count: int
    baseline_sample_count: int


@dataclass(frozen=True)
class DecayComparison:
    """Configuration for a decay comparison."""
    metric_name: str
    stat: str  # "mean", "p50", "p95", "p99"
    recent_window: str
    baseline_window: str


# Standard decay comparisons to compute
DEFAULT_COMPARISONS = (
    # Latency comparisons
    DecayComparison("detection_to_fill_latency_ns", "p95", "1hour", "24hour"),
    DecayComparison("detection_to_fill_latency_ns", "p99", "1hour", "24hour"),
    DecayComparison("detection_to_fill_latency_ns", "mean", "1hour", "24hour"),

    # Slippage comparisons
    DecayComparison("slippage_bps", "mean", "1hour", "24hour"),
    DecayComparison("slippage_bps", "p95", "1hour", "24hour"),

    # Fill rate comparisons
    DecayComparison("fill_rate", "mean", "1hour", "24hour"),
    DecayComparison("fill_rate", "mean", "5min", "1hour"),

    # Rejection count comparisons
    DecayComparison("rejection_count", "mean", "1hour", "24hour"),
)


class DecayDetector:
    """
    Detects statistical changes in metrics over time.

    Constitutional compliance:
    - Returns factual comparisons only
    - Does NOT interpret results
    - Does NOT claim "decay detected"
    - Does NOT suggest action
    """

    def __init__(
        self,
        windowed_metrics: WindowedMetricsCollector,
        comparisons: tuple = DEFAULT_COMPARISONS,
        min_samples_for_zscore: int = 30,
    ):
        """
        Initialize decay detector.

        Args:
            windowed_metrics: Windowed metrics collector
            comparisons: Tuple of DecayComparison configs
            min_samples_for_zscore: Minimum samples to compute z-score
        """
        self._metrics = windowed_metrics
        self._comparisons = comparisons
        self._min_samples_for_zscore = min_samples_for_zscore
        self._lock = RLock()

        # Historical baseline statistics for z-score computation
        # metric_name -> stat -> list of (recent_value, baseline_value, change_pct)
        self._history: Dict[str, Dict[str, List[float]]] = {}

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def compute_decay_signals(
        self,
        now_ns: int = None,
    ) -> List[DecaySignal]:
        """
        Compute decay signals for all configured comparisons.

        Returns:
            List of DecaySignal facts (not interpretations)
        """
        if now_ns is None:
            now_ns = self._now_ns()

        signals = []

        for comparison in self._comparisons:
            signal = self._compute_single_signal(comparison, now_ns)
            if signal is not None:
                signals.append(signal)

        return signals

    def _compute_single_signal(
        self,
        comparison: DecayComparison,
        now_ns: int,
    ) -> Optional[DecaySignal]:
        """Compute a single decay signal."""
        recent_stats = self._metrics.get_stats(
            comparison.metric_name,
            comparison.recent_window,
            now_ns,
        )
        baseline_stats = self._metrics.get_stats(
            comparison.metric_name,
            comparison.baseline_window,
            now_ns,
        )

        if recent_stats is None or baseline_stats is None:
            return None
        if recent_stats.sample_count == 0 or baseline_stats.sample_count == 0:
            return None

        recent_value = getattr(recent_stats, comparison.stat, None)
        baseline_value = getattr(baseline_stats, comparison.stat, None)

        if recent_value is None or baseline_value is None:
            return None
        if baseline_value == 0:
            return None

        change_pct = ((recent_value - baseline_value) / abs(baseline_value)) * 100

        # Compute z-score if we have enough history
        z_score = self._compute_zscore(
            comparison.metric_name,
            comparison.stat,
            change_pct,
        )

        return DecaySignal(
            metric_name=comparison.metric_name,
            recent_window=comparison.recent_window,
            baseline_window=comparison.baseline_window,
            recent_value=recent_value,
            baseline_value=baseline_value,
            change_pct=change_pct,
            z_score=z_score,
            recent_sample_count=recent_stats.sample_count,
            baseline_sample_count=baseline_stats.sample_count,
        )

    def _compute_zscore(
        self,
        metric_name: str,
        stat: str,
        change_pct: float,
    ) -> Optional[float]:
        """
        Compute z-score based on historical change percentages.

        Returns None if insufficient history.
        """
        key = f"{metric_name}:{stat}"

        with self._lock:
            if key not in self._history:
                self._history[key] = []

            history = self._history[key]
            history.append(change_pct)

            # Keep only recent history (last 100 observations)
            if len(history) > 100:
                self._history[key] = history[-100:]
                history = self._history[key]

            if len(history) < self._min_samples_for_zscore:
                return None

            # Compute z-score
            mean = sum(history) / len(history)
            variance = sum((x - mean) ** 2 for x in history) / len(history)
            if variance == 0:
                return None

            std_dev = math.sqrt(variance)
            return (change_pct - mean) / std_dev

    def get_signal_for_metric(
        self,
        metric_name: str,
        stat: str = "mean",
        recent_window: str = "1hour",
        baseline_window: str = "24hour",
        now_ns: int = None,
    ) -> Optional[DecaySignal]:
        """
        Get a single decay signal for a specific metric.

        Args:
            metric_name: Name of metric
            stat: Statistic to compare
            recent_window: Recent window name
            baseline_window: Baseline window name
            now_ns: Current timestamp

        Returns:
            DecaySignal or None if insufficient data
        """
        comparison = DecayComparison(
            metric_name=metric_name,
            stat=stat,
            recent_window=recent_window,
            baseline_window=baseline_window,
        )
        return self._compute_single_signal(
            comparison,
            now_ns or self._now_ns(),
        )

    def get_all_signals_for_metric(
        self,
        metric_name: str,
        now_ns: int = None,
    ) -> List[DecaySignal]:
        """
        Get all configured signals for a specific metric.

        Args:
            metric_name: Name of metric
            now_ns: Current timestamp

        Returns:
            List of DecaySignal for this metric
        """
        if now_ns is None:
            now_ns = self._now_ns()

        signals = []
        for comparison in self._comparisons:
            if comparison.metric_name == metric_name:
                signal = self._compute_single_signal(comparison, now_ns)
                if signal is not None:
                    signals.append(signal)

        return signals

    def clear_history(self) -> None:
        """Clear z-score computation history."""
        with self._lock:
            self._history.clear()


def format_decay_signals(signals: List[DecaySignal]) -> str:
    """
    Format decay signals for display.

    Args:
        signals: List of decay signals

    Returns:
        Formatted string (factual, no interpretation)
    """
    if not signals:
        return "No decay signals computed (insufficient data)"

    lines = ["Decay Signal Comparison:"]
    lines.append("-" * 70)

    for signal in signals:
        z_str = f"z={signal.z_score:+.2f}" if signal.z_score else "z=N/A"
        lines.append(
            f"  {signal.metric_name} [{signal.stat if hasattr(signal, 'stat') else 'value'}]: "
            f"{signal.recent_window}={signal.recent_value:.4f} vs "
            f"{signal.baseline_window}={signal.baseline_value:.4f} "
            f"({signal.change_pct:+.1f}% {z_str})"
        )

    return "\n".join(lines)
