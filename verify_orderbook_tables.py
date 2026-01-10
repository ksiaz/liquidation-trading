import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# Connect to database
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'liquidation_trading'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', '')
)

cursor = conn.cursor()

# Check if orderbook tables exist
cursor.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('orderbook_snapshots', 'orderbook_metrics')
    ORDER BY table_name;
""")

tables = cursor.fetchall()

print("=" * 60)
print("ORDERBOOK TABLES CHECK")
print("=" * 60)

if tables:
    print(f"\n✅ Found {len(tables)} orderbook table(s):")
    for table in tables:
        print(f"   - {table[0]}")
        
        # Check row count
        cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
        count = cursor.fetchone()[0]
        print(f"     Rows: {count}")
else:
    print("\n❌ No orderbook tables found!")
    print("\nTables need to be created. Run:")
    print("python -c \"exec(open('database_orderbook_schema.sql').read())\"")

cursor.close()
conn.close()
