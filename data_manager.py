"""
Data Persistence Manager for Liquidation Data (PostgreSQL Version)

Handles saving liquidation events to PostgreSQL database with:
- Buffered writes for performance
- Batch inserts
- Connection pooling
- Automatic reconnection
"""

import threading
from datetime import datetime
import logging
from database import DatabaseManager

logger = logging.getLogger(__name__)


class DataManager:
    """
    Manages persistent storage of liquidation data in PostgreSQL.
    
    Features:
    - Buffered writes (flush every N events or T seconds)
    - Batch inserts for performance
    - Automatic reconnection on failure
    - Statistics tracking
    """
    
    def __init__(self, buffer_size=100, flush_interval=10):
        """
        Initialize data manager.
        
        Args:
            buffer_size: Number of events to buffer before flushing
            flush_interval: Seconds between automatic flushes
        """
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        # Database connection
        self.db = None
        self._connect_db()
        
        # Buffer for pending writes
        self.buffer = []
        self.buffer_lock = threading.Lock()
        
        # Auto-flush thread
        self.is_running = False
        self.flush_thread = None
        
        # Statistics
        self.total_events_written = 0
        self.total_flushes = 0
        
        logger.info("Data manager initialized (PostgreSQL)")
    
    def _connect_db(self):
        """Connect to database and create tables."""
        try:
            self.db = DatabaseManager()
            self.db.create_tables()
            logger.info("Database connected and ready")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def start(self):
        """Start the auto-flush thread."""
        if self.is_running:
            return
        
        self.is_running = True
        self.flush_thread = threading.Thread(target=self._auto_flush, daemon=True)
        self.flush_thread.start()
        logger.info("Data manager started")
    
    def stop(self):
        """Stop the manager and flush remaining data."""
        self.is_running = False
        self.flush()
        
        if self.db:
            self.db.close()
        
        logger.info("Data manager stopped")
    
    def save_event(self, event):
        """
        Save a liquidation event.
        
        Args:
            event: Liquidation event dictionary
        """
        with self.buffer_lock:
            self.buffer.append(event)
            
            # Flush if buffer is full
            if len(self.buffer) >= self.buffer_size:
                self._flush_buffer()
    
    def flush(self):
        """Manually flush the buffer."""
        with self.buffer_lock:
            self._flush_buffer()
    
    def _flush_buffer(self):
        """Internal method to flush buffer to database."""
        if not self.buffer:
            return
        
        try:
            # Batch insert all events
            self.db.insert_liquidations_batch(self.buffer)
            self.db.commit()
            
            self.total_events_written += len(self.buffer)
            self.total_flushes += 1
            
            logger.debug(f"Flushed {len(self.buffer)} events to database")
            
            # Clear buffer
            self.buffer.clear()
            
        except Exception as e:
            logger.error(f"Error flushing buffer: {e}")
            self.db.rollback()
            
            # Try to reconnect
            try:
                logger.info("Attempting to reconnect to database...")
                self.db.close()
                self._connect_db()
            except Exception as reconnect_error:
                logger.error(f"Failed to reconnect: {reconnect_error}")
    
    def _auto_flush(self):
        """Background thread for periodic flushing."""
        while self.is_running:
            threading.Event().wait(self.flush_interval)
            
            if self.buffer:
                with self.buffer_lock:
                    self._flush_buffer()
    
    def get_stats(self):
        """Get data manager statistics."""
        db_stats = self.db.get_stats() if self.db else {}
        
        return {
            'total_events_written': self.total_events_written,
            'total_flushes': self.total_flushes,
            'buffer_size': len(self.buffer),
            'db_total_events': db_stats.get('total_events', 0),
            'db_total_value': db_stats.get('total_value', 0)
        }
    
    def get_recent_liquidations(self, limit=100, symbol=None):
        """
        Get recent liquidation events from database.
        
        Args:
            limit: Number of events to retrieve
            symbol: Filter by symbol (optional)
        
        Returns:
            List of liquidation dictionaries
        """
        if not self.db:
            return []
        
        return self.db.get_recent_liquidations(limit=limit, symbol=symbol)


if __name__ == "__main__":
    """Test the data manager."""
    
    logging.basicConfig(level=logging.INFO)
    
    # Create test data manager
    manager = DataManager(buffer_size=10, flush_interval=5)
    manager.start()
    
    # Simulate some events
    print("Writing test events...")
    for i in range(25):
        event = {
            'timestamp': datetime.now(),
            'trade_time': datetime.now(),
            'symbol': 'BTCUSDT',
            'side': 'SELL' if i % 2 == 0 else 'BUY',
            'quantity': 0.1 + i * 0.01,
            'price': 50000 + i * 100,
            'avg_price': 50000 + i * 100,
            'value_usd': (0.1 + i * 0.01) * (50000 + i * 100),
            'status': 'FILLED'
        }
        manager.save_event(event)
        print(f"  Event {i+1} buffered")
    
    print("\nFlushing...")
    manager.flush()
    
    # Show stats
    stats = manager.get_stats()
    print(f"\nStatistics:")
    print(f"  Events written: {stats['total_events_written']}")
    print(f"  Total flushes: {stats['total_flushes']}")
    print(f"  DB total events: {stats['db_total_events']}")
    print(f"  DB total value: ${stats['db_total_value']:,.2f}")
    
    # Get recent events
    recent = manager.get_recent_liquidations(limit=5)
    print(f"\nRecent events ({len(recent)}):")
    for event in recent:
        print(f"  {event['timestamp']} - {event['symbol']} {event['side']} ${event['value_usd']:,.2f}")
    
    manager.stop()
    print("\nTest complete!")
