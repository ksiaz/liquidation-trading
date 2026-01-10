import psycopg2
from datetime import datetime

print("Checking latest data...")
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
    
    # Get latest timestamp
    cur.execute("SELECT MAX(timestamp) FROM orderbook_snapshots")
    latest = cur.fetchone()[0]
    print(f"Latest timestamp: {latest}")
    
    # Check how recent
    if latest:
        age = datetime.now() - latest.replace(tzinfo=None)
        print(f"Age: {age.total_seconds():.0f} seconds ago")
        
        if age.total_seconds() > 60:
            print("⚠️ WARNING: Data is stale (>1 minute old)")
        else:
            print("✅ Data is recent")
    
    # Get count by symbol
    cur.execute("SELECT symbol, COUNT(*) FROM orderbook_snapshots GROUP BY symbol")
    print("\nBy symbol:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} rows")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
