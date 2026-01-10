"""
Simulate V-bottom detection with new thresholds on recent data.
Shows exact entry price and timing.
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

# Look at last 30 minutes of ETH data
start_time = datetime.now() - timedelta(minutes=30)

print("=" * 80)
print("V-BOTTOM SIMULATION - What Would Trigger with New Thresholds")
print("=" * 80)

# Get orderbook snapshots
cur = conn.cursor()
cur.execute("""
    SELECT 
        timestamp,
        bid_depth_5,
        ask_depth_5,
        spread,
        price
    FROM orderbook_snapshots
    WHERE symbol = 'ETHUSDT'
        AND timestamp >= %s
    ORDER BY timestamp
""", (start_time,))

snapshots = cur.fetchall()

if not snapshots:
    print("\n❌ No orderbook data found")
    exit()

print(f"\nAnalyzing {len(snapshots)} orderbook snapshots...")
print("\nNew Thresholds:")
print("  SELLOFF_THRESHOLD = -0.08 (-8% orderbook skew)")
print("  BID_REFILL = 50% increase from low")
print("  CAPITULATION_SPREAD = 0.002 (0.2%)")

# Calculate skew for each snapshot
print("\n" + "=" * 80)
print("ORDERBOOK SKEW ANALYSIS")
print("=" * 80)
print(f"{'Time':<20} {'Price':<10} {'Bid Depth':<12} {'Ask Depth':<12} {'Skew':<8} {'State'}")
print("-" * 80)

state = "NORMAL"
selloff_detected = False
capitulation_detected = False
reversal_price = None
reversal_time = None
min_bid_depth = float('inf')
selloff_start_price = None

for i, (ts, bid_depth, ask_depth, spread, price) in enumerate(snapshots):
    # Calculate skew
    total_depth = bid_depth + ask_depth
    if total_depth > 0:
        skew = (bid_depth - ask_depth) / total_depth
    else:
        skew = 0
    
    # Track minimum bid depth
    if bid_depth < min_bid_depth:
        min_bid_depth = bid_depth
    
    # State machine simulation
    prev_state = state
    
    # Check for SELLOFF (skew < -0.08)
    if state == "NORMAL" and skew < -0.08:
        state = "SELLOFF"
        selloff_start_price = price
        selloff_detected = True
    
    # Check for CAPITULATION (in selloff + spread widens)
    elif state == "SELLOFF" and spread > 0.002:
        state = "CAPITULATION"
        capitulation_detected = True
    
    # Check for REVERSAL (bid refill from low)
    elif state == "CAPITULATION":
        bid_refill_pct = (bid_depth - min_bid_depth) / min_bid_depth if min_bid_depth > 0 else 0
        if bid_refill_pct > 0.5:  # 50% refill
            state = "REVERSAL"
            reversal_price = price
            reversal_time = ts
    
    # Print every 10th snapshot or state changes
    if i % 10 == 0 or state != prev_state:
        print(f"{str(ts):<20} ${price:<9.2f} ${bid_depth:<11,.0f} ${ask_depth:<11,.0f} {skew:>+7.2%} {state}")

print("\n" + "=" * 80)
print("SIGNAL GENERATION")
print("=" * 80)

if reversal_price and reversal_time:
    print(f"\n✅ V-BOTTOM SIGNAL WOULD BE GENERATED!")
    print(f"\n📍 ENTRY DETAILS:")
    print(f"  Time:  {reversal_time}")
    print(f"  Price: ${reversal_price:.2f}")
    print(f"  Type:  V_BOTTOM LONG")
    print(f"\n📊 PATTERN METRICS:")
    if selloff_start_price:
        selloff_pct = ((reversal_price - selloff_start_price) / selloff_start_price) * 100
        print(f"  Selloff: {selloff_pct:.2f}%")
    print(f"  Min bid depth: ${min_bid_depth:,.0f}")
    print(f"\n🎯 TRADE SETUP:")
    print(f"  Entry:  ${reversal_price:.2f}")
    print(f"  Stop:   ${reversal_price * 0.995:.2f} (-0.5%)")
    print(f"  Target: ${reversal_price * 1.015:.2f} (+1.5%)")
    print(f"  R:R:    1:3")
    
elif selloff_detected:
    print(f"\n⚠️  SELLOFF detected but no reversal yet")
    print(f"  State: {state}")
    print(f"  Waiting for bid refill...")
    
else:
    print(f"\n❌ No V-bottom pattern detected in this timeframe")
    print(f"  Market was stable (no selloff)")
    print(f"  Max negative skew seen: {min([((b-a)/(b+a)) for _, b, a, _, _ in snapshots if b+a > 0]):.2%}")

cur.close()
conn.close()
