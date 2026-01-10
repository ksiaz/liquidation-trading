"""
Liquidity Drain Detector - Data-Driven Signal Generator
Based on empirical analysis showing volume depletion predicts reversals.

Configurable threshold profiles for testing different quality/quantity tradeoffs.
"""

from collections import deque
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

class LiquidityDrainDetector:
    """
    Detects reversals based on liquidity depletion patterns.
    
    Primary signal: Volume draining from orderbook
    Direction: Tick divergence (fake pump vs capitulation)
    Confirmation: Price context (mean reversion)
    """
    
    # Threshold profiles (from relaxed to extreme)
    PROFILES = {
        'RELAXED': {
            'depth_threshold': 0.96,      # 4% below avg
            'slope_threshold': -200,      # Moderate decline
            'fake_pump_ticks': 3.0,       # Moderate pattern
            'capitulation_ticks': 2.0,
            'min_confidence': 60,
            'cooldown': 30,
        },
        'MODERATE': {
            'depth_threshold': 0.94,      # 6% below avg
            'slope_threshold': -250,      # Steeper decline
            'fake_pump_ticks': 3.5,       # Stronger pattern
            'capitulation_ticks': 2.5,
            'min_confidence': 70,
            'cooldown': 60,
        },
        'STRICT': {
            'depth_threshold': 0.92,      # 8% below avg
            'slope_threshold': -300,      # Steep decline
            'fake_pump_ticks': 4.0,       # Strong pattern
            'capitulation_ticks': 3.5,
            'min_confidence': 80,
            'cooldown': 120,
        },
        'EXTREME': {
            'depth_threshold': 0.90,      # 10% below avg
            'slope_threshold': -400,      # Very steep
            'fake_pump_ticks': 5.0,       # Very strong
            'capitulation_ticks': 4.0,
            'min_confidence': 90,
            'cooldown': 180,
        }
    }
    
    # Per-symbol optimized configurations (data-driven)
    SYMBOL_CONFIGS = {
        'ETHUSDT': {
            'depth_threshold': 0.96,
            'slope_pct': -0.02,        # -2% over 30s
            'slope_threshold': -200,   # Legacy field for logging
            'fake_pump_ticks': 3.0,
            'capitulation_ticks': 2.0,
            'min_confidence': 60,
            'cooldown': 30,
        },
        'BTCUSDT': {
            'depth_threshold': 0.96,
            'slope_pct': -0.02,        # -2% over 30s
            'slope_threshold': -200,   # Legacy field for logging
            'fake_pump_ticks': 3.0,
            'capitulation_ticks': 2.0,
            'min_confidence': 60,
            'cooldown': 30,
        },
        'SOLUSDT': {
            'depth_threshold': 0.92,   # Stricter for SOL
            'slope_pct': -0.05,        # -5% over 30s (stricter)
            'slope_threshold': -500,   # Legacy field for logging
            'fake_pump_ticks': 3.0,
            'capitulation_ticks': 2.0,
            'min_confidence': 80,      # Higher confidence
            'cooldown': 120,           # Longer cooldown
        }
    }
    
    def __init__(self, profile='MODERATE', symbol=None):
        """
        Args:
            profile: One of 'RELAXED', 'MODERATE', 'STRICT', 'EXTREME' (used if symbol not specified)
            symbol: If provided, uses optimized SYMBOL_CONFIGS for this symbol
        """
        if symbol and symbol in self.SYMBOL_CONFIGS:
            self.profile_name = f"{symbol}_OPTIMIZED"
            self.config = self.SYMBOL_CONFIGS[symbol].copy()
            logger.info(f"Initialized LiquidityDrainDetector with OPTIMIZED config for {symbol}")
        else:
            self.profile_name = profile
            self.config = self.PROFILES[profile]
            logger.info(f"Initialized LiquidityDrainDetector with profile: {profile}")
        
        # History buffers
        self.depth_history = deque(maxlen=300)  # 5 min
        self.tick_history = deque(maxlen=30)    # 30s
        self.price_history = deque(maxlen=60)   # 1 min
        
        # State tracking
        self.last_signal_time = 0
        self.last_price = None
        
        logger.info(f"Initialized LiquidityDrainDetector with profile: {profile}")
        logger.info(f"  Depth threshold: {self.config['depth_threshold']:.2%}")
        logger.info(f"  Slope: {self.config.get('slope_pct', self.config['slope_threshold'])}")
        logger.info(f"  Min confidence: {self.config['min_confidence']}%")
    
    def update(self, orderbook_data):
        """
        Process orderbook snapshot and check for signals.
        
        Args:
            orderbook_data: Dict with best_bid, best_ask, bid_volume_10, ask_volume_10, timestamp
        
        Returns:
            Signal dict or None
        """
        # Extract data
        best_bid = float(orderbook_data['best_bid'])
        best_ask = float(orderbook_data['best_ask'])
        bid_vol = float(orderbook_data['bid_volume_10'])
        ask_vol = float(orderbook_data['ask_volume_10'])
        timestamp = orderbook_data['timestamp']
        
        mid_price = (best_bid + best_ask) / 2
        total_depth = bid_vol + ask_vol
        
        # Calculate tick direction
        if self.last_price is not None:
            if mid_price > self.last_price:
                tick = 1
            elif mid_price < self.last_price:
                tick = -1
            else:
                tick = 0
        else:
            tick = 0
        
        self.last_price = mid_price
        
        # Update histories
        self.depth_history.append(total_depth)
        self.tick_history.append(tick)
        self.price_history.append(mid_price)
        
        # Check cooldown
        current_time = timestamp.timestamp() if hasattr(timestamp, 'timestamp') else timestamp
        if current_time - self.last_signal_time < self.config['cooldown']:
            return None
        
        # === STEP 1: Check PRIMARY signal (volume depletion) ===
        drain_info = self._check_liquidity_drain()
        if not drain_info:
            return None
        
        # === STEP 2: Determine DIRECTION (tick pattern) ===
        direction_info = self._analyze_tick_pattern()
        if not direction_info:
            return None
        
        # === STEP 3: CONFIRM with price context ===
        if not self._price_context_confirms(direction_info['direction']):
            return None
        
        # === STEP 4: Calculate confidence ===
        confidence = self._calculate_confidence(drain_info, direction_info)
        
        if confidence < self.config['min_confidence']:
            return None
        
        # Signal generated!
        self.last_signal_time = current_time
        
        signal = {
            'type': 'LIQUIDITY_DRAIN',
            'direction': direction_info['direction'],
            'confidence': confidence,
            'entry_price': mid_price,
            'timestamp': timestamp,
            'metadata': {
                'depth_ratio': drain_info['depth_ratio'],
                'slope': drain_info['slope'],
                'tick_pattern': direction_info['pattern'],
                'up_ticks': direction_info['up_ticks'],
                'down_ticks': direction_info['down_ticks'],
                'profile': self.profile_name
            }
        }
        
        logger.info(f"🎯 SIGNAL: {direction_info['direction']} @ ${mid_price:.2f} "
                   f"(conf={confidence}%, depth={drain_info['depth_ratio']:.1%}, "
                   f"slope={drain_info['slope']:.0f})")
        
        return signal
    
    def _check_liquidity_drain(self):
        """Check if liquidity is draining from the orderbook."""
        if len(self.depth_history) < 60:
            return None
        
        depths = list(self.depth_history)
        current_depth = depths[-1]
        
        # Calculate 60s moving average
        avg_depth_60 = np.mean(depths[-60:])
        depth_ratio = current_depth / avg_depth_60
        
        # Calculate PERCENTAGE slope (symbol-agnostic!)
        if len(depths) >= 30:
            recent_depths = depths[-30:]
            # Slope as % change per second
            pct_change = (recent_depths[-1] - recent_depths[0]) / recent_depths[0]
            slope_pct_per_sec = pct_change / 30
        else:
            slope_pct_per_sec = 0
        
        # NORMALIZED thresholds (work across ALL symbols)
        # Use symbol-specific slope_pct if available, otherwise default -2%
        slope_threshold_pct_total = self.config.get('slope_pct', -0.02)
        
        is_draining = (
            depth_ratio < self.config['depth_threshold'] and
            pct_change < slope_threshold_pct_total  # Total % change over 30s
        )
        
        if is_draining:
            return {
                'depth_ratio': depth_ratio,
                'slope': slope_pct_per_sec * 100,  # Store as % for logging
                'avg_depth': avg_depth_60
            }
        
        return None
    
    def _analyze_tick_pattern(self):
        """Analyze tick direction pattern to determine likely reversal direction."""
        if len(self.tick_history) < 30:
            return None
        
        ticks = list(self.tick_history)
        up_ticks = sum([1 for t in ticks if t > 0])
        down_ticks = sum([1 for t in ticks if t < 0])
        
        # BEARISH: Fake pump pattern (many up ticks before drain)
        if up_ticks >= self.config['fake_pump_ticks'] and down_ticks >= 2.0:
            return {
                'direction': 'SHORT',
                'pattern': 'FAKE_PUMP',
                'up_ticks': up_ticks,
                'down_ticks': down_ticks
            }
        
        # BULLISH: Capitulation pattern (heavy selling before drain)
        if down_ticks >= self.config['capitulation_ticks'] and up_ticks <= 2.5:
            return {
                'direction': 'LONG',
                'pattern': 'CAPITULATION',
                'up_ticks': up_ticks,
                'down_ticks': down_ticks
            }
        
        return None
    
    def _price_context_confirms(self, direction):
        """Check if price context supports the direction (mean reversion)."""
        if len(self.price_history) < 30:
            return True  # Not enough data, allow signal
        
        prices = list(self.price_history)
        current_price = prices[-1]
        avg_price = np.mean(prices)
        
        price_deviation = (current_price - avg_price) / avg_price
        
        # LONG signals better at low prices (mean revert up)
        if direction == 'LONG':
            return price_deviation < 0.002  # Allow if at/below average
        
        # SHORT signals better at high prices (mean revert down)
        if direction == 'SHORT':
            return price_deviation > -0.002  # Allow if at/above average
        
        return True
    
    def _calculate_confidence(self, drain_info, direction_info):
        """Calculate signal confidence (0-100)."""
        confidence = 50  # Base
        
        # Stronger drain = higher confidence
        depth_deviation = 1 - drain_info['depth_ratio']
        confidence += min(depth_deviation * 200, 30)  # +0-30
        
        # Steeper slope = higher confidence
        slope_strength = abs(drain_info['slope']) / 500
        confidence += min(slope_strength * 100, 20)  # +0-20
        
        # Clearer pattern = higher confidence
        if direction_info['pattern'] == 'FAKE_PUMP':
            pattern_strength = direction_info['up_ticks'] / 8.0  # 8 ticks = very strong
        else:  # CAPITULATION
            pattern_strength = direction_info['down_ticks'] / 8.0
        
        confidence += min(pattern_strength * 100, 30)  # +0-30
        
        return min(int(confidence), 100)

if __name__ == "__main__":
    # Test initialization
    logging.basicConfig(level=logging.INFO)
    
    print("Available profiles:")
    for profile, config in LiquidityDrainDetector.PROFILES.items():
        print(f"\n{profile}:")
        for key, value in config.items():
            print(f"  {key}: {value}")
    
    print("\n" + "="*50)
    detector = LiquidityDrainDetector(profile='MODERATE')
    print("Detector initialized successfully!")
