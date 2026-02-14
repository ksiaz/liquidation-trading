"""
VWAP (Volume-Weighted Average Price) Calculation

Session-anchored VWAP for regime classification.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)
- Observable metric, no interpretation or prediction

VWAP Formula:
    VWAP = Σ(price × volume) / Σ(volume)

Reset at session start (UTC 00:00).
"""

from collections import deque
from typing import Optional


class VWAPCalculator:
    """
    Session-anchored VWAP calculator.

    Accumulates price × volume and volume over the session.
    Resets at session boundary.
    """

    def __init__(self, session_start_hour: int = 0):
        """
        Initialize VWAP calculator.

        Args:
            session_start_hour: Hour (UTC) when session resets (default 0 = midnight)
        """
        self.session_start_hour = session_start_hour
        self._cumulative_pv = 0.0  # Σ(price × volume)
        self._cumulative_p2v = 0.0  # Σ(price² × volume)
        self._cumulative_volume = 0.0  # Σ(volume)
        self._last_session_day = None  # Track session day for reset

    def update(self, price: float, volume: float, timestamp: float) -> Optional[float]:
        """
        Update VWAP with new price/volume observation.

        Args:
            price: Trade price
            volume: Trade volume
            timestamp: Unix timestamp

        Returns:
            Current VWAP if volume accumulated, None otherwise
        """
        # Check if session boundary crossed
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        current_session_day = dt.date() if dt.hour >= self.session_start_hour else (dt.date() - dt.resolution)

        if self._last_session_day is None:
            self._last_session_day = current_session_day
        elif current_session_day != self._last_session_day:
            # Session boundary crossed - reset
            self._cumulative_pv = 0.0
            self._cumulative_p2v = 0.0
            self._cumulative_volume = 0.0
            self._last_session_day = current_session_day

        # Accumulate price × volume, price² × volume, and volume
        self._cumulative_pv += price * volume
        self._cumulative_p2v += price * price * volume
        self._cumulative_volume += volume

        # Calculate VWAP
        if self._cumulative_volume > 0:
            return self._cumulative_pv / self._cumulative_volume
        else:
            return None

    def get_vwap(self) -> Optional[float]:
        """
        Get current VWAP value.

        Returns:
            Current VWAP if volume accumulated, None otherwise
        """
        if self._cumulative_volume > 0:
            return self._cumulative_pv / self._cumulative_volume
        else:
            return None

    def get_distance(self, current_price: float) -> Optional[float]:
        """
        Get absolute distance from current price to VWAP.

        Args:
            current_price: Current market price

        Returns:
            Absolute distance |price - VWAP|, or None if VWAP not available
        """
        if self._cumulative_volume > 0:
            vwap = self._cumulative_pv / self._cumulative_volume
            return abs(current_price - vwap)
        else:
            return None

    def get_stddev(self) -> Optional[float]:
        """
        Get VWAP standard deviation.

        σ = sqrt(Σ(price² × volume) / Σ(volume) - VWAP²)

        Returns:
            Standard deviation if volume accumulated and σ > 0, None otherwise
        """
        if self._cumulative_volume <= 0:
            return None
        vwap = self._cumulative_pv / self._cumulative_volume
        variance = self._cumulative_p2v / self._cumulative_volume - vwap * vwap
        if variance <= 0:
            return None
        return variance ** 0.5

    def get_z(self, current_price: float) -> Optional[float]:
        """
        Get signed z-score of current price relative to VWAP.

        vwap_z = (price - VWAP) / σ
        Positive = above VWAP, negative = below.

        Args:
            current_price: Current market price

        Returns:
            Signed z-score, or None if VWAP or σ not available
        """
        stddev = self.get_stddev()
        if stddev is None:
            return None
        vwap = self._cumulative_pv / self._cumulative_volume
        return (current_price - vwap) / stddev

    def reset(self):
        """Reset VWAP calculator (manual session boundary)."""
        self._cumulative_pv = 0.0
        self._cumulative_p2v = 0.0
        self._cumulative_volume = 0.0
        self._last_session_day = None
