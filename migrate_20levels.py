import psycopg2

print("Adding 20-level columns to orderbook_snapshots...")

try:
    conn = psycopg2.connect(
        dbname="liquidation_trading",
        user="postgres",
        password="postgres",
        host="localhost"
    )
    conn.set_session(autocommit=True)
    cur = conn.cursor()
    
    # Add 20-level columns
    print("Adding bid_volume_20...")
    cur.execute("ALTER TABLE orderbook_snapshots ADD COLUMN IF NOT EXISTS bid_volume_20 DECIMAL(20, 8)")
    
    print("Adding ask_volume_20...")
    cur.execute("ALTER TABLE orderbook_snapshots ADD COLUMN IF NOT EXISTS ask_volume_20 DECIMAL(20, 8)")
    
    print("Adding bid_value_20...")
    cur.execute("ALTER TABLE orderbook_snapshots ADD COLUMN IF NOT EXISTS bid_value_20 DECIMAL(20, 2)")
    
    print("Adding ask_value_20...")
    cur.execute("ALTER TABLE orderbook_snapshots ADD COLUMN IF NOT EXISTS ask_value_20 DECIMAL(20, 2)")
    
    print("Adding imbalance_20...")
    cur.execute("ALTER TABLE orderbook_snapshots ADD COLUMN IF NOT EXISTS imbalance_20 DECIMAL(10, 6)")
    
    print("\n✅ Schema updated successfully!")
    
    # Verify columns exist
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'orderbook_snapshots' 
        AND column_name LIKE '%_20'
        ORDER BY column_name
    """)
    
    print("\nNew columns:")
    for col, dtype in cur.fetchall():
        print(f"  {col}: {dtype}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
