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
from .types import SynchronizedData
from .rolling_buffer import RollingBuffer
from .data_synchronizer import DataSynchronizer

__all__ = [
    # Canonical event types (from data_pipeline)
    "OrderbookEvent",
    "TradeEvent",
    "LiquidationEvent",
    "CandleEvent",
    "BookTickerEvent",
    "generate_event_id",
    # Local types
    "SynchronizedData",
    "RollingBuffer",
    "DataSynchronizer",
]
