"""
Check orderbook data flow and signal generator connectivity
"""
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

def check_orderbook_flow():
    """Check if orderbook data is being collected"""
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
        print("ORDERBOOK DATA FLOW CHECK")
        print("=" * 80)
        
        # Check orderbook snapshots by symbol
        cursor.execute("""
            SELECT 
                symbol,
                COUNT(*) as snapshot_count,
                MAX(timestamp) as latest_snapshot,
                MIN(timestamp) as earliest_snapshot
            FROM orderbook_snapshots
            GROUP BY symbol
            ORDER BY symbol
        """)
        
        results = cursor.fetchall()
        if results:
            print("\nOrderbook Snapshots:")
            for row in results:
                symbol, count, latest, earliest = row
                time_since_latest = (datetime.now() - latest).total_seconds() if latest else None
                print(f"\n{symbol}:")
                print(f"  Total Snapshots: {count:,}")
                print(f"  Latest: {latest}")
                print(f"  Earliest: {earliest}")
                if time_since_latest is not None:
                    print(f"  Time since latest: {time_since_latest:.1f}s ago")
                    if time_since_latest < 5:
                        print(f"  ✓ Data is LIVE")
                    elif time_since_latest < 60:
                        print(f"  ⚠ Data is recent but not live")
                    else:
                        print(f"  ✗ Data is STALE")
        else:
            print("\n✗ No orderbook snapshots found")
        
        # Check recent orderbook activity (last 5 minutes)
        print("\n" + "-" * 80)
        print("RECENT ORDERBOOK ACTIVITY (Last 5 minutes)")
        print("-" * 80)
        
        cursor.execute("""
            SELECT 
                symbol,
                COUNT(*) as recent_count
            FROM orderbook_snapshots
            WHERE timestamp > NOW() - INTERVAL '5 minutes'
            GROUP BY symbol
            ORDER BY symbol
        """)
        
        recent = cursor.fetchall()
        if recent:
            for row in recent:
                symbol, count = row
                rate = count / 5  # snapshots per minute
                print(f"{symbol}: {count} snapshots ({rate:.1f}/min)")
                if rate >= 50:  # Should be ~60/min for 1s sampling
                    print(f"  ✓ Good sampling rate")
                elif rate >= 30:
                    print(f"  ⚠ Lower than expected sampling rate")
                else:
                    print(f"  ✗ Very low sampling rate")
        else:
            print("No recent orderbook activity")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"✗ Error checking orderbook flow: {e}")
        import traceback
        traceback.print_exc()

def check_signal_generator_logs():
    """Check for signal generator activity in logs"""
    print("\n" + "=" * 80)
    print("SIGNAL GENERATOR LOG CHECK")
    print("=" * 80)
    
    log_files = ['monitor.log', 'prediction_monitor.log']
    
    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"\nChecking {log_file}...")
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    
                    # Look for signal generator related messages
                    signal_lines = [l for l in lines if 'SignalGenerator' in l or 'EarlyReversal' in l or 'signal' in l.lower()]
                    
                    if signal_lines:
                        print(f"  Found {len(signal_lines)} signal-related log entries")
                        print(f"  Last 5 entries:")
                        for line in signal_lines[-5:]:
                            print(f"    {line.strip()}")
                    else:
                        print(f"  No signal-related log entries found")
            except Exception as e:
                print(f"  Error reading log: {e}")
        else:
            print(f"\n{log_file} not found")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    check_orderbook_flow()
    check_signal_generator_logs()
