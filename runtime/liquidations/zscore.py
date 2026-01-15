"""
Liquidation Z-Score Calculation

Measures liquidation rate deviation from baseline for regime classification.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)
- Observable metric, no interpretation or prediction

Z-Score Formula:
    Z = (current_rate - mean) / stddev

Where:
- current_rate: Liquidations per minute (recent window)
- mean: Average liquidations per minute (baseline window)
- stddev: Standard deviation of baseline

Used for regime classification:
- < 2.0: Normal liquidation activity (SIDEWAYS)
- ≥ 2.5: Elevated liquidation activity (EXPANSION)
"""

from collections import deque
from typing import Optional
import math


class LiquidationZScoreCalculator:
    """
    Liquidation Z-score calculator.

    Tracks liquidation events and calculates Z-score deviation from baseline.
    """

    def __init__(
        self,
        baseline_window_seconds: int = 3600,  # 60 minutes
        current_window_seconds: int = 60  # 1 minute
    ):
        """
        Initialize liquidation Z-score calculator.

        Args:
            baseline_window_seconds: Baseline window for mean/stddev (default 60 minutes)
            current_window_seconds: Current rate window (default 1 minute)
        """
        self.baseline_window_seconds = baseline_window_seconds
        self.current_window_seconds = current_window_seconds

        self._events = deque()  # (timestamp, quantity)

    def update(self, quantity: float, timestamp: float):
        """
        Record liquidation event.

        Args:
            quantity: Liquidation quantity
            timestamp: Unix timestamp
        """
        self._events.append((timestamp, quantity))

        # Remove events outside baseline window
        cutoff_time = timestamp - self.baseline_window_seconds
        while self._events and self._events[0][0] < cutoff_time:
            self._events.popleft()

    def get_zscore(self, current_timestamp: float) -> Optional[float]:
        """
        Calculate liquidation Z-score.

        Args:
            current_timestamp: Current time for window calculation

        Returns:
            Z-score, or 0.0 if no liquidations (baseline/neutral activity)
        """
        if not self._events:
            # No liquidations = baseline activity (Z-score 0.0)
            return 0.0

        # Calculate baseline statistics (full window)
        baseline_cutoff = current_timestamp - self.baseline_window_seconds
        baseline_events = [
            (ts, qty) for ts, qty in self._events
            if ts >= baseline_cutoff
        ]

        if not baseline_events:
            # No recent liquidations = baseline activity (Z-score 0.0)
            return 0.0

        # Baseline: Liquidations per minute
        baseline_duration_minutes = self.baseline_window_seconds / 60.0
        baseline_total = sum(qty for ts, qty in baseline_events)
        baseline_rate = baseline_total / baseline_duration_minutes

        # Calculate baseline mean and stddev
        # (For simplicity, using constant rate assumption)
        # In production, would calculate per-minute buckets
        mean_rate = baseline_rate
        stddev_rate = self._calculate_stddev(baseline_events, current_timestamp)

        if stddev_rate == 0:
            # No variance - return 0 if current matches baseline, else large Z
            return 0.0

        # Current rate: Liquidations in recent window
        current_cutoff = current_timestamp - self.current_window_seconds
        current_events = [
            qty for ts, qty in self._events
            if ts >= current_cutoff
        ]

        if not current_events:
            current_rate = 0.0
        else:
            current_duration_minutes = self.current_window_seconds / 60.0
            current_total = sum(current_events)
            current_rate = current_total / current_duration_minutes

        # Calculate Z-score
        z = (current_rate - mean_rate) / stddev_rate
        return z

    def _calculate_stddev(self, events, current_timestamp: float) -> float:
        """
        Calculate standard deviation of liquidation rate.

        Divides baseline window into 1-minute buckets and calculates stddev.

        Args:
            events: List of (timestamp, quantity) events
            current_timestamp: Current timestamp

        Returns:
            Standard deviation of per-minute rates
        """
        if not events:
            return 0.0

        # Divide into 1-minute buckets
        buckets = {}
        for ts, qty in events:
            bucket_id = int(ts) // 60
            if bucket_id not in buckets:
                buckets[bucket_id] = 0.0
            buckets[bucket_id] += qty

        if len(buckets) < 2:
            # Need at least 2 buckets for stddev
            return 0.0

        # Calculate mean and stddev
        rates = list(buckets.values())
        mean = sum(rates) / len(rates)
        variance = sum((r - mean) ** 2 for r in rates) / len(rates)
        stddev = math.sqrt(variance)

        return stddev

    def get_current_rate(self, current_timestamp: float) -> Optional[float]:
        """
        Get current liquidation rate (liquidations per minute).

        Args:
            current_timestamp: Current timestamp

        Returns:
            Liquidations per minute in recent window, or None if no events
        """
        current_cutoff = current_timestamp - self.current_window_seconds
        current_events = [
            qty for ts, qty in self._events
            if ts >= current_cutoff
        ]

        if not current_events:
            return None

        current_duration_minutes = self.current_window_seconds / 60.0
        current_total = sum(current_events)
        return current_total / current_duration_minutes
