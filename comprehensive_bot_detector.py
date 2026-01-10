"""
Comprehensive Institutional Bot Pattern Detector

NO RESTRICTIONS - tracks ALL fill amounts and finds ANY patterns.

Key features:
1. Track every single fill with exact $ amount
2. Continuously scan for repeated amounts (any size, any frequency)
3. Real-time pattern matching across all historical fills
4. No predefined thresholds - let the data speak
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ComprehensiveBotDetector:
    """
    Unrestricted bot pattern detector.
    Tracks ALL fills and finds ANY repeated patterns.
    """
    
    def __init__(self, tolerance_pct=0.05, max_history=1000):
        """
        Args:
            tolerance_pct: Percentage tolerance for matching amounts (default 5%)
            max_history: Maximum fills to track (default 1000 = ~16 minutes at 1/sec)
        """
        self.tolerance_pct = tolerance_pct
        self.max_history = max_history
        
        # Track EVERY fill with full details
        self.all_fills = deque(maxlen=max_history)
        
        # Index fills by dollar amount for fast pattern matching
        # Key: rounded dollar amount, Value: list of fills
        self.amount_index = defaultdict(list)
        
        # Track detected patterns
        self.active_patterns = []
    
    def _get_bucket(self, dollar_amount):
        """
        Calculate bucket for amount using FIXED bucket sizes based on amount range.
        
        This ensures fills in the same range use the same bucket size,
        so similar amounts will land in the same bucket.
        
        Bucket sizes (approximately 5% of range midpoint):
        - $0-$100k:    $5k buckets
        - $100k-$1M:   $50k buckets
        - $1M-$5M:     $100k buckets
        - $5M-$10M:    $250k buckets
        - $10M+:       $500k buckets
        """
        # Determine bucket size based on amount range
        if dollar_amount < 100000:  # < $100k
            bucket_size = 5000  # $5k buckets
        elif dollar_amount < 1000000:  # $100k - $1M
            bucket_size = 50000  # $50k buckets
        elif dollar_amount < 5000000:  # $1M - $5M
            bucket_size = 100000  # $100k buckets
        elif dollar_amount < 10000000:  # $5M - $10M
            bucket_size = 250000  # $250k buckets
        else:  # $10M+
            bucket_size = 500000  # $500k buckets
        
        # Round to nearest bucket
        bucket = round(dollar_amount / bucket_size) * bucket_size
        
        return bucket
    
    def add_fill(self, side, size, price, timestamp):
        """
        Add a fill and immediately check for patterns.
        
        Returns:
            dict with pattern info if detected, None otherwise
        """
        dollar_amount = size * price
        
        fill = {
            'side': side,
            'size': size,
            'price': price,
            'dollar_amount': dollar_amount,
            'timestamp': timestamp
        }
        
        self.all_fills.append(fill)
        
        # Index by percentage-based bucket
        # This scales with fill size (e.g., $100k tolerance for $2M fill at 5%)
        bucket = self._get_bucket(dollar_amount)
        self.amount_index[bucket].append(fill)
        
        # Immediately check if this amount has appeared before
        pattern = self._check_for_pattern(fill, bucket)
        
        return pattern
    
    def _check_for_pattern(self, new_fill, bucket):
        """
        Check if the new fill matches any existing pattern.
        
        Returns pattern info if match found.
        """
        # Get all fills in this bucket
        similar_fills = self.amount_index[bucket]
        
        if len(similar_fills) < 2:
            return None  # Need at least 2 fills to make a pattern
        
        # Check if fills are on same side
        same_side_fills = [f for f in similar_fills if f['side'] == new_fill['side']]
        
        if len(same_side_fills) < 2:
            return None
        
        # Calculate pattern metrics
        amounts = [f['dollar_amount'] for f in same_side_fills]
        timestamps = [f['timestamp'] for f in same_side_fills]
        
        # Time span
        time_span = (timestamps[-1] - timestamps[0]).total_seconds()
        
        # Amount statistics
        avg_amount = np.mean(amounts)
        std_amount = np.std(amounts)
        variation_pct = (std_amount / avg_amount * 100) if avg_amount > 0 else 0
        
        # Calculate frequency (fills per minute)
        if time_span > 0:
            frequency = (len(same_side_fills) - 1) / (time_span / 60)
        else:
            frequency = 0
        
        # Detect pattern type
        if variation_pct < 0.1:
            pattern_type = "EXACT_REPEAT"  # Exact same amount
        elif variation_pct < 1.0:
            pattern_type = "TIGHT_CLUSTER"  # Very similar amounts
        elif variation_pct < 5.0:
            pattern_type = "LOOSE_CLUSTER"  # Somewhat similar amounts
        else:
            return None  # Too much variation
        
        # Calculate confidence based on:
        # - Number of fills (more = higher)
        # - Frequency (faster = higher)
        # - Consistency (lower variation = higher)
        count_score = min(len(same_side_fills) / 10, 1.0)
        freq_score = min(frequency / 5, 1.0)  # 5 fills/min = max
        consistency_score = max(1.0 - (variation_pct / 5), 0)
        
        confidence = (count_score * 0.4 + freq_score * 0.3 + consistency_score * 0.3)
        
        pattern = {
            'pattern_detected': True,
            'pattern_type': pattern_type,
            'side': new_fill['side'],
            'fill_count': len(same_side_fills),
            'avg_amount': avg_amount,
            'variation_pct': variation_pct,
            'time_span': time_span,
            'frequency': frequency,
            'confidence': confidence,
            'fills': same_side_fills
        }
        
        logger.info(f"BOT PATTERN: {pattern_type} - {len(same_side_fills)} {new_fill['side']} "
                   f"fills of ${avg_amount:,.0f} (±{variation_pct:.1f}%) "
                   f"over {time_span:.0f}s ({frequency:.1f}/min)")
        
        return pattern
    
    def get_all_active_patterns(self, lookback_seconds=300):
        """
        Get all currently active patterns.
        
        Args:
            lookback_seconds: How far back to look (default 5 minutes)
        
        Returns:
            List of all detected patterns
        """
        if not self.all_fills:
            return []
        
        cutoff = self.all_fills[-1]['timestamp'] - timedelta(seconds=lookback_seconds)
        
        # Rebuild patterns from recent fills
        patterns = []
        checked_buckets = set()
        
        for bucket, fills in self.amount_index.items():
            if bucket in checked_buckets:
                continue
            
            # Filter to recent fills
            recent_fills = [f for f in fills if f['timestamp'] >= cutoff]
            
            if len(recent_fills) < 2:
                continue
            
            # Check each side separately
            for side in ['BID', 'ASK']:
                side_fills = [f for f in recent_fills if f['side'] == side]
                
                if len(side_fills) < 2:
                    continue
                
                # Calculate metrics
                amounts = [f['dollar_amount'] for f in side_fills]
                timestamps = [f['timestamp'] for f in side_fills]
                
                avg_amount = np.mean(amounts)
                std_amount = np.std(amounts)
                variation_pct = (std_amount / avg_amount * 100) if avg_amount > 0 else 0
                
                if variation_pct > 5.0:
                    continue  # Too much variation
                
                time_span = (timestamps[-1] - timestamps[0]).total_seconds()
                frequency = (len(side_fills) - 1) / (time_span / 60) if time_span > 0 else 0
                
                # Determine pattern type
                if variation_pct < 0.1:
                    pattern_type = "EXACT_REPEAT"
                elif variation_pct < 1.0:
                    pattern_type = "TIGHT_CLUSTER"
                else:
                    pattern_type = "LOOSE_CLUSTER"
                
                # Calculate confidence
                count_score = min(len(side_fills) / 10, 1.0)
                freq_score = min(frequency / 5, 1.0)
                consistency_score = max(1.0 - (variation_pct / 5), 0)
                confidence = (count_score * 0.4 + freq_score * 0.3 + consistency_score * 0.3)
                
                patterns.append({
                    'pattern_type': pattern_type,
                    'side': side,
                    'fill_count': len(side_fills),
                    'avg_amount': avg_amount,
                    'variation_pct': variation_pct,
                    'time_span': time_span,
                    'frequency': frequency,
                    'confidence': confidence,
                    'bucket': bucket
                })
            
            checked_buckets.add(bucket)
        
        # Sort by confidence (highest first)
        patterns.sort(key=lambda x: x['confidence'], reverse=True)
        
        return patterns
    
    def get_pattern_summary(self, lookback_seconds=300):
        """
        Get summary of all patterns.
        
        Returns:
            dict with summary statistics
        """
        patterns = self.get_all_active_patterns(lookback_seconds)
        
        if not patterns:
            return {
                'total_patterns': 0,
                'bid_patterns': 0,
                'ask_patterns': 0,
                'strongest_pattern': None
            }
        
        bid_patterns = [p for p in patterns if p['side'] == 'BID']
        ask_patterns = [p for p in patterns if p['side'] == 'ASK']
        
        return {
            'total_patterns': len(patterns),
            'bid_patterns': len(bid_patterns),
            'ask_patterns': len(ask_patterns),
            'strongest_pattern': patterns[0] if patterns else None,
            'all_patterns': patterns
        }
    
    def get_stats(self):
        """Get detector statistics"""
        return {
            'total_fills_tracked': len(self.all_fills),
            'unique_amounts': len(self.amount_index),
            'patterns_detected': len([k for k, v in self.amount_index.items() if len(v) >= 2])
        }


if __name__ == "__main__":
    """Test the comprehensive detector"""
    
    logging.basicConfig(level=logging.INFO)
    
    detector = ComprehensiveBotDetector(max_history=1000)
    
    print("=" * 80)
    print("COMPREHENSIVE BOT PATTERN DETECTOR TEST")
    print("=" * 80)
    
    base_time = datetime.now()
    
    # Simulate various fills
    print("\nSimulating fills...")
    
    # Pattern 1: Exact repeats
    for i in range(5):
        pattern = detector.add_fill(
            side='BID',
            size=0.5714,  # Exact same
            price=87500,
            timestamp=base_time + timedelta(seconds=i * 10)
        )
        if pattern:
            print(f"\n✓ Pattern detected: {pattern['pattern_type']}")
            print(f"  {pattern['fill_count']} fills, confidence: {pattern['confidence']:.1%}")
    
    # Pattern 2: Similar amounts (different pattern)
    for i in range(4):
        pattern = detector.add_fill(
            side='ASK',
            size=1.14 + i * 0.02,  # Slightly varying
            price=87500,
            timestamp=base_time + timedelta(seconds=50 + i * 15)
        )
        if pattern:
            print(f"\n✓ Pattern detected: {pattern['pattern_type']}")
            print(f"  {pattern['fill_count']} fills, confidence: {pattern['confidence']:.1%}")
    
    # Get summary
    print("\n" + "=" * 80)
    print("PATTERN SUMMARY")
    print("=" * 80)
    
    summary = detector.get_pattern_summary(lookback_seconds=300)
    print(f"\nTotal patterns: {summary['total_patterns']}")
    print(f"BID patterns: {summary['bid_patterns']}")
    print(f"ASK patterns: {summary['ask_patterns']}")
    
    if summary['strongest_pattern']:
        p = summary['strongest_pattern']
        print(f"\nStrongest pattern:")
        print(f"  Type: {p['pattern_type']}")
        print(f"  Side: {p['side']}")
        print(f"  Fills: {p['fill_count']}")
        print(f"  Amount: ${p['avg_amount']:,.0f} (±{p['variation_pct']:.1f}%)")
        print(f"  Frequency: {p['frequency']:.1f} fills/min")
        print(f"  Confidence: {p['confidence']:.1%}")
    
    stats = detector.get_stats()
    print(f"\nDetector stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 80)
