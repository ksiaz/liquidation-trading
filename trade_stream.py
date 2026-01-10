"""
Binance Trade Stream

Connects to Binance WebSocket to receive real-time trade executions.
Feeds trade data to volume flow analyzers for reversal detection.

Features:
- Real-time trade stream for multiple symbols
- Automatic reconnection on disconnect
- Trade aggregation and buffering
- Integration with volume flow detector
"""

import json
import logging
import threading
import time
from typing import Dict, Callable, List
from collections import deque
import websocket

logger = logging.getLogger(__name__)


class BinanceTradeStream:
    """
    Stream real-time trades from Binance WebSocket.
    
    Subscribes to aggTrade stream which provides:
    - Aggregated trades (multiple small trades combined)
    - Taker side (BUY or SELL)
    - Price and quantity
    - Timestamp
    """
    
    def __init__(self, symbols: List[str]):
        """
        Initialize trade stream.
        
        Args:
            symbols: List of symbols to monitor (e.g., ['BTCUSDT', 'ETHUSDT'])
        """
        self.symbols = [s.lower() for s in symbols]
        self.callbacks = []
        
        # WebSocket
        self.ws = None
        self.ws_thread = None
        self.running = False
        
        # Statistics
        self.trades_received = 0
        self.last_trade_time = {}
        
        # Tick rule classifiers for accurate trade classification
        from tick_rule_classifier import TickRuleClassifier
        self.tick_classifiers = {s.upper(): TickRuleClassifier(s.upper()) for s in symbols}
        
        # Build WebSocket URL
        streams = [f"{symbol}@aggTrade" for symbol in self.symbols]
        self.ws_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
        
        logger.info(f"Trade stream initialized for {len(symbols)} symbols with tick rule classification")
    
    def add_callback(self, callback: Callable):
        """
        Add callback function to receive trade updates.
        
        Callback signature: callback(symbol: str, trade: Dict)
        
        Trade dict contains:
        - price: float
        - quantity: float
        - side: 'BUY' or 'SELL' (taker side)
        - timestamp: float (seconds)
        - trade_id: int
        """
        self.callbacks.append(callback)
    
    def start(self):
        """Start the trade stream."""
        if self.running:
            logger.warning("Trade stream already running")
            return
        
        self.running = True
        self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.ws_thread.start()
        
        logger.info(f"Trade stream started: {self.ws_url}")
    
    def stop(self):
        """Stop the trade stream."""
        logger.info("Stopping trade stream...")
        self.running = False
        
        if self.ws:
            self.ws.close()
        
        if self.ws_thread:
            self.ws_thread.join(timeout=5)
        
        logger.info("Trade stream stopped")
    
    def _run_websocket(self):
        """Run WebSocket connection (runs in separate thread)."""
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open
                )
                
                self.ws.run_forever()
                
                # If we get here, connection closed
                if self.running:
                    logger.warning("WebSocket closed, reconnecting in 5 seconds...")
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    time.sleep(5)
    
    def _on_open(self, ws):
        """WebSocket opened."""
        logger.info("Trade stream connected")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket closed."""
        logger.warning(f"Trade stream disconnected: {close_status_code} - {close_msg}")
    
    def _on_error(self, ws, error):
        """WebSocket error."""
        logger.error(f"Trade stream error: {error}")
    
    def _on_message(self, ws, message):
        """
        Process incoming trade message.
        
        Binance aggTrade format:
        {
            "stream": "btcusdt@aggTrade",
            "data": {
                "e": "aggTrade",
                "E": 1234567890,
                "s": "BTCUSDT",
                "a": 12345,
                "p": "100000.00",
                "q": "0.5",
                "f": 100,
                "l": 105,
                "T": 1234567890,
                "m": true
            }
        }
        """
        try:
            msg = json.loads(message)
            
            if 'data' not in msg:
                return
            
            data = msg['data']
            
            # Extract trade info
            symbol = data['s']
            price = float(data['p'])
            quantity = float(data['q'])
            timestamp = data['T'] / 1000  # Convert to seconds
            trade_id = data['a']
            
            # Determine side (m=true means buyer is maker, so taker is seller)
            is_buyer_maker = data['m']
            side = 'SELL' if is_buyer_maker else 'BUY'
            
            # Create trade object
            trade = {
                'price': price,
                'quantity': quantity,
                'side': side,  # Exchange label (taker side)
                'timestamp': timestamp,
                'trade_id': trade_id
            }
            
            # Apply tick rule classification for true aggressor
            if symbol in self.tick_classifiers:
                true_side = self.tick_classifiers[symbol].classify(trade)
                trade['true_side'] = true_side  # Add true aggressor side
            else:
                trade['true_side'] = side  # Fallback to exchange label
            
            # Update statistics
            self.trades_received += 1
            self.last_trade_time[symbol] = timestamp
            
            # Call all callbacks
            for callback in self.callbacks:
                try:
                    callback(symbol, trade)
                except Exception as e:
                    logger.error(f"Error in trade callback: {e}")
            
        except Exception as e:
            logger.error(f"Error processing trade message: {e}")
    
    def get_stats(self) -> Dict:
        """Get stream statistics."""
        return {
            'trades_received': self.trades_received,
            'symbols': len(self.symbols),
            'last_trade_times': self.last_trade_time,
            'running': self.running
        }


if __name__ == "__main__":
    """Test trade stream."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    def on_trade(symbol, trade):
        """Print received trades."""
        print(f"{symbol}: {trade['side']:4} {trade['quantity']:8.4f} @ ${trade['price']:,.2f}")
    
    # Create stream
    stream = BinanceTradeStream(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
    stream.add_callback(on_trade)
    
    print("="*60)
    print("BINANCE TRADE STREAM TEST")
    print("="*60)
    print("Connecting to Binance WebSocket...")
    print("Press Ctrl+C to stop\n")
    
    try:
        stream.start()
        
        # Monitor stats
        while True:
            time.sleep(30)
            stats = stream.get_stats()
            print(f"\nStats: {stats['trades_received']} trades received")
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        stream.stop()
