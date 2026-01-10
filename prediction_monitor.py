"""
Prediction Monitor - Continuously monitors liquidation risk

Runs alongside the main monitor to:
1. Fetch open interest and funding rates every minute
2. Estimate liquidation zones
3. Alert when price approaches danger zones
4. Save predictions to database
"""

import time
import signal
import sys
from datetime import datetime
from liquidation_predictor import LiquidationPredictor
from config import SYMBOLS
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('prediction_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PredictionMonitor:
    """
    Monitors liquidation risk in real-time.
    
    Fetches market data and estimates liquidation zones periodically.
    """
    
    def __init__(self, update_interval=60):
        """
        Initialize prediction monitor.
        
        Args:
            update_interval: Seconds between updates (default: 60)
        """
        self.predictor = LiquidationPredictor(SYMBOLS)
        self.update_interval = update_interval
        self.is_running = False
        self.start_time = None
        
        # Statistics
        self.total_updates = 0
        self.alerts_triggered = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def start(self):
        """Start the prediction monitor."""
        logger.info("=" * 60)
        logger.info("LIQUIDATION PREDICTION MONITOR STARTING")
        logger.info("=" * 60)
        logger.info(f"Monitoring symbols: {', '.join(SYMBOLS)}")
        logger.info(f"Update interval: {self.update_interval}s")
        logger.info("=" * 60)
        
        self.is_running = True
        self.start_time = datetime.now()
        
        print("\n" + "=" * 60)
        print("LIQUIDATION RISK MONITOR")
        print("=" * 60)
        print(f"Analyzing: {', '.join(SYMBOLS)}")
        print(f"Update interval: {self.update_interval}s")
        print("Press Ctrl+C to stop\n")
        
        self._run()
    
    def stop(self):
        """Stop the monitor."""
        logger.info("Stopping prediction monitor...")
        self.is_running = False
        self._print_final_stats()
    
    def _run(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                self._update_predictions()
                self.total_updates += 1
                
                # Wait for next update
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)  # Wait a bit before retrying
    
    def _update_predictions(self):
        """Fetch latest data and update predictions."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Updating predictions...")
        print("─" * 60)
        
        for symbol in SYMBOLS:
            try:
                # Get risk analysis
                risk = self.predictor.analyze_liquidation_risk(symbol)
                
                if 'error' in risk:
                    print(f"{symbol}: Error - {risk['error']}")
                    continue
                
                # Display analysis
                self._display_risk_analysis(risk)
                
                # Check for alerts
                self._check_alerts(risk)
                
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
        
        print("─" * 60)
    
    def _display_risk_analysis(self, risk: dict):
        """Display risk analysis for a symbol."""
        symbol = risk['symbol']
        
        # Color coding based on bias
        if risk['market_bias'] == 'LONG_HEAVY':
            color = '\033[91m'  # Red
            bias_icon = '📈'
        elif risk['market_bias'] == 'SHORT_HEAVY':
            color = '\033[92m'  # Green
            bias_icon = '📉'
        else:
            color = '\033[0m'  # Normal
            bias_icon = '⚖️'
        
        reset = '\033[0m'
        
        print(f"\n{color}{symbol}{reset}")
        print(f"  Price: ${risk['current_price']:,.2f}")
        print(f"  Funding: {risk['funding_rate_pct']:.4f}% {bias_icon} {risk['market_bias']}")
        
        if risk['open_interest']:
            print(f"  Open Interest: {risk['open_interest']:,.0f}")
        
        if risk['danger_zones_count'] > 0:
            print(f"  ⚠️  {risk['danger_zones_count']} danger zones nearby")
            
            if risk['nearest_long_liq']:
                distance = ((risk['current_price'] - risk['nearest_long_liq']) / risk['current_price']) * 100
                print(f"     Long liq: ${risk['nearest_long_liq']:,.2f} ({distance:.2f}% below)")
            
            if risk['nearest_short_liq']:
                distance = ((risk['nearest_short_liq'] - risk['current_price']) / risk['current_price']) * 100
                print(f"     Short liq: ${risk['nearest_short_liq']:,.2f} ({distance:.2f}% above)")
    
    def _check_alerts(self, risk: dict):
        """Check if any alerts should be triggered."""
        # Alert if funding rate is extreme
        if risk['funding_rate_pct'] and abs(risk['funding_rate_pct']) > 0.05:  # 0.05%
            self.alerts_triggered += 1
            
            direction = "LONG" if risk['funding_rate_pct'] > 0 else "SHORT"
            print(f"\n  🚨 ALERT: Extreme funding rate! {direction} cascade risk")
        
        # Alert if many danger zones
        if risk['danger_zones_count'] >= 3:
            self.alerts_triggered += 1
            print(f"\n  🚨 ALERT: Multiple liquidation zones nearby!")
    
    def _print_final_stats(self):
        """Print final statistics."""
        uptime = datetime.now() - self.start_time
        
        print("\n" + "=" * 60)
        print("FINAL STATISTICS")
        print("=" * 60)
        print(f"Runtime: {uptime}")
        print(f"Total Updates: {self.total_updates}")
        print(f"Alerts Triggered: {self.alerts_triggered}")
        print("=" * 60)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\n\nReceived shutdown signal...")
        self.stop()
        sys.exit(0)


if __name__ == "__main__":
    """Run the prediction monitor."""
    
    # Get update interval from command line or use default
    update_interval = 60  # 1 minute default
    
    if len(sys.argv) > 1:
        try:
            update_interval = int(sys.argv[1])
        except ValueError:
            print(f"Invalid interval: {sys.argv[1]}, using default 60s")
    
    monitor = PredictionMonitor(update_interval=update_interval)
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        monitor.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        monitor.stop()
        sys.exit(1)
