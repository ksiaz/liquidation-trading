"""
Market Impact Calculator

Calculates how much liquidation volume is needed to move price by a given percentage.
Uses order book depth and historical liquidation data.
"""

import requests
from typing import Dict, Optional
import logging
import time

logger = logging.getLogger(__name__)


class MarketImpactCalculator:
    """
    Calculates market impact of liquidations.
    
    Estimates how much volume is needed to move price by X%.
    """
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self):
        """Initialize calculator."""
        self.last_request_time = 0
        self.min_request_interval = 0.2  # 200ms between requests
    
    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def get_order_book_depth(self, symbol: str, limit: int = 500) -> Optional[Dict]:
        """
        Get order book depth from Binance.
        
        Args:
            symbol: Trading pair
            limit: Number of levels (max 1000)
        
        Returns:
            Dict with bids and asks
        """
        try:
            self._rate_limit()  # Enforce rate limiting
            url = f"{self.BASE_URL}/fapi/v1/depth"
            params = {'symbol': symbol, 'limit': limit}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            return {
                'bids': [[float(price), float(qty)] for price, qty in data['bids']],
                'asks': [[float(price), float(qty)] for price, qty in data['asks']]
            }
            
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {e}")
            return None
    
    def calculate_impact_for_move(self, symbol: str, target_move_pct: float = 1.0) -> Dict:
        """
        Calculate how much volume is needed to move price by target %.
        
        Args:
            symbol: Trading pair
            target_move_pct: Target price move percentage (default 1%)
        
        Returns:
            Dict with impact analysis
        """
        order_book = self.get_order_book_depth(symbol)
        if not order_book:
            return {'error': 'Could not fetch order book'}
        
        bids = order_book['bids']
        asks = order_book['asks']
        
        if not bids or not asks:
            return {'error': 'Empty order book'}
        
        current_price = (bids[0][0] + asks[0][0]) / 2
        
        # Calculate for downward move (long liquidations)
        target_price_down = current_price * (1 - target_move_pct / 100)
        volume_needed_down = self._calculate_volume_to_price(bids, target_price_down, 'down')
        
        # Calculate for upward move (short liquidations)
        target_price_up = current_price * (1 + target_move_pct / 100)
        volume_needed_up = self._calculate_volume_to_price(asks, target_price_up, 'up')
        
        # Calculate value in USD
        value_down_usd = volume_needed_down * current_price
        value_up_usd = volume_needed_up * current_price
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'target_move_pct': target_move_pct,
            'target_price_down': target_price_down,
            'target_price_up': target_price_up,
            'volume_needed_down': volume_needed_down,
            'volume_needed_up': volume_needed_up,
            'value_down_usd': value_down_usd,
            'value_up_usd': value_up_usd,
            'avg_value_usd': (value_down_usd + value_up_usd) / 2,
            'liquidity_asymmetry': abs(value_down_usd - value_up_usd) / max(value_down_usd, value_up_usd)
        }
    
    def _calculate_volume_to_price(self, levels: list, target_price: float, direction: str) -> float:
        """
        Calculate volume needed to reach target price.
        
        Args:
            levels: Order book levels [[price, qty], ...]
            target_price: Target price to reach
            direction: 'up' or 'down'
        
        Returns:
            Total volume needed
        """
        total_volume = 0
        
        for price, qty in levels:
            if direction == 'down':
                if price <= target_price:
                    break
                total_volume += qty
            else:  # up
                if price >= target_price:
                    break
                total_volume += qty
        
        return total_volume
    
    def get_impact_levels(self, symbol: str) -> Dict:
        """
        Get impact levels for common move sizes.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with impact for 0.5%, 1%, 2%, 5% moves
        """
        move_sizes = [0.5, 1.0, 2.0, 5.0]
        results = {}
        
        for move_pct in move_sizes:
            impact = self.calculate_impact_for_move(symbol, move_pct)
            if 'error' not in impact:
                results[f"{move_pct}%"] = {
                    'down_usd': impact['value_down_usd'],
                    'up_usd': impact['value_up_usd'],
                    'avg_usd': impact['avg_value_usd']
                }
        
        return results


if __name__ == "__main__":
    """Test market impact calculator."""
    
    import logging
    logging.basicConfig(level=logging.INFO)
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    calculator = MarketImpactCalculator()
    
    print("=" * 80)
    print("MARKET IMPACT ANALYSIS")
    print("=" * 80)
    print("\nHow much liquidation volume needed to move price?\n")
    
    for symbol in symbols:
        print(f"\n{symbol}")
        print("-" * 80)
        
        # Get 1% move impact
        impact = calculator.calculate_impact_for_move(symbol, 1.0)
        
        if 'error' in impact:
            print(f"Error: {impact['error']}")
            continue
        
        print(f"Current Price:     ${impact['current_price']:,.2f}")
        print(f"\nTo move price DOWN by 1% (to ${impact['target_price_down']:,.2f}):")
        print(f"  Volume needed:   {impact['volume_needed_down']:,.2f} contracts")
        print(f"  Value needed:    ${impact['value_down_usd']:,.0f}")
        
        print(f"\nTo move price UP by 1% (to ${impact['target_price_up']:,.2f}):")
        print(f"  Volume needed:   {impact['volume_needed_up']:,.2f} contracts")
        print(f"  Value needed:    ${impact['value_up_usd']:,.0f}")
        
        print(f"\nAverage:           ${impact['avg_value_usd']:,.0f}")
        
        # Liquidity asymmetry
        if impact['liquidity_asymmetry'] > 0.2:
            direction = "DOWN" if impact['value_down_usd'] < impact['value_up_usd'] else "UP"
            print(f"⚠️  Liquidity imbalance: Easier to move {direction}")
        
        # Get multiple levels
        print(f"\nImpact for different move sizes:")
        levels = calculator.get_impact_levels(symbol)
        for move, data in levels.items():
            print(f"  {move:>5} move: ${data['avg_usd']:>12,.0f}")
    
    print("\n" + "=" * 80)
