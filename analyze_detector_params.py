import psycopg2
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 100)
print("COMPREHENSIVE SIGNAL DETECTION PARAMETER ANALYSIS")
print("=" * 100)

# Get available data range
cur.execute("""
    SELECT 
        MIN(timestamp) as first_snapshot,
        MAX(timestamp) as last_snapshot,
        COUNT(*) as total_snapshots,
        COUNT(DISTINCT symbol) as symbols
    FROM orderbook_snapshots
""")

first_ts, last_ts, total_snaps, symbols = cur.fetchone()
duration_hours = (last_ts - first_ts).total_seconds() / 3600

print(f"\n📊 DATA COVERAGE")
print(f"   First Snapshot: {first_ts}")
print(f"   Last Snapshot:  {last_ts}")
print(f"   Duration: {duration_hours:.1f} hours ({duration_hours/24:.1f} days)")
print(f"   Total Snapshots: {total_snaps:,}")
print(f"   Symbols: {symbols}")

# Analyze each symbol
symbols_list = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

for symbol in symbols_list:
    print(f"\n{'=' * 100}")
    print(f"ANALYSIS FOR {symbol}")
    print(f"{'=' * 100}")
    
    # Get symbol-specific data range
    cur.execute("""
        SELECT 
            MIN(timestamp) as first_ts,
            MAX(timestamp) as last_ts,
            COUNT(*) as count
        FROM orderbook_snapshots
        WHERE symbol = %s
    """, (symbol,))
    
    sym_first, sym_last, sym_count = cur.fetchone()
    
    if not sym_count:
        print(f"   ⚠️ No data available for {symbol}")
        continue
    
    sym_duration = (sym_last - sym_first).total_seconds() / 3600
    print(f"\n📈 {symbol} DATA")
    print(f"   Snapshots: {sym_count:,}")
    print(f"   Duration: {sym_duration:.1f} hours")
    print(f"   Avg Rate: {sym_count / (sym_duration * 60):.1f} snapshots/minute")
    
    # Price volatility analysis
    cur.execute("""
        WITH price_data AS (
            SELECT 
                timestamp,
                (best_bid + best_ask) / 2 as mid_price,
                LAG((best_bid + best_ask) / 2) OVER (ORDER BY timestamp) as prev_price
            FROM orderbook_snapshots
            WHERE symbol = %s
            ORDER BY timestamp
        ),
        price_changes AS (
            SELECT 
                timestamp,
                mid_price,
                prev_price,
                CASE 
                    WHEN prev_price IS NOT NULL AND prev_price > 0 
                    THEN ((mid_price - prev_price) / prev_price) * 100 
                    ELSE 0 
                END as pct_change
            FROM price_data
        )
        SELECT 
            MIN(mid_price) as min_price,
            MAX(mid_price) as max_price,
            AVG(mid_price) as avg_price,
            STDDEV(mid_price) as price_stddev,
            AVG(ABS(pct_change)) as avg_abs_change,
            STDDEV(pct_change) as change_stddev,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ABS(pct_change)) as p95_change,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ABS(pct_change)) as p99_change
        FROM price_changes
        WHERE pct_change IS NOT NULL
    """, (symbol,))
    
    min_p, max_p, avg_p, p_std, avg_abs_chg, chg_std, p95_chg, p99_chg = cur.fetchone()
    
    print(f"\n💰 PRICE STATISTICS")
    print(f"   Range: ${min_p:,.2f} - ${max_p:,.2f}")
    print(f"   Average: ${avg_p:,.2f}")
    print(f"   Total Range: ${max_p - min_p:,.2f} ({((max_p - min_p) / min_p * 100):.3f}%)")
    print(f"   Std Dev: ${p_std:,.2f}")
    print(f"   Avg Absolute Change: {avg_abs_chg:.6f}%")
    print(f"   Change Std Dev: {chg_std:.6f}%")
    print(f"   95th Percentile Change: {p95_chg:.6f}%")
    print(f"   99th Percentile Change: {p99_chg:.6f}%")
    
    # Imbalance analysis
    cur.execute("""
        SELECT 
            AVG(imbalance) as avg_imb,
            STDDEV(imbalance) as std_imb,
            MIN(imbalance) as min_imb,
            MAX(imbalance) as max_imb,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY imbalance) as p25_imb,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY imbalance) as p75_imb,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY imbalance) as p90_imb,
            PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY imbalance) as p10_imb,
            COUNT(CASE WHEN ABS(imbalance) > 0.5 THEN 1 END) as strong_imb_count,
            COUNT(CASE WHEN ABS(imbalance) > 0.7 THEN 1 END) as very_strong_imb_count,
            COUNT(CASE WHEN ABS(imbalance) > 0.9 THEN 1 END) as extreme_imb_count
        FROM orderbook_snapshots
        WHERE symbol = %s
    """, (symbol,))
    
    avg_imb, std_imb, min_imb, max_imb, p25, p75, p90, p10, strong_cnt, vstrong_cnt, extreme_cnt = cur.fetchone()
    
    print(f"\n⚖️  ORDERBOOK IMBALANCE")
    print(f"   Average: {avg_imb:+.4f}")
    print(f"   Std Dev: {std_imb:.4f}")
    print(f"   Range: {min_imb:+.4f} to {max_imb:+.4f}")
    print(f"   10th/90th Percentile: {p10:+.4f} / {p90:+.4f}")
    print(f"   25th/75th Percentile: {p25:+.4f} / {p75:+.4f}")
    print(f"   Strong (>0.5): {strong_cnt:,} ({strong_cnt/sym_count*100:.2f}%)")
    print(f"   Very Strong (>0.7): {vstrong_cnt:,} ({vstrong_cnt/sym_count*100:.2f}%)")
    print(f"   Extreme (>0.9): {extreme_cnt:,} ({extreme_cnt/sym_count*100:.2f}%)")
    
    # Reversal opportunity detection
    # Look for price reversals (significant moves followed by opposite moves)
    cur.execute("""
        WITH minute_data AS (
            SELECT 
                DATE_TRUNC('minute', timestamp) as minute,
                AVG((best_bid + best_ask) / 2) as avg_price,
                AVG(imbalance) as avg_imb,
                MIN((best_bid + best_ask) / 2) as min_price,
                MAX((best_bid + best_ask) / 2) as max_price
            FROM orderbook_snapshots
            WHERE symbol = %s
            GROUP BY DATE_TRUNC('minute', timestamp)
            ORDER BY minute
        ),
        price_moves AS (
            SELECT 
                minute,
                avg_price,
                avg_imb,
                LAG(avg_price, 1) OVER (ORDER BY minute) as price_1m_ago,
                LAG(avg_price, 3) OVER (ORDER BY minute) as price_3m_ago,
                LAG(avg_price, 5) OVER (ORDER BY minute) as price_5m_ago,
                LEAD(avg_price, 3) OVER (ORDER BY minute) as price_3m_later,
                LEAD(avg_price, 5) OVER (ORDER BY minute) as price_5m_later
            FROM minute_data
        ),
        reversals AS (
            SELECT 
                minute,
                avg_price,
                avg_imb,
                CASE 
                    WHEN price_3m_ago IS NOT NULL AND price_3m_ago > 0 
                    THEN ((avg_price - price_3m_ago) / price_3m_ago) * 100 
                END as move_3m,
                CASE 
                    WHEN price_5m_ago IS NOT NULL AND price_5m_ago > 0 
                    THEN ((avg_price - price_5m_ago) / price_5m_ago) * 100 
                END as move_5m,
                CASE 
                    WHEN price_3m_later IS NOT NULL AND avg_price > 0 
                    THEN ((price_3m_later - avg_price) / avg_price) * 100 
                END as future_3m,
                CASE 
                    WHEN price_5m_later IS NOT NULL AND avg_price > 0 
                    THEN ((price_5m_later - avg_price) / avg_price) * 100 
                END as future_5m
            FROM price_moves
        )
        SELECT 
            COUNT(CASE WHEN move_3m < -0.1 AND future_3m > 0.1 THEN 1 END) as bullish_reversals_3m,
            COUNT(CASE WHEN move_3m > 0.1 AND future_3m < -0.1 THEN 1 END) as bearish_reversals_3m,
            COUNT(CASE WHEN move_5m < -0.15 AND future_5m > 0.15 THEN 1 END) as bullish_reversals_5m,
            COUNT(CASE WHEN move_5m > 0.15 AND future_5m < -0.15 THEN 1 END) as bearish_reversals_5m,
            COUNT(CASE WHEN ABS(move_3m) > 0.1 THEN 1 END) as significant_moves_3m,
            COUNT(CASE WHEN ABS(move_5m) > 0.15 THEN 1 END) as significant_moves_5m
        FROM reversals
    """, (symbol,))
    
    bull_rev_3m, bear_rev_3m, bull_rev_5m, bear_rev_5m, sig_moves_3m, sig_moves_5m = cur.fetchone()
    
    print(f"\n🔄 REVERSAL OPPORTUNITIES")
    print(f"   3-Minute Timeframe:")
    print(f"      Bullish Reversals: {bull_rev_3m} (down >0.1% then up >0.1%)")
    print(f"      Bearish Reversals: {bear_rev_3m} (up >0.1% then down >0.1%)")
    print(f"      Total Opportunities: {bull_rev_3m + bear_rev_3m}")
    print(f"      Significant Moves: {sig_moves_3m}")
    if sig_moves_3m > 0:
        print(f"      Reversal Rate: {(bull_rev_3m + bear_rev_3m) / sig_moves_3m * 100:.1f}%")
    
    print(f"   5-Minute Timeframe:")
    print(f"      Bullish Reversals: {bull_rev_5m} (down >0.15% then up >0.15%)")
    print(f"      Bearish Reversals: {bear_rev_5m} (up >0.15% then down >0.15%)")
    print(f"      Total Opportunities: {bull_rev_5m + bear_rev_5m}")
    print(f"      Significant Moves: {sig_moves_5m}")
    if sig_moves_5m > 0:
        print(f"      Reversal Rate: {(bull_rev_5m + bear_rev_5m) / sig_moves_5m * 100:.1f}%")
    
    # Imbalance divergence analysis
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
        divergences AS (
            SELECT 
                minute,
                avg_price,
                avg_imb,
                LAG(avg_price, 3) OVER (ORDER BY minute) as price_3m_ago,
                LAG(avg_imb, 3) OVER (ORDER BY minute) as imb_3m_ago
            FROM minute_data
        )
        SELECT 
            COUNT(CASE 
                WHEN price_3m_ago IS NOT NULL 
                AND avg_price > price_3m_ago 
                AND avg_imb < imb_3m_ago - 0.2 
                THEN 1 
            END) as bearish_divergences,
            COUNT(CASE 
                WHEN price_3m_ago IS NOT NULL 
                AND avg_price < price_3m_ago 
                AND avg_imb > imb_3m_ago + 0.2 
                THEN 1 
            END) as bullish_divergences
        FROM divergences
    """, (symbol,))
    
    bear_div, bull_div = cur.fetchone()
    
    print(f"\n📊 IMBALANCE DIVERGENCES (3-min lookback)")
    print(f"   Bearish: {bear_div} (price up, imbalance down >0.2)")
    print(f"   Bullish: {bull_div} (price down, imbalance up >0.2)")
    print(f"   Total: {bear_div + bull_div}")
    
    # Chop/Range analysis
    cur.execute("""
        WITH minute_data AS (
            SELECT 
                DATE_TRUNC('minute', timestamp) as minute,
                AVG((best_bid + best_ask) / 2) as avg_price,
                MIN((best_bid + best_ask) / 2) as min_price,
                MAX((best_bid + best_ask) / 2) as max_price
            FROM orderbook_snapshots
            WHERE symbol = %s
            GROUP BY DATE_TRUNC('minute', timestamp)
            ORDER BY minute
        ),
        ranges AS (
            SELECT 
                minute,
                avg_price,
                max_price - min_price as minute_range,
                LAG(avg_price, 1) OVER (ORDER BY minute) as prev_price
            FROM minute_data
        ),
        chop_analysis AS (
            SELECT 
                minute,
                minute_range,
                CASE 
                    WHEN prev_price IS NOT NULL AND prev_price > 0 
                    THEN ABS((avg_price - prev_price) / prev_price) * 100 
                END as price_change_pct,
                CASE 
                    WHEN avg_price > 0 
                    THEN (minute_range / avg_price) * 100 
                END as range_pct
            FROM ranges
        )
        SELECT 
            AVG(range_pct) as avg_range_pct,
            AVG(price_change_pct) as avg_change_pct,
            COUNT(CASE WHEN range_pct > price_change_pct * 3 THEN 1 END) as choppy_minutes,
            COUNT(*) as total_minutes
        FROM chop_analysis
        WHERE range_pct IS NOT NULL AND price_change_pct IS NOT NULL
    """, (symbol,))
    
    avg_range_pct, avg_change_pct, choppy_min, total_min = cur.fetchone()
    
    print(f"\n📉 CHOP/RANGE ANALYSIS")
    print(f"   Avg Minute Range: {avg_range_pct:.4f}%")
    print(f"   Avg Minute Change: {avg_change_pct:.4f}%")
    print(f"   Choppy Minutes: {choppy_min}/{total_min} ({choppy_min/total_min*100:.1f}%)")
    print(f"   (Choppy = range > 3x net change)")

print(f"\n{'=' * 100}")
print("RECOMMENDATIONS")
print(f"{'=' * 100}")

print("""
Based on the analysis above, consider these adjustments:

1. SNR THRESHOLD
   - Current: 2.0
   - If reversals are rare but high quality, keep strict (2.0+)
   - If many reversals exist, consider lowering to 1.5-1.8

2. IMBALANCE DIVERGENCE THRESHOLD
   - Current: Likely 0.2-0.3
   - Check divergence counts vs reversal opportunities
   - Adjust based on false positive rate

3. CHOP FILTER
   - If >50% of time is choppy, filter is working correctly
   - If <30% choppy, market is trending - loosen filter
   - If >70% choppy, tighten filter or wait for better conditions

4. TIMEFRAME SELECTION
   - Compare 3-min vs 5-min reversal rates
   - Use timeframe with better reversal/move ratio

5. CONFIRMATION REQUIREMENTS
   - Current: 3+ signals out of 5
   - If opportunities are abundant, keep strict
   - If too few signals, reduce to 2+ out of 5
""")

conn.close()
