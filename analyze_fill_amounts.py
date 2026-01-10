"""
Analyze actual fill amounts to see if variation tolerance is appropriate.

Current tolerance: Rounds to nearest $100
Question: Is this too strict? Should we allow more variation?
"""

import sys
sys.path.insert(0, 'd:/liquidation-trading')

import psycopg2
from datetime import datetime
import numpy as np
from collections import defaultdict

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

print("=" * 100)
print("FILL AMOUNT ANALYSIS - Testing Different Tolerances")
print("=" * 100)

# Detect fills (same logic as before)
prev_bid_vol = 0
prev_ask_vol = 0
bid_vol_changes = []
ask_vol_changes = []

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

bid_mean = np.mean(bid_vol_changes[30:])
bid_std = np.std(bid_vol_changes[30:])
ask_mean = np.mean(ask_vol_changes[30:])
ask_std = np.std(ask_vol_changes[30:])

# Collect all fills with their exact amounts
bid_fills = []
ask_fills = []
bid_spikes = {}
ask_spikes = {}

for i, row in enumerate(rows):
    if i < 30:
        continue
    
    timestamp, best_bid, best_ask, bid_vol_10, ask_vol_10, bid_vol_20, ask_vol_20 = row
    mid_price = (float(best_bid) + float(best_ask)) / 2
    
    bid_change = bid_vol_changes[i]
    ask_change = ask_vol_changes[i]
    
    if bid_change > bid_mean + 3 * bid_std:
        bid_spikes[i] = {'timestamp': timestamp, 'size': bid_change, 'price': mid_price, 'withdrawn': False}
    
    if ask_change > ask_mean + 3 * ask_std:
        ask_spikes[i] = {'timestamp': timestamp, 'size': ask_change, 'price': mid_price, 'withdrawn': False}
    
    if bid_change < bid_mean - 3 * bid_std:
        for spike_idx in list(bid_spikes.keys()):
            if i - spike_idx <= 10:
                bid_spikes[spike_idx]['withdrawn'] = True
    
    if ask_change < ask_mean - 3 * ask_std:
        for spike_idx in list(ask_spikes.keys()):
            if i - spike_idx <= 10:
                ask_spikes[spike_idx]['withdrawn'] = True
    
    for spike_idx, spike in list(bid_spikes.items()):
        if i - spike_idx > 10 and not spike['withdrawn']:
            dollar_amount = spike['size'] * spike['price']
            bid_fills.append({
                'timestamp': spike['timestamp'],
                'size': spike['size'],
                'price': spike['price'],
                'dollar_amount': dollar_amount
            })
            del bid_spikes[spike_idx]
    
    for spike_idx, spike in list(ask_spikes.items()):
        if i - spike_idx > 10 and not spike['withdrawn']:
            dollar_amount = spike['size'] * spike['price']
            ask_fills.append({
                'timestamp': spike['timestamp'],
                'size': spike['size'],
                'price': spike['price'],
                'dollar_amount': dollar_amount
            })
            del ask_spikes[spike_idx]

print(f"\nTotal fills detected:")
print(f"  BID: {len(bid_fills)}")
print(f"  ASK: {len(ask_fills)}")

# Show all fill amounts
print(f"\n{'=' * 100}")
print("ALL FILL AMOUNTS (sorted)")
print(f"{'=' * 100}")

all_fills = []
for f in bid_fills:
    all_fills.append(('BID', f['timestamp'], f['dollar_amount']))
for f in ask_fills:
    all_fills.append(('ASK', f['timestamp'], f['dollar_amount']))

all_fills.sort(key=lambda x: x[2])

print(f"{'Side':<6} {'Time':<20} {'Dollar Amount':<20} {'Rounded $100':<15} {'Rounded $500':<15} {'Rounded $1k':<15}")
print("-" * 100)

for side, timestamp, amount in all_fills:
    rounded_100 = round(amount / 100) * 100
    rounded_500 = round(amount / 500) * 500
    rounded_1k = round(amount / 1000) * 1000
    print(f"{side:<6} {timestamp.strftime('%H:%M:%S'):<20} ${amount:>18,.2f} ${rounded_100:>13,.0f} ${rounded_500:>13,.0f} ${rounded_1k:>13,.0f}")

# Test different rounding tolerances
print(f"\n{'=' * 100}")
print("PATTERN DETECTION WITH DIFFERENT TOLERANCES")
print(f"{'=' * 100}")

tolerances = [
    (100, "Current ($100)"),
    (500, "Relaxed ($500)"),
    (1000, "Very Relaxed ($1k)"),
    (5000, "Extremely Relaxed ($5k)"),
]

for rounding, label in tolerances:
    # Group by rounded amount
    bid_groups = defaultdict(list)
    ask_groups = defaultdict(list)
    
    for f in bid_fills:
        rounded = round(f['dollar_amount'] / rounding) * rounding
        bid_groups[rounded].append(f)
    
    for f in ask_fills:
        rounded = round(f['dollar_amount'] / rounding) * rounding
        ask_groups[rounded].append(f)
    
    # Count patterns (2+ fills with same rounded amount)
    bid_patterns = sum(1 for fills in bid_groups.values() if len(fills) >= 2)
    ask_patterns = sum(1 for fills in ask_groups.values() if len(fills) >= 2)
    total_patterns = bid_patterns + ask_patterns
    
    print(f"\n{label}:")
    print(f"  BID patterns: {bid_patterns}")
    print(f"  ASK patterns: {ask_patterns}")
    print(f"  Total: {total_patterns}")
    
    # Show the patterns
    if total_patterns > 0:
        print(f"  Detected patterns:")
        for rounded, fills in bid_groups.items():
            if len(fills) >= 2:
                amounts = [f['dollar_amount'] for f in fills]
                variation = (np.std(amounts) / np.mean(amounts) * 100)
                print(f"    BID: {len(fills)} fills near ${rounded:,.0f} (variation: {variation:.1f}%)")
        
        for rounded, fills in ask_groups.items():
            if len(fills) >= 2:
                amounts = [f['dollar_amount'] for f in fills]
                variation = (np.std(amounts) / np.mean(amounts) * 100)
                print(f"    ASK: {len(fills)} fills near ${rounded:,.0f} (variation: {variation:.1f}%)")

conn.close()

print(f"\n{'=' * 100}\n")
