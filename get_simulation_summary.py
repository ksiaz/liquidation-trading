import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

# Time range
start_time = datetime(2026, 1, 1, 2, 0, 0)
end_time = datetime(2026, 1, 1, 6, 54, 0)

print("=" * 80)
print("SIMULATION SUMMARY: 02:00 - 06:54 (2026-01-01)")
print("=" * 80)

# Get snapshot count
cur.execute("""
    SELECT COUNT(*) 
    FROM orderbook_snapshots 
    WHERE symbol = 'BTCUSDT' 
    AND timestamp BETWEEN %s AND %s
""", (start_time, end_time))

count = cur.fetchone()[0]
print(f"\nTotal snapshots: {count} ({count/60:.1f} minutes)")

# Get price range
cur.execute("""
    SELECT 
        MIN((best_bid + best_ask) / 2) as min_price,
        MAX((best_bid + best_ask) / 2) as max_price,
        (SELECT (best_bid + best_ask) / 2 FROM orderbook_snapshots 
         WHERE symbol = 'BTCUSDT' AND timestamp >= %s 
         ORDER BY timestamp LIMIT 1) as start_price,
        (SELECT (best_bid + best_ask) / 2 FROM orderbook_snapshots 
         WHERE symbol = 'BTCUSDT' AND timestamp <= %s 
         ORDER BY timestamp DESC LIMIT 1) as end_price
    FROM orderbook_snapshots 
    WHERE symbol = 'BTCUSDT' 
    AND timestamp BETWEEN %s AND %s
""", (start_time, end_time, start_time, end_time))

min_price, max_price, start_price, end_price = cur.fetchone()

print(f"\nPrice Movement:")
print(f"  Start: ${start_price:,.2f}")
print(f"  End:   ${end_price:,.2f}")
print(f"  Change: {((end_price - start_price) / start_price * 100):+.3f}%")
print(f"  High:  ${max_price:,.2f}")
print(f"  Low:   ${min_price:,.2f}")
print(f"  Range: ${max_price - min_price:,.2f} ({((max_price - min_price) / min_price * 100):.3f}%)")

# Get imbalance stats
cur.execute("""
    SELECT 
        AVG(imbalance) as avg_imb,
        MIN(imbalance) as min_imb,
        MAX(imbalance) as max_imb,
        STDDEV(imbalance) as std_imb
    FROM orderbook_snapshots 
    WHERE symbol = 'BTCUSDT' 
    AND timestamp BETWEEN %s AND %s
""", (start_time, end_time))

avg_imb, min_imb, max_imb, std_imb = cur.fetchone()

print(f"\nOrderbook Imbalance:")
print(f"  Average: {avg_imb:+.4f}")
print(f"  Range: {min_imb:+.4f} to {max_imb:+.4f}")
print(f"  StdDev: {std_imb:.4f}")

# Look for potential signal periods (strong imbalance shifts)
cur.execute("""
    WITH minute_stats AS (
        SELECT 
            DATE_TRUNC('minute', timestamp) as minute,
            AVG(imbalance) as avg_imb,
            AVG((best_bid + best_ask) / 2) as avg_price,
            MIN((best_bid + best_ask) / 2) as min_price,
            MAX((best_bid + best_ask) / 2) as max_price
        FROM orderbook_snapshots 
        WHERE symbol = 'BTCUSDT' 
        AND timestamp BETWEEN %s AND %s
        GROUP BY DATE_TRUNC('minute', timestamp)
        ORDER BY minute
    )
    SELECT 
        minute,
        avg_imb,
        avg_price,
        max_price - min_price as range
    FROM minute_stats
    WHERE ABS(avg_imb) > 0.5
    ORDER BY minute
""", (start_time, end_time))

strong_imbalance_periods = cur.fetchall()

if strong_imbalance_periods:
    print(f"\nStrong Imbalance Periods (|imbalance| > 0.5):")
    for minute, imb, price, range_val in strong_imbalance_periods[:10]:  # Show first 10
        print(f"  {minute.strftime('%H:%M')} - Imb: {imb:+.4f}, Price: ${price:,.2f}, Range: ${range_val:.2f}")
    if len(strong_imbalance_periods) > 10:
        print(f"  ... and {len(strong_imbalance_periods) - 10} more")
else:
    print("\nNo strong imbalance periods detected")

print("\n" + "=" * 80)

conn.close()
