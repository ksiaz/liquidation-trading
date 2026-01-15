"""
Hyperliquid Integration Module

Components:
- client.py: WebSocket/REST client for Hyperliquid API
- position_tracker.py: Track positions and liquidation proximity
- types.py: Data structures for Hyperliquid events
"""

from .types import (
    HyperliquidPosition,
    LiquidationProximity,
    PositionEvent,
    WalletState
)
from .client import HyperliquidClient
from .position_tracker import PositionTracker

__all__ = [
    'HyperliquidClient',
    'PositionTracker',
    'HyperliquidPosition',
    'LiquidationProximity',
    'PositionEvent',
    'WalletState'
]
