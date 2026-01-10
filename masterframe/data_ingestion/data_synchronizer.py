"""
Data Synchronizer - Time-Aligned Data Streams

Data Synchronizer Module

Synchronizes multiple rolling buffers for time-aligned data snapshots.

Uses canonical event types from data_pipeline.normalized_events.
"""

import sys
sys.path.append('d:/liquidation-trading')

from typing import Optional, Tuple
from data_pipeline.normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent
)
from .types import SynchronizedData
from .rolling_buffer import (
    OrderbookBuffer,
    TradeBuffer,
    LiquidationBuffer,
    KlineBuffer,
)


class DataSynchronizer:
    """
    Aligns all data streams by timestamp.
    
    RULE: If timestamps do not align within tolerance, returns None.
    RULE: If any stream not warm, returns None.
    RULE: Never uses forward-looking data.
    
    The synchronizer is the ONLY interface for accessing aligned data.
    Downstream modules must NEVER access raw streams directly.
    """
    
    # Timestamp alignment tolerance in seconds
    TIMESTAMP_TOLERANCE_SECONDS = 1.0
    
    # Time windows for aggregating recent trades/liquidations
    TRADES_WINDOW_SECONDS = 30.0  # Last 30 seconds of trades
    LIQUIDATIONS_WINDOW_SECONDS = 60.0  # Last 60 seconds of liquidations
    
    def __init__(self, symbol: str):
        """
        Initialize data synchronizer for a symbol.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        
        # Initialize all stream buffers
        self.orderbook_buffer = OrderbookBuffer()
        self.trade_buffer = TradeBuffer()
        self.liquidation_buffer = LiquidationBuffer()
        self.kline_buffer_1m = KlineBuffer('1m')
        self.kline_buffer_5m = KlineBuffer('5m')
    
    def push_orderbook(self, snapshot: OrderbookEvent) -> None:
        """
        Add orderbook snapshot.
        
        RULE: Raw snapshot is NOT accessible to strategies.
        RULE: Only synchronized data is exposed.
        """
        self.orderbook_buffer.push(snapshot)
    
    def push_trade(self, trade: TradeEvent) -> None:
        """Add aggressive trade."""
        self.trade_buffer.push(trade)
    
    def push_liquidation(self, event: LiquidationEvent) -> None:
        """Add liquidation event."""
        self.liquidation_buffer.push(event)
    
    def push_kline(self, kline: CandleEvent) -> None:
        """
        Add kline to appropriate buffer.
        
        RULE: Routes to correct buffer based on kline interval field.
        """
        # Note: CandleEvent doesn't have  interval field like old Kline did
        # Will need to check if this method is even used or needs refactoring
        if hasattr(kline, 'interval'):
            if kline.interval == '1m':
                self.kline_buffer_1m.push(kline)
            elif kline.interval == '5m':
                self.kline_buffer_5m.push(kline)
    
    def get_all_klines_1m(self) -> Optional[Tuple[CandleEvent, ...]]:
        """
        Get all 1m klines if warm.
        
        Returns:
            All 1m klines if warm, None otherwise
        
        RULE: Used by ATR calculator.
        """
        return self.kline_buffer_1m.get_all()
    
    def get_all_klines_5m(self) -> Optional[Tuple[Kline, ...]]:
        """
        Get all 5m klines if warm.
        
        Returns:
            All 5m klines if warm, None otherwise
        
        RULE: Used by ATR calculator.
        """
        return self.kline_buffer_5m.get_all()
    
    def get_aligned_snapshot(self, current_time: float) -> Optional[SynchronizedData]:
        """
        Get time-aligned snapshot of all data streams.
        
        Args:
            current_time: Reference timestamp (typically current time)
        
        Returns:
            SynchronizedData if all conditions met, None otherwise
        
        RULE 1: Returns None if any buffer is not warm.
        RULE 2: Returns None if timestamps do not align within tolerance.
        RULE 3: Never interpolates or guesses missing data.
        
        This is the ONLY method that should be used by downstream modules.
        """
        # Check 1: All buffers must be warm
        if not self._all_buffers_warm():
            return None
        
        # Get latest data from each stream
        orderbook = self.orderbook_buffer.get_latest()
        kline_1m = self.kline_buffer_1m.get_latest()
        kline_5m = self.kline_buffer_5m.get_latest()
        
        # These should not be None since buffers are warm, but check defensively
        if orderbook is None or kline_1m is None or kline_5m is None:
            return None
        
        # Get recent trades and liquidations in time windows
        trades = self.trade_buffer.get_trades_in_window(
            self.TRADES_WINDOW_SECONDS,
            current_time
        )
        liquidations = self.liquidation_buffer.get_liquidations_in_window(
            self.LIQUIDATIONS_WINDOW_SECONDS,
            current_time
        )
        
        if trades is None or liquidations is None:
            return None
        
        # Check 2: Timestamps must align within tolerance
        timestamps = [
            orderbook.timestamp,
            kline_1m.timestamp,
            kline_5m.timestamp,
        ]
        
        if not self._timestamps_aligned(timestamps, current_time):
            return None
        
        # All checks passed - return synchronized data
        return SynchronizedData(
            timestamp=current_time,
            orderbook=orderbook,
            trades=trades,
            liquidations=liquidations,
            kline_1m=kline_1m,
            kline_5m=kline_5m,
        )
    
    def _all_buffers_warm(self) -> bool:
        """
        Check if all buffers have sufficient data.
        
        Returns:
            True only if ALL buffers are warm
        
        RULE: All buffers must be warm before any data is returned.
        """
        return (
            self.orderbook_buffer.is_warm() and
            self.trade_buffer.is_warm() and
            self.liquidation_buffer.is_warm() and
            self.kline_buffer_1m.is_warm() and
            self.kline_buffer_5m.is_warm()
        )
    
    def _timestamps_aligned(self, timestamps: list[float], reference: float) -> bool:
        """
        Check if all timestamps are aligned within tolerance.
        
        Args:
            timestamps: List of timestamps to check
            reference: Reference timestamp (current_time)
        
        Returns:
            True if all timestamps within TIMESTAMP_TOLERANCE_SECONDS of reference
        
        RULE: If ANY timestamp is outside tolerance, returns False.
        RULE: No interpolation or guessing of timestamps.
        """
        for ts in timestamps:
            time_diff = abs(ts - reference)
            if time_diff > self.TIMESTAMP_TOLERANCE_SECONDS:
                return False
        
        return True
    
    def clear_all(self) -> None:
        """
        Clear all buffers.
        
        RULE: After clear, all buffers must warm up again.
        """
        self.orderbook_buffer.clear()
        self.trade_buffer.clear()
        self.liquidation_buffer.clear()
        self.kline_buffer_1m.clear()
        self.kline_buffer_5m.clear()
    
    def get_status(self) -> dict:
        """
        Get synchronizer status for debugging.
        
        Returns:
            Dict with buffer warm status
        """
        return {
            'symbol': self.symbol,
            'orderbook_warm': self.orderbook_buffer.is_warm(),
            'trade_warm': self.trade_buffer.is_warm(),
            'liquidation_warm': self.liquidation_buffer.is_warm(),
            'kline_1m_warm': self.kline_buffer_1m.is_warm(),
            'kline_5m_warm': self.kline_buffer_5m.is_warm(),
            'all_warm': self._all_buffers_warm(),
        }
