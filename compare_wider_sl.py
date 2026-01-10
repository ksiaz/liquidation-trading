"""
Exit Strategy Comparison v2 - Testing Wider Parameters
Based on analysis: 0.25% SL is too tight for SOL volatility.
Testing: SL 0.4% with various TP configurations
"""

import psycopg2
from datetime import datetime, timedelta
from early_reversal_detector import EarlyReversalDetector
import os
from dotenv import load_dotenv

load_dotenv()

def run_wider_sl_comparison():
    """
    Test wider SL (0.4%) with different TP strategies.
    """
    
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'liquidation_trading'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    
    cursor = conn.cursor()
    
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=8)
    
    cursor.execute("""
        SELECT symbol, best_bid, best_ask, bid_volume_10, ask_volume_10, 
               spread_pct, timestamp
        FROM orderbook_snapshots
        WHERE symbol = 'SOLUSDT'
          AND timestamp >= %s
          AND timestamp <= %s
        ORDER BY timestamp ASC
    """, (start_time, end_time))
    
    rows = cursor.fetchall()
    print(f"Loaded {len(rows)} snapshots for replay")
    
    results = {}
    
    print("\n" + "="*80)
    print("STRATEGY A: SL 0.4% / TP 0.4% (Full Close)")
    print("="*80)
    results['A: SL 0.4% / TP 0.4%'] = simulate_wider_sl_single(rows, 0.004, 0.004)
    
    print("\n" + "="*80)
    print("STRATEGY B: SL 0.4% / TP1 0.3% / TP2 0.6%")
    print("="*80)
    results['B: SL 0.4% / TP 0.3%/0.6%'] = simulate_wider_sl_double(rows, 0.004, 0.003, 0.006)
    
    print("\n" + "="*80)
    print("STRATEGY C: SL 0.4% / TP1 0.4% / TP2 0.8%")
    print("="*80)
    results['C: SL 0.4% / TP 0.4%/0.8%'] = simulate_wider_sl_double(rows, 0.004, 0.004, 0.008)
    
    print("\n" + "="*80)
    print("STRATEGY D: SL 0.4% / TP 0.3% + Trail 0.15%")
    print("="*80)
    results['D: SL 0.4% / Trail'] = simulate_wider_sl_trailing(rows, 0.004, 0.003, 0.0015)
    
    # Comparison
    print("\n" + "="*80)
    print("WIDER SL COMPARISON (All with 0.4% Stop Loss)")
    print("="*80)
    print(f"{'Strategy':<30} {'Signals':<10} {'Closed':<10} {'WR':<8} {'Net PnL':<12} {'Avg':<10}")
    print("-"*80)
    
    for name, stats in results.items():
        print(f"{name:<30} {stats['signals']:<10} {stats['closed']:<10} "
              f"{stats['win_rate']:.1f}%{'':<4} {stats['net_pnl']:+.2f}%{'':<7} {stats['avg_trade']:+.3f}%")
    
    print("="*80)
    
    # Find best
    best = max(results.items(), key=lambda x: x[1]['net_pnl'])
    print(f"\n🏆 BEST PERFORMER: {best[0]}")
    print(f"   Net PnL: {best[1]['net_pnl']:+.2f}%")
    print(f"   Win Rate: {best[1]['win_rate']:.1f}%")
    
    conn.close()

def simulate_wider_sl_single(rows, sl_pct, tp_pct):
    """Single TP with wider SL."""
    detector = EarlyReversalDetector(snr_threshold=0.15)
    
    active_trades = []
    closed_trades = []
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        mid_price = (float(best_bid) + float(best_ask)) / 2
        total_vol = float(bid_vol) + float(ask_vol)
        imbalance = (float(bid_vol) - float(ask_vol)) / total_vol if total_vol > 0 else 0
        
        ob_data = {
            'symbol': symbol,
            'best_bid': float(best_bid),
            'best_ask': float(best_ask),
            'imbalance': imbalance,
            'bid_volume_10': float(bid_vol),
            'ask_volume_10': float(ask_vol),
            'spread_pct': float(spread),
            'timestamp': timestamp
        }
        
        # Manage trades
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            
            sl_price = entry_price * (1 - sl_pct) if direction == 'LONG' else entry_price * (1 + sl_pct)
            tp_price = entry_price * (1 + tp_pct) if direction == 'LONG' else entry_price * (1 - tp_pct)
            
            closed = False
            
            if direction == 'LONG':
                if mid_price >= tp_price:
                    pnl_pct = tp_pct
                    outcome = "TP_HIT"
                    closed = True
                elif mid_price <= sl_price:
                    pnl_pct = -sl_pct
                    outcome = "SL_HIT"
                    closed = True
            else:
                if mid_price <= tp_price:
                    pnl_pct = tp_pct
                    outcome = "TP_HIT"
                    closed = True
                elif mid_price >= sl_price:
                    pnl_pct = -sl_pct
                    outcome = "SL_HIT"
                    closed = True
            
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = closing_pnl
                outcome = "TIMEOUT"
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        # Detection
        signal = detector.update(ob_data)
        
        if signal:
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = closing_pnl
                    trade['outcome'] = "OPP"
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            }
            active_trades.append(trade)
            signals_found += 1
    
    wins = [t for t in closed_trades if t['pnl_pct'] > 0]
    return {
        'signals': signals_found,
        'closed': len(closed_trades),
        'win_rate': len(wins) / len(closed_trades) * 100 if closed_trades else 0,
        'net_pnl': sum([t['pnl_pct'] for t in closed_trades]) * 100 if closed_trades else 0,
        'avg_trade': sum([t['pnl_pct'] for t in closed_trades]) / len(closed_trades) * 100 if closed_trades else 0
    }

def simulate_wider_sl_double(rows, sl_pct, tp1_pct, tp2_pct):
    """Double TP with wider SL."""
    detector = EarlyReversalDetector(snr_threshold=0.15)
    
    active_trades = []
    closed_trades = []
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        mid_price = (float(best_bid) + float(best_ask)) / 2
        total_vol = float(bid_vol) + float(ask_vol)
        imbalance = (float(bid_vol) - float(ask_vol)) / total_vol if total_vol > 0 else 0
        
        ob_data = {
            'symbol': symbol,
            'best_bid': float(best_bid),
            'best_ask': float(best_ask),
            'imbalance': imbalance,
            'bid_volume_10': float(bid_vol),
            'ask_volume_10': float(ask_vol),
            'spread_pct': float(spread),
            'timestamp': timestamp
        }
        
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            quantity = trade.get('quantity', 1.0)
            
            if trade.get('tp1_hit'):
                sl_price = entry_price
            else:
                sl_price = entry_price * (1 - sl_pct) if direction == 'LONG' else entry_price * (1 + sl_pct)
            
            tp1_price = entry_price * (1 + tp1_pct) if direction == 'LONG' else entry_price * (1 - tp1_pct)
            tp2_price = entry_price * (1 + tp2_pct) if direction == 'LONG' else entry_price * (1 - tp2_pct)
            
            closed = False
            pnl_pct = 0
            
            if direction == 'LONG':
                if mid_price <= sl_price:
                    loss = (sl_price - entry_price) / entry_price
                    pnl_pct = loss * quantity + trade.get('realized_pnl', 0)
                    outcome = "BE_STOP" if trade.get('tp1_hit') else "SL_HIT"
                    closed = True
                elif trade.get('tp1_hit') and mid_price >= tp2_price:
                    pnl_pct = tp2_pct * quantity + trade.get('realized_pnl', 0)
                    outcome = "TP2_HIT"
                    closed = True
                elif not trade.get('tp1_hit') and mid_price >= tp1_price:
                    trade['tp1_hit'] = True
                    pnl_pct = tp1_pct * 0.5
                    trade['quantity'] = 0.5
                    trade['realized_pnl'] = pnl_pct
            else:
                if mid_price >= sl_price:
                    loss = (entry_price - sl_price) / entry_price
                    pnl_pct = loss * quantity + trade.get('realized_pnl', 0)
                    outcome = "BE_STOP" if trade.get('tp1_hit') else "SL_HIT"
                    closed = True
                elif trade.get('tp1_hit') and mid_price <= tp2_price:
                    pnl_pct = tp2_pct * quantity + trade.get('realized_pnl', 0)
                    outcome = "TP2_HIT"
                    closed = True
                elif not trade.get('tp1_hit') and mid_price <= tp1_price:
                    trade['tp1_hit'] = True
                    pnl_pct = tp1_pct * 0.5
                    trade['quantity'] = 0.5
                    trade['realized_pnl'] = pnl_pct
            
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = closing_pnl * quantity + trade.get('realized_pnl', 0)
                outcome = "TIMEOUT"
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        signal = detector.update(ob_data)
        
        if signal:
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    quantity = trade.get('quantity', 1.0)
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = closing_pnl * quantity + trade.get('realized_pnl', 0)
                    trade['outcome'] = "OPP"
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            }
            active_trades.append(trade)
            signals_found += 1
    
    wins = [t for t in closed_trades if t['pnl_pct'] > 0]
    return {
        'signals': signals_found,
        'closed': len(closed_trades),
        'win_rate': len(wins) / len(closed_trades) * 100 if closed_trades else 0,
        'net_pnl': sum([t['pnl_pct'] for t in closed_trades]) * 100 if closed_trades else 0,
        'avg_trade': sum([t['pnl_pct'] for t in closed_trades]) / len(closed_trades) * 100 if closed_trades else 0
    }

def simulate_wider_sl_trailing(rows, sl_pct, tp_pct, trail_dist):
    """Trailing stop with wider SL."""
    detector = EarlyReversalDetector(snr_threshold=0.15)
    
    active_trades = []
    closed_trades = []
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        mid_price = (float(best_bid) + float(best_ask)) / 2
        total_vol = float(bid_vol) + float(ask_vol)
        imbalance = (float(bid_vol) - float(ask_vol)) / total_vol if total_vol > 0 else 0
        
        ob_data = {
            'symbol': symbol,
            'best_bid': float(best_bid),
            'best_ask': float(best_ask),
            'imbalance': imbalance,
            'bid_volume_10': float(bid_vol),
            'ask_volume_10': float(ask_vol),
            'spread_pct': float(spread),
            'timestamp': timestamp
        }
        
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            
            if 'high_water' not in trade:
                trade['high_water'] = mid_price
                trade['low_water'] = mid_price
            
            if mid_price > trade['high_water']:
                trade['high_water'] = mid_price
            if mid_price < trade['low_water']:
                trade['low_water'] = mid_price
            
            closed = False
            pnl_pct = 0
            
            if direction == 'LONG':
                tp_price = entry_price * (1 + tp_pct)
                
                if not trade.get('trailing_active'):
                    sl_price = entry_price * (1 - sl_pct)
                    
                    if mid_price >= tp_price:
                        trade['trailing_active'] = True
                        trade['trailing_stop'] = entry_price
                    elif mid_price <= sl_price:
                        pnl_pct = -sl_pct
                        outcome = "SL_HIT"
                        closed = True
                else:
                    new_trail = trade['high_water'] * (1 - trail_dist)
                    if new_trail > trade['trailing_stop']:
                        trade['trailing_stop'] = new_trail
                    
                    if mid_price <= trade['trailing_stop']:
                        pnl_pct = (trade['trailing_stop'] - entry_price) / entry_price
                        outcome = "TRAIL"
                        closed = True
            else:
                tp_price = entry_price * (1 - tp_pct)
                
                if not trade.get('trailing_active'):
                    sl_price = entry_price * (1 + sl_pct)
                    
                    if mid_price <= tp_price:
                        trade['trailing_active'] = True
                        trade['trailing_stop'] = entry_price
                    elif mid_price >= sl_price:
                        pnl_pct = -sl_pct
                        outcome = "SL_HIT"
                        closed = True
                else:
                    new_trail = trade['low_water'] * (1 + trail_dist)
                    if new_trail < trade['trailing_stop']:
                        trade['trailing_stop'] = new_trail
                    
                    if mid_price >= trade['trailing_stop']:
                        pnl_pct = (entry_price - trade['trailing_stop']) / entry_price
                        outcome = "TRAIL"
                        closed = True
            
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = closing_pnl
                outcome = "TIMEOUT"
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        signal = detector.update(ob_data)
        
        if signal:
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = closing_pnl
                    trade['outcome'] = "OPP"
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            }
            active_trades.append(trade)
            signals_found += 1
    
    wins = [t for t in closed_trades if t['pnl_pct'] > 0]
    return {
        'signals': signals_found,
        'closed': len(closed_trades),
        'win_rate': len(wins) / len(closed_trades) * 100 if closed_trades else 0,
        'net_pnl': sum([t['pnl_pct'] for t in closed_trades]) * 100 if closed_trades else 0,
        'avg_trade': sum([t['pnl_pct'] for t in closed_trades]) / len(closed_trades) * 100 if closed_trades else 0
    }

if __name__ == "__main__":
    run_wider_sl_comparison()
