"""Quick script to verify signals are being saved to database"""
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

# Connect to database
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', 5432),
    database=os.getenv('DB_NAME', 'liquidation_trading'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD')
)

cursor = conn.cursor()

# Check signals from last hour
one_hour_ago = datetime.now() - timedelta(hours=1)

query = """
SELECT timestamp, symbol, direction, entry_price, confidence
FROM trading_signals
WHERE timestamp > %s
ORDER BY timestamp DESC
LIMIT 20
"""

cursor.execute(query, (one_hour_ago,))
signals = cursor.fetchall()

print("=" * 60)
print("RECENT SIGNALS (Last Hour)")
print("=" * 60)
print(f"Total signals: {len(signals)}\n")

if signals:
    for signal in signals:
        ts, symbol, direction, price, conf = signal
        print(f"{ts.strftime('%H:%M:%S')} | {symbol:8} | {direction:5} @ ${price:,.2f} | Conf: {conf}%")
else:
    print("❌ NO SIGNALS FOUND IN DATABASE")
    print("\n⚠️ Signals are being generated but NOT saved to database!")

cursor.close()
conn.close()
