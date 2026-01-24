"""
Binance Data Collection.

Provides funding rate and spot price data from Binance for cross-exchange analysis.
Used for HLP25 Part 1 (funding lead) and Part 8 (spot-perp basis) validation.
"""

from .client import BinanceClient

__all__ = ['BinanceClient']
