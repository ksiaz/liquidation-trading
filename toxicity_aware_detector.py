"""
Week 2 Task 2.4: Toxicity-Aware Liquidity Drain Detector
==========================================================

Integrates all three Week 2 toxicity filtering modules:
1. Survival-Weighted Depth (context-aware λ weighting)
2. CTR Calculator (cancel-to-trade ratio)
3. Ghost Order Filter (spoofing detection)

This enhanced detector replaces raw depth with toxicity-filtered depth
to reduce false signals from spoofing and improve signal quality.

Expected Impact (per expert):
- Signal count: ↓20-35%
- Win rate: ↑4-8 points
- Net P&L: ↑2-4%
"""

from collections import deque
from datetime import datetime
import numpy as np
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import toxicity modules
from survival_weighted_depth import SurvivalWeightedDepth
from ctr_calculator import CTRCalculator
from ghost_order_filter import GhostOrderFilter

logger = logging.getLogger(__name__)


class ToxicityAwareLiquidityDrainDetector:
    """
    Enhanced liquidity drain detector with toxicity filtering.
    
    Combines three toxicity modules to filter out:
    1. Stale depth (survival weighting)
    2. Spoofed levels (CTR filtering)
    3. Ghost orders (short-lived large orders)
    """
    
    # Profile configurations (same as original)
    PROFILES = {
        'MODERATE': {
            'drain_threshold': 0.20,      # 20% depth decline
            'lookback_seconds': 30,
            'min_consecutive_ticks': 3,
            'imbalance_threshold': 0.3
        }
    }
    
    # Symbol-specific configs (from original detector)
    SYMBOL_CONFIGS = {
        'BTCUSDT': {'drain_threshold': 0.22, 'lookback_seconds': 30},
        'ETHUSDT': {'drain_threshold': 0.20, 'lookback_seconds': 30},
        'SOLUSDT': {'drain_threshold': 0.18, 'lookback_seconds': 25}
    }
    
    def __init__(self, symbol: str = 'BTCUSDT', profile: str = 'MODERATE'):
        """
        Initialize toxicity-aware detector.
        
        Args:
            symbol: Trading symbol
            profile: Detection profile
        """
        self.symbol = symbol
        
        # Load configuration
        if symbol in self.SYMBOL_CONFIGS:
            self.config = self.SYMBOL_CONFIGS[symbol]
        else:
            self.config = self.PROFILES[profile]
        
        # Initialize toxicity modules
        self.survival_depth = SurvivalWeightedDepth(
            symbol=symbol,
            lookback_seconds=self.config['lookback_seconds']
        )
        self.ctr_calculator = CTRCalculator(symbol=symbol)
        self.ghost_filter = GhostOrderFilter(symbol=symbol, tick_size=self._get_tick_size(symbol))
        
        # History tracking
        self.depth_history = deque(maxlen=self.config['lookback_seconds'])
        self.tick_history = deque(maxlen=10)
        
        # Metrics
        self.total_signals = 0
        self.filtered_signals = 0  # Signals blocked by toxicity
        
    def _get_tick_size(self, symbol: str) -> float:
        """Get appropriate tick size for symbol."""
        if 'BTC' in symbol:
            return 1.0
        elif 'ETH' in symbol:
            return 0.1
        else:  # SOL
            return 0.01
    
    def update(self, orderbook_data: dict, trades: list = None) -> dict:
        """
        Process orderbook snapshot with toxicity filtering.
        
        Args:
            orderbook_data: {
                'timestamp': float,
                'best_bid': float,
                'best_ask': float,
                'bid_volume_10': float,
                'ask_volume_10': float,
                'bids': [[price, qty], ...],  # Full orderbook
                'asks': [[price, qty], ...]
            }
            trades: Optional list of recent trades for CTR calculation
            
        Returns:
            Signal dict or None
        """
        timestamp = orderbook_data.get('timestamp', datetime.now().timestamp())
        
        # Update all toxicity modules
        orderbook_full = {
            'bids': orderbook_data.get('bids', []),
            'asks': orderbook_data.get('asks', [])
        }
        
        self.survival_depth.update(orderbook_full, timestamp)
        self.ctr_calculator.update_orderbook(orderbook_full, timestamp)
        self.ghost_filter.update(orderbook_full, timestamp)
        
        # Update CTR with trades if provided
        if trades:
            for trade in trades:
                self.ctr_calculator.update_trade(trade)
        
        # Calculate toxicity-filtered depth
        filtered_bid_depth = self._calculate_toxicity_filtered_depth(
            side='bid',
            raw_depth=orderbook_data.get('bid_volume_10', 0),
            price=orderbook_data.get('best_bid', 0),
            timestamp=timestamp
        )
        
        filtered_ask_depth = self._calculate_toxicity_filtered_depth(
            side='ask',
            raw_depth=orderbook_data.get('ask_volume_10', 0),
            price=orderbook_data.get('best_ask', 0),
            timestamp=timestamp
        )
        
        # Store filtered depth in history
        self.depth_history.append({
            'timestamp': timestamp,
            'bid_depth': filtered_bid_depth,
            'ask_depth': filtered_ask_depth,
            'raw_bid_depth': orderbook_data.get('bid_volume_10', 0),
            'raw_ask_depth': orderbook_data.get('ask_volume_10', 0)
        })
        
        # Track tick direction
        midprice = (orderbook_data.get('best_bid', 0) + orderbook_data.get('best_ask', 0)) / 2
        self.tick_history.append(midprice)
        
        # Check for liquidity drain using FILTERED depth
        drain_detected, drain_info = self._check_liquidity_drain()
        
        if not drain_detected:
            return None
        
        # Analyze direction
        direction = self._analyze_tick_pattern()
        
        if not direction:
            return None
        
        # Calculate confidence
        confidence = self._calculate_confidence(drain_info, direction)
        
        # Generate signal
        self.total_signals += 1
        
        signal = {
            'timestamp': timestamp,
            'symbol': self.symbol,
            'direction': direction,
            'confidence': confidence,
            'drain_pct': drain_info['drain_pct'],
            'filtered_bid_depth': filtered_bid_depth,
            'filtered_ask_depth': filtered_ask_depth,
            'raw_bid_depth': orderbook_data.get('bid_volume_10', 0),
            'raw_ask_depth': orderbook_data.get('ask_volume_10', 0),
            'toxicity_discount': drain_info.get('toxicity_discount', 1.0),
            'source': 'toxicity_aware_detector'
        }
        
        return signal
    
    def _calculate_toxicity_filtered_depth(self, side: str, raw_depth: float, 
                                           price: float, timestamp: float) -> float:
        """
        Apply all three toxicity filters to depth.
        
        Combined formula:
        filtered_depth = raw × survival_weight × ctr_discount × ghost_discount
        """
        if raw_depth == 0:
            return 0
        
        # 1. Survival weighting (context-aware λ decay)
        survival_result = self.survival_depth.calculate_weighted_depth(side, num_levels=10)
        survival_weight = survival_result.get('weight_ratio', 1.0)
        
        # 2. CTR discount (spoofing filter)
        ctr_discount = 1.0
        ctr_per_level = self.ctr_calculator.calculate_ctr_per_level(num_levels=10)
        if price in ctr_per_level:
            ctr = ctr_per_level[price]
            if ctr > CTRCalculator.CTR_THRESHOLD:
                ctr_discount = 0.5  # 50% discount for toxic levels
        
        # 3. Ghost discount (large short-lived orders)
        ghost_depth = self.ghost_filter.apply_ghost_discount(raw_depth, price, timestamp)
        ghost_discount = ghost_depth / raw_depth if raw_depth > 0 else 1.0
        
        # Combined discount
        filtered_depth = raw_depth * survival_weight * ctr_discount * ghost_discount
        
        return filtered_depth
    
    def _check_liquidity_drain(self) -> tuple:
        """
        Check for liquidity drain using TOXICITY-FILTERED depth.
        
        Returns:
            (bool, dict): (drain_detected, drain_info)
        """
        if len(self.depth_history) < 5:
            return False, {}
        
        # Get current and historical depths
        current = self.depth_history[-1]
        historical = list(self.depth_history)[-self.config['lookback_seconds']:]
        
        # Calculate average historical depth (filtered)
        avg_bid_depth = np.mean([h['bid_depth'] for h in historical[:-1]])
        avg_ask_depth = np.mean([h['ask_depth'] for h in historical[:-1]])
        
        # Calculate drain percentage
        bid_drain_pct = (avg_bid_depth - current['bid_depth']) / avg_bid_depth if avg_bid_depth > 0 else 0
        ask_drain_pct = (avg_ask_depth - current['ask_depth']) / avg_ask_depth if avg_ask_depth > 0 else 0
        
        # Determine which side drained
        if bid_drain_pct > self.config['drain_threshold']:
            drain_side = 'bid'
            drain_pct = bid_drain_pct
        elif ask_drain_pct > self.config['drain_threshold']:
            drain_side = 'ask'
            drain_pct = ask_drain_pct
        else:
            return False, {}
        
        # Calculate toxicity discount for metrics
        raw_current = current['raw_bid_depth'] if drain_side == 'bid' else current['raw_ask_depth']
        filtered_current = current['bid_depth'] if drain_side == 'bid' else current['ask_depth']
        toxicity_discount = filtered_current / raw_current if raw_current > 0 else 1.0
        
        drain_info = {
            'side': drain_side,
            'drain_pct': drain_pct,
            'avg_depth': avg_bid_depth if drain_side == 'bid' else avg_ask_depth,
            'current_depth': current['bid_depth'] if drain_side == 'bid' else current['ask_depth'],
            'toxicity_discount': toxicity_discount
        }
        
        return True, drain_info
    
    def _analyze_tick_pattern(self) -> str:
        """Analyze recent price ticks to determine reversal direction."""
        if len(self.tick_history) < 3:
            return None
        
        recent_ticks = list(self.tick_history)[-5:]
        
        # Count up vs down ticks
        up_ticks = sum(1 for i in range(1, len(recent_ticks)) 
                      if recent_ticks[i] > recent_ticks[i-1])
        down_ticks = len(recent_ticks) - 1 - up_ticks
        
        # Mean reversion logic: if price went down, expect reversal up
        if down_ticks >= self.config.get('min_consecutive_ticks', 3):
            return 'LONG'  # Price dropped, expect reversal up
        elif up_ticks >= self.config.get('min_consecutive_ticks', 3):
            return 'SHORT'  # Price pumped, expect reversal down
        
        return None
    
    def _calculate_confidence(self, drain_info: dict, direction: str) -> float:
        """Calculate signal confidence (0-100)."""
        # Base confidence from drain magnitude
        base_confidence = min(drain_info['drain_pct'] * 100, 70)
        
        # Bonus for strong toxicity filtering (more discount = cleaner signal)
        toxicity_discount = drain_info.get('toxicity_discount', 1.0)
        toxicity_bonus = (1 - toxicity_discount) * 20  # Up to +20 points
        
        confidence = min(base_confidence + toxicity_bonus, 95)
        
        return confidence
    
    def get_stats(self) -> dict:
        """Get detector statistics including toxicity metrics."""
        survival_stats = self.survival_depth.get_stats()
        ctr_stats = self.ctr_calculator.get_stats()
        ghost_stats = self.ghost_filter.get_stats()
        
        return {
            'total_signals': self.total_signals,
            'filtered_signals': self.filtered_signals,
            'survival_weight_avg': survival_stats.get('weight_ratio', 1.0),
            'ctr_toxic_pct': ctr_stats.get('toxic_pct', 0),
            'ghost_buckets_active': ghost_stats.get('active_ghost_buckets', 0),
            'toxicity_modules_active': 3
        }


if __name__ == "__main__":
    """Test toxicity-aware detector."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 2 TASK 2.4: TOXICITY-AWARE DETECTOR TEST")
    print("=" * 80)
    print("\n✅ Integrated Modules:")
    print("   1. Survival-Weighted Depth")
    print("   2. CTR Calculator")
    print("   3. Ghost Order Filter\n")
    
    detector = ToxicityAwareLiquidityDrainDetector(symbol='BTCUSDT')
    
    # Simulate orderbook sequence
    import time
    base_price = 100000
    
    print("Simulating orderbook sequence with liquidity drain...")
    
    for i in range(35):
        # Simulate depth draining
        drain_factor = 1.0 - (i / 35) * 0.3  # 30% drain over time
        
        orderbook = {
            'timestamp': time.time(),
            'best_bid': base_price - 1,
            'best_ask': base_price + 1,
            'bid_volume_10': 100 * drain_factor,
            'ask_volume_10': 100,
            'bids': [[base_price - j, 10 * drain_factor] for j in range(1, 11)],
            'asks': [[base_price + j, 10] for j in range(1, 11)]
        }
        
        signal = detector.update(orderbook)
        
        if signal:
            print(f"\n🎯 SIGNAL DETECTED at t={i}s:")
            print(f"   Direction: {signal['direction']}")
            print(f"   Confidence: {signal['confidence']:.1f}%")
            print(f"   Drain: {signal['drain_pct']*100:.1f}%")
            print(f"   Toxicity Discount: {signal.get('toxicity_discount', 1.0):.2f}")
            print(f"   Raw Bid Depth: {signal['raw_bid_depth']:.2f}")
            print(f"   Filtered Bid Depth: {signal['filtered_bid_depth']:.2f}")
        
        time.sleep(0.1)
    
    # Stats
    print("\n" + "=" * 80)
    print("DETECTOR STATISTICS")
    print("=" * 80)
    stats = detector.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<30s}: {value:.4f}")
        else:
            print(f"   {key:<30s}: {value}")
    
    print("\n✅ Integration test complete!")
    print("\n📊 Next Step: Run full backtest with toxicity-aware detector")
    print("   Expected: Signal count ↓20-35%, WR ↑4-8 points")
