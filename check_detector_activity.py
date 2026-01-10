"""
Check if EarlyReversalDetector is actually being called and what it's seeing.
Add temporary debug logging to see detector internals.
"""

import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)

print("=" * 80)
print("DETECTOR ACTIVITY CHECK")
print("=" * 80)

# Check if detector is seeing data
cur = conn.cursor()

# 1. Check orderbook data availability
cur.execute("""
    SELECT 
        symbol,
        COUNT(*) as snapshots,
        MIN(timestamp) as first_snapshot,
        MAX(timestamp) as last_snapshot
    FROM orderbook_snapshots
    WHERE timestamp > NOW() - INTERVAL '3 hours'
    GROUP BY symbol
""")

print("\nOrderbook data (last 3 hours):")
print(f"{'Symbol':<10} {'Snapshots':<12} {'First':<20} {'Last':<20}")
print("-" * 70)
for row in cur.fetchall():
    symbol, count, first, last = row
    print(f"{symbol:<10} {count:<12} {first.strftime('%H:%M:%S'):<20} {last.strftime('%H:%M:%S'):<20}")

# 2. Find price movements >0.5% (should trigger detector)
print("\n" + "=" * 80)
print("PRICE MOVEMENTS >0.5% (last 3 hours)")
print("=" * 80)

cur.execute("""
    WITH price_changes AS (
        SELECT 
            symbol,
            timestamp,
            (best_bid + best_ask) / 2 as mid_price,
            LAG((best_bid + best_ask) / 2, 60) OVER (PARTITION BY symbol ORDER BY timestamp) as price_60s_ago,
            imbalance,
            spread_pct
        FROM orderbook_snapshots
        WHERE timestamp > NOW() - INTERVAL '3 hours'
    )
    SELECT 
        symbol,
        timestamp,
        mid_price,
        price_60s_ago,
        ((mid_price - price_60s_ago) / price_60s_ago * 100) as change_pct,
        imbalance,
        spread_pct
    FROM price_changes
    WHERE price_60s_ago IS NOT NULL
        AND ABS((mid_price - price_60s_ago) / price_60s_ago) > 0.005
    ORDER BY timestamp DESC
    LIMIT 20
""")

moves = cur.fetchall()
if moves:
    print(f"\n{'Time':<20} {'Symbol':<10} {'Price':<12} {'60s Chg %':<12} {'Imbal':<10} {'Spread %':<10}")
    print("-" * 90)
    for row in moves:
        symbol, ts, price, prev_price, change_pct, imb, spread = row
        print(f"{ts.strftime('%m-%d %H:%M:%S'):<20} "
              f"{symbol:<10} "
              f"${float(price):>10,.2f} "
              f"{float(change_pct):>10.2f}% "
              f"{float(imb):>8.3f} "
              f"{float(spread)*100:>8.4f}%")
else:
    print("\n❌ No price movements >0.5% found in last 3 hours")

# 3. Check for any detector activity (check logs or signal attempts)
print("\n" + "=" * 80)
print("DETECTOR DIAGNOSIS")
print("=" * 80)

if moves:
    print(f"\n✅ Found {len(moves)} significant price movements")
    print("   These SHOULD have triggered detector analysis")
    print("\n❌ But 0 signals in database")
    print("\nPOSSIBLE REASONS:")
    print("1. Chop filter blocking (but we saw it's OK now)")
    print("2. SNR threshold too high (signals detected but filtered)")
    print("3. Not enough confirmed signals (need 2+)")
    print("4. Wave trend filter blocking counter-trend signals")
    print("5. Signal cooldown preventing duplicates")
    print("\nNEXT: Add debug logging to see detector internals")
else:
    print("\n⚠️  No significant price movements in last 3 hours")
    print("   Breakouts may have occurred >3 hours ago")
    print("   Or price moved gradually (not detected as breakout)")

conn.close()
print(f"\n{'='*80}\n")
