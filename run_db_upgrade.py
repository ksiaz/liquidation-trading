"""
Simple database upgrade script - add position management fields
"""
import psycopg2

try:
    conn = psycopg2.connect(
        dbname="liquidation_trading",
        user="postgres",
        password="postgres",
        host="localhost"
    )
    cur = conn.cursor()
    
    print("🔄 Starting database upgrade...")
    
    # 1. Delete old signals
    print("  - Deleting old signals (>7 days)...")
    cur.execute("DELETE FROM trading_signals WHERE timestamp < NOW() - INTERVAL '7 days'")
    deleted = cur.rowcount
    print(f"    ✓ Deleted {deleted} old signals")
    
    # 2. Add position management fields one by one
    fields = [
        ("target1_price", "DECIMAL(20, 8)"),
        ("target1_hit", "BOOLEAN DEFAULT FALSE"),
        ("target1_time", "TIMESTAMP"),
        ("sl_breakeven", "BOOLEAN DEFAULT FALSE"),
        ("sl_breakeven_time", "TIMESTAMP"),
        ("exit_price", "DECIMAL(20, 8)"),
        ("exit_time", "TIMESTAMP"),
        ("exit_reason", "VARCHAR(50)"),
        ("pnl_t1", "DECIMAL(10, 4)"),
        ("pnl_t2", "DECIMAL(10, 4)"),
        ("pnl_total", "DECIMAL(10, 4)"),
        ("position_status", "VARCHAR(20) DEFAULT 'ACTIVE'")
    ]
    
    print("  - Adding position management fields...")
    for field_name, field_type in fields:
        try:
            cur.execute(f"ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS {field_name} {field_type}")
            print(f"    ✓ Added {field_name}")
        except Exception as e:
            print(f"    ⚠ {field_name} (may already exist): {e}")
    
    # 3. Add indexes
    print("  - Creating indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON trading_signals(position_status)")
    print("    ✓ idx_signals_status")
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading_signals(symbol, timestamp DESC)")
    print("    ✓ idx_signals_symbol_time")
    
    conn.commit()
    print("\n✅ Database upgrade completed successfully!")
    
    # Show stats
    cur.execute("SELECT COUNT(*) FROM trading_signals")
    total = cur.fetchone()[0]
    print(f"\nTotal signals in database: {total}")
    
    conn.close()
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    if conn:
        conn.rollback()
        conn.close()
