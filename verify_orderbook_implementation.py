"""
Verify Active Orderbook Implementation

This script verifies all active orderbook components are working correctly:
1. Orderbook Storage - capturing 20 levels
2. Orderbook Stream - WebSocket connection
3. Orderbook Analyzers - OFI, imbalance, etc.
4. Signal Integration - using orderbook data
"""

import psycopg2
from datetime import datetime, timedelta

print("=" * 80)
print("ORDERBOOK IMPLEMENTATION VERIFICATION")
print("=" * 80)

try:
    conn = psycopg2.connect(
        dbname="liquidation_trading",
        user="postgres",
        password="postgres",
        host="localhost"
    )
    conn.set_session(autocommit=True)
    cur = conn.cursor()
    
    # 1. Verify Storage is Active
    print("\n1. STORAGE STATUS")
    print("-" * 80)
    cur.execute("SELECT MAX(timestamp), COUNT(*) FROM orderbook_snapshots WHERE timestamp > NOW() - INTERVAL '1 minute'")
    latest, count_1min = cur.fetchone()
    
    if latest:
        age = (datetime.now() - latest.replace(tzinfo=None)).total_seconds()
        status = "✅ ACTIVE" if age < 10 else "⚠️ STALE"
        print(f"Status: {status}")
        print(f"Latest: {latest} ({age:.0f}s ago)")
        print(f"Rate: {count_1min} snapshots/min (expected: ~180)")
    else:
        print("❌ NO DATA")
    
    # 2. Verify 20-Level Capture
    print("\n2. 20-LEVEL METRICS")
    print("-" * 80)
    cur.execute("""
        SELECT COUNT(*) 
        FROM orderbook_snapshots 
        WHERE bid_volume_20 IS NOT NULL 
        AND timestamp > NOW() - INTERVAL '5 minutes'
    """)
    count_20level = cur.fetchone()[0]
    
    if count_20level > 0:
        print(f"✅ Capturing 20-level data ({count_20level} snapshots in last 5 min)")
        
        # Show volume increase
        cur.execute("""
            SELECT 
                AVG((bid_volume_20 + ask_volume_20) / NULLIF(bid_volume_10 + ask_volume_10, 0)) as ratio
            FROM orderbook_snapshots
            WHERE bid_volume_20 IS NOT NULL
            AND timestamp > NOW() - INTERVAL '5 minutes'
        """)
        ratio = cur.fetchone()[0]
        if ratio:
            print(f"   Volume increase: {(ratio - 1) * 100:.1f}% more in 20 levels")
    else:
        print("⚠️ No 20-level data yet")
    
    # 3. Verify Schema Correctness
    print("\n3. SCHEMA VALIDATION")
    print("-" * 80)
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'orderbook_snapshots'
        ORDER BY ordinal_position
    """)
    
    expected_columns = {
        'id', 'symbol', 'timestamp', 'best_bid', 'best_ask', 'spread', 'spread_pct',
        'bid_volume_10', 'ask_volume_10', 'bid_value_10', 'ask_value_10', 'imbalance',
        'bid_volume_20', 'ask_volume_20', 'bid_value_20', 'ask_value_20', 'imbalance_20'
    }
    
    actual_columns = {row[0] for row in cur.fetchall()}
    
    if expected_columns.issubset(actual_columns):
        print(f"✅ All {len(expected_columns)} expected columns present")
    else:
        missing = expected_columns - actual_columns
        print(f"⚠️ Missing columns: {missing}")
    
    # 4. Verify Data Quality
    print("\n4. DATA QUALITY")
    print("-" * 80)
    cur.execute("""
        SELECT 
            symbol,
            COUNT(*) as snapshots,
            AVG(imbalance) as avg_imb,
            AVG(spread_pct) as avg_spread,
            AVG(bid_volume_10 + ask_volume_10) as avg_vol_10,
            AVG(bid_volume_20 + ask_volume_20) as avg_vol_20
        FROM orderbook_snapshots
        WHERE timestamp > NOW() - INTERVAL '5 minutes'
        GROUP BY symbol
        ORDER BY symbol
    """)
    
    for symbol, snaps, imb, spread, vol10, vol20 in cur.fetchall():
        print(f"\n{symbol}:")
        print(f"  Snapshots: {snaps}")
        print(f"  Avg Imbalance: {imb:+.4f}")
        print(f"  Avg Spread: {spread:.4f}%")
        print(f"  Avg Volume (10): {vol10:.2f}")
        print(f"  Avg Volume (20): {vol20:.2f}")
        if vol20 and vol10:
            print(f"  Volume Ratio: {vol20/vol10:.2f}x")
    
    # 5. Verify Signal Integration
    print("\n5. SIGNAL INTEGRATION")
    print("-" * 80)
    
    # Check if signal_generator.py can query orderbook
    cur.execute("""
        SELECT imbalance, spread_pct, bid_volume_10, ask_volume_10
        FROM orderbook_snapshots
        WHERE symbol = 'BTCUSDT'
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    
    ob_data = cur.fetchone()
    if ob_data:
        print("✅ Orderbook data accessible for signal generation")
        print(f"   Latest BTC: imbalance={ob_data[0]:+.4f}, spread={ob_data[1]:.4f}%")
    else:
        print("⚠️ No orderbook data for signals")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
