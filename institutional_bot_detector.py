"""
Institutional Bot Pattern Detector

Detects when multiple orders of similar $ amount appear in quick succession,
indicating algorithmic/institutional activity.

Patterns to detect:
1. Clustered fills: Multiple fills of similar size within short timeframe
2. Repeated patterns: Same size appearing multiple times
3. Round numbers: Institutional bots often use round $ amounts
"""

from collections import deque
from datetime import datetime, timedelta
import numpy as np
import logging

logger = logging.getLogger(__name__)


class InstitutionalBotDetector:
    """
    Detects institutional bot patterns in fill data.
    """
    
    def __init__(self, similarity_threshold=0.1, time_window=60):
        """
        Args:
            similarity_threshold: How similar sizes must be (10% = within 10% of each other)
            time_window: Time window to look for patterns (seconds)
        """
        self.similarity_threshold = similarity_threshold
        self.time_window = time_window
        
        # Track all fills with metadata
        self.all_fills = deque(maxlen=200)
    
    def add_fill(self, side, size, price, timestamp):
        """Add a new fill for pattern detection"""
        dollar_amount = size * price
        
        self.all_fills.append({
            'side': side,
            'size': size,
            'price': price,
            'dollar_amount': dollar_amount,
            'timestamp': timestamp
        })
    
    def detect_bot_pattern(self, current_time):
        """
        Detect if recent fills show bot pattern.
        
        Returns:
            dict with:
                - pattern_detected: bool
                - pattern_type: 'CLUSTERED', 'REPEATED', 'ROUND_NUMBERS'
                - confidence: 0-1
                - details: explanation
        """
        if len(self.all_fills) < 3:
            return {
                'pattern_detected': False,
                'pattern_type': None,
                'confidence': 0,
                'details': 'Not enough fills'
            }
        
        # Get recent fills
        cutoff = current_time - timedelta(seconds=self.time_window)
        recent_fills = [f for f in self.all_fills if f['timestamp'] >= cutoff]
        
        if len(recent_fills) < 3:
            return {
                'pattern_detected': False,
                'pattern_type': None,
                'confidence': 0,
                'details': 'Not enough recent fills'
            }
        
        # Check for different patterns
        clustered = self._detect_clustered_fills(recent_fills)
        if clustered['detected']:
            return clustered
        
        repeated = self._detect_repeated_pattern(recent_fills)
        if repeated['detected']:
            return repeated
        
        round_nums = self._detect_round_numbers(recent_fills)
        if round_nums['detected']:
            return round_nums
        
        return {
            'pattern_detected': False,
            'pattern_type': None,
            'confidence': 0,
            'details': 'No pattern detected'
        }
    
    def _detect_clustered_fills(self, fills):
        """
        Detect if multiple fills of similar size appeared close together.
        
        Institutional bots often split large orders into similar-sized chunks.
        """
        if len(fills) < 3:
            return {'detected': False}
        
        # Group fills by side
        bid_fills = [f for f in fills if f['side'] == 'BID']
        ask_fills = [f for f in fills if f['side'] == 'ASK']
        
        # Check each side
        for side_name, side_fills in [('BID', bid_fills), ('ASK', ask_fills)]:
            if len(side_fills) < 3:
                continue
            
            # Get dollar amounts
            amounts = [f['dollar_amount'] for f in side_fills]
            
            # Find clusters of similar amounts
            clusters = self._find_similar_clusters(amounts, side_fills)
            
            for cluster in clusters:
                if len(cluster['fills']) >= 3:
                    # Found cluster of 3+ similar fills
                    avg_amount = cluster['avg_amount']
                    time_span = (cluster['fills'][-1]['timestamp'] - 
                                cluster['fills'][0]['timestamp']).total_seconds()
                    
                    # Calculate confidence
                    # More fills = higher confidence
                    # Tighter time span = higher confidence
                    # More similar sizes = higher confidence
                    count_score = min(len(cluster['fills']) / 5, 1.0)
                    time_score = max(1.0 - (time_span / self.time_window), 0.3)
                    similarity_score = 1.0 - cluster['std_dev'] / cluster['avg_amount']
                    
                    confidence = (count_score * 0.4 + time_score * 0.3 + similarity_score * 0.3)
                    
                    return {
                        'pattern_detected': True,
                        'detected': True,
                        'pattern_type': 'CLUSTERED',
                        'confidence': confidence,
                        'details': (f"{len(cluster['fills'])} {side_name} fills of "
                                  f"~${avg_amount:,.0f} in {time_span:.0f}s "
                                  f"(institutional bot splitting order)"),
                        'cluster_size': len(cluster['fills']),
                        'avg_amount': avg_amount,
                        'side': side_name
                    }
        
        return {'detected': False}
    
    def _detect_repeated_pattern(self, fills):
        """
        Detect if same exact size appears multiple times.
        
        Bots often use exact same order size repeatedly.
        """
        if len(fills) < 3:
            return {'detected': False}
        
        # Group by side
        for side_name in ['BID', 'ASK']:
            side_fills = [f for f in fills if f['side'] == side_name]
            
            if len(side_fills) < 3:
                continue
            
            # Count exact matches (within 0.1%)
            amounts = [f['dollar_amount'] for f in side_fills]
            
            for i, amount in enumerate(amounts):
                matches = [j for j, a in enumerate(amounts) 
                          if abs(a - amount) / amount < 0.001]  # Within 0.1%
                
                if len(matches) >= 3:
                    # Found repeated pattern
                    matched_fills = [side_fills[j] for j in matches]
                    time_span = (matched_fills[-1]['timestamp'] - 
                                matched_fills[0]['timestamp']).total_seconds()
                    
                    confidence = min(len(matches) / 5, 1.0) * 0.9  # High confidence
                    
                    return {
                        'pattern_detected': True,
                        'detected': True,
                        'pattern_type': 'REPEATED',
                        'confidence': confidence,
                        'details': (f"{len(matches)} {side_name} fills of EXACT "
                                  f"${amount:,.0f} in {time_span:.0f}s "
                                  f"(bot using fixed order size)"),
                        'repeat_count': len(matches),
                        'amount': amount,
                        'side': side_name
                    }
        
        return {'detected': False}
    
    def _detect_round_numbers(self, fills):
        """
        Detect if fills are using round dollar amounts.
        
        Institutional bots often use round numbers like $10k, $25k, $50k, $100k.
        """
        if len(fills) < 3:
            return {'detected': False}
        
        round_thresholds = [10000, 25000, 50000, 100000, 250000, 500000, 1000000]
        
        for side_name in ['BID', 'ASK']:
            side_fills = [f for f in fills if f['side'] == side_name]
            
            if len(side_fills) < 3:
                continue
            
            # Check how many fills are near round numbers
            round_fills = []
            for fill in side_fills:
                amount = fill['dollar_amount']
                
                # Check if within 5% of a round number
                for threshold in round_thresholds:
                    if abs(amount - threshold) / threshold < 0.05:
                        round_fills.append(fill)
                        break
            
            if len(round_fills) >= 3:
                # Found pattern of round numbers
                amounts = [f['dollar_amount'] for f in round_fills]
                avg_amount = np.mean(amounts)
                
                confidence = min(len(round_fills) / len(side_fills), 0.8)
                
                return {
                    'pattern_detected': True,
                    'detected': True,
                    'pattern_type': 'ROUND_NUMBERS',
                    'confidence': confidence,
                    'details': (f"{len(round_fills)} {side_name} fills using round "
                              f"$ amounts (~${avg_amount:,.0f}) "
                              f"(institutional bot pattern)"),
                    'round_count': len(round_fills),
                    'avg_amount': avg_amount,
                    'side': side_name
                }
        
        return {'detected': False}
    
    def _find_similar_clusters(self, amounts, fills):
        """
        Find clusters of similar amounts.
        
        Returns list of clusters, each with fills that are similar to each other.
        """
        if len(amounts) < 3:
            return []
        
        clusters = []
        used_indices = set()
        
        for i, amount in enumerate(amounts):
            if i in used_indices:
                continue
            
            # Find all amounts within similarity threshold
            similar_indices = []
            for j, other_amount in enumerate(amounts):
                if j in used_indices:
                    continue
                
                if abs(other_amount - amount) / amount <= self.similarity_threshold:
                    similar_indices.append(j)
            
            if len(similar_indices) >= 3:
                # Found a cluster
                cluster_fills = [fills[j] for j in similar_indices]
                cluster_amounts = [amounts[j] for j in similar_indices]
                
                clusters.append({
                    'fills': cluster_fills,
                    'avg_amount': np.mean(cluster_amounts),
                    'std_dev': np.std(cluster_amounts),
                    'count': len(similar_indices)
                })
                
                used_indices.update(similar_indices)
        
        # Sort by cluster size (largest first)
        clusters.sort(key=lambda x: x['count'], reverse=True)
        
        return clusters


if __name__ == "__main__":
    """Test the detector"""
    
    logging.basicConfig(level=logging.INFO)
    
    detector = InstitutionalBotDetector(similarity_threshold=0.1, time_window=60)
    
    print("=" * 80)
    print("INSTITUTIONAL BOT PATTERN DETECTOR TEST")
    print("=" * 80)
    
    # Simulate fills
    base_time = datetime.now()
    
    # Pattern 1: Clustered fills (bot splitting large order)
    print("\n1. Testing CLUSTERED pattern (5 fills of ~$50k each):")
    for i in range(5):
        detector.add_fill(
            side='BID',
            size=0.57 + i * 0.01,  # Slightly varying sizes
            price=87500,
            timestamp=base_time + timedelta(seconds=i * 5)
        )
    
    result = detector.detect_bot_pattern(base_time + timedelta(seconds=30))
    if result['pattern_detected']:
        print(f"   ✓ {result['pattern_type']}: {result['details']}")
        print(f"   Confidence: {result['confidence']:.1%}")
    
    # Pattern 2: Repeated exact amounts
    print("\n2. Testing REPEATED pattern (4 fills of exact $100k):")
    detector = InstitutionalBotDetector()
    for i in range(4):
        detector.add_fill(
            side='ASK',
            size=1.14,  # Exact same size
            price=87500,
            timestamp=base_time + timedelta(seconds=i * 10)
        )
    
    result = detector.detect_bot_pattern(base_time + timedelta(seconds=40))
    if result['pattern_detected']:
        print(f"   ✓ {result['pattern_type']}: {result['details']}")
        print(f"   Confidence: {result['confidence']:.1%}")
    
    # Pattern 3: Round numbers
    print("\n3. Testing ROUND_NUMBERS pattern (fills near $50k, $100k):")
    detector = InstitutionalBotDetector()
    detector.add_fill('BID', 0.57, 87500, base_time)  # ~$50k
    detector.add_fill('BID', 0.58, 87500, base_time + timedelta(seconds=10))  # ~$50k
    detector.add_fill('BID', 1.14, 87500, base_time + timedelta(seconds=20))  # ~$100k
    
    result = detector.detect_bot_pattern(base_time + timedelta(seconds=30))
    if result['pattern_detected']:
        print(f"   ✓ {result['pattern_type']}: {result['details']}")
        print(f"   Confidence: {result['confidence']:.1%}")
    
    print("\n" + "=" * 80)
