"""
Week 2 Task 2.3: Ghost Order Filter
====================================

Detects and filters "ghost orders" - large orders placed and quickly cancelled (spoofing).

Expert Guidance (Expert #2 - Q2):
- FORWARD-ONLY discounting (NO retroactive signal invalidation)
- Track repeat offender PRICE BUCKETS (not relative levels)
- Discount factor: 0.15× for 60 seconds
- Detection: Orders >5× median size, lifespan <10s

Why Price Buckets:
"Spoofing clusters around psychological prices, VWAP, round numbers.
Level index (L3, L5) is irrelevant once price moves."

Implementation:
1. Detect large short-lived orders
2. Mark price bucket as suspicious
3. Apply forward discount (0.15×) for next 60s
4. Track repeat offenders locally (increase λ for that bucket)
"""

import numpy as np
from typing import Dict, List, Set
from collections import defaultdict, deque
import logging
import time

logger = logging.getLogger(__name__)


class GhostOrderFilter:
    """
    Detect and discount ghost orders (spoofing) using price bucket tracking.
    """
    
    # LOCKED PARAMETERS (per expert Q2)
    SIZE_THRESHOLD_MULTIPLIER = 5.0  # >5× median = ghost candidate
    LIFESPAN_THRESHOLD_SECONDS = 10   # <10s = ghost
    DISCOUNT_FACTOR = 0.15            # 15% weight for ghost-flagged buckets
    DISCOUNT_DURATION_SECONDS = 60    # Forward discount for 60s
    
    def __init__(self, symbol: str, tick_size: float = 0.01):
        """
        Initialize ghost order filter.
        
        Args:
            symbol: Trading symbol
            tick_size: Price tick size for bucketing (default: $0.01 for most crypto)
        """
        self.symbol = symbol
        self.tick_size = tick_size
        
        # Track orderbook history to detect ghosts
        self.orderbook_history: deque = deque(maxlen=20)  # Last 20 snapshots
        
        # Track median order size (for ghost detection threshold)
        self.order_sizes: deque = deque(maxlen=100)
        
        # Ghost flags per price bucket
        # price_bucket → {'expires_at': timestamp, 'discount': float, 'count': int}
        self.ghost_buckets: Dict[float, Dict] = {}
        
        # Repeat offender tracking
        self.repeat_offender_buckets: Dict[float, int] = defaultdict(int)
        
    def update(self, orderbook: Dict, timestamp: float):
        """
        Update with new orderbook snapshot and detect ghosts.
        
        Args:
            orderbook: {
                'bids': [[price, qty], ...],
                'asks': [[price, qty], ...]
            }
            timestamp: Current timestamp
        """
        snapshot = {
            'timestamp': timestamp,
            'bids': {self._price_to_bucket(float(p)): float(q) 
                     for p, q in orderbook.get('bids', [])[:20]},
            'asks': {self._price_to_bucket(float(p)): float(q) 
                     for p, q in orderbook.get('asks', [])[:20]}
        }
        
        # Detect ghosts by comparing with previous snapshots
        if len(self.orderbook_history) > 0:
            self._detect_ghosts(snapshot)
        
        self.orderbook_history.append(snapshot)
        
        # Update median order size
        for side in ['bids', 'asks']:
            for qty in snapshot[side].values():
                self.order_sizes.append(qty)
        
        # Clean expired ghost flags
        self._clean_expired_flags(timestamp)
        
    def _price_to_bucket(self, price: float) -> float:
        """
        Convert price to bucket (round to tick_size).
        
        Expert: "Track absolute price levels (e.g., $87,850), not relative levels (L3, L5)"
        """
        return round(price / self.tick_size) * self.tick_size
    
    def _get_median_order_size(self) -> float:
        """Get median order size for ghost detection threshold."""
        if len(self.order_sizes) == 0:
            return 1.0  # Default
        return float(np.median(list(self.order_sizes)))
    
    def _detect_ghosts(self, current_snapshot: Dict):
        """
        Detect ghost orders by finding large orders that appeared and disappeared quickly.
        """
        current_time = current_snapshot['timestamp']
        median_size = self._get_median_order_size()
        ghost_threshold = median_size * self.SIZE_THRESHOLD_MULTIPLIER
        
        # Look back through recent snapshots
        for i in range(len(self.orderbook_history) - 1, max(0, len(self.orderbook_history) - 5), -1):
            past_snapshot = self.orderbook_history[i]
            age = current_time - past_snapshot['timestamp']
            
            if age > self.LIFESPAN_THRESHOLD_SECONDS:
                break  # Too old to be a ghost
            
            # Check both sides
            for side in ['bids', 'asks']:
                past_levels = past_snapshot[side]
                current_levels = current_snapshot[side]
                
                # Find large orders that disappeared
                for price_bucket, past_qty in past_levels.items():
                    current_qty = current_levels.get(price_bucket, 0)
                    
                    # Check if large order disappeared
                    if past_qty >= ghost_threshold and current_qty < past_qty * 0.2:
                        # Large order (>5× median) disappeared quickly (<10s)
                        # → Likely ghost
                        disappeared_qty = past_qty - current_qty
                        
                        if disappeared_qty >= ghost_threshold * 0.8:  # At least 80% of size gone
                            self._flag_ghost_bucket(price_bucket, current_time, disappeared_qty)
    
    def _flag_ghost_bucket(self, price_bucket: float, timestamp: float, ghost_size: float):
        """
        Flag a price bucket as containing ghost orders.
        
        FORWARD-ONLY: Applies discount to future signals, NO retroactive invalidation.
        """
        # Check if already flagged (extend expiry)
        if price_bucket in self.ghost_buckets:
            existing = self.ghost_buckets[price_bucket]
            existing['expires_at'] = max(existing['expires_at'], 
                                        timestamp + self.DISCOUNT_DURATION_SECONDS)
            existing['count'] += 1
        else:
            # New ghost detection
            self.ghost_buckets[price_bucket] = {
                'expires_at': timestamp + self.DISCOUNT_DURATION_SECONDS,
                'discount': self.DISCOUNT_FACTOR,
                'count': 1,
                'first_seen': timestamp
            }
        
        # Track repeat offenders
        self.repeat_offender_buckets[price_bucket] += 1
        
        logger.info(f"Ghost detected at price bucket ${price_bucket:,.2f} "
                   f"(size: {ghost_size:.4f}, repeat count: {self.repeat_offender_buckets[price_bucket]})")
    
    def apply_ghost_discount(self, depth: float, price: float, timestamp: float) -> float:
        """
        Apply forward discount to depth if price bucket is flagged as ghost.
        
        Args:
            depth: Original depth at price
            price: Price of the level
            timestamp: Current timestamp
            
        Returns:
            Discounted depth (0.15× if ghost-flagged, 1.0× if clean)
        """
        price_bucket = self._price_to_bucket(price)
        
        if price_bucket in self.ghost_buckets:
            ghost_info = self.ghost_buckets[price_bucket]
            
            # Check if still active
            if timestamp < ghost_info['expires_at']:
                # Apply discount
                discounted = depth * ghost_info['discount']
                
                # If repeat offender, apply additional local λ increase
                # (per expert: "Increase λ locally for that bucket")
                if self.repeat_offender_buckets[price_bucket] >= 3:
                    # Severe repeat offender - additional 50% discount
                    discounted *= 0.5
                
                return discounted
        
        # No ghost flag or expired
        return depth
    
    def get_ghost_buckets(self) -> List[Dict]:
        """
        Get currently flagged ghost buckets.
        
        Returns:
            List of {price_bucket, expires_at, count, first_seen}
        """
        current_time = time.time()
        
        active_ghosts = []
        for price_bucket, info in self.ghost_buckets.items():
            if current_time < info['expires_at']:
                active_ghosts.append({
                    'price_bucket': price_bucket,
                    'expires_at': info['expires_at'],
                    'count': info['count'],
                    'first_seen': info['first_seen'],
                    'discount': info['discount'],
                    'is_repeat_offender': self.repeat_offender_buckets[price_bucket] >= 3
                })
        
        return active_ghosts
    
    def is_price_bucket_toxic(self, price: float, timestamp: float) -> bool:
        """Check if a price bucket is currently flagged as ghost."""
        price_bucket = self._price_to_bucket(price)
        
        if price_bucket in self.ghost_buckets:
            return timestamp < self.ghost_buckets[price_bucket]['expires_at']
        
        return False
    
    def _clean_expired_flags(self, current_time: float):
        """Remove expired ghost flags."""
        expired = [
            bucket for bucket, info in self.ghost_buckets.items()
            if current_time >= info['expires_at']
        ]
        
        for bucket in expired:
            del self.ghost_buckets[bucket]
    
    def get_stats(self) -> Dict:
        """Get ghost filter statistics."""
        active_ghosts = len([b for b, info in self.ghost_buckets.items() 
                            if time.time() < info['expires_at']])
        
        total_detections = sum(self.repeat_offender_buckets.values())
        repeat_offenders = sum(1 for count in self.repeat_offender_buckets.values() if count >= 3)
        
        return {
            'active_ghost_buckets': active_ghosts,
            'total_detections': total_detections,
            'repeat_offenders': repeat_offenders,
            'discount_factor': self.DISCOUNT_FACTOR,
            'discount_duration_seconds': self.DISCOUNT_DURATION_SECONDS,
            'size_threshold_multiplier': self.SIZE_THRESHOLD_MULTIPLIER
        }


if __name__ == "__main__":
    """Test ghost order filter."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 2 TASK 2.3: GHOST ORDER FILTER TEST")
    print("=" * 80)
    print("\n🔒 LOCKED PARAMETERS (per expert Q2):")
    print(f"   Size threshold: {GhostOrderFilter.SIZE_THRESHOLD_MULTIPLIER}× median")
    print(f"   Lifespan threshold: {GhostOrderFilter.LIFESPAN_THRESHOLD_SECONDS}s")
    print(f"   Discount factor: {GhostOrderFilter.DISCOUNT_FACTOR} (15%)")
    print(f"   Discount duration: {GhostOrderFilter.DISCOUNT_DURATION_SECONDS}s")
    print(f"   Forward-only: YES (no retroactive invalidation)\n")
    
    ghost_filter = GhostOrderFilter('BTCUSDT', tick_size=1.0)
    
    # Simulate ghost order scenario
    print("Simulating spoofing scenario...")
    base_price = 100000
    
    # T=0: Normal orderbook
    orderbook_t0 = {
        'bids': [[base_price - i, 1.0] for i in range(1, 11)],
        'asks': [[base_price + i, 1.0] for i in range(1, 11)]
    }
    ghost_filter.update(orderbook_t0, time.time())
    print(f"T=0s: Normal orderbook")
    time.sleep(0.5)
    
    # T=1: Large ghost order appears at $99,997
    ghost_price = base_price - 3
    orderbook_t1 = {
        'bids': [[base_price - i, 20.0 if i == 3 else 1.0] for i in range(1, 11)],
        'asks': [[base_price + i, 1.0] for i in range(1, 11)]
    }
    ghost_filter.update(orderbook_t1, time.time())
    print(f"T=1s: Large order (20× median) appears at ${ghost_price:,}")
    time.sleep(0.5)
    
    # T=2-8: Ghost order persists
    for t in range(2, 9):
        ghost_filter.update(orderbook_t1, time.time())
        time.sleep(0.2)
    
    # T=9: Ghost order disappears (within 10s threshold)
    orderbook_t9 = orderbook_t0  # Back to normal
    ghost_filter.update(orderbook_t9, time.time())
    print(f"T=9s: Large order disappears (GHOST DETECTED)")
    
    # Check ghost flags
    print("\n" + "=" * 80)
    print("GHOST DETECTION RESULTS")
    print("=" * 80)
    
    ghost_buckets = ghost_filter.get_ghost_buckets()
    print(f"\n⚠️  Active Ghost Buckets: {len(ghost_buckets)}")
    
    for bucket_info in ghost_buckets:
        print(f"\n   Price Bucket: ${bucket_info['price_bucket']:,.2f}")
        print(f"   Detections: {bucket_info['count']}")
        print(f"   Discount: {bucket_info['discount'] * 100:.0f}%")
        print(f"   Expires: {bucket_info['expires_at'] - time.time():.1f}s from now")
        print(f"   Repeat Offender: {'YES' if bucket_info['is_repeat_offender'] else 'NO'}")
    
    # Test forward discount
    print("\n" + "=" * 80)
    print("FORWARD DISCOUNT TEST")
    print("=" * 80)
    
    test_depth = 10.0
    discounted = ghost_filter.apply_ghost_discount(test_depth, ghost_price, time.time())
    
    print(f"\n   Original depth at ${ghost_price:,}: {test_depth:.2f}")
    print(f"   Discounted depth: {discounted:.2f}")
    print(f"   Discount applied: {(1 - discounted/test_depth) * 100:.0f}%")
    
    # Stats
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    stats = ghost_filter.get_stats()
    for key, value in stats.items():
        print(f"   {key:<30s}: {value}")
    
    print("\n✅ Test complete - Ready for integration with toxicity modules")
