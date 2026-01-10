"""
Week 2 Task 2.2: Cancel-to-Trade Ratio (CTR) Calculator
========================================================

Detects spoofing by measuring order cancellation rate per price level.

Expert Guidance (Expert #2 - Q3):
- Use FIXED 10-second window (not adaptive)
- Threshold: CTR > 4.0 indicates toxic level
- Calculate per level, then aggregate via weighted average
- Epsilon (minimum trade volume) per symbol:
  * BTC: 0.001
  * ETH: 0.01
  * SOL: 1.0

Formula:
    CTR(level) = cancelled_volume / (executed_volume + ε)
    
    If CTR > 4.0 → Level is toxic (likely spoofing)

Interpretation:
- High CTR = Orders placed and cancelled without execution (spoofing)
- Low CTR = Orders being filled (real liquidity)
"""

import numpy as np
from typing import Dict, List, Tuple, Deque
from collections import deque, defaultdict
import logging
import time

logger = logging.getLogger(__name__)


class CTRCalculator:
    """
    Calculate Cancel-to-Trade Ratio per price level to detect spoofing.
    
    Infers cancellations from orderbook snapshot changes.
    """
    
    # LOCKED PARAMETERS (per expert decision Q3)
    CTR_WINDOW_SECONDS = 10  # Fixed window (DO NOT make adaptive)
    CTR_THRESHOLD = 4.0      # Toxic if CTR > 4.0
    
    # Epsilon values (minimum trade volume to avoid division by zero)
    EPSILON = {
        'BTCUSDT': 0.001,
        'ETHUSDT': 0.01,
        'SOLUSDT': 1.0
    }
    
    def __init__(self, symbol: str):
        """
        Initialize CTR calculator.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        self.epsilon = self.EPSILON.get(symbol, 0.01)  # Default for unknown symbols
        
        # Store orderbook snapshots for cancellation inference
        self.snapshot_history: Deque[Dict] = deque(maxlen=self.CTR_WINDOW_SECONDS * 2)
        
        # Track trades (executed volume) per price level
        self.trade_history: Deque[Dict] = deque(maxlen=100)
        
        # CTR values per price level (price_bucket → CTR)
        self.ctr_per_level: Dict[float, float] = {}
        
        # Toxic levels cache
        self.toxic_levels: Dict[float, float] = {}  # price → CTR value
        
    def update_orderbook(self, orderbook: Dict, timestamp: float):
        """
        Update with new orderbook snapshot and infer cancellations.
        
        Args:
            orderbook: {
                'bids': [[price, qty], ...],
                'asks': [[price, qty], ...]
            }
            timestamp: Current timestamp
        """
        snapshot = {
            'timestamp': timestamp,
            'bids': {float(p): float(q) for p, q in orderbook.get('bids', [])[:20]},
            'asks': {float(p): float(q) for p, q in orderbook.get('asks', [])[:20]}
        }
        
        # Infer cancellations if we have previous snapshot
        if len(self.snapshot_history) > 0:
            self._infer_cancellations(snapshot)
        
        self.snapshot_history.append(snapshot)
        
        # Clean old data
        self._clean_old_data(timestamp)
        
    def update_trade(self, trade: Dict):
        """
        Update with executed trade.
        
        Args:
            trade: {
                'price': float,
                'quantity': float,
                'timestamp': float,
                'side': 'BUY' or 'SELL'
            }
        """
        self.trade_history.append({
            'price': float(trade['price']),
            'quantity': float(trade['quantity']),
            'timestamp': float(trade['timestamp']),
            'side': trade['side']
        })
        
    def _infer_cancellations(self, current_snapshot: Dict):
        """
        Infer cancelled volume by comparing snapshots.
        
        Cancellation = Previous depth - Current depth (if decreased without trade)
        """
        if len(self.snapshot_history) == 0:
            return
        
        prev_snapshot = self.snapshot_history[-1]
        current_time = current_snapshot['timestamp']
        
        # Analyze both bid and ask sides
        for side in ['bids', 'asks']:
            prev_levels = prev_snapshot[side]
            curr_levels = current_snapshot[side]
            
            # Find prices that decreased in depth (potential cancellations)
            for price, prev_qty in prev_levels.items():
                curr_qty = curr_levels.get(price, 0)
                
                if curr_qty < prev_qty:
                    # Depth decreased - check if it was due to trade or cancellation
                    qty_decreased = prev_qty - curr_qty
                    
                    # Check if there was a trade at this price
                    executed_qty = self._get_executed_volume_at_price(
                        price, 
                        prev_snapshot['timestamp'],
                        current_time
                    )
                    
                    # Inferred cancellation = decrease - executed
                    cancelled_qty = max(qty_decreased - executed_qty, 0)
                    
                    if cancelled_qty > self.epsilon * 0.1:  # Only track meaningful cancellations
                        # Store cancellation event
                        if not hasattr(self, 'cancellation_history'):
                            self.cancellation_history = deque(maxlen=200)
                        
                        self.cancellation_history.append({
                            'price': price,
                            'quantity': cancelled_qty,
                            'timestamp': current_time,
                            'side': side
                        })
    
    def _get_executed_volume_at_price(self, price: float, start_time: float, end_time: float) -> float:
        """
        Get total executed volume at a specific price in time window.
        """
        price_tolerance = price * 0.0001  # 0.01% tolerance
        
        executed = 0
        for trade in self.trade_history:
            if start_time <= trade['timestamp'] <= end_time:
                if abs(trade['price'] - price) < price_tolerance:
                    executed += trade['quantity']
        
        return executed
    
    def calculate_ctr_per_level(self, num_levels: int = 10) -> Dict[float, float]:
        """
        Calculate CTR for each price level in current orderbook.
        
        Args:
            num_levels: Number of levels to analyze
            
        Returns:
            Dict mapping price → CTR value
        """
        if len(self.snapshot_history) == 0:
            return {}
        
        current_snapshot = self.snapshot_history[-1]
        current_time = current_snapshot['timestamp']
        cutoff_time = current_time - self.CTR_WINDOW_SECONDS
        
        ctr_results = {}
        
        # Analyze both sides
        for side in ['bids', 'asks']:
            levels = current_snapshot[side]
            
            # Get top N levels
            sorted_prices = sorted(levels.keys(), reverse=(side == 'bids'))[:num_levels]
            
            for price in sorted_prices:
                # Calculate cancelled volume at this price (last 10s)
                cancelled_volume = 0
                if hasattr(self, 'cancellation_history'):
                    for cancel_event in self.cancellation_history:
                        if cancel_event['timestamp'] >= cutoff_time:
                            if abs(cancel_event['price'] - price) < price * 0.0001:
                                cancelled_volume += cancel_event['quantity']
                
                # Calculate executed volume at this price (last 10s)
                executed_volume = 0
                for trade in self.trade_history:
                    if trade['timestamp'] >= cutoff_time:
                        if abs(trade['price'] - price) < price * 0.0001:
                            executed_volume += trade['quantity']
                
                # Calculate CTR
                ctr = cancelled_volume / (executed_volume + self.epsilon)
                ctr_results[price] = ctr
                
                # Flag toxic levels
                if ctr > self.CTR_THRESHOLD:
                    self.toxic_levels[price] = ctr
        
        self.ctr_per_level = ctr_results
        return ctr_results
    
    def get_weighted_average_ctr(self, side: str = 'both') -> float:
        """
        Calculate weighted average CTR across levels.
        
        Args:
            side: 'bid', 'ask', or 'both'
            
        Returns:
            Weighted average CTR
        """
        if len(self.snapshot_history) == 0:
            return 0.0
        
        current_snapshot = self.snapshot_history[-1]
        
        total_ctr_weighted = 0
        total_weight = 0
        
        for price, ctr in self.ctr_per_level.items():
            # Determine side
            if side == 'bid' and price not in current_snapshot['bids']:
                continue
            if side == 'ask' and price not in current_snapshot['asks']:
                continue
            
            # Weight by depth at that level
            depth = current_snapshot['bids'].get(price, 0) + current_snapshot['asks'].get(price, 0)
            
            total_ctr_weighted += ctr * depth
            total_weight += depth
        
        if total_weight == 0:
            return 0.0
        
        return total_ctr_weighted / total_weight
    
    def get_toxic_levels(self) -> List[Dict]:
        """
        Get list of toxic price levels (CTR > threshold).
        
        Returns:
            List of {price, ctr, side}
        """
        if len(self.snapshot_history) == 0:
            return []
        
        current_snapshot = self.snapshot_history[-1]
        
        toxic_list = []
        for price, ctr in self.toxic_levels.items():
            side = 'bid' if price in current_snapshot['bids'] else 'ask'
            toxic_list.append({
                'price': price,
                'ctr': ctr,
                'side': side,
                'threshold': self.CTR_THRESHOLD
            })
        
        return toxic_list
    
    def apply_toxicity_discount(self, depth: float, price: float) -> float:
        """
        Apply discount to depth if price level is toxic.
        
        Args:
            depth: Original depth at price level
            price: Price of the level
            
        Returns:
            Discounted depth (0.5× if toxic, 1.0× if clean)
        """
        ctr = self.ctr_per_level.get(price, 0)
        
        if ctr > self.CTR_THRESHOLD:
            # Toxic level - discount by 50%
            return depth * 0.5
        
        return depth
    
    def _clean_old_data(self, current_time: float):
        """Remove data older than window."""
        cutoff_time = current_time - (self.CTR_WINDOW_SECONDS * 2)
        
        # Clean toxic levels cache (keep recent toxic flags)
        self.toxic_levels = {
            price: ctr for price, ctr in self.toxic_levels.items()
            if current_time - cutoff_time < 60  # Keep for 1 minute
        }
    
    def get_stats(self) -> Dict:
        """Get CTR statistics."""
        toxic_count = len(self.toxic_levels)
        total_levels = len(self.ctr_per_level)
        
        return {
            'total_levels_tracked': total_levels,
            'toxic_levels_count': toxic_count,
            'toxic_pct': (toxic_count / total_levels * 100) if total_levels > 0 else 0,
            'avg_ctr': np.mean(list(self.ctr_per_level.values())) if self.ctr_per_level else 0,
            'max_ctr': max(list(self.ctr_per_level.values())) if self.ctr_per_level else 0,
            'ctr_threshold': self.CTR_THRESHOLD,
            'window_seconds': self.CTR_WINDOW_SECONDS,
            'epsilon': self.epsilon
        }


if __name__ == "__main__":
    """Test CTR calculator."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 2 TASK 2.2: CTR (CANCEL-TO-TRADE RATIO) TEST")
    print("=" * 80)
    print("\n🔒 LOCKED PARAMETERS (per expert Q3):")
    print(f"   CTR Window: {CTRCalculator.CTR_WINDOW_SECONDS}s (fixed)")
    print(f"   CTR Threshold: {CTRCalculator.CTR_THRESHOLD}")
    print(f"   Epsilon (BTC): {CTRCalculator.EPSILON['BTCUSDT']}")
    print(f"   Epsilon (ETH): {CTRCalculator.EPSILON['ETHUSDT']}")
    print(f"   Epsilon (SOL): {CTRCalculator.EPSILON['SOLUSDT']}\n")
    
    calc = CTRCalculator('BTCUSDT')
    
    # Simulate orderbook with spoofing
    print("Simulating orderbook with spoofing behavior...")
    base_price = 100000
    
    for t in range(15):
        timestamp = time.time() + t
        
        # Create orderbook with large orders that will be cancelled
        bids = [[base_price - i, 10.0 if i == 3 else 1.0] for i in range(1, 11)]
        asks = [[base_price + i, 1.0] for i in range(1, 11)]
        
        orderbook = {'bids': bids, 'asks': asks}
        calc.update_orderbook(orderbook, timestamp)
        
        # Simulate some trades (minimal execution at spoofed level)
        if t % 5 == 0:
            calc.update_trade({
                'price': base_price - 3,
                'quantity': 0.1,  # Small execution despite large order
                'timestamp': timestamp,
                'side': 'SELL'
            })
        
        time.sleep(0.1)
    
    # Calculate CTR
    print("\n" + "=" * 80)
    print("CALCULATING CTR PER LEVEL")
    print("=" * 80)
    
    ctr_results = calc.calculate_ctr_per_level(num_levels=5)
    
    print("\n📊 CTR by Price Level:")
    for price, ctr in sorted(ctr_results.items(), reverse=True)[:10]:
        toxic_flag = "⚠️ TOXIC" if ctr > CTRCalculator.CTR_THRESHOLD else "✅ Clean"
        print(f"   ${price:,.2f}: CTR = {ctr:.2f} {toxic_flag}")
    
    # Weighted average
    avg_ctr = calc.get_weighted_average_ctr()
    print(f"\n💡 Weighted Average CTR: {avg_ctr:.2f}")
    
    # Toxic levels
    toxic_levels = calc.get_toxic_levels()
    print(f"\n⚠️  Toxic Levels Detected: {len(toxic_levels)}")
    for level in toxic_levels:
        print(f"   {level['side'].upper()} ${level['price']:,.2f}: CTR = {level['ctr']:.2f}")
    
    # Stats
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    stats = calc.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<25s}: {value:.4f}")
        else:
            print(f"   {key:<25s}: {value}")
    
    print("\n✅ Test complete - Ready for integration with survival_weighted_depth.py")
