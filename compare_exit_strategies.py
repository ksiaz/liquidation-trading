"""
Exit Strategy Comparison - SOLUSDT 8h Replay
Tests 3 different exit strategies on the same signal set.
"""

import psycopg2
from datetime import datetime, timedelta
from early_reversal_detector import EarlyReversalDetector
import os
from dotenv import load_dotenv

load_dotenv()

def run_strategy_comparison():
    """
    Run 3 exit strategies on same data and compare results.
    """
    
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'liquidation_trading'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    
    cursor = conn.cursor()
    
    # Get last 8 hours of data
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
    
    # Run each strategy
    results = {}
    
    print("\n" + "="*80)
    print("STRATEGY 1: Single TP 0.25% (Full Close)")
    print("="*80)
    results['Strategy 1'] = simulate_single_tp(rows)
    
    print("\n" + "="*80)
    print("STRATEGY 2: Double TP (0.25% + 0.5%)")
    print("="*80)
    results['Strategy 2'] = simulate_double_tp(rows)
    
    print("\n" + "="*80)
    print("STRATEGY 3: TP 0.2% + Trailing 0.1%")
    print("="*80)
    results['Strategy 3'] = simulate_trailing_stop(rows)
    
    # Print comparison table
    print("\n" + "="*80)
    print("STRATEGY COMPARISON")
    print("="*80)
    print(f"{'Strategy':<25} {'Signals':<10} {'Closed':<10} {'Win Rate':<12} {'Net PnL':<12} {'Avg Trade':<12}")
    print("-"*80)
    
    for name, stats in results.items():
        print(f"{name:<25} {stats['signals']:<10} {stats['closed']:<10} "
              f"{stats['win_rate']:.1f}%{'':<7} {stats['net_pnl']:+.2f}%{'':<7} {stats['avg_trade']:+.3f}%")
    
    print("="*80)
    
    conn.close()

def simulate_single_tp(rows):
    """Strategy 1: Single TP at 0.25%, Full position close."""
    detector = EarlyReversalDetector(snr_threshold=0.15)
    
    active_trades = []
    closed_trades = []
    SL_PCT = 0.0025
    TP_PCT = 0.0025
    
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        best_bid = float(best_bid)
        best_ask = float(best_ask)
        mid_price = (best_bid + best_ask) / 2
        
        bid_vol = float(bid_vol)
        ask_vol = float(ask_vol)
        total_vol = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0
        
        ob_data = {
            'symbol': symbol,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'imbalance': imbalance,
            'bid_volume_10': bid_vol,
            'ask_volume_10': ask_vol,
            'spread_pct': float(spread),
            'timestamp': timestamp
        }
        
        # Manage active trades
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            
            sl_price = entry_price * (1 - SL_PCT) if direction == 'LONG' else entry_price * (1 + SL_PCT)
            tp_price = entry_price * (1 + TP_PCT) if direction == 'LONG' else entry_price * (1 - TP_PCT)
            
            closed = False
            
            if direction == 'LONG':
                if mid_price >= tp_price:
                    pnl_pct = TP_PCT
                    outcome = "TP_HIT"
                    closed = True
                elif mid_price <= sl_price:
                    pnl_pct = -SL_PCT
                    outcome = "SL_HIT"
                    closed = True
            else:  # SHORT
                if mid_price <= tp_price:
                    pnl_pct = TP_PCT
                    outcome = "TP_HIT"
                    closed = True
                elif mid_price >= sl_price:
                    pnl_pct = -SL_PCT
                    outcome = "SL_HIT"
                    closed = True
            
            # Timeout after 2 hours
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = closing_pnl
                outcome = "TIMEOUT"
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                trade['exit_time'] = timestamp
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        # Detection
        signal = detector.update(ob_data)
        
        if signal:
            # Close opposite trades
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = closing_pnl
                    trade['outcome'] = "OPP_SIGNAL"
                    trade['exit_time'] = timestamp
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            # Open new
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            }
            active_trades.append(trade)
            signals_found += 1
    
    # Stats
    wins = [t for t in closed_trades if t['pnl_pct'] > 0]
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    total_pnl = sum([t['pnl_pct'] for t in closed_trades]) * 100 if closed_trades else 0
    avg_pnl = total_pnl / len(closed_trades) if closed_trades else 0
    
    return {
        'signals': signals_found,
        'closed': len(closed_trades),
        'win_rate': win_rate,
        'net_pnl': total_pnl,
        'avg_trade': avg_pnl
    }

def simulate_double_tp(rows):
    """Strategy 2: TP1 at 0.25% (50%), TP2 at 0.5% (50%)."""
    detector = EarlyReversalDetector(snr_threshold=0.15)
    
    active_trades = []
    closed_trades = []
    SL_PCT = 0.0025
    TP1_PCT = 0.0025
    TP2_PCT = 0.005
    
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        best_bid = float(best_bid)
        best_ask = float(best_ask)
        mid_price = (best_bid + best_ask) / 2
        
        bid_vol = float(bid_vol)
        ask_vol = float(ask_vol)
        total_vol = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0
        
        ob_data = {
            'symbol': symbol,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'imbalance': imbalance,
            'bid_volume_10': bid_vol,
            'ask_volume_10': ask_vol,
            'spread_pct': float(spread),
            'timestamp': timestamp
        }
        
        # Manage active trades
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            quantity = trade.get('quantity', 1.0)
            
            # SL/TP levels
            if trade.get('tp1_hit'):
                sl_price = entry_price  # Breakeven
            else:
                sl_price = entry_price * (1 - SL_PCT) if direction == 'LONG' else entry_price * (1 + SL_PCT)
            
            tp1_price = entry_price * (1 + TP1_PCT) if direction == 'LONG' else entry_price * (1 - TP1_PCT)
            tp2_price = entry_price * (1 + TP2_PCT) if direction == 'LONG' else entry_price * (1 - TP2_PCT)
            
            closed = False
            pnl_pct = 0
            
            if direction == 'LONG':
                # Check SL
                if mid_price <= sl_price:
                    loss = (sl_price - entry_price) / entry_price
                    pnl_pct = loss * quantity
                    outcome = "BE_STOP" if trade.get('tp1_hit') else "SL_HIT"
                    closed = True
                # Check TP2
                elif trade.get('tp1_hit') and mid_price >= tp2_price:
                    profit = TP2_PCT
                    pnl_pct = profit * quantity + trade.get('realized_pnl', 0)
                    outcome = "TP2_HIT"
                    closed = True
                # Check TP1
                elif not trade.get('tp1_hit') and mid_price >= tp1_price:
                    trade['tp1_hit'] = True
                    profit = TP1_PCT
                    pnl_pct = profit * 0.5
                    trade['quantity'] = 0.5
                    trade['realized_pnl'] = pnl_pct
                    # Continue (not closed)
            else:  # SHORT
                # Check SL
                if mid_price >= sl_price:
                    loss = (entry_price - sl_price) / entry_price
                    pnl_pct = loss * quantity
                    outcome = "BE_STOP" if trade.get('tp1_hit') else "SL_HIT"
                    closed = True
                # Check TP2
                elif trade.get('tp1_hit') and mid_price <= tp2_price:
                    profit = TP2_PCT
                    pnl_pct = profit * quantity + trade.get('realized_pnl', 0)
                    outcome = "TP2_HIT"
                    closed = True
                # Check TP1
                elif not trade.get('tp1_hit') and mid_price <= tp1_price:
                    trade['tp1_hit'] = True
                    profit = TP1_PCT
                    pnl_pct = profit * 0.5
                    trade['quantity'] = 0.5
                    trade['realized_pnl'] = pnl_pct
                    # Continue
            
            # Timeout
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = closing_pnl * quantity + trade.get('realized_pnl', 0)
                outcome = "TIMEOUT"
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                trade['exit_time'] = timestamp
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        # Detection
        signal = detector.update(ob_data)
        
        if signal:
            # Close opposite
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    quantity = trade.get('quantity', 1.0)
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = closing_pnl * quantity + trade.get('realized_pnl', 0)
                    trade['outcome'] = "OPP_SIGNAL"
                    trade['exit_time'] = timestamp
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            # Open new
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            }
            active_trades.append(trade)
            signals_found += 1
    
    # Stats
    wins = [t for t in closed_trades if t['pnl_pct'] > 0]
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    total_pnl = sum([t['pnl_pct'] for t in closed_trades]) * 100 if closed_trades else 0
    avg_pnl = total_pnl / len(closed_trades) if closed_trades else 0
    
    return {
        'signals': signals_found,
        'closed': len(closed_trades),
        'win_rate': win_rate,
        'net_pnl': total_pnl,
        'avg_trade': avg_pnl
    }

def simulate_trailing_stop(rows):
    """Strategy 3: TP at 0.2%, then trailing stop 0.1% from BE."""
    detector = EarlyReversalDetector(snr_threshold=0.15)
    
    active_trades = []
    closed_trades = []
    SL_PCT = 0.0025
    TP_PCT = 0.002  # 0.2%
    TRAIL_DIST = 0.001  # 0.1%
    
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        best_bid = float(best_bid)
        best_ask = float(best_ask)
        mid_price = (best_bid + best_ask) / 2
        
        bid_vol = float(bid_vol)
        ask_vol = float(ask_vol)
        total_vol = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0
        
        ob_data = {
            'symbol': symbol,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'imbalance': imbalance,
            'bid_volume_10': bid_vol,
            'ask_volume_10': ask_vol,
            'spread_pct': float(spread),
            'timestamp': timestamp
        }
        
        # Manage active trades
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            
            # Initialize high/low water marks
            if 'high_water' not in trade:
                trade['high_water'] = mid_price
                trade['low_water'] = mid_price
            
            # Update water marks
            if mid_price > trade['high_water']:
                trade['high_water'] = mid_price
            if mid_price < trade['low_water']:
                trade['low_water'] = mid_price
            
            closed = False
            pnl_pct = 0
            
            if direction == 'LONG':
                # Check if TP hit (activate trailing)
                tp_price = entry_price * (1 + TP_PCT)
                
                if not trade.get('trailing_active'):
                    # Not trailing yet
                    sl_price = entry_price * (1 - SL_PCT)
                    
                    if mid_price >= tp_price:
                        # Activate trailing
                        trade['trailing_active'] = True
                        trade['trailing_stop'] = entry_price  # Start at BE
                    elif mid_price <= sl_price:
                        pnl_pct = -SL_PCT
                        outcome = "SL_HIT"
                        closed = True
                else:
                    # Trailing active
                    # Update trailing stop (rises with price, 0.1% below high water)
                    new_trail = trade['high_water'] * (1 - TRAIL_DIST)
                    if new_trail > trade['trailing_stop']:
                        trade['trailing_stop'] = new_trail
                    
                    # Check if trailing stop hit
                    if mid_price <= trade['trailing_stop']:
                        pnl_pct = (trade['trailing_stop'] - entry_price) / entry_price
                        outcome = "TRAIL_STOP"
                        closed = True
            
            else:  # SHORT
                tp_price = entry_price * (1 - TP_PCT)
                
                if not trade.get('trailing_active'):
                    sl_price = entry_price * (1 + SL_PCT)
                    
                    if mid_price <= tp_price:
                        trade['trailing_active'] = True
                        trade['trailing_stop'] = entry_price
                    elif mid_price >= sl_price:
                        pnl_pct = -SL_PCT
                        outcome = "SL_HIT"
                        closed = True
                else:
                    # Update trailing (falls with price, 0.1% above low water)
                    new_trail = trade['low_water'] * (1 + TRAIL_DIST)
                    if new_trail < trade['trailing_stop']:
                        trade['trailing_stop'] = new_trail
                    
                    if mid_price >= trade['trailing_stop']:
                        pnl_pct = (entry_price - trade['trailing_stop']) / entry_price
                        outcome = "TRAIL_STOP"
                        closed = True
            
            # Timeout
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = closing_pnl
                outcome = "TIMEOUT"
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                trade['exit_time'] = timestamp
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        # Detection
        signal = detector.update(ob_data)
        
        if signal:
            # Close opposite
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = closing_pnl
                    trade['outcome'] = "OPP_SIGNAL"
                    trade['exit_time'] = timestamp
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            # Open new
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            }
            active_trades.append(trade)
            signals_found += 1
    
    # Stats
    wins = [t for t in closed_trades if t['pnl_pct'] > 0]
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    total_pnl = sum([t['pnl_pct'] for t in closed_trades]) * 100 if closed_trades else 0
    avg_pnl = total_pnl / len(closed_trades) if closed_trades else 0
    
    return {
        'signals': signals_found,
        'closed': len(closed_trades),
        'win_rate': win_rate,
        'net_pnl': total_pnl,
        'avg_trade': avg_pnl
    }

if __name__ == "__main__":
    run_strategy_comparison()
