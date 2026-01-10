"""
Diagnostic script to check if detector is receiving orderbook updates.
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

print("=" * 80)
print("DETECTOR HEALTH CHECK")
print("=" * 80)

# 1. Check if orderbook data is being captured
cursor.execute("""
    SELECT symbol, COUNT(*), MAX(timestamp), 
           MAX(timestamp) - MIN(timestamp) as duration
    FROM orderbook_snapshots
    WHERE timestamp >= NOW() - INTERVAL '10 minutes'
    GROUP BY symbol
    ORDER BY symbol
""")

rows = cursor.fetchall()
print("\n1. ORDERBOOK DATA CAPTURE (Last 10 min):")
if rows:
    for symbol, count, last_ts, duration in rows:
        time_ago = (datetime.now() - last_ts.replace(tzinfo=None)).total_seconds()
        print(f"   {symbol}: {count} snapshots, last {time_ago:.0f}s ago")
        if count > 0:
            print(f"      ✅ Data flowing ({count} snapshots in {duration})")
        else:
            print(f"      ⚠️ No data")
else:
    print("   ❌ NO ORDERBOOK DATA - Detector cannot work without this!")
    print("   Check: Is orderbook_storage running?")

# 2. Check signal generation attempts
cursor.execute("""
    SELECT COUNT(*), MAX(timestamp)
    FROM trading_signals
    WHERE timestamp >= NOW() - INTERVAL '10 minutes'
""")
sig_count, last_sig = cursor.fetchone()

print(f"\n2. SIGNAL GENERATION (Last 10 min):")
print(f"   Signals generated: {sig_count}")
if last_sig:
    time_ago = (datetime.now() - last_sig.replace(tzinfo=None)).total_seconds()
    print(f"   Last signal: {time_ago:.0f}s ago")
    print(f"   ✅ Detector is working!")
else:
    print(f"   No signals yet")
    if rows:
        print(f"   ℹ️ Normal - market might be flat (92% of time)")
    else:
        print(f"   ⚠️ No orderbook data = no signals possible")

# 3. Check detector configuration
print(f"\n3. DETECTOR STATUS:")
print(f"   Expected symbols: BTCUSDT, ETHUSDT, SOLUSDT")
print(f"   Expected frequency: 0-20 signals/hour per symbol")
print(f"   Detection logic: Liquidity drain + tick divergence")

cursor.close()
conn.close()

print("\n" + "=" * 80)
