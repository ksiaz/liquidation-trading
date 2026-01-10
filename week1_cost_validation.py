"""
Week 1 Critical Validation: Cost-Adjusted Backtest

Based on Expert #1's guidance:
1. Add REAL fees (0.02% maker, 0.04% taker)
2. Load REAL spread data from database
3. Calculate actual execution costs
4. Determine if system is profitable after costs

DECISION GATE: If real_pnl < 0, STOP and fix execution first.
"""

import psycopg2
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()

# Database connection
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', 5432),
    database=os.getenv('DB_NAME', 'trading_system'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', '')
)
cur = conn.cursor()

print("=" * 80)
print("WEEK 1 CRITICAL VALIDATION: COST-ADJUSTED BACKTEST")
print("=" * 80)

# Parameters from Expert #1
MAKER_FEE = 0.0002  # 0.02% (limit orders)
TAKER_FEE = 0.0004  # 0.04% (market orders)
LIMIT_ORDER_FILL_RATE = 0.60  # 60% of signals

def get_real_spread(symbol, timestamp):
    """
    Get actual spread from orderbook_snapshots at exact timestamp.
    Returns spread as percentage of midprice.
    """
    query = """
    SELECT 
        best_bid,
        best_ask,
        ((best_ask - best_bid) / ((best_ask + best_bid) / 2.0)) as spread_pct
    FROM orderbook_snapshots
    WHERE symbol = %s 
    AND timestamp >= %s - INTERVAL '5 seconds'
    AND timestamp <= %s + INTERVAL '5 seconds'
    ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
    LIMIT 1
    """
    
    cur.execute(query, (symbol, timestamp, timestamp, timestamp))
    result = cur.fetchone()
    
    if result:
        return result[2]  # spread_pct
    else:
        # Fallback to average spread
        return 0.0001  # 0.01% average

def calculate_costs_market_orders():
    """Calculate costs assuming market orders (current approach)."""
    
    print("\n" + "=" * 80)
    print("SCENARIO 1: MARKET ORDERS (Current Approach)")
    print("=" * 80)
    
    # Get all historical signals
    query = """
    SELECT 
        timestamp,
        symbol,
        direction,
        entry_price,
        confidence
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    ORDER BY timestamp DESC
    """
    
    cur.execute(query)
    signals = cur.fetchall()
    
    print(f"\nTotal signals (24h): {len(signals)}")
    
    total_cost = 0
    spread_costs = []
    
    for signal in signals:
        timestamp, symbol, direction, entry_price, confidence = signal
        
        # Get real spread at signal time
        spread_pct = get_real_spread(symbol, timestamp)
        spread_costs.append(float(spread_pct) * 100 if spread_pct else 0)  # Convert to percentage
        
        # Cost = Spread + Taker Fee
        cost_pct = float(spread_pct) + TAKER_FEE if spread_pct else TAKER_FEE
        total_cost += cost_pct * 100  # As percentage
    
    avg_cost_per_trade = total_cost / len(signals) if signals else 0
    avg_spread = np.mean(spread_costs) if spread_costs else 0
    
    print(f"\n📊 COST BREAKDOWN:")
    print(f"   Average Spread:        {avg_spread:.3f}%")
    print(f"   Taker Fee:             {TAKER_FEE * 100:.3f}%")
    print(f"   Average Cost/Trade:    {avg_cost_per_trade:.3f}%")
    print(f"   Total Cost (all {len(signals)} trades): {total_cost:.2f}%")
    
    return avg_cost_per_trade, total_cost

def calculate_costs_limit_orders():
    """Calculate costs assuming limit orders at bid (Expert #1 recommendation)."""
    
    print("\n" + "=" * 80)
    print("SCENARIO 2: LIMIT ORDERS at BID (Expert #1 Recommendation)")
    print("=" * 80)
    
    query = """
    SELECT 
        timestamp,
        symbol,
        direction,
        entry_price,
        confidence
    FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    ORDER BY timestamp DESC
    """
    
    cur.execute(query)
    signals = cur.fetchall()
    
    # Apply fill rate
    filled_signals = int(len(signals) * LIMIT_ORDER_FILL_RATE)
    
    print(f"\nTotal signals:     {len(signals)}")
    print(f"Fill rate:         {LIMIT_ORDER_FILL_RATE * 100:.0f}%")
    print(f"Filled signals:    {filled_signals}")
    print(f"Skipped signals:   {len(signals) - filled_signals}")
    
    # Cost for limit orders: Only maker fee (no spread cost)
    cost_per_trade_pct = MAKER_FEE * 100  # 0.02%
    total_cost = cost_per_trade_pct * filled_signals
    
    print(f"\n📊 COST BREAKDOWN:")
    print(f"   Spread Cost:           0.000% (limit at bid)")
    print(f"   Maker Fee:             {MAKER_FEE * 100:.3f}%")
    print(f"   Cost per Trade:        {cost_per_trade_pct:.3f}%")
    print(f"   Total Cost ({filled_signals} filled): {total_cost:.2f}%")
    
    return cost_per_trade_pct, total_cost, filled_signals

def estimate_gross_pnl():
    """
    Estimate gross PnL from backtest results.
    Using the reported +3.29% over 8 hours.
    """
    
    # From Expert feedback analysis: +3.29% over 8h with 42 signals
    BACKTEST_PNL_8H = 3.29  # Percentage
    BACKTEST_SIGNALS_8H = 42
    
    # Scale to 24h
    signals_24h_query = """
    SELECT COUNT(*) FROM trading_signals
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    """
    cur.execute(signals_24h_query)
    actual_signals_24h = cur.fetchone()[0]
    
    # Estimate gross PnL proportionally
    estimated_gross_pnl = (actual_signals_24h / BACKTEST_SIGNALS_8H) * BACKTEST_PNL_8H
    
    return estimated_gross_pnl, actual_signals_24h

def main():
    # Get gross PnL estimate
    gross_pnl_24h, signals_24h = estimate_gross_pnl()
    
    print(f"\n📈 GROSS PnL ESTIMATE (24h):")
    print(f"   Signals:      {signals_24h}")
    print(f"   Gross PnL:    +{gross_pnl_24h:.2f}%")
    
    # Scenario 1: Market Orders
    market_cost_per_trade, market_total_cost = calculate_costs_market_orders()
    market_real_pnl = gross_pnl_24h - market_total_cost
    
    print(f"\n🔴 SCENARIO 1 RESULT (Market Orders):")
    print(f"   Gross PnL:    +{gross_pnl_24h:.2f}%")
    print(f"   Total Cost:   -{market_total_cost:.2f}%")
    print(f"   ═══════════════════════════════════")
    print(f"   REAL PnL:     {market_real_pnl:+.2f}%")
    
    if market_real_pnl < 0:
        print(f"\n   ❌ VERDICT:   UNPROFITABLE")
        print(f"   ACTION:       DO NOT GO LIVE WITH MARKET ORDERS")
    elif market_real_pnl < 0.5:
        print(f"\n   ⚠️  VERDICT:   MARGINALLY PROFITABLE")
        print(f"   ACTION:       HIGH RISK - UPGRADE EXECUTION")
    else:
        print(f"\n   ✅ VERDICT:   PROFITABLE")
        print(f"   ACTION:       CAN PROCEED (but limit orders better)")
    
    # Scenario 2: Limit Orders
    limit_cost_per_trade, limit_total_cost, filled_count = calculate_costs_limit_orders()
    
    # Adjust gross PnL for reduced signal count
    limit_gross_pnl = gross_pnl_24h * (filled_count / signals_24h)
    limit_real_pnl = limit_gross_pnl - limit_total_cost
    
    print(f"\n🟢 SCENARIO 2 RESULT (Limit Orders at Bid):")
    print(f"   Gross PnL:    +{limit_gross_pnl:.2f}% ({filled_count} fills)")
    print(f"   Total Cost:   -{limit_total_cost:.2f}%")
    print(f"   ═══════════════════════════════════")
    print(f"   REAL PnL:     {limit_real_pnl:+.2f}%")
    
    if limit_real_pnl < 0:
        print(f"\n   ❌ VERDICT:   UNPROFITABLE")
        print(f"   ACTION:       DETECTOR QUALITY ISSUE")
    elif limit_real_pnl < 0.5:
        print(f"\n   ⚠️  VERDICT:   MARGINALLY PROFITABLE")
        print(f"   ACTION:       IMPROVE FILTERING")
    else:
        print(f"\n   ✅ VERDICT:   PROFITABLE")
        print(f"   ACTION:       PROCEED TO WEEK 2")
    
    # Comparison
    print(f"\n" + "=" * 80)
    print("COMPARISON: Limit vs Market Orders")
    print("=" * 80)
    print(f"Market Orders Real PnL:  {market_real_pnl:+.2f}%")
    print(f"Limit Orders Real PnL:   {limit_real_pnl:+.2f}%")
    print(f"Improvement:             {(limit_real_pnl - market_real_pnl):+.2f}%")
    
    savings_pct = ((limit_real_pnl - market_real_pnl) / abs(market_real_pnl) * 100) if market_real_pnl != 0 else 0
    print(f"Cost Reduction:          {savings_pct:+.1f}%")
    
    # DECISION GATE
    print(f"\n" + "=" * 80)
    print("🚨 DECISION GATE (Expert #1's Criteria)")
    print("=" * 80)
    
    if limit_real_pnl >= 0.5:
        print("✅ PASS: Real PnL >+0.5% daily")
        print("✅ ACTION: Proceed to Week 2 - Implement limit order execution")
        return True
    elif limit_real_pnl >= 0:
        print("⚠️  BORDERLINE: Real PnL >0% but <0.5%")
        print("⚠️  ACTION: Improve signal filtering before live deployment")
        return False
    else:
        print("❌ FAIL: Real PnL <0%")
        print("❌ ACTION: STOP - Fix execution and/or detector quality first")
        print("\n   Recommendations:")
        print("   1. Increase confidence threshold (60% → 75%+)")
        print("   2. Implement toxicity filtering (CTR-based)")
        print("   3. Add passive vs active drain classification")
        return False

if __name__ == "__main__":
    try:
        result = main()
        conn.close()
        
        exit_code = 0 if result else 1
        exit(exit_code)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        exit(1)
