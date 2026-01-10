"""
Replay historical orderbook data through EarlyReversalDetector to diagnose missed signals.
Focus: SOLUSDT around 10:07 - 10:17
"""

import psycopg2
import logging
import sys
from datetime import datetime, timedelta
import pandas as pd
from collections import deque

# Import detector
sys.path.append('d:/liquidation-trading')
from early_reversal_detector import EarlyReversalDetector

# Configure logging to show debug info to console
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("early_reversal_detector")
logger.setLevel(logging.DEBUG)  # Set to DEBUG to see rejection reasons

def run_replay():
    print("=" * 80)
    print("DETECTOR REPLAY SIMULATION - SOLUSDT")
    print("=" * 80)

    conn = psycopg2.connect(
        dbname="liquidation_trading",
        user="postgres",
        password="postgres",
        host="localhost"
    )
    
    # Fetch data for SOLUSDT for last 8 hours
    start_time = "NOW() - INTERVAL '8 hours'" 
    
    cur = conn.cursor()
    cur.execute(f"""
        SELECT 
            symbol,
            best_bid,
            best_ask,
            bid_volume_10,
            ask_volume_10,
            spread_pct,
            timestamp
        FROM orderbook_snapshots
        WHERE symbol = 'SOLUSDT'
          AND timestamp > {start_time}
        ORDER BY timestamp ASC
    """)
    
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} snapshots for replay")
    
    if len(rows) == 0:
        print("No data found!")
        return

    # Initialize Detector
    # Using defaults: snr_threshold=0.15
    detector = EarlyReversalDetector(snr_threshold=0.15)
    # Cooldown enabled by default (60s), good for 8h run
    
    # Trade Simulation State
    active_trades = []
    closed_trades = []
    
    # TP/SL Parameters (from SignalGenerator)
    TP_PCT = 0.005   # 0.5%
    SL_PCT = 0.0025  # 0.25%
    
    detector.signal_cooldown = 60 # Restore cooldown for realistic simulation
    
    print("\nStarting Replay with Trade Simulation...")
    print("-" * 80)
    print(f"{'Time':<10} {'Signal':<6} {'Price':<10} {'Outcome':<10} {'PnL %':<8}")
    print("-" * 80)
    
    signals_found = 0
    
    for row in rows:
        symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        
        # Calculate derived metrics
        best_bid = float(best_bid)
        best_ask = float(best_ask)
        bid_vol = float(bid_vol)
        ask_vol = float(ask_vol)
        spread = float(spread)
        
        mid_price = (best_bid + best_ask) / 2
        total_vol = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0
        
        # Prepare data dict
        ob_data = {
            'symbol': symbol,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'imbalance': imbalance,
            'bid_volume_10': bid_vol,
            'ask_volume_10': ask_vol,
            'spread_pct': spread,
            'timestamp': timestamp
        }

        time_str = timestamp.strftime('%H:%M:%S')

        # 1. Manage Active Trades
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            quantity = trade.get('quantity', 1.0) # Start with full unit
            
            # SL/TP Levels
            # If TP1 hit, SL is Breakeven. Else, SL is fixed distance.
            if trade.get('tp1_hit'):
                current_sl_pct = 0.0 # Breakeven
                sl_price = entry_price # BE
            else:
                current_sl_pct = SL_PCT
                sl_price = entry_price * (1 - SL_PCT) if direction == 'LONG' else entry_price * (1 + SL_PCT)
            
            tp1_price = entry_price * (1 + 0.0025) if direction == 'LONG' else entry_price * (1 - 0.0025)
            
            pnl_pct = 0
            closed = False
            outcome = ""
            
            # 1. Check Opposite Signal (TP2 condition) - BEFORE price checks
            # Note: We need to know if CURRENT row generates an opposite signal. 
            # But detection happens below. We can check AFTER detection or check 'detector' state? 
            # Simpler: Check price limits first, then check opposite signal in the Detection block below.
            
            # 2. Check Price limits
            if direction == 'LONG':
                # Check SL first (Max drawdown logic)
                if mid_price <= sl_price:
                    # STOP HIT
                    loss = (sl_price - entry_price) / entry_price
                    # If TP1 was hit, remaining position is stopped at BE (0 loss)
                    # If TP1 not hit, full position stopped at SL
                    pnl_pct += loss * quantity
                    outcome = "BE_STOP" if trade.get('tp1_hit') else "SL_HIT"
                    closed = True
                
                # Check TP1 (if not yet hit)
                elif not trade.get('tp1_hit') and mid_price >= tp1_price:
                    # TP1 HIT
                    trade['tp1_hit'] = True
                    # Take 50% profit
                    profit = 0.0025
                    pnl_pct += profit * 0.5
                    quantity = 0.5
                    trade['quantity'] = 0.5
                    trade['realized_pnl'] = trade.get('realized_pnl', 0) + profit * 0.5
                    outcome = "TP1_HIT" # Trade stays open
                    print(f"{time_str:<10} {direction:<6} ${entry_price:<9.2f} {outcome:<10} +0.25% (Partial)")

            else: # SHORT
                # Check SL
                if mid_price >= sl_price:
                    loss = (entry_price - sl_price) / entry_price
                    pnl_pct += loss * quantity
                    outcome = "BE_STOP" if trade.get('tp1_hit') else "SL_HIT"
                    closed = True
                
                # Check TP1
                elif not trade.get('tp1_hit') and mid_price <= tp1_price:
                    trade['tp1_hit'] = True
                    # Take 50% profit
                    profit = 0.0025
                    pnl_pct += profit * 0.5
                    quantity = 0.5
                    trade['quantity'] = 0.5
                    trade['realized_pnl'] = trade.get('realized_pnl', 0) + profit * 0.5
                    outcome = "TP1_HIT"
                    print(f"{time_str:<10} {direction:<6} ${entry_price:<9.2f} {outcome:<10} +0.25% (Partial)")
            
            # Timeout check (4 hours)
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 14400:
                # Close remaining at market
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct += closing_pnl * quantity
                outcome = "TIMEOUT"
                closed = True

            if closed:
                # Add realized PnL from TP1 if any
                pnl_pct += trade.get('realized_pnl', 0)
                
                trade['exit_price'] = mid_price
                trade['exit_time'] = timestamp
                trade['pnl_pct'] = pnl_pct
                trade['outcome'] = outcome
                closed_trades.append(trade)
                active_trades.remove(trade)
                
                print(f"{time_str:<10} {direction:<6} ${entry_price:<9.2f} {outcome:<10} {pnl_pct*100:+.2f}%")

        # 2. Run Detection
        signal = detector.update(ob_data)
        
        if signal:
            # Check for Opposite Signals to Close Active Trades (TP2)
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    # OPPOSITE SIGNAL -> CLOSE TRADE
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    quantity = trade.get('quantity', 1.0)
                    
                    closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    
                    trade['pnl_pct'] = closing_pnl * quantity + trade.get('realized_pnl', 0)
                    trade['outcome'] = "TP2_OPP"
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = mid_price
                    
                    closed_trades.append(trade)
                    active_trades.remove(trade)
                    print(f"{time_str:<10} {direction:<6} ${entry_price:<9.2f} TP2_OPP    {trade['pnl_pct']*100:+.2f}%")

            # Open new trade
            trade = {
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction'],
                'confidence': signal['confidence'],
                'snr': signal['snr']
            }
            active_trades.append(trade)
            signals_found += 1
            
    print("-" * 80)
    print(f"Total Signals: {signals_found}")
    
    # Statistics
    if closed_trades:
        wins = [t for t in closed_trades if t['pnl_pct'] > 0]
        losses = [t for t in closed_trades if t['pnl_pct'] <= 0]
        
        win_rate = len(wins) / len(closed_trades) * 100
        total_pnl = sum([t['pnl_pct'] for t in closed_trades]) * 100
        avg_pnl = total_pnl / len(closed_trades)
        
        print(f"\n📈 PERFORMANCE STATISTICS (8 Hours)")
        print(f"Win Rate:      {win_rate:.1f}% ({len(wins)}/{len(closed_trades)})")
        print(f"Total Return:  {total_pnl:+.2f}%")
        print(f"Avg Trade:     {avg_pnl:+.2f}%")
        print(f"Parameters:    TP={TP_PCT*100}% | SL={SL_PCT*100}%")
    else:
        print("No closed trades to analyze.")
        
    conn.close()

if __name__ == "__main__":
    run_replay()
