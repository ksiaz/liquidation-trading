"""
Market Maker Inventory Tracker

Infers market maker positions from orderbook behavior and generates signals
when MMs are unwinding positions.

Theory:
- Market makers reveal their inventory through quote skewing
- MM long → wider asks (trying to sell)
- MM short → wider bids (trying to buy)
- When MM unwinds, it's a strong directional signal
"""

import time
import logging
import numpy as np
from typing import Dict, Optional
from collections import deque

logger = logging.getLogger(__name__)


class MarketMakerInventoryTracker:
    """
    Track market maker inventory and detect unwinding.
    
    Features:
    - Quote skew analysis
    - Position inference
    - Unwind detection
    - Signal generation
    """
    
    def __init__(self, symbol: str):
        """
        Initialize MM tracker.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        
        # Quote history for skew analysis
        self.quote_history = deque(maxlen=100)  # Last 100 updates
        
        # Inferred MM position
        self.inferred_position = 0  # -1 = long, 0 = neutral, +1 = short
        self.position_confidence = 0.0
        
        # Skew thresholds
        self.skew_threshold = 0.2  # 20% imbalance = position
        
    def update(self, orderbook: Dict):
        """
        Update tracker with new orderbook data.
        
        Args:
            orderbook: Dict with 'bids' and 'asks'
        """
        try:
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks or len(bids) < 5 or len(asks) < 5:
                return
            
            # Calculate bid/ask depth (top 5 levels)
            bid_depth = sum(float(qty) for _, qty in bids[:5])
            ask_depth = sum(float(qty) for _, qty in asks[:5])
            
            if bid_depth + ask_depth == 0:
                return
            
            # Calculate quote skew
            # Positive skew = more bids (MM is short, trying to buy)
            # Negative skew = more asks (MM is long, trying to sell)
            skew = (bid_depth - ask_depth) / (bid_depth + ask_depth)
            
            # Store skew
            self.quote_history.append({
                'timestamp': time.time(),
                'skew': skew,
                'bid_depth': bid_depth,
                'ask_depth': ask_depth
            })
            
            # Infer position
            self._infer_position()
            
        except Exception as e:
            logger.error(f"Error updating MM tracker for {self.symbol}: {e}")
    
    def _infer_position(self):
        """
        Infer MM position from quote history.
        
        Consistent skew indicates MM position:
        - Persistent bid skew → MM is short
        - Persistent ask skew → MM is long
        """
        if len(self.quote_history) < 20:
            return
        
        # Calculate average skew (last 20 updates)
        recent_skews = [q['skew'] for q in list(self.quote_history)[-20:]]
        avg_skew = np.mean(recent_skews)
        skew_std = np.std(recent_skews)
        
        # Consistent skew = MM position
        if avg_skew > self.skew_threshold and skew_std < 0.1:
            # Persistent bid skew → MM is short
            self.inferred_position = 1
            self.position_confidence = min(avg_skew, 0.8)
        elif avg_skew < -self.skew_threshold and skew_std < 0.1:
            # Persistent ask skew → MM is long
            self.inferred_position = -1
            self.position_confidence = min(abs(avg_skew), 0.8)
        else:
            # No clear position
            self.inferred_position = 0
            self.position_confidence = 0.0
    
    def get_signal(self) -> Optional[Dict]:
        """
        Detect MM unwinding and generate signal.
        
        Returns:
            Signal dict or None
        """
        if len(self.quote_history) < 30:
            return None
        
        if self.inferred_position == 0:
            return None  # No position to unwind
        
        # Get recent skew (last 10 updates)
        recent_skews = [q['skew'] for q in list(self.quote_history)[-10:]]
        recent_avg = np.mean(recent_skews)
        
        # Detect unwinding (skew reversing)
        # MM was long (negative skew), now unwinding (skew turning positive)
        if self.inferred_position == -1 and recent_avg > 0:
            return {
                'type': 'MM_UNWIND',
                'direction': 'SHORT',
                'confidence': 0.75,
                'reason': f'Market maker unwinding long position (skew: {recent_avg:.2f})',
                'mm_position': 'LONG',
                'unwind_strength': abs(recent_avg)
            }
        
        # MM was short (positive skew), now unwinding (skew turning negative)
        elif self.inferred_position == 1 and recent_avg < 0:
            return {
                'type': 'MM_UNWIND',
                'direction': 'LONG',
                'confidence': 0.75,
                'reason': f'Market maker unwinding short position (skew: {recent_avg:.2f})',
                'mm_position': 'SHORT',
                'unwind_strength': abs(recent_avg)
            }
        
        return None
    
    def get_stats(self) -> Dict:
        """Get tracker statistics."""
        if not self.quote_history:
            return {
                'symbol': self.symbol,
                'inferred_position': 'NEUTRAL',
                'confidence': 0.0,
                'current_skew': 0.0
            }
        
        latest = self.quote_history[-1]
        
        position_str = 'NEUTRAL'
        if self.inferred_position == -1:
            position_str = 'LONG'
        elif self.inferred_position == 1:
            position_str = 'SHORT'
        
        return {
            'symbol': self.symbol,
            'inferred_position': position_str,
            'confidence': self.position_confidence,
            'current_skew': latest['skew'],
            'bid_depth': latest['bid_depth'],
            'ask_depth': latest['ask_depth']
        }


if __name__ == "__main__":
    """Test MM inventory tracker."""
    
    logging.basicConfig(level=logging.INFO)
    
    tracker = MarketMakerInventoryTracker('BTCUSDT')
    
    print("=" * 60)
    print("MARKET MAKER INVENTORY TRACKER TEST")
    print("=" * 60)
    
    # Simulate MM with long position (more asks)
    print("\nSimulating MM with LONG position (wider asks)...")
    for i in range(25):
        orderbook = {
            'bids': [[95000, 1.0], [94900, 1.0], [94800, 1.0], [94700, 1.0], [94600, 1.0]],
            'asks': [[95100, 2.0], [95200, 2.0], [95300, 2.0], [95400, 2.0], [95500, 2.0]]  # Wider asks
        }
        tracker.update(orderbook)
        time.sleep(0.01)
    
    stats = tracker.get_stats()
    print(f"Inferred Position: {stats['inferred_position']}")
    print(f"Confidence: {stats['confidence']:.2f}")
    print(f"Current Skew: {stats['current_skew']:.2f}")
    
    # Simulate unwinding (skew reversing)
    print("\nSimulating MM unwinding (skew reversing)...")
    for i in range(15):
        orderbook = {
            'bids': [[95000, 2.0], [94900, 2.0], [94800, 2.0], [94700, 2.0], [94600, 2.0]],  # More bids now
            'asks': [[95100, 1.0], [95200, 1.0], [95300, 1.0], [95400, 1.0], [95500, 1.0]]
        }
        tracker.update(orderbook)
        time.sleep(0.01)
    
    signal = tracker.get_signal()
    if signal:
        print(f"\n🎯 SIGNAL GENERATED!")
        print(f"Type: {signal['type']}")
        print(f"Direction: {signal['direction']}")
        print(f"Confidence: {signal['confidence']:.0%}")
        print(f"Reason: {signal['reason']}")
    else:
        print("\nNo signal (need more data or no unwinding detected)")
