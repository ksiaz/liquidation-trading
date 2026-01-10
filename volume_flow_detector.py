"""
Volume Flow Reversal Detector

Tracks cumulative buy/sell volume to detect:
1. Sell-off exhaustion (when buying exceeds recent selling)
2. Rally exhaustion (when selling exceeds recent buying)
3. Sharp reversal points

This is a powerful signal because it detects when market has absorbed
all pressure in one direction and is ready to reverse.
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class VolumeFlowTracker:
    """
    Track cumulative volume flow to detect reversals.
    
    Key Concept:
    - During selloff: Track total sell volume
    - When buy volume exceeds that sell volume → Reversal signal
    - Vice versa for rallies
    """
    
    def __init__(self, symbol: str, window_minutes: int = 5):
        self.symbol = symbol
        self.window_seconds = window_minutes * 60
        
        # Store all trades with timestamps
        self.trades = deque(maxlen=10000)  # Last 10k trades
        
        # Volume tracking
        self.cumulative_buy_volume = 0
        self.cumulative_sell_volume = 0
        
        # Reversal detection
        self.last_reversal = None
        self.reversal_history = deque(maxlen=100)
        
        # Volume significance thresholds (prevent choppy market noise)
        self.min_total_volume = self._get_min_volume_threshold(symbol)
        self.min_volume_delta = self._get_min_delta_threshold(symbol)
    
    def _get_min_volume_threshold(self, symbol: str) -> float:
        """
        Get minimum total volume threshold for significance.
        
        This prevents triggering on tiny volume in quiet markets.
        """
        # Minimum volume in base currency (HIGH QUALITY - conservative)
        thresholds = {
            'BTCUSDT': 8.0,    # 8 BTC (higher for quality)
            'ETHUSDT': 80.0,   # 80 ETH
            'SOLUSDT': 1500.0  # 1500 SOL
        }
        return thresholds.get(symbol, 10.0)
    
    def _get_min_delta_threshold(self, symbol: str) -> float:
        """
        Get minimum volume delta for reversal significance.
        
        This ensures the volume shift is large enough to matter.
        """
        # Minimum delta in base currency (HIGH QUALITY - conservative)
        thresholds = {
            'BTCUSDT': 3.0,    # 3 BTC (higher for quality)
            'ETHUSDT': 30.0,   # 30 ETH
            'SOLUSDT': 600.0   # 600 SOL
        }
        return thresholds.get(symbol, 5.0)
        
    def on_trade(self, trade: Dict):
        """
        Process incoming trade.
        
        Args:
            trade: {
                'price': float,
                'quantity': float,
                'side': 'BUY' or 'SELL',  # Exchange label (taker side)
                'true_side': 'BUY' or 'SELL',  # Tick rule classification (true aggressor)
                'timestamp': float
            }
        """
        # Add to history
        self.trades.append(trade)
        
        # Use tick rule classification if available, otherwise fall back to exchange label
        side = trade.get('true_side', trade['side'])
        
        # Update cumulative volumes
        if side == 'BUY':
            self.cumulative_buy_volume += trade['quantity']
        else:
            self.cumulative_sell_volume += trade['quantity']
        
        # Clean old trades outside window
        self._clean_old_trades()
        
        # Check for reversal
        self._check_reversal()
    
    def _clean_old_trades(self):
        """Remove trades outside the time window."""
        cutoff_time = time.time() - self.window_seconds
        
        while self.trades and self.trades[0]['timestamp'] < cutoff_time:
            old_trade = self.trades.popleft()
            
            # Subtract from cumulative volumes
            if old_trade['side'] == 'BUY':
                self.cumulative_buy_volume -= old_trade['quantity']
            else:
                self.cumulative_sell_volume -= old_trade['quantity']
    
    def _check_reversal(self):
        """
        Detect reversal conditions with volume significance filtering.
        
        Reversal occurs when:
        1. Price was falling (sell volume dominated)
        2. Buy volume now exceeds recent sell volume
        3. **TOTAL VOLUME IS SIGNIFICANT** (not choppy noise)
        4. **VOLUME DELTA IS MEANINGFUL** (real shift, not tiny flip)
        
        Or vice versa for uptrend reversals.
        """
        # Calculate volume delta
        volume_delta = self.cumulative_buy_volume - self.cumulative_sell_volume
        total_volume = self.cumulative_buy_volume + self.cumulative_sell_volume
        
        # FILTER 1: Check if total volume is significant
        if total_volume < self.min_total_volume:
            return  # Too quiet, ignore
        
        # FILTER 2: Check if volume delta is meaningful
        if abs(volume_delta) < self.min_volume_delta:
            return  # Delta too small, choppy market
        
        # Get recent price trend
        if len(self.trades) < 10:
            return
        
        recent_trades = list(self.trades)[-100:]
        price_change = recent_trades[-1]['price'] - recent_trades[0]['price']
        price_change_pct = (price_change / recent_trades[0]['price']) * 100
        
        # FILTER 3: Price must have moved meaningfully
        # (prevents triggering in tight ranges)
        if abs(price_change_pct) < 0.3:  # Less than 0.3% move
            return  # Price barely moved, not a real trend to reverse
        
        # BULLISH REVERSAL: Price falling but buy volume now dominates
        if price_change_pct < -0.5 and volume_delta > 0:
            # Buy volume exceeded sell volume during selloff
            reversal_strength = volume_delta / (self.cumulative_sell_volume + 0.0001)
            
            # FILTER 4: Reversal strength must be significant (HIGH QUALITY)
            if reversal_strength > 0.30:  # Buy volume 30% more than sell (strict)
                self._record_reversal('BULLISH', reversal_strength, price_change_pct, total_volume)
        
        # BEARISH REVERSAL: Price rising but sell volume now dominates
        elif price_change_pct > 0.5 and volume_delta < 0:
            # Sell volume exceeded buy volume during rally
            reversal_strength = abs(volume_delta) / (self.cumulative_buy_volume + 0.0001)
            
            # FILTER 4: Reversal strength must be significant (HIGH QUALITY)
            if reversal_strength > 0.30:  # Sell volume 30% more than buy (strict)
                self._record_reversal('BEARISH', reversal_strength, price_change_pct, total_volume)
    
    def _record_reversal(self, direction: str, strength: float, price_change_pct: float, total_volume: float):
        """Record a detected reversal."""
        # Avoid duplicate signals (cooldown period)
        if self.last_reversal and time.time() - self.last_reversal['timestamp'] < 60:
            return
        
        reversal = {
            'timestamp': time.time(),
            'direction': direction,
            'strength': strength,
            'price_change_pct': price_change_pct,
            'buy_volume': self.cumulative_buy_volume,
            'sell_volume': self.cumulative_sell_volume,
            'volume_delta': self.cumulative_buy_volume - self.cumulative_sell_volume,
            'total_volume': total_volume  # Added for significance tracking
        }
        
        self.last_reversal = reversal
        self.reversal_history.append(reversal)
        
        logger.info(f"🔄 {self.symbol} REVERSAL DETECTED: {direction} "
                   f"(Strength: {strength:.2%}, Price Δ: {price_change_pct:+.2f}%, "
                   f"Volume: {total_volume:.2f})")
    
    def get_current_state(self) -> Dict:
        """Get current volume flow state."""
        volume_delta = self.cumulative_buy_volume - self.cumulative_sell_volume
        total_volume = self.cumulative_buy_volume + self.cumulative_sell_volume
        
        # Calculate dominance
        if total_volume > 0:
            buy_dominance = self.cumulative_buy_volume / total_volume
            sell_dominance = self.cumulative_sell_volume / total_volume
        else:
            buy_dominance = 0.5
            sell_dominance = 0.5
        
        # Determine flow state
        if buy_dominance > 0.6:
            flow_state = 'STRONG_BUYING'
        elif buy_dominance > 0.55:
            flow_state = 'BUYING'
        elif sell_dominance > 0.6:
            flow_state = 'STRONG_SELLING'
        elif sell_dominance > 0.55:
            flow_state = 'SELLING'
        else:
            flow_state = 'BALANCED'
        
        return {
            'symbol': self.symbol,
            'buy_volume': self.cumulative_buy_volume,
            'sell_volume': self.cumulative_sell_volume,
            'volume_delta': volume_delta,
            'buy_dominance': buy_dominance,
            'sell_dominance': sell_dominance,
            'flow_state': flow_state,
            'last_reversal': self.last_reversal,
            'window_seconds': self.window_seconds
        }


class MultiWindowVolumeAnalyzer:
    """
    Analyze volume flow across multiple time windows.
    
    This gives you flexibility to detect:
    - Quick reversals (1-minute window)
    - Medium-term shifts (5-minute window)
    - Longer exhaustion (15-minute window)
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        
        # Multiple time windows
        self.trackers = {
            '1m': VolumeFlowTracker(symbol, window_minutes=1),
            '5m': VolumeFlowTracker(symbol, window_minutes=5),
            '15m': VolumeFlowTracker(symbol, window_minutes=15)
        }
    
    def on_trade(self, trade: Dict):
        """Feed trade to all trackers."""
        for tracker in self.trackers.values():
            tracker.on_trade(trade)
    
    def get_reversal_signal(self) -> Optional[Dict]:
        """
        Get reversal signal if multiple windows agree.
        
        Strongest signal: All windows show same reversal direction
        """
        reversals = {}
        
        for window, tracker in self.trackers.items():
            if tracker.last_reversal:
                # Only consider recent reversals (< 2 minutes old)
                age = time.time() - tracker.last_reversal['timestamp']
                if age < 120:
                    reversals[window] = tracker.last_reversal
        
        if not reversals:
            return None
        
        # Check if multiple windows agree
        directions = [r['direction'] for r in reversals.values()]
        
        if len(set(directions)) == 1:  # All agree on direction
            # Calculate combined strength
            avg_strength = sum(r['strength'] for r in reversals.values()) / len(reversals)
            
            return {
                'direction': directions[0],
                'strength': avg_strength,
                'confirming_windows': list(reversals.keys()),
                'confidence': len(reversals) / 3  # 0.33, 0.66, or 1.0
            }
        
        return None
    
    def get_all_states(self) -> Dict:
        """Get states for all windows."""
        return {
            window: tracker.get_current_state()
            for window, tracker in self.trackers.items()
        }


if __name__ == "__main__":
    """Test volume flow tracker."""
    
    logging.basicConfig(level=logging.INFO)
    
    analyzer = MultiWindowVolumeAnalyzer('BTCUSDT')
    
    # Simulate selloff then reversal
    print("Simulating selloff...")
    for i in range(100):
        # Heavy selling
        analyzer.on_trade({
            'price': 100000 - i * 10,  # Price falling
            'quantity': 0.5,
            'side': 'SELL',
            'timestamp': time.time()
        })
        time.sleep(0.01)
    
    print("\nSimulating reversal (buying kicks in)...")
    for i in range(150):
        # Heavy buying
        analyzer.on_trade({
            'price': 99000 + i * 5,  # Price rising
            'quantity': 0.6,
            'side': 'BUY',
            'timestamp': time.time()
        })
        time.sleep(0.01)
    
    # Check for reversal signal
    signal = analyzer.get_reversal_signal()
    if signal:
        print(f"\n🎯 REVERSAL SIGNAL DETECTED!")
        print(f"Direction: {signal['direction']}")
        print(f"Strength: {signal['strength']:.2%}")
        print(f"Confidence: {signal['confidence']:.2%}")
        print(f"Confirming windows: {signal['confirming_windows']}")
    
    # Show all states
    print("\n" + "="*60)
    print("VOLUME FLOW STATES")
    print("="*60)
    states = analyzer.get_all_states()
    for window, state in states.items():
        print(f"\n{window} Window:")
        print(f"  Flow State: {state['flow_state']}")
        print(f"  Buy Volume: {state['buy_volume']:.2f}")
        print(f"  Sell Volume: {state['sell_volume']:.2f}")
        print(f"  Buy Dominance: {state['buy_dominance']:.1%}")
