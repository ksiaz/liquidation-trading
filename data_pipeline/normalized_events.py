"""
Normalized Event Schemas

Canonical schemas for database storage.

SCOPE: Schema definition ONLY.
- No processing
- No derived metrics
- Preserve all fields
- 1:1 mapping from live events

PRINCIPLE: Data correctness > completeness > performance
"""

import json
import uuid
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class OrderbookEvent:
    """
    Normalized orderbook snapshot for storage.
    
    Fields:
        event_id: Unique identifier (UUID)
        timestamp: Exchange timestamp (seconds)
        receive_time: Local receive timestamp (seconds)
        symbol: Trading pair
        bids: JSON string of bid levels [[price, qty], ...]
        asks: JSON string of ask levels [[price, qty], ...]
    """
    event_id: str
    timestamp: float
    receive_time: float
    symbol: str
    bids: str  # JSON array
    asks: str  # JSON array


@dataclass(frozen=True)
class TradeEvent:
    """
    Normalized trade event for storage.
    
    Fields:
        event_id: Unique identifier (UUID)
        timestamp: Exchange timestamp
        receive_time: Local receive timestamp
        symbol: Trading pair
        price: Trade price
        quantity: Trade quantity
        is_buyer_maker: True if buyer was maker (passive)
    """
    event_id: str
    timestamp: float
    receive_time: float
    symbol: str
    price: float
    quantity: float
    is_buyer_maker: bool


@dataclass(frozen=True)
class LiquidationEvent:
    """
    Normalized liquidation event for storage.
    
    Fields:
        event_id: Unique identifier (UUID)
        timestamp: Exchange timestamp
        receive_time: Local receive timestamp
        symbol: Trading pair
        side: "BUY" or "SELL"
        price: Liquidation price
        quantity: Liquidation quantity
    """
    event_id: str
    timestamp: float
    receive_time: float
    symbol: str
    side: str
    price: float
    quantity: float


@dataclass(frozen=True)
class BookTickerEvent:
    """
    Normalized book ticker event for storage.
    
    Fields:
        event_id: Unique identifier (UUID)
        timestamp: Exchange timestamp
        receive_time: Local receive timestamp
        symbol: Trading pair
        best_bid_price: Best bid price
        best_bid_qty: Best bid quantity
        best_ask_price: Best ask price
        best_ask_qty: Best ask quantity
    """
    event_id: str
    timestamp: float
    receive_time: float
    symbol: str
    best_bid_price: float
    best_bid_qty: float
    best_ask_price: float
    best_ask_qty: float


@dataclass(frozen=True)
class CandleEvent:
    """
    Normalized candle event for storage.
    
    Fields:
        event_id: Unique identifier (UUID)
        timestamp: Candle open time
        receive_time: Local receive timestamp
        symbol: Trading pair
        open, high, low, close: OHLC prices
        volume: Trade volume
        is_closed: Whether candle is finalized
    """
    event_id: str
    timestamp: float
    receive_time: float
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool


def generate_event_id() -> str:
    """
    Generate unique event ID.
    
    Returns:
        UUID string
    """
    return str(uuid.uuid4())


def serialize_orderbook_levels(levels: Tuple[Tuple[float, float], ...]) -> str:
    """
    Serialize orderbook levels to JSON.
    
    Args:
        levels: Tuple of (price, quantity) tuples
        
    Returns:
        JSON string: [[price, qty], ...]
    """
    return json.dumps([[p, q] for p, q in levels])


def deserialize_orderbook_levels(json_str: str) -> List[Tuple[float, float]]:
    """
    Deserialize orderbook levels from JSON.
    
    Args:
        json_str: JSON string
        
    Returns:
        List of (price, quantity) tuples
    """
    return [tuple(level) for level in json.loads(json_str)]
