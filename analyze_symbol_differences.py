"""
Analyze why detector works on SOL but not BTC/ETH.
Compare orderbook characteristics across symbols.
"""

import psycopg2
from datetime import datetime, timedelta
import numpy as np
import os
from dotenv import load_dotenv

load_dotenv()

def analyze_symbol_characteristics(symbol):
    """Analyze orderbook characteristics for a symbol."""
    
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'liquidation_trading'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    
    cursor = conn.cursor()
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=8)
    
    cursor.execute("""
        SELECT best_bid, best_ask, bid_volume_10, ask_volume_10, spread_pct
        FROM orderbook_snapshots
        WHERE symbol = %s
          AND timestamp >= %s
          AND timestamp <= %s
    """, (symbol, start_time, end_time))
    
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if len(rows) == 0:
        return None
    
    # Calculate metrics
    depths = []
    spreads = []
    prices = []
    
    for row in rows:
        best_bid, best_ask, bid_vol, ask_vol, spread = row
        total_depth = float(bid_vol) + float(ask_vol)
        depths.append(total_depth)
        spreads.append(float(spread))
        prices.append((float(best_bid) + float(best_ask)) / 2)
    
    # Calculate depth volatility
    depth_changes = np.diff(depths)
    depth_volatility = np.std(depth_changes)
    
    # Calculate price volatility
    price_changes = np.diff(prices) / prices[:-1]
    price_volatility = np.std(price_changes)
    
    return {
        'symbol': symbol,
        'avg_depth': np.mean(depths),
        'min_depth': np.min(depths),
        'max_depth': np.max(depths),
        'depth_std': np.std(depths),
        'depth_volatility': depth_volatility,
        'avg_spread': np.mean(spreads),
        'avg_price': np.mean(prices),
        'price_volatility': price_volatility
    }

if __name__ == "__main__":
    print("="*80)
    print("ORDERBOOK CHARACTERISTICS COMPARISON")
    print("="*80)
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    results = {}
    
    for symbol in symbols:
        result = analyze_symbol_characteristics(symbol)
        if result:
            results[symbol] = result
    
    # Print comparison
    print(f"\n{'Metric':<25} {'BTCUSDT':<20} {'ETHUSDT':<20} {'SOLUSDT':<20}")
    print("-"*85)
    
    metrics = ['avg_depth', 'depth_std', 'depth_volatility', 'avg_spread', 'price_volatility']
    for metric in metrics:
        values = [f"{results[s][metric]:.2f}" if s in results else "N/A" for s in symbols]
        print(f"{metric:<25} {values[0]:<20} {values[1]:<20} {values[2]:<20}")
    
    print("="*80)
    
    # Analysis
    if 'SOLUSDT' in results and 'BTCUSDT' in results:
        sol_depth = results['SOLUSDT']['avg_depth']
        btc_depth = results['BTCUSDT']['avg_depth']
        eth_depth = results['ETHUSDT']['avg_depth']
        
        print(f"\n💡 KEY INSIGHTS:")
        print(f"  SOL avg depth: {sol_depth:.0f}")
        print(f"  BTC avg depth: {btc_depth:.0f} ({btc_depth/sol_depth:.1f}x SOL)")
        print(f"  ETH avg depth: {eth_depth:.0f} ({eth_depth/sol_depth:.1f}x SOL)")
        
        print(f"\n⚠️ PROBLEM:")
        print(f"  Detector threshold: depth < 96% of avg")
        print(f"  SOL: Triggers when depth < {sol_depth * 0.96:.0f}")
        print(f"  BTC: Triggers when depth < {btc_depth * 0.96:.0f}")
        print(f"  ETH: Triggers when depth < {eth_depth * 0.96:.0f}")
        print(f"\n  BTC/ETH have MUCH higher liquidity → detector never triggers!")
