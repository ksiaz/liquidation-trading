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

# Read and execute SQL
with open('create_orderbook_metrics.sql', 'r') as f:
    sql = f.read()
    cursor.execute(sql)
    conn.commit()

print("✅ orderbook_metrics table created successfully!")

# Verify
cursor.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('orderbook_snapshots', 'orderbook_metrics')
    ORDER BY table_name;
""")

tables = cursor.fetchall()
print(f"\n📊 Orderbook tables: {[t[0] for t in tables]}")

cursor.close()
conn.close()
