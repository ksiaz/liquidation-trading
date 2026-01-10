"""
Deep dive into raw orderbook data to find mathematical patterns
that describe the pre-move setup and the actual move.
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

# Focus on the critical periods
pre_move = (datetime(2026, 1, 1, 4, 30, 0), datetime(2026, 1, 1, 4, 40, 0))
move = (datetime(2026, 1, 1, 4, 40, 0), datetime(2026, 1, 1, 5, 17, 0))
pivot = (datetime(2026, 1, 1, 5, 17, 0), datetime(2026, 1, 1, 5, 27, 0))

symbol = 'BTCUSDT'

# Get ALL orderbook fields
query = """
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        imbalance,
        bid_volume_10,
        ask_volume_10,
        spread_pct,
        bid_volume_20,
        ask_volume_20
    FROM orderbook_snapshots
    WHERE symbol = %s
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
"""

print("=" * 120)
print("RAW ORDERBOOK DATA ANALYSIS - FINDING MATHEMATICAL PATTERNS")
print("=" * 120)

def analyze_raw_data(start, end, phase_name):
    """Extract and analyze raw orderbook patterns"""
    cur = conn.cursor()
    cur.execute(query, (symbol, start, end))
    rows = cur.fetchall()
    
    if not rows:
        print(f"\n⚠️ No data for {phase_name}")
        return
    
    print(f"\n{'=' * 120}")
    print(f"{phase_name} - {len(rows)} snapshots")
    print(f"{'=' * 120}")
    
    # Convert to arrays for analysis
    data = {
        'timestamp': [r[0] for r in rows],
        'bid': np.array([float(r[1]) for r in rows]),
        'ask': np.array([float(r[2]) for r in rows]),
        'imbalance': np.array([float(r[3]) if r[3] else 0 for r in rows]),
        'bid_vol_10': np.array([float(r[4]) if r[4] else 0 for r in rows]),
        'ask_vol_10': np.array([float(r[5]) if r[5] else 0 for r in rows]),
        'spread': np.array([float(r[6]) if r[6] else 0 for r in rows]),
        'bid_vol_20': np.array([float(r[7]) if r[7] else 0 for r in rows]),
        'ask_vol_20': np.array([float(r[8]) if r[8] else 0 for r in rows]),
    }
    
    # Calculate derived metrics
    data['mid'] = (data['bid'] + data['ask']) / 2
    data['price_change'] = np.diff(data['mid'], prepend=data['mid'][0])
    data['price_velocity'] = data['price_change'] / 1.0  # per second
    data['price_acceleration'] = np.diff(data['price_velocity'], prepend=data['price_velocity'][0])
    
    # Volume metrics
    data['total_bid_vol'] = data['bid_vol_10'] + data['bid_vol_20']
    data['total_ask_vol'] = data['ask_vol_10'] + data['ask_vol_20']
    data['total_vol'] = data['total_bid_vol'] + data['total_ask_vol']
    data['vol_imbalance'] = (data['total_bid_vol'] - data['total_ask_vol']) / (data['total_bid_vol'] + data['total_ask_vol'] + 1e-10)
    
    # Depth changes
    data['bid_vol_change'] = np.diff(data['bid_vol_10'], prepend=data['bid_vol_10'][0])
    data['ask_vol_change'] = np.diff(data['ask_vol_10'], prepend=data['ask_vol_10'][0])
    
    # Spread dynamics
    data['spread_change'] = np.diff(data['spread'], prepend=data['spread'][0])
    
    print(f"\n📊 PRICE DYNAMICS:")
    print(f"   Start Price:     ${data['mid'][0]:,.2f}")
    print(f"   End Price:       ${data['mid'][-1]:,.2f}")
    print(f"   Change:          {((data['mid'][-1] - data['mid'][0]) / data['mid'][0] * 100):+.3f}%")
    print(f"   Avg Velocity:    ${np.mean(data['price_velocity']):.4f}/s")
    print(f"   Max Velocity:    ${np.max(np.abs(data['price_velocity'])):.4f}/s")
    print(f"   Avg Accel:       ${np.mean(data['price_acceleration']):.6f}/s²")
    
    print(f"\n⚖️  IMBALANCE PATTERNS:")
    print(f"   Mean:            {np.mean(data['imbalance']):+.4f}")
    print(f"   Std Dev:         {np.std(data['imbalance']):.4f}")
    print(f"   Trend (slope):   {np.polyfit(range(len(data['imbalance'])), data['imbalance'], 1)[0]:.6f}")
    
    # Detect imbalance regime shifts
    imb_rolling_mean = pd.Series(data['imbalance']).rolling(window=30).mean().values
    imb_regime_changes = np.sum(np.abs(np.diff(np.sign(imb_rolling_mean))) > 0)
    print(f"   Regime Changes:  {imb_regime_changes} (30s window)")
    
    print(f"\n💧 VOLUME DYNAMICS:")
    print(f"   Bid Vol (avg):   {np.mean(data['bid_vol_10']):.2f}")
    print(f"   Ask Vol (avg):   {np.mean(data['ask_vol_10']):.2f}")
    print(f"   Vol Imbalance:   {np.mean(data['vol_imbalance']):+.4f}")
    print(f"   Bid Vol Trend:   {np.polyfit(range(len(data['bid_vol_10'])), data['bid_vol_10'], 1)[0]:+.4f}/s")
    print(f"   Ask Vol Trend:   {np.polyfit(range(len(data['ask_vol_10'])), data['ask_vol_10'], 1)[0]:+.4f}/s")
    
    # Detect volume exhaustion
    bid_vol_declining = np.polyfit(range(len(data['bid_vol_10'])), data['bid_vol_10'], 1)[0] < -0.01
    ask_vol_building = np.polyfit(range(len(data['ask_vol_10'])), data['ask_vol_10'], 1)[0] > 0.01
    print(f"   Bid Exhaustion:  {'YES' if bid_vol_declining else 'NO'}")
    print(f"   Ask Building:    {'YES' if ask_vol_building else 'NO'}")
    
    print(f"\n📏 SPREAD BEHAVIOR:")
    print(f"   Mean Spread:     {np.mean(data['spread']):.6f}%")
    print(f"   Spread Trend:    {np.polyfit(range(len(data['spread'])), data['spread'], 1)[0]:.8f}")
    print(f"   Spread Volatility: {np.std(data['spread']):.8f}")
    
    print(f"\n🔍 PATTERN DETECTION:")
    
    # 1. Depth divergence (price vs depth)
    price_direction = np.sign(data['mid'][-1] - data['mid'][0])
    bid_vol_direction = np.sign(np.mean(data['bid_vol_10'][-30:]) - np.mean(data['bid_vol_10'][:30]))
    ask_vol_direction = np.sign(np.mean(data['ask_vol_10'][-30:]) - np.mean(data['ask_vol_10'][:30]))
    
    depth_divergence = False
    if price_direction > 0 and ask_vol_direction > 0:  # Price up but ask building
        depth_divergence = True
        print(f"   ⚠️  BEARISH DIVERGENCE: Price rising but ask depth building")
    elif price_direction < 0 and bid_vol_direction > 0:  # Price down but bid building
        depth_divergence = True
        print(f"   ⚠️  BULLISH DIVERGENCE: Price falling but bid depth building")
    else:
        print(f"   ✓ No depth divergence")
    
    # 2. Imbalance momentum
    imb_early = np.mean(data['imbalance'][:len(data['imbalance'])//3])
    imb_late = np.mean(data['imbalance'][-len(data['imbalance'])//3:])
    imb_momentum = imb_late - imb_early
    print(f"   Imbalance Momentum: {imb_momentum:+.4f} ({'ACCELERATING' if abs(imb_momentum) > 0.2 else 'STABLE'})")
    
    # 3. Volume exhaustion pattern
    bid_early = np.mean(data['bid_vol_10'][:len(data['bid_vol_10'])//3])
    bid_late = np.mean(data['bid_vol_10'][-len(data['bid_vol_10'])//3:])
    bid_exhaustion_pct = ((bid_late - bid_early) / bid_early * 100) if bid_early > 0 else 0
    
    ask_early = np.mean(data['ask_vol_10'][:len(data['ask_vol_10'])//3])
    ask_late = np.mean(data['ask_vol_10'][-len(data['ask_vol_10'])//3:])
    ask_exhaustion_pct = ((ask_late - ask_early) / ask_early * 100) if ask_early > 0 else 0
    
    print(f"   Bid Vol Change:  {bid_exhaustion_pct:+.1f}% ({'EXHAUSTED' if bid_exhaustion_pct < -10 else 'BUILDING' if bid_exhaustion_pct > 10 else 'STABLE'})")
    print(f"   Ask Vol Change:  {ask_exhaustion_pct:+.1f}% ({'EXHAUSTED' if ask_exhaustion_pct < -10 else 'BUILDING' if ask_exhaustion_pct > 10 else 'STABLE'})")
    
    # 4. Price-volume correlation
    price_vol_corr = np.corrcoef(data['price_change'], data['total_vol'])[0, 1]
    print(f"   Price-Volume Corr: {price_vol_corr:+.3f}")
    
    # 5. Imbalance-price correlation
    imb_price_corr = np.corrcoef(data['imbalance'], data['price_change'])[0, 1]
    print(f"   Imbalance-Price Corr: {imb_price_corr:+.3f}")
    
    print(f"\n🎯 SIGNAL STRENGTH INDICATORS:")
    
    # Calculate composite signal strength
    signals = []
    
    if depth_divergence:
        signals.append("DEPTH_DIVERGENCE")
    
    if abs(imb_momentum) > 0.3:
        signals.append(f"IMB_MOMENTUM_{'+' if imb_momentum > 0 else '-'}")
    
    if bid_exhaustion_pct < -15:
        signals.append("BID_EXHAUSTION")
    
    if ask_exhaustion_pct < -15:
        signals.append("ASK_EXHAUSTION")
    
    if abs(imb_price_corr) > 0.5:
        signals.append(f"IMB_PRICE_SYNC_{'+' if imb_price_corr > 0 else '-'}")
    
    print(f"   Active Signals: {len(signals)}")
    for sig in signals:
        print(f"      • {sig}")
    
    if len(signals) == 0:
        print(f"      (No strong signals detected)")
    
    return {
        'depth_divergence': depth_divergence,
        'imb_momentum': imb_momentum,
        'bid_exhaustion_pct': bid_exhaustion_pct,
        'ask_exhaustion_pct': ask_exhaustion_pct,
        'imb_price_corr': imb_price_corr,
        'signals': signals
    }

# Analyze each phase
pre_results = analyze_raw_data(*pre_move, "PRE-MOVE (04:30-04:40)")
move_results = analyze_raw_data(*move, "THE MOVE (04:40-05:17)")
pivot_results = analyze_raw_data(*pivot, "PIVOT (05:17-05:27)")

print(f"\n{'=' * 120}")
print("SUMMARY: WHAT MATHEMATICAL PATTERNS DESCRIBE THIS MOVE?")
print(f"{'=' * 120}")

print(f"\n🔬 PRE-MOVE SIGNATURE:")
if pre_results and pre_results['signals']:
    for sig in pre_results['signals']:
        print(f"   ✓ {sig}")
else:
    print(f"   ⚠️ No clear pre-move signals detected")

print(f"\n📉 MOVE SIGNATURE:")
if move_results and move_results['signals']:
    for sig in move_results['signals']:
        print(f"   ✓ {sig}")
else:
    print(f"   ⚠️ No clear move signals detected")

print(f"\n🔄 PIVOT SIGNATURE:")
if pivot_results and pivot_results['signals']:
    for sig in pivot_results['signals']:
        print(f"   ✓ {sig}")
else:
    print(f"   ⚠️ No clear pivot signals detected")

conn.close()

print(f"\n{'=' * 120}\n")
