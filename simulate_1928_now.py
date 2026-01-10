import psycopg2
from datetime import datetime, timedelta

# Only use data after app restart (using data from today)
APP_RESTART_TIME = datetime(2026, 1, 1, 0, 0, 0)

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 80)
print("SYSTEM BEHAVIOR SIMULATION: 02:00 - 06:54 (2026-01-01)")
print("Simulating how our multi-timeframe detector would react")
print("=" * 80)

# Analyze entire move from 02:00 to now (06:54)
start_time = datetime(2026, 1, 1, 2, 0, 0)
end_time = datetime(2026, 1, 1, 6, 54, 0)

cur.execute("""
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        imbalance,
        imbalance_20,
        bid_volume_10,
        ask_volume_10,
        spread_pct
    FROM orderbook_snapshots
    WHERE symbol = 'BTCUSDT'
    AND timestamp >= %s
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
""", (APP_RESTART_TIME, start_time, end_time))

rows = cur.fetchall()

print(f"\n📊 Found {len(rows)} snapshots ({len(rows)/60:.1f} minutes)")

if not rows:
    print("❌ No data available")
    conn.close()
    exit()

# Calculate prices
prices = [(r[1] + r[2]) / 2 for r in rows]
start_price = prices[0]
current_price = prices[-1]
total_move = ((current_price - start_price) / start_price) * 100

print(f"\n🎯 OVERALL MOVE:")
print(f"   Start: ${start_price:,.2f} at {rows[0][0].strftime('%H:%M:%S')}")
print(f"   End:   ${current_price:,.2f} at {rows[-1][0].strftime('%H:%M:%S')}")
print(f"   Move:  {total_move:+.3f}%")

# Find key turning points
min_price = min(prices)
max_price = max(prices)
min_idx = prices.index(min_price)
max_idx = prices.index(max_price)

print(f"\n📍 KEY LEVELS:")
print(f"   High: ${max_price:,.2f} at {rows[max_idx][0].strftime('%H:%M:%S')}")
print(f"   Low:  ${min_price:,.2f} at {rows[min_idx][0].strftime('%H:%M:%S')}")

# Simulate system behavior minute-by-minute
print(f"\n{'=' * 80}")
print("MINUTE-BY-MINUTE SYSTEM SIMULATION")
print(f"{'=' * 80}")

# Group by minute
by_minute = {}
for i, row in enumerate(rows):
    minute = row[0].strftime('%H:%M')
    if minute not in by_minute:
        by_minute[minute] = []
    by_minute[minute].append((i, row))

# Track trade state
trade_active = False
entry_price = None
entry_time = None
target_1_hit = False
position_remaining = 100
stop_loss = None
total_pnl = 0

print("\nLegend:")
print("  🔍 = Analyzing")
print("  🎯 = Signal detected")
print("  💰 = Target hit")
print("  🛑 = Stop loss")
print("  📊 = Position update")

for minute in sorted(by_minute.keys()):
    snapshots = by_minute[minute]
    
    # Get minute stats
    first_idx, first_row = snapshots[0]
    last_idx, last_row = snapshots[-1]
    
    first_price = (first_row[1] + first_row[2]) / 2
    last_price = (last_row[1] + last_row[2]) / 2
    
    # Imbalance stats
    imbalances = [s[1][3] for s in snapshots]
    avg_imb = sum(imbalances) / len(imbalances)
    
    # Price direction
    price_change = last_price - first_price
    price_change_pct = (price_change / first_price) * 100
    
    print(f"\n{minute} - Price: ${first_price:,.2f} → ${last_price:,.2f} ({price_change_pct:+.3f}%)")
    print(f"       Imbalance: {avg_imb:+.4f}")
    
    # ENTRY DETECTION (if no trade active)
    # Look for signals in first 10 minutes
    if not trade_active and minute >= '02:00' and minute <= '02:10':
        # Check for SHORT signal at top
        # Look for: Price rising but imbalance weakening
        
        # Get 1-min lookback
        lookback_start = max(0, first_idx - 60)
        lookback_data = rows[lookback_start:first_idx]
        
        if len(lookback_data) >= 30:
            # Split into earlier and recent
            split = len(lookback_data) * 2 // 3
            earlier_imb = [r[3] for r in lookback_data[:split]]
            recent_imb = [r[3] for r in lookback_data[split:]]
            
            earlier_prices = [(r[1] + r[2]) / 2 for r in lookback_data[:split]]
            recent_prices = [(r[1] + r[2]) / 2 for r in lookback_data[split:]]
            
            if earlier_imb and recent_imb and earlier_prices and recent_prices:
                imb_flip = sum(recent_imb) / len(recent_imb) - sum(earlier_imb) / len(earlier_imb)
                price_trend = sum(recent_prices) / len(recent_prices) - sum(earlier_prices) / len(earlier_prices)
                
                # Bearish divergence: Price up, imbalance down
                if price_trend > 0 and imb_flip < -0.2:
                    trade_active = True
                    entry_price = float(last_price)
                    entry_time = minute
                    stop_loss = entry_price * 1.0025  # +0.25% stop
                    target_1 = entry_price * 0.995  # -0.5% target
                    
                    print(f"  🎯 SHORT SIGNAL DETECTED!")
                    print(f"     Entry: ${entry_price:,.2f}")
                    print(f"     Target 1: ${target_1:,.2f} (-0.5%)")
                    print(f"     Stop: ${stop_loss:,.2f} (+0.25%)")
                    print(f"     Reason: Bearish divergence (price +, imbalance {imb_flip:+.2f})")

    
    # TRADE MANAGEMENT (if trade active)
    if trade_active:
        current = float(last_price)
        
        # Check stop loss
        if current >= stop_loss:
            pnl = ((entry_price - current) / entry_price) * 100
            total_pnl += pnl * (position_remaining / 100)
            print(f"  🛑 STOP LOSS HIT at ${current:,.2f}")
            print(f"     PnL: {pnl:.3f}% on {position_remaining}% position")
            print(f"     Total PnL: {total_pnl:.3f}%")
            trade_active = False
            continue
        
        # Check target 1
        if not target_1_hit:
            target_1 = entry_price * 0.995
            if current <= target_1:
                target_1_hit = True
                position_remaining = 50
                stop_loss = entry_price  # Move to breakeven
                pnl_t1 = 0.5  # 0.5% on 50% position
                total_pnl += pnl_t1
                
                print(f"  💰 TARGET 1 HIT at ${current:,.2f}")
                print(f"     Closed 50% at +0.5% = +{pnl_t1:.2f}%")
                print(f"     Stop moved to breakeven: ${stop_loss:,.2f}")
                print(f"     Runner: 50% remaining")
        
        # Check for pivot (exit runner)
        if target_1_hit:
            # Look for bullish signals (opposite of entry)
            # Check if imbalance flipping positive
            if avg_imb > 0.3:
                pnl_runner = ((entry_price - current) / entry_price) * 100 * 0.5
                total_pnl += pnl_runner
                
                print(f"  📊 PIVOT DETECTED - Exiting runner at ${current:,.2f}")
                print(f"     Runner PnL: {pnl_runner:.3f}%")
                print(f"     Total PnL: {total_pnl:.3f}%")
                trade_active = False
                continue
        
        # Show current PnL
        unrealized = ((entry_price - current) / entry_price) * 100 * (position_remaining / 100)
        print(f"     Current: ${current:,.2f} | Unrealized: {unrealized:+.3f}% | Total: {total_pnl + unrealized:.3f}%")


# Final summary
print(f"\n{'=' * 80}")
print("TRADE SUMMARY")
print(f"{'=' * 80}")

if trade_active:
    final_pnl = ((entry_price - float(current_price)) / entry_price) * 100 * (position_remaining / 100)
    total_pnl += final_pnl
    print(f"\n⚠️ TRADE STILL OPEN")
    print(f"   Entry: ${entry_price:,.2f} at {entry_time}")
    print(f"   Current: ${current_price:,.2f}")
    print(f"   Position: {position_remaining}%")
    print(f"   Unrealized PnL: {final_pnl:+.3f}%")


print(f"\n💰 TOTAL REALIZED PnL: {total_pnl:+.3f}%")
print(f"\n📊 WITH 10x LEVERAGE: {total_pnl * 10:+.2f}%")

print(f"\n{'=' * 80}")

conn.close()
