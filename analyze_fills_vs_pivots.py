"""
Analyze large FILLED orders (not spoofs) and their relationship to pivots.

Key question: Do large orders that STAY in the book (get filled) 
predict price pivots better than spoofs?
"""

import psycopg2
from datetime import datetime, timedelta
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
        imbalance,
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
print("FILLED ORDERS vs PIVOTS ANALYSIS")
print("=" * 120)
print(f"\nAnalyzing {len(rows)} snapshots")

# Convert to arrays
timestamps = [r[0] for r in rows]
mid_prices = np.array([(float(r[1]) + float(r[2])) / 2 for r in rows])
imbalances = np.array([float(r[3]) if r[3] else 0 for r in rows])
bid_vol_10 = np.array([float(r[4]) if r[4] else 0 for r in rows])
ask_vol_10 = np.array([float(r[5]) if r[5] else 0 for r in rows])
bid_vol_20 = np.array([float(r[6]) if r[6] else 0 for r in rows])
ask_vol_20 = np.array([float(r[7]) if r[7] else 0 for r in rows])

total_bid = bid_vol_10 + bid_vol_20
total_ask = ask_vol_10 + ask_vol_20

# Calculate volume changes
bid_vol_changes = np.diff(total_bid, prepend=total_bid[0])
ask_vol_changes = np.diff(total_ask, prepend=total_ask[0])

# Detect volume spikes
bid_mean = np.mean(bid_vol_changes)
bid_std = np.std(bid_vol_changes)
ask_mean = np.mean(ask_vol_changes)
ask_std = np.std(ask_vol_changes)

bid_spikes = np.where(bid_vol_changes > bid_mean + 3 * bid_std)[0]
ask_spikes = np.where(ask_vol_changes > ask_mean + 3 * ask_std)[0]

# Detect withdrawals
bid_withdrawals = np.where(bid_vol_changes < bid_mean - 3 * bid_std)[0]
ask_withdrawals = np.where(ask_vol_changes < ask_mean - 3 * ask_std)[0]

print(f"\n{'=' * 120}")
print("1. CLASSIFYING SPIKES: FILLED vs SPOOFED")
print(f"{'=' * 120}")

# Classify each spike
def classify_spike(spike_idx, spike_side, withdrawal_indices):
    """
    Classify if spike was filled or spoofed
    """
    # Check if withdrawn within 10 seconds
    for withdraw_idx in withdrawal_indices:
        if spike_idx < withdraw_idx <= spike_idx + 10:
            time_diff = (timestamps[withdraw_idx] - timestamps[spike_idx]).total_seconds()
            return "SPOOFED", time_diff, withdraw_idx
    
    # If no withdrawal within 10s, consider it filled
    return "FILLED", None, None

bid_filled = []
bid_spoofed = []

for spike_idx in bid_spikes:
    classification, time_diff, withdraw_idx = classify_spike(spike_idx, 'BID', bid_withdrawals)
    
    spike_data = {
        'idx': spike_idx,
        'time': timestamps[spike_idx],
        'size': bid_vol_changes[spike_idx],
        'price': mid_prices[spike_idx],
        'classification': classification
    }
    
    if classification == "FILLED":
        bid_filled.append(spike_data)
    else:
        spike_data['withdraw_time'] = time_diff
        bid_spoofed.append(spike_data)

ask_filled = []
ask_spoofed = []

for spike_idx in ask_spikes:
    classification, time_diff, withdraw_idx = classify_spike(spike_idx, 'ASK', ask_withdrawals)
    
    spike_data = {
        'idx': spike_idx,
        'time': timestamps[spike_idx],
        'size': ask_vol_changes[spike_idx],
        'price': mid_prices[spike_idx],
        'classification': classification
    }
    
    if classification == "FILLED":
        ask_filled.append(spike_data)
    else:
        spike_data['withdraw_time'] = time_diff
        ask_spoofed.append(spike_data)

print(f"\nBID SPIKES:")
print(f"   Total: {len(bid_spikes)}")
print(f"   Filled: {len(bid_filled)} ({len(bid_filled)/len(bid_spikes)*100:.1f}%)")
print(f"   Spoofed: {len(bid_spoofed)} ({len(bid_spoofed)/len(bid_spikes)*100:.1f}%)")

print(f"\nASK SPIKES:")
print(f"   Total: {len(ask_spikes)}")
print(f"   Filled: {len(ask_filled)} ({len(ask_filled)/len(ask_spikes)*100:.1f}%)")
print(f"   Spoofed: {len(ask_spoofed)} ({len(ask_spoofed)/len(ask_spikes)*100:.1f}%)")

print(f"\n{'=' * 120}")
print("2. DETECTING PRICE PIVOTS")
print(f"{'=' * 120}")

# Detect pivots (local min/max)
def detect_pivots(prices, window=30):
    """Detect local minima and maxima"""
    pivots = []
    
    for i in range(window, len(prices) - window):
        # Local minimum (bottom)
        if prices[i] == min(prices[i-window:i+window+1]):
            pivots.append({
                'idx': i,
                'type': 'BOTTOM',
                'price': prices[i],
                'time': timestamps[i]
            })
        # Local maximum (top)
        elif prices[i] == max(prices[i-window:i+window+1]):
            pivots.append({
                'idx': i,
                'type': 'TOP',
                'price': prices[i],
                'time': timestamps[i]
            })
    
    return pivots

pivots = detect_pivots(mid_prices, window=30)

print(f"\nDetected {len(pivots)} pivots (30s window):")
print(f"   Bottoms: {len([p for p in pivots if p['type'] == 'BOTTOM'])}")
print(f"   Tops: {len([p for p in pivots if p['type'] == 'TOP'])}")

print(f"\n{'=' * 120}")
print("3. FILLED ORDERS BEFORE PIVOTS")
print(f"{'=' * 120}")

# For each pivot, check if there was a filled order before it
def find_orders_before_pivot(pivot, filled_orders, lookback_seconds=60):
    """Find filled orders within lookback period before pivot"""
    pivot_idx = pivot['idx']
    pivot_time = pivot['time']
    
    orders_before = []
    for order in filled_orders:
        order_time = order['time']
        time_diff = (pivot_time - order_time).total_seconds()
        
        if 0 < time_diff <= lookback_seconds:
            orders_before.append({
                **order,
                'time_before_pivot': time_diff
            })
    
    return orders_before

# Analyze each pivot
pivot_analysis = []

for pivot in pivots:
    # For bottoms, look for ask fills (sellers getting filled before reversal up)
    # For tops, look for bid fills (buyers getting filled before reversal down)
    
    if pivot['type'] == 'BOTTOM':
        relevant_fills = find_orders_before_pivot(pivot, ask_filled, lookback_seconds=60)
        expected_side = 'ASK'
    else:  # TOP
        relevant_fills = find_orders_before_pivot(pivot, bid_filled, lookback_seconds=60)
        expected_side = 'BID'
    
    # Calculate price move after pivot
    pivot_idx = pivot['idx']
    if pivot_idx < len(mid_prices) - 30:
        price_after_30s = mid_prices[min(pivot_idx + 30, len(mid_prices) - 1)]
        price_move = ((price_after_30s - pivot['price']) / pivot['price'] * 100)
    else:
        price_move = 0
    
    pivot_analysis.append({
        'pivot': pivot,
        'filled_orders_before': relevant_fills,
        'num_fills': len(relevant_fills),
        'expected_side': expected_side,
        'price_move_30s': price_move
    })

# Print results
print(f"\nPivot Analysis (60s lookback):")
print(f"{'Type':<8} {'Time':<20} {'Price':<12} {'Fills Before':<15} {'Side':<6} {'Move 30s':<12}")
print("-" * 90)

for analysis in pivot_analysis:
    pivot = analysis['pivot']
    print(f"{pivot['type']:<8} "
          f"{pivot['time'].strftime('%H:%M:%S'):<20} "
          f"${pivot['price']:>10,.2f} "
          f"{analysis['num_fills']:>14} "
          f"{analysis['expected_side']:<6} "
          f"{analysis['price_move_30s']:>+11.3f}%")

print(f"\n{'=' * 120}")
print("4. STATISTICAL ANALYSIS")
print(f"{'=' * 120}")

# Calculate correlation
pivots_with_fills = [p for p in pivot_analysis if p['num_fills'] > 0]
pivots_without_fills = [p for p in pivot_analysis if p['num_fills'] == 0]

print(f"\nPivots WITH filled orders before (within 60s): {len(pivots_with_fills)}")
if pivots_with_fills:
    avg_move_with = np.mean([abs(p['price_move_30s']) for p in pivots_with_fills])
    print(f"   Avg absolute price move 30s after: {avg_move_with:.3f}%")

print(f"\nPivots WITHOUT filled orders before: {len(pivots_without_fills)}")
if pivots_without_fills:
    avg_move_without = np.mean([abs(p['price_move_30s']) for p in pivots_without_fills])
    print(f"   Avg absolute price move 30s after: {avg_move_without:.3f}%")

# Check if fills predict pivot strength
if pivots_with_fills and pivots_without_fills:
    print(f"\n📊 CONCLUSION:")
    if avg_move_with > avg_move_without:
        improvement = ((avg_move_with - avg_move_without) / avg_move_without * 100)
        print(f"   ✅ Pivots WITH filled orders have {improvement:+.1f}% stronger moves")
        print(f"   → Filled orders ARE predictive of pivot strength")
    else:
        print(f"   ❌ Filled orders do NOT predict stronger pivots")

print(f"\n{'=' * 120}")
print("5. TIMING ANALYSIS: How far before pivot do fills appear?")
print(f"{'=' * 120}")

# Analyze timing
all_fill_timings = []
for analysis in pivots_with_fills:
    for fill in analysis['filled_orders_before']:
        all_fill_timings.append(fill['time_before_pivot'])

if all_fill_timings:
    print(f"\nFilled orders timing before pivots:")
    print(f"   Count: {len(all_fill_timings)}")
    print(f"   Avg: {np.mean(all_fill_timings):.1f}s before pivot")
    print(f"   Median: {np.median(all_fill_timings):.1f}s before pivot")
    print(f"   Min: {np.min(all_fill_timings):.1f}s before pivot")
    print(f"   Max: {np.max(all_fill_timings):.1f}s before pivot")
    
    # Distribution
    print(f"\n   Distribution:")
    print(f"      0-10s:  {len([t for t in all_fill_timings if t <= 10])} fills")
    print(f"      10-30s: {len([t for t in all_fill_timings if 10 < t <= 30])} fills")
    print(f"      30-60s: {len([t for t in all_fill_timings if 30 < t <= 60])} fills")

conn.close()

print(f"\n{'=' * 120}\n")
