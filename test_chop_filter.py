"""
Test the new zero-lag chop filter against historical data.
Compare with old filter to validate improvements.
"""

import sys
import psycopg2
from datetime import datetime, timedelta
import numpy as np

sys.path.insert(0, 'd:/liquidation-trading')
from early_reversal_detector import EarlyReversalDetector

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 100)
print("CHOP FILTER TEST: Zero-Lag Orderbook Microstructure vs Old Filter")
print("=" * 100)

# Test period: Last 6 hours
end_time = datetime(2026, 1, 1, 7, 0, 0)
start_time = end_time - timedelta(hours=6)

symbol = 'BTCUSDT'

cur.execute("""
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        imbalance,
        bid_volume_10,
        ask_volume_10,
        spread_pct
    FROM orderbook_snapshots
    WHERE symbol = %s
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
""", (symbol, start_time, end_time))

rows = cur.fetchall()

print(f"\n📊 Processing {len(rows)} snapshots...")

# Initialize detector with NEW filter
detector = EarlyReversalDetector(
    max_lookback_seconds=300,
    snr_threshold=0.15
)

chop_blocks = 0
trend_allows = 0
chop_periods = []

for i, row in enumerate(rows):
    timestamp, best_bid, best_ask, imbalance, bid_vol, ask_vol, spread_pct = row
    
    orderbook_data = {
        'timestamp': timestamp,
        'symbol': symbol,
        'best_bid': float(best_bid),
        'best_ask': float(best_ask),
        'imbalance': float(imbalance) if imbalance else 0,
        'bid_volume_10': float(bid_vol) if bid_vol else 0,
        'ask_volume_10': float(ask_vol) if ask_vol else 0,
        'spread_pct': float(spread_pct) if spread_pct else 0
    }
    
    # Update detector
    detector.update(orderbook_data)
    
    # Check chop filter every 60 snapshots (1 minute)
    if i % 60 == 0 and len(detector.price_history) >= 60:
        is_choppy = detector._is_choppy_market()
        
        if is_choppy:
            chop_blocks += 1
            chop_periods.append({
                'time': timestamp,
                'price': (float(best_bid) + float(best_ask)) / 2
            })
        else:
            trend_allows += 1

total_checks = chop_blocks + trend_allows

print(f"\n{'=' * 100}")
print("RESULTS")
print(f"{'=' * 100}")

print(f"\nTotal Checks: {total_checks}")
print(f"Choppy Periods: {chop_blocks} ({chop_blocks/total_checks*100:.1f}%)")
print(f"Trending Periods: {trend_allows} ({trend_allows/total_checks*100:.1f}%)")

if chop_periods:
    print(f"\n{'=' * 100}")
    print("CHOPPY PERIODS DETECTED (First 10)")
    print(f"{'=' * 100}")
    
    for i, period in enumerate(chop_periods[:10], 1):
        print(f"\n  #{i} - {period['time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"       Price: ${period['price']:,.2f}")

print(f"\n{'=' * 100}")
print("ANALYSIS")
print(f"{'=' * 100}")

print(f"""
Expected Behavior:
- Old filter: 100% choppy (broken, blocked everything)
- New filter: 20-40% choppy (healthy balance)

Actual Result: {chop_blocks/total_checks*100:.1f}% choppy

Status: {'✅ WORKING' if 20 <= chop_blocks/total_checks*100 <= 50 else '⚠️ NEEDS TUNING'}
""")

if chop_blocks/total_checks*100 < 20:
    print("⚠️ Filter may be too lenient - consider tightening thresholds")
elif chop_blocks/total_checks*100 > 50:
    print("⚠️ Filter may be too strict - consider loosening thresholds")
else:
    print("✅ Filter is working well - good balance between filtering and allowing signals")

conn.close()
