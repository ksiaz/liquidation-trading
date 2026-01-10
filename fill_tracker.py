"""
Real-time Fill Tracker - Monitors what gets filled and at what rate
to predict balance flips and measure conviction.

Key Metrics:
1. Fill Rate: How fast orders are being filled
2. Fill Size: Total volume filled (larger = higher conviction)
3. Fill Side: Which side is absorbing (bid/ask)
4. Fill Acceleration: Is fill rate increasing?
"""

from collections import deque
from datetime import datetime, timedelta
import numpy as np
import logging

logger = logging.getLogger(__name__)


class FillTracker:
    """
    Tracks filled orders in real-time to predict balance flips.
    
    Conviction Score based on:
    - Fill size (larger = higher conviction)
    - Fill rate (faster = higher conviction)
    - Fill persistence (sustained = higher conviction)
    """
    
    def __init__(self, lookback_seconds=60):
        self.lookback_seconds = lookback_seconds
        self.last_update_time = None  # Track current orderbook time
        
        # Track fills by side
        self.bid_fills = deque(maxlen=100)  # Recent bid fills
        self.ask_fills = deque(maxlen=100)  # Recent ask fills
        
        # Track volume spikes for spoof detection
        self.bid_spikes = deque(maxlen=50)
        self.ask_spikes = deque(maxlen=50)
        
        # Previous volume for change detection
        self.prev_bid_vol = 0
        self.prev_ask_vol = 0
        
        # Statistics for spike detection
        self.bid_vol_changes = deque(maxlen=300)
        self.ask_vol_changes = deque(maxlen=300)
    
    def update(self, orderbook_data):
        """
        Update with new orderbook snapshot.
        
        Args:
            orderbook_data: Dict with bid_volume_10, ask_volume_10, timestamp
        """
        timestamp = orderbook_data.get('timestamp', datetime.now())
        self.last_update_time = timestamp  # Track current time for metrics
        
        bid_vol = orderbook_data.get('bid_volume_10', 0) + orderbook_data.get('bid_volume_20', 0)
        ask_vol = orderbook_data.get('ask_volume_10', 0) + orderbook_data.get('ask_volume_20', 0)
        
        # Calculate volume changes
        bid_change = bid_vol - self.prev_bid_vol
        ask_change = ask_vol - self.prev_ask_vol
        
        # Store changes for statistics
        self.bid_vol_changes.append(bid_change)
        self.ask_vol_changes.append(ask_change)
        
        # Detect spikes (>3 std deviations)
        bid_mean = 0
        bid_std = 0
        ask_mean = 0
        ask_std = 0
        
        if len(self.bid_vol_changes) > 30:
            bid_mean = np.mean(self.bid_vol_changes)
            bid_std = np.std(self.bid_vol_changes)
            
            if bid_change > bid_mean + 3 * bid_std:
                # Large bid spike detected
                self.bid_spikes.append({
                    'timestamp': timestamp,
                    'size': bid_change,
                    'total_vol': bid_vol,
                    'withdrawn': False
                })
        
        if len(self.ask_vol_changes) > 30:
            ask_mean = np.mean(self.ask_vol_changes)
            ask_std = np.std(self.ask_vol_changes)
            
            if ask_change > ask_mean + 3 * ask_std:
                # Large ask spike detected
                self.ask_spikes.append({
                    'timestamp': timestamp,
                    'size': ask_change,
                    'total_vol': ask_vol,
                    'withdrawn': False
                })
        
        # Check for withdrawals (spoofs)
        if len(self.bid_vol_changes) > 30 and bid_change < bid_mean - 3 * bid_std:
            # Large bid withdrawal - mark recent spikes as spoofed
            self._mark_spoofs(self.bid_spikes, timestamp, lookback=10)
        
        if len(self.ask_vol_changes) > 30 and ask_change < ask_mean - 3 * ask_std:
            self._mark_spoofs(self.ask_spikes, timestamp, lookback=10)
        
        # Detect fills (spikes that weren't withdrawn)
        self._detect_fills(timestamp)
        
        # Update previous volumes
        self.prev_bid_vol = bid_vol
        self.prev_ask_vol = ask_vol
    
    def _mark_spoofs(self, spikes, current_time, lookback=10):
        """Mark recent spikes as spoofed if withdrawn quickly"""
        for spike in spikes:
            if spike['withdrawn']:
                continue
            
            time_diff = (current_time - spike['timestamp']).total_seconds()
            if time_diff <= lookback:
                spike['withdrawn'] = True
    
    def _detect_fills(self, current_time):
        """Detect filled orders (spikes that stayed >10s)"""
        # Check bid spikes
        for spike in self.bid_spikes:
            if spike['withdrawn']:
                continue
            
            time_diff = (current_time - spike['timestamp']).total_seconds()
            if time_diff > 10 and spike not in [f['spike'] for f in self.bid_fills]:
                # This spike stayed >10s = filled order
                self.bid_fills.append({
                    'timestamp': spike['timestamp'],
                    'size': spike['size'],
                    'spike': spike
                })
                logger.info(f"BID FILL detected: {spike['size']:.2f} at {spike['timestamp']}")
        
        # Check ask spikes
        for spike in self.ask_spikes:
            if spike['withdrawn']:
                continue
            
            time_diff = (current_time - spike['timestamp']).total_seconds()
            if time_diff > 10 and spike not in [f['spike'] for f in self.ask_fills]:
                # This spike stayed >10s = filled order
                self.ask_fills.append({
                    'timestamp': spike['timestamp'],
                    'size': spike['size'],
                    'spike': spike
                })
                logger.info(f"ASK FILL detected: {spike['size']:.2f} at {spike['timestamp']}")
    
    def get_fill_metrics(self, lookback_seconds=None):
        """
        Calculate fill metrics for conviction scoring.
        
        Returns:
            dict with:
                - bid_fill_rate: Fills per minute on bid side
                - ask_fill_rate: Fills per minute on ask side
                - bid_fill_size: Total size filled on bid side
                - ask_fill_size: Total size filled on ask side
                - dominant_side: Which side has more fills
                - conviction_score: 0-1 score based on fill metrics
        """
        if lookback_seconds is None:
            lookback_seconds = self.lookback_seconds
        
        # Use last update time instead of current time (fixes backtest bug)
        if self.last_update_time is None:
            return {
                'bid_fill_count': 0,
                'ask_fill_count': 0,
                'bid_fill_rate': 0,
                'ask_fill_rate': 0,
                'bid_fill_size': 0,
                'ask_fill_size': 0,
                'dominant_side': 'NEUTRAL',
                'dominance': 0.5,
                'conviction_score': 0
            }
        
        cutoff = self.last_update_time - timedelta(seconds=lookback_seconds)
        
        # Filter fills within lookback window
        recent_bid_fills = [f for f in self.bid_fills if f['timestamp'] >= cutoff]
        recent_ask_fills = [f for f in self.ask_fills if f['timestamp'] >= cutoff]
        
        # Calculate metrics
        bid_fill_count = len(recent_bid_fills)
        ask_fill_count = len(recent_ask_fills)
        
        bid_fill_size = sum(f['size'] for f in recent_bid_fills)
        ask_fill_size = sum(f['size'] for f in recent_ask_fills)
        
        # Fill rate (per minute)
        bid_fill_rate = (bid_fill_count / lookback_seconds) * 60
        ask_fill_rate = (ask_fill_count / lookback_seconds) * 60
        
        # Determine dominant side
        if bid_fill_count > ask_fill_count:
            dominant_side = 'BID'
            dominance = bid_fill_count / (bid_fill_count + ask_fill_count + 1e-10)
        elif ask_fill_count > bid_fill_count:
            dominant_side = 'ASK'
            dominance = ask_fill_count / (bid_fill_count + ask_fill_count + 1e-10)
        else:
            dominant_side = 'NEUTRAL'
            dominance = 0.5
        
        # Conviction score (0-1)
        # Based on: fill count, fill size, dominance
        count_score = min((bid_fill_count + ask_fill_count) / 5, 1.0)  # Max at 5 fills
        size_score = min((bid_fill_size + ask_fill_size) / 100, 1.0)  # Max at 100 BTC
        dominance_score = abs(dominance - 0.5) * 2  # 0 = balanced, 1 = one-sided
        
        conviction_score = (count_score * 0.3 + size_score * 0.4 + dominance_score * 0.3)
        
        return {
            'bid_fill_count': bid_fill_count,
            'ask_fill_count': ask_fill_count,
            'bid_fill_rate': bid_fill_rate,
            'ask_fill_rate': ask_fill_rate,
            'bid_fill_size': bid_fill_size,
            'ask_fill_size': ask_fill_size,
            'dominant_side': dominant_side,
            'dominance': dominance,
            'conviction_score': conviction_score
        }
    
    def predict_balance_flip(self):
        """
        Predict if balance flip is imminent based on fill patterns.
        Uses multi-window approach for better signal detection.
        
        Returns:
            tuple: (prediction, confidence, reason)
                prediction: 'FLIP_TO_BID', 'FLIP_TO_ASK', or None
                confidence: 0-1
                reason: Explanation string
        """
        # Check multiple time windows with different thresholds
        # Recent fills need higher conviction, older fills need lower
        windows = [
            (10, 0.7, "IMMEDIATE"),   # 10s window, very high threshold
            (30, 0.5, "RECENT"),      # 30s window, medium threshold  
            (60, 0.3, "HISTORICAL"),  # 60s window, low threshold
        ]
        
        best_prediction = None
        best_confidence = 0
        best_reason = ""
        
        for lookback, threshold, window_name in windows:
            metrics = self.get_fill_metrics(lookback_seconds=lookback)
            
            # Check for dominant side with sufficient conviction
            if metrics['dominant_side'] == 'ASK' and metrics['conviction_score'] > threshold:
                # Large ASK fills = sellers getting filled = bottom soon
                reason = (f"[{window_name}] ASK fills: {metrics['ask_fill_count']} "
                         f"({metrics['ask_fill_size']:.1f} BTC) in {lookback}s. "
                         f"Sellers absorbing bids → Bottom imminent")
                
                # Check for acceleration in shorter window
                if lookback >= 30:
                    recent_metrics = self.get_fill_metrics(lookback_seconds=lookback//2)
                    if recent_metrics['ask_fill_rate'] > metrics['ask_fill_rate']:
                        confidence = min(metrics['conviction_score'] * 1.2, 1.0)
                        reason += " (ACCELERATING)"
                    else:
                        confidence = metrics['conviction_score']
                else:
                    confidence = metrics['conviction_score']
                
                # Keep best prediction (highest confidence)
                if confidence > best_confidence:
                    best_prediction = 'FLIP_TO_BID'
                    best_confidence = confidence
                    best_reason = reason
            
            elif metrics['dominant_side'] == 'BID' and metrics['conviction_score'] > threshold:
                # Large BID fills = buyers getting filled = top soon
                reason = (f"[{window_name}] BID fills: {metrics['bid_fill_count']} "
                         f"({metrics['bid_fill_size']:.1f} BTC) in {lookback}s. "
                         f"Buyers absorbing asks → Top imminent")
                
                if lookback >= 30:
                    recent_metrics = self.get_fill_metrics(lookback_seconds=lookback//2)
                    if recent_metrics['bid_fill_rate'] > metrics['bid_fill_rate']:
                        confidence = min(metrics['conviction_score'] * 1.2, 1.0)
                        reason += " (ACCELERATING)"
                    else:
                        confidence = metrics['conviction_score']
                else:
                    confidence = metrics['conviction_score']
                
                if confidence > best_confidence:
                    best_prediction = 'FLIP_TO_ASK'
                    best_confidence = confidence
                    best_reason = reason
        
        if best_prediction:
            return best_prediction, best_confidence, best_reason
        
        return None, 0, "No significant fill pattern"
    
    def get_stats(self):
        """Get tracker statistics"""
        metrics = self.get_fill_metrics()
        
        return {
            'total_bid_fills': len(self.bid_fills),
            'total_ask_fills': len(self.ask_fills),
            'recent_bid_fills': metrics['bid_fill_count'],
            'recent_ask_fills': metrics['ask_fill_count'],
            'conviction_score': metrics['conviction_score'],
            'dominant_side': metrics['dominant_side']
        }


if __name__ == "__main__":
    """Test the fill tracker"""
    
    logging.basicConfig(level=logging.INFO)
    
    tracker = FillTracker(lookback_seconds=60)
    
    print("=" * 80)
    print("FILL TRACKER TEST")
    print("=" * 80)
    
    # Simulate orderbook updates
    import random
    
    base_bid_vol = 10.0
    base_ask_vol = 10.0
    
    for i in range(100):
        # Simulate volume changes
        bid_vol = base_bid_vol + random.gauss(0, 2)
        ask_vol = base_ask_vol + random.gauss(0, 2)
        
        # Occasionally add large spike
        if random.random() < 0.1:
            if random.random() < 0.5:
                bid_vol += 50  # Large bid spike
            else:
                ask_vol += 50  # Large ask spike
        
        orderbook_data = {
            'timestamp': datetime.now(),
            'bid_volume_10': bid_vol * 0.6,
            'bid_volume_20': bid_vol * 0.4,
            'ask_volume_10': ask_vol * 0.6,
            'ask_volume_20': ask_vol * 0.4
        }
        
        tracker.update(orderbook_data)
        
        # Check for predictions every 10 updates
        if i % 10 == 0:
            prediction, confidence, reason = tracker.predict_balance_flip()
            if prediction:
                print(f"\n🎯 PREDICTION: {prediction}")
                print(f"   Confidence: {confidence:.2%}")
                print(f"   Reason: {reason}")
    
    print("\n" + "=" * 80)
    print("FINAL STATS")
    print("=" * 80)
    stats = tracker.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
