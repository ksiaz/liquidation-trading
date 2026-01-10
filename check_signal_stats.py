"""
Query current signal generation stats from database.
Shows what signals are actually being generated.
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
print("CURRENT SIGNAL GENERATION STATS")
print("=" * 80)

# 1. Total signals
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM trading_signals")
total = cur.fetchone()[0]
print(f"\nTotal signals in database: {total}")

# 2. Signals by symbol
cur.execute("""
    SELECT symbol, COUNT(*) as count
    FROM trading_signals
    GROUP BY symbol
    ORDER BY count DESC
""")
print(f"\nSignals by symbol:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# 3. Recent signals (last 24 hours)
cur.execute("""
    SELECT COUNT(*) 
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
""")
recent = cur.fetchone()[0]
print(f"\nSignals in last 24 hours: {recent}")
print(f"  Rate: {recent/24:.1f} signals/hour")

# 4. Signal distribution
cur.execute("""
    SELECT 
        direction,
        COUNT(*) as count,
        AVG(confidence) as avg_confidence,
        AVG(snr) as avg_snr,
        AVG(timeframe) as avg_timeframe
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY direction
""")
print(f"\nSignal distribution (last 24h):")
print(f"{'Direction':<10} {'Count':<8} {'Avg Conf':<12} {'Avg SNR':<12} {'Avg TF':<10}")
print("-" * 60)
for row in cur.fetchall():
    print(f"{row[0]:<10} {row[1]:<8} {row[2]:>10.1f}% {row[3]:>10.2f} {row[4]:>8.0f}s")

# 5. Confidence distribution
cur.execute("""
    SELECT 
        CASE 
            WHEN confidence >= 90 THEN '90-100%'
            WHEN confidence >= 80 THEN '80-90%'
            WHEN confidence >= 70 THEN '70-80%'
            WHEN confidence >= 60 THEN '60-70%'
            ELSE '<60%'
        END as conf_bucket,
        COUNT(*) as count
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY conf_bucket
    ORDER BY conf_bucket DESC
""")
print(f"\nConfidence distribution (last 24h):")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} signals")

# 6. Timeframe distribution
cur.execute("""
    SELECT 
        timeframe,
        COUNT(*) as count
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY timeframe
    ORDER BY timeframe
""")
print(f"\nTimeframe distribution (last 24h):")
for row in cur.fetchall():
    print(f"  {row[0]}s: {row[1]} signals")

# 7. SNR distribution
cur.execute("""
    SELECT 
        CASE 
            WHEN snr >= 0.5 THEN '>=0.5 (excellent)'
            WHEN snr >= 0.3 THEN '0.3-0.5 (good)'
            WHEN snr >= 0.15 THEN '0.15-0.3 (ok)'
            ELSE '<0.15 (poor)'
        END as snr_bucket,
        COUNT(*) as count
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY snr_bucket
    ORDER BY snr_bucket DESC
""")
print(f"\nSNR distribution (last 24h):")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} signals")

# 8. Most recent signals
cur.execute("""
    SELECT 
        timestamp,
        symbol,
        direction,
        confidence,
        snr,
        timeframe,
        entry_price
    FROM trading_signals
    ORDER BY timestamp DESC
    LIMIT 10
""")
print(f"\nMost recent 10 signals:")
print(f"{'Time':<20} {'Symbol':<10} {'Dir':<6} {'Conf':<8} {'SNR':<8} {'TF':<6} {'Entry':<12}")
print("-" * 80)
for row in cur.fetchall():
    print(f"{row[0].strftime('%Y-%m-%d %H:%M:%S'):<20} "
          f"{row[1]:<10} "
          f"{row[2]:<6} "
          f"{row[3]:>6.1f}% "
          f"{row[4]:>6.2f} "
          f"{row[5]:>4.0f}s "
          f"${row[6]:>10,.2f}")

conn.close()

print(f"\n{'=' * 80}\n")
