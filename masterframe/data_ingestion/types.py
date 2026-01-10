"""
Data Type Definitions for Market Regime Masterframe

DEPRECATED: Individual event types moved to data_pipeline.normalized_events

This module now only contains SynchronizedData for time-aligned snapshots.
All event types must be imported from data_pipeline.normalized_events.

RULE: No mutable state in data structures.
RULE: All timestamps are Unix epoch in seconds (float).
"""

from dataclasses import dataclass
from typing import Tuple

# Import canonical event types
import sys
sys.path.append('d:/liquidation-trading')
from data_pipeline.normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent
)


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


# Re-export canonical types for backward compatibility
__all__ = [
    'SynchronizedData',
    'OrderbookEvent',
    'TradeEvent', 
    'LiquidationEvent',
]
