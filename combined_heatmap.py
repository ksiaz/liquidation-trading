"""
Combined Heatmap Generator

Merges multiple data sources into comprehensive heatmap:
1. Historical liquidation density
2. Current order walls
3. Predicted liquidation zones
"""

import time
import logging
from typing import Dict, List, Optional
from liquidation_heatmap import LiquidationHeatmap
from order_wall_detector import OrderWallDetector
from liquidation_predictor import LiquidationPredictor

logger = logging.getLogger(__name__)


class CombinedHeatmapGenerator:
    """
    Generate comprehensive heatmap combining:
    - Historical liquidation density (where liqs occurred)
    - Current order walls (from 20-level orderbook)
    - Predicted liquidation zones (theoretical)
    """
    
    def __init__(self, symbol: str, predictor=None):
        """
        Initialize combined heatmap generator.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            predictor: Optional LiquidationPredictor instance
        """
        self.symbol = symbol
        
        # Initialize components
        self.liq_heatmap = LiquidationHeatmap(symbol)
        self.wall_detector = OrderWallDetector(symbol)
        self.zone_predictor = predictor  # Can be None initially
        
        # Current price
        self.current_price = None
    
    def set_predictor(self, predictor):
        """Set predictor after initialization."""
        self.zone_predictor = predictor
        
    def on_liquidation(self, liq_event: Dict):
        """
        Update liquidation heatmap.
        
        Args:
            liq_event: Liquidation event data
        """
        self.liq_heatmap.on_liquidation(liq_event)
    
    def on_orderbook_update(self, orderbook: Dict):
        """
        Update order walls and price.
        
        Args:
            orderbook: Orderbook data with bids/asks
        """
        # Update wall detector
        self.wall_detector.on_orderbook_update(orderbook)
        
        # Update current price
        if orderbook.get('bids') and orderbook.get('asks'):
            best_bid = float(orderbook['bids'][0][0])
            best_ask = float(orderbook['asks'][0][0])
            self.current_price = (best_bid + best_ask) / 2
            
            # Update heatmap price reference
            self.liq_heatmap.on_price_update(self.current_price)
    
    def generate_heatmap(self) -> Dict:
        """
        Generate complete heatmap data.
        
        Returns:
            Dict with all heatmap layers and metadata
        """
        if self.current_price is None:
            return {'error': 'No price data available'}
        
        # Layer 1: Historical liquidation density
        liq_density = self.liq_heatmap.get_heatmap_data()
        hot_zones = self.liq_heatmap.get_hot_zones()
        
        # Layer 2: Current order walls
        walls = self.wall_detector.get_all_walls()
        significant_walls = self.wall_detector.get_significant_walls()
        
        # Layer 3: Predicted zones
        predicted_zones = self.zone_predictor.estimate_liquidation_zones(self.symbol)
        
        # Combine into visualization data
        heatmap_data = {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'timestamp': time.time(),
            
            # Layers
            'layers': {
                'liquidation_density': self._format_density_layer(liq_density),
                'order_walls': self._format_walls_layer(walls),
                'predicted_zones': self._format_zones_layer(predicted_zones)
            },
            
            # Highlights
            'hot_zones': hot_zones,
            'significant_walls': significant_walls,
            
            # Statistics
            'stats': {
                'heatmap': self.liq_heatmap.get_stats(),
                'walls': self.wall_detector.get_stats(),
                'spoofing_events': len(self.wall_detector.get_spoofing_events(60))
            }
        }
        
        return heatmap_data
    
    def _format_density_layer(self, density_data: Dict) -> List[Dict]:
        """
        Format liquidation density for visualization.
        
        Args:
            density_data: {price_offset_pct: density_score}
        
        Returns:
            List of density points
        """
        if not self.current_price:
            return []
        
        return [
            {
                'price': self.current_price * (1 + offset_pct / 100),
                'offset_pct': offset_pct,
                'density': density,
                'type': 'HISTORICAL'
            }
            for offset_pct, density in density_data.items()
        ]
    
    def _format_walls_layer(self, walls: List[Dict]) -> List[Dict]:
        """
        Format order walls for visualization.
        
        Args:
            walls: List of wall dicts
        
        Returns:
            List of formatted walls
        """
        if not self.current_price:
            return []
        
        return [
            {
                'price': wall['price'],
                'offset_pct': ((wall['price'] - self.current_price) / self.current_price) * 100,
                'value_usd': wall['value_usd'],
                'quantity': wall['quantity'],
                'side': wall['side'],
                'level': wall['level'],
                'size_ratio': wall['size_ratio'],
                'type': 'ORDER_WALL'
            }
            for wall in walls
        ]
    
    def _format_zones_layer(self, zones: List[Dict]) -> List[Dict]:
        """
        Format predicted zones for visualization.
        
        Args:
            zones: List of predicted zone dicts
        
        Returns:
            List of formatted zones
        """
        return [
            {
                'price': zone['liquidation_price'],
                'offset_pct': zone['distance_pct'] * (-1 if zone['type'] == 'LONG' else 1),
                'leverage': zone['leverage'],
                'side': zone['type'],
                'type': 'PREDICTED'
            }
            for zone in zones
        ]
    
    def get_summary(self) -> Dict:
        """
        Get quick summary of current heatmap state.
        
        Returns:
            Dict with summary statistics
        """
        heatmap_data = self.generate_heatmap()
        
        if 'error' in heatmap_data:
            return heatmap_data
        
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'hot_zones_count': len(heatmap_data['hot_zones']),
            'active_walls_count': heatmap_data['stats']['walls']['total_walls'],
            'largest_wall_usd': max(
                heatmap_data['stats']['walls']['largest_bid_wall'],
                heatmap_data['stats']['walls']['largest_ask_wall']
            ),
            'total_liquidations_tracked': heatmap_data['stats']['heatmap']['total_liquidations'],
            'spoofing_events_1min': heatmap_data['stats']['spoofing_events']
        }


if __name__ == "__main__":
    """Test combined heatmap generator."""
    
    logging.basicConfig(level=logging.INFO)
    
    # Create generator
    generator = CombinedHeatmapGenerator('BTCUSDT')
    
    # Simulate orderbook
    test_orderbook = {
        'bids': [
            [95000, 0.5],
            [94900, 0.6],
            [94800, 5.0],  # Wall
        ],
        'asks': [
            [95100, 0.5],
            [95200, 10.0],  # Wall
            [95300, 0.6],
        ]
    }
    
    # Simulate liquidations
    test_liquidations = [
        {'price': 94000, 'value_usd': 500000, 'side': 'SELL'},
        {'price': 94000, 'value_usd': 300000, 'side': 'SELL'},
        {'price': 93500, 'value_usd': 1000000, 'side': 'SELL'},
    ]
    
    # Update
    generator.on_orderbook_update(test_orderbook)
    for liq in test_liquidations:
        generator.on_liquidation(liq)
    
    # Generate heatmap
    heatmap = generator.generate_heatmap()
    
    print("=" * 60)
    print("COMBINED HEATMAP TEST")
    print("=" * 60)
    
    print(f"\nSummary: {generator.get_summary()}")
    
    print(f"\nLayers:")
    print(f"  Density points: {len(heatmap['layers']['liquidation_density'])}")
    print(f"  Order walls: {len(heatmap['layers']['order_walls'])}")
    print(f"  Predicted zones: {len(heatmap['layers']['predicted_zones'])}")
    
    print(f"\nHot Zones:")
    for zone in heatmap['hot_zones'][:5]:
        print(f"  {zone['price_offset_pct']:+.1f}% | ${zone['price']:,.0f} | "
              f"Density: {zone['density_score']:,.0f}")
    
    print(f"\nSignificant Walls:")
    for wall in heatmap['significant_walls']:
        print(f"  {wall['side']} @ ${wall['price']:,.0f} | ${wall['value_usd']:,.0f}")
