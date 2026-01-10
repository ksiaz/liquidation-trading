"""
Pivot Detector - Real-time V-Bottom and Inverse-V Top Detection

Identifies price pivots (reversal points) by detecting:
1. Exhaustion zones (price momentum slowing)
2. Orderbook flips (imbalance reversal)
3. Volume spikes
4. Price confirmation
"""

import numpy as np
from collections import deque
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PivotDetector:
    """
    Detects price pivots in real-time using orderbook microstructure
    """
    
    def __init__(self, symbol):
        self.symbol = symbol
        
        # Price history (last 5 minutes of 1-second snapshots)
        self.price_history = deque(maxlen=300)
        self.timestamp_history = deque(maxlen=300)
        
        # Orderbook history (last 60 seconds)
        self.imbalance_history = deque(maxlen=60)
        self.volume_history = deque(maxlen=60)
        
        # Pivot state
        self.in_pivot_zone = False
        self.pivot_type = None  # 'LOW' or 'HIGH'
        self.pivot_price = None
        self.pivot_time = None
        self.zone_start_time = None
        
        # Configuration (Calibrated)
        self.exhaustion_lookback = 100  # seconds
        self.momentum_threshold = 0.10  # 10% momentum slowdown
        self.imbalance_flip_threshold = 0.30  # Flip magnitude (0.15 to -0.15 = 0.30)
        self.trend_threshold_pct = 0.15  # 0.15% price trend required
        self.volume_spike_multiplier = 1.1  # Relaxed from 1.5
        
        # Statistics
        self.pivots_detected = 0
        self.false_signals = 0
        
    def update(self, orderbook_data):
        """
        Update with new orderbook snapshot and check for pivots
        
        Args:
            orderbook_data: dict with keys: timestamp, best_bid, best_ask, imbalance, bid_volume, ask_volume
            
        Returns:
            dict or None: Pivot signal if detected
        """
        # Extract data
        timestamp = orderbook_data['timestamp']
        mid_price = (orderbook_data['best_bid'] + orderbook_data['best_ask']) / 2
        imbalance = orderbook_data['imbalance']
        total_volume = orderbook_data.get('bid_volume_10', 0) + orderbook_data.get('ask_volume_10', 0)
        
        # Update history
        self.price_history.append(mid_price)
        self.timestamp_history.append(timestamp)
        self.imbalance_history.append(imbalance)
        self.volume_history.append(total_volume)
        
        # Need enough data
        if len(self.price_history) < self.exhaustion_lookback:
            return None
        
        # STAGE 1: Check if entering exhaustion zone
        if not self.in_pivot_zone:
            exhaustion_signal = self._detect_exhaustion_zone()
            if exhaustion_signal:
                self.in_pivot_zone = True
                self.pivot_type = exhaustion_signal['type']
                self.zone_start_time = timestamp
                
                logger.info(f"[{self.symbol}] 🟡 EXHAUSTION ZONE: {self.pivot_type}")
                logger.info(f"   Price: ${mid_price:.2f} | Trend: {exhaustion_signal['trend']}")
                logger.info(f"   Momentum: {exhaustion_signal['momentum']:.4f}% | Imbalance: {exhaustion_signal['imbalance']:+.2f}")
        
        # STAGE 2: If in zone, check for orderbook flip (the pivot)
        if self.in_pivot_zone:
            flip_signal = self._detect_orderbook_flip()
            
            if flip_signal:
                # STAGE 3: Confirm with price action
                confirmation = self._confirm_pivot_formation(mid_price)
                
                if confirmation:
                    # PIVOT DETECTED!
                    self.pivots_detected += 1
                    self.pivot_price = mid_price
                    self.pivot_time = timestamp
                    
                    signal = {
                        'type': 'PIVOT',
                        'pivot_type': self.pivot_type,
                        'direction': 'LONG' if self.pivot_type == 'LOW' else 'SHORT',
                        'price': mid_price,
                        'timestamp': timestamp,
                        'confidence': flip_signal['confidence'],
                        'details': {
                            'imbalance': imbalance,
                            'imbalance_flip': flip_signal['flip_magnitude'],
                            'volume_spike': flip_signal['volume_ratio'],
                            'zone_duration': (timestamp - self.zone_start_time).total_seconds() if self.zone_start_time else 0
                        }
                    }
                    
                    logger.info(f"[{self.symbol}] 🎯 PIVOT DETECTED: {self.pivot_type}")
                    logger.info(f"   Direction: {signal['direction']}")
                    logger.info(f"   Price: ${mid_price:.2f}")
                    logger.info(f"   Confidence: {signal['confidence']:.2f}")
                    logger.info(f"   Imbalance flip: {flip_signal['flip_magnitude']:.2f}")
                    logger.info(f"   Volume spike: {flip_signal['volume_ratio']:.2f}x")
                    
                    # Reset state
                    self.in_pivot_zone = False
                    self.pivot_type = None
                    
                    return signal
            
            # Timeout if in zone too long (60 seconds)
            if self.zone_start_time and (timestamp - self.zone_start_time).total_seconds() > 60:
                logger.debug(f"[{self.symbol}] Exhaustion zone timeout, no pivot")
                self.in_pivot_zone = False
                self.pivot_type = None
                self.false_signals += 1
        
        return None
    
    def _detect_exhaustion_zone(self):
        """
        Stage 1: Detect if price is in exhaustion zone
        
        Returns dict with exhaustion details or None
        """
        prices = np.array(self.price_history)
        
        # Check trend direction
        recent_prices = prices[-self.exhaustion_lookback:]
        trend_start = recent_prices[0]
        trend_end = recent_prices[-1]
        price_change_pct = ((trend_end - trend_start) / trend_start) * 100
        
        # Calculate momentum (rate of price change)
        # Compare last 20s to previous 20s
        if len(prices) < 40:
            return None
            
        recent_momentum = abs(prices[-20:].mean() - prices[-40:-20].mean()) / prices[-40:-20].mean()
        prev_momentum = abs(prices[-40:-20].mean() - prices[-60:-40].mean()) / prices[-60:-40].mean()
        
        momentum_slowing = recent_momentum < prev_momentum * (1 - self.momentum_threshold)
        
        # Check orderbook imbalance extreme
        recent_imbalance = np.mean(list(self.imbalance_history)[-20:])
        
        # DOWNTREND EXHAUSTION (potential pivot low)
        if price_change_pct < -self.trend_threshold_pct and momentum_slowing and recent_imbalance < -(self.imbalance_flip_threshold/2):
            return {
                'type': 'LOW',
                'trend': 'DOWN',
                'momentum': recent_momentum * 100,
                'imbalance': recent_imbalance,
                'price_change': price_change_pct
            }
        
        # UPTREND EXHAUSTION (potential pivot high)
        if price_change_pct > self.trend_threshold_pct and momentum_slowing and recent_imbalance > (self.imbalance_flip_threshold/2):
            return {
                'type': 'HIGH',
                'trend': 'UP',
                'momentum': recent_momentum * 100,
                'imbalance': recent_imbalance,
                'price_change': price_change_pct
            }
        
        return None
    
    def _detect_orderbook_flip(self):
        """
        Stage 2: Detect orderbook imbalance flip (the pivot moment)
        
        Returns dict with flip details or None
        """
        if len(self.imbalance_history) < 30:
            return None
        
        imb_list = list(self.imbalance_history)
        
        # Previous imbalance (30s ago to 10s ago)
        prev_imbalance = np.mean(imb_list[-30:-10])
        
        # Current imbalance (last 5s)
        curr_imbalance = np.mean(imb_list[-5:])
        
        # SIMPLIFIED: Just check for imbalance improvement (buyers stepping in)
        # Prev: mean of [-30:-10], Curr: mean of [-5:]
        
        # For PIVOT LOW: Imbalance should increase (become less negative or positive)
        if self.pivot_type == 'LOW':
            # E.g. -0.30 -> -0.15 (improvement of 0.15)
            improvement = curr_imbalance - prev_imbalance
            flipped = improvement > 0.10  # 10% improvement
            
        # For PIVOT HIGH: Imbalance should decrease (become less positive or negative)
        elif self.pivot_type == 'HIGH':
            # E.g. 0.30 -> 0.15 (decrease of 0.15)
            improvement = prev_imbalance - curr_imbalance
            flipped = improvement > 0.10  # 10% decrease
        else:
            flipped = False
            improvement = 0
        
        if not flipped:
            return None
            
        # Optional Volume Check (just log it, don't filter)
        if len(self.volume_history) >= 30:
            vol_list = list(self.volume_history)
            recent_vol = np.mean(vol_list[-5:])
            prev_vol = np.mean(vol_list[-30:-10])
            volume_ratio = recent_vol / prev_vol if prev_vol > 0 else 1.0
        else:
            volume_ratio = 1.0
        
        # Calculate confidence
        confidence = min(1.0, (improvement / 0.20))
        
        return {
            'flipped': True,
            'flip_magnitude': improvement,
            'volume_ratio': volume_ratio,
            'confidence': confidence
        }
    
    def _confirm_pivot_formation(self, current_price):
        """
        Stage 3: Confirm price is moving off the pivot
        
        Returns bool
        """
        if len(self.price_history) < 10:
            return False
        
        prices = list(self.price_history)
        
        # For PIVOT LOW: Price should be rising
        if self.pivot_type == 'LOW':
            price_rising = current_price > np.mean(prices[-10:])
            sustained = current_price > prices[-10] * 1.0001  # 0.01% above (just clear the pivot)
            return price_rising and sustained
        
        # For PIVOT HIGH: Price should be falling
        elif self.pivot_type == 'HIGH':
            price_falling = current_price < np.mean(prices[-10:])
            sustained = current_price < prices[-10] * 0.9999  # 0.01% below
            return price_falling and sustained
        
        return False
    
    def get_stats(self):
        """Get detector statistics"""
        return {
            'symbol': self.symbol,
            'pivots_detected': self.pivots_detected,
            'false_signals': self.false_signals,
            'in_zone': self.in_pivot_zone,
            'zone_type': self.pivot_type,
            'last_pivot_price': self.pivot_price,
            'last_pivot_time': self.pivot_time
        }
