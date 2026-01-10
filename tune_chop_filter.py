"""
Parameter tuning script for chop filter.
Tests different threshold combinations to find optimal values.
"""

import sys
import psycopg2
from datetime import datetime, timedelta
import numpy as np
from collections import deque

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

# Test period: Last 24 hours
end_time = datetime(2026, 1, 1, 7, 0, 0)
start_time = end_time - timedelta(hours=24)

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

print("=" * 120)
print("CHOP FILTER PARAMETER TUNING")
print("=" * 120)
print(f"\nDataset: {len(rows)} snapshots ({len(rows)/60:.1f} minutes)")

# Parameter grid to test
persistence_thresholds = [0.5, 0.55, 0.6, 0.65, 0.7]
symmetry_thresholds = [0.5, 0.55, 0.6, 0.65, 0.7]
range_eff_thresholds = [0.3, 0.4, 0.5, 0.6]
min_conditions = [2, 3]  # 2/3 or 3/3

results = []

total_tests = len(persistence_thresholds) * len(symmetry_thresholds) * len(range_eff_thresholds) * len(min_conditions)
test_num = 0

print(f"\nTesting {total_tests} parameter combinations...\n")

for persist_thresh in persistence_thresholds:
    for sym_thresh in symmetry_thresholds:
        for range_thresh in range_eff_thresholds:
            for min_cond in min_conditions:
                test_num += 1
                
                # Simulate detector with these parameters
                price_history = deque(maxlen=300)
                imbalance_history = deque(maxlen=300)
                bid_depth_history = deque(maxlen=300)
                ask_depth_history = deque(maxlen=300)
                
                chop_count = 0
                trend_count = 0
                
                for i, row in enumerate(rows):
                    timestamp, best_bid, best_ask, imbalance, bid_vol, ask_vol, spread_pct = row
                    
                    price = (float(best_bid) + float(best_ask)) / 2
                    price_history.append(price)
                    imbalance_history.append(float(imbalance) if imbalance else 0)
                    bid_depth_history.append(float(bid_vol) if bid_vol else 0)
                    ask_depth_history.append(float(ask_vol) if ask_vol else 0)
                    
                    # Check every 60 snapshots
                    if i % 60 == 0 and len(price_history) >= 60:
                        recent_prices = list(price_history)[-60:]
                        recent_imbalances = list(imbalance_history)[-60:]
                        recent_bid_depth = list(bid_depth_history)[-60:]
                        recent_ask_depth = list(ask_depth_history)[-60:]
                        
                        # Calculate metrics
                        sign_changes = sum(1 for j in range(1, len(recent_imbalances))
                                         if (recent_imbalances[j] > 0) != (recent_imbalances[j-1] > 0))
                        imbalance_persistence = 1.0 - (sign_changes / 60.0)
                        
                        avg_bid_depth = sum(recent_bid_depth) / len(recent_bid_depth)
                        avg_ask_depth = sum(recent_ask_depth) / len(recent_ask_depth)
                        
                        if avg_bid_depth > 0 and avg_ask_depth > 0:
                            liquidity_symmetry = min(avg_bid_depth, avg_ask_depth) / max(avg_bid_depth, avg_ask_depth)
                        else:
                            liquidity_symmetry = 0.5
                        
                        total_range = max(recent_prices) - min(recent_prices)
                        directional_move = abs(recent_prices[-1] - recent_prices[0])
                        
                        if total_range < 0.0001:
                            is_choppy = False
                        else:
                            range_efficiency = directional_move / total_range if total_range > 0 else 1.0
                            
                            # Test with current parameters
                            choppy_signals = 0
                            if imbalance_persistence < persist_thresh:
                                choppy_signals += 1
                            if liquidity_symmetry > sym_thresh:
                                choppy_signals += 1
                            if range_efficiency < range_thresh:
                                choppy_signals += 1
                            
                            is_choppy = choppy_signals >= min_cond
                        
                        if is_choppy:
                            chop_count += 1
                        else:
                            trend_count += 1
                
                total_checks = chop_count + trend_count
                choppy_pct = (chop_count / total_checks * 100) if total_checks > 0 else 0
                
                results.append({
                    'persist': persist_thresh,
                    'symmetry': sym_thresh,
                    'range_eff': range_thresh,
                    'min_cond': min_cond,
                    'choppy_pct': choppy_pct,
                    'chop_count': chop_count,
                    'trend_count': trend_count
                })
                
                if test_num % 20 == 0:
                    print(f"Progress: {test_num}/{total_tests} tests completed...")

# Sort by choppy percentage (target: 20-40%)
results.sort(key=lambda x: abs(x['choppy_pct'] - 30))  # Closest to 30%

print(f"\n{'=' * 120}")
print("TOP 10 PARAMETER COMBINATIONS (Closest to 30% choppy)")
print(f"{'=' * 120}\n")

print(f"{'Rank':<6} {'Persist':<8} {'Symmetry':<10} {'RangeEff':<10} {'MinCond':<8} {'Choppy%':<10} {'Chop/Trend':<15}")
print("-" * 120)

for i, result in enumerate(results[:10], 1):
    print(f"{i:<6} {result['persist']:<8.2f} {result['symmetry']:<10.2f} {result['range_eff']:<10.2f} "
          f"{result['min_cond']:<8} {result['choppy_pct']:<10.1f} "
          f"{result['chop_count']}/{result['trend_count']}")

print(f"\n{'=' * 120}")
print("ANALYSIS")
print(f"{'=' * 120}\n")

best = results[0]
print(f"RECOMMENDED PARAMETERS:")
print(f"  imbalance_persistence < {best['persist']}")
print(f"  liquidity_symmetry > {best['symmetry']}")
print(f"  range_efficiency < {best['range_eff']}")
print(f"  min_conditions: {best['min_cond']}/3")
print(f"\nExpected choppy detection: {best['choppy_pct']:.1f}%")

# Show distribution
print(f"\nDISTRIBUTION OF RESULTS:")
ranges = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 100)]
for low, high in ranges:
    count = sum(1 for r in results if low <= r['choppy_pct'] < high)
    bar = '█' * (count // 5)
    print(f"  {low:3d}-{high:3d}%: {count:3d} combinations {bar}")

conn.close()
