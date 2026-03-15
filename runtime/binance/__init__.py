"""
Binance Data Collection.

Provides funding rate and spot price data from Binance for cross-exchange analysis.
Used for HLP25 Part 1 (funding lead) and Part 8 (spot-perp basis) validation.

Components:
- BinanceClient: Low-level API client for fetching data
- BinanceCollector: Background service for continuous collection
"""

from .client import BinanceClient, FundingInfo, SpotPrice
from .collector import (
    BinanceCollector,
    CollectorConfig,
    CollectorStats,
    CollectorState,
)
from .data_provider import BinanceDataProvider

__all__ = [
    'BinanceClient',
    'FundingInfo',
    'SpotPrice',
    'BinanceCollector',
    'CollectorConfig',
    'CollectorStats',
    'CollectorState',
    'BinanceDataProvider',
]
