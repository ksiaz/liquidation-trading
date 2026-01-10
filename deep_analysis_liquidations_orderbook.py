"""
Deep Empirical Analysis: Liquidations + Orderbook Microstructure
-----------------------------------------------------------------

Missing piece from initial analysis: LIQUIDATION DATA

Questions to answer:
1. Do liquidations precede larger price moves (>0.5%)?
2. Does orderbook imbalance + liquidations predict better than imbalance alone?
3. Are liquidation cascades the "magnitude" signal we're missing?
4. What's the relationship between liquidation volume and forward returns?
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
FORWARD_WINDOWS = [60, 300, 900]  # 1min, 5min, 15min (longer for liquidation impact)

print("=" * 100)
print("DEEP ANALYSIS: LIQUIDATIONS + ORDERBOOK")
print("=" * 100)
print("\nHypothesis: Liquidation events are the missing 'magnitude' signal")
print("Testing if liquidations + orderbook imbalance predicts >0.5% moves\n")

# First, check what liquidation data we have
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='public' 
    AND table_name LIKE '%liquid%'
""")

liq_tables = [t[0] for t in cur.fetchall()]
print(f"📊 Liquidation tables found: {liq_tables}\n")

if not liq_tables:
    print("⚠️ No liquidation data in database!")
    print("\nTo collect liquidation data, run:")
    print("  python liquidation_stream.py")
    cur.close()
    conn.close()
    exit()

# Assume table is 'liquidations' - adjust if needed
liq_table = liq_tables[0] if liq_tables else 'liquidations'

# Check liquidation data structure
cur.execute(f"""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = '{liq_table}'
""")

columns = cur.fetchall()
print(f"📋 Liquidation table structure ({liq_table}):")
for col, dtype in columns:
    print(f"   {col}: {dtype}")
print()

# Get liquidation data summary
cur.execute(f"""
    SELECT 
        MIN(timestamp) as first_liq,
        MAX(timestamp) as last_liq,
        COUNT(*) as total_liqs,
        SUM(CASE WHEN symbol = 'BTCUSDT' THEN 1 ELSE 0 END) as btc_count,
        SUM(CASE WHEN symbol = 'ETHUSDT' THEN 1 ELSE 0 END) as eth_count,
        SUM(CASE WHEN symbol = 'SOLUSDT' THEN 1 ELSE 0 END) as sol_count
    FROM {liq_table}
""")

result = cur.fetchone()
if result and result[0]:
    min_ts, max_ts, total, btc_cnt, eth_cnt, sol_cnt = result
    
    duration = (max_ts - min_ts).total_seconds() / 3600 if max_ts and min_ts else 0
    
    print(f"📈 LIQUIDATION DATA SUMMARY")
    print(f"   Period: {min_ts} to {max_ts}")
    print(f"   Duration: {duration:.1f} hours")
    print(f"   Total Liquidations: {total:,}")
    print(f"   BTC: {btc_cnt:,} | ETH: {eth_cnt:,} | SOL: {sol_cnt:,}")
    print()
else:
    print("⚠️ Liquidation table exists but is EMPTY")
    print("\nCollection needed. Run: python liquidation_stream.py")
    cur.close()
    conn.close()
    exit()

# ANALYSIS 1: Liquidation Volume vs Forward Returns
print(f"🔍 ANALYSIS 1: LIQUIDATION VOLUME PREDICTIVE POWER")
print(f"   Question: Do large liquidations predict price moves >0.5%?\n")

for symbol in SYMBOLS:
    print(f"   --- {symbol} ---")
    
    # Join liquidations with orderbook snapshots for forward returns
    cur.execute(f"""
        WITH liq_with_price AS (
            SELECT 
                l.timestamp as liq_time,
                l.side,
                l.value_usd,
                o.timestamp as ob_time,
                (o.best_bid + o.best_ask) / 2 as price,
                o.imbalance
            FROM {liq_table} l
            JOIN LATERAL (
                SELECT timestamp, best_bid, best_ask, imbalance
                FROM orderbook_snapshots
                WHERE symbol = %s
                AND timestamp >= l.timestamp - INTERVAL '5 seconds'
                AND timestamp <= l.timestamp + INTERVAL '5 seconds'
                ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - l.timestamp)))
                LIMIT 1
            ) o ON true
            WHERE l.symbol = %s
            ORDER BY l.timestamp
        )
        SELECT 
            COUNT(*) as total_liqs,
            AVG(value_usd) as avg_value,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_usd) as median_value,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value_usd) as p95_value,
            MAX(value_usd) as max_value
        FROM liq_with_price
    """, (symbol, symbol))
    
    result = cur.fetchone()
    if result and result[0]:
        total, avg_val, median_val, p95_val, max_val = result
        print(f"   Liquidations matched with orderbook: {total:,}")
        print(f"   Average value: ${avg_val:,.2f}")
        print(f"   Median value: ${median_val:,.2f}")
        print(f"   95th percentile: ${p95_val:,.2f}")
        print(f"   Max value: ${max_val:,.2f}")
    else:
        print(f"   No liquidation data for {symbol}")
    
    print()

# ANALYSIS 2: Liquidation Cascades
print(f"\n🔍 ANALYSIS 2: LIQUIDATION CASCADES")
print(f"   Question: Do clustered liquidations (within 30s) predict larger moves?\n")

for symbol in SYMBOLS:
    print(f"   --- {symbol} ---")
    
    # Detect cascades: 3+ liquidations within 30 seconds
    cur.execute(f"""
        WITH liq_with_next AS (
            SELECT 
                timestamp,
                side,
                value_usd,
                LEAD(timestamp) OVER (ORDER BY timestamp) as next_liq_time
            FROM {liq_table}
            WHERE symbol = %s
        ),
        cascades AS (
            SELECT 
                timestamp,
                COUNT(*) OVER (
                    ORDER BY timestamp 
                    RANGE BETWEEN CURRENT ROW AND INTERVAL '30 seconds' FOLLOWING
                ) as cascade_count,
                SUM(value_usd) OVER (
                    ORDER BY timestamp 
                    RANGE BETWEEN CURRENT ROW AND INTERVAL '30 seconds' FOLLOWING
                ) as cascade_volume
            FROM liq_with_next
        )
        SELECT 
            COUNT(CASE WHEN cascade_count >= 3 THEN 1 END) as cascade_events,
            AVG(CASE WHEN cascade_count >= 3 THEN cascade_volume END) as avg_cascade_vol,
            MAX(cascade_volume) as max_cascade_vol
        FROM cascades
    """, (symbol,))
    
    result = cur.fetchone()
    if result and result[0] is not None:
        cascade_cnt, avg_vol, max_vol = result
        print(f"   Cascade events (3+ liqs in 30s): {cascade_cnt:,}")
        if avg_vol:
            print(f"   Average cascade volume: ${avg_vol:,.2f}")
        if max_vol:
            print(f"   Max cascade volume: ${max_vol:,.2f}")
    else:
        print(f"   No cascade data")
    
    print()

# ANALYSIS 3: Combined Signal (Liquidation + Imbalance)
print(f"\n🔍 ANALYSIS 3: COMBINED SIGNAL POWER")
print(f"   Question: Does liquidation + imbalance alignment predict better?\n")

# Analyze cases where:
# - Large liquidation occurs (>=$50k)
# - Orderbook imbalance is OPPOSITE direction (potential reversal)
# Example: BIG LONG LIQUIDATION (sell pressure) + HIGH BID IMBALANCE (buyers stepping in)

for symbol in SYMBOLS:
    print(f"   --- {symbol} ---")
    
    cur.execute(f"""
        WITH signals AS (
            SELECT 
                l.timestamp,
                l.side as liq_side,
                l.value_usd,
                o.imbalance,
                o.best_bid,
                o.best_ask,
                LAG((o.best_bid + o.best_ask) / 2, 60) OVER (ORDER BY l.timestamp) as price_60s_before,
                LEAD((o.best_bid + o.best_ask) / 2, 60) OVER (ORDER BY l.timestamp) as price_60s_after,
                LEAD((o.best_bid + o.best_ask) / 2, 300) OVER (ORDER BY l.timestamp) as price_5m_after
            FROM {liq_table} l
            JOIN LATERAL (
                SELECT timestamp, imbalance, best_bid, best_ask
                FROM orderbook_snapshots
                WHERE symbol = %s
                AND timestamp >= l.timestamp
                AND timestamp <= l.timestamp + INTERVAL '10 seconds'
                ORDER BY timestamp
                LIMIT 1
            ) o ON true
            WHERE l.symbol = %s
            AND l.value_usd >= 50000  -- Focus on large liquidations
        )
        SELECT 
            -- Bearish reversal: Long liq (SELL) + bid imbalance (buyers)
            COUNT(CASE 
                WHEN liq_side = 'SELL' AND imbalance > 0.30 
                THEN 1 
            END) as long_liq_bid_imb,
            AVG(CASE 
                WHEN liq_side = 'SELL' AND imbalance > 0.30 
                AND price_60s_after IS NOT NULL AND (best_bid + best_ask) / 2 > 0
                THEN ((price_60s_after - (best_bid + best_ask) / 2) / ((best_bid + best_ask) / 2)) * 100
            END) as avg_return_60s_long_liq,
            
            -- Bullish reversal: Short liq (BUY) + ask imbalance (sellers)
            COUNT(CASE 
                WHEN liq_side = 'BUY' AND imbalance < -0.30 
                THEN 1 
            END) as short_liq_ask_imb,
            AVG(CASE 
                WHEN liq_side = 'BUY' AND imbalance < -0.30 
                AND price_60s_after IS NOT NULL AND (best_bid + best_ask) / 2 > 0
                THEN ((price_60s_after - (best_bid + best_ask) / 2) / ((best_bid + best_ask) / 2)) * 100
            END) as avg_return_60s_short_liq,
            
            -- Count how many hit 0.5% target
            COUNT(CASE 
                WHEN liq_side = 'SELL' AND imbalance > 0.30 
                AND price_5m_after IS NOT NULL AND (best_bid + best_ask) / 2 > 0
                AND ((price_5m_after - (best_bid + best_ask) / 2) / ((best_bid + best_ask) / 2)) * 100 > 0.5
                THEN 1 
            END) as long_liq_hits_target
        FROM signals
    """, (symbol, symbol))
    
    result = cur.fetchone()
    if result:
        long_liq_cnt, avg_ret_long, short_liq_cnt, avg_ret_short, target_hits = result
        
        print(f"   LONG LIQUIDATION + BID IMBALANCE (reversal setup):")
        print(f"      Occurrences: {long_liq_cnt or 0}")
        if avg_ret_long is not None:
            print(f"      Avg 60s return: {avg_ret_long:+.3f}%")
            print(f"      Hit 0.5% target (5min): {target_hits or 0} ({(target_hits/long_liq_cnt*100) if long_liq_cnt else 0:.1f}%)")
        
        print(f"   SHORT LIQUIDATION + ASK IMBALANCE (reversal setup):")
        print(f"      Occurrences: {short_liq_cnt or 0}")
        if avg_ret_short is not None:
            print(f"      Avg 60s return: {avg_ret_short:+.3f}%")
    else:
        print(f"   No data")
    
    print()

cur.close()
conn.close()

print("\n" + "=" * 100)
print("ANALYSIS COMPLETE")
print("=" * 100)
print("\nKey Questions to Answer:")
print("1. Are liquidation-driven moves larger than pure orderbook signals?")
print("2. Do liquidation cascades create the 0.5%+ moves we need?")
print("3. Should we ONLY trade around liquidation events?")
print("4. Is liquidation + imbalance the 'hybrid' signal we actually need?")
