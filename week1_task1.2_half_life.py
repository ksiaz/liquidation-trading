"""
Week 1 Task 1.2: Signal Half-Life Measurement
==============================================

Measures time-based metrics for signals:
- t_peak_MFE: Time to maximum favorable excursion (peak profit)
- t_reversion_50%: Time to 50% retracement from peak
- t_zero_PnL: Time back to breakeven

Per expert guidance:
"Signal half-life is massively underused. Measure t_peak_MFE for each symbol/session."

Expected ranges (Expert #2):
- BTC: 20-90 seconds
- ETH: 30-120 seconds  
- SOL: 10-40 seconds
"""

import psycopg2
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 100)
print("WEEK 1 TASK 1.2: SIGNAL HALF-LIFE MEASUREMENT")
print("=" * 100)
print("\n📊 Measuring time-based signal metrics:")
print("   - t_peak_MFE: Time to peak profit")
print("   - t_reversion_50%: Time to 50% retracement")
print("   - t_zero_PnL: Time back to breakeven")
print("\nGrouped by: (symbol, session, volatility regime)\n")

# Test period
end_time = datetime(2026, 1, 1, 7, 0, 0)
start_time = end_time - timedelta(hours=24)

symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Storage for half-life data
half_life_data = []

# Session classification (UTC)
def get_session(hour):
    """Classify hour into trading session."""
    if 0 <= hour < 8:
        return 'ASIA'
    elif 8 <= hour < 16:
        return 'EUROPE'
    else:
        return 'US'

for symbol in symbols:
    print(f"\n{'=' * 100}")
    print(f"ANALYZING {symbol}")
    print(f"{'=' * 100}")
    
    # Load orderbook data with price information
    cur.execute("""
        SELECT 
            timestamp,
            best_bid,
            best_ask,
            imbalance,
            bid_volume_10,
            ask_volume_10
        FROM orderbook_snapshots
        WHERE symbol = %s
        AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp
    """, (symbol, start_time, end_time))
    
    rows = cur.fetchall()
    
    if not rows:
        print(f"   ⚠️  No data for {symbol}")
        continue
    
    print(f"   📊 Processing {len(rows)} snapshots...")
    
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(rows, columns=['timestamp', 'best_bid', 'best_ask', 'imbalance', 'bid_vol', 'ask_vol'])
    df['midprice'] = (df['best_bid'] + df['best_ask']) / 2
    df['hour'] = df['timestamp'].apply(lambda x: x.hour)
    df['session'] = df['hour'].apply(get_session)
    
    # Calculate rolling volatility (5-minute window)
    df['returns'] = df['midprice'].pct_change()
    df['volatility_5m'] = df['returns'].rolling(window=300, min_periods=30).std() * np.sqrt(300)
    
    # Classify volatility regime
    vol_33 = df['volatility_5m'].quantile(0.33)
    vol_66 = df['volatility_5m'].quantile(0.66)
    
    def get_vol_regime(vol):
        if pd.isna(vol):
            return 'UNKNOWN'
        elif vol < vol_33:
            return 'LOW_VOL'
        elif vol < vol_66:
            return 'MED_VOL'
        else:
            return 'HIGH_VOL'
    
    df['vol_regime'] = df['volatility_5m'].apply(get_vol_regime)
    
    # Simulate signals using simple imbalance threshold
    # (In production, this would come from actual signal generator)
    signals = []
    
    for i in range(len(df) - 300):  # Need at least 5min of data ahead
        row = df.iloc[i]
        
        # Simple signal: large imbalance shift
        if i > 10:
            imb_current = float(row['imbalance']) if row['imbalance'] else 0
            imb_prev = float(df.iloc[i-10]['imbalance']) if df.iloc[i-10]['imbalance'] else 0
            imb_change = abs(imb_current - imb_prev)
            
            if imb_change > 0.3:  # Significant imbalance change
                direction = 'LONG' if imb_current > 0 else 'SHORT'
                
                signals.append({
                    'timestamp': row['timestamp'],
                    'entry_idx': i,
                    'entry_price': float(row['midprice']),
                    'direction': direction,
                    'session': row['session'],
                    'vol_regime': row['vol_regime']
                })
    
    print(f"   🎯 Generated {len(signals)} test signals")
    
    # Measure half-life for each signal
    for sig in signals:
        entry_idx = sig['entry_idx']
        entry_price = sig['entry_price']
        direction = sig['direction']
        
        # Look ahead up to 5 minutes (300 snapshots)
        lookhead_window = min(300, len(df) - entry_idx - 1)
        
        if lookhead_window < 30:  # Need at least 30s of data
            continue
        
        # Track P&L path
        pnl_path = []
        peak_mfe = 0
        peak_mfe_time = 0
        time_to_zero = None
        time_to_reversion_50 = None
        
        for t in range(1, lookhead_window + 1):
            current_price = float(df.iloc[entry_idx + t]['midprice'])
            
            # Calculate P&L
            if direction == 'LONG':
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            pnl_path.append(pnl_pct)
            
            # Track peak MFE
            if pnl_pct > peak_mfe:
                peak_mfe = pnl_pct
                peak_mfe_time = t
            
            # Check if returned to zero (after being profitable)
            if time_to_zero is None and peak_mfe > 0.05 and pnl_pct <= 0:
                time_to_zero = t
            
            # Check 50% retracement from peak
            if time_to_reversion_50 is None and peak_mfe > 0.1:
                if pnl_pct <= peak_mfe * 0.5:
                    time_to_reversion_50 = t
        
        # Only record if signal was profitable at some point
        if peak_mfe > 0.05:  # At least 5 bps profit
            half_life_data.append({
                'symbol': symbol,
                'session': sig['session'],
                'vol_regime': sig['vol_regime'],
                'direction': direction,
                't_peak_MFE': peak_mfe_time,
                'peak_MFE_value': peak_mfe,
                't_reversion_50pct': time_to_reversion_50 if time_to_reversion_50 else lookhead_window,
                't_zero_PnL': time_to_zero if time_to_zero else lookhead_window,
                'final_pnl': pnl_path[-1] if pnl_path else 0
            })
    
    print(f"   ✅ Recorded {len([d for d in half_life_data if d['symbol'] == symbol])} profitable signals with half-life metrics")

# ========================================================================================
# AGGREGATE ANALYSIS
# ========================================================================================

print(f"\n{'=' * 100}")
print("📊 SIGNAL HALF-LIFE ANALYSIS RESULTS")
print(f"{'=' * 100}")

if not half_life_data:
    print("\n❌ No profitable signals found in test period")
    conn.close()
    exit(0)

df_hl = pd.DataFrame(half_life_data)

print(f"\nTotal profitable signals analyzed: {len(df_hl)}")

# Overall statistics by symbol
print(f"\n{'=' * 100}")
print("BY SYMBOL (All Sessions)")
print(f"{'=' * 100}")

for symbol in symbols:
    symbol_data = df_hl[df_hl['symbol'] == symbol]
    
    if len(symbol_data) == 0:
        continue
    
    median_peak = symbol_data['t_peak_MFE'].median()
    median_reversion = symbol_data['t_reversion_50pct'].median()
    median_zero = symbol_data['t_zero_PnL'].median()
    
    print(f"\n{symbol}:")
    print(f"   Signals:           {len(symbol_data)}")
    print(f"   Median t_peak:     {median_peak:.0f}s")
    print(f"   Median t_reversion:{median_reversion:.0f}s")
    print(f"   Median t_zero:     {median_zero:.0f}s")
    print(f"   Avg peak MFE:      {symbol_data['peak_MFE_value'].mean():.3f}%")
    
    # Compare to expert predictions
    if symbol == 'BTCUSDT':
        expected = "20-90s"
    elif symbol == 'ETHUSDT':
        expected = "30-120s"
    else:  # SOL
        expected = "10-40s"
    
    print(f"   Expert predicted:  {expected}")
    if symbol == 'BTCUSDT':
        in_range = 20 <= median_peak <= 90
    elif symbol == 'ETHUSDT':
        in_range = 30 <= median_peak <= 120
    else:
        in_range = 10 <= median_peak <= 40
    
    print(f"   Match:             {'✅ YES' if in_range else '⚠️ Outside range'}")

# By session
print(f"\n{'=' * 100}")
print("BY SESSION (UTC Hours)")
print(f"{'=' * 100}")

for session in ['ASIA', 'EUROPE', 'US']:
    session_data = df_hl[df_hl['session'] == session]
    
    if len(session_data) == 0:
        continue
    
    print(f"\n{session}:")
    print(f"   Signals:           {len(session_data)}")
    print(f"   Median t_peak:     {session_data['t_peak_MFE'].median():.0f}s")
    print(f"   Median t_reversion:{session_data['t_reversion_50pct'].median():.0f}s")
    print(f"   Median t_zero:     {session_data['t_zero_PnL'].median():.0f}s")

# By volatility regime
print(f"\n{'=' * 100}")
print("BY VOLATILITY REGIME")
print(f"{'=' * 100}")

for vol_regime in ['LOW_VOL', 'MED_VOL', 'HIGH_VOL']:
    vol_data = df_hl[df_hl['vol_regime'] == vol_regime]
    
    if len(vol_data) == 0:
        continue
    
    print(f"\n{vol_regime}:")
    print(f"   Signals:           {len(vol_data)}")
    print(f"   Median t_peak:     {vol_data['t_peak_MFE'].median():.0f}s")
    print(f"   Median t_reversion:{vol_data['t_reversion_50pct'].median():.0f}s")
    print(f"   Avg peak MFE:      {vol_data['peak_MFE_value'].mean():.3f}%")

# Export detailed data for Week 5
output_file = 'd:/liquidation-trading/signal_halflife_data.csv'
df_hl.to_csv(output_file, index=False)
print(f"\n{'=' * 100}")
print(f"📁 Detailed data exported to: {output_file}")
print(f"{'=' * 100}")

conn.close()

print("""
\n✅ WEEK 1 TASK 1.2: COMPLETE
============================

Key Findings:
- Signal half-life measured for all symbols
- Data grouped by (symbol, session, volatility)
- Export ready for Week 5 time-based exits

Next Use Cases:
1. Week 5: Set time-based exit thresholds (t > half_life → move SL to breakeven)
2. Week 5: MFE stagnation detection (no new peak for 0.5 × half_life)
3. Signal quality: Longer half-life = higher quality signal

Remaining Week 1 Tasks:
- Task 1.3: Signal distribution analysis
- Task 1.5: Enhanced losing trade autopsy
""")
