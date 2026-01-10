"""
Orderbook Storage Manager

Captures and stores 20-level orderbook snapshots at 1-second intervals.
Integrates with BinanceOrderBookStream.

Storage: ~5.4 GB/month for 3 symbols (BTC, ETH, SOL)
"""

import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
from database import DatabaseManager
from orderbook_stream import BinanceOrderBookStream
import threading

logger = logging.getLogger(__name__)


class OrderbookStorageManager:
    """
    Manages storage of orderbook snapshots to PostgreSQL.
    
    Features:
    - 1-second sampling rate (reduces from 100ms stream)
    - Full 20-level storage
    - Automatic metrics calculation
    - Buffered writes for performance
    """
    
    def __init__(self, symbols: List[str], db: DatabaseManager):
        """
        Initialize orderbook storage manager.
        
        Args:
            symbols: List of symbols to monitor (e.g., ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
            db: Database manager instance
        """
        self.symbols = symbols
        self.db = db
        
        # Orderbook stream
        self.stream = BinanceOrderBookStream(symbols, depth=20)
        self.stream.add_callback(self._on_orderbook_update)
        
        # Storage control
        self.last_stored = {symbol: 0 for symbol in symbols}
        self.storage_interval = 1.0  # Store every 1 second
        
        # Buffer for batch inserts
        self.buffer = []
        self.buffer_size = 10  # Flush every 10 snapshots
        self.buffer_lock = threading.Lock()
        
        # Statistics
        self.snapshots_stored = 0
        self.snapshots_skipped = 0
        self.last_flush_time = time.time()
        
        # Metrics calculator
        self.metrics_calculator = OrderbookMetricsCalculator()
        
        # Signal generators (optional - will be set externally)
        # Dict mapping symbol -> SignalGenerator
        self.signal_generators = {}
        
    def set_signal_generator(self, signal_generator):
        """Set signal generator for a specific symbol (legacy method)."""
        if hasattr(signal_generator, 'symbol'):
            self.signal_generators[signal_generator.symbol] = signal_generator
            logger.info(f"Signal generator attached for {signal_generator.symbol}")
        
    def start(self):
        """Start orderbook stream and storage."""
        logger.info("Starting orderbook storage manager...")
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"Storage interval: {self.storage_interval}s")
        logger.info(f"Expected storage: ~1.8 GB/month per symbol")
        
        self.stream.start()
        
        # Start periodic flush thread
        self.flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self.flush_thread.start()
        
        logger.info("Orderbook storage started")
    
    def stop(self):
        """Stop orderbook stream and flush remaining data."""
        logger.info("Stopping orderbook storage...")
        self.stream.stop()
        self._flush_buffer()
        logger.info(f"Final stats: {self.snapshots_stored} stored, {self.snapshots_skipped} skipped")
    
    def _on_orderbook_update(self, symbol: str, orderbook: Dict):
        """
        Callback for orderbook updates from stream.
        
        Args:
            symbol: Trading pair
            orderbook: Orderbook data with bids, asks, timestamp
        """
        try:
            current_time = time.time()
            
            # Check if we should store (1-second interval)
            if current_time - self.last_stored[symbol] < self.storage_interval:
                self.snapshots_skipped += 1
                return
            
            logger.info(f"Processing orderbook update for {symbol}")
            
            # Prepare snapshot for storage
            snapshot = self._prepare_snapshot(symbol, orderbook)
            
            logger.info(f"Snapshot prepared for {symbol}, adding to buffer (current size: {len(self.buffer)})")
            
            # Generate trading signals if signal generator is attached for this symbol
            if symbol in self.signal_generators and self.signal_generators[symbol]:
                try:
                    signal_gen = self.signal_generators[symbol]
                    
                    # Prepare orderbook data for signal generation
                    ob_data = {
                        'symbol': symbol,
                        'best_bid': snapshot['best_bid'],
                        'best_ask': snapshot['best_ask'],
                        'imbalance': snapshot.get('imbalance_10', 0),  # Will be calculated below
                        'bid_volume_10': 0,  # Will be calculated below
                        'ask_volume_10': 0,  # Will be calculated below
                        'spread_pct': snapshot['spread_bps'] / 100,
                        'timestamp': snapshot['timestamp']
                    }
                    
                    # Calculate volumes from bids/asks
                    bids = snapshot['bids']
                    asks = snapshot['asks']
                    ob_data['bid_volume_10'] = sum([float(q) for p, q in bids[:10]])
                    ob_data['ask_volume_10'] = sum([float(q) for p, q in asks[:10]])
                    
                    # Calculate imbalance
                    total_vol = ob_data['bid_volume_10'] + ob_data['ask_volume_10']
                    if total_vol > 0:
                        ob_data['imbalance'] = (ob_data['bid_volume_10'] - ob_data['ask_volume_10']) / total_vol
                    
                    # Process for signal generation
                    signal_gen.process_orderbook(ob_data)
                    
                except Exception as e:
                    logger.error(f"Error in signal generation for {symbol}: {e}", exc_info=True)
            
            # Add to buffer
            with self.buffer_lock:
                self.buffer.append(snapshot)
                
                logger.info(f"Buffer size after append: {len(self.buffer)}/{self.buffer_size}")
                
                # Flush if buffer is full
                if len(self.buffer) >= self.buffer_size:
                    logger.info(f"Buffer full, flushing...")
                    self._flush_buffer()
            
            self.last_stored[symbol] = current_time
            
        except Exception as e:
            logger.error(f"Error processing orderbook update for {symbol}: {e}", exc_info=True)
    
    def _prepare_snapshot(self, symbol: str, orderbook: Dict) -> Dict:
        """
        Prepare orderbook snapshot for database storage.
        
        Args:
            symbol: Trading pair
            orderbook: Raw orderbook data
        
        Returns:
            Dict ready for database insertion
        """
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        # Ensure we have data
        if not bids or not asks:
            raise ValueError(f"Empty orderbook for {symbol}")
        
        # Extract best bid/ask
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        best_bid_qty = float(bids[0][1])
        best_ask_qty = float(asks[0][1])
        
        # Calculate spread
        spread_bps = ((best_ask - best_bid) / best_bid) * 10000
        mid_price = (best_bid + best_ask) / 2
        
        # Convert to list format (will be processed in flush)
        bids_json = [[float(p), float(q)] for p, q in bids[:20]]
        asks_json = [[float(p), float(q)] for p, q in asks[:20]]
        
        return {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'event_time': orderbook.get('event_time'),
            'best_bid': best_bid,
            'best_ask': best_ask,
            'best_bid_qty': best_bid_qty,
            'best_ask_qty': best_ask_qty,
            'spread_bps': spread_bps,
            'mid_price': mid_price,
            'bids': bids_json,  # Store as list, not JSON string
            'asks': asks_json,  # Store as list, not JSON string
            'update_id': orderbook.get('update_id')
        }
    
    def _flush_buffer(self):
        """Flush buffered snapshots to database. 
        NOTE: Caller must already hold self.buffer_lock!
        """
        logger.info(f"_flush_buffer called, buffer size: {len(self.buffer)}")
        if not self.buffer:
            logger.info("Buffer empty, skipping flush")
            return
        
        try:
            logger.info("Step 1: Starting metric calculation")
            # Calculate metrics and prepare for insert
            values = []
            for s in self.buffer:
                # Get bids/asks (already as lists)
                bids = s['bids']
                asks = s['asks']
                
                # Calculate depth (top 10 levels)
                bid_value_10 = sum([float(p) * float(q) for p, q in bids[:10]])
                ask_value_10 = sum([float(p) * float(q) for p, q in asks[:10]])
                
                # Calculate volume (top 10 levels)
                bid_volume_10 = sum([float(q) for p, q in bids[:10]])
                ask_volume_10 = sum([float(q) for p, q in asks[:10]])
                
                # Calculate imbalance (top 10 levels)
                total_volume_10 = bid_volume_10 + ask_volume_10
                imbalance_10 = (bid_volume_10 - ask_volume_10) / total_volume_10 if total_volume_10 > 0 else 0
                
                # Calculate depth (top 20 levels)
                bid_value_20 = sum([float(p) * float(q) for p, q in bids[:20]])
                ask_value_20 = sum([float(p) * float(q) for p, q in asks[:20]])
                
                # Calculate volume (top 20 levels)
                bid_volume_20 = sum([float(q) for p, q in bids[:20]])
                ask_volume_20 = sum([float(q) for p, q in asks[:20]])
                
                # Calculate imbalance (top 20 levels)
                total_volume_20 = bid_volume_20 + ask_volume_20
                imbalance_20 = (bid_volume_20 - ask_volume_20) / total_volume_20 if total_volume_20 > 0 else 0
                
                # Convert spread_bps to spread_pct
                spread_pct = s['spread_bps'] / 100  # Convert basis points to percentage
                
                values.append((
                    s['symbol'],
                    s['timestamp'],
                    s['best_bid'],
                    s['best_ask'],
                    s['spread_bps'],  # Keep as spread
                    spread_pct,
                    bid_volume_10,
                    ask_volume_10,
                    bid_value_10,
                    ask_value_10,
                    imbalance_10,
                    bid_volume_20,
                    ask_volume_20,
                    bid_value_20,
                    ask_value_20,
                    imbalance_20
                ))
            
            logger.info(f"Step 2: Prepared {len(values)} value tuples")
            
            # Batch insert with CORRECT schema (including 20-level metrics)
            query = """
            INSERT INTO orderbook_snapshots 
            (symbol, timestamp, best_bid, best_ask, spread, spread_pct,
             bid_volume_10, ask_volume_10, bid_value_10, ask_value_10, imbalance,
             bid_volume_20, ask_volume_20, bid_value_20, ask_value_20, imbalance_20)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            logger.info("Step 3: Executing database insert")
            self.db.cursor.executemany(query, values)
            logger.info("Step 4: Committing transaction")
            self.db.conn.commit()
            logger.info("Step 5: Commit successful")
            
            self.snapshots_stored += len(self.buffer)
            logger.info(f"Flushed {len(self.buffer)} snapshots to database")
            
            # Clear buffer
            self.buffer.clear()
            self.last_flush_time = time.time()
            
        except Exception as e:
            logger.error(f"Error flushing buffer: {e}", exc_info=True)
            self.db.conn.rollback()
    
    
    def _periodic_flush(self):
        """Periodically flush buffer even if not full."""
        while True:
            time.sleep(5)  # Check every 5 seconds
            
            # Flush if buffer has data and hasn't been flushed recently
            if self.buffer and (time.time() - self.last_flush_time > 10):
                self._flush_buffer()
    
    def get_stats(self) -> Dict:
        """Get storage statistics."""
        return {
            'snapshots_stored': self.snapshots_stored,
            'snapshots_skipped': self.snapshots_skipped,
            'buffer_size': len(self.buffer),
            'storage_rate_per_hour': self.snapshots_stored / max((time.time() - self.last_flush_time) / 3600, 0.01)
        }


class OrderbookMetricsCalculator:
    """Calculate derived metrics from orderbook snapshots."""
    
    def calculate(self, symbol: str, timestamp: datetime, bids: List, asks: List) -> Dict:
        """
        Calculate all metrics for an orderbook snapshot.
        
        Args:
            symbol: Trading pair
            timestamp: Snapshot timestamp
            bids: List of [price, qty] bid levels
            asks: List of [price, qty] ask levels
        
        Returns:
            Dict of calculated metrics
        """
        # Depth calculations
        bid_depth_5 = self._calculate_depth(bids[:5])
        ask_depth_5 = self._calculate_depth(asks[:5])
        bid_depth_10 = self._calculate_depth(bids[:10])
        ask_depth_10 = self._calculate_depth(asks[:10])
        bid_depth_20 = self._calculate_depth(bids[:20])
        ask_depth_20 = self._calculate_depth(asks[:20])
        
        # Imbalance calculations
        imbalance_5 = self._calculate_imbalance(bids[:5], asks[:5])
        imbalance_10 = self._calculate_imbalance(bids[:10], asks[:10])
        imbalance_20 = self._calculate_imbalance(bids[:20], asks[:20])
        
        # Average sizes
        avg_bid_size_5 = sum(q for p, q in bids[:5]) / 5 if len(bids) >= 5 else 0
        avg_ask_size_5 = sum(q for p, q in asks[:5]) / 5 if len(asks) >= 5 else 0
        
        # Wall detection
        wall_detection = self._detect_walls(bids, asks)
        
        return {
            'symbol': symbol,
            'timestamp': timestamp,
            'bid_depth_5': bid_depth_5,
            'ask_depth_5': ask_depth_5,
            'bid_depth_10': bid_depth_10,
            'ask_depth_10': ask_depth_10,
            'bid_depth_20': bid_depth_20,
            'ask_depth_20': ask_depth_20,
            'imbalance_5': imbalance_5,
            'imbalance_10': imbalance_10,
            'imbalance_20': imbalance_20,
            'avg_bid_size_5': avg_bid_size_5,
            'avg_ask_size_5': avg_ask_size_5,
            **wall_detection
        }
    
    def _calculate_depth(self, levels: List) -> float:
        """Calculate total USD depth for given levels."""
        return sum(float(price) * float(qty) for price, qty in levels)
    
    def _calculate_imbalance(self, bids: List, asks: List) -> float:
        """Calculate orderbook imbalance: (bid_vol - ask_vol) / total_vol"""
        bid_vol = sum(float(qty) for _, qty in bids)
        ask_vol = sum(float(qty) for _, qty in asks)
        total_vol = bid_vol + ask_vol
        
        if total_vol == 0:
            return 0.0
        
        return (bid_vol - ask_vol) / total_vol
    
    def _detect_walls(self, bids: List, asks: List) -> Dict:
        """Detect large walls in orderbook."""
        # Calculate average size
        all_sizes = [float(qty) for _, qty in bids + asks]
        if not all_sizes:
            return {'large_bid_wall': False, 'large_ask_wall': False}
        
        avg_size = sum(all_sizes) / len(all_sizes)
        wall_threshold = avg_size * 5  # 5x average = wall
        
        # Check for bid walls
        large_bid_wall = False
        bid_wall_price = None
        bid_wall_size = None
        
        for price, qty in bids[:10]:
            if float(qty) > wall_threshold:
                large_bid_wall = True
                bid_wall_price = float(price)
                bid_wall_size = float(price) * float(qty)
                break
        
        # Check for ask walls
        large_ask_wall = False
        ask_wall_price = None
        ask_wall_size = None
        
        for price, qty in asks[:10]:
            if float(qty) > wall_threshold:
                large_ask_wall = True
                ask_wall_price = float(price)
                ask_wall_size = float(price) * float(qty)
                break
        
        return {
            'large_bid_wall': large_bid_wall,
            'large_ask_wall': large_ask_wall,
            'wall_price': bid_wall_price or ask_wall_price,
            'wall_size': bid_wall_size or ask_wall_size
        }


if __name__ == "__main__":
    """Test orderbook storage."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    db = DatabaseManager()
    
    storage = OrderbookStorageManager(symbols, db)
    
    print("=" * 60)
    print("ORDERBOOK STORAGE MANAGER")
    print("=" * 60)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Storage interval: 1 second")
    print(f"Expected storage: ~5.4 GB/month")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")
    
    try:
        storage.start()
        
        # Monitor stats
        while True:
            time.sleep(30)
            stats = storage.get_stats()
            print(f"\nStats: {stats['snapshots_stored']} stored, "
                  f"{stats['snapshots_skipped']} skipped, "
                  f"buffer: {stats['buffer_size']}")
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        storage.stop()
        db.close()
