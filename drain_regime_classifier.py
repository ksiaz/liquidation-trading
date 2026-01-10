"""
Week 3 Task 3.1: Active vs Passive Drain Classifier
====================================================

Distinguishes real selling pressure from spoofing by analyzing trade flow.

Expert Guidance (Expert #3 - Q4):
- PRIMARY: Measure active drain (taker_sell) concurrent with depth decline (30s window)
- SECONDARY: Sanity check for non-zero taker_sell in [0s, +1.5s] trailing window
- Threshold: active > 1.8× passive to confirm "real pressure"

Regime Classification:
1. REAL_PRESSURE: Active drain concurrent with depth decline (TRADE)
2. SPOOF_CLEANUP: Passive drain, minimal active (SKIP)
3. PANIC: High active, extremely high absorption (CONDITIONAL if conf > 85%)
4. NOISE: Low drain, balanced flow (SKIP)

Formula:
    absorption_efficiency = executed_volume / depth_decline
    
    If taker_sell > 1.8 × taker_buy (concurrent 30s):
        → REAL_PRESSURE (real selling)
    Else:
        → SPOOF_CLEANUP (fake orders cancelled)
"""

import numpy as np
from typing import Dict, List, Tuple
from collections import deque
import logging
import time

logger = logging.getLogger(__name__)


class DrainRegimeClassifier:
    """
    Classify liquidity drains into regimes based on active vs passive pressure.
    
    Distinguishes:
    - Real pressure (aggressive selling into bids)
    - Spoof cleanup (cancelled orders without trades)
    - Panic (extreme selling with high absorption)
    - Noise (normal market activity)
    """
    
    # LOCKED PARAMETERS (per expert Q4)
    DRAIN_WINDOW_SECONDS = 30       # Concurrent with depth decline
    SANITY_CHECK_WINDOW = 1.5       # Trailing check
    ACTIVE_THRESHOLD_RATIO = 1.8    # taker_sell > 1.8× taker_buy
    PANIC_ABSORPTION_THRESHOLD = 0.8  # 80% of depth absorbed
    
    def __init__(self, symbol: str):
        """
        Initialize regime classifier.
        
        Args:
            symbol: Trading symbol
        """
        self.symbol = symbol
        
        # Track trade flow history
        self.trade_history: deque = deque(maxlen=100)
        
        # Track orderbook depth history for cancellation inference
        self.depth_history: deque = deque(maxlen=60)  # Up to 60 seconds
        
        # Regime statistics
        self.regime_counts = {
            'REAL_PRESSURE': 0,
            'SPOOF_CLEANUP': 0,
            'PANIC': 0,
            'NOISE': 0
        }
        
    def update_trade(self, trade: Dict):
        """
        Update with executed trade.
        
        Args:
            trade: {
                'price': float,
                'quantity': float,
                'timestamp': float,
                'side': 'BUY' or 'SELL',
                'is_buyer_maker': bool  # True if buyer is maker (taker is seller)
            }
        """
        # Classify as taker buy or taker sell
        if trade.get('is_buyer_maker', False):
            # Buyer is maker → Seller is taker → Taker SELL
            taker_side = 'SELL'
        else:
            # Seller is maker → Buyer is taker → Taker BUY
            taker_side = 'BUY'
        
        self.trade_history.append({
            'timestamp': trade['timestamp'],
            'quantity': trade['quantity'],
            'taker_side': taker_side,
            'price': trade['price']
        })
    
    def update_depth(self, depth_snapshot: Dict, timestamp: float):
        """
        Update with orderbook depth snapshot.
        
        Args:
            depth_snapshot: {
                'bid_depth': float,  # Total bid depth
                'ask_depth': float,  # Total ask depth
            }
            timestamp: Current timestamp
        """
        self.depth_history.append({
            'timestamp': timestamp,
            'bid_depth': depth_snapshot.get('bid_depth', 0),
            'ask_depth': depth_snapshot.get('ask_depth', 0)
        })
    
    def classify_drain(self, 
                      drain_side: str,
                      drain_start_time: float,
                      drain_end_time: float,
                      confidence: float = 50.0) -> Dict:
        """
        Classify a detected liquidity drain into regime.
        
        Args:
            drain_side: 'bid' or 'ask'
            drain_start_time: When drain started (t - 30s)
            drain_end_time: When drain detected (t = 0)
            confidence: Signal confidence (for panic classification)
            
        Returns:
            {
                'regime': str,
                'active_drain': float,
                'passive_drain': float,
                'absorption_efficiency': float,
                'taker_sell_volume': float,
                'taker_buy_volume': float,
                'sanity_check_passed': bool
            }
        """
        # PRIMARY: Calculate active drain (concurrent 30s window)
        active_result = self._calculate_active_drain_concurrent(
            drain_side, drain_start_time, drain_end_time
        )
        
        # SECONDARY: Sanity check (trailing 1.5s)
        sanity_result = self._sanity_check_trailing(
            drain_side, drain_end_time
        )
        
        # Calculate passive drain (cancelled volume)
        passive_drain = self._calculate_passive_drain(
            drain_side, drain_start_time, drain_end_time
        )
        
        # Calculate absorption efficiency
        depth_decline = self._calculate_depth_decline(
            drain_side, drain_start_time, drain_end_time
        )
        
        absorption_eff = active_result['executed_volume'] / depth_decline if depth_decline > 0 else 0
        
        # Classify regime
        regime = self._classify_regime(
            active_volume=active_result['taker_sell_volume'],
            passive_volume=passive_drain,
            taker_buy_volume=active_result['taker_buy_volume'],
            absorption_efficiency=absorption_eff,
            sanity_check_passed=sanity_result['has_active_flow'],
            confidence=confidence
        )
        
        # Increment regime counter
        self.regime_counts[regime] += 1
        
        return {
            'regime': regime,
            'active_drain': active_result['taker_sell_volume'],
            'passive_drain': passive_drain,
            'absorption_efficiency': absorption_eff,
            'taker_sell_volume': active_result['taker_sell_volume'],
            'taker_buy_volume': active_result['taker_buy_volume'],
            'sanity_check_passed': sanity_result['has_active_flow'],
            'depth_decline': depth_decline,
            'active_ratio': active_result['taker_sell_volume'] / active_result['taker_buy_volume'] if active_result['taker_buy_volume'] > 0 else 0
        }
    
    def _calculate_active_drain_concurrent(self, 
                                          drain_side: str,
                                          start_time: float,
                                          end_time: float) -> Dict:
        """
        Calculate active drain (executed taker volume) concurrent with depth decline.
        
        This is the PRIMARY confirmation method per expert Q4.
        """
        taker_sell_volume = 0
        taker_buy_volume = 0
        executed_volume = 0
        
        for trade in self.trade_history:
            # Only consider trades in concurrent window
            if start_time <= trade['timestamp'] <= end_time:
                executed_volume += trade['quantity']
                
                if trade['taker_side'] == 'SELL':
                    taker_sell_volume += trade['quantity']
                else:
                    taker_buy_volume += trade['quantity']
        
        return {
            'taker_sell_volume': taker_sell_volume,
            'taker_buy_volume': taker_buy_volume,
            'executed_volume': executed_volume
        }
    
    def _sanity_check_trailing(self, drain_side: str, end_time: float) -> Dict:
        """
        SECONDARY sanity check: Ensure non-zero taker_sell in trailing 1.5s window.
        
        Per expert: "Ensure non-zero taker sell flow in [0s, +1.5s]"
        """
        trailing_start = end_time
        trailing_end = end_time + self.SANITY_CHECK_WINDOW
        
        taker_sell_volume = 0
        
        for trade in self.trade_history:
            if trailing_start <= trade['timestamp'] <= trailing_end:
                if trade['taker_side'] == 'SELL':
                    taker_sell_volume += trade['quantity']
        
        return {
            'has_active_flow': taker_sell_volume > 0,
            'trailing_sell_volume': taker_sell_volume
        }
    
    def _calculate_passive_drain(self, 
                                drain_side: str,
                                start_time: float,
                                end_time: float) -> float:
        """
        Calculate passive drain (cancelled volume) by comparing depth changes.
        
        Passive drain = depth decline - executed volume
        """
        depth_decline = self._calculate_depth_decline(drain_side, start_time, end_time)
        
        # Get executed volume in same window
        executed = 0
        for trade in self.trade_history:
            if start_time <= trade['timestamp'] <= end_time:
                executed += trade['quantity']
        
        # Passive = what disappeared without being traded
        passive = max(depth_decline - executed, 0)
        
        return passive
    
    def _calculate_depth_decline(self, drain_side: str, start_time: float, end_time: float) -> float:
        """Calculate total depth decline during window."""
        # Find depth at start and end
        start_depth = None
        end_depth = None
        
        for snapshot in self.depth_history:
            if snapshot['timestamp'] <= start_time:
                start_depth = snapshot['bid_depth'] if drain_side == 'bid' else snapshot['ask_depth']
            if snapshot['timestamp'] <= end_time:
                end_depth = snapshot['bid_depth'] if drain_side == 'bid' else snapshot['ask_depth']
        
        if start_depth is None or end_depth is None:
            return 0
        
        return max(start_depth - end_depth, 0)
    
    def _classify_regime(self, 
                        active_volume: float,
                        passive_volume: float,
                        taker_buy_volume: float,
                        absorption_efficiency: float,
                        sanity_check_passed: bool,
                        confidence: float) -> str:
        """
        Classify drain into one of 4 regimes.
        
        Expert logic (Q4):
        1. Check PRIMARY: active > 1.8× buy (concurrent window)
        2. Check SECONDARY: non-zero active in trailing window
        3. If both pass → REAL_PRESSURE (or PANIC if extreme)
        4. Else → SPOOF_CLEANUP or NOISE
        """
        # Check PRIMARY condition
        active_ratio = active_volume / taker_buy_volume if taker_buy_volume > 0 else float('inf')
        
        if active_ratio > self.ACTIVE_THRESHOLD_RATIO and sanity_check_passed:
            # Real selling pressure confirmed
            
            # Check for PANIC regime (extreme absorption)
            if absorption_efficiency > self.PANIC_ABSORPTION_THRESHOLD:
                return 'PANIC'
            else:
                return 'REAL_PRESSURE'
        
        elif passive_volume > active_volume * 2:
            # Mostly passive (cancelled orders)
            return 'SPOOF_CLEANUP'
        
        else:
            # Low drain or balanced flow
            return 'NOISE'
    
    def should_trade(self, regime: str, confidence: float) -> bool:
        """
        Determine if signal should be traded based on regime.
        
        Per expert guidance (Week 3 Task 3.2):
        - REAL_PRESSURE: Trade ✅
        - SPOOF_CLEANUP: Skip ❌
        - PANIC: Conditional (only if conf > 85%)  
        - NOISE: Skip ❌
        """
        if regime == 'REAL_PRESSURE':
            return True
        elif regime == 'PANIC':
            return confidence > 85.0
        else:  # SPOOF_CLEANUP or NOISE
            return False
    
    def get_stats(self) -> Dict:
        """Get regime classification statistics."""
        total = sum(self.regime_counts.values())
        
        return {
            'total_drains_classified': total,
            'real_pressure_count': self.regime_counts['REAL_PRESSURE'],
            'spoof_cleanup_count': self.regime_counts['SPOOF_CLEANUP'],
            'panic_count': self.regime_counts['PANIC'],
            'noise_count': self.regime_counts['NOISE'],
            'real_pressure_pct': self.regime_counts['REAL_PRESSURE'] / total * 100 if total > 0 else 0,
            'spoof_cleanup_pct': self.regime_counts['SPOOF_CLEANUP'] / total * 100 if total > 0 else 0
        }


if __name__ == "__main__":
    """Test drain regime classifier."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 3 TASK 3.1: ACTIVE VS PASSIVE DRAIN CLASSIFIER TEST")
    print("=" * 80)
    print("\n🔒 LOCKED PARAMETERS (per expert Q4):")
    print(f"   Concurrent window: {DrainRegimeClassifier.DRAIN_WINDOW_SECONDS}s")
    print(f"   Sanity check: {DrainRegimeClassifier.SANITY_CHECK_WINDOW}s trailing")
    print(f"   Active threshold: {DrainRegimeClassifier.ACTIVE_THRESHOLD_RATIO}× taker_buy")
    print(f"   Panic threshold: {DrainRegimeClassifier.PANIC_ABSORPTION_THRESHOLD} absorption\n")
    
    classifier = DrainRegimeClassifier('BTCUSDT')
    
    # Test Scenario 1: REAL_PRESSURE (concurrent selling with depth decline)
    print("Scenario 1: REAL PRESSURE (aggressive selling)")
    print("-" * 80)
    
    # Simulate depth decline
    base_time = time.time()
    for t in range(-30, 1):
        depth = 100 - (t + 30) * 2  # Depth declining from 100 to 40
        classifier.update_depth({
            'bid_depth': depth,
            'ask_depth': 100
        }, base_time + t)
    
    # Simulate aggressive taker SELL trades (concurrent with decline)
    for t in range(-30, 1, 2):
        classifier.update_trade({
            'timestamp': base_time + t,
            'quantity': 2.0,
            'price': 100000,
            'side': 'SELL',
            'is_buyer_maker': True  # Seller is taker
        })
    
    # Small buy pressure
    for t in range(-30, 1, 5):
        classifier.update_trade({
            'timestamp': base_time + t,
            'quantity': 0.5,
            'price': 100000,
            'side': 'BUY',
            'is_buyer_maker': False  # Buyer is taker
        })
    
    result1 = classifier.classify_drain('bid', base_time - 30, base_time, confidence=75)
    
    print(f"   Regime: {result1['regime']}")
    print(f"   Active (taker_sell): {result1['active_drain']:.2f}")
    print(f"   Passive (cancelled): {result1['passive_drain']:.2f}")
    print(f"   Absorption Efficiency: {result1['absorption_efficiency']:.2%}")
    print(f"   Active Ratio: {result1['active_ratio']:.2f}×")
    print(f"   Sanity Check: {'✅ PASS' if result1['sanity_check_passed'] else '❌ FAIL'}")
    print(f"   Should Trade: {'✅ YES' if classifier.should_trade(result1['regime'], 75) else '❌ NO'}\n")
    
    # Test Scenario 2: SPOOF_CLEANUP (orders cancelled, minimal execution)
    print("Scenario 2: SPOOF CLEANUP (cancelled orders)")
    print("-" * 80)
    
    classifier2 = DrainRegimeClassifier('BTCUSDT')
    
    # Simulate depth decline (mostly passive)
    base_time2 = time.time()
    for t in range(-30, 1):
        depth = 100 - (t + 30) * 2
        classifier2.update_depth({
            'bid_depth': depth,
            'ask_depth': 100
        }, base_time2 + t)
    
    # Very few trades (mostly cancellations)
    for t in range(-30, 1, 10):
        classifier2.update_trade({
            'timestamp': base_time2 + t,
            'quantity': 0.3,
            'price': 100000,
            'side': 'SELL',
            'is_buyer_maker': True
        })
    
    result2 = classifier2.classify_drain('bid', base_time2 - 30, base_time2, confidence=70)
    
    print(f"   Regime: {result2['regime']}")
    print(f"   Active (taker_sell): {result2['active_drain']:.2f}")
    print(f"   Passive (cancelled): {result2['passive_drain']:.2f}")
    print(f"   Absorption Efficiency: {result2['absorption_efficiency']:.2%}")
    print(f"   Active Ratio: {result2['active_ratio']:.2f}×")
    print(f"   Should Trade: {'✅ YES' if classifier2.should_trade(result2['regime'], 70) else '❌ NO'}\n")
    
    # Stats
    print("=" * 80)
    print("STATISTICS")
    print("=" * 80)
    stats = classifier.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<30s}: {value:.2f}")
        else:
            print(f"   {key:<30s}: {value}")
    
    print("\n✅ Test complete - Ready for integration with toxicity_aware_detector.py")
