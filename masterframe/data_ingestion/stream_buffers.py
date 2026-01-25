"""
Stream Buffers for Specific Data Types

Wrapper around RollingBuffer for type-specific operations.
Uses canonical event types from data_pipeline.normalized_events.
"""

import sys
sys.path.append('d:/liquidation-trading')

from typing import Optional, Tuple
from data_pipeline.normalized_events import (
    OrderbookEvent, TradeEvent, LiquidationEvent, CandleEvent
)
from .rolling_buffer import RollingBuffer


class OrderbookBuffer:
    """
    Buffer for orderbook snapshots with time alignment awareness.
    """
    
    def __init__(self, max_age_seconds: float = 10.0):
        """
        Initialize orderbook buffer.
        
        Args:
            max_age_seconds: Maximum age of orderbook before discarded
        """
        self._buffer = RollingBuffer[OrderbookEvent](
            max_size=100,
            min_size=1,
            max_age_seconds=max_age_seconds
        )
    
    def push(self, snapshot: OrderbookEvent) -> None:
        """Add new orderbook snapshot."""
        self._buffer.push(snapshot, snapshot.timestamp)
    
    def is_warm(self) -> bool:
        """Check if buffer has data."""
        return self._buffer.is_warm()
    
    def get_latest(self) -> Optional[OrderbookEvent]:
        """Get most recent snapshot."""
        return self._buffer.get_latest()
    
    def clear(self) -> None:
        """Clear all snapshots."""
        self._buffer.clear()


class TradeBuffer:
    """
    Buffer for trades with windowed access.
    """
    
    def __init__(self, max_age_seconds: float = 60.0):
        """
        Initialize trade buffer.
        
        Args:
            max_age_seconds: Maximum age of trades kept in buffer
        """
        self._buffer = RollingBuffer[TradeEvent](
            max_size=1000,
            min_size=10,
            max_age_seconds=max_age_seconds
        )
    
    def push(self, trade: TradeEvent) -> None:
        """Add new trade."""
        self._buffer.push(trade, trade.timestamp)
    
    def is_warm(self) -> bool:
        """Check if buffer is warm."""
        return self._buffer.is_warm()
    
    def get_trades_in_window(self, window_seconds: float, reference_time: float) -> Optional[Tuple[TradeEvent, ...]]:
        """
        Get all trades within time window ending at reference_time.
        
        Args:
            window_seconds: Size of time window
            reference_time: End time of window
            
        Returns:
            Tuple of trades or None if insufficient data
        """
        return self._buffer.get_items_in_window(window_seconds, reference_time)
    
    def clear(self) -> None:
        """Clear all trades."""
        self._buffer.clear()


class LiquidationBuffer:
    """
    Buffer for liquidation events.
    
    RULE: Stores forced liquidations.
    RULE: Used for liquidation z-score calculation.
    """
    
    # Configuration
    MAX_LIQUIDATIONS = 500
    MIN_LIQUIDATIONS = 5
    MAX_AGE_SECONDS = 3600.0  # Keep last hour for z-score baseline
    
    def __init__(self):
        self._buffer = RollingBuffer[LiquidationEvent](
            max_size=self.MAX_LIQUIDATIONS,
            min_size=self.MIN_LIQUIDATIONS,
            max_age_seconds=self.MAX_AGE_SECONDS
        )
    
    def push(self, event: LiquidationEvent) -> None:
        """Add liquidation event."""
        self._buffer.push(event, event.timestamp)
    
    def is_warm(self) -> bool:
        """Check if buffer has sufficient liquidations."""
        return self._buffer.is_warm()
    
    def get_liquidations_in_window(self, window_seconds: float, reference_time: float) -> Optional[Tuple[LiquidationEvent, ...]]:
        """
        Get liquidations within time window.
        
        Args:
            window_seconds: Size of window
            reference_time: End of window
        
        Returns:
            Liquidations in window if warm, None otherwise
        """
        return self._buffer.get_items_in_window(window_seconds, reference_time)
    
    def clear(self) -> None:
        """Clear all liquidations."""
        self._buffer.clear()


class KlineBuffer:
    """
    Buffer for OHLCV klines (candlesticks).

    RULE: Stores klines for specific interval (1m or 5m).
    RULE: Used for ATR and VWAP calculations.
    """
    
    # Configuration per interval
    MAX_KLINES = 100  # Keep last 100 candles
    MIN_KLINES_1M = 30  # Need 30 x 1-minute candles for ATR(30m)
    MIN_KLINES_5M = 10  # Need 10 x 5-minute candles
    MAX_AGE_SECONDS = 7200.0  # Keep last 2 hours
    
    def __init__(self, interval: str):
        """
        Initialize kline buffer for specific interval.
        
        Args:
            interval: '1m' or '5m'
        
        RULE: interval must be exactly '1m' or '5m'.
        """
        if interval not in ('1m', '5m'):
            raise ValueError(f"Invalid interval: {interval}. Must be '1m' or '5m'.")
        
        self.interval = interval
        
        # Set min_size based on interval
        min_size = self.MIN_KLINES_1M if interval == '1m' else self.MIN_KLINES_5M
        
        self._buffer = RollingBuffer[CandleEvent](
            max_size=self.MAX_KLINES,
            min_size=min_size,
            max_age_seconds=self.MAX_AGE_SECONDS
        )
    
    def push(self, kline: CandleEvent) -> None:
        """
        Add kline to buffer.
        
        RULE: kline.interval must match buffer interval.
        """
        if kline.interval != self.interval:
            raise ValueError(
                f"CandleEvent interval mismatch: expected {self.interval}, got {kline.interval}"
            )
        
        self._buffer.push(kline, kline.timestamp)
    
    def is_warm(self) -> bool:
        """Check if buffer has sufficient klines."""
        return self._buffer.is_warm()
    
    def get_latest(self) -> Optional[CandleEvent]:
        """Get most recent kline if warm."""
        return self._buffer.get_latest()
    
    def get_all(self) -> Optional[Tuple[CandleEvent, ...]]:
        """Get all klines if warm."""
        return self._buffer.get_items()
    
    def clear(self) -> None:
        """Clear all klines."""
        self._buffer.clear()
