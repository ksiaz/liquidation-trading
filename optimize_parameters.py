"""
Comprehensive Parameter Optimization Suite
Tests multiple detector configurations and exit strategies to find optimal settings.

Grid Search Parameters:
- SNR Threshold: [0.3, 0.5, 0.8, 1.0, 1.5]
- Min Signals: [2, 3, 4]
- Confidence Filter: [0, 60, 75]
- Exit Strategies: 4 best performers
"""

import psycopg2
from datetime import datetime, timedelta
from early_reversal_detector import EarlyReversalDetector
import os
from dotenv import load_dotenv
import pandas as pd
from itertools import product

load_dotenv()

class ParameterOptimizer:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'liquidation_trading'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )
        
        # Load data once
        cursor = self.conn.cursor()
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
        
        self.rows = cursor.fetchall()
        cursor.close()
        print(f"Loaded {len(self.rows)} snapshots for optimization")
        
        # Parameter grids
        self.snr_thresholds = [0.3, 0.5, 0.8, 1.0, 1.5]
        self.min_signals = [2, 3, 4]
        self.confidence_filters = [0, 60, 75]
        
        # Exit strategies (simplified - using best from previous tests)
        self.exit_strategies = [
            {'name': 'Single_0.25', 'sl': 0.0025, 'tp': 0.0025, 'type': 'single'},
            {'name': 'Single_0.4', 'sl': 0.004, 'tp': 0.004, 'type': 'single'},
            {'name': 'Trail_0.3', 'sl': 0.004, 'tp': 0.003, 'trail': 0.0015, 'type': 'trail'},
            {'name': 'Double_0.3/0.6', 'sl': 0.004, 'tp1': 0.003, 'tp2': 0.006, 'type': 'double'},
        ]
        
        self.results = []
    
    def run_optimization(self):
        """Run full parameter sweep."""
        total_configs = len(self.snr_thresholds) * len(self.min_signals) * len(self.confidence_filters) * len(self.exit_strategies)
        print(f"\nTesting {total_configs} configurations...")
        print("="*80)
        
        config_num = 0
        
        for snr, min_sig, conf, exit_strat in product(
            self.snr_thresholds, 
            self.min_signals, 
            self.confidence_filters, 
            self.exit_strategies
        ):
            config_num += 1
            
            # Run simulation
            result = self.simulate_config(snr, min_sig, conf, exit_strat)
            
            # Store results
            self.results.append({
                'config_num': config_num,
                'snr_threshold': snr,
                'min_signals': min_sig,
                'confidence_filter': conf,
                'exit_strategy': exit_strat['name'],
                **result
            })
            
            # Progress update every 10 configs
            if config_num % 10 == 0:
                print(f"Progress: {config_num}/{total_configs} ({config_num/total_configs*100:.0f}%)")
        
        print("="*80)
        print("Optimization complete!\n")
    
    def simulate_config(self, snr_threshold, min_signals, confidence_filter, exit_strategy):
        """Simulate a specific configuration."""
        # Create detector with custom parameters
        detector = EarlyReversalDetector(snr_threshold=snr_threshold)
        detector.min_signals_required = min_signals
        
        active_trades = []
        closed_trades = []
        signals_found = 0
        
        for row in self.rows:
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
            
            # Manage active trades (exit logic)
            active_trades, closed = self._manage_trades(
                active_trades, mid_price, timestamp, exit_strategy
            )
            closed_trades.extend(closed)
            
            # Detection
            signal = detector.update(ob_data)
            
            # Apply confidence filter
            if signal and signal.get('confidence', 100) < confidence_filter:
                signal = None
            
            if signal:
                # Close opposite trades
                for trade in list(active_trades):
                    if trade['direction'] != signal['direction']:
                        direction = trade['direction']
                        entry_price = trade['entry_price']
                        quantity = trade.get('quantity', 1.0)
                        closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                        trade['pnl_pct'] = closing_pnl * quantity + trade.get('realized_pnl', 0)
                        trade['outcome'] = 'OPP'
                        closed_trades.append(trade)
                        active_trades.remove(trade)
                
                # Open new trade
                active_trades.append({
                    'entry_time': timestamp,
                    'entry_price': signal['entry_price'],
                    'direction': signal['direction'],
                    'confidence': signal.get('confidence', 0)
                })
                signals_found += 1
        
        # Calculate statistics
        if len(closed_trades) == 0:
            return {
                'signals': signals_found,
                'trades': 0,
                'win_rate': 0,
                'net_pnl': 0,
                'avg_trade': 0,
                'sharpe': 0,
                'max_dd': 0
            }
        
        wins = [t for t in closed_trades if t['pnl_pct'] > 0]
        pnls = [t['pnl_pct'] for t in closed_trades]
        
        return {
            'signals': signals_found,
            'trades': len(closed_trades),
            'win_rate': len(wins) / len(closed_trades) * 100,
            'net_pnl': sum(pnls) * 100,
            'avg_trade': sum(pnls) / len(pnls) * 100,
            'sharpe': (sum(pnls) / len(pnls)) / (pd.Series(pnls).std()) if len(pnls) > 1 and pd.Series(pnls).std() > 0 else 0,
            'max_dd': self._calculate_max_drawdown(pnls) * 100
        }
    
    def _manage_trades(self, active_trades, mid_price, timestamp, exit_strategy):
        """Manage active trades based on exit strategy."""
        closed_trades = []
        
        for trade in list(active_trades):
            entry_price = trade['entry_price']
            direction = trade['direction']
            
            closed = False
            pnl_pct = 0
            
            if exit_strategy['type'] == 'single':
                # Simple SL/TP
                sl_pct = exit_strategy['sl']
                tp_pct = exit_strategy['tp']
                
                sl_price = entry_price * (1 - sl_pct) if direction == 'LONG' else entry_price * (1 + sl_pct)
                tp_price = entry_price * (1 + tp_pct) if direction == 'LONG' else entry_price * (1 - tp_pct)
                
                if direction == 'LONG':
                    if mid_price >= tp_price:
                        pnl_pct = tp_pct
                        closed = True
                    elif mid_price <= sl_price:
                        pnl_pct = -sl_pct
                        closed = True
                else:
                    if mid_price <= tp_price:
                        pnl_pct = tp_pct
                        closed = True
                    elif mid_price >= sl_price:
                        pnl_pct = -sl_pct
                        closed = True
            
            elif exit_strategy['type'] == 'trail':
                # Trailing stop
                if 'high_water' not in trade:
                    trade['high_water'] = mid_price
                    trade['low_water'] = mid_price
                
                if mid_price > trade['high_water']:
                    trade['high_water'] = mid_price
                if mid_price < trade['low_water']:
                    trade['low_water'] = mid_price
                
                sl_pct = exit_strategy['sl']
                tp_pct = exit_strategy['tp']
                trail_dist = exit_strategy['trail']
                
                if direction == 'LONG':
                    tp_price = entry_price * (1 + tp_pct)
                    
                    if not trade.get('trailing_active'):
                        sl_price = entry_price * (1 - sl_pct)
                        
                        if mid_price >= tp_price:
                            trade['trailing_active'] = True
                            trade['trailing_stop'] = entry_price
                        elif mid_price <= sl_price:
                            pnl_pct = -sl_pct
                            closed = True
                    else:
                        new_trail = trade['high_water'] * (1 - trail_dist)
                        if new_trail > trade.get('trailing_stop', entry_price):
                            trade['trailing_stop'] = new_trail
                        
                        if mid_price <= trade['trailing_stop']:
                            pnl_pct = (trade['trailing_stop'] - entry_price) / entry_price
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
                            closed = True
                    else:
                        new_trail = trade['low_water'] * (1 + trail_dist)
                        if new_trail < trade.get('trailing_stop', entry_price):
                            trade['trailing_stop'] = new_trail
                        
                        if mid_price >= trade['trailing_stop']:
                            pnl_pct = (entry_price - trade['trailing_stop']) / entry_price
                            closed = True
            
            elif exit_strategy['type'] == 'double':
                # Double TP
                sl_pct = exit_strategy['sl']
                tp1_pct = exit_strategy['tp1']
                tp2_pct = exit_strategy['tp2']
                
                quantity = trade.get('quantity', 1.0)
                
                if trade.get('tp1_hit'):
                    sl_price = entry_price
                else:
                    sl_price = entry_price * (1 - sl_pct) if direction == 'LONG' else entry_price * (1 + sl_pct)
                
                tp1_price = entry_price * (1 + tp1_pct) if direction == 'LONG' else entry_price * (1 - tp1_pct)
                tp2_price = entry_price * (1 + tp2_pct) if direction == 'LONG' else entry_price * (1 - tp2_pct)
                
                if direction == 'LONG':
                    if mid_price <= sl_price:
                        pnl_pct = (sl_price - entry_price) / entry_price * quantity + trade.get('realized_pnl', 0)
                        closed = True
                    elif trade.get('tp1_hit') and mid_price >= tp2_price:
                        pnl_pct = tp2_pct * quantity + trade.get('realized_pnl', 0)
                        closed = True
                    elif not trade.get('tp1_hit') and mid_price >= tp1_price:
                        trade['tp1_hit'] = True
                        trade['quantity'] = 0.5
                        trade['realized_pnl'] = tp1_pct * 0.5
                else:
                    if mid_price >= sl_price:
                        pnl_pct = (entry_price - sl_price) / entry_price * quantity + trade.get('realized_pnl', 0)
                        closed = True
                    elif trade.get('tp1_hit') and mid_price <= tp2_price:
                        pnl_pct = tp2_pct * quantity + trade.get('realized_pnl', 0)
                        closed = True
                    elif not trade.get('tp1_hit') and mid_price <= tp1_price:
                        trade['tp1_hit'] = True
                        trade['quantity'] = 0.5
                        trade['realized_pnl'] = tp1_pct * 0.5
            
            # Timeout (2 hours)
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 7200:
                closing_pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                quantity = trade.get('quantity', 1.0)
                pnl_pct = closing_pnl * quantity + trade.get('realized_pnl', 0)
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        return active_trades, closed_trades
    
    def _calculate_max_drawdown(self, pnls):
        """Calculate maximum drawdown from PnL series."""
        cumulative = pd.Series(pnls).cumsum()
        running_max = cumulative.cummax()
        drawdown = cumulative - running_max
        return drawdown.min() if len(drawdown) > 0 else 0
    
    def print_top_results(self, top_n=20):
        """Print top N configurations by net PnL."""
        df = pd.DataFrame(self.results)
        
        # Sort by net_pnl
        df_sorted = df.sort_values('net_pnl', ascending=False)
        
        print("\n" + "="*120)
        print(f"TOP {top_n} CONFIGURATIONS (by Net PnL)")
        print("="*120)
        print(f"{'Rank':<6} {'SNR':<6} {'MinSig':<8} {'ConfFlt':<8} {'Exit':<18} {'Sigs':<6} {'WR%':<8} {'PnL%':<10} {'AvgTrade%':<12} {'Sharpe':<8}")
        print("-"*120)
        
        for idx, row in df_sorted.head(top_n).iterrows():
            print(f"{row['config_num']:<6} {row['snr_threshold']:<6.2f} {row['min_signals']:<8} {row['confidence_filter']:<8} "
                  f"{row['exit_strategy']:<18} {row['signals']:<6} {row['win_rate']:<8.1f} "
                  f"{row['net_pnl']:+<10.2f} {row['avg_trade']:+<12.3f} {row['sharpe']:<8.2f}")
        
        print("="*120)
        
        # Find best by different metrics
        print("\n" + "="*120)
        print("BEST PERFORMERS BY METRIC")
        print("="*120)
        
        best_pnl = df_sorted.iloc[0]
        print(f"Best PnL:      Config #{best_pnl['config_num']} - SNR={best_pnl['snr_threshold']}, MinSig={best_pnl['min_signals']}, "
              f"Conf={best_pnl['confidence_filter']}, Exit={best_pnl['exit_strategy']} → {best_pnl['net_pnl']:+.2f}%")
        
        best_wr = df.loc[df['win_rate'].idxmax()]
        print(f"Best Win Rate: Config #{best_wr['config_num']} - SNR={best_wr['snr_threshold']}, MinSig={best_wr['min_signals']}, "
              f"Conf={best_wr['confidence_filter']}, Exit={best_wr['exit_strategy']} → {best_wr['win_rate']:.1f}%")
        
        best_sharpe = df.loc[df['sharpe'].idxmax()]
        print(f"Best Sharpe:   Config #{best_sharpe['config_num']} - SNR={best_sharpe['snr_threshold']}, MinSig={best_sharpe['min_signals']}, "
              f"Conf={best_sharpe['confidence_filter']}, Exit={best_sharpe['exit_strategy']} → {best_sharpe['sharpe']:.2f}")
        
        print("="*120)
        
        # Save to CSV
        df_sorted.to_csv('optimization_results.csv', index=False)
        print("\n📊 Full results saved to: optimization_results.csv\n")
    
    def close(self):
        self.conn.close()

if __name__ == "__main__":
    optimizer = ParameterOptimizer()
    optimizer.run_optimization()
    optimizer.print_top_results(top_n=20)
    optimizer.close()
