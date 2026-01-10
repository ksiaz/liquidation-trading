"""
Real-time Liquidation Monitor

Main application that:
1. Connects to Binance liquidation stream
2. Filters and displays significant events
3. Saves all data to PostgreSQL database
4. Shows live statistics
"""

import time
import signal
import sys
from datetime import datetime
from liquidation_stream import BinanceLiquidationStream
from data_manager import DataManager
from config import SYMBOLS, MIN_LIQUIDATION_SIZE, BUFFER_SIZE, FLUSH_INTERVAL
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LiquidationMonitor:
    """
    Main monitoring application.
    
    Orchestrates the WebSocket stream and data persistence.
    """
    
    def __init__(self, setup_signals=True, live_callback=None):
        """
        Initialize the liquidation monitor.
        
        Args:
            setup_signals: If True, setup signal handlers (only works in main thread)
            live_callback: Optional callback function to receive live liquidations
        """
        self.stream = BinanceLiquidationStream(symbols=SYMBOLS)
        self.data_manager = DataManager(
            buffer_size=BUFFER_SIZE,
            flush_interval=FLUSH_INTERVAL
        )
        
        self.is_running = False
        self.start_time = None
        self.live_callback = live_callback  # Store callback
        
        # Statistics
        self.total_liquidations = 0
        self.significant_events = 0
        self.liquidations_by_symbol = {symbol: 0 for symbol in SYMBOLS}
        self.liquidations_by_side = {'BUY': 0, 'SELL': 0}
        self.total_value_usd = 0
        
        # Setup signal handlers for graceful shutdown (only if in main thread)
        if setup_signals:
            try:
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            except ValueError:
                # Signal handlers can only be set in main thread
                logger.warning("Signal handlers not set (not in main thread)")
    
    def start(self):
        """Start the monitor."""
        logger.info("=" * 60)
        logger.info("LIQUIDATION MONITOR STARTING")
        logger.info("=" * 60)
        logger.info(f"Monitoring symbols: {', '.join(SYMBOLS)}")
        logger.info(f"Database: PostgreSQL")
        logger.info(f"Thresholds: {MIN_LIQUIDATION_SIZE}")
        logger.info("=" * 60)
        
        self.is_running = True
        self.start_time = datetime.now()
        
        # Start components
        self.stream.start()
        self.data_manager.start()
        
        # Main processing loop
        self._run()
    
    def stop(self):
        """Stop the monitor."""
        logger.info("Stopping monitor...")
        self.is_running = False
        
        self.stream.stop()
        self.data_manager.stop()
        
        self._print_final_stats()
    
    def _run(self):
        """Main processing loop."""
        last_stats_time = time.time()
        stats_interval = 30  # Show stats every 30 seconds
        
        print("\n" + "=" * 60)
        print("LIVE LIQUIDATION MONITOR")
        print("=" * 60)
        print("Waiting for liquidation events...")
        print("Press Ctrl+C to stop\n")
        
        while self.is_running:
            try:
                # Process events from stream
                if not self.stream.data_queue.empty():
                    event = self.stream.data_queue.get()
                    self._process_event(event)
                
                # Show periodic stats
                if time.time() - last_stats_time >= stats_interval:
                    self._print_stats()
                    last_stats_time = time.time()
                
                time.sleep(0.1)  # Small delay to prevent CPU spinning
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
    
    def _process_event(self, event):
        """
        Process a liquidation event.
        
        Args:
            event: Liquidation event dictionary
        """
        # Save to disk
        self.data_manager.save_event(event)
        
        # Broadcast to live dashboard if callback provided
        if self.live_callback:
            try:
                self.live_callback(event)
            except Exception as e:
                logger.error(f"Error in live callback: {e}")
        
        # Update statistics
        self.total_liquidations += 1
        self.liquidations_by_symbol[event['symbol']] += 1
        self.liquidations_by_side[event['side']] += 1
        self.total_value_usd += event['value_usd']
        
        # Check if significant
        threshold = MIN_LIQUIDATION_SIZE.get(event['symbol'], 50000)
        is_significant = event['value_usd'] >= threshold
        
        if is_significant:
            self.significant_events += 1
            self._display_significant_event(event)
    
    def _display_significant_event(self, event):
        """Display a significant liquidation event."""
        # Color coding
        if event['side'] == 'SELL':
            color = '\033[91m'  # Red for longs liquidated
            direction = '📉 LONGS LIQUIDATED'
        else:
            color = '\033[92m'  # Green for shorts liquidated
            direction = '📈 SHORTS LIQUIDATED'
        
        reset = '\033[0m'
        
        print(f"\n{color}{'=' * 60}")
        print(f"🚨 SIGNIFICANT LIQUIDATION - {event['symbol']}")
        print(f"{'=' * 60}")
        # Handle timestamp - could be string or datetime
        timestamp = event['timestamp']
        time_str = timestamp if isinstance(timestamp, str) else timestamp.strftime('%Y-%m-%d %H:%M:%S')
        print(f"Time:      {time_str}")
        print(f"Direction: {direction}")
        print(f"Value:     ${event['value_usd']:,.2f}")
        print(f"Price:     ${event['avg_price']:,.2f}")
        print(f"Quantity:  {event['quantity']:.4f}")
        print(f"{'=' * 60}{reset}\n")
    
    def _print_stats(self):
        """Print current statistics."""
        uptime = datetime.now() - self.start_time
        
        print("\n" + "─" * 60)
        print(f"📊 STATISTICS (Uptime: {uptime})")
        print("─" * 60)
        print(f"Total Liquidations:    {self.total_liquidations}")
        print(f"Significant Events:    {self.significant_events}")
        print(f"Total Value:           ${self.total_value_usd:,.2f}")
        print()
        
        # By symbol
        print("By Symbol:")
        for symbol, count in self.liquidations_by_symbol.items():
            print(f"  {symbol:10s}: {count:5d} events")
        print()
        
        # By side
        print("By Side:")
        print(f"  LONGS liquidated (SELL):  {self.liquidations_by_side['SELL']:5d}")
        print(f"  SHORTS liquidated (BUY):  {self.liquidations_by_side['BUY']:5d}")
        print()
        
        # Stream stats
        stream_stats = self.stream.get_stats()
        print(f"Stream Status:         {'🟢 RUNNING' if stream_stats['is_running'] else '🔴 STOPPED'}")
        print(f"Queue Size:            {stream_stats['queue_size']}")
        print()
        
        # Data manager stats
        dm_stats = self.data_manager.get_stats()
        print(f"Events Written:        {dm_stats['total_events_written']}")
        print(f"DB Total Events:       {dm_stats.get('db_total_events', 0)}")
        print(f"Buffer Size:           {dm_stats['buffer_size']}")
        print("─" * 60 + "\n")
    
    def _print_final_stats(self):
        """Print final statistics on shutdown."""
        print("\n" + "=" * 60)
        print("FINAL STATISTICS")
        print("=" * 60)
        
        uptime = datetime.now() - self.start_time
        print(f"Total Runtime:         {uptime}")
        print(f"Total Liquidations:    {self.total_liquidations}")
        print(f"Significant Events:    {self.significant_events}")
        print(f"Total Value:           ${self.total_value_usd:,.2f}")
        print()
        
        # Data manager stats
        dm_stats = self.data_manager.get_stats()
        print(f"Events Saved:          {dm_stats['total_events_written']}")
        print(f"Total Flushes:         {dm_stats.get('total_flushes', 0)}")
        print(f"DB Total Events:       {dm_stats.get('db_total_events', 0)}")
        print(f"DB Total Value:        ${dm_stats.get('db_total_value', 0):,.2f}")
        print()
        
        print("=" * 60)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\n\nReceived shutdown signal...")
        self.stop()
        sys.exit(0)


if __name__ == "__main__":
    """Run the liquidation monitor."""
    
    monitor = LiquidationMonitor()
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        monitor.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        monitor.stop()
        sys.exit(1)
