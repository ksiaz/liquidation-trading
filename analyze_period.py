import psycopg2
from datetime import datetime
import numpy as np

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

start_time = datetime(2025, 12, 31, 22, 45, 0)
end_time = datetime.now()

cur.execute("""
    SELECT 
        timestamp,
        (best_bid + best_ask) / 2 as price,
        imbalance,
        (bid_volume_10 + ask_volume_10) as volume,
        spread_pct
    FROM orderbook_snapshots
    WHERE symbol = 'BTCUSDT'
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
""", (start_time, end_time))

rows = cur.fetchall()

if not rows:
    print("No data available")
    exit()

prices = [float(r[1]) for r in rows]
imbalances = [float(r[2]) for r in rows]
volumes = [float(r[3]) for r in rows]

start_price = prices[0]
end_price = prices[-1]
high = max(prices)
low = min(prices)
price_range = high - low
price_change = end_price - start_price

print("=" * 80)
print(f"MARKET ANALYSIS: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
print("=" * 80)

print(f"\n📊 Price Action:")
print(f"   Start: ${start_price:,.2f}")
print(f"   End:   ${end_price:,.2f}")
print(f"   High:  ${high:,.2f}")
print(f"   Low:   ${low:,.2f}")
print(f"   Range: ${price_range:,.2f} ({(price_range/start_price)*100:.2f}%)")
print(f"   Change: ${price_change:+,.2f} ({(price_change/start_price)*100:+.2f}%)")

# Calculate volatility
price_changes = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
avg_change = np.mean(price_changes)
std_change = np.std(price_changes)

print(f"\n📈 Volatility:")
print(f"   Avg tick change: ${avg_change:.2f}")
print(f"   Std deviation: ${std_change:.2f}")

# Imbalance analysis
imb_reversals = sum(1 for i in range(1, len(imbalances)) 
                    if (imbalances[i] > 0) != (imbalances[i-1] > 0))
imb_reversals_per_min = imb_reversals / (len(rows) / 60)

print(f"\n⚖️ Imbalance:")
print(f"   Avg: {np.mean(imbalances):.3f}")
print(f"   Std: {np.std(imbalances):.3f}")
print(f"   Reversals/min: {imb_reversals_per_min:.1f}")

# Range efficiency
range_efficiency = abs(price_change) / price_range if price_range > 0 else 0

print(f"\n🎯 Market Character:")
print(f"   Range Efficiency: {range_efficiency:.1%}")
if range_efficiency < 0.55:
    print(f"   ⚠️ CHOPPY (< 55%)")
elif range_efficiency > 0.75:
    print(f"   ✅ TRENDING (> 75%)")
else:
    print(f"   📊 MIXED")

if imb_reversals_per_min > 6.6:
    print(f"   ⚠️ HIGH IMB REVERSALS (> 6.6/min)")

print(f"\n💡 Why 0 Signals:")
if range_efficiency < 0.55:
    print(f"   • Chop filter blocked (Range Efficiency {range_efficiency:.1%} < 55%)")
if imb_reversals_per_min > 6.6:
    print(f"   • Chop filter blocked (Imb Reversals {imb_reversals_per_min:.1f}/min > 6.6)")
if range_efficiency >= 0.55 and imb_reversals_per_min <= 6.6:
    print(f"   • No quality reversal setups detected")
    print(f"   • Or trend alignment filter blocked counter-trend attempts")

conn.close()
