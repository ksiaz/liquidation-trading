"""
Analyze recent price action to see what the detector saw during the breakouts.
"""

import psycopg2
from datetime import datetime, timedelta
import pandas as pd

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)

print("=" * 80)
print("BREAKOUT ANALYSIS - What Did Detector See?")
print("=" * 80)

# Get recent price action (last 2 hours)
cur = conn.cursor()
cur.execute("""
    SELECT 
        timestamp,
        symbol,
        best_bid,
        best_ask,
        imbalance,
        spread_pct,
        bid_volume_10,
        ask_volume_10
    FROM orderbook_snapshots
    WHERE timestamp > NOW() - INTERVAL '2 hours'
    ORDER BY timestamp DESC
    LIMIT 7200
""")

data = cur.fetchall()
df = pd.DataFrame(data, columns=[
    'timestamp', 'symbol', 'best_bid', 'best_ask', 
    'imbalance', 'spread_pct', 'bid_volume_10', 'ask_volume_10'
])

# Convert decimal columns to float
df['best_bid'] = df['best_bid'].astype(float)
df['best_ask'] = df['best_ask'].astype(float)
df['imbalance'] = df['imbalance'].astype(float)
df['spread_pct'] = df['spread_pct'].astype(float)
df['bid_volume_10'] = df['bid_volume_10'].astype(float)
df['ask_volume_10'] = df['ask_volume_10'].astype(float)

# Calculate mid price
df['mid_price'] = (df['best_bid'] + df['best_ask']) / 2

# Analyze each symbol
for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
    symbol_df = df[df['symbol'] == symbol].sort_values('timestamp')
    
    if len(symbol_df) == 0:
        continue
    
    print(f"\n{'='*80}")
    print(f"{symbol} - Last 2 Hours")
    print(f"{'='*80}")
    
    # Calculate price changes
    symbol_df['price_change_1m'] = symbol_df['mid_price'].pct_change(60)
    symbol_df['price_change_5m'] = symbol_df['mid_price'].pct_change(300)
    
    # Find significant moves (>0.1%)
    significant_moves = symbol_df[abs(symbol_df['price_change_1m']) > 0.001]
    
    if len(significant_moves) > 0:
        print(f"\n🚀 SIGNIFICANT MOVES (>0.1% in 1 min):")
        print(f"{'Time':<20} {'Price':<12} {'1m Change':<12} {'Imbalance':<12} {'Spread %':<12}")
        print("-" * 80)
        
        for idx, row in significant_moves.tail(10).iterrows():
            print(f"{row['timestamp'].strftime('%H:%M:%S'):<20} "
                  f"${row['mid_price']:>10,.2f} "
                  f"{row['price_change_1m']*100:>10.2f}% "
                  f"{row['imbalance']:>10.3f} "
                  f"{row['spread_pct']*100:>10.4f}%")
    
    # Calculate volatility metrics
    recent_60 = symbol_df.tail(60)
    if len(recent_60) > 0:
        imb_volatility = recent_60['imbalance'].std()
        price_range = (recent_60['mid_price'].max() - recent_60['mid_price'].min()) / recent_60['mid_price'].min() * 100
        
        print(f"\nRECENT METRICS (last 60 sec):")
        print(f"  Imbalance volatility: {imb_volatility:.3f}")
        print(f"  Price range: {price_range:.3f}%")
        print(f"  Avg imbalance: {recent_60['imbalance'].mean():.3f}")
        
        # Check if chop filter would trigger
        imb_changes = abs(recent_60['imbalance'].diff())
        avg_imb_change = imb_changes.mean()
        
        print(f"  Avg imbalance change: {avg_imb_change:.3f}")
        
        if imb_volatility > 0.3:
            print(f"  ⚠️  CHOP FILTER WOULD TRIGGER (volatility > 0.3)")
        else:
            print(f"  ✅ Chop filter OK")
    
    # Find breakouts (price moves >0.5% from recent range)
    for i in range(60, len(symbol_df)):
        lookback = symbol_df.iloc[i-60:i]
        current = symbol_df.iloc[i]
        
        range_low = lookback['mid_price'].min()
        range_high = lookback['mid_price'].max()
        current_price = current['mid_price']
        
        # Breakout up (0.15% move)
        if current_price > range_high * 1.0015:
            print(f"\n🔥 BREAKOUT UP at {current['timestamp'].strftime('%H:%M:%S')}")
            print(f"   Price: ${current_price:,.2f} (broke ${range_high:,.2f})")
            print(f"   Imbalance: {current['imbalance']:.3f}")
            print(f"   Spread: {current['spread_pct']*100:.4f}%")
            
        # Breakout down (0.15% move)
        if current_price < range_low * 0.9985:
            print(f"\n🔥 BREAKOUT DOWN at {current['timestamp'].strftime('%H:%M:%S')}")
            print(f"   Price: ${current_price:,.2f} (broke ${range_low:,.2f})")
            print(f"   Imbalance: {current['imbalance']:.3f}")
            print(f"   Spread: {current['spread_pct']*100:.4f}%")

conn.close()
print(f"\n{'='*80}\n")
