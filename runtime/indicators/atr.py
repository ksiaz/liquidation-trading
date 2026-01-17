"""
ATR (Average True Range) Calculation

Multi-timeframe ATR for volatility measurement.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VI (Threshold Derivation)
- Observable metric, no interpretation or prediction

ATR Formula:
    True Range (TR) = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR = EMA(TR, period)

Used for:
- Volatility-adjusted thresholds (e.g., displacement ≥ 0.5 × ATR)
- Regime classification (ATR compression/expansion)
"""

from collections import deque
from typing import Optional


class ATRCalculator:
    """
    ATR calculator using exponential moving average of true range.

    Tracks high, low, close for true range calculation.
    """

    def __init__(self, period: int, smoothing: float = 2.0):
        """
        Initialize ATR calculator.

        Args:
            period: ATR period (e.g., 14 for ATR(14))
            smoothing: EMA smoothing factor (default 2.0)
        """
        self.period = period
        self.smoothing = smoothing
        self.alpha = smoothing / (period + 1)  # EMA smoothing constant

        self._prev_close: Optional[float] = None
        self._atr: Optional[float] = None
        self._sample_count = 0

    def update(self, high: float, low: float, close: float) -> Optional[float]:
        """
        Update ATR with new candle data.

        Args:
            high: Period high
            low: Period low
            close: Period close

        Returns:
            Current ATR if available, None otherwise
        """
        # Calculate true range
        if self._prev_close is not None:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close)
            )
        else:
            # First sample - use high-low only
            tr = high - low

        # Update ATR using EMA
        if self._atr is None:
            # Initialize ATR with first TR
            self._atr = tr
        else:
            # EMA update: ATR = α × TR + (1 - α) × ATR_prev
            self._atr = self.alpha * tr + (1 - self.alpha) * self._atr

        self._prev_close = close
        self._sample_count += 1

        # Return ATR if enough samples accumulated
        if self._sample_count >= self.period:
            return self._atr
        else:
            return None

    def get(self) -> Optional[float]:
        """Get current ATR value."""
        if self._sample_count >= self.period:
            return self._atr
        else:
            return None

    def reset(self):
        """Reset ATR calculator."""
        self._prev_close = None
        self._atr = None
        self._sample_count = 0


class MultiTimeframeATR:
    """
    Multi-timeframe ATR calculator.

    Maintains ATR for multiple timeframes simultaneously.
    """

    def __init__(self, period: int = 14):
        """
        Initialize multi-timeframe ATR calculators.

        Args:
            period: ATR period (default 14). For testing, use smaller values like 3-5.
        """
        # ATR on 5-minute candles
        self.atr_5m = ATRCalculator(period=period)
        # ATR on 30-minute candles
        self.atr_30m = ATRCalculator(period=period)

        # Candle aggregation state
        self._candle_5m: Optional[dict] = None
        self._candle_30m: Optional[dict] = None

    def update_trade(self, price: float, timestamp: float):
        """
        Update ATR calculators with trade price.

        Aggregates trades into 5m and 30m candles, then updates ATR.

        Args:
            price: Trade price
            timestamp: Unix timestamp
        """
        # Determine candle boundaries
        candle_5m_ts = (int(timestamp) // 300) * 300  # 5-minute boundary
        candle_30m_ts = (int(timestamp) // 1800) * 1800  # 30-minute boundary

        # Update 5-minute candle
        if self._candle_5m is None or self._candle_5m['timestamp'] != candle_5m_ts:
            # Close previous candle
            if self._candle_5m is not None:
                self.atr_5m.update(
                    high=self._candle_5m['high'],
                    low=self._candle_5m['low'],
                    close=self._candle_5m['close']
                )
            # Start new candle
            self._candle_5m = {
                'timestamp': candle_5m_ts,
                'high': price,
                'low': price,
                'close': price
            }
        else:
            # Update current candle
            self._candle_5m['high'] = max(self._candle_5m['high'], price)
            self._candle_5m['low'] = min(self._candle_5m['low'], price)
            self._candle_5m['close'] = price

        # Update 30-minute candle
        if self._candle_30m is None or self._candle_30m['timestamp'] != candle_30m_ts:
            # Close previous candle
            if self._candle_30m is not None:
                self.atr_30m.update(
                    high=self._candle_30m['high'],
                    low=self._candle_30m['low'],
                    close=self._candle_30m['close']
                )
            # Start new candle
            self._candle_30m = {
                'timestamp': candle_30m_ts,
                'high': price,
                'low': price,
                'close': price
            }
        else:
            # Update current candle
            self._candle_30m['high'] = max(self._candle_30m['high'], price)
            self._candle_30m['low'] = min(self._candle_30m['low'], price)
            self._candle_30m['close'] = price

    def get_atr_5m(self) -> Optional[float]:
        """Get ATR(5m) value."""
        return self.atr_5m.get()

    def get_atr_30m(self) -> Optional[float]:
        """Get ATR(30m) value."""
        return self.atr_30m.get()

    def get_ratio(self) -> Optional[float]:
        """
        Get ATR ratio (5m / 30m).

        Used for regime classification:
        - Ratio < 0.80: Volatility compression (SIDEWAYS)
        - Ratio ≥ 1.0: Volatility expansion (EXPANSION)

        Returns:
            ATR ratio if both timeframes available, None otherwise
        """
        atr_5m = self.atr_5m.get()
        atr_30m = self.atr_30m.get()

        if atr_5m is not None and atr_30m is not None and atr_30m > 0:
            return atr_5m / atr_30m
        else:
            return None
