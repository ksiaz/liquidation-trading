import psycopg2

print("Verifying 20-level data capture...")
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
    
    # Get most recent snapshot with 20-level data
    cur.execute("""
        SELECT 
            symbol, timestamp,
            bid_volume_10, ask_volume_10, imbalance,
            bid_volume_20, ask_volume_20, imbalance_20
        FROM orderbook_snapshots
        WHERE bid_volume_20 IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    
    rows = cur.fetchall()
    
    if not rows:
        print("⚠️ No 20-level data found yet (app may need to restart)")
    else:
        print(f"✅ Found {len(rows)} snapshots with 20-level data\n")
        print(f"{'Symbol':<10} {'Time':<20} {'10-Lvl Vol':<12} {'20-Lvl Vol':<12} {'Imb-10':<10} {'Imb-20':<10}")
        print("-" * 80)
        
        for symbol, ts, bv10, av10, imb10, bv20, av20, imb20 in rows:
            vol10 = bv10 + av10
            vol20 = bv20 + av20
            print(f"{symbol:<10} {str(ts):<20} {vol10:<12.2f} {vol20:<12.2f} {imb10:>+9.4f} {imb20:>+9.4f}")
        
        # Calculate average difference
        print("\n📊 20-Level vs 10-Level Comparison:")
        cur.execute("""
            SELECT 
                AVG((bid_volume_20 + ask_volume_20) / NULLIF(bid_volume_10 + ask_volume_10, 0)) as vol_ratio,
                AVG(ABS(imbalance_20 - imbalance)) as imb_diff
            FROM orderbook_snapshots
            WHERE bid_volume_20 IS NOT NULL
              AND timestamp > NOW() - INTERVAL '5 minutes'
        """)
        vol_ratio, imb_diff = cur.fetchone()
        if vol_ratio:
            print(f"  Volume increase: {(vol_ratio - 1) * 100:.1f}% more volume in 20 levels")
            print(f"  Imbalance delta: {imb_diff:.4f} average difference")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
