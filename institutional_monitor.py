"""
Institutional Activity Monitor

Detects suspicious market manipulation patterns:
- Spoofing (fake walls)
- Absorption (hidden orders)
- Stop hunting
- Coordinated liquidations
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from database import DatabaseManager
import logging

logger = logging.getLogger(__name__)


class InstitutionalMonitor:
    """
    Monitor for institutional and potentially manipulative activity.
    """
    
    def __init__(self, db: DatabaseManager):
        """
        Initialize monitor.
        
        Args:
            db: Database manager instance
        """
        self.db = db
        
    def detect_spoofing(self, symbol: str, lookback_seconds: int = 60) -> Optional[Dict]:
        """
        Detect spoofing: large orders that appear and disappear quickly.
        """
        try:
            query = """
            SELECT 
                price,
                size,
                value_usd,
                side,
                event_type,
                duration_seconds,
                timestamp
            FROM orderbook_walls
            WHERE symbol = %s
                AND timestamp > NOW() - INTERVAL '%s seconds'
                AND event_type = 'DETECTED'
            ORDER BY timestamp DESC
            LIMIT 20
            """
            
            try:
                self.db.cursor.execute(query, (symbol, lookback_seconds))
                walls = self.db.cursor.fetchall()
            except Exception as e:
                # Table might not exist or schema mismatch
                return None
            
            if not walls:
                return None
            
            spoofing_events = []
            
            for wall in walls:
                # Safe unpacking
                if len(wall) < 7:
                    continue
                    
                price, size, value_usd, side, event_type, duration, timestamp = wall
                
                check_query = """
                SELECT COUNT(*) FROM orderbook_walls
                WHERE symbol = %s
                    AND price = %s
                    AND side = %s
                    AND timestamp > %s
                    AND event_type = 'REMOVED'
                """
                
                self.db.cursor.execute(check_query, (symbol, price, side, timestamp))
                result = self.db.cursor.fetchone()
                removed_count = result[0] if result else 0
                
                if removed_count > 0 and duration and duration < 30:
                    spoofing_events.append({
                        'price': float(price),
                        'size': float(size),
                        'value_usd': float(value_usd),
                        'side': side,
                        'duration': duration,
                        'timestamp': timestamp
                    })
            
            if spoofing_events:
                return {
                    'detected': True,
                    'count': len(spoofing_events),
                    'events': spoofing_events[:3],
                    'total_value': sum(e['value_usd'] for e in spoofing_events)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting spoofing: {e}")
            return None
    
    def detect_stop_hunting(self, symbol: str) -> Optional[Dict]:
        """
        Detect stop hunting: price moves to liquidation zones then reverses.
        """
        try:
            query = """
            SELECT 
                side,
                price,
                value_usd,
                timestamp
            FROM liquidations
            WHERE symbol = %s
                AND timestamp > NOW() - INTERVAL '5 minutes'
            ORDER BY timestamp DESC
            """
            
            self.db.cursor.execute(query, (symbol,))
            recent_liqs = self.db.cursor.fetchall()
            
            if not recent_liqs or len(recent_liqs) < 5:
                return None
            
            timestamps = [liq[3] for liq in recent_liqs]
            
            clusters = []
            current_cluster = [recent_liqs[0]]
            
            for i in range(1, len(recent_liqs)):
                time_diff = (current_cluster[0][3] - recent_liqs[i][3]).total_seconds()
                
                if time_diff < 30:
                    current_cluster.append(recent_liqs[i])
                else:
                    if len(current_cluster) >= 3:
                        clusters.append(current_cluster)
                    current_cluster = [recent_liqs[i]]
            
            if len(current_cluster) >= 3:
                clusters.append(current_cluster)
            
            if clusters:
                largest_cluster = max(clusters, key=len)
                total_value = sum(float(liq[2]) for liq in largest_cluster)
                
                return {
                    'detected': True,
                    'liquidation_count': len(largest_cluster),
                    'total_value': total_value,
                    'timespan_seconds': (largest_cluster[0][3] - largest_cluster[-1][3]).total_seconds(),
                    'avg_price': sum(float(liq[1]) for liq in largest_cluster) / len(largest_cluster)
                }
            
            return None
            
        except Exception as e:
            # logger.error(f"Error detecting stop hunting: {e}") 
            # Suppress noisy errors for empty data
            return None
    
    def calculate_liquidation_velocity(self, symbol: str) -> Dict:
        """
        Calculate liquidation velocity over different timeframes.
        """
        try:
            timeframes = {
                '1min': 60,
                '5min': 300,
                '15min': 900,
                '1hour': 3600
            }
            
            velocity = {}
            
            for label, seconds in timeframes.items():
                query = """
                SELECT 
                    COUNT(*) as count,
                    COALESCE(SUM(value_usd), 0) as total_value,
                    COALESCE(AVG(value_usd), 0) as avg_value
                FROM liquidations
                WHERE symbol = %s
                    AND timestamp > NOW() - INTERVAL '%s seconds'
                """
                
                try:
                    self.db.cursor.execute(query, (symbol, seconds))
                    result = self.db.cursor.fetchone()
                    
                    if result:
                        velocity[label] = {
                            'count': result[0],
                            'total_value': float(result[1]),
                            'avg_value': float(result[2])
                        }
                    else:
                        velocity[label] = {'count': 0, 'total_value': 0, 'avg_value': 0}
                        
                except Exception:
                     velocity[label] = {'count': 0, 'total_value': 0, 'avg_value': 0}
            
            # Calculate acceleration
            acceleration = 'neutral'
            if velocity.get('1min', {}).get('total_value', 0) > 0:
                rate_1min = velocity['1min']['total_value'] / 60
                rate_5min = velocity['5min']['total_value'] / 300
                
                if rate_5min > 0:
                    if rate_1min > rate_5min * 2:
                        acceleration = 'accelerating'
                    elif rate_1min < rate_5min * 0.5:
                        acceleration = 'decelerating'
                else:
                    acceleration = 'accelerating'
            
            velocity['acceleration'] = acceleration
            
            return velocity
            
        except Exception as e:
            logger.error(f"Error calculating velocity: {e}")
            return {'error': str(e)}
    
    def detect_large_absorption(self, symbol: str) -> Optional[Dict]:
        """
        Detect large orders being absorbed (filled over time).
        """
        try:
            query = """
            SELECT 
                price,
                size,
                value_usd,
                side,
                duration_seconds
            FROM orderbook_walls
            WHERE symbol = %s
                AND timestamp > NOW() - INTERVAL '5 minutes'
                AND event_type = 'REMOVED'
                AND duration_seconds > 60
                AND value_usd > 1000000
            ORDER BY value_usd DESC
            LIMIT 5
            """
            
            try:
                self.db.cursor.execute(query, (symbol,))
                absorbed_walls = self.db.cursor.fetchall()
            except Exception:
                return None
            
            if absorbed_walls:
                # Safe checking
                if len(absorbed_walls[0]) < 5:
                    return None
                    
                return {
                    'detected': True,
                    'count': len(absorbed_walls),
                    'largest': {
                        'price': float(absorbed_walls[0][0]),
                        'size': float(absorbed_walls[0][1]),
                        'value_usd': float(absorbed_walls[0][2]),
                        'side': absorbed_walls[0][3],
                        'duration': absorbed_walls[0][4]
                    },
                    'total_absorbed': sum(float(w[2]) for w in absorbed_walls)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting absorption: {e}")
            return None
    
    def get_institutional_summary(self, symbol: str) -> Dict:
        """
        Get complete summary with error handling
        """
        return {
            'spoofing': self.detect_spoofing(symbol),
            'stop_hunting': self.detect_stop_hunting(symbol),
            'absorption': self.detect_large_absorption(symbol),
            'velocity': self.calculate_liquidation_velocity(symbol)
        }


if __name__ == "__main__":
    """Test institutional monitor."""
    
    logging.basicConfig(level=logging.INFO)
    
    db = DatabaseManager()
    monitor = InstitutionalMonitor(db)
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"INSTITUTIONAL ACTIVITY: {symbol}")
        print('='*60)
        
        summary = monitor.get_institutional_summary(symbol)
        
        # Velocity
        print("\n📊 Liquidation Velocity:")
        for timeframe, data in summary['velocity'].items():
            if timeframe != 'acceleration':
                print(f"  {timeframe}: ${data['total_value']:,.0f} ({data['count']} events)")
        print(f"  Trend: {summary['velocity'].get('acceleration', 'neutral').upper()}")
        
        # Spoofing
        if summary['spoofing']:
            print(f"\n⚠️ SPOOFING DETECTED:")
            print(f"  {summary['spoofing']['count']} fake walls (${summary['spoofing']['total_value']:,.0f})")
        
        # Stop Hunting
        if summary['stop_hunting']:
            print(f"\n🎯 STOP HUNTING DETECTED:")
            print(f"  {summary['stop_hunting']['liquidation_count']} liquidations in {summary['stop_hunting']['timespan_seconds']:.0f}s")
            print(f"  Total: ${summary['stop_hunting']['total_value']:,.0f}")
        
        # Absorption
        if summary['absorption']:
            print(f"\n🐋 LARGE ABSORPTION:")
            print(f"  ${summary['absorption']['total_absorbed']:,.0f} absorbed")
            print(f"  Largest: ${summary['absorption']['largest']['value_usd']:,.0f} {summary['absorption']['largest']['side']}")
    
    db.close()
