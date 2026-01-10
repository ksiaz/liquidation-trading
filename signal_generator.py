"""
Signal Generator Module

Wraps LiquidityDrainDetector with database persistence and dashboard broadcasting.
Processes orderbook updates and generates trading signals.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from queue import Queue

from liquidity_drain_detector import LiquidityDrainDetector
from liquidation_predictor import LiquidationPredictor
from market_impact import MarketImpactCalculator

logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    Generates trading signals from orderbook data using LiquidityDrainDetector.
    
    Features:
    - Real-time signal generation with data-driven detector
    - Per-symbol optimized thresholds
    - Database persistence
    - Dashboard broadcasting
    - Signal history tracking
    """
    
    def __init__(self, db_manager, dashboard_queue: Optional[Queue] = None, symbol: str = 'BTCUSDT', performance_tracker=None):
        """
        Initialize signal generator.
        
        Args:
            db_manager: DatabaseManager instance for persistence
            dashboard_queue: Optional queue for broadcasting signals to dashboard
            symbol: Trading symbol to monitor
            performance_tracker: Optional SignalPerformanceTracker for live positions
        """
        self.db = db_manager
        self.dashboard_queue = dashboard_queue
        self.symbol = symbol
        self.performance_tracker = performance_tracker
        
        # Initialize NEW data-driven detector with symbol-specific config
        logger.info(f"Initializing LiquidityDrainDetector for {symbol}...")
        
        self.detector = LiquidityDrainDetector(symbol=symbol)
        
        logger.info(f"✅ LiquidityDrainDetector initialized with optimized config for {symbol}")
        
        # Statistics
        self.signals_generated = 0
        self.signals_saved = 0
        self.last_signal_time = None
        
    def process_orderbook(self, orderbook_data: Dict) -> Optional[Dict]:
        """
        Process orderbook update and generate signal if conditions are met.
        
        Args:
            orderbook_data: Dict with keys:
                - symbol: str
                - best_bid: float
                - best_ask: float
                - imbalance: float
                - bid_volume_10: float
                - ask_volume_10: float
                - spread_pct: float
                - timestamp: datetime
        
        Returns:
            Signal dict if generated, None otherwise
        """
        try:
            # Update detector
            signal = self.detector.update(orderbook_data)
            
            if signal:
                self.signals_generated += 1
                self.last_signal_time = datetime.now()
                
                logger.info(f"🎯 SIGNAL GENERATED: {signal['direction']} @ ${signal['entry_price']:,.2f} "
                           f"(Confidence: {signal['confidence']}%, Type: {signal.get('type', 'LIQUIDITY_DRAIN')})")
                
                # Save to database
                self._save_signal(signal, orderbook_data)
                
                # Broadcast to dashboard
                if self.dashboard_queue:
                    try:
                        self.dashboard_queue.put(signal)
                    except Exception as e:
                        logger.error(f"Failed to broadcast signal to dashboard: {e}")
                
                return signal
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing orderbook for signal generation: {e}", exc_info=True)
            return None
    
    def _save_signal(self, signal: Dict, orderbook_data: Dict):
        """
        Save signal to database.
        
        Args:
            signal: Signal dictionary from detector
            orderbook_data: Original orderbook data
        """
        try:
            # Handle new detector format (metadata contains pattern info)
            metadata = signal.get('metadata', {})
            
            # Simpler insert for new detector (no complex signal breakdown)
            query = """
            INSERT INTO trading_signals 
            (timestamp, symbol, direction, entry_price, confidence, snr, timeframe,
             signals_confirmed, signals_total,
             imbalance_divergence, depth_building, volume_exhaustion,
             funding_divergence, liquidity_confirmation,
             wave_trend_bias, chop_filtered)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = (
                orderbook_data.get('timestamp', datetime.now()),
                orderbook_data.get('symbol', self.symbol),
                signal['direction'],
                signal['entry_price'],
                signal['confidence'],
                0.0,  # No SNR in new detector
                0,    # timeframe=0 for liquidity drain (not timeframe-based)
                1,  # Simple: 1 signal confirmed
                1,  # Simple: 1 signal total
                False,  # Legacy fields
                True,   # depth_building (we use depth drain)
                False,
                False,
                False,
                None,   # No wave trend
                False
            )
            
            self.db.cursor.execute(query, values)
            self.db.conn.commit()
            
            self.signals_saved += 1
            logger.debug(f"Signal saved to database")
            
            # Add to performance tracker for Live Positions
            if self.performance_tracker:
                try:
                    # Convert to performance tracker format
                    tracker_signal = {
                        'id': f"{self.symbol}_{int(orderbook_data.get('timestamp', datetime.now()).timestamp())}",
                        'symbol': self.symbol,  # Fixed: detector signal doesn't have 'symbol' key
                        'direction': signal['direction'],
                        'type': 'LIQUIDITY_DRAIN',
                        'entry': signal['entry_price'],
                        'target': signal['entry_price'] * 1.005 if signal['direction'] == 'LONG' else signal['entry_price'] * 0.995,
                        'stop': signal['entry_price'] * 0.9975 if signal['direction'] == 'LONG' else signal['entry_price'] * 1.0025,
                        'timestamp': orderbook_data.get('timestamp', datetime.now()).timestamp(),
                        'confidence': signal['confidence'] / 100  # Convert to 0-1 range
                    }
                    self.performance_tracker.add_signal(tracker_signal)
                    logger.info(f"✅ Signal added to performance tracker for Live Positions")
                except Exception as e:
                    logger.error(f"Failed to add signal to performance tracker: {e}")
            
        except Exception as e:
            logger.error(f"Failed to save signal to database: {e}", exc_info=True)
            self.db.conn.rollback()
    
    def get_stats(self) -> Dict:
        """Get signal generator statistics."""
        return {
            'signals_generated': self.signals_generated,
            'signals_saved': self.signals_saved,
            'last_signal_time': self.last_signal_time
        }
    
    def get_recent_signals(self, limit: int = 10) -> list:
        """
        Retrieve recent signals from database.
        
        Args:
            limit: Number of signals to retrieve
            
        Returns:
            List of signal dictionaries
        """
        try:
            query = """
            SELECT timestamp, symbol, direction, entry_price, confidence, snr,
                   timeframe, signals_confirmed, signals_total,
                   imbalance_divergence, depth_building, volume_exhaustion,
                   funding_divergence, liquidity_confirmation,
                   wave_trend_bias
            FROM trading_signals
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            self.db.cursor.execute(query, (self.symbol, limit))
            
            signals = []
            for row in self.db.cursor.fetchall():
                signals.append({
                    'timestamp': row[0],
                    'symbol': row[1],
                    'direction': row[2],
                    'entry_price': float(row[3]),
                    'confidence': row[4],
                    'snr': float(row[5]),
                    'timeframe': row[6],
                    'signals_confirmed': row[7],
                    'signals_total': row[8],
                    'signals': {
                        'imbalance_divergence': row[9],
                        'depth_building': row[10],
                        'volume_exhaustion': row[11],
                        'funding_divergence': row[12],
                        'liquidity_confirmation': row[13]
                    },
                    'wave_trend_bias': row[14]
                })
            
            return signals
            
        except Exception as e:
            logger.error(f"Failed to retrieve recent signals: {e}")
            return []


if __name__ == "__main__":
    """Test signal generator."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from database import DatabaseManager
    
    print("=" * 60)
    print("SIGNAL GENERATOR TEST")
    print("=" * 60)
    
    # Initialize
    db = DatabaseManager()
    db.create_tables()
    
    generator = SignalGenerator(db, symbol='BTCUSDT')
    
    print(f"\n✅ Signal generator initialized")
    print(f"Symbol: {generator.symbol}")
    print(f"Detector ready: {generator.detector is not None}")
    
    # Test with dummy orderbook data
    test_data = {
        'symbol': 'BTCUSDT',
        'best_bid': 87000.0,
        'best_ask': 87001.0,
        'imbalance': 0.05,
        'bid_volume_10': 10.5,
        'ask_volume_10': 9.8,
        'spread_pct': 0.001,
        'timestamp': datetime.now()
    }
    
    print("\n📊 Processing test orderbook data...")
    signal = generator.process_orderbook(test_data)
    
    if signal:
        print(f"✅ Signal generated: {signal}")
    else:
        print("ℹ️  No signal (conditions not met)")
    
    stats = generator.get_stats()
    print(f"\n📈 Stats: {stats}")
    
    db.close()
    print("\n" + "=" * 60)
