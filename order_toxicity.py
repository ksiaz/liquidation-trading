"""
Order Toxicity Calculator

Detects "toxic" orders from informed traders vs "non-toxic" orders from uninformed retail.

Toxic orders have:
1. Large size relative to spread liquidity
2. High aggressiveness (market orders, price impact)
3. Clustering (multiple similar orders in short time)
4. Followed by price continuation

Use cases:
- Follow toxic flow (informed traders)
- Fade non-toxic flow (uninformed retail)
- Adjust market making spreads
"""

import time
import logging
from typing import Dict, List, Optional
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


class OrderToxicityCalculator:
    """
    Calculate toxicity score for each trade.
    
    High toxicity = Informed trader (follow the flow)
    Low toxicity = Uninformed retail (fade the flow)
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        
        # Trade history for clustering analysis
        self.recent_trades = deque(maxlen=1000)
        
        # Toxicity history
        self.toxicity_history = deque(maxlen=100)
        
        # Current orderbook (updated externally)
        self.current_orderbook = None
        
    def update_orderbook(self, orderbook: Dict):
        """Update current orderbook state."""
        self.current_orderbook = orderbook
    
    def calculate_toxicity(self, trade: Dict) -> float:
        """
        Calculate toxicity score for a trade (0-1).
        
        Args:
            trade: {
                'price': float,
                'quantity': float,
                'side': 'BUY' or 'SELL',
                'timestamp': float
            }
        
        Returns:
            Toxicity score (0 = uninformed, 1 = highly informed)
        """
        if self.current_orderbook is None:
            return 0.5  # Unknown
        
        try:
            # Factor 1: Size relative to spread liquidity (40% weight)
            size_factor = self._calculate_size_factor(trade)
            
            # Factor 2: Aggressiveness / Price impact (30% weight)
            impact_factor = self._calculate_impact_factor(trade)
            
            # Factor 3: Clustering (30% weight)
            cluster_factor = self._calculate_cluster_factor(trade)
            
            # Combine factors
            toxicity = (size_factor * 0.4 + 
                       impact_factor * 0.3 + 
                       cluster_factor * 0.3)
            
            # Store trade and toxicity
            self.recent_trades.append(trade)
            self.toxicity_history.append({
                'timestamp': trade['timestamp'],
                'toxicity': toxicity,
                'side': trade['side']
            })
            
            return toxicity
            
        except Exception as e:
            logger.error(f"Error calculating toxicity for {self.symbol}: {e}")
            return 0.5
    
    def _calculate_size_factor(self, trade: Dict) -> float:
        """
        Calculate size factor (0-1).
        
        Large trades relative to spread liquidity = higher toxicity.
        """
        try:
            bids = self.current_orderbook.get('bids', [])
            asks = self.current_orderbook.get('asks', [])
            
            if not bids or not asks:
                return 0.5
            
            # Calculate spread liquidity (top 3 levels)
            spread_liquidity = 0
            for i in range(min(3, len(bids))):
                spread_liquidity += float(bids[i][1])
            for i in range(min(3, len(asks))):
                spread_liquidity += float(asks[i][1])
            
            if spread_liquidity == 0:
                return 0.5
            
            # Size factor = trade size / spread liquidity
            size_ratio = trade['quantity'] / spread_liquidity
            
            # Normalize to 0-1 (cap at 2x spread liquidity = 1.0)
            return min(size_ratio / 2.0, 1.0)
            
        except Exception as e:
            logger.error(f"Error in size factor: {e}")
            return 0.5
    
    def _calculate_impact_factor(self, trade: Dict) -> float:
        """
        Calculate price impact factor (0-1).
        
        Trades that move through the book = higher toxicity.
        """
        try:
            bids = self.current_orderbook.get('bids', [])
            asks = self.current_orderbook.get('asks', [])
            
            if not bids or not asks:
                return 0.5
            
            # Calculate mid price
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid_price = (best_bid + best_ask) / 2
            
            # Calculate price impact (distance from mid)
            price_impact = abs(trade['price'] - mid_price) / mid_price
            
            # Normalize to 0-1 (0.1% impact = 0.5, 0.5% impact = 1.0)
            normalized_impact = min(price_impact / 0.005, 1.0)
            
            return normalized_impact
            
        except Exception as e:
            logger.error(f"Error in impact factor: {e}")
            return 0.5
    
    def _calculate_cluster_factor(self, trade: Dict) -> float:
        """
        Calculate clustering factor (0-1).
        
        Multiple trades in same direction within 10s = higher toxicity.
        Uses tick rule classification for accurate direction detection.
        """
        try:
            # Look at trades in last 10 seconds
            cutoff_time = trade['timestamp'] - 10
            
            same_side_count = 0
            total_count = 0
            
            # Use tick rule classification
            trade_side = trade.get('true_side', trade['side'])
            
            for past_trade in self.recent_trades:
                if past_trade['timestamp'] >= cutoff_time:
                    total_count += 1
                    past_side = past_trade.get('true_side', past_trade['side'])
                    if past_side == trade_side:
                        same_side_count += 1
            
            if total_count == 0:
                return 0.0
            
            # Clustering ratio
            cluster_ratio = same_side_count / total_count
            
            # High clustering (>80% same side) = high toxicity
            # Normalize: 50% = 0, 100% = 1
            return max((cluster_ratio - 0.5) * 2, 0.0)
            
        except Exception as e:
            logger.error(f"Error in cluster factor: {e}")
            return 0.0
    
    def get_toxicity_signal(self, window_seconds: int = 30) -> Dict:
        """
        Get trading signal based on recent toxicity.
        
        Args:
            window_seconds: Time window to analyze
            
        Returns:
            Dict with signal and confidence
        """
        if len(self.toxicity_history) == 0:
            return {'signal': 'NEUTRAL', 'confidence': 0}
        
        # Get recent toxicity scores
        cutoff_time = time.time() - window_seconds
        recent = [t for t in self.toxicity_history if t['timestamp'] >= cutoff_time]
        
        if len(recent) == 0:
            return {'signal': 'NEUTRAL', 'confidence': 0}
        
        # Calculate average toxicity
        avg_toxicity = np.mean([t['toxicity'] for t in recent])
        
        # Count buy vs sell toxic trades (using tick rule classification)
        toxic_buys = sum(1 for t in recent 
                        if t.get('true_side', t.get('side')) == 'BUY' and t['toxicity'] > 0.7)
        toxic_sells = sum(1 for t in recent 
                         if t.get('true_side', t.get('side')) == 'SELL' and t['toxicity'] > 0.7)
        
        # Generate signal
        if avg_toxicity > 0.7:
            # High toxicity - follow the flow
            if toxic_buys > toxic_sells * 1.5:
                return {
                    'signal': 'FOLLOW_TOXIC_BUYING',
                    'confidence': avg_toxicity,
                    'toxic_buys': toxic_buys,
                    'toxic_sells': toxic_sells
                }
            elif toxic_sells > toxic_buys * 1.5:
                return {
                    'signal': 'FOLLOW_TOXIC_SELLING',
                    'confidence': avg_toxicity,
                    'toxic_buys': toxic_buys,
                    'toxic_sells': toxic_sells
                }
        elif avg_toxicity < 0.3:
            # Low toxicity - fade the flow
            non_toxic_buys = sum(1 for t in recent if t['side'] == 'BUY' and t['toxicity'] < 0.3)
            non_toxic_sells = sum(1 for t in recent if t['side'] == 'SELL' and t['toxicity'] < 0.3)
            
            if non_toxic_buys > non_toxic_sells * 1.5:
                return {
                    'signal': 'FADE_RETAIL_BUYING',
                    'confidence': 1 - avg_toxicity,
                    'non_toxic_buys': non_toxic_buys,
                    'non_toxic_sells': non_toxic_sells
                }
            elif non_toxic_sells > non_toxic_buys * 1.5:
                return {
                    'signal': 'FADE_RETAIL_SELLING',
                    'confidence': 1 - avg_toxicity,
                    'non_toxic_buys': non_toxic_buys,
                    'non_toxic_sells': non_toxic_sells
                }
        
        return {'signal': 'NEUTRAL', 'confidence': 0}
    
    def get_stats(self) -> Dict:
        """Get toxicity statistics."""
        if len(self.toxicity_history) == 0:
            return {
                'avg_toxicity': 0,
                'current_toxicity': 0,
                'toxic_trade_pct': 0
            }
        
        toxicities = [t['toxicity'] for t in self.toxicity_history]
        
        return {
            'avg_toxicity': float(np.mean(toxicities)),
            'current_toxicity': toxicities[-1],
            'toxic_trade_pct': sum(1 for t in toxicities if t > 0.7) / len(toxicities) * 100,
            'std': float(np.std(toxicities))
        }


if __name__ == "__main__":
    """Test toxicity calculator."""
    
    logging.basicConfig(level=logging.INFO)
    
    calc = OrderToxicityCalculator('BTCUSDT')
    
    # Sample orderbook
    orderbook = {
        'bids': [[100000, 2.0], [99999, 1.5], [99998, 1.0]],
        'asks': [[100001, 2.0], [100002, 1.5], [100003, 1.0]]
    }
    
    calc.update_orderbook(orderbook)
    
    print("="*60)
    print("ORDER TOXICITY CALCULATOR TEST")
    print("="*60)
    
    # Test 1: Large aggressive buy (toxic)
    print("\nTest 1: Large aggressive buy")
    trade1 = {
        'price': 100002,  # Through the spread
        'quantity': 3.0,   # Large size
        'side': 'BUY',
        'timestamp': time.time()
    }
    toxicity1 = calc.calculate_toxicity(trade1)
    print(f"Toxicity: {toxicity1:.2f} (Expected: High ~0.7-0.9)")
    
    # Test 2: Small passive sell (non-toxic)
    print("\nTest 2: Small passive sell")
    trade2 = {
        'price': 100001,  # At best ask
        'quantity': 0.1,   # Small size
        'side': 'SELL',
        'timestamp': time.time()
    }
    toxicity2 = calc.calculate_toxicity(trade2)
    print(f"Toxicity: {toxicity2:.2f} (Expected: Low ~0.1-0.3)")
    
    # Test 3: Clustered toxic buys
    print("\nTest 3: Clustered toxic buys")
    for i in range(5):
        trade = {
            'price': 100002,
            'quantity': 2.0,
            'side': 'BUY',
            'timestamp': time.time()
        }
        toxicity = calc.calculate_toxicity(trade)
        time.sleep(0.1)
    
    signal = calc.get_toxicity_signal()
    print(f"Signal: {signal['signal']}")
    print(f"Confidence: {signal['confidence']:.2f}")
    
    # Stats
    print("\nStatistics:")
    stats = calc.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value:.2f}")
