"""
Order Book Monitor

Orchestrates order book data collection and analysis.
Logs snapshots, depth metrics, and large orders to database.
"""

import time
import threading
from datetime import datetime
from typing import Dict, List
import logging
import signal
import sys

from orderbook_stream import BinanceOrderBookStream
from orderbook_analyzer import OrderBookAnalyzer
from database import DatabaseManager
from config import SYMBOLS

logger = logging.getLogger(__name__)


class OrderBookMonitor:
    """
    Main order book monitoring service.
    
    Collects real-time order book data and stores analytics.
    """
    
    def __init__(self, snapshot_interval: int = 5, depth_interval: int = 30):
        """
        Initialize monitor.
        
        Args:
            snapshot_interval: Seconds between snapshots
            depth_interval: Seconds between depth analysis
        """
        self.snapshot_interval = snapshot_interval
        self.depth_interval = depth_interval
        
        # Components
        self.stream = BinanceOrderBookStream(SYMBOLS, depth=20)
        self.analyzer = OrderBookAnalyzer(large_order_threshold_usd=500000)
        self.db = DatabaseManager()
        
        # State
        self.is_running = False
        self.start_time = None
        
        # Threads
        self.snapshot_thread = None
        self.depth_thread = None
        
        # Statistics
        self.snapshots_taken = 0
        self.depth_analyses = 0
        self.walls_detected = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Shutdown signal received")
        self.stop()
        sys.exit(0)
    
    def _snapshot_worker(self):
        """Worker thread for taking snapshots."""
        while self.is_running:
            try:
                for symbol in SYMBOLS:
                    orderbook = self.stream.get_orderbook(symbol)
                    if orderbook:
                        # Get current price (mid price)
                        spread_data = self.analyzer.analyze_spread(orderbook)
                        if spread_data:
                            current_price = spread_data['mid_price']
                            
                            # Generate snapshot metrics
                            metrics = self.analyzer.generate_snapshot_metrics(
                                orderbook, symbol, current_price
                            )
                            
                            # Store in database
                            self._store_snapshot(metrics)
                            self.snapshots_taken += 1
                
                time.sleep(self.snapshot_interval)
                
            except Exception as e:
                logger.error(f"Error in snapshot worker: {e}")
                time.sleep(1)
    
    def _depth_worker(self):
        """Worker thread for depth analysis."""
        while self.is_running:
            try:
                for symbol in SYMBOLS:
                    orderbook = self.stream.get_orderbook(symbol)
                    if orderbook:
                        spread_data = self.analyzer.analyze_spread(orderbook)
                        if spread_data:
                            current_price = spread_data['mid_price']
                            
                            # Calculate liquidity at distances
                            liq_0_5 = self.analyzer.calculate_liquidity_at_distance(
                                orderbook, current_price, 0.5
                            )
                            liq_1 = self.analyzer.calculate_liquidity_at_distance(
                                orderbook, current_price, 1.0
                            )
                            liq_2 = self.analyzer.calculate_liquidity_at_distance(
                                orderbook, current_price, 2.0
                            )
                            
                            # Detect cliffs
                            cliffs = self.analyzer.detect_liquidity_cliffs(
                                orderbook, current_price
                            )
                            
                            # Store depth analysis
                            self._store_depth_analysis(
                                symbol, current_price, liq_0_5, liq_1, liq_2,
                                len(cliffs) > 0
                            )
                            
                            # Detect and store large orders
                            large_orders = self.analyzer.detect_large_orders(
                                orderbook, current_price
                            )
                            for order in large_orders:
                                self._store_large_order(symbol, order)
                                self.walls_detected += 1
                            
                            self.depth_analyses += 1
                
                time.sleep(self.depth_interval)
                
            except Exception as e:
                logger.error(f"Error in depth worker: {e}")
                time.sleep(1)
    
    def _store_snapshot(self, metrics: Dict):
        """Store snapshot in database."""
        try:
            query = """
            INSERT INTO orderbook_snapshots 
            (timestamp, symbol, best_bid, best_ask, spread, spread_pct,
             bid_volume_10, ask_volume_10, bid_value_10, ask_value_10, imbalance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db.cursor.execute(query, (
                metrics['timestamp'],
                metrics['symbol'],
                metrics['best_bid'],
                metrics['best_ask'],
                metrics['spread'],
                metrics['spread_pct'],
                metrics['bid_volume_10'],
                metrics['ask_volume_10'],
                metrics['bid_value_10'],
                metrics['ask_value_10'],
                metrics['imbalance']
            ))
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error storing snapshot: {e}")
            self.db.rollback()
    
    def _store_depth_analysis(self, symbol: str, price: float, liq_0_5: Dict,
                               liq_1: Dict, liq_2: Dict, cliff_detected: bool):
        """Store depth analysis in database."""
        try:
            query = """
            INSERT INTO orderbook_depth
            (timestamp, symbol, liquidity_0_5pct_down, liquidity_1pct_down, liquidity_2pct_down,
             liquidity_0_5pct_up, liquidity_1pct_up, liquidity_2pct_up, cliff_detected)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db.cursor.execute(query, (
                datetime.now(),
                symbol,
                liq_0_5.get('bid_liquidity', 0),
                liq_1.get('bid_liquidity', 0),
                liq_2.get('bid_liquidity', 0),
                liq_0_5.get('ask_liquidity', 0),
                liq_1.get('ask_liquidity', 0),
                liq_2.get('ask_liquidity', 0),
                cliff_detected
            ))
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error storing depth analysis: {e}")
            self.db.rollback()
    
    def _store_large_order(self, symbol: str, order: Dict):
        """Store large order in database."""
        try:
            query = """
            INSERT INTO orderbook_walls
            (timestamp, symbol, side, price, size, value_usd, event_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db.cursor.execute(query, (
                datetime.now(),
                symbol,
                order['side'],
                order['price'],
                order['size'],
                order['value_usd'],
                'DETECTED'
            ))
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error storing large order: {e}")
            self.db.rollback()
    
    def start(self):
        """Start the order book monitor."""
        if self.is_running:
            logger.warning("Monitor already running")
            return
        
        logger.info("Starting order book monitor...")
        self.is_running = True
        self.start_time = datetime.now()
        
        # Start order book stream
        self.stream.start()
        time.sleep(2)  # Wait for initial data
        
        # Start worker threads
        self.snapshot_thread = threading.Thread(target=self._snapshot_worker, daemon=True)
        self.depth_thread = threading.Thread(target=self._depth_worker, daemon=True)
        
        self.snapshot_thread.start()
        self.depth_thread.start()
        
        logger.info("Order book monitor started")
        self._print_status()
    
    def stop(self):
        """Stop the order book monitor."""
        logger.info("Stopping order book monitor...")
        self.is_running = False
        
        if self.stream:
            self.stream.stop()
        
        if self.db:
            self.db.close()
        
        logger.info("Order book monitor stopped")
        self._print_final_stats()
    
    def _print_status(self):
        """Print current status."""
        print("\n" + "=" * 60)
        print("ORDER BOOK MONITOR")
        print("=" * 60)
        print(f"Symbols:           {', '.join(SYMBOLS)}")
        print(f"Snapshot Interval: {self.snapshot_interval}s")
        print(f"Depth Interval:    {self.depth_interval}s")
        print("=" * 60 + "\n")
    
    def _print_final_stats(self):
        """Print final statistics."""
        uptime = datetime.now() - self.start_time if self.start_time else None
        
        print("\n" + "=" * 60)
        print("ORDER BOOK MONITOR - FINAL STATISTICS")
        print("=" * 60)
        if uptime:
            print(f"Uptime:            {uptime}")
        print(f"Snapshots Taken:   {self.snapshots_taken}")
        print(f"Depth Analyses:    {self.depth_analyses}")
        print(f"Walls Detected:    {self.walls_detected}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    """Run the order book monitor."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("BINANCE ORDER BOOK MONITOR")
    print("=" * 60)
    print("Monitoring order book depth and liquidity")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    monitor = OrderBookMonitor(snapshot_interval=5, depth_interval=30)
    monitor.start()
    
    try:
        while True:
            time.sleep(30)
            # Print periodic stats
            print(f"\r📊 Snapshots: {monitor.snapshots_taken} | "
                  f"Depth: {monitor.depth_analyses} | "
                  f"Walls: {monitor.walls_detected}", end='', flush=True)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        monitor.stop()
