"""
Binance Futures Liquidation WebSocket Stream Collector

Connects to Binance's !forceOrder@arr stream to receive real-time
liquidation events for all symbols in the market.
"""

import json
import time
import threading
from datetime import datetime
from queue import Queue
import websocket
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BinanceLiquidationStream:
    """
    WebSocket client for Binance Futures liquidation stream.
    
    Connects to wss://fstream.binance.com/ws/!forceOrder@arr
    to receive all market liquidation events.
    """
    
    def __init__(self, symbols=None, data_queue=None):
        """
        Initialize the liquidation stream.
        
        Args:
            symbols: List of symbols to filter (e.g., ['BTCUSDT', 'ETHUSDT'])
                    If None, all symbols are processed
            data_queue: Queue to push parsed liquidation events to
        """
        self.symbols = set(symbols) if symbols else None
        self.data_queue = data_queue or Queue()
        
        # WebSocket configuration
        self.ws_url = "wss://fstream.binance.com/ws/!forceOrder@arr"
        self.ws = None
        self.ws_thread = None
        
        # Connection state
        self.is_running = False
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 60
        self.last_ping_time = None
        
        # Statistics
        self.events_received = 0
        self.events_filtered = 0
        self.connection_start_time = None
        
    def start(self):
        """Start the WebSocket connection in a separate thread."""
        if self.is_running:
            logger.warning("Stream already running")
            return
        
        self.is_running = True
        self.ws_thread = threading.Thread(target=self._run, daemon=True)
        self.ws_thread.start()
        logger.info("Liquidation stream started")
        
    def stop(self):
        """Stop the WebSocket connection."""
        self.is_running = False
        if self.ws:
            self.ws.close()
        logger.info("Liquidation stream stopped")
        
    def _run(self):
        """Main run loop with automatic reconnection."""
        while self.is_running:
            try:
                self._connect()
            except Exception as e:
                logger.error(f"Connection error: {e}")
                
            if self.is_running:
                logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                
                # Exponential backoff for reconnection
                self.reconnect_delay = min(
                    self.reconnect_delay * 2,
                    self.max_reconnect_delay
                )
    
    def _connect(self):
        """Establish WebSocket connection."""
        logger.info(f"Connecting to {self.ws_url}")
        
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
            on_ping=self._on_ping,
            on_pong=self._on_pong
        )
        
        # Run WebSocket (blocking call)
        self.ws.run_forever(ping_interval=60, ping_timeout=10)
        
    def _on_open(self, ws):
        """Called when WebSocket connection is established."""
        logger.info("WebSocket connection established")
        self.connection_start_time = datetime.now()
        self.reconnect_delay = 5  # Reset reconnect delay
        
    def _on_message(self, ws, message):
        """
        Called when a message is received from WebSocket.
        
        Message format:
        {
          "e": "forceOrder",
          "E": 1568014460893,
          "o": {
            "s": "BTCUSDT",
            "S": "SELL",
            "o": "LIMIT",
            "f": "IOC",
            "q": "0.014",
            "p": "9910",
            "ap": "9910",
            "X": "FILLED",
            "l": "0.014",
            "z": "0.014",
            "T": 1568014460893
          }
        }
        """
        try:
            data = json.loads(message)
            
            # Validate event type
            if data.get('e') != 'forceOrder':
                return
            
            order = data.get('o', {})
            symbol = order.get('s')
            
            # Filter by symbols if specified
            if self.symbols and symbol not in self.symbols:
                return
            
            # Parse liquidation event
            liquidation = self._parse_liquidation(data)
            
            # Push to queue
            self.data_queue.put(liquidation)
            
            self.events_received += 1
            
            # Log periodically
            if self.events_received % 100 == 0:
                logger.info(f"Processed {self.events_received} liquidation events")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _parse_liquidation(self, data):
        """
        Parse Binance liquidation event into standardized format.
        
        Returns:
            dict: Parsed liquidation data
        """
        order = data['o']
        
        # Extract fields
        symbol = order['s']
        side = order['S']  # SELL = longs liquidated, BUY = shorts liquidated
        quantity = float(order['q'])
        price = float(order['p'])
        avg_price = float(order['ap'])
        status = order['X']
        
        # Event timestamps
        event_time = data['E']
        trade_time = order['T']
        
        # Calculate USD value
        value_usd = quantity * avg_price
        
        return {
            'timestamp': datetime.fromtimestamp(event_time / 1000).isoformat(),
            'trade_time': datetime.fromtimestamp(trade_time / 1000).isoformat(),
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'avg_price': avg_price,
            'value_usd': value_usd,
            'status': status,
            'raw_event': data  # Keep raw data for debugging
        }
    
    def _on_error(self, ws, error):
        """Called when WebSocket encounters an error."""
        logger.error(f"WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection is closed."""
        logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
        
        if self.connection_start_time:
            uptime = datetime.now() - self.connection_start_time
            logger.info(f"Connection uptime: {uptime}")
    
    def _on_ping(self, ws, message):
        """Called when server sends a ping."""
        self.last_ping_time = datetime.now()
        logger.debug("Received ping from server")
    
    def _on_pong(self, ws, message):
        """Called when server responds to our ping."""
        logger.debug("Received pong from server")
    
    def get_stats(self):
        """Get stream statistics."""
        uptime = None
        if self.connection_start_time:
            uptime = datetime.now() - self.connection_start_time
            
        return {
            'is_running': self.is_running,
            'events_received': self.events_received,
            'uptime': str(uptime) if uptime else None,
            'queue_size': self.data_queue.qsize(),
            'last_ping': str(self.last_ping_time) if self.last_ping_time else None
        }


if __name__ == "__main__":
    """
    Test the liquidation stream.
    Run this to verify WebSocket connection and data reception.
    """
    
    # Monitor BTC, ETH, SOL
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    # Create stream
    stream = BinanceLiquidationStream(symbols=symbols)
    
    # Start streaming
    stream.start()
    
    print(f"Monitoring liquidations for: {', '.join(symbols)}")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            # Process events from queue
            if not stream.data_queue.empty():
                event = stream.data_queue.get()
                
                # Display liquidation
                color = '\033[92m' if event['side'] == 'BUY' else '\033[91m'
                reset = '\033[0m'
                
                print(f"{color}[{event['timestamp']}] {event['symbol']}")
                print(f"  Side: {event['side']} (${event['value_usd']:,.2f})")
                print(f"  Price: ${event['avg_price']:,.2f} | Qty: {event['quantity']:.4f}{reset}\n")
            
            # Show stats every 30 seconds
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping stream...")
        stream.stop()
        
        # Final stats
        stats = stream.get_stats()
        print(f"\nFinal Statistics:")
        print(f"  Events received: {stats['events_received']}")
        print(f"  Uptime: {stats['uptime']}")
