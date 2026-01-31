"""
Data Storage Package.

Provides append-only raw data storage and retrieval:
- ColdStorage: SQLite-based historical data storage
- DataExporter: Export data for backtesting

HLP24 Components.
"""

from .cold_storage import (
    ColdStorage,
    MarketSnapshot,
    TradeRecord,
    StorageConfig,
    QueryResult,
)

__all__ = [
    'ColdStorage',
    'MarketSnapshot',
    'TradeRecord',
    'StorageConfig',
    'QueryResult',
]
