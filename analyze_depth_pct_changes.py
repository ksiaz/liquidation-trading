"""
Analyze actual depth percentage changes across symbols.
Find appropriate threshold that works universally.
"""

import psycopg2
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

def analyze_depth_changes(symbol):
    """Analyze depth percentage changes for a symbol."""
    
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
        SELECT bid_volume_10, ask_volume_10
        FROM orderbook_snapshots
        WHERE symbol = %s
          AND timestamp >= %s
          AND timestamp <= %s
        ORDER BY timestamp ASC
    """, (symbol, start_time, end_time))
    
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    depths = [float(row[0]) + float(row[1]) for row in rows]
    
    # Calculate 30-second percentage changes
    pct_changes_30s = []
    for i in range(30, len(depths)):
        pct_change = (depths[i] - depths[i-30]) / depths[i-30]
        pct_changes_30s.append(pct_change * 100)  # Convert to %
    
    if not pct_changes_30s:
        return None
    
    return {
        'symbol': symbol,
        'min_pct': np.min(pct_changes_30s),
        'p10': np.percentile(pct_changes_30s, 10),
        'median': np.median(pct_changes_30s),
        'mean': np.mean(pct_changes_30s),
        'p90': np.percentile(pct_changes_30s, 90),
        'max_pct': np.max(pct_changes_30s),
        'std': np.std(pct_changes_30s)
    }

if __name__ == "__main__":
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    print("="*80)
    print("30-SECOND DEPTH PERCENTAGE CHANGES")
    print("="*80)
    print(f"\n{'Metric':<15} {'BTCUSDT':<15} {'ETHUSDT':<15} {'SOLUSDT':<15}")
    print("-"*65)
    
    results = {}
    for symbol in symbols:
        result = analyze_depth_changes(symbol)
        if result:
            results[symbol] = result
    
    metrics = ['min_pct', 'p10', 'median', 'mean', 'p90', 'max_pct', 'std']
    for metric in metrics:
        values = [f"{results[s][metric]:.2f}%" if s in results else "N/A" for s in symbols]
        print(f"{metric:<15} {values[0]:<15} {values[1]:<15} {values[2]:<15}")
    
    print("="*80)
    
    # Find threshold
    if results:
        all_p10 = [results[s]['p10'] for s in results]
        recommended_threshold = np.mean(all_p10)
        
        print(f"\n💡 RECOMMENDED THRESHOLD:")
        print(f"  Average 10th percentile: {recommended_threshold:.2f}%")
        print(f"  (This means depth drops by this % in 2% of cases)")
        print(f"\n  In detector config: slope_threshold = {int(recommended_threshold * -1)}")
        print(f"  (Negative because we want declining depth)")
