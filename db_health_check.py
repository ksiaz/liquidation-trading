import psycopg2
from datetime import datetime

print("Detailed Database Health Check")
print("=" * 80)

try:
    conn = psycopg2.connect(
        dbname="liquidation_trading",
        user="postgres",
        password="postgres",
        host="localhost",
        connect_timeout=2
    )
    conn.set_session(autocommit=True)
    cur = conn.cursor()
    
    # 1. Overall stats
    print("\n📊 OVERALL STATISTICS")
    print("-" * 80)
    cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM orderbook_snapshots")
    total, first, last = cur.fetchone()
    print(f"Total snapshots: {total:,}")
    print(f"First snapshot:  {first}")
    print(f"Last snapshot:   {last}")
    if last:
        age = datetime.now() - last.replace(tzinfo=None)
        print(f"Data age:        {age.total_seconds():.0f} seconds ago")
        if age.total_seconds() < 10:
            print(f"Status:          ✅ ACTIVE")
        else:
            print(f"Status:          ⚠️ STALE")
    
    # 2. Per-symbol breakdown
    print("\n📈 PER-SYMBOL BREAKDOWN")
    print("-" * 80)
    cur.execute("""
        SELECT 
            symbol, 
            COUNT(*) as rows,
            MIN(timestamp) as first,
            MAX(timestamp) as last
        FROM orderbook_snapshots
        GROUP BY symbol
        ORDER BY symbol
    """)
    for symbol, rows, first, last in cur.fetchall():
        age = datetime.now() - last.replace(tzinfo=None)
        status = "✅" if age.total_seconds() < 10 else "⚠️"
        print(f"{status} {symbol:10s}: {rows:5,} rows | Last: {last} ({age.total_seconds():.0f}s ago)")
    
    # 3. Storage rate (last 5 minutes)
    print("\n⏱️  STORAGE RATE (Last 5 minutes)")
    print("-" * 80)
    cur.execute("""
        SELECT 
            symbol,
            COUNT(*) as snapshots,
            EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) as duration_sec
        FROM orderbook_snapshots
        WHERE timestamp > NOW() - INTERVAL '5 minutes'
        GROUP BY symbol
    """)
    for symbol, snapshots, duration in cur.fetchall():
        if duration and duration > 0:
            rate = snapshots / duration
            print(f"{symbol:10s}: {snapshots:4} snapshots in {duration:.0f}s = {rate:.2f} snapshots/sec")
    
    # 4. Recent data sample
    print("\n🔍 RECENT DATA SAMPLE (Last 3 snapshots per symbol)")
    print("-" * 80)
    cur.execute("""
        WITH ranked AS (
            SELECT 
                symbol, timestamp, imbalance, spread_pct,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
            FROM orderbook_snapshots
        )
        SELECT symbol, timestamp, imbalance, spread_pct
        FROM ranked
        WHERE rn <= 3
        ORDER BY symbol, timestamp DESC
    """)
    current_symbol = None
    for symbol, ts, imbalance, spread_pct in cur.fetchall():
        if symbol != current_symbol:
            print(f"\n{symbol}:")
            current_symbol = symbol
        print(f"  {ts} | Imbalance: {imbalance:+.4f} | Spread: {spread_pct:.4f}%")
    
    # 5. Data gaps check
    print("\n🕳️  DATA GAPS CHECK (Last hour)")
    print("-" * 80)
    cur.execute("""
        WITH gaps AS (
            SELECT 
                symbol,
                timestamp,
                LEAD(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) - timestamp as gap
            FROM orderbook_snapshots
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        )
        SELECT symbol, timestamp, gap
        FROM gaps
        WHERE gap > INTERVAL '5 seconds'
        ORDER BY gap DESC
        LIMIT 5
    """)
    gaps = cur.fetchall()
    if gaps:
        print("⚠️ Found gaps > 5 seconds:")
        for symbol, ts, gap in gaps:
            print(f"  {symbol} at {ts}: {gap}")
    else:
        print("✅ No significant gaps detected")
    
    conn.close()
    
except Exception as e:
    print(f"\n❌ Error: {e}")
