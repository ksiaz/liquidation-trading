"""
Data Pipeline Package

Handles live data acquisition and storage.

Components:
- live_feeds: Exchange websocket connectors
- normalized_events: Canonical event schemas
- normalizer: Event normalization layer
- (future) storage: PostgreSQL persistence
- (future) replay: Historical data emission

SCOPE: Data infrastructure ONLY - no trading logic.
"""

from .live_feeds import (
    LiveOrderbookSnapshot,
    LiveTrade,
    LiveLiquidation,
    LiveKline,
    BinanceFuturesFeeds,
)
from .normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent,
)
from .normalizer import EventNormalizer

__all__ = [
    # Live feeds
    'LiveOrderbookSnapshot',
    'LiveTrade',
    'LiveLiquidation',
    'LiveKline',
    'BinanceFuturesFeeds',
    # Normalized events
    'OrderbookEvent',
    'TradeEvent',
    'LiquidationEvent',
    'CandleEvent',
    'EventNormalizer',
]
