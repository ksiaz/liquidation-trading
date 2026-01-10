"""
Feed Synchronization Layer

Wraps DataSynchronizer for replay to ensure identical synchronization logic.

INVARIANTS:
- All required streams must be present
- Timestamps within tolerance window
- No interpolation/backfilling
- Fail-closed behavior

GOAL:
Replay uses IDENTICAL synchronization logic as live trading.
"""

from typing import Optional
from masterframe.data_ingestion import DataSynchronizer, SynchronizedData
from .event_loop import Event


class ReplayDataSync:
    """
    Wrapper around DataSynchronizer for replay.
    
    RULE: Reuses live synchronization logic.
    RULE: Same behavior as production.
    RULE: Fail-closed on missing/misaligned data.
    """
    
    def __init__(self, symbol: str = "BTCUSDT"):
        """
        Initialize replay synchronizer.
        
        Args:
            symbol: Trading symbol
        """
        self.sync = DataSynchronizer(symbol)
        self.symbol = symbol
    
    def handle_event(self, event: Event) -> None:
        """
        Process event and push to synchronizer.
        
        Routes events to appropriate push methods based on type.
        
        Args:
            event: Event from feed adapter
        """
        data = event.data
        
        if event.event_type == 'orderbook':
            self.sync.push_orderbook(data)
        elif event.event_type == 'trade':
            self.sync.push_trade(data)
        elif event.event_type == 'liquidation':
            self.sync.push_liquidation(data)
        elif event.event_type.startswith('kline_'):
            # Extract interval from event type (e.g., 'kline_1m' -> '1m')
            self.sync.push_kline(data)
        else:
            # Unknown event type - ignore
            pass
    
    def get_snapshot(self, timestamp: float) -> Optional[SynchronizedData]:
        """
        Get aligned snapshot at timestamp.
        
        RULE: All required streams must be aligned.
        RULE: Return None if missing/misaligned.
        
        Args:
            timestamp: Target timestamp
            
        Returns:
            SynchronizedData if aligned, None otherwise
        """
        return self.sync.get_aligned_snapshot(timestamp)
    
    def is_warm(self) -> bool:
        """
        Check if all buffers are warm.
        
        Returns:
            True if ready for evaluation
        """
        return (
            self.sync.orderbook_buffer.is_warm() and
            self.sync.trade_buffer.is_warm() and
            self.sync.liquidation_buffer.is_warm() and
            self.sync.kline_buffer_1m.is_warm() and
            self.sync.kline_buffer_5m.is_warm()
        )
    
    def get_all_klines_1m(self):
        """Get all 1m klines for ATR calculation."""
        return self.sync.get_all_klines_1m()
    
    def get_all_klines_5m(self):
        """Get all 5m klines for ATR calculation."""
        return self.sync.get_all_klines_5m()
    
    def __repr__(self) -> str:
        warm_status = "warm" if self.is_warm() else "warming"
        return f"ReplayDataSync(symbol={self.symbol}, {warm_status})"
