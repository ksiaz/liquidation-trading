"""
Order Wall Detector - Real-Time Large Order Detection

Detects large orders (walls) from 20-level orderbook data.
Tracks wall appearance/disappearance for spoofing detection.
"""

import time
import logging
from collections import deque
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderWallDetector:
    """
    Detect large orders (walls) in real-time orderbook.
    
    Features:
    - Uses 20-level orderbook depth
    - Detects walls (5x+ average size)
    - Tracks wall persistence
    - Spoofing detection
    """
    
    def __init__(self, symbol: str):
        """
        Initialize order wall detector.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        
        # Wall detection thresholds
        self.size_multiplier = 5.0  # 5x average = wall
        self.min_wall_usd = 500_000  # Minimum $500k
        
        # Active walls (currently visible)
        self.active_walls = []
        
        # Wall history (for spoofing detection)
        self.wall_history = deque(maxlen=100)
        
        # Wall tracking (by price level)
        self.wall_tracker = {}  # {price: {'first_seen': time, 'last_seen': time, 'count': X}}
        
        # Statistics
        self.total_walls_detected = 0
        self.spoofing_events = 0
        
    def on_orderbook_update(self, orderbook: Dict):
        """
        Detect walls from 20-level orderbook.
        
        Args:
            orderbook: Dict with 'bids' and 'asks' as [[price, qty], ...]
        """
        try:
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                return
            
            # Calculate average order size
            all_sizes = [float(qty) for _, qty in bids + asks]
            avg_size = sum(all_sizes) / len(all_sizes) if all_sizes else 0
            
            if avg_size == 0:
                return
            
            # Detect bid walls
            bid_walls = self._detect_walls(bids, avg_size, 'BID')
            
            # Detect ask walls
            ask_walls = self._detect_walls(asks, avg_size, 'ASK')
            
            # Update active walls
            previous_walls = self.active_walls.copy()
            self.active_walls = bid_walls + ask_walls
            
            # Track wall events
            self._track_wall_events(previous_walls, self.active_walls)
            
        except Exception as e:
            logger.error(f"Error detecting walls for {self.symbol}: {e}")
    
    def _detect_walls(self, levels: List, avg_size: float, side: str) -> List[Dict]:
        """
        Detect walls in orderbook levels.
        
        Args:
            levels: List of [price, qty] pairs
            avg_size: Average order size
            side: 'BID' or 'ASK'
        
        Returns:
            List of detected walls
        """
        walls = []
        
        for i, (price, qty) in enumerate(levels):
            price = float(price)
            qty = float(qty)
            value_usd = price * qty
            
            # Check if this is a wall
            is_wall = (
                qty > avg_size * self.size_multiplier and
                value_usd > self.min_wall_usd
            )
            
            if is_wall:
                walls.append({
                    'side': side,
                    'price': price,
                    'quantity': qty,
                    'value_usd': value_usd,
                    'level': i,  # 0 = best bid/ask
                    'size_ratio': qty / avg_size,
                    'timestamp': time.time()
                })
                
                self.total_walls_detected += 1
        
        return walls
    
    def _track_wall_events(self, previous_walls: List[Dict], current_walls: List[Dict]):
        """
        Track when walls appear/disappear.
        
        Args:
            previous_walls: Walls from last update
            current_walls: Walls from current update
        """
        current_time = time.time()
        
        # Create price sets for comparison
        prev_prices = {w['price'] for w in previous_walls}
        curr_prices = {w['price'] for w in current_walls}
        
        # Detect new walls (appeared)
        new_walls = curr_prices - prev_prices
        for price in new_walls:
            if price not in self.wall_tracker:
                self.wall_tracker[price] = {
                    'first_seen': current_time,
                    'last_seen': current_time,
                    'appearances': 1
                }
            else:
                self.wall_tracker[price]['last_seen'] = current_time
                self.wall_tracker[price]['appearances'] += 1
        
        # Detect removed walls (disappeared)
        removed_walls = prev_prices - curr_prices
        for price in removed_walls:
            if price in self.wall_tracker:
                tracker = self.wall_tracker[price]
                duration = current_time - tracker['first_seen']
                
                # Check for spoofing (wall removed quickly)
                if duration < 10:  # Removed within 10 seconds
                    self.spoofing_events += 1
                    
                    # Find the wall details
                    wall_data = next((w for w in previous_walls if w['price'] == price), None)
                    
                    if wall_data:
                        self.wall_history.append({
                            'event': 'SPOOFING_SUSPECTED',
                            'price': price,
                            'side': wall_data['side'],
                            'value_usd': wall_data['value_usd'],
                            'duration': duration,
                            'timestamp': current_time
                        })
                        
                        logger.warning(f"Spoofing suspected on {self.symbol}: "
                                     f"{wall_data['side']} wall at ${price:,.0f} "
                                     f"(${wall_data['value_usd']:,.0f}) removed after {duration:.1f}s")
    
    def get_significant_walls(self, min_value_usd: float = 1_000_000) -> List[Dict]:
        """
        Get walls above threshold.
        
        Args:
            min_value_usd: Minimum wall size in USD
        
        Returns:
            List of significant walls
        """
        return [
            wall for wall in self.active_walls
            if wall['value_usd'] >= min_value_usd
        ]
    
    def get_all_walls(self) -> List[Dict]:
        """Get all currently active walls."""
        return self.active_walls.copy()
    
    def get_spoofing_events(self, window_seconds: float = 60) -> List[Dict]:
        """
        Get recent spoofing events.
        
        Args:
            window_seconds: Time window to check
        
        Returns:
            List of suspected spoofing events
        """
        current_time = time.time()
        
        return [
            event for event in self.wall_history
            if current_time - event['timestamp'] < window_seconds
            and event['event'] == 'SPOOFING_SUSPECTED'
        ]
    
    def get_wall_summary(self) -> Dict:
        """
        Get summary of current wall state.
        
        Returns:
            Dict with wall statistics
        """
        bid_walls = [w for w in self.active_walls if w['side'] == 'BID']
        ask_walls = [w for w in self.active_walls if w['side'] == 'ASK']
        
        return {
            'symbol': self.symbol,
            'total_walls': len(self.active_walls),
            'bid_walls': len(bid_walls),
            'ask_walls': len(ask_walls),
            'largest_bid_wall': max((w['value_usd'] for w in bid_walls), default=0),
            'largest_ask_wall': max((w['value_usd'] for w in ask_walls), default=0),
            'total_bid_value': sum(w['value_usd'] for w in bid_walls),
            'total_ask_value': sum(w['value_usd'] for w in ask_walls),
            'spoofing_events_1min': len(self.get_spoofing_events(60)),
            'total_walls_detected': self.total_walls_detected,
            'total_spoofing_events': self.spoofing_events
        }
    
    def get_stats(self) -> Dict:
        """Get detector statistics."""
        return self.get_wall_summary()


if __name__ == "__main__":
    """Test order wall detector."""
    
    logging.basicConfig(level=logging.DEBUG)
    
    # Create detector
    detector = OrderWallDetector('BTCUSDT')
    
    # Simulate orderbook with walls
    test_orderbook = {
        'bids': [
            [95000, 0.5],   # Normal
            [94900, 0.6],   # Normal
            [94800, 5.0],   # WALL (5x average)
            [94700, 0.4],
        ],
        'asks': [
            [95100, 0.5],
            [95200, 10.0],  # WALL (10x average)
            [95300, 0.6],
            [95400, 0.5],
        ]
    }
    
    # Detect walls
    detector.on_orderbook_update(test_orderbook)
    
    print("=" * 60)
    print("ORDER WALL DETECTOR TEST")
    print("=" * 60)
    
    summary = detector.get_wall_summary()
    print(f"\nWall Summary:")
    print(f"  Total walls: {summary['total_walls']}")
    print(f"  Bid walls: {summary['bid_walls']}")
    print(f"  Ask walls: {summary['ask_walls']}")
    print(f"  Largest bid: ${summary['largest_bid_wall']:,.0f}")
    print(f"  Largest ask: ${summary['largest_ask_wall']:,.0f}")
    
    print(f"\nActive Walls:")
    for wall in detector.get_all_walls():
        print(f"  {wall['side']} @ ${wall['price']:,.0f} | "
              f"${wall['value_usd']:,.0f} | "
              f"{wall['size_ratio']:.1f}x avg | "
              f"Level {wall['level']}")
