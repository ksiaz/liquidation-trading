"""
Liquidation Heatmap - Real-Time Density Tracking

Tracks where liquidations actually occur to build a density map.
Uses time-weighted decay so recent liquidations matter more.
"""

import time
import logging
from collections import deque
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LiquidationHeatmap:
    """
    Real-time heatmap of actual liquidation density.
    
    Features:
    - Tracks historical liquidation locations
    - Time-weighted decay (recent matters more)
    - Price-binned for efficient storage
    - Hot zone detection
    """
    
    def __init__(self, symbol: str, price_bins: int = 200):
        """
        Initialize liquidation heatmap.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            price_bins: Number of price bins for granularity
        """
        self.symbol = symbol
        self.price_bins = price_bins
        
        # Heatmap data: {price_offset_pct: {'count': X, 'total_usd': Y, 'weight': Z}}
        self.heatmap = {}
        
        # Time-weighted decay
        self.decay_factor = 0.95  # 5% decay per interval
        self.decay_interval = 300  # 5 minutes
        self.last_decay = time.time()
        
        # Current price tracking
        self.current_price = None
        
        # Statistics
        self.total_liquidations = 0
        self.total_value_usd = 0
        
    def on_liquidation(self, liq_event: Dict):
        """
        Update heatmap when liquidation occurs.
        
        Args:
            liq_event: Dict with 'price', 'value_usd', 'side', 'timestamp'
        """
        try:
            price = float(liq_event['price'])
            value_usd = float(liq_event['value_usd'])
            
            # Get price bin
            price_bin = self._get_price_bin(price)
            
            # Update heatmap
            if price_bin not in self.heatmap:
                self.heatmap[price_bin] = {
                    'count': 0,
                    'total_usd': 0,
                    'weight': 0,
                    'last_update': time.time()
                }
            
            self.heatmap[price_bin]['count'] += 1
            self.heatmap[price_bin]['total_usd'] += value_usd
            self.heatmap[price_bin]['weight'] += 1.0  # Fresh weight
            self.heatmap[price_bin]['last_update'] = time.time()
            
            # Update statistics
            self.total_liquidations += 1
            self.total_value_usd += value_usd
            
            # Apply time decay periodically
            self._apply_decay()
            
        except Exception as e:
            logger.error(f"Error updating heatmap for {self.symbol}: {e}")
    
    def on_price_update(self, price: float):
        """
        Update current price reference.
        
        Args:
            price: Current market price
        """
        self.current_price = price
    
    def _get_price_bin(self, price: float) -> float:
        """
        Round price to nearest bin.
        
        Bins are % offset from current price.
        
        Args:
            price: Liquidation price
        
        Returns:
            Price bin as % offset (e.g., -2.5 = 2.5% below current)
        """
        if self.current_price is None or self.current_price == 0:
            return 0.0
        
        # Calculate % from current price
        pct_offset = ((price - self.current_price) / self.current_price) * 100
        
        # Round to nearest 0.1%
        bin_pct = round(pct_offset, 1)
        
        return bin_pct
    
    def _apply_decay(self):
        """
        Apply time-weighted decay to old liquidations.
        Recent liquidations matter more.
        """
        current_time = time.time()
        
        # Only decay every interval
        if current_time - self.last_decay < self.decay_interval:
            return
        
        # Apply decay to all bins
        bins_to_remove = []
        
        for price_bin, data in self.heatmap.items():
            # Decay weight
            data['weight'] *= self.decay_factor
            
            # Mark for removal if weight too low
            if data['weight'] < 0.01:
                bins_to_remove.append(price_bin)
        
        # Remove low-weight bins
        for price_bin in bins_to_remove:
            del self.heatmap[price_bin]
        
        self.last_decay = current_time
        
        logger.debug(f"Applied decay to {self.symbol} heatmap. "
                    f"Removed {len(bins_to_remove)} bins. "
                    f"Active bins: {len(self.heatmap)}")
    
    def get_hot_zones(self, threshold_percentile: float = 75) -> List[Dict]:
        """
        Get price levels with high liquidation density.
        
        Args:
            threshold_percentile: Return top X percentile (default 75%)
        
        Returns:
            List of hot zones sorted by density score
        """
        if not self.heatmap:
            return []
        
        # Calculate density score for each bin
        densities = []
        
        for price_bin, data in self.heatmap.items():
            # Density = value × weight (recent + large = high score)
            density_score = data['total_usd'] * data['weight']
            
            densities.append({
                'price_offset_pct': price_bin,
                'price': self.current_price * (1 + price_bin / 100) if self.current_price else None,
                'liquidation_count': data['count'],
                'total_value_usd': data['total_usd'],
                'density_score': density_score,
                'weight': data['weight'],
                'last_update': data['last_update']
            })
        
        # Sort by density (highest first)
        densities.sort(key=lambda x: x['density_score'], reverse=True)
        
        # Filter to top percentile
        if threshold_percentile < 100:
            threshold_idx = max(1, int(len(densities) * (threshold_percentile / 100)))
            hot_zones = densities[:threshold_idx]
        else:
            hot_zones = densities
        
        return hot_zones
    
    def get_heatmap_data(self) -> Dict[float, float]:
        """
        Get full heatmap for visualization.
        
        Returns:
            Dict: {price_offset_pct: density_score}
        """
        return {
            price_bin: data['total_usd'] * data['weight']
            for price_bin, data in self.heatmap.items()
        }
    
    def get_density_at_price(self, price: float) -> float:
        """
        Get liquidation density at specific price.
        
        Args:
            price: Price to check
        
        Returns:
            Density score at that price
        """
        price_bin = self._get_price_bin(price)
        
        if price_bin in self.heatmap:
            data = self.heatmap[price_bin]
            return data['total_usd'] * data['weight']
        
        return 0.0
    
    def get_stats(self) -> Dict:
        """Get heatmap statistics."""
        return {
            'symbol': self.symbol,
            'total_liquidations': self.total_liquidations,
            'total_value_usd': self.total_value_usd,
            'active_bins': len(self.heatmap),
            'current_price': self.current_price,
            'hot_zones_count': len(self.get_hot_zones())
        }


if __name__ == "__main__":
    """Test liquidation heatmap."""
    
    logging.basicConfig(level=logging.DEBUG)
    
    # Create heatmap
    heatmap = LiquidationHeatmap('BTCUSDT')
    
    # Simulate current price
    heatmap.on_price_update(95000)
    
    # Simulate liquidations
    test_liquidations = [
        {'price': 94000, 'value_usd': 500000, 'side': 'SELL'},  # 1% below
        {'price': 94000, 'value_usd': 300000, 'side': 'SELL'},  # Same zone
        {'price': 93500, 'value_usd': 1000000, 'side': 'SELL'}, # 1.5% below
        {'price': 96000, 'value_usd': 200000, 'side': 'BUY'},   # 1% above
    ]
    
    for liq in test_liquidations:
        heatmap.on_liquidation(liq)
    
    # Get hot zones
    hot_zones = heatmap.get_hot_zones()
    
    print("=" * 60)
    print("LIQUIDATION HEATMAP TEST")
    print("=" * 60)
    print(f"\nStats: {heatmap.get_stats()}")
    print(f"\nHot Zones:")
    for zone in hot_zones:
        print(f"  {zone['price_offset_pct']:+.1f}% | "
              f"${zone['price']:,.0f} | "
              f"{zone['liquidation_count']} liqs | "
              f"${zone['total_value_usd']:,.0f} | "
              f"Density: {zone['density_score']:,.0f}")
