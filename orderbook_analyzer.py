"""
Order Book Analyzer

Analyzes order book data for trading signals:
- Imbalance calculation
- Liquidity cliff detection
- Large order/wall tracking
- Spread monitoring
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OrderBookAnalyzer:
    """
    Analyzes order book data for trading insights.
    """
    
    def __init__(self, large_order_threshold_usd: float = 500000):
        """
        Initialize analyzer.
        
        Args:
            large_order_threshold_usd: Minimum size for "large" orders
        """
        self.large_order_threshold = large_order_threshold_usd
        
        # Order Flow Imbalance tracking
        self.prev_orderbook = None
        self.ofi_history = []  # Store recent OFI values
    
    def calculate_imbalance(self, orderbook: Dict, depth_levels: int = 10) -> float:
        """
        Calculate bid/ask imbalance.
        
        Positive = more bids (buying pressure)
        Negative = more asks (selling pressure)
        
        Args:
            orderbook: Order book data
            depth_levels: Number of levels to analyze
        
        Returns:
            Imbalance ratio (-1 to 1)
        """
        if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
            return 0.0
        
        bids = orderbook['bids'][:depth_levels]
        asks = orderbook['asks'][:depth_levels]
        
        bid_volume = sum(qty for price, qty in bids)
        ask_volume = sum(qty for price, qty in asks)
        
        if bid_volume + ask_volume == 0:
            return 0.0
        
        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        return imbalance
    
    def calculate_order_flow_imbalance(self, orderbook: Dict, levels: int = 5) -> float:
        """
        Calculate Order Flow Imbalance (OFI) - predicts short-term price movements.
        
        OFI = Δ(bid_volume) - Δ(ask_volume)
        Positive = buying pressure, Negative = selling pressure
        
        Args:
            orderbook: Current order book data
            levels: Number of levels to analyze (default: 5)
            
        Returns:
            OFI value (positive = bullish, negative = bearish)
        """
        if self.prev_orderbook is None:
            self.prev_orderbook = orderbook
            return 0.0
        
        try:
            # Calculate bid volume change
            prev_bid_vol = sum(float(qty) for _, qty in self.prev_orderbook.get('bids', [])[:levels])
            curr_bid_vol = sum(float(qty) for _, qty in orderbook.get('bids', [])[:levels])
            delta_bid = curr_bid_vol - prev_bid_vol
            
            # Calculate ask volume change
            prev_ask_vol = sum(float(qty) for _, qty in self.prev_orderbook.get('asks', [])[:levels])
            curr_ask_vol = sum(float(qty) for _, qty in orderbook.get('asks', [])[:levels])
            delta_ask = curr_ask_vol - prev_ask_vol
            
            # OFI = change in bids - change in asks
            ofi = delta_bid - delta_ask
            
            # Store for history
            self.ofi_history.append(ofi)
            if len(self.ofi_history) > 100:
                self.ofi_history.pop(0)
            
            # Update previous orderbook
            self.prev_orderbook = orderbook
            
            return ofi
            
        except Exception as e:
            logger.error(f"Error calculating OFI: {e}")
            return 0.0
    
    def calculate_weighted_imbalance(self, orderbook: Dict, max_levels: int = 20) -> float:
        """
        Calculate weighted imbalance across deep orderbook levels.
        
        Gives more weight to levels closer to mid-price.
        Better predictor than simple top-of-book imbalance.
        
        Args:
            orderbook: Order book data
            max_levels: Maximum levels to analyze (default: 20)
            
        Returns:
            Weighted imbalance from -1 (strong sell) to +1 (strong buy)
        """
        try:
            bids = orderbook.get('bids', [])[:max_levels]
            asks = orderbook.get('asks', [])[:max_levels]
            
            if not bids or not asks:
                return 0.0
            
            # Calculate mid price
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid_price = (best_bid + best_ask) / 2
            
            # Calculate weighted bid pressure
            bid_pressure = 0
            for price, qty in bids:
                price = float(price)
                qty = float(qty)
                distance = abs(price - mid_price) / mid_price
                weight = 1 / (1 + distance * 100)  # Closer = higher weight
                bid_pressure += qty * weight
            
            # Calculate weighted ask pressure
            ask_pressure = 0
            for price, qty in asks:
                price = float(price)
                qty = float(qty)
                distance = abs(price - mid_price) / mid_price
                weight = 1 / (1 + distance * 100)
                ask_pressure += qty * weight
            
            # Calculate imbalance (-1 to +1)
            total_pressure = bid_pressure + ask_pressure
            if total_pressure == 0:
                return 0.0
            
            return (bid_pressure - ask_pressure) / total_pressure
            
        except Exception as e:
            logger.error(f"Error calculating weighted imbalance: {e}")
            return 0.0
    
    def calculate_volumes(self, orderbook: Dict, depth_levels: int = 10) -> Dict:
        """
        Calculate bid/ask volumes and values.
        
        Args:
            orderbook: Order book data
            depth_levels: Number of levels
        
        Returns:
            Dict with volumes and values
        """
        if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
            return {
                'bid_volume': 0,
                'ask_volume': 0,
                'bid_value': 0,
                'ask_value': 0
            }
        
        bids = orderbook['bids'][:depth_levels]
        asks = orderbook['asks'][:depth_levels]
        
        bid_volume = sum(qty for price, qty in bids)
        ask_volume = sum(qty for price, qty in asks)
        
        bid_value = sum(price * qty for price, qty in bids)
        ask_value = sum(price * qty for price, qty in asks)
        
        return {
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
            'bid_value': bid_value,
            'ask_value': ask_value
        }
    
    def detect_liquidity_cliffs(self, orderbook: Dict, current_price: float, 
                                 threshold_pct: float = 50) -> List[Dict]:
        """
        Detect price levels with abnormally low liquidity.
        
        Args:
            orderbook: Order book data
            current_price: Current market price
            threshold_pct: % below average to consider a cliff
        
        Returns:
            List of cliff dictionaries
        """
        if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
            return []
        
        cliffs = []
        
        # Analyze bids (support levels)
        bids = orderbook['bids']
        if len(bids) > 5:
            avg_bid_qty = sum(qty for _, qty in bids) / len(bids)
            
            for price, qty in bids:
                if qty < avg_bid_qty * (threshold_pct / 100):
                    distance_pct = abs(price - current_price) / current_price * 100
                    cliffs.append({
                        'side': 'bid',
                        'price': price,
                        'quantity': qty,
                        'avg_quantity': avg_bid_qty,
                        'gap_pct': (avg_bid_qty - qty) / avg_bid_qty * 100,
                        'distance_from_price_pct': distance_pct
                    })
        
        # Analyze asks (resistance levels)
        asks = orderbook['asks']
        if len(asks) > 5:
            avg_ask_qty = sum(qty for _, qty in asks) / len(asks)
            
            for price, qty in asks:
                if qty < avg_ask_qty * (threshold_pct / 100):
                    distance_pct = abs(price - current_price) / current_price * 100
                    cliffs.append({
                        'side': 'ask',
                        'price': price,
                        'quantity': qty,
                        'avg_quantity': avg_ask_qty,
                        'gap_pct': (avg_ask_qty - qty) / avg_ask_qty * 100,
                        'distance_from_price_pct': distance_pct
                    })
        
        # Sort by distance from current price
        cliffs.sort(key=lambda x: x['distance_from_price_pct'])
        
        return cliffs
    
    def detect_large_orders(self, orderbook: Dict, current_price: float) -> List[Dict]:
        """
        Detect large orders (walls) in the order book.
        
        Args:
            orderbook: Order book data
            current_price: Current market price
        
        Returns:
            List of large order dictionaries
        """
        if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
            return []
        
        large_orders = []
        
        # Check bids
        for price, qty in orderbook['bids']:
            value_usd = price * qty
            if value_usd >= self.large_order_threshold:
                distance_pct = abs(price - current_price) / current_price * 100
                large_orders.append({
                    'side': 'bid',
                    'price': price,
                    'size': qty,
                    'value_usd': value_usd,
                    'distance_pct': distance_pct,
                    'type': 'support_wall'
                })
        
        # Check asks
        for price, qty in orderbook['asks']:
            value_usd = price * qty
            if value_usd >= self.large_order_threshold:
                distance_pct = abs(price - current_price) / current_price * 100
                large_orders.append({
                    'side': 'ask',
                    'price': price,
                    'size': qty,
                    'value_usd': value_usd,
                    'distance_pct': distance_pct,
                    'type': 'resistance_wall'
                })
        
        # Sort by size
        large_orders.sort(key=lambda x: x['value_usd'], reverse=True)
        
        return large_orders
    
    def calculate_liquidity_at_distance(self, orderbook: Dict, current_price: float,
                                         distance_pct: float, side: str = 'both') -> Dict:
        """
        Calculate available liquidity at a % distance from current price.
        
        Args:
            orderbook: Order book data
            current_price: Current market price
            distance_pct: Distance in % (e.g., 1.0 for 1%)
            side: 'bid', 'ask', or 'both'
        
        Returns:
            Dict with liquidity info
        """
        if not orderbook:
            return {'bid_liquidity': 0, 'ask_liquidity': 0}
        
        result = {}
        
        if side in ['bid', 'both']:
            target_price = current_price * (1 - distance_pct / 100)
            bid_liquidity = sum(
                qty for price, qty in orderbook.get('bids', [])
                if price >= target_price
            )
            result['bid_liquidity'] = bid_liquidity
        
        if side in ['ask', 'both']:
            target_price = current_price * (1 + distance_pct / 100)
            ask_liquidity = sum(
                qty for price, qty in orderbook.get('asks', [])
                if price <= target_price
            )
            result['ask_liquidity'] = ask_liquidity
        
        return result
    
    def analyze_spread(self, orderbook: Dict) -> Optional[Dict]:
        """
        Analyze bid-ask spread.
        
        Args:
            orderbook: Order book data
        
        Returns:
            Spread analysis dict
        """
        if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
            return None
        
        best_bid = orderbook['bids'][0][0]
        best_ask = orderbook['asks'][0][0]
        
        spread = best_ask - best_bid
        spread_pct = (spread / best_bid) * 100
        mid_price = (best_bid + best_ask) / 2
        
        return {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread': spread,
            'spread_pct': spread_pct,
            'mid_price': mid_price
        }
    
    def generate_snapshot_metrics(self, orderbook: Dict, symbol: str, 
                                   current_price: float) -> Dict:
        """
        Generate complete snapshot metrics for database storage.
        
        Args:
            orderbook: Order book data
            symbol: Trading pair
            current_price: Current market price
        
        Returns:
            Dict with all metrics
        """
        spread_data = self.analyze_spread(orderbook)
        volumes = self.calculate_volumes(orderbook, depth_levels=10)
        imbalance = self.calculate_imbalance(orderbook, depth_levels=10)
        
        return {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'best_bid': spread_data['best_bid'] if spread_data else None,
            'best_ask': spread_data['best_ask'] if spread_data else None,
            'spread': spread_data['spread'] if spread_data else None,
            'spread_pct': spread_data['spread_pct'] if spread_data else None,
            'bid_volume_10': volumes['bid_volume'],
            'ask_volume_10': volumes['ask_volume'],
            'bid_value_10': volumes['bid_value'],
            'ask_value_10': volumes['ask_value'],
            'imbalance': imbalance
        }


if __name__ == "__main__":
    """Test the analyzer."""
    
    logging.basicConfig(level=logging.INFO)
    
    # Sample order book
    sample_orderbook = {
        'bids': [
            [87000.00, 2.5],
            [86999.00, 1.8],
            [86998.00, 3.2],
            [86997.00, 1.5],
            [86996.00, 2.1],
            [86995.00, 0.5],  # Liquidity cliff
            [86994.00, 2.8],
            [86993.00, 1.9],
            [86992.00, 2.3],
            [86991.00, 1.7],
        ],
        'asks': [
            [87001.00, 3.2],
            [87002.00, 2.1],
            [87003.00, 1.9],
            [87004.00, 2.5],
            [87005.00, 1.6],
            [87006.00, 50.0],  # Large wall
            [87007.00, 2.2],
            [87008.00, 1.8],
            [87009.00, 2.4],
            [87010.00, 1.5],
        ]
    }
    
    analyzer = OrderBookAnalyzer(large_order_threshold_usd=500000)
    current_price = 87000.50
    
    print("=" * 60)
    print("ORDER BOOK ANALYZER TEST")
    print("=" * 60)
    
    # Imbalance
    imbalance = analyzer.calculate_imbalance(sample_orderbook)
    print(f"\nImbalance: {imbalance:.4f}")
    if imbalance > 0.2:
        print("  → Strong buying pressure")
    elif imbalance < -0.2:
        print("  → Strong selling pressure")
    else:
        print("  → Balanced")
    
    # Spread
    spread = analyzer.analyze_spread(sample_orderbook)
    print(f"\nSpread: ${spread['spread']:.2f} ({spread['spread_pct']:.4f}%)")
    
    # Liquidity cliffs
    cliffs = analyzer.detect_liquidity_cliffs(sample_orderbook, current_price)
    print(f"\nLiquidity Cliffs: {len(cliffs)}")
    for cliff in cliffs[:3]:
        print(f"  {cliff['side'].upper()} at ${cliff['price']:,.2f} - {cliff['gap_pct']:.1f}% below average")
    
    # Large orders
    large_orders = analyzer.detect_large_orders(sample_orderbook, current_price)
    print(f"\nLarge Orders: {len(large_orders)}")
    for order in large_orders:
        print(f"  {order['type'].upper()}: ${order['value_usd']:,.0f} at ${order['price']:,.2f}")
    
    # Liquidity at distances
    liq_1pct = analyzer.calculate_liquidity_at_distance(sample_orderbook, current_price, 1.0)
    print(f"\nLiquidity within 1%:")
    print(f"  Bids: {liq_1pct.get('bid_liquidity', 0):.2f} BTC")
    print(f"  Asks: {liq_1pct.get('ask_liquidity', 0):.2f} BTC")
    
    print("\n" + "=" * 60)
