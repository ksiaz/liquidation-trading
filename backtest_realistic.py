"""
Realistic backtest with proper position management:
- Target 1: 0.25% (exit 50%, SL to breakeven)
- Target 2: Opposite signal (exit remaining 50%)
- Stop: -0.25% (full position before T1, breakeven after T1)
"""

import sys
import psycopg2
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

sys.path.insert(0, 'd:/liquidation-trading')
from early_reversal_detector import EarlyReversalDetector

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 100)
print("REALISTIC BACKTEST - Proper Position Management")
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
    
    detector = EarlyReversalDetector(
        max_lookback_seconds=300,
        snr_threshold=0.15
    )
    
    # Track active position
    active_position = None
    
    for i, row in enumerate(rows):
        timestamp, best_bid, best_ask, imbalance, bid_vol, ask_vol, spread_pct = row
        
        current_price = float((best_bid + best_ask) / 2)
        
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
        
        # Check active position first
        if active_position:
            pos = active_position
            direction = pos['direction']
            entry_price = pos['entry_price']
            
            # Calculate current P&L
            if direction == 'LONG':
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                
                # Check Target 1 (0.25%)
                if not pos['t1_hit'] and pnl_pct >= 0.25:
                    pos['t1_hit'] = True
                    pos['t1_pnl'] = 0.25  # Lock in 50% at 0.25%
                    pos['sl_price'] = entry_price  # Move SL to breakeven
                    pos['remaining'] = 0.5  # 50% left
                
                # Check Stop Loss
                if pos['t1_hit']:
                    # After T1: breakeven stop
                    if current_price <= pos['sl_price']:
                        pos['t2_pnl'] = 0  # Breakeven on remaining 50%
                        pos['exit_reason'] = 'BREAKEVEN STOP'
                        pos['exit_time'] = timestamp
                        active_position = None
                else:
                    # Before T1: original stop at -0.25%
                    if pnl_pct <= -0.25:
                        pos['t1_pnl'] = -0.25  # Full stop
                        pos['t2_pnl'] = 0
                        pos['exit_reason'] = 'STOP LOSS'
                        pos['exit_time'] = timestamp
                        active_position = None
                
                # Check for opposite signal (Target 2)
                if signal and signal['direction'] == 'SHORT' and pos['t1_hit']:
                    pos['t2_pnl'] = pnl_pct  # Exit remaining at current price
                    pos['exit_reason'] = 'OPPOSITE SIGNAL'
                    pos['exit_time'] = timestamp
                    active_position = None
                    
            else:  # SHORT
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
                
                # Check Target 1 (0.25%)
                if not pos['t1_hit'] and pnl_pct >= 0.25:
                    pos['t1_hit'] = True
                    pos['t1_pnl'] = 0.25
                    pos['sl_price'] = entry_price
                    pos['remaining'] = 0.5
                
                # Check Stop Loss
                if pos['t1_hit']:
                    if current_price >= pos['sl_price']:
                        pos['t2_pnl'] = 0
                        pos['exit_reason'] = 'BREAKEVEN STOP'
                        pos['exit_time'] = timestamp
                        active_position = None
                else:
                    if pnl_pct <= -0.25:
                        pos['t1_pnl'] = -0.25
                        pos['t2_pnl'] = 0
                        pos['exit_reason'] = 'STOP LOSS'
                        pos['exit_time'] = timestamp
                        active_position = None
                
                # Check for opposite signal
                if signal and signal['direction'] == 'LONG' and pos['t1_hit']:
                    pos['t2_pnl'] = pnl_pct
                    pos['exit_reason'] = 'OPPOSITE SIGNAL'
                    pos['exit_time'] = timestamp
                    active_position = None
            
            # If position closed, record trade
            if not active_position and pos.get('exit_time'):
                total_pnl = (pos['t1_pnl'] * 0.5) + (pos['t2_pnl'] * 0.5)
                all_trades.append({
                    'symbol': symbol,
                    'entry_time': pos['entry_time'],
                    'exit_time': pos['exit_time'],
                    'direction': pos['direction'],
                    'entry_price': pos['entry_price'],
                    't1_pnl': pos['t1_pnl'],
                    't2_pnl': pos['t2_pnl'],
                    'total_pnl': total_pnl,
                    'exit_reason': pos['exit_reason'],
                    'snr': pos['snr']
                })
        
        # Open new position if signal and no active position
        if signal and not active_position:
            active_position = {
                'symbol': symbol,
                'entry_time': timestamp,
                'direction': signal['direction'],
                'entry_price': current_price,
                'sl_price': current_price * (0.9975 if signal['direction'] == 'LONG' else 1.0025),
                't1_hit': False,
                't1_pnl': 0,
                't2_pnl': 0,
                'remaining': 1.0,
                'snr': signal['snr']
            }
    
    # Close any remaining position at end
    if active_position:
        pos = active_position
        if pos['direction'] == 'LONG':
            pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
        else:
            pnl_pct = ((pos['entry_price'] - current_price) / pos['entry_price']) * 100
        
        if pos['t1_hit']:
            pos['t2_pnl'] = pnl_pct
        else:
            pos['t1_pnl'] = pnl_pct
            pos['t2_pnl'] = 0
        
        total_pnl = (pos['t1_pnl'] * 0.5) + (pos['t2_pnl'] * 0.5)
        all_trades.append({
            'symbol': symbol,
            'entry_time': pos['entry_time'],
            'exit_time': timestamp,
            'direction': pos['direction'],
            'entry_price': pos['entry_price'],
            't1_pnl': pos['t1_pnl'],
            't2_pnl': pos['t2_pnl'],
            'total_pnl': total_pnl,
            'exit_reason': 'END OF DATA',
            'snr': pos['snr']
        })
    
    print(f"\n✅ Trades Completed: {len([t for t in all_trades if t['symbol'] == symbol])}")

# Summary
print(f"\n{'=' * 100}")
print("PERFORMANCE SUMMARY")
print(f"{'=' * 100}")

if not all_trades:
    print("\n❌ No trades generated")
else:
    total_pnl = sum(t['total_pnl'] for t in all_trades)
    winners = [t for t in all_trades if t['total_pnl'] > 0]
    losers = [t for t in all_trades if t['total_pnl'] < 0]
    
    print(f"\n  Total Trades:    {len(all_trades)}")
    print(f"  Winners:         {len(winners)} ({len(winners)/len(all_trades)*100:.1f}%)")
    print(f"  Losers:          {len(losers)} ({len(losers)/len(all_trades)*100:.1f}%)")
    print(f"  Total P&L:       {total_pnl:+.3f}%")
    print(f"  Average P&L:     {total_pnl/len(all_trades):+.3f}%")
    print(f"  With 10x Lev:    {total_pnl * 10:+.2f}%")
    
    if winners:
        print(f"  Avg Win:         {sum(t['total_pnl'] for t in winners)/len(winners):+.3f}%")
    if losers:
        print(f"  Avg Loss:        {sum(t['total_pnl'] for t in losers)/len(losers):+.3f}%")
    
    # Exit reason breakdown
    print(f"\n  Exit Reasons:")
    reasons = {}
    for t in all_trades:
        r = t['exit_reason']
        reasons[r] = reasons.get(r, 0) + 1
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count} ({count/len(all_trades)*100:.1f}%)")
    
    # Compare T1 vs T2 performance
    t1_avg = sum(t['t1_pnl'] for t in all_trades) / len(all_trades)
    t2_avg = sum(t['t2_pnl'] for t in all_trades) / len(all_trades)
    print(f"\n  Avg T1 (50%):    {t1_avg:+.3f}%")
    print(f"  Avg T2 (50%):    {t2_avg:+.3f}%")

print(f"\n{'=' * 100}\n")

conn.close()
