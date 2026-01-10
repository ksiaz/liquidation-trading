"""
Analyze imbalance flips and order manipulation patterns
during the -0.47% move period.

Focus on:
1. Imbalance sign flips (bid-heavy → ask-heavy)
2. Sudden volume spikes (large order appearances)
3. Volume withdrawal patterns (spoofing)
4. Depth asymmetry changes
"""

import psycopg2
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)

# Analyze the critical period
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
print("IMBALANCE FLIP & MANIPULATION PATTERN ANALYSIS")
print("=" * 120)
print(f"\nAnalyzing {len(rows)} snapshots from {start_time} to {end_time}")

# Convert to arrays
timestamps = [r[0] for r in rows]
mid_prices = np.array([(float(r[1]) + float(r[2])) / 2 for r in rows])
imbalances = np.array([float(r[3]) if r[3] else 0 for r in rows])
bid_vol_10 = np.array([float(r[4]) if r[4] else 0 for r in rows])
ask_vol_10 = np.array([float(r[5]) if r[5] else 0 for r in rows])
bid_vol_20 = np.array([float(r[6]) if r[6] else 0 for r in rows])
ask_vol_20 = np.array([float(r[7]) if r[7] else 0 for r in rows])

# Calculate total volumes
total_bid = bid_vol_10 + bid_vol_20
total_ask = ask_vol_10 + ask_vol_20

print(f"\n{'=' * 120}")
print("1. IMBALANCE FLIP DETECTION")
print(f"{'=' * 120}")

# Detect sign flips
imb_signs = np.sign(imbalances)
flips = np.where(np.diff(imb_signs) != 0)[0]

print(f"\nTotal imbalance flips: {len(flips)}")
print(f"Flip frequency: {len(flips) / (len(rows) / 60):.1f} flips/minute")

# Analyze significant flips (large magnitude change)
significant_flips = []
for i in flips:
    if i > 0 and i < len(imbalances) - 1:
        before = imbalances[i]
        after = imbalances[i + 1]
        magnitude = abs(after - before)
        
        if magnitude > 0.5:  # Significant flip
            price_change = mid_prices[i + 1] - mid_prices[i]
            significant_flips.append({
                'index': i,
                'time': timestamps[i + 1],
                'before': before,
                'after': after,
                'magnitude': magnitude,
                'price_change': price_change,
                'price': mid_prices[i + 1]
            })

print(f"\nSignificant flips (magnitude > 0.5): {len(significant_flips)}")

if significant_flips:
    print(f"\nTop 10 largest flips:")
    print(f"{'Time':<20} {'Before':<10} {'After':<10} {'Magnitude':<12} {'Price':<12} {'Price Δ':<10}")
    print("-" * 90)
    
    sorted_flips = sorted(significant_flips, key=lambda x: x['magnitude'], reverse=True)[:10]
    for flip in sorted_flips:
        print(f"{flip['time'].strftime('%H:%M:%S'):<20} "
              f"{flip['before']:>+9.3f} {flip['after']:>+9.3f} "
              f"{flip['magnitude']:>11.3f} ${flip['price']:>10,.2f} "
              f"{flip['price_change']:>+9.2f}")

print(f"\n{'=' * 120}")
print("2. SUDDEN VOLUME SPIKE DETECTION (Large Order Appearances)")
print(f"{'=' * 120}")

# Calculate volume changes
bid_vol_changes = np.diff(total_bid, prepend=total_bid[0])
ask_vol_changes = np.diff(total_ask, prepend=total_ask[0])

# Detect spikes (> 3 std deviations)
bid_mean = np.mean(bid_vol_changes)
bid_std = np.std(bid_vol_changes)
ask_mean = np.mean(ask_vol_changes)
ask_std = np.std(ask_vol_changes)

bid_spikes = np.where(bid_vol_changes > bid_mean + 3 * bid_std)[0]
ask_spikes = np.where(ask_vol_changes > ask_mean + 3 * ask_std)[0]

print(f"\nBid volume spikes (>3σ): {len(bid_spikes)}")
print(f"Ask volume spikes (>3σ): {len(ask_spikes)}")

# Analyze spike impact on price
bid_spike_events = []
for i in bid_spikes:
    if i < len(mid_prices) - 5:
        spike_size = bid_vol_changes[i]
        price_before = mid_prices[i]
        price_after_1s = mid_prices[min(i + 1, len(mid_prices) - 1)]
        price_after_5s = mid_prices[min(i + 5, len(mid_prices) - 1)]
        
        bid_spike_events.append({
            'time': timestamps[i],
            'spike_size': spike_size,
            'spike_pct': (spike_size / total_bid[i - 1] * 100) if i > 0 and total_bid[i - 1] > 0 else 0,
            'price_impact_1s': ((price_after_1s - price_before) / price_before * 100),
            'price_impact_5s': ((price_after_5s - price_before) / price_before * 100)
        })

ask_spike_events = []
for i in ask_spikes:
    if i < len(mid_prices) - 5:
        spike_size = ask_vol_changes[i]
        price_before = mid_prices[i]
        price_after_1s = mid_prices[min(i + 1, len(mid_prices) - 1)]
        price_after_5s = mid_prices[min(i + 5, len(mid_prices) - 1)]
        
        ask_spike_events.append({
            'time': timestamps[i],
            'spike_size': spike_size,
            'spike_pct': (spike_size / total_ask[i - 1] * 100) if i > 0 and total_ask[i - 1] > 0 else 0,
            'price_impact_1s': ((price_after_1s - price_before) / price_before * 100),
            'price_impact_5s': ((price_after_5s - price_before) / price_before * 100)
        })

if bid_spike_events:
    print(f"\nTop 5 BID spikes:")
    print(f"{'Time':<20} {'Spike Size':<12} {'Spike %':<10} {'Impact 1s':<12} {'Impact 5s':<12}")
    print("-" * 80)
    sorted_bids = sorted(bid_spike_events, key=lambda x: x['spike_size'], reverse=True)[:5]
    for event in sorted_bids:
        print(f"{event['time'].strftime('%H:%M:%S'):<20} "
              f"{event['spike_size']:>11.2f} {event['spike_pct']:>9.1f}% "
              f"{event['price_impact_1s']:>+11.3f}% {event['price_impact_5s']:>+11.3f}%")

if ask_spike_events:
    print(f"\nTop 5 ASK spikes:")
    print(f"{'Time':<20} {'Spike Size':<12} {'Spike %':<10} {'Impact 1s':<12} {'Impact 5s':<12}")
    print("-" * 80)
    sorted_asks = sorted(ask_spike_events, key=lambda x: x['spike_size'], reverse=True)[:5]
    for event in sorted_asks:
        print(f"{event['time'].strftime('%H:%M:%S'):<20} "
              f"{event['spike_size']:>11.2f} {event['spike_pct']:>9.1f}% "
              f"{event['price_impact_1s']:>+11.3f}% {event['price_impact_5s']:>+11.3f}%")

print(f"\n{'=' * 120}")
print("3. VOLUME WITHDRAWAL DETECTION (Spoofing)")
print(f"{'=' * 120}")

# Detect sudden withdrawals (> 3 std deviations negative)
bid_withdrawals = np.where(bid_vol_changes < bid_mean - 3 * bid_std)[0]
ask_withdrawals = np.where(ask_vol_changes < ask_mean - 3 * ask_std)[0]

print(f"\nBid volume withdrawals (>3σ): {len(bid_withdrawals)}")
print(f"Ask volume withdrawals (>3σ): {len(ask_withdrawals)}")

# Check for spoof patterns (spike followed by withdrawal within 5s)
spoof_patterns = []

for spike_idx in bid_spikes:
    # Look for withdrawal within next 5 snapshots
    for withdraw_idx in bid_withdrawals:
        if spike_idx < withdraw_idx <= spike_idx + 5:
            spoof_patterns.append({
                'side': 'BID',
                'spike_time': timestamps[spike_idx],
                'withdraw_time': timestamps[withdraw_idx],
                'duration': (timestamps[withdraw_idx] - timestamps[spike_idx]).total_seconds(),
                'spike_size': bid_vol_changes[spike_idx],
                'withdraw_size': abs(bid_vol_changes[withdraw_idx])
            })

for spike_idx in ask_spikes:
    for withdraw_idx in ask_withdrawals:
        if spike_idx < withdraw_idx <= spike_idx + 5:
            spoof_patterns.append({
                'side': 'ASK',
                'spike_time': timestamps[spike_idx],
                'withdraw_time': timestamps[withdraw_idx],
                'duration': (timestamps[withdraw_idx] - timestamps[spike_idx]).total_seconds(),
                'spike_size': ask_vol_changes[spike_idx],
                'withdraw_size': abs(ask_vol_changes[withdraw_idx])
            })

print(f"\nPotential spoof patterns detected: {len(spoof_patterns)}")

if spoof_patterns:
    print(f"\nSpoof events (spike → withdrawal within 5s):")
    print(f"{'Side':<6} {'Spike Time':<20} {'Withdraw Time':<20} {'Duration':<10} {'Spike':<10} {'Withdraw':<10}")
    print("-" * 90)
    for pattern in spoof_patterns[:10]:
        print(f"{pattern['side']:<6} "
              f"{pattern['spike_time'].strftime('%H:%M:%S'):<20} "
              f"{pattern['withdraw_time'].strftime('%H:%M:%S'):<20} "
              f"{pattern['duration']:>9.1f}s "
              f"{pattern['spike_size']:>9.2f} "
              f"{pattern['withdraw_size']:>9.2f}")

print(f"\n{'=' * 120}")
print("4. DEPTH ASYMMETRY ANALYSIS")
print(f"{'=' * 120}")

# Calculate depth ratio
depth_ratio = total_bid / (total_ask + 1e-10)

# Detect extreme asymmetries
extreme_bid_heavy = np.where(depth_ratio > 3.0)[0]  # 3x more bids
extreme_ask_heavy = np.where(depth_ratio < 0.33)[0]  # 3x more asks

print(f"\nExtreme bid-heavy moments (>3:1): {len(extreme_bid_heavy)}")
print(f"Extreme ask-heavy moments (<1:3): {len(extreme_ask_heavy)}")

# Analyze what happens after extreme asymmetries
if len(extreme_bid_heavy) > 0:
    print(f"\nAfter extreme bid-heavy (top 5):")
    print(f"{'Time':<20} {'Ratio':<10} {'Price Δ 5s':<15} {'Price Δ 30s':<15}")
    print("-" * 70)
    
    for i in extreme_bid_heavy[:5]:
        if i < len(mid_prices) - 30:
            ratio = depth_ratio[i]
            price_5s = ((mid_prices[min(i + 5, len(mid_prices) - 1)] - mid_prices[i]) / mid_prices[i] * 100)
            price_30s = ((mid_prices[min(i + 30, len(mid_prices) - 1)] - mid_prices[i]) / mid_prices[i] * 100)
            print(f"{timestamps[i].strftime('%H:%M:%S'):<20} {ratio:>9.2f} {price_5s:>+14.3f}% {price_30s:>+14.3f}%")

if len(extreme_ask_heavy) > 0:
    print(f"\nAfter extreme ask-heavy (top 5):")
    print(f"{'Time':<20} {'Ratio':<10} {'Price Δ 5s':<15} {'Price Δ 30s':<15}")
    print("-" * 70)
    
    for i in extreme_ask_heavy[:5]:
        if i < len(mid_prices) - 30:
            ratio = depth_ratio[i]
            price_5s = ((mid_prices[min(i + 5, len(mid_prices) - 1)] - mid_prices[i]) / mid_prices[i] * 100)
            price_30s = ((mid_prices[min(i + 30, len(mid_prices) - 1)] - mid_prices[i]) / mid_prices[i] * 100)
            print(f"{timestamps[i].strftime('%H:%M:%S'):<20} {ratio:>9.2f} {price_5s:>+14.3f}% {price_30s:>+14.3f}%")

print(f"\n{'=' * 120}")
print("SUMMARY: ACTIONABLE PATTERNS")
print(f"{'=' * 120}")

print(f"\n🎯 PATTERN 1: Imbalance Flip + Volume Spike")
print(f"   Detection: Imbalance flips >0.5 magnitude + volume spike >3σ")
print(f"   Found: {len([f for f in significant_flips if any(abs(f['index'] - s) <= 2 for s in list(bid_spikes) + list(ask_spikes))])} events")

print(f"\n🎯 PATTERN 2: Spoofing (Spike → Withdrawal)")
print(f"   Detection: Large order appears then disappears <5s")
print(f"   Found: {len(spoof_patterns)} events")

print(f"\n🎯 PATTERN 3: Extreme Depth Asymmetry")
print(f"   Detection: Depth ratio >3:1 or <1:3")
print(f"   Found: {len(extreme_bid_heavy) + len(extreme_ask_heavy)} events")

print(f"\n🎯 PATTERN 4: Flip + Price Impact")
flip_with_impact = [f for f in significant_flips if abs(f['price_change']) > 5]
print(f"   Detection: Imbalance flip + immediate price move >$5")
print(f"   Found: {len(flip_with_impact)} events")

conn.close()

print(f"\n{'=' * 120}\n")
