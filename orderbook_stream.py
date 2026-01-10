"""
Order Book Stream - Binance Futures

Real-time order book depth monitoring via WebSocket.
Provides snapshots and updates for liquidity analysis.
"""

import websocket
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class BinanceOrderBookStream:
    """
    WebSocket stream for Binance Futures order book depth.
    
    Provides real-time order book updates for specified symbols.
    """
    
    def __init__(self, symbols: List[str], depth: int = 20):
        """
        Initialize order book stream.
        
        Args:
            symbols: List of trading pairs (e.g., ['BTCUSDT', 'ETHUSDT'])
            depth: Depth levels (5, 10, or 20)
        """
        self.symbols = [s.lower() for s in symbols]
        self.depth = depth
        self.ws = None
        self.is_running = False
        self.callbacks = []
        
        # Order book state
        self.orderbooks = {symbol: {'bids': [], 'asks': []} for symbol in symbols}
        self.last_update = {symbol: None for symbol in symbols}
        
        # Threading
        self.thread = None
        self.lock = threading.Lock()
        
    def on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            
            if 'e' in data and data['e'] == 'depthUpdate':
                symbol = data['s']
                
                # Update order book
                with self.lock:
                    self.orderbooks[symbol] = {
                        'bids': [[float(p), float(q)] for p, q in data['b']],
                        'asks': [[float(p), float(q)] for p, q in data['a']],
                        'timestamp': datetime.now(),
                        'event_time': datetime.fromtimestamp(data['E'] / 1000)
                    }
                    self.last_update[symbol] = datetime.now()
                
                # Trigger callbacks
                for callback in self.callbacks:
                    try:
                        callback(symbol, self.orderbooks[symbol])
                    except Exception as e:
                        logger.error(f"Error in callback: {e}")
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        logger.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
        
        if self.is_running:
            logger.info("Attempting to reconnect...")
            time.sleep(5)
            self._connect()
    
    def on_open(self, ws):
        """Handle WebSocket open."""
        logger.info("Order book WebSocket connected")
        
        # Subscribe to depth streams
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol}@depth{self.depth}@100ms" for symbol in self.symbols],
            "id": 1
        }
        ws.send(json.dumps(subscribe_message))
        logger.info(f"Subscribed to {len(self.symbols)} order book streams")
    
    def _connect(self):
        """Establish WebSocket connection."""
        url = "wss://fstream.binance.com/ws"
        
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        self.ws.run_forever()
    
    def start(self):
        """Start the order book stream."""
        if self.is_running:
            logger.warning("Stream already running")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._connect, daemon=True)
        self.thread.start()
        logger.info("Order book stream started")
    
    def stop(self):
        """Stop the order book stream."""
        self.is_running = False
        if self.ws:
            self.ws.close()
        logger.info("Order book stream stopped")
    
    def add_callback(self, callback: Callable):
        """
        Add callback function for order book updates.
        
        Args:
            callback: Function(symbol, orderbook_data)
        """
        self.callbacks.append(callback)
    
    def get_orderbook(self, symbol: str) -> Optional[Dict]:
        """
        Get current order book for a symbol.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Order book dict or None
        """
        with self.lock:
            return self.orderbooks.get(symbol.upper())
    
    def get_best_bid_ask(self, symbol: str) -> Optional[Dict]:
        """
        Get best bid and ask prices.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with best_bid, best_ask, spread
        """
        orderbook = self.get_orderbook(symbol)
        if not orderbook or not orderbook['bids'] or not orderbook['asks']:
            return None
        
        best_bid = orderbook['bids'][0][0]
        best_ask = orderbook['asks'][0][0]
        
        return {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread': best_ask - best_bid,
            'spread_pct': (best_ask - best_bid) / best_bid * 100
        }


if __name__ == "__main__":
    """Test the order book stream."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    def print_orderbook(symbol, data):
        """Print order book updates."""
        print(f"\n{symbol} Order Book Update:")
        print(f"Best Bid: ${data['bids'][0][0]:,.2f} ({data['bids'][0][1]} BTC)")
        print(f"Best Ask: ${data['asks'][0][0]:,.2f} ({data['asks'][0][1]} BTC)")
        spread = data['asks'][0][0] - data['bids'][0][0]
        print(f"Spread: ${spread:.2f}")
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    stream = BinanceOrderBookStream(symbols, depth=20)
    stream.add_callback(print_orderbook)
    
    print("=" * 60)
    print("ORDER BOOK STREAM TEST")
    print("=" * 60)
    print(f"Monitoring: {', '.join(symbols)}")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    stream.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        stream.stop()
