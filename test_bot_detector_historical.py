"""
Test comprehensive bot detector on real historical data.

Uses the same 04:30-05:27 period to see what bot patterns existed.
"""

import sys
sys.path.insert(0, 'd:/liquidation-trading')

import psycopg2
from datetime import datetime
from comprehensive_bot_detector import ComprehensiveBotDetector
import numpy as np

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)

start_time = datetime(2026, 1, 1, 4, 30, 0)
end_time = datetime(2026, 1, 1, 5, 27, 0)
symbol = 'BTCUSDT'

# Get orderbook data
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

print("=" * 120)
print("COMPREHENSIVE BOT DETECTOR - HISTORICAL DATA TEST")
print("=" * 120)
print(f"\nPeriod: {start_time} to {end_time}")
print(f"Snapshots: {len(rows)}")

# Initialize detector
detector = ComprehensiveBotDetector(max_history=1000)

# Track volume changes to detect fills (same logic as fill_tracker)
prev_bid_vol = 0
prev_ask_vol = 0
bid_vol_changes = []
ask_vol_changes = []

# First pass: collect volume changes
for row in rows:
    timestamp, best_bid, best_ask, bid_vol_10, ask_vol_10, bid_vol_20, ask_vol_20 = row
    
    bid_vol = (float(bid_vol_10) if bid_vol_10 else 0) + (float(bid_vol_20) if bid_vol_20 else 0)
    ask_vol = (float(ask_vol_10) if ask_vol_10 else 0) + (float(ask_vol_20) if ask_vol_20 else 0)
    
    bid_change = bid_vol - prev_bid_vol
    ask_change = ask_vol - prev_ask_vol
    
    bid_vol_changes.append(bid_change)
    ask_vol_changes.append(ask_change)
    
    prev_bid_vol = bid_vol
    prev_ask_vol = ask_vol

# Calculate spike thresholds
bid_mean = np.mean(bid_vol_changes[30:])
bid_std = np.std(bid_vol_changes[30:])
ask_mean = np.mean(ask_vol_changes[30:])
ask_std = np.std(ask_vol_changes[30:])

print(f"\nVolume spike thresholds:")
print(f"  BID: >{bid_mean + 3*bid_std:.2f} (mean={bid_mean:.2f}, std={bid_std:.2f})")
print(f"  ASK: >{ask_mean + 3*ask_std:.2f} (mean={ask_mean:.2f}, std={ask_std:.2f})")

# Second pass: detect fills and add to bot detector
bid_spikes = {}
ask_spikes = {}
fills_detected = 0
patterns_detected = []

for i, row in enumerate(rows):
    if i < 30:
        continue
    
    timestamp, best_bid, best_ask, bid_vol_10, ask_vol_10, bid_vol_20, ask_vol_20 = row
    
    mid_price = (float(best_bid) + float(best_ask)) / 2
    bid_vol = (float(bid_vol_10) if bid_vol_10 else 0) + (float(bid_vol_20) if bid_vol_20 else 0)
    ask_vol = (float(ask_vol_10) if ask_vol_10 else 0) + (float(ask_vol_20) if ask_vol_20 else 0)
    
    bid_change = bid_vol_changes[i]
    ask_change = ask_vol_changes[i]
    
    # Detect BID spikes
    if bid_change > bid_mean + 3 * bid_std:
        bid_spikes[i] = {
            'timestamp': timestamp,
            'size': bid_change,
            'price': mid_price,
            'withdrawn': False
        }
    
    # Detect ASK spikes
    if ask_change > ask_mean + 3 * ask_std:
        ask_spikes[i] = {
            'timestamp': timestamp,
            'size': ask_change,
            'price': mid_price,
            'withdrawn': False
        }
    
    # Check for withdrawals (mark as spoofed)
    if bid_change < bid_mean - 3 * bid_std:
        for spike_idx in list(bid_spikes.keys()):
            if i - spike_idx <= 10 and not bid_spikes[spike_idx]['withdrawn']:
                bid_spikes[spike_idx]['withdrawn'] = True
    
    if ask_change < ask_mean - 3 * ask_std:
        for spike_idx in list(ask_spikes.keys()):
            if i - spike_idx <= 10 and not ask_spikes[spike_idx]['withdrawn']:
                ask_spikes[spike_idx]['withdrawn'] = True
    
    # Detect fills (spikes that stayed >10 snapshots)
    for spike_idx, spike in list(bid_spikes.items()):
        if i - spike_idx > 10 and not spike['withdrawn']:
            # This is a fill
            pattern = detector.add_fill(
                side='BID',
                size=spike['size'],
                price=spike['price'],
                timestamp=spike['timestamp']
            )
            
            fills_detected += 1
            
            if pattern and pattern['fill_count'] >= 2:
                patterns_detected.append({
                    'timestamp': timestamp,
                    'pattern': pattern
                })
            
            del bid_spikes[spike_idx]
    
    for spike_idx, spike in list(ask_spikes.items()):
        if i - spike_idx > 10 and not spike['withdrawn']:
            # This is a fill
            pattern = detector.add_fill(
                side='ASK',
                size=spike['size'],
                price=spike['price'],
                timestamp=spike['timestamp']
            )
            
            fills_detected += 1
            
            if pattern and pattern['fill_count'] >= 2:
                patterns_detected.append({
                    'timestamp': timestamp,
                    'pattern': pattern
                })
            
            del ask_spikes[spike_idx]

print(f"\n{'=' * 120}")
print("RESULTS")
print(f"{'=' * 120}")

print(f"\nFills detected: {fills_detected}")
print(f"Bot patterns detected: {len(patterns_detected)}")

# Get final summary
summary = detector.get_pattern_summary(lookback_seconds=3600)

print(f"\n{'=' * 120}")
print("PATTERN SUMMARY")
print(f"{'=' * 120}")

print(f"\nTotal patterns: {summary['total_patterns']}")
print(f"BID patterns: {summary['bid_patterns']}")
print(f"ASK patterns: {summary['ask_patterns']}")

if summary.get('all_patterns'):
    print(f"\n{'=' * 120}")
    print("ALL DETECTED PATTERNS")
    print(f"{'=' * 120}")
    print(f"{'Type':<20} {'Side':<6} {'Fills':<8} {'Avg Amount':<15} {'Variation':<12} {'Frequency':<12} {'Confidence':<12}")
    print("-" * 120)
    
    for p in summary['all_patterns'][:20]:  # Top 20
        print(f"{p['pattern_type']:<20} "
              f"{p['side']:<6} "
              f"{p['fill_count']:<8} "
              f"${p['avg_amount']:>13,.0f} "
              f"{p['variation_pct']:>11.2f}% "
              f"{p['frequency']:>11.1f}/min "
              f"{p['confidence']:>11.1%}")
else:
    print(f"\n❌ No bot patterns detected in the data")

# Show strongest patterns over time
if patterns_detected:
    print(f"\n{'=' * 120}")
    print("PATTERN TIMELINE (First Detection)")
    print(f"{'=' * 120}")
    print(f"{'Time':<20} {'Type':<20} {'Side':<6} {'Fills':<8} {'Amount':<15} {'Confidence':<12}")
    print("-" * 120)
    
    seen_patterns = set()
    for event in patterns_detected[:30]:  # First 30
        p = event['pattern']
        key = (p['pattern_type'], p['side'], round(p['avg_amount'], -2))
        
        if key not in seen_patterns:
            print(f"{event['timestamp'].strftime('%H:%M:%S'):<20} "
                  f"{p['pattern_type']:<20} "
                  f"{p['side']:<6} "
                  f"{p['fill_count']:<8} "
                  f"${p['avg_amount']:>13,.0f} "
                  f"{p['confidence']:>11.1%}")
            seen_patterns.add(key)

stats = detector.get_stats()
print(f"\n{'=' * 120}")
print("DETECTOR STATS")
print(f"{'=' * 120}")
for key, value in stats.items():
    print(f"  {key}: {value}")

conn.close()

print(f"\n{'=' * 120}\n")
