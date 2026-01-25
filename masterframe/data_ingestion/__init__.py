"""
Data Ingestion & Normalization Module

Provides time-aligned rolling buffers for all required data streams.

CANONICAL EVENT TYPES: All event types are now imported from 
data_pipeline.normalized_events (single source of truth).

INVARIANTS:
- Returns NULL until all buffers are warm
- Returns NULL if timestamps do not align within tolerance
- No forward-looking data access
- No interpolation of missing data
- All logic is deterministic
"""

import sys
sys.path.append('d:/liquidation-trading')

# Import canonical event types from DB layer
from data_pipeline.normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent,
    BookTickerEvent,
    generate_event_id,
)

# Import local modules
from .types import (
    SynchronizedData,
    # Legacy types for backward compatibility
    OrderbookSnapshot,
    AggressiveTrade,
    LiquidationEvent as LegacyLiquidationEvent,
    Kline,
)
from .rolling_buffer import RollingBuffer
from .data_synchronizer import DataSynchronizer

# Use legacy LiquidationEvent for backward compatibility
LiquidationEvent = LegacyLiquidationEvent

__all__ = [
    # Canonical event types (from data_pipeline)
    "OrderbookEvent",
    "TradeEvent",
    "CandleEvent",
    "BookTickerEvent",
    "generate_event_id",
    # Legacy types (backward compatibility)
    "OrderbookSnapshot",
    "AggressiveTrade",
    "LiquidationEvent",
    "Kline",
    # Local types
    "SynchronizedData",
    "RollingBuffer",
    "DataSynchronizer",
]
