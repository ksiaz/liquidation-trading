"""
Debug fill tracker - see what's actually happening with fills
"""

import sys
sys.path.insert(0, 'd:/liquidation-trading')

import psycopg2
from datetime import datetime
from fill_tracker import FillTracker

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)

start_time = datetime(2026, 1, 1, 4, 30, 0)
end_time = datetime(2026, 1, 1, 5, 27, 0)
symbol = 'BTCUSDT'

query = """
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        bid_volume_10,
        ask_volume_10,
        bid_volume_20,
        ask_volume_20
    FROM orderbook_snapshots
    WHERE symbol = %s
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
"""

cur = conn.cursor()
cur.execute(query, (symbol, start_time, end_time))
rows = cur.fetchall()

print("=" * 80)
print("FILL TRACKER DEBUG")
print("=" * 80)

tracker = FillTracker(lookback_seconds=60)

# Process snapshots and log fill detections
for i, row in enumerate(rows):
    timestamp, best_bid, best_ask, bid_vol_10, ask_vol_10, bid_vol_20, ask_vol_20 = row
    
    orderbook_data = {
        'timestamp': timestamp,
        'bid_volume_10': float(bid_vol_10) if bid_vol_10 else 0,
        'ask_volume_10': float(ask_vol_10) if ask_vol_10 else 0,
        'bid_volume_20': float(bid_vol_20) if bid_vol_20 else 0,
        'ask_volume_20': float(ask_vol_20) if ask_vol_20 else 0
    }
    
    # Store previous fill counts
    prev_bid_fills = len(tracker.bid_fills)
    prev_ask_fills = len(tracker.ask_fills)
    
    tracker.update(orderbook_data)
    
    # Check if new fills were detected
    if len(tracker.bid_fills) > prev_bid_fills:
        new_fill = tracker.bid_fills[-1]
        print(f"\n[BID FILL] detected at {timestamp.strftime('%H:%M:%S')}")
        print(f"  Size: {new_fill['size']:.2f}")
        
        # Check metrics immediately after
        for lookback in [10, 30, 60]:
            metrics = tracker.get_fill_metrics(lookback)
            print(f"  {lookback}s window: {metrics['bid_fill_count']} fills, "
                  f"conviction={metrics['conviction_score']:.3f}, "
                  f"dominant={metrics['dominant_side']}")
    
    if len(tracker.ask_fills) > prev_ask_fills:
        new_fill = tracker.ask_fills[-1]
        print(f"\n[ASK FILL] detected at {timestamp.strftime('%H:%M:%S')}")
        print(f"  Size: {new_fill['size']:.2f}")
        
        for lookback in [10, 30, 60]:
            metrics = tracker.get_fill_metrics(lookback)
            print(f"  {lookback}s window: {metrics['ask_fill_count']} fills, "
                  f"conviction={metrics['conviction_score']:.3f}, "
                  f"dominant={metrics['dominant_side']}")
    
    # Every 100 snapshots, check prediction
    if i % 100 == 0 and i > 0:
        prediction, confidence, reason = tracker.predict_balance_flip()
        if prediction:
            print(f"\n[PREDICTION] at {timestamp.strftime('%H:%M:%S')}: {prediction}")
            print(f"   Confidence: {confidence:.2%}")
            print(f"   Reason: {reason}")

print("\n" + "=" * 80)
print("FINAL STATS")
print("=" * 80)
print(f"Total BID fills: {len(tracker.bid_fills)}")
print(f"Total ASK fills: {len(tracker.ask_fills)}")

# Check final metrics
for lookback in [10, 30, 60]:
    metrics = tracker.get_fill_metrics(lookback)
    print(f"\n{lookback}s window:")
    print(f"  BID: {metrics['bid_fill_count']} fills, {metrics['bid_fill_size']:.1f} BTC")
    print(f"  ASK: {metrics['ask_fill_count']} fills, {metrics['ask_fill_size']:.1f} BTC")
    print(f"  Dominant: {metrics['dominant_side']}")
    print(f"  Conviction: {metrics['conviction_score']:.3f}")

conn.close()
