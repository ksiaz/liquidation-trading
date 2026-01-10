"""
Check if EarlyReversalDetector is receiving orderbook updates and why no signals.
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
print("EARLY REVERSAL DETECTOR - DIAGNOSTIC")
print("=" * 80)

# 1. Check if orderbook snapshots are being stored
cur = conn.cursor()
cur.execute("""
    SELECT COUNT(*) 
    FROM orderbook_snapshots
    WHERE timestamp > NOW() - INTERVAL '10 minutes'
""")
recent_snapshots = cur.fetchone()[0]
print(f"\nOrderbook snapshots (last 10 min): {recent_snapshots}")
print(f"  Expected: ~600 per symbol (1/sec * 600sec)")
print(f"  Rate: {recent_snapshots/10:.1f} snapshots/min")

if recent_snapshots == 0:
    print("\n❌ NO ORDERBOOK DATA - Stream not working!")
else:
    print("\n✅ Orderbook stream is working")

# 2. Check market conditions (is it too choppy?)
cur.execute("""
    SELECT 
        symbol,
        AVG(imbalance) as avg_imbalance,
        STDDEV(imbalance) as std_imbalance,
        AVG(spread_pct) as avg_spread,
        COUNT(*) as snapshots
    FROM orderbook_snapshots
    WHERE timestamp > NOW() - INTERVAL '5 minutes'
    GROUP BY symbol
""")

print(f"\nMarket conditions (last 5 min):")
print(f"{'Symbol':<10} {'Snapshots':<12} {'Avg Imbal':<12} {'Std Imbal':<12} {'Avg Spread':<12}")
print("-" * 70)
for row in cur.fetchall():
    symbol, avg_imb, std_imb, avg_spread, count = row
    print(f"{symbol:<10} {count:<12} {avg_imb:>10.3f} {std_imb:>10.3f} {avg_spread:>10.4f}%")

# 3. Check for price movement (reversals need movement)
cur.execute("""
    WITH price_changes AS (
        SELECT 
            symbol,
            timestamp,
            best_bid,
            LAG(best_bid) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_bid,
            best_ask,
            LAG(best_ask) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_ask
        FROM orderbook_snapshots
        WHERE timestamp > NOW() - INTERVAL '5 minutes'
    )
    SELECT 
        symbol,
        COUNT(*) as total_snapshots,
        SUM(CASE WHEN best_bid != prev_bid THEN 1 ELSE 0 END) as bid_changes,
        SUM(CASE WHEN best_ask != prev_ask THEN 1 ELSE 0 END) as ask_changes,
        MAX(best_bid) as max_bid,
        MIN(best_bid) as min_bid,
        (MAX(best_bid) - MIN(best_bid)) / MIN(best_bid) * 100 as price_range_pct
    FROM price_changes
    WHERE prev_bid IS NOT NULL
    GROUP BY symbol
""")

print(f"\nPrice movement (last 5 min):")
print(f"{'Symbol':<10} {'Snapshots':<12} {'Bid Chg':<10} {'Ask Chg':<10} {'Range %':<12}")
print("-" * 70)
for row in cur.fetchall():
    symbol, total, bid_chg, ask_chg, max_bid, min_bid, range_pct = row
    print(f"{symbol:<10} {total:<12} {bid_chg:<10} {ask_chg:<10} {range_pct:>10.3f}%")

# 4. Check imbalance volatility (chop filter checks this)
cur.execute("""
    WITH imbalance_stats AS (
        SELECT 
            symbol,
            timestamp,
            imbalance,
            LAG(imbalance) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_imbalance
        FROM orderbook_snapshots
        WHERE timestamp > NOW() - INTERVAL '1 minute'
    )
    SELECT 
        symbol,
        COUNT(*) as snapshots,
        AVG(ABS(imbalance - prev_imbalance)) as avg_imbalance_change,
        STDDEV(imbalance) as imbalance_volatility
    FROM imbalance_stats
    WHERE prev_imbalance IS NOT NULL
    GROUP BY symbol
""")

print(f"\nImbalance volatility (last 1 min):")
print(f"{'Symbol':<10} {'Snapshots':<12} {'Avg Change':<15} {'Volatility':<12}")
print("-" * 70)
for row in cur.fetchall():
    symbol, snapshots, avg_change, volatility = row
    print(f"{symbol:<10} {snapshots:<12} {avg_change:>13.4f} {volatility:>10.4f}")
    
    # Interpret
    if volatility and volatility > 0.3:
        print(f"  ⚠️  High volatility - may be too choppy for reversal detection")
    elif avg_change and avg_change < 0.01:
        print(f"  ⚠️  Low movement - market may be too quiet")

print(f"\n{'=' * 80}")
print("INTERPRETATION:")
print("=" * 80)

if recent_snapshots == 0:
    print("❌ Orderbook stream is NOT running - no data being captured")
else:
    print("✅ Orderbook stream is working")
    print("\nPossible reasons for 0 signals:")
    print("1. Market is too choppy (chop filter blocking signals)")
    print("2. No clear reversal patterns detected")
    print("3. SNR threshold too high (signals filtered out)")
    print("4. Price movement too small (no reversals to detect)")
    print("\nNext: Check EarlyReversalDetector logs for detailed diagnostics")

conn.close()
print(f"\n{'=' * 80}\n")
