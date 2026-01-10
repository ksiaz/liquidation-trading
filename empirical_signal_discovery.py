"""
Empirical Signal Discovery
--------------------------
Data-driven approach to discover which orderbook patterns 
actually predict profitable price movements.

No pre-conceived "counter-trend" or "momentum" labels.
Let the data speak for itself.
"""

import psycopg2
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

# Connect to database
conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

# Configuration
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
TARGET_PCT = 0.5  # Our profit target
STOP_PCT = 10.0   # Our stop loss
FORWARD_WINDOWS = [10, 30, 60, 120]  # seconds to look ahead

print("=" * 100)
print("EMPIRICAL SIGNAL DISCOVERY - Data-Driven Pattern Analysis")
print("=" * 100)
print(f"\nTarget: {TARGET_PCT}% profit")
print(f"Stop: {STOP_PCT}% loss")
print(f"Forward windows: {FORWARD_WINDOWS} seconds\n")

for symbol in SYMBOLS:
    print(f"\n{'=' * 100}")
    print(f"ANALYZING: {symbol}")
    print(f"{'=' * 100}\n")
    
    # Get data range
    cur.execute("""
        SELECT 
            MIN(timestamp), MAX(timestamp),
            COUNT(*) as snapshots
        FROM orderbook_snapshots
        WHERE symbol = %s
    """, (symbol,))
    
    min_ts, max_ts, total_snaps = cur.fetchone()
    
    if not min_ts:
        print(f"No data for {symbol}")
        continue
        
    duration_hours = (max_ts - min_ts).total_seconds() / 3600
    print(f"📊 DATA SUMMARY")
    print(f"   Period: {min_ts} to {max_ts}")
    print(f"   Duration: {duration_hours:.1f} hours")
    print(f"   Snapshots: {total_snaps:,}\n")
    
    # ANALYSIS 1: Imbalance vs Forward Returns
    print(f"🔍 ANALYSIS 1: IMBALANCE PREDICTIVE POWER")
    print(f"   Question: Does high/low imbalance predict price movement?\n")
    
    for window in FORWARD_WINDOWS:
        # Simple approach: sample data and calculate forward returns in Python
        # More efficient than complex SQL with LEAD for large datasets
        cur.execute("""
            SELECT 
                timestamp,
                (best_bid + best_ask) / 2 as mid_price,
                imbalance
            FROM orderbook_snapshots
            WHERE symbol = %s
            ORDER BY timestamp
        """, (symbol,))
        
        data = cur.fetchall()
        
        if len(data) < window:
            continue
            
        # Calculate forward returns
        wins_pos, loss_pos, total_pos = 0, 0, 0
        wins_neg, loss_neg, total_neg = 0, 0, 0
        total_neutral = 0
        
        returns_pos, returns_neg, returns_neutral = [], [], []
        
        for i in range(len(data) - window):
            ts, mid_price, imbalance = data[i]
            future_price = data[i + window][1]
            
            if mid_price > 0:
                forward_return = ((future_price - mid_price) / mid_price) * 100
                
                # High positive imbalance
                if imbalance > 0.30:
                    total_pos += 1
                    returns_pos.append(forward_return)
                    if forward_return > TARGET_PCT:
                        wins_pos += 1
                    if forward_return < -STOP_PCT:
                        loss_pos += 1
                
                # High negative imbalance
                elif imbalance < -0.30:
                    total_neg += 1
                    returns_neg.append(forward_return)
                    if forward_return > TARGET_PCT:
                        wins_neg += 1
                    if forward_return < -STOP_PCT:
                        loss_neg += 1
                
                # Neutral
                elif -0.10 <= imbalance <= 0.10:
                    total_neutral += 1
                    returns_neutral.append(forward_return)
        
        avg_pos_imb = np.mean(returns_pos) if returns_pos else 0
        avg_neg_imb = np.mean(returns_neg) if returns_neg else 0
        avg_neutral = np.mean(returns_neutral) if returns_neutral else 0
        
        print(f"   {window}s forward window:")
        
        if total_pos and total_pos > 0:
            win_rate_pos = (wins_pos / total_pos) * 100 if total_pos > 0 else 0
            print(f"      HIGH BID IMBALANCE (>30%): {total_pos:,} instances")
            print(f"         Avg Return: {avg_pos_imb:+.3f}%")
            print(f"         Hit {TARGET_PCT}% target: {wins_pos:,} ({win_rate_pos:.1f}%)")
            print(f"         Hit {STOP_PCT}% stop: {loss_pos:,}")
            
        if total_neg and total_neg > 0:
            win_rate_neg = (wins_neg / total_neg) * 100 if total_neg > 0 else 0
            print(f"      HIGH ASK IMBALANCE (<-30%): {total_neg:,} instances")
            print(f"         Avg Return: {avg_neg_imb:+.3f}%")
            print(f"         Hit {TARGET_PCT}% target: {wins_neg:,} ({win_rate_neg:.1f}%)")
            print(f"         Hit {STOP_PCT}% stop: {loss_neg:,}")
            
        if total_neutral and total_neutral > 0:
            print(f"      NEUTRAL IMBALANCE (-10% to +10%): {total_neutral:,} instances")
            print(f"         Avg Return: {avg_neutral:+.3f}% (baseline)")
        
        print()
    
    # ANALYSIS 2: Imbalance Divergence
    print(f"\n🔍 ANALYSIS 2: IMBALANCE DIVERGENCE")
    print(f"   Question: Does imbalance moving opposite to price predict reversal?\n")
    
    cur.execute("""
        WITH minute_data AS (
            SELECT 
                DATE_TRUNC('minute', timestamp) as minute,
                AVG((best_bid + best_ask) / 2) as avg_price,
                AVG(imbalance) as avg_imb
            FROM orderbook_snapshots
            WHERE symbol = %s
            GROUP BY DATE_TRUNC('minute', timestamp)
            ORDER BY minute
        ),
        changes AS (
            SELECT 
                minute,
                avg_price,
                avg_imb,
                AVG(avg_price) OVER (ORDER BY minute ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) as price_3m_ago,
                AVG(avg_imb) OVER (ORDER BY minute ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) as imb_3m_ago,
                LEAD(avg_price, 3) OVER (ORDER BY minute) as price_3m_later,
                LEAD(avg_price, 5) OVER (ORDER BY minute) as price_5m_later
            FROM minute_data
        )
        SELECT 
            -- Bearish divergence: price up, imbalance down
            COUNT(CASE 
                WHEN (avg_price - price_3m_ago) / price_3m_ago > 0.002 
                AND (avg_imb - imb_3m_ago) < -0.20
                AND (price_3m_later - avg_price) / avg_price < -0.003
                THEN 1 
            END) as bear_div_reversals,
            COUNT(CASE 
                WHEN (avg_price - price_3m_ago) / price_3m_ago > 0.002 
                AND (avg_imb - imb_3m_ago) < -0.20
                THEN 1 
            END) as bear_div_total,
            
            -- Bullish divergence: price down, imbalance up
            COUNT(CASE 
                WHEN (avg_price - price_3m_ago) / price_3m_ago < -0.002 
                AND (avg_imb - imb_3m_ago) > 0.20
                AND (price_3m_later - avg_price) / avg_price > 0.003
                THEN 1 
            END) as bull_div_reversals,
            COUNT(CASE 
                WHEN (avg_price - price_3m_ago) / price_3m_ago < -0.002 
                AND (avg_imb - imb_3m_ago) > 0.20
                THEN 1 
            END) as bull_div_total
        FROM changes
        WHERE price_3m_ago IS NOT NULL 
        AND price_3m_later IS NOT NULL
    """, (symbol,))
    
    bear_rev, bear_total, bull_rev, bull_total = cur.fetchone()
    
    print(f"   Bearish Divergence (price↑ imbalance↓):")
    print(f"      Occurrences: {bear_total}")
    if bear_total > 0:
        print(f"      Reversals (price fell >0.3% in next 3min): {bear_rev} ({bear_rev/bear_total*100:.1f}%)")
    
    print(f"   Bullish Divergence (price↓ imbalance↑):")
    print(f"      Occurrences: {bull_total}")
    if bull_total > 0:
        print(f"      Reversals (price rose >0.3% in next 3min): {bull_rev} ({bull_rev/bull_total*100:.1f}%)")
    
    print()

cur.close()
conn.close()

print("\n" + "=" * 100)
print("ANALYSIS COMPLETE")
print("=" * 100)
print("\nNext Steps:")
print("1. Review which patterns have >60% win rate")
print("2. Check if avg returns are positive after costs")
print("3. Build signals ONLY from patterns that work")
print("4. Forget 'counter-trend' vs 'momentum' labels - use what works")
