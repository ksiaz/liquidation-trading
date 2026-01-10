"""
Verification script for multi-symbol signal generation system
"""
import psycopg2
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

load_dotenv()

def check_database():
    """Check database state for signal generation"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'liquidation_trading'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )
        cursor = conn.cursor()
        
        print("=" * 80)
        print("DATABASE VERIFICATION")
        print("=" * 80)
        
        # Check if trading_signals table exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'trading_signals'
        """)
        
        if cursor.fetchone():
            print("✓ trading_signals table exists")
        else:
            print("✗ trading_signals table NOT FOUND")
            return
        
        # Check signal counts by symbol
        print("\n" + "-" * 80)
        print("SIGNAL COUNTS BY SYMBOL")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                symbol, 
                COUNT(*) as signal_count,
                MAX(timestamp) as latest_signal,
                MIN(timestamp) as earliest_signal
            FROM trading_signals 
            GROUP BY symbol 
            ORDER BY symbol
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                symbol, count, latest, earliest = row
                print(f"\n{symbol}:")
                print(f"  Total Signals: {count}")
                print(f"  Latest Signal: {latest}")
                print(f"  Earliest Signal: {earliest}")
        else:
            print("No signals found in database yet")
        
        # Check recent signals (last 10)
        print("\n" + "-" * 80)
        print("RECENT SIGNALS (Last 10)")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                timestamp,
                symbol,
                direction,
                entry_price,
                confidence,
                snr,
                timeframe
            FROM trading_signals 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        
        recent = cursor.fetchall()
        if recent:
            for row in recent:
                ts, sym, dir, price, conf, snr, tf = row
                print(f"\n{ts} | {sym} | {dir} | ${price:.2f} | Conf:{conf:.1f}% | SNR:{snr:.2f} | TF:{tf}s")
        else:
            print("No recent signals found")
        
        # Check signal distribution in last hour
        print("\n" + "-" * 80)
        print("SIGNALS IN LAST HOUR")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                symbol,
                direction,
                COUNT(*) as count
            FROM trading_signals 
            WHERE timestamp > NOW() - INTERVAL '1 hour'
            GROUP BY symbol, direction
            ORDER BY symbol, direction
        """)
        
        last_hour = cursor.fetchall()
        if last_hour:
            for row in last_hour:
                sym, dir, count = row
                print(f"{sym} {dir}: {count} signals")
        else:
            print("No signals in the last hour")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        print("DATABASE CHECK COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"✗ Database error: {e}")

def check_api_endpoints():
    """Check API endpoints for signal retrieval"""
    import requests
    
    print("\n" + "=" * 80)
    print("API ENDPOINT VERIFICATION")
    print("=" * 80)
    
    base_url = "http://localhost:5000"
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    for symbol in symbols:
        try:
            response = requests.get(f"{base_url}/api/trading_signals?symbol={symbol}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"\n✓ {symbol} endpoint working")
                
                # Handle both response formats (dict with 'signals' key or direct list)
                if isinstance(data, dict):
                    signals = data.get('signals', [])
                    stats = data.get('stats', {})
                    print(f"  Returned {len(signals)} signals")
                    
                    if stats:
                        print(f"  Stats: {stats.get('total_signals', 0)} total, "
                              f"Avg Conf: {stats.get('avg_confidence', 0):.1f}%, "
                              f"Avg SNR: {stats.get('avg_snr', 0):.2f}")
                    
                    if signals:
                        latest = signals[0]
                        print(f"  Latest: {latest.get('direction')} @ ${latest.get('entry_price', 0):.2f} "
                              f"(Conf: {latest.get('confidence', 0):.1f}%, SNR: {latest.get('snr', 0):.2f})")
                else:
                    # Fallback for list format
                    print(f"  Returned {len(data)} signals")
                    if data:
                        latest = data[0]
                        print(f"  Latest: {latest.get('direction')} @ ${latest.get('entry_price', 0):.2f}")
            else:
                print(f"\n✗ {symbol} endpoint returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"\n✗ {symbol} endpoint - Connection refused (server may not be running)")
        except Exception as e:
            print(f"\n✗ {symbol} endpoint error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("API CHECK COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    check_database()
    check_api_endpoints()
