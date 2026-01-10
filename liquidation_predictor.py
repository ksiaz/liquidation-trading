"""
Liquidation Prediction Module

Predicts where future liquidations will occur by analyzing:
- Open interest data
- Funding rates (long/short imbalance)
- Current price levels
- Common leverage ratios

This helps identify price levels where cascading liquidations are likely.
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import time

logger = logging.getLogger(__name__)


class LiquidationPredictor:
    """
    Predicts liquidation zones based on market data.
    
    Uses Binance Futures API to fetch:
    - Open interest
    - Funding rates
    - Current prices
    """
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self, symbols: List[str]):
        """
        Initialize predictor.
        
        Args:
            symbols: List of symbols to monitor (e.g., ['BTCUSDT', 'ETHUSDT'])
        """
        self.symbols = symbols
        self.cache = {}
        self.cache_duration = 60  # Cache data for 60 seconds
        self.last_request_time = 0
        self.min_request_interval = 0.2  # 200ms between requests (max 5 req/sec)
    
    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current mark price for a symbol.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        
        Returns:
            Current price or None if error
        """
        try:
            self._rate_limit()  # Enforce rate limiting
            url = f"{self.BASE_URL}/fapi/v1/premiumIndex"
            params = {'symbol': symbol}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            return float(data['markPrice'])
            
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """
        Get current funding rate.
        
        Positive = longs paying shorts (too many longs)
        Negative = shorts paying longs (too many shorts)
        
        Args:
            symbol: Trading pair
        
        Returns:
            Funding rate as decimal (e.g., 0.0001 = 0.01%)
        """
        try:
            self._rate_limit()  # Enforce rate limiting
            url = f"{self.BASE_URL}/fapi/v1/premiumIndex"
            params = {'symbol': symbol}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            return float(data['lastFundingRate'])
            
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return None
    
    def get_open_interest(self, symbol: str) -> Optional[Dict]:
        """
        Get open interest data.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with open interest value and sum
        """
        try:
            self._rate_limit()  # Enforce rate limiting
            url = f"{self.BASE_URL}/fapi/v1/openInterest"
            params = {'symbol': symbol}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            return {
                'open_interest': float(data['openInterest']),
                'timestamp': datetime.fromtimestamp(int(data['time']) / 1000)
            }
            
        except Exception as e:
            logger.error(f"Error fetching open interest for {symbol}: {e}")
            return None
    
    def estimate_liquidation_zones(self, symbol: str) -> List[Dict]:
        """
        Estimate price levels where liquidations are likely to occur.
        
        Calculates liquidation prices for common leverage levels:
        - 10x, 20x, 50x, 100x
        
        Args:
            symbol: Trading pair
        
        Returns:
            List of liquidation zone dictionaries
        """
        current_price = self.get_current_price(symbol)
        if not current_price:
            return []
        
        funding_rate = self.get_funding_rate(symbol)
        open_interest = self.get_open_interest(symbol)
        
        zones = []
        
        # Common leverage levels on Binance
        leverage_levels = [10, 20, 50, 100, 125]
        
        for leverage in leverage_levels:
            # Calculate liquidation distance
            # For longs: liquidation_price = entry_price * (1 - 1/leverage)
            # For shorts: liquidation_price = entry_price * (1 + 1/leverage)
            
            liquidation_distance_pct = (1 / leverage) * 100
            liquidation_distance = current_price / leverage
            
            # Long liquidation zone (price drops)
            long_liq_price = current_price - liquidation_distance
            zones.append({
                'symbol': symbol,
                'type': 'LONG',
                'leverage': leverage,
                'liquidation_price': long_liq_price,
                'current_price': current_price,
                'distance_usd': liquidation_distance,
                'distance_pct': liquidation_distance_pct,
                'funding_rate': funding_rate,
                'open_interest': open_interest.get('open_interest') if open_interest else None,
                'timestamp': datetime.now()
            })
            
            # Short liquidation zone (price rises)
            short_liq_price = current_price + liquidation_distance
            zones.append({
                'symbol': symbol,
                'type': 'SHORT',
                'leverage': leverage,
                'liquidation_price': short_liq_price,
                'current_price': current_price,
                'distance_usd': liquidation_distance,
                'distance_pct': liquidation_distance_pct,
                'funding_rate': funding_rate,
                'open_interest': open_interest.get('open_interest') if open_interest else None,
                'timestamp': datetime.now()
            })
        
        return zones
    
    def get_danger_zones(self, symbol: str, threshold_pct: float = 2.0) -> List[Dict]:
        """
        Get liquidation zones that are close to current price (danger zones).
        
        Args:
            symbol: Trading pair
            threshold_pct: Consider zones within this % as dangerous
        
        Returns:
            List of nearby liquidation zones
        """
        all_zones = self.estimate_liquidation_zones(symbol)
        
        # Filter zones within threshold
        danger_zones = [
            zone for zone in all_zones
            if zone['distance_pct'] <= threshold_pct
        ]
        
        return danger_zones
    
    def analyze_liquidation_risk(self, symbol: str) -> Dict:
        """
        Comprehensive liquidation risk analysis.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with risk assessment
        """
        current_price = self.get_current_price(symbol)
        funding_rate = self.get_funding_rate(symbol)
        open_interest = self.get_open_interest(symbol)
        
        if not current_price:
            return {'error': 'Could not fetch price'}
        
        # Determine market bias from funding rate
        if funding_rate is None:
            market_bias = 'UNKNOWN'
            bias_strength = 0
        elif funding_rate > 0.0001:  # 0.01%
            market_bias = 'LONG_HEAVY'
            bias_strength = min(funding_rate / 0.001, 1.0)  # Normalize to 0-1
        elif funding_rate < -0.0001:
            market_bias = 'SHORT_HEAVY'
            bias_strength = min(abs(funding_rate) / 0.001, 1.0)
        else:
            market_bias = 'BALANCED'
            bias_strength = 0
        
        # Get danger zones
        danger_zones = self.get_danger_zones(symbol, threshold_pct=3.0)
        
        # Count zones by type
        long_zones = [z for z in danger_zones if z['type'] == 'LONG']
        short_zones = [z for z in danger_zones if z['type'] == 'SHORT']
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'funding_rate': funding_rate,
            'funding_rate_pct': funding_rate * 100 if funding_rate else None,
            'market_bias': market_bias,
            'bias_strength': bias_strength,
            'open_interest': open_interest.get('open_interest') if open_interest else None,
            'danger_zones_count': len(danger_zones),
            'long_liquidation_zones': len(long_zones),
            'short_liquidation_zones': len(short_zones),
            'nearest_long_liq': long_zones[0]['liquidation_price'] if long_zones else None,
            'nearest_short_liq': short_zones[0]['liquidation_price'] if short_zones else None,
            'timestamp': datetime.now()
        }
    
    def predict_cascade_direction(self, symbol: str) -> Optional[str]:
        """
        Predict which direction is more likely to cascade.
        
        Based on:
        - Funding rate (shows imbalance)
        - Recent liquidation patterns
        
        Args:
            symbol: Trading pair
        
        Returns:
            'LONG' (longs will cascade), 'SHORT' (shorts will cascade), or None
        """
        funding_rate = self.get_funding_rate(symbol)
        
        if funding_rate is None:
            return None
        
        # High positive funding = too many longs = long cascade risk
        if funding_rate > 0.0002:  # 0.02%
            return 'LONG'
        
        # High negative funding = too many shorts = short cascade risk
        elif funding_rate < -0.0002:
            return 'SHORT'
        
        return None
    
    def detect_liquidation_clusters(self, symbol: str, price_range_pct: float = 1.0) -> Dict:
        """
        Detect clusters of liquidation zones within a price range.
        
        A cluster indicates multiple leverage levels will be liquidated
        in a small price move, potentially causing a cascade.
        
        Args:
            symbol: Trading pair
            price_range_pct: Price range to check for clusters (default 1%)
        
        Returns:
            Dict with cluster information
        """
        current_price = self.get_current_price(symbol)
        if not current_price:
            return {'has_clusters': False}
        
        zones = self.estimate_liquidation_zones(symbol)
        
        # Separate by type
        long_zones = [z for z in zones if z['type'] == 'LONG']
        short_zones = [z for z in zones if z['type'] == 'SHORT']
        
        # Check for long clusters (price dropping)
        long_clusters = []
        price_threshold = current_price * (price_range_pct / 100)
        
        for i, zone in enumerate(long_zones):
            # Count how many zones are within price_range_pct of this zone
            cluster_zones = [
                z for z in long_zones
                if abs(z['liquidation_price'] - zone['liquidation_price']) <= price_threshold
            ]
            
            if len(cluster_zones) >= 3:  # 3+ zones = cluster
                distance_pct = ((current_price - zone['liquidation_price']) / current_price) * 100
                long_clusters.append({
                    'center_price': zone['liquidation_price'],
                    'zone_count': len(cluster_zones),
                    'distance_pct': distance_pct,
                    'leverages': [z['leverage'] for z in cluster_zones]
                })
        
        # Check for short clusters (price rising)
        short_clusters = []
        for i, zone in enumerate(short_zones):
            cluster_zones = [
                z for z in short_zones
                if abs(z['liquidation_price'] - zone['liquidation_price']) <= price_threshold
            ]
            
            if len(cluster_zones) >= 3:
                distance_pct = ((zone['liquidation_price'] - current_price) / current_price) * 100
                short_clusters.append({
                    'center_price': zone['liquidation_price'],
                    'zone_count': len(cluster_zones),
                    'distance_pct': distance_pct,
                    'leverages': [z['leverage'] for z in cluster_zones]
                })
        
        # Remove duplicates (same center price)
        long_clusters = list({c['center_price']: c for c in long_clusters}.values())
        short_clusters = list({c['center_price']: c for c in short_clusters}.values())
        
        # Sort by distance
        long_clusters.sort(key=lambda x: x['distance_pct'])
        short_clusters.sort(key=lambda x: x['distance_pct'])
        
        return {
            'has_clusters': len(long_clusters) > 0 or len(short_clusters) > 0,
            'long_clusters': long_clusters,
            'short_clusters': short_clusters,
            'total_clusters': len(long_clusters) + len(short_clusters),
            'nearest_cluster': (
                long_clusters[0] if long_clusters and long_clusters[0]['distance_pct'] < 5
                else short_clusters[0] if short_clusters and short_clusters[0]['distance_pct'] < 5
                else None
            )
        }


if __name__ == "__main__":
    """Test the liquidation predictor."""
    
    logging.basicConfig(level=logging.INFO)
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    predictor = LiquidationPredictor(symbols)
    
    print("=" * 60)
    print("LIQUIDATION RISK ANALYSIS")
    print("=" * 60)
    
    for symbol in symbols:
        print(f"\n{symbol}")
        print("-" * 60)
        
        # Get risk analysis
        risk = predictor.analyze_liquidation_risk(symbol)
        
        if 'error' in risk:
            print(f"Error: {risk['error']}")
            continue
        
        print(f"Current Price:     ${risk['current_price']:,.2f}")
        print(f"Funding Rate:      {risk['funding_rate_pct']:.4f}%")
        print(f"Market Bias:       {risk['market_bias']}")
        print(f"Open Interest:     {risk['open_interest']:,.0f}" if risk['open_interest'] else "Open Interest:     N/A")
        print(f"Danger Zones:      {risk['danger_zones_count']}")
        
        if risk['nearest_long_liq']:
            distance = ((risk['current_price'] - risk['nearest_long_liq']) / risk['current_price']) * 100
            print(f"Nearest Long Liq:  ${risk['nearest_long_liq']:,.2f} ({distance:.2f}% below)")
        
        if risk['nearest_short_liq']:
            distance = ((risk['nearest_short_liq'] - risk['current_price']) / risk['current_price']) * 100
            print(f"Nearest Short Liq: ${risk['nearest_short_liq']:,.2f} ({distance:.2f}% above)")
        
        # Predict cascade
        cascade = predictor.predict_cascade_direction(symbol)
        if cascade:
            print(f"\n⚠️  {cascade} CASCADE RISK")
    
    print("\n" + "=" * 60)
