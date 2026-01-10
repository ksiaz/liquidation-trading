"""
Analyze specific market move: BTC 04:40-05:17 downtrend (-0.47%)
Extract orderbook behavior during preparation, move, and pivot
"""

import psycopg2
from datetime import datetime, timedelta
import numpy as np
import sys

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
print("ANALYZING SPECIFIC MARKET MOVE: BTC 04:40-05:17 (Jan 1, 2026)")
print("=" * 100)

# Define periods
pre_move_start = datetime(2026, 1, 1, 4, 30, 0)
pre_move_end = datetime(2026, 1, 1, 4, 40, 0)
move_start = datetime(2026, 1, 1, 4, 40, 0)
move_end = datetime(2026, 1, 1, 5, 17, 0)
pivot_time = datetime(2026, 1, 1, 5, 17, 0)
post_pivot = datetime(2026, 1, 1, 5, 27, 0)

symbol = 'BTCUSDT'

# Get orderbook data for entire period
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
""", (symbol, pre_move_start, post_pivot))

rows = cur.fetchall()

print(f"\n📊 Retrieved {len(rows)} orderbook snapshots")
print(f"   Period: {pre_move_start} to {post_pivot}")

# Analyze each phase
def analyze_phase(phase_rows, phase_name):
    """Analyze orderbook behavior in a specific phase"""
    if not phase_rows:
        print(f"\n⚠️ No data for {phase_name}")
        return
    
    print(f"\n{'=' * 100}")
    print(f"{phase_name}")
    print(f"{'=' * 100}")
    
    prices = [(float(r[1]) + float(r[2])) / 2 for r in phase_rows]
    imbalances = [float(r[3]) if r[3] else 0 for r in phase_rows]
    bid_vols = [float(r[4]) if r[4] else 0 for r in phase_rows]
    ask_vols = [float(r[5]) if r[5] else 0 for r in phase_rows]
    spreads = [float(r[6]) if r[6] else 0 for r in phase_rows]
    
    # Price stats
    price_start = prices[0]
    price_end = prices[-1]
    price_change_pct = ((price_end - price_start) / price_start) * 100
    price_high = max(prices)
    price_low = min(prices)
    price_range = ((price_high - price_low) / price_start) * 100
    
    print(f"\n📈 PRICE ACTION:")
    print(f"   Start: ${price_start:,.2f}")
    print(f"   End:   ${price_end:,.2f}")
    print(f"   Change: {price_change_pct:+.3f}%")
    print(f"   Range:  {price_range:.3f}%")
    print(f"   High:  ${price_high:,.2f}")
    print(f"   Low:   ${price_low:,.2f}")
    
    # Imbalance stats
    imb_mean = np.mean(imbalances)
    imb_std = np.std(imbalances)
    imb_min = min(imbalances)
    imb_max = max(imbalances)
    
    # Count sign changes (choppiness indicator)
    sign_changes = sum(1 for i in range(1, len(imbalances))
                      if (imbalances[i] > 0) != (imbalances[i-1] > 0))
    imb_persistence = 1.0 - (sign_changes / len(imbalances))
    
    print(f"\n⚖️  IMBALANCE:")
    print(f"   Mean:        {imb_mean:+.4f}")
    print(f"   Std Dev:     {imb_std:.4f}")
    print(f"   Range:       {imb_min:+.4f} to {imb_max:+.4f}")
    print(f"   Sign Changes: {sign_changes}")
    print(f"   Persistence:  {imb_persistence:.2%} {'(TRENDING)' if imb_persistence > 0.6 else '(CHOPPY)'}")
    
    # Liquidity stats
    bid_mean = np.mean(bid_vols)
    ask_mean = np.mean(ask_vols)
    liq_symmetry = min(bid_mean, ask_mean) / max(bid_mean, ask_mean) if max(bid_mean, ask_mean) > 0 else 0
    
    print(f"\n💧 LIQUIDITY:")
    print(f"   Avg Bid Depth: {bid_mean:,.2f}")
    print(f"   Avg Ask Depth: {ask_mean:,.2f}")
    print(f"   Symmetry:      {liq_symmetry:.2%} {'(BALANCED)' if liq_symmetry > 0.6 else '(IMBALANCED)'}")
    
    # Spread stats
    spread_mean = np.mean(spreads)
    spread_std = np.std(spreads)
    
    print(f"\n📏 SPREAD:")
    print(f"   Mean:    {spread_mean:.4f}%")
    print(f"   Std Dev: {spread_std:.4f}%")
    
    # Range efficiency (directional move / total range)
    directional_move = abs(price_end - price_start)
    total_range = price_high - price_low
    range_efficiency = directional_move / total_range if total_range > 0 else 0
    
    print(f"\n🎯 RANGE EFFICIENCY:")
    print(f"   Directional: ${directional_move:,.2f}")
    print(f"   Total Range: ${total_range:,.2f}")
    print(f"   Efficiency:  {range_efficiency:.2%} {'(TRENDING)' if range_efficiency > 0.5 else '(CHOPPY)'}")
    
    # Chop filter verdict
    choppy_signals = 0
    if imb_persistence < 0.6:
        choppy_signals += 1
    if liq_symmetry > 0.6:
        choppy_signals += 1
    if range_efficiency < 0.5:
        choppy_signals += 1
    
    is_choppy = choppy_signals >= 2
    
    print(f"\n🔍 CHOP FILTER VERDICT:")
    print(f"   Choppy Signals: {choppy_signals}/3")
    print(f"   Status: {'❌ CHOPPY (would block)' if is_choppy else '✅ TRENDING (would allow)'}")
    
    return {
        'price_change_pct': price_change_pct,
        'imb_persistence': imb_persistence,
        'liq_symmetry': liq_symmetry,
        'range_efficiency': range_efficiency,
        'is_choppy': is_choppy
    }

# Split data by phase
pre_move_rows = [r for r in rows if pre_move_start <= r[0] < pre_move_end]
move_rows = [r for r in rows if move_start <= r[0] < move_end]
pivot_rows = [r for r in rows if pivot_time <= r[0] < post_pivot]

# Analyze each phase
pre_stats = analyze_phase(pre_move_rows, "PHASE 1: PRE-MOVE (04:30-04:40)")
move_stats = analyze_phase(move_rows, "PHASE 2: THE MOVE (04:40-05:17) - -0.47%")
pivot_stats = analyze_phase(pivot_rows, "PHASE 3: PIVOT & REVERSAL (05:17-05:27)")

# Summary
print(f"\n{'=' * 100}")
print("SUMMARY & DETECTOR ANALYSIS")
print(f"{'=' * 100}")

print(f"\n📋 PHASE COMPARISON:")
print(f"{'Metric':<25} {'Pre-Move':<15} {'The Move':<15} {'Pivot':<15}")
print("-" * 70)
if pre_stats and move_stats and pivot_stats:
    print(f"{'Price Change %':<25} {pre_stats['price_change_pct']:>+14.3f} {move_stats['price_change_pct']:>+14.3f} {pivot_stats['price_change_pct']:>+14.3f}")
    print(f"{'Imbalance Persistence':<25} {pre_stats['imb_persistence']:>14.2%} {move_stats['imb_persistence']:>14.2%} {pivot_stats['imb_persistence']:>14.2%}")
    print(f"{'Liquidity Symmetry':<25} {pre_stats['liq_symmetry']:>14.2%} {move_stats['liq_symmetry']:>14.2%} {pivot_stats['liq_symmetry']:>14.2%}")
    print(f"{'Range Efficiency':<25} {pre_stats['range_efficiency']:>14.2%} {move_stats['range_efficiency']:>14.2%} {pivot_stats['range_efficiency']:>14.2%}")
    print(f"{'Chop Filter':<25} {'BLOCK' if pre_stats['is_choppy'] else 'ALLOW':>14} {'BLOCK' if move_stats['is_choppy'] else 'ALLOW':>14} {'BLOCK' if pivot_stats['is_choppy'] else 'ALLOW':>14}")

print(f"\n🎯 KEY INSIGHTS:")
print(f"   1. Pre-Move: Should detector have warned of impending move?")
print(f"   2. The Move: Should detector have caught the trend?")
print(f"   3. Pivot: Should detector have signaled reversal?")

# Check if detector would have generated signals
print(f"\n🤖 DETECTOR SIMULATION:")
detector = EarlyReversalDetector(max_lookback_seconds=300, snr_threshold=0.15)

signals_generated = []
for i, row in enumerate(move_rows):
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
    
    signal = detector.update(orderbook_data)
    if signal:
        signals_generated.append({
            'time': timestamp,
            'direction': signal['direction'],
            'snr': signal['snr'],
            'confidence': signal['confidence']
        })

print(f"\n   Signals Generated During Move: {len(signals_generated)}")
if signals_generated:
    for sig in signals_generated:
        print(f"      {sig['time'].strftime('%H:%M:%S')} - {sig['direction']} (SNR: {sig['snr']:.2f}, Conf: {sig['confidence']}%)")
else:
    print(f"      ❌ No signals generated (chop filter or SNR threshold blocked)")

conn.close()

print(f"\n{'=' * 100}\n")
