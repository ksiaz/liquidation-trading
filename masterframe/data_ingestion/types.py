"""
Data Type Definitions for Market Regime Masterframe

Contains:
- Legacy types for backward compatibility (OrderbookSnapshot, AggressiveTrade, Kline)
- SynchronizedData for time-aligned snapshots
- Re-exports of canonical types from data_pipeline.normalized_events

RULE: No mutable state in data structures.
RULE: All timestamps are Unix epoch in seconds (float).
"""

from dataclasses import dataclass
from typing import Tuple, Optional

# Import canonical event types
import sys
sys.path.append('d:/liquidation-trading')
from data_pipeline.normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent as CanonicalLiquidationEvent,
    CandleEvent,
)


# =============================================================================
# LEGACY TYPES - For backward compatibility with existing tests and modules
# =============================================================================

@dataclass(frozen=True)
class OrderbookSnapshot:
    """
    Legacy orderbook snapshot type for backward compatibility.

    Used by: orderbook_zoning, tests
    """
    timestamp: float
    bids: Tuple[Tuple[float, float], ...]  # ((price, qty), ...)
    asks: Tuple[Tuple[float, float], ...]
    mid_price: float


@dataclass(frozen=True)
class AggressiveTrade:
    """
    Legacy aggressive trade type for backward compatibility.

    Used by: metrics, orderbook_zoning, tests
    """
    timestamp: float
    price: float
    quantity: float
    is_buyer_aggressor: bool


@dataclass(frozen=True)
class LiquidationEvent:
    """
    Legacy liquidation event type for backward compatibility.

    Used by: tests
    """
    timestamp: float
    symbol: str
    side: str
    quantity: float
    price: float
    value_usd: Optional[float] = None


@dataclass(frozen=True)
class Kline:
    """
    Legacy kline (candlestick) type for backward compatibility.

    Used by: tests, metrics
    """
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str  # '1m', '5m', etc.


@dataclass(frozen=True)
class SynchronizedData:
    """
    Time-aligned snapshot of all required data streams.
    
    INVARIANT: All data timestamps are aligned within tolerance.
    INVARIANT: Only created when all buffers are warm.
    
    This is the ONLY data structure that should be passed to downstream
    modules (regime classifier, strategies, etc.).
    
    NOTE: Uses canonical event types from data_pipeline.normalized_events
    """
    timestamp: float  # Reference timestamp for alignment
    orderbook: OrderbookEvent
    trades: Tuple[TradeEvent, ...]  # Recent trades in time window
    liquidations: Tuple[LiquidationEvent, ...]  # Recent liquidations
    kline_1m: 'CandleEvent'  # Forward reference to avoid circular import
    kline_5m: 'CandleEvent'


# Re-export types
__all__ = [
    # Legacy types (backward compatibility)
    'OrderbookSnapshot',
    'AggressiveTrade',
    'LiquidationEvent',
    'Kline',
    # Synchronized data
    'SynchronizedData',
    # Canonical types
    'OrderbookEvent',
    'TradeEvent',
    'CandleEvent',
]
