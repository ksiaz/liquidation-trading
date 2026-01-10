"""
ATR (Average True Range) Calculator

ATR measures market volatility using True Range.

True Range = max(
    high - low,
    |high - previous_close|,
    |low - previous_close|
)

ATR = 14-period EMA of True Range

RULES:
- Fixed 14-period window
- Returns None until 14 candles available
- No smoothing beyond EMA
- Deterministic calculation
"""

from typing import Optional, Tuple, List
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import Kline


class ATRCalculator:
    """
    Calculates ATR for specific kline interval.
    
    INVARIANT: Uses 14-period EMA.
    INVARIANT: Returns None until 14 candles available.
    """
    
    PERIOD = 14  # Standard ATR period
    SMOOTHING = 2.0 / (PERIOD + 1)  # EMA smoothing factor
    
    def __init__(self, interval: str):
        """
        Initialize ATR calculator for specific interval.
        
        Args:
            interval: Kline interval ('1m', '5m', or '30m')
        
        RULE: interval must match klines provided to update().
        """
        if interval not in ('1m', '5m', '30m'):
            raise ValueError(f"Invalid interval: {interval}. Must be '1m', '5m', or '30m'.")
        
        self.interval = interval
        self._prev_close: Optional[float] = None
        self._atr: Optional[float] = None
        self._tr_history: List[float] = []  # For initial SMA
    
    def update(self, klines: Tuple[Kline, ...]) -> None:
        """
        Update ATR with new klines.
        
        Args:
            klines: All available klines for this interval
        
        RULE: Processes klines in chronological order.
        RULE: Returns None until 14 klines available.
        """
        if not klines:
            return
        
        # Process each kline in order
        for kline in klines:
            if kline.interval != self.interval:
                raise ValueError(
                    f"Kline interval mismatch: expected {self.interval}, got {kline.interval}"
                )
            
            # Calculate True Range
            tr = self._calculate_true_range(
                high=kline.high,
                low=kline.low,
                prev_close=self._prev_close
            )
            
            # Update ATR
            if self._atr is None:
                # Building initial history for first ATR calculation
                self._tr_history.append(tr)
                
                # Once we have PERIOD values, calculate initial ATR as SMA
                if len(self._tr_history) >= self.PERIOD:
                    self._atr = sum(self._tr_history[-self.PERIOD:]) / self.PERIOD
                    self._tr_history.clear()  # Free memory
            else:
                # Use EMA formula: ATR = (TR * smoothing) + (prev_ATR * (1 - smoothing))
                self._atr = (tr * self.SMOOTHING) + (self._atr * (1 - self.SMOOTHING))
            
            # Update previous close for next iteration
            self._prev_close = kline.close
    
    def _calculate_true_range(
        self,
        high: float,
        low: float,
        prev_close: Optional[float]
    ) -> float:
        """
        Calculate True Range for current candle.
        
        Args:
            high: Current high
            low: Current low
            prev_close: Previous close (None for first candle)
        
        Returns:
            True Range value
        
        RULE: If no previous close, TR = high - low.
        """
        if prev_close is None:
            # First candle - use high - low
            return high - low
        
        # True Range = max of three values
        return max(
            high - low,                  # Current range
            abs(high - prev_close),      # Gap up
            abs(low - prev_close)        # Gap down
        )
    
    def get_atr(self) -> Optional[float]:
        """
        Get current ATR value.
        
        Returns:
            ATR if available (>=14 candles processed), None otherwise
        
        RULE: Returns None until PERIOD candles available.
        """
        return self._atr
    
    def reset(self) -> None:
        """Reset ATR calculator to initial state."""
        self._prev_close = None
        self._atr = None
        self._tr_history.clear()
