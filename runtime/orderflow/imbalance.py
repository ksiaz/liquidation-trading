"""
Orderflow Imbalance Calculation

Measures taker buy/sell volume ratio for regime classification.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)
- Observable metric, no interpretation or prediction

Orderflow Imbalance Formula:
    Imbalance = taker_buy_volume / (taker_buy_volume + taker_sell_volume)

Values:
- 0.50: Perfectly balanced (equal buy/sell)
- > 0.50: Buy-side dominant
- < 0.50: Sell-side dominant

Used for regime classification:
- < 0.18: Severely sell-dominant (error - should be checking deviation from 0.5)
- ≥ 0.35: Moderately buy-dominant

Note: Thresholds represent deviation from balance (0.5 ± threshold)
"""

from collections import deque
from typing import Optional


class OrderflowImbalanceCalculator:
    """
    Rolling window orderflow imbalance calculator.

    Tracks taker buy and sell volume over a time window.
    """

    def __init__(self, window_seconds: int = 30):
        """
        Initialize orderflow imbalance calculator.

        Args:
            window_seconds: Rolling window duration in seconds
        """
        self.window_seconds = window_seconds
        self._trades = deque()  # (timestamp, is_buyer_maker, volume)

    def update(self, is_buyer_maker: bool, volume: float, timestamp: float):
        """
        Update orderflow imbalance with new trade.

        Args:
            is_buyer_maker: True if buyer was maker (taker sell), False if seller was maker (taker buy)
            volume: Trade volume
            timestamp: Unix timestamp
        """
        # Add new trade
        self._trades.append((timestamp, is_buyer_maker, volume))

        # Remove trades outside window
        cutoff_time = timestamp - self.window_seconds
        while self._trades and self._trades[0][0] < cutoff_time:
            self._trades.popleft()

    def get_imbalance(self) -> Optional[float]:
        """
        Calculate current orderflow imbalance.

        Returns:
            Imbalance ratio (0 to 1), or None if no trades in window

        Interpretation (for reference only, not used in code):
        - 0.50: Balanced
        - 0.35-0.50: Slightly sell-dominant
        - 0.50-0.65: Slightly buy-dominant
        - > 0.65: Strongly buy-dominant
        - < 0.35: Strongly sell-dominant
        """
        if not self._trades:
            return None

        taker_buy_volume = 0.0
        taker_sell_volume = 0.0

        for ts, is_buyer_maker, volume in self._trades:
            if is_buyer_maker:
                # Buyer was maker → taker was seller
                taker_sell_volume += volume
            else:
                # Seller was maker → taker was buyer
                taker_buy_volume += volume

        total_volume = taker_buy_volume + taker_sell_volume
        if total_volume > 0:
            return taker_buy_volume / total_volume
        else:
            return None

    def get_deviation_from_balance(self) -> Optional[float]:
        """
        Get absolute deviation from balanced orderflow (0.5).

        Returns:
            Absolute deviation |imbalance - 0.5|, or None if no trades
        """
        imbalance = self.get_imbalance()
        if imbalance is not None:
            return abs(imbalance - 0.5)
        else:
            return None


class MultiWindowOrderflow:
    """
    Multi-window orderflow imbalance calculator.

    Maintains imbalance for multiple time windows.
    """

    def __init__(self):
        """Initialize multi-window orderflow calculators."""
        self.window_10s = OrderflowImbalanceCalculator(window_seconds=10)
        self.window_30s = OrderflowImbalanceCalculator(window_seconds=30)
        self.window_60s = OrderflowImbalanceCalculator(window_seconds=60)

    def update(self, is_buyer_maker: bool, volume: float, timestamp: float):
        """
        Update all orderflow windows with new trade.

        Args:
            is_buyer_maker: True if buyer was maker (taker sell)
            volume: Trade volume
            timestamp: Unix timestamp
        """
        self.window_10s.update(is_buyer_maker, volume, timestamp)
        self.window_30s.update(is_buyer_maker, volume, timestamp)
        self.window_60s.update(is_buyer_maker, volume, timestamp)

    def get_imbalance_30s(self) -> Optional[float]:
        """Get 30-second orderflow imbalance (primary for regime classification)."""
        return self.window_30s.get_imbalance()

    def get_imbalance_10s(self) -> Optional[float]:
        """Get 10-second orderflow imbalance."""
        return self.window_10s.get_imbalance()

    def get_imbalance_60s(self) -> Optional[float]:
        """Get 60-second orderflow imbalance."""
        return self.window_60s.get_imbalance()
