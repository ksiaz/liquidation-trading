"""
Quick script to check if new detector is generating signals.
"""
import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'liquidation_trading'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD')
)

cursor = conn.cursor()

# Check for signals in last hour
query = """
SELECT timestamp, symbol, direction, entry_price, confidence, timeframe
FROM trading_signals
WHERE timestamp >= NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC
LIMIT 10
"""

cursor.execute(query)
rows = cursor.fetchall()

print("=" * 80)
print("RECENT SIGNALS (Last 1 Hour)")
print("=" * 80)

if rows:
    print(f"\n✅ Found {len(rows)} signals:\n")
    for row in rows:
        timestamp, symbol, direction, price, conf, timeframe = row
        print(f"  {timestamp.strftime('%H:%M:%S')} | {symbol:8} | {direction:5} @ ${price:9,.2f} | Conf: {conf:3}% | TF: {timeframe}")
else:
    print("\n⚠️ No signals in the last hour")
    print("\nThis is normal if:")
    print("  1. App just started (detector needs 60s of data)")
    print("  2. Market is flat (92% of the time)")
    print("  3. No liquidity drain patterns detected")

# Check overall stats
cursor.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM trading_signals")
total, first, last = cursor.fetchone()

print(f"\n" + "=" * 80)
print("OVERALL SIGNAL STATS")
print("=" * 80)
print(f"Total signals ever: {total}")
if first and last:
    print(f"First signal: {first}")
    print(f"Last signal: {last}")
    
    # Check if detector is actually running
    time_since_last = datetime.now() - last.replace(tzinfo=None)
    if time_since_last.total_seconds() < 3600:
        print(f"\n✅ Detector recently active ({time_since_last.total_seconds()/60:.0f}m ago)")
    else:
        print(f"\n⚠️ No recent signals ({time_since_last.total_seconds()/3600:.1f}h since last)")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("\nTo monitor live signals:")
print("  1. Check app logs for: '🎯 SIGNAL GENERATED'")
print("  2. Watch Signals tab in the dashboard UI")
print("  3. Run this script again: python check_signals.py")
print("=" * 80)
