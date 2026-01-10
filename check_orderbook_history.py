import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres", 
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

# Get first and last snapshots
cur.execute("""
    SELECT 
        MIN(timestamp) as first,
        MAX(timestamp) as last,
        COUNT(*) as total
    FROM orderbook_snapshots
""")

first, last, total = cur.fetchone()

print("=" * 80)
print("ORDERBOOK DATA LOGGING HISTORY")
print("=" * 80)
print(f"\nFirst snapshot: {first}")
print(f"Latest snapshot: {last}")
print(f"Total snapshots: {total:,}")

if first and last:
    duration = last - first
    print(f"\nLogging duration: {duration}")
    print(f"Days: {duration.days}")
    print(f"Hours: {duration.total_seconds() / 3600:.1f}")
    
    age = datetime.now() - last.replace(tzinfo=None)
    print(f"\nData age: {age.total_seconds():.0f} seconds")
    
# Per-symbol breakdown
print("\n" + "=" * 80)
print("PER-SYMBOL BREAKDOWN")
print("=" * 80)

cur.execute("""
    SELECT 
        symbol,
        MIN(timestamp) as first,
        MAX(timestamp) as last,
        COUNT(*) as count
    FROM orderbook_snapshots
    GROUP BY symbol
    ORDER BY symbol
""")

for symbol, first, last, count in cur.fetchall():
    print(f"\n{symbol}:")
    print(f"  First: {first}")
    print(f"  Last: {last}")
    print(f"  Count: {count:,}")

conn.close()
