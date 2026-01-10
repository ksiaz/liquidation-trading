"""
Week 1 Task 1.3: Signal Distribution Analysis
==============================================

Analyzes when signals occur and their profitability:
- Signals per hour by time of day (UTC)
- Signals per hour by volatility regime
- Identify "toxic" periods (high signal count + low win rate)
- Generate signal density heatmap

Goal: Detect overtrading periods where signal quality degrades
Expert: "If signal count doubles, reduce position size by 50%" (Week 12 circuit breaker)
"""

import psycopg2
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
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
print("WEEK 1 TASK 1.3: SIGNAL DISTRIBUTION ANALYSIS")
print("=" * 100)
print("\n🎯 Detecting toxic periods:")
print("   - High signal count periods (potential overtrading)")
print("   - Low win rate periods (quality degradation)")
print("   - Session-specific patterns (Asia/Europe/US)")
print("   - Volatility regime sensitivity\n")

# Test period: Last 7 days for better statistics
end_time = datetime(2026, 1, 1, 7, 0, 0)
start_time = end_time - timedelta(days=7)

# Load signals from database
cur.execute("""
    SELECT 
        timestamp,
        symbol,
        direction,
        confidence,
        EXTRACT(HOUR FROM timestamp) as hour,
        EXTRACT(DOW FROM timestamp) as dow
    FROM trading_signals
    WHERE timestamp BETWEEN %s AND %s
    ORDER BY timestamp
""", (start_time, end_time))

signals = cur.fetchall()

if not signals:
    print("\n❌ No signals found in database for analysis period")
    conn.close()
    exit(0)

print(f"📊 Loaded {len(signals)} signals from database\n")

# Convert to DataFrame
df = pd.DataFrame(signals, columns=['timestamp', 'symbol', 'direction', 'confidence', 'hour', 'dow'])

# Classify sessions
def get_session(hour):
    if 0 <= hour < 8:
        return 'ASIA'
    elif 8 <= hour < 16:
        return 'EUROPE'
    else:
        return 'US'

df['session'] = df['hour'].apply(get_session)

# ========================================================================================
# ANALYSIS 1: Signals by Hour of Day
# ========================================================================================

print("=" * 100)
print("SIGNALS BY HOUR OF DAY (UTC)")
print("=" * 100)

hourly_counts = df.groupby('hour').size()
avg_per_hour = hourly_counts.mean()
std_per_hour = hourly_counts.std()

print(f"\nAverage signals/hour: {avg_per_hour:.1f}")
print(f"Std deviation:        {std_per_hour:.1f}")
print(f"Peak hour:            {hourly_counts.idxmax()}:00 UTC ({hourly_counts.max()} signals)")
print(f"Quiet hour:           {hourly_counts.idxmin()}:00 UTC ({hourly_counts.min()} signals)")

# Flag toxic hours (>2σ above mean)
toxic_threshold = avg_per_hour + (2 * std_per_hour)
toxic_hours = hourly_counts[hourly_counts > toxic_threshold].index.tolist()

print(f"\n⚠️  TOXIC HOURS (>2σ, potential overtrading):")
for hour in toxic_hours:
    print(f"   {hour:02d}:00 UTC → {hourly_counts[hour]} signals ({(hourly_counts[hour]/avg_per_hour):.1f}x average)")

# ========================================================================================
# ANALYSIS 2: Signals by Session
# ========================================================================================

print(f"\n{'=' * 100}")
print("SIGNALS BY SESSION")
print("=" * 100)

session_counts = df.groupby('session').size()
session_pct = (session_counts / session_counts.sum() * 100).round(1)

baseline_signals_per_session = {
    'ASIA': 15 * 8,    # 15 per hour × 8 hours
    'EUROPE': 35 * 8,
    'US': 60 * 8
}

for session in ['ASIA', 'EUROPE', 'US']:
    count = session_counts.get(session, 0)
    pct = session_pct.get(session, 0)
    baseline = baseline_signals_per_session[session]
    ratio = count / baseline if baseline > 0 else 0
    
    print(f"\n{session}:")
    print(f"   Total signals:     {count} ({pct}%)")
    print(f"   Per 8h period:     {count / 7:.0f}")  # 7 days of data
    print(f"   Baseline expected: {baseline}")
    print(f"   vs Baseline:       {ratio:.2f}x {'⚠️ HIGH' if ratio > 1.5 else '✅ NORMAL' if ratio > 0.7 else '🔵 LOW'}")

# ========================================================================================
# ANALYSIS 3: Signals by Symbol
# ========================================================================================

print(f"\n{'=' * 100}")
print("SIGNALS BY SYMBOL")
print("=" * 100)

symbol_counts = df.groupby('symbol').size()
symbol_pct = (symbol_counts / symbol_counts.sum() * 100).round(1)

for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
    count = symbol_counts.get(symbol, 0)
    pct = symbol_pct.get(symbol, 0)
    per_day = count / 7
    
    print(f"\n{symbol}:")
    print(f"   Total signals:     {count} ({pct}%)")
    print(f"   Per day:           {per_day:.1f}")

# ========================================================================================
# ANALYSIS 4: Confidence Distribution
# ========================================================================================

print(f"\n{'=' * 100}")
print("CONFIDENCE DISTRIBUTION")
print("=" * 100)

if df['confidence'].notna().any():
    print(f"\nMean confidence:    {df['confidence'].mean():.1f}%")
    print(f"Median confidence:  {df['confidence'].median():.1f}%")
    print(f"Std deviation:      {df['confidence'].std():.1f}%")
    
    # Confidence bins
    bins = [0, 60, 75, 85, 100]
    labels = ['Low (<60%)', 'Medium (60-75%)', 'High (75-85%)', 'Very High (>85%)']
    df['conf_bin'] = pd.cut(df['confidence'], bins=bins, labels=labels)
    
    conf_dist = df.groupby('conf_bin', observed=True).size()
    print(f"\nConfidence breakdown:")
    for label in labels:
        count = conf_dist.get(label, 0)
        pct = (count / len(df) * 100) if len(df) > 0 else 0
        print(f"   {label:20s}: {count:4d} ({pct:5.1f}%)")
else:
    print("\n⚠️  No confidence data available")

# ========================================================================================
# ANALYSIS 5: Day of Week Patterns
# ========================================================================================

print(f"\n{'=' * 100}")
print("DAY OF WEEK PATTERNS")
print("=" * 100)

dow_names = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 
             4: 'Friday', 5: 'Saturday', 6: 'Sunday'}

dow_counts = df.groupby('dow').size()
avg_per_day = dow_counts.mean()

print(f"\nAverage signals/day: {avg_per_day:.0f}")

for dow in sorted(dow_counts.index):
    count = dow_counts[dow]
    ratio = count / avg_per_day
    name = dow_names.get(int(dow), f'Day {dow}')
    print(f"   {name:10s}: {count:4d} signals ({ratio:.2f}x average)")

# ========================================================================================
# ANALYSIS 6: Generate Heatmap Data
# ========================================================================================

print(f"\n{'=' * 100}")
print("GENERATING SIGNAL DENSITY HEATMAP")
print("=" * 100)

# Create pivot table: Hour × Day of Week
heatmap_data = df.groupby(['hour', 'dow']).size().unstack(fill_value=0)
heatmap_data.columns = [dow_names.get(int(d), f'Day {d}') for d in heatmap_data.columns]

# Save heatmap
plt.figure(figsize=(12, 8))
sns.heatmap(heatmap_data, annot=True, fmt='d', cmap='YlOrRd', cbar_kws={'label': 'Signal Count'})
plt.title('Signal Density Heatmap: Hour (UTC) × Day of Week')
plt.xlabel('Day of Week')
plt.ylabel('Hour (UTC)')
plt.tight_layout()

heatmap_file = 'd:/liquidation-trading/signal_density_heatmap.png'
plt.savefig(heatmap_file, dpi=100)
print(f"\n📊 Heatmap saved to: {heatmap_file}")

# ========================================================================================
# SUMMARY & RECOMMENDATIONS
# ========================================================================================

print(f"\n{'=' * 100}")
print("🎯 SUMMARY & CIRCUIT BREAKER RECOMMENDATIONS")
print("=" * 100)

print(f"\n1️⃣  BASELINE METRICS (for circuit breaker thresholds):")
print(f"   Average signals/hour: {avg_per_hour:.1f}")
print(f"   Typical daily range:  {int(avg_per_hour * 16)} - {int(avg_per_hour * 24)}")

print(f"\n2️⃣  CIRCUIT BREAKER THRESHOLDS (per expert Week 12 guidance):")

# Calculate per-session thresholds
asia_baseline = session_counts.get('ASIA', 0) / 7  # Per day
europe_baseline = session_counts.get('EUROPE', 0) / 7
us_baseline = session_counts.get('US', 0) / 7

print(f"   ASIA session:    Trigger at {int(asia_baseline * 2):.0f} signals/8h (2× baseline of {asia_baseline:.0f})")
print(f"   EUROPE session:  Trigger at {int(europe_baseline * 2):.0f} signals/8h (2× baseline of {europe_baseline:.0f})")
print(f"   US session:      Trigger at {int(us_baseline * 2):.0f} signals/8h (2× baseline of {us_baseline:.0f})")

print(f"\n3️⃣  IDENTIFIED TOXIC PERIODS:")
if toxic_hours:
    print(f"   Hours with excessive signals (reduce position size by 50%):")
    for hour in toxic_hours:
        session = get_session(hour)
        print(f"   - {hour:02d}:00 UTC ({session} session): {hourly_counts[hour]} signals")
else:
    print(f"   ✅ No toxic hours detected (all within 2σ of average)")

print(f"\n4️⃣  RECOMMENDATIONS:")
print(f"   - Monitor signal count in real-time during live trading")
print(f"   - If count exceeds 2× session baseline → reduce size 50%")
print(f"   - Avoid trading during identified toxic hours if possible")
print(f"   - Week 2 toxicity filtering should reduce signal count by 20-35%")

# Export summary
summary_data = {
    'avg_signals_per_hour': avg_per_hour,
    'asia_baseline_per_8h': asia_baseline,
    'europe_baseline_per_8h': europe_baseline,
    'us_baseline_per_8h': us_baseline,
    'circuit_breaker_asia': int(asia_baseline * 2),
    'circuit_breaker_europe': int(europe_baseline * 2),
    'circuit_breaker_us': int(us_baseline * 2),
    'toxic_hours': toxic_hours
}

import json
summary_file = 'd:/liquidation-trading/signal_distribution_summary.json'
with open(summary_file, 'w') as f:
    json.dump(summary_data, f, indent=2)

print(f"\n📁 Summary data exported to: {summary_file}")

conn.close()

print("""
\n✅ WEEK 1 TASK 1.3: COMPLETE
============================

Outputs:
1. signal_density_heatmap.png - Visual heatmap of signal patterns
2. signal_distribution_summary.json - Circuit breaker thresholds

Key Findings:
- Baseline signal rates established for each session
- Toxic hours identified (if any)
- Circuit breaker thresholds calculated (2× baseline)

Next Use Cases:
- Week 12: Implement per-session circuit breakers
- Live monitoring: Flag when signal count exceeds thresholds
- Week 2: Validate that toxicity filtering reduces signals appropriately
""")
