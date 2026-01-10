"""
Live Exchange Feed Connectors

Data acquisition infrastructure for Binance Futures.

SCOPE: Data infrastructure ONLY.
- No trading logic
- No indicators
- No filtering/labeling
- No aggregation beyond exchange boundaries

PRINCIPLE: Data correctness > completeness > performance
"""

import asyncio
import websockets
import json
from typing import Callable, Optional, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LiveOrderbookSnapshot:
    """
    Raw L2 orderbook snapshot from exchange.
    
    Fields:
        timestamp: Exchange timestamp (seconds)
        receive_time: Local receive timestamp (seconds)
        symbol: Trading pair
        bids: Top 20 bid levels (price, quantity)
        asks: Top 20 ask levels (price, quantity)
    """
    timestamp: float
    receive_time: float
    symbol: str
    bids: tuple  # ((price, qty), ...)
    asks: tuple  # ((price, qty), ...)


@dataclass(frozen=True)
class LiveTrade:
    """
    Raw trade event from exchange.
    
    Fields:
        timestamp: Exchange timestamp
        receive_time: Local receive timestamp
        symbol: Trading pair
        price: Trade price
        quantity: Trade quantity
        is_buyer_maker: True if buyer was maker (passive)
    """
    timestamp: float
    receive_time: float
    symbol: str
    price: float
    quantity: float
    is_buyer_maker: bool


@dataclass(frozen=True)
class LiveLiquidation:
    """
    Raw liquidation event from exchange.
    
    Fields:
        timestamp: Exchange timestamp
        receive_time: Local receive timestamp
        symbol: Trading pair
        side: "BUY" or "SELL"
        price: Liquidation price
        quantity: Liquidation quantity
    """
    timestamp: float
    receive_time: float
    symbol: str
    side: str
    price: float
    quantity: float


@dataclass(frozen=True)
class LiveKline:
    """
    Raw 1m kline from exchange.
    
    Fields:
        timestamp: Candle open time
        receive_time: Local receive timestamp
        symbol: Trading pair
        open, high, low, close: OHLC prices
        volume: Trade volume
        is_closed: Whether candle is finalized
    """
    timestamp: float
    receive_time: float
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool


class BinanceFuturesFeeds:
    """
    Live feed connector for Binance Futures websocket streams.
    
    RULE: Data acquisition only - no processing.
    RULE: Immutable data structures.
    RULE: Dual timestamps (exchange + receive).
    """
    
    WSS_BASE = "wss://fstream.binance.com/stream"
    
    def __init__(self, symbol: str = "BTCUSDT"):
        """
        Initialize feed connector.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
        """
        self.symbol = symbol.upper()
        self.symbol_lower = symbol.lower()
        
        # Handlers for each stream type
        self._handlers: Dict[str, Callable] = {}
        
        # Stream names
        self.streams = {
            'orderbook': f"{self.symbol_lower}@depth20@100ms",
            'trade': f"{self.symbol_lower}@aggTrade",
            'liquidation': f"{self.symbol_lower}@forceOrder",
            'kline': f"{self.symbol_lower}@kline_1m",
        }
        
        self._running = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
    
    def register_orderbook_handler(self, handler: Callable[[LiveOrderbookSnapshot], None]):
        """Register handler for orderbook snapshots."""
        self._handlers['orderbook'] = handler
    
    def register_trade_handler(self, handler: Callable[[LiveTrade], None]):
        """Register handler for trade events."""
        self._handlers['trade'] = handler
    
    def register_liquidation_handler(self, handler: Callable[[LiveLiquidation], None]):
        """Register handler for liquidation events."""
        self._handlers['liquidation'] = handler
    
    def register_kline_handler(self, handler: Callable[[LiveKline], None]):
        """Register handler for kline events."""
        self._handlers['kline'] = handler
    
    def _parse_orderbook(self, data: dict) -> LiveOrderbookSnapshot:
        """
        Parse orderbook snapshot.
        
        RULE: Use exchange timestamp when available.
        """
        receive_time = datetime.utcnow().timestamp()
        
        # Exchange timestamp (milliseconds → seconds)
        timestamp = data.get('E', int(receive_time * 1000)) / 1000.0
        
        # Convert to immutable tuples (top 20 levels)
        bids = tuple((float(p), float(q)) for p, q in data['b'][:20])
        asks = tuple((float(p), float(q)) for p, q in data['a'][:20])
        
        return LiveOrderbookSnapshot(
            timestamp=timestamp,
            receive_time=receive_time,
            symbol=self.symbol,
            bids=bids,
            asks=asks
        )
    
    def _parse_trade(self, data: dict) -> LiveTrade:
        """
        Parse trade event.
        
        RULE: Use exchange timestamp.
        """
        receive_time = datetime.utcnow().timestamp()
        
        # Exchange timestamp (milliseconds → seconds)
        timestamp = data['T'] / 1000.0
        
        return LiveTrade(
            timestamp=timestamp,
            receive_time=receive_time,
            symbol=self.symbol,
            price=float(data['p']),
            quantity=float(data['q']),
            is_buyer_maker=data['m']  # True = buyer is maker (passive)
        )
    
    def _parse_liquidation(self, data: dict) -> LiveLiquidation:
        """
        Parse liquidation event.
        
        RULE: Use exchange timestamp.
        """
        receive_time = datetime.utcnow().timestamp()
        
        # Extract order data
        order = data['o']
        timestamp = data['E'] / 1000.0
        
        return LiveLiquidation(
            timestamp=timestamp,
            receive_time=receive_time,
            symbol=self.symbol,
            side=order['S'],
            price=float(order['p']),
            quantity=float(order['q'])
        )
    
    def _parse_kline(self, data: dict) -> LiveKline:
        """
        Parse kline event.
        
        RULE: Use candle open time as timestamp.
        """
        receive_time = datetime.utcnow().timestamp()
        
        # Extract kline data
        k = data['k']
        timestamp = k['t'] / 1000.0  # Candle open time
        
        return LiveKline(
            timestamp=timestamp,
            receive_time=receive_time,
            symbol=self.symbol,
            open=float(k['o']),
            high=float(k['h']),
            low=float(k['l']),
            close=float(k['c']),
            volume=float(k['v']),
            is_closed=k['x']
        )
    
    async def _handle_message(self, message: dict):
        """
        Route message to appropriate parser and handler.
        
        RULE: No processing - just parse and emit.
        """
        stream = message.get('stream', '')
        data = message.get('data', {})
        
        try:
            if 'depth20' in stream:
                snapshot = self._parse_orderbook(data)
                if 'orderbook' in self._handlers:
                    self._handlers['orderbook'](snapshot)
            
            elif 'aggTrade' in stream:
                trade = self._parse_trade(data)
                if 'trade' in self._handlers:
                    self._handlers['trade'](trade)
            
            elif 'forceOrder' in stream:
                liquidation = self._parse_liquidation(data)
                if 'liquidation' in self._handlers:
                    self._handlers['liquidation'](liquidation)
            
            elif 'kline' in stream:
                kline = self._parse_kline(data)
                if 'kline' in self._handlers:
                    self._handlers['kline'](kline)
        
        except Exception as e:
            print(f"Error parsing message: {e}")
            # Don't crash - log and continue
    
    async def connect(self):
        """
        Connect to websocket and start receiving data.
        
        RULE: One message at a time - no batching.
        """
        # Build stream URL
        stream_names = '/'.join(self.streams.values())
        url = f"{self.WSS_BASE}?streams={stream_names}"
        
        self._running = True
        
        async with websockets.connect(url) as ws:
            self._ws = ws
            
            while self._running:
                try:
                    message = await ws.recv()
                    data = json.loads(message)
                    await self._handle_message(data)
                
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed")
                    break
                except Exception as e:
                    print(f"Error receiving message: {e}")
    
    def stop(self):
        """Stop receiving data."""
        self._running = False


# Example usage (for documentation):
"""
async def main():
    feeds = BinanceFuturesFeeds("BTCUSDT")
    
    # Register handlers
    def handle_orderbook(snapshot: LiveOrderbookSnapshot):
        print(f"Orderbook: {snapshot.timestamp}, mid={sum(snapshot.bids[0][0], snapshot.asks[0][0])/2}")
    
    def handle_trade(trade: LiveTrade):
        print(f"Trade: {trade.timestamp}, price={trade.price}, qty={trade.quantity}")
    
    feeds.register_orderbook_handler(handle_orderbook)
    feeds.register_trade_handler(handle_trade)
    
    # Connect
    await feeds.connect()

if __name__ == "__main__":
    asyncio.run(main())
"""
