"""
Backtest adjusted signal detector parameters.
Shows what trades would have been generated with SNR threshold = 0.15
"""

import sys
import psycopg2
from datetime import datetime, timedelta
from collections import deque
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Import detector
sys.path.insert(0, 'd:/liquidation-trading')
from early_reversal_detector import EarlyReversalDetector

# Database connection
conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 100)
print("BACKTEST WITH ADJUSTED PARAMETERS (SNR = 0.15)")
print("=" * 100)

# Test period: Last 24 hours
end_time = datetime(2026, 1, 1, 7, 0, 0)
start_time = end_time - timedelta(hours=24)

symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
all_trades = []

for symbol in symbols:
    print(f"\n{'=' * 100}")
    print(f"TESTING {symbol}")
    print(f"{'=' * 100}")
    
    # Get orderbook data
    cur.execute("""
        SELECT 
            timestamp,
            best_bid,
            best_ask,
            imbalance,
            bid_volume_10,
            ask_volume_10,
            spread_pct
        FROM orderbook_snapshots
        WHERE symbol = %s
        AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp
    """, (symbol, start_time, end_time))
    
    rows = cur.fetchall()
    
    if not rows:
        print(f"   ⚠️ No data for {symbol}")
        continue
    
    print(f"\n📊 Processing {len(rows)} snapshots...")
    
    # Initialize detector with NEW parameters
    detector = EarlyReversalDetector(
        max_lookback_seconds=300,
        snr_threshold=0.15  # NEW: Lowered from 0.3
    )
    
    signals_generated = []
    
    # Process each snapshot
    for i, row in enumerate(rows):
        timestamp, best_bid, best_ask, imbalance, bid_vol, ask_vol, spread_pct = row
        
        # Create orderbook data dict
        orderbook_data = {
            'timestamp': timestamp,
            'symbol': symbol,
            'best_bid': float(best_bid),
            'best_ask': float(best_ask),
            'imbalance': float(imbalance) if imbalance else 0,
            'bid_volume_10': float(bid_vol) if bid_vol else 0,
            'ask_volume_10': float(ask_vol) if ask_vol else 0,
            'spread_pct': float(spread_pct) if spread_pct else 0
        }
        
        # Update detector
        signal = detector.update(orderbook_data)
        
        if signal:
            signals_generated.append(signal)
            
            # Calculate potential P&L (simplified)
            entry_price = float(signal['entry_price'])
            direction = signal['direction']
            
            # Look ahead 5 minutes to see what happened
            future_idx = min(i + 300, len(rows) - 1)
            future_prices = [float((rows[j][1] + rows[j][2]) / 2) for j in range(i, future_idx)]
            
            if direction == 'LONG':
                # Target: +0.5%, Stop: -0.25%
                target = entry_price * 1.005
                stop = entry_price * 0.9975
                
                # Check if target or stop hit
                max_price = max(future_prices)
                min_price = min(future_prices)
                
                if max_price >= target:
                    pnl = 0.5
                    outcome = "TARGET HIT"
                elif min_price <= stop:
                    pnl = -0.25
                    outcome = "STOP HIT"
                else:
                    final_price = future_prices[-1]
                    pnl = ((final_price - entry_price) / entry_price) * 100
                    outcome = "OPEN"
            else:  # SHORT
                target = entry_price * 0.995
                stop = entry_price * 1.0025
                
                min_price = min(future_prices)
                max_price = max(future_prices)
                
                if min_price <= target:
                    pnl = 0.5
                    outcome = "TARGET HIT"
                elif max_price >= stop:
                    pnl = -0.25
                    outcome = "STOP HIT"
                else:
                    final_price = future_prices[-1]
                    pnl = ((entry_price - final_price) / entry_price) * 100
                    outcome = "OPEN"
            
            trade = {
                'symbol': symbol,
                'timestamp': timestamp,
                'direction': direction,
                'entry_price': entry_price,
                'confidence': signal['confidence'],
                'snr': signal['snr'],
                'timeframe': signal['timeframe'],
                'signals_confirmed': signal['signals_confirmed'],
                'pnl': pnl,
                'outcome': outcome
            }
            
            all_trades.append(trade)
    
    print(f"\n✅ Signals Generated: {len(signals_generated)}")
    
    if signals_generated:
        for sig in signals_generated:
            print(f"\n   🎯 {sig['direction']} Signal")
            print(f"      Time: {sig['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"      Entry: ${sig['entry_price']:,.2f}")
            print(f"      Confidence: {sig['confidence']}%")
            print(f"      SNR: {sig['snr']:.3f}")
            print(f"      Timeframe: {sig['timeframe']}s")
            print(f"      Signals: {sig['signals_confirmed']}/{len([k for k, v in sig['signals'].items() if v])}")

# Summary
print(f"\n{'=' * 100}")
print("TRADE SUMMARY")
print(f"{'=' * 100}")

if not all_trades:
    print("\n❌ No trades generated")
    print("\nPossible reasons:")
    print("  - Market too choppy (chop filter active)")
    print("  - Not enough data points for analysis")
    print("  - SNR still too strict for current conditions")
else:
    print(f"\n📊 Total Trades: {len(all_trades)}")
    
    # Group by symbol
    by_symbol = {}
    for trade in all_trades:
        sym = trade['symbol']
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(trade)
    
    # Print detailed trade list
    print(f"\n{'=' * 100}")
    print("DETAILED TRADE LIST")
    print(f"{'=' * 100}")
    
    for sym in symbols:
        if sym not in by_symbol:
            continue
        
        trades = by_symbol[sym]
        print(f"\n{sym} - {len(trades)} trades")
        print("-" * 100)
        
        for i, trade in enumerate(trades, 1):
            print(f"\n  Trade #{i}")
            print(f"    Time:      {trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    Direction: {trade['direction']}")
            print(f"    Entry:     ${trade['entry_price']:,.2f}")
            print(f"    SNR:       {trade['snr']:.3f}")
            print(f"    Signals:   {trade['signals_confirmed']}")
            print(f"    Outcome:   {trade['outcome']}")
            print(f"    P&L:       {trade['pnl']:+.3f}%")
    
    # Calculate statistics
    total_pnl = sum(t['pnl'] for t in all_trades)
    avg_pnl = total_pnl / len(all_trades)
    winners = [t for t in all_trades if t['pnl'] > 0]
    losers = [t for t in all_trades if t['pnl'] < 0]
    
    print(f"\n{'=' * 100}")
    print("PERFORMANCE METRICS")
    print(f"{'=' * 100}")
    print(f"\n  Total Trades:    {len(all_trades)}")
    print(f"  Winners:         {len(winners)} ({len(winners)/len(all_trades)*100:.1f}%)")
    print(f"  Losers:          {len(losers)} ({len(losers)/len(all_trades)*100:.1f}%)")
    print(f"  Total P&L:       {total_pnl:+.3f}%")
    print(f"  Average P&L:     {avg_pnl:+.3f}%")
    print(f"  With 10x Lev:    {total_pnl * 10:+.2f}%")
    
    if winners:
        avg_win = sum(t['pnl'] for t in winners) / len(winners)
        print(f"  Avg Win:         {avg_win:+.3f}%")
    
    if losers:
        avg_loss = sum(t['pnl'] for t in losers) / len(losers)
        print(f"  Avg Loss:        {avg_loss:+.3f}%")
    
    # SNR distribution
    avg_snr = sum(t['snr'] for t in all_trades) / len(all_trades)
    print(f"\n  Average SNR:     {avg_snr:.3f}")
    print(f"  SNR Range:       {min(t['snr'] for t in all_trades):.3f} - {max(t['snr'] for t in all_trades):.3f}")

print(f"\n{'=' * 100}\n")

conn.close()
