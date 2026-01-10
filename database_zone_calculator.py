"""
Database-based Liquidation Zone Calculator

Calculates liquidation zones from stored database liquidations
instead of relying on live API calls.
"""
from database import DatabaseManager
from datetime import datetime, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class DatabaseZoneCalculator:
    """Calculate liquidation zones from database history."""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        
    def get_recent_liquidations(self, symbol: str, minutes: int = 60) -> List[Dict]:
        """Get recent liquidations from database."""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            
            query = """
            SELECT symbol, side, price, quantity, value_usd, timestamp, exchange
            FROM liquidations
            WHERE symbol = %s AND timestamp >= %s
            ORDER BY timestamp DESC
            LIMIT 1000
            """
            
            self.db.cursor.execute(query, (symbol, cutoff_time))
            rows = self.db.cursor.fetchall()
            
            liquidations = []
            for row in rows:
                liquidations.append({
                    'symbol': row[0],
                    'side': row[1],
                    'price': float(row[2]),
                    'quantity': float(row[3]),
                    'value_usd': float(row[4]),
                    'timestamp': row[5],
                    'exchange': row[6]
                })
            
            return liquidations
            
        except Exception as e:
            logger.error(f"Error fetching liquidations: {e}")
            return []
    
    def calculate_zones_from_history(self, symbol: str) -> Dict:
        """Calculate liquidation zones from recent history."""
        try:
            liquidations = self.get_recent_liquidations(symbol, minutes=60)
            
            if not liquidations:
                return {
                    'zones': [],
                    'risk': {
                        'current_price': 0,
                        'long_risk': 0,
                        'short_risk': 0
                    }
                }
            
            # Calculate current price (average of recent liquidations)
            recent_prices = [liq['price'] for liq in liquidations[:10]]
            current_price = sum(recent_prices) / len(recent_prices) if recent_prices else 0
            
            # Aggregate liquidations by price level (1% buckets)
            price_buckets = {}
            
            for liq in liquidations:
                # Round to 1% bucket
                bucket_pct = round((liq['price'] / current_price - 1) * 100)
                bucket_key = f"{liq['side']}_{bucket_pct}"
                
                if bucket_key not in price_buckets:
                    price_buckets[bucket_key] = {
                        'side': liq['side'],
                        'price': liq['price'],
                        'total_value': 0,
                        'count': 0,
                        'distance_pct': bucket_pct
                    }
                
                price_buckets[bucket_key]['total_value'] += liq['value_usd']
                price_buckets[bucket_key]['count'] += 1
            
            # Convert to zones format
            zones = []
            for bucket in price_buckets.values():
                if bucket['total_value'] > 10000:  # Min $10k
                    zones.append({
                        'type': bucket['side'],
                        'liquidation_price': bucket['price'],
                        'value_usd': bucket['total_value'],
                        'leverage': 20,  # Estimated average
                        'distance_pct': abs(bucket['distance_pct']),
                        'timestamp': datetime.now()
                    })
            
            # Sort by distance from current price
            zones.sort(key=lambda x: x['distance_pct'])
            
            # Calculate risk metrics
            long_value = sum(z['value_usd'] for z in zones if z['type'] == 'LONG')
            short_value = sum(z['value_usd'] for z in zones if z['type'] == 'SHORT')
            
            return {
                'zones': zones[:20],  # Top 20 zones
                'risk': {
                    'current_price': current_price,
                    'long_risk': long_value,
                    'short_risk': short_value,
                    'total_liquidations': len(liquidations),
                    'data_source': 'database'
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating zones: {e}")
            return {
                'zones': [],
                'risk': {
                    'current_price': 0,
                    'long_risk': 0,
                    'short_risk': 0,
                    'error': str(e)
                }
            }
