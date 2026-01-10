"""
Week 2 Task 2.1: Survival-Weighted Depth Calculator
===================================================

Implements context-aware lambda (λ) weighting for orderbook depth.

Expert Guidance (Expert #2):
- Use FIXED heuristic values (DO NOT optimize on PnL)
- Lambda is a regularization prior, not a predictive parameter
- Validate directional impact only (signal ↓20-35%, WR ↑4-8pts)

LOCKED PARAMETERS (from expert_response_final_decisions.md):
- base_λ = 0.08
- α (spread factor) = 0.5
- β (volatility factor) = 0.6
- γ (level distance factor) = 1.2

Formula:
    λ_final = base_λ × (1 + α × spread_factor) × 
              (1 + β × vol_factor) × (1 + γ × level_factor)
    
    weight(age) = exp(-λ_final × age_seconds)
    weighted_depth = Σ(depth_i × weight_i)
"""

import numpy as np
from typing import Dict, List, Tuple
from collections import deque
import logging

logger = logging.getLogger(__name__)


class SurvivalWeightedDepth:
    """
    Calculate survival-weighted depth using context-aware lambda.
    
    Weights recent depth higher than stale depth, with context adjustments
    for spread, volatility, and level distance.
    """
    
    # LOCKED PARAMETERS - DO NOT MODIFY (per expert decision)
    BASE_LAMBDA = 0.08
    ALPHA_SPREAD = 0.5
    BETA_VOLATILITY = 0.6
    GAMMA_LEVEL_DISTANCE = 1.2
    
    def __init__(self, symbol: str, lookback_seconds: int = 30):
        """
        Initialize survival-weighted depth calculator.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            lookback_seconds: Time window for depth tracking
        """
        self.symbol = symbol
        self.lookback_seconds = lookback_seconds
        
        # Store depth snapshots for survival weighting
        self.depth_history = deque(maxlen=lookback_seconds)
        
        # Track volatility for β scaling
        self.price_history = deque(maxlen=300)  # 5min window
        
        # Metrics tracking
        self.original_depth_sum = 0
        self.weighted_depth_sum = 0
        
    def update(self, orderbook: Dict, timestamp: float):
        """
        Update with new orderbook snapshot.
        
        Args:
            orderbook: {
                'bids': [[price, qty], ...],
                'asks': [[price, qty], ...],
                'timestamp': float
            }
            timestamp: Current timestamp
        """
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return
        
        # Store snapshot with timestamp
        midprice = (float(bids[0][0]) + float(asks[0][0])) / 2
        
        snapshot = {
            'timestamp': timestamp,
            'bids': [(float(p), float(q)) for p, q in bids[:10]],  # Top 10 levels
            'asks': [(float(p), float(q)) for p, q in asks[:10]],
            'midprice': midprice
        }
        
        self.depth_history.append(snapshot)
        self.price_history.append(midprice)
        
    def calculate_weighted_depth(self, side: str, num_levels: int = 5) -> Dict:
        """
        Calculate survival-weighted depth for bid or ask side.
        
        Args:
            side: 'bid' or 'ask'
            num_levels: Number of levels to include
            
        Returns:
            {
                'original_depth': float,  # Unweighted total
                'weighted_depth': float,  # Survival-weighted total
                'weight_ratio': float,    # weighted / original
                'lambda_final': float     # Final λ used
            }
        """
        if len(self.depth_history) == 0:
            return {
                'original_depth': 0,
                'weighted_depth': 0,
                'weight_ratio': 1.0,
                'lambda_final': self.BASE_LAMBDA
            }
        
        # Get most recent snapshot
        current_snapshot = self.depth_history[-1]
        current_time = current_snapshot['timestamp']
        
        # Calculate context factors
        spread_factor = self._calculate_spread_factor(current_snapshot)
        vol_factor = self._calculate_volatility_factor()
        
        # Initialize accumulators
        original_depth_total = 0
        weighted_depth_total = 0
        
        # Get levels to analyze
        levels = current_snapshot['bids'] if side == 'bid' else current_snapshot['asks']
        levels = levels[:num_levels]
        
        # Calculate weighted depth for each level
        for level_idx, (price, qty) in enumerate(levels):
            # Level distance factor
            level_factor = level_idx / num_levels  # 0 for L1, approaching 1 for deeper levels
            
            # Calculate λ for this price level
            lambda_final = self._calculate_lambda(
                spread_factor=spread_factor,
                vol_factor=vol_factor,
                level_factor=level_factor
            )
            
            # Find historical depth at this price level and apply survival weights
            weighted_qty = 0
            age_weight_sum = 0
            
            for snapshot in self.depth_history:
                age_seconds = current_time - snapshot['timestamp']
                
                # Find depth at this price in historical snapshot
                snapshot_levels = snapshot['bids'] if side == 'bid' else snapshot['asks']
                
                # Look for matching price (within tolerance)
                price_tolerance = price * 0.0001  # 0.01% tolerance
                for hist_price, hist_qty in snapshot_levels:
                    if abs(hist_price - price) < price_tolerance:
                        # Apply survival weight: exp(-λ × age)
                        weight = np.exp(-lambda_final * age_seconds)
                        weighted_qty += hist_qty * weight
                        age_weight_sum += weight
                        break  # Found matching price, move to next snapshot
            
            # Calculate effective weighted quantity for this level
            if age_weight_sum > 0:
                effective_qty = weighted_qty / age_weight_sum
            else:
                effective_qty = qty  # Fallback to current if no history
            
            original_depth_total += qty
            weighted_depth_total += effective_qty
        
        # Calculate weight ratio
        weight_ratio = weighted_depth_total / original_depth_total if original_depth_total > 0 else 1.0
        
        # Store for tracking
        self.original_depth_sum = original_depth_total
        self.weighted_depth_sum = weighted_depth_total
        
        return {
            'original_depth': original_depth_total,
            'weighted_depth': weighted_depth_total,
            'weight_ratio': weight_ratio,
            'lambda_final': lambda_final,
            'spread_factor': spread_factor,
            'vol_factor': vol_factor
        }
    
    def _calculate_lambda(self, spread_factor: float, vol_factor: float, level_factor: float) -> float:
        """
        Calculate final λ using locked parameters.
        
        Formula: λ = base_λ × (1 + α×spread) × (1 + β×vol) × (1 + γ×level)
        """
        lambda_final = (
            self.BASE_LAMBDA *
            (1 + self.ALPHA_SPREAD * spread_factor) *
            (1 + self.BETA_VOLATILITY * vol_factor) *
            (1 + self.GAMMA_LEVEL_DISTANCE * level_factor)
        )
        
        return lambda_final
    
    def _calculate_spread_factor(self, snapshot: Dict) -> float:
        """
        Calculate spread factor (normalized 0-1).
        
        Wider spread → higher λ → faster decay (less trust in stale depth)
        """
        bids = snapshot['bids']
        asks = snapshot['asks']
        
        if not bids or not asks:
            return 0.5
        
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        midprice = snapshot['midprice']
        
        # Spread as % of midprice
        spread_pct = (best_ask - best_bid) / midprice
        
        # Normalize: 0.01% spread = 0.0, 0.10% spread = 1.0
        # Most crypto spreads are 0.01-0.05%
        spread_factor = min(max((spread_pct - 0.0001) / 0.0009, 0.0), 1.0)
        
        return spread_factor
    
    def _calculate_volatility_factor(self) -> float:
        """
        Calculate volatility factor (normalized 0-1).
        
        Higher volatility → higher λ → faster decay
        """
        if len(self.price_history) < 10:
            return 0.5  # Default
        
        # Calculate rolling volatility (5-minute window)
        prices = np.array(self.price_history)
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns) * np.sqrt(len(returns))  # Annualize
        
        # Normalize: 0.2% vol = 0.0, 2.0% vol = 1.0
        vol_factor = min(max((volatility - 0.002) / 0.018, 0.0), 1.0)
        
        return vol_factor
    
    def get_stats(self) -> Dict:
        """Get survival weighting statistics."""
        if len(self.depth_history) == 0:
            return {
                'snapshots_tracked': 0,
                'original_depth': 0,
                'weighted_depth': 0,
                'weight_ratio': 1.0
            }
        
        return {
            'snapshots_tracked': len(self.depth_history),
            'original_depth': self.original_depth_sum,
            'weighted_depth': self.weighted_depth_sum,
            'weight_ratio': self.weighted_depth_sum / self.original_depth_sum if self.original_depth_sum > 0 else 1.0,
            'base_lambda': self.BASE_LAMBDA,
            'alpha': self.ALPHA_SPREAD,
            'beta': self.BETA_VOLATILITY,
            'gamma': self.GAMMA_LEVEL_DISTANCE
        }


if __name__ == "__main__":
    """Test survival-weighted depth calculator."""
    
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 2 TASK 2.1: SURVIVAL-WEIGHTED DEPTH TEST")
    print("=" * 80)
    print("\n🔒 LOCKED PARAMETERS (DO NOT OPTIMIZE):")
    print(f"   base_λ = {SurvivalWeightedDepth.BASE_LAMBDA}")
    print(f"   α (spread) = {SurvivalWeightedDepth.ALPHA_SPREAD}")
    print(f"   β (volatility) = {SurvivalWeightedDepth.BETA_VOLATILITY}")
    print(f"   γ (level distance) = {SurvivalWeightedDepth.GAMMA_LEVEL_DISTANCE}\n")
    
    calc = SurvivalWeightedDepth('BTCUSDT', lookback_seconds=30)
    
    # Simulate orderbook snapshots over time
    base_price = 100000
    
    print("Simulating 30 orderbook snapshots...")
    for t in range(30):
        # Simulate price movement
        price_offset = np.random.normal(0, 10)
        midprice = base_price + price_offset
        
        # Create orderbook
        bids = [[midprice - i, 1.0 - (i * 0.1)] for i in range(1, 11)]
        asks = [[midprice + i, 1.0 - (i * 0.1)] for i in range(1, 11)]
        
        orderbook = {
            'bids': bids,
            'asks': asks,
            'timestamp': time.time()
        }
        
        calc.update(orderbook, orderbook['timestamp'])
        time.sleep(0.1)  # Simulate 100ms snapshots
    
    # Calculate weighted depth for bids
    print("\n" + "=" * 80)
    print("CALCULATING WEIGHTED BID DEPTH (Top 5 Levels)")
    print("=" * 80)
    
    result = calc.calculate_weighted_depth('bid', num_levels=5)
    
    print(f"\n📊 Results:")
    print(f"   Original Depth:    {result['original_depth']:.4f}")
    print(f"   Weighted Depth:    {result['weighted_depth']:.4f}")
    print(f"   Weight Ratio:      {result['weight_ratio']:.4f}")
    print(f"   Lambda (final):    {result['lambda_final']:.6f}")
    print(f"   Spread Factor:     {result['spread_factor']:.4f}")
    print(f"   Volatility Factor: {result['vol_factor']:.4f}")
    
    print(f"\n💡 Interpretation:")
    if result['weight_ratio'] < 0.9:
        print(f"   ⚠️  Depth discounted by {(1 - result['weight_ratio'])*100:.1f}% (stale/toxic)")
    elif result['weight_ratio'] > 0.95:
        print(f"   ✅ Depth is stable (minimal decay)")
    else:
        print(f"   🔵 Moderate decay (normal market conditions)")
    
    # Stats
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    stats = calc.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<20s}: {value:.4f}")
        else:
            print(f"   {key:<20s}: {value}")
    
    print("\n✅ Test complete - Ready for integration with liquidity_drain_detector.py")
