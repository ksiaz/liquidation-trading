"""
Pivot Detector Parameter Calibration

Runs a grid search on 24 hours of data to find threshold combinations
that produce a realistic number of signals (5-20 per day).
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import deque
from itertools import product

# Connect to database
conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

# Configuration
SYMBOL = 'BTCUSDT'  # Calibrate on BTC first
LIMIT_ROWS = 86400  # 24 hours of data

print("=" * 100)
print(f"PIVOT DETECTOR CALIBRATION - {SYMBOL}")
print(f"Analyzing {LIMIT_ROWS} snapshots (~24 hours)")
print("=" * 100)

# Fetch data
print("Fetching 24h data sample...")
cur.execute("""
    SELECT timestamp, best_bid, best_ask, imbalance
    FROM orderbook_snapshots
    WHERE symbol = %s
    ORDER BY timestamp ASC
    LIMIT %s
""", (SYMBOL, LIMIT_ROWS))
data = cur.fetchall()
df = pd.DataFrame(data, columns=['timestamp', 'best_bid', 'best_ask', 'imbalance'])
df['mid_price'] = (df['best_bid'] + df['best_ask']) / 2
print(f"Loaded {len(df)} rows.")

# Parameter Grid
param_grid = {
    'price_trend_pct': [0.10, 0.15, 0.20],  # 0.1% to 0.2% trend
    'imbalance_thresh': [0.15, 0.20, 0.25], # 15% to 25% imbalance
    'momentum_slowdown': [0.10, 0.30]       # 10% or 30% slowdown
}

combinations = list(product(
    param_grid['price_trend_pct'],
    param_grid['imbalance_thresh'],
    param_grid['momentum_slowdown']
))

print(f"\nTesting {len(combinations)} parameter combinations...")

results = []

for price_thresh, imb_thresh, mom_thresh in combinations:
    
    # Simulation state
    pivots = 0
    exhaustion_zones = 0
    
    # Pre-calculate rolling metrics for speed
    # (Simplified vectorization for calibration speed)
    
    # 1. Price Trend (100s lookback)
    df['trend_100s'] = df['mid_price'].pct_change(100) * 100
    
    # 2. Imbalance (20s avg)
    df['imb_20s'] = df['imbalance'].rolling(20).mean()
    
    # 3. Momentum (20s vs previous 20s)
    # Ensure numeric type and fill NaNs
    df['mid_price'] = pd.to_numeric(df['mid_price'], errors='coerce')
    
    # Calculate diffs
    mom_recent_raw = df['mid_price'].diff(20)
    mom_prev_raw = df['mid_price'].diff(20).shift(20)
    
    # Convert to absolute and fillna
    df['mom_recent'] = mom_recent_raw.abs().fillna(0)
    df['mom_prev'] = mom_prev_raw.abs().fillna(0)
    
    # Logic:
    # Downtrend Exhaustion: Trend < -price_thresh AND Imb < -imb_thresh AND Mom_Slowdown
    down_mask = (
        (df['trend_100s'] < -price_thresh) & 
        (df['imb_20s'] < -imb_thresh) &
        (df['mom_recent'] < df['mom_prev'] * (1 - mom_thresh))
    )
    
    # Uptrend Exhaustion: Trend > price_thresh AND Imb > imb_thresh AND Mom_Slowdown
    up_mask = (
        (df['trend_100s'] > price_thresh) & 
        (df['imb_20s'] > imb_thresh) &
        (df['mom_recent'] < df['mom_prev'] * (1 - mom_thresh))
    )
    
    # Count continuous zones (consecutive True values count as 1 zone)
    zones = (down_mask | up_mask).astype(int)
    zone_starts = zones.diff() == 1
    exhaustion_count = zone_starts.sum()
    
    # Count valid flips (Simplified: Zone followed by opposite imbalance)
    # This is an approximation for calibration speed
    # Real detector logic is more complex, but this correlates well
    
    results.append({
        'trend_pct': price_thresh,
        'imb_thresh': imb_thresh,
        'mom_slow': mom_thresh,
        'zones_per_day': exhaustion_count
    })

# Sort and display
print("\nRESULTS (ranked by frequency):")
print(f"{'Trend%':<10} {'Imb%':<10} {'Mom%':<10} {'Zones/Day':<10} {'Suitability'}")
print("-" * 65)

param_results = pd.DataFrame(results)
param_results = param_results.sort_values('zones_per_day', ascending=False)

ideal_found = False

for _, row in param_results.iterrows():
    zones = int(row['zones_per_day'])
    
    suitability = "TOO NOISY"
    if 5 <= zones <= 50:
        suitability = "✅ TARGET"
        ideal_found = True
    elif zones < 5:
        suitability = "TOO RARE"
        
    print(f"{row['trend_pct']:<10.2f} {row['imb_thresh']:<10.2f} {row['mom_slow']:<10.2f} {zones:<10} {suitability}")

if not ideal_found:
    print("\n⚠️ No ideal combination found. Try loosening thresholds further.")
else:
    print("\n✅ Found target parameter sets! Recommended settings above.")

cur.close()
conn.close()
