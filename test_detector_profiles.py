"""
Test LiquidityDrainDetector across all threshold profiles.
Shows win rate and signal frequency for each configuration.
"""

import psycopg2
from datetime import datetime, timedelta
from liquidity_drain_detector import LiquidityDrainDetector
import os
from dotenv import load_dotenv

load_dotenv()

def test_all_profiles():
    """Test all detector profiles and compare performance."""
    
    # Connect to DB
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'liquidation_trading'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    
    # Fetch 8h data
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
    cursor.close()
    conn.close()
    
    print(f"Loaded {len(rows)} snapshots for testing\n")
    print("="*80)
    
    results = {}
    
    # Test each profile
    for profile in ['RELAXED', 'MODERATE', 'STRICT', 'EXTREME']:
        print(f"\nTesting profile: {profile}")
        print("-"*80)
        
        detector = LiquidityDrainDetector(profile=profile)
        
        signals = []
        active_trades = []
        closed_trades = []
        
        # Simulate
        for row in rows:
            symbol, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
            
            mid_price = (float(best_bid) + float(best_ask)) / 2
            
            ob_data = {
                'symbol': symbol,
                'best_bid': best_bid,
                'best_ask': best_ask,
                'bid_volume_10': bid_vol,
                'ask_volume_10': ask_vol,
                'spread_pct': spread,
                'timestamp': timestamp
            }
            
            # Manage trades (simple 0.25% TP/SL)
            for trade in list(active_trades):
                entry_price = trade['entry_price']
                direction = trade['direction']
                
                closed = False
                pnl_pct = 0
                
                if direction == 'LONG':
                    if mid_price >= entry_price * 1.0025:
                        pnl_pct = 0.0025
                        closed = True
                    elif mid_price <= entry_price * 0.9975:
                        pnl_pct = -0.0025
                        closed = True
                else:  # SHORT
                    if mid_price <= entry_price * 0.9975:
                        pnl_pct = 0.0025
                        closed = True
                    elif mid_price >= entry_price * 1.0025:
                        pnl_pct = -0.0025
                        closed = True
                
                # Timeout
                if not closed and (timestamp - trade['entry_time']).total_seconds() > 3600:
                    if direction == 'LONG':
                        pnl_pct = (mid_price - entry_price) / entry_price
                    else:
                        pnl_pct = (entry_price - mid_price) / entry_price
                    closed = True
                
                if closed:
                    trade['exit_time'] = timestamp
                    trade['pnl_pct'] = pnl_pct
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            # Detect
            signal = detector.update(ob_data)
            
            if signal:
                # Close opposite trades
                for trade in list(active_trades):
                    if trade['direction'] != signal['direction']:
                        direction = trade['direction']
                        entry_price = trade['entry_price']
                        pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                        trade['pnl_pct'] = pnl
                        closed_trades.append(trade)
                        active_trades.remove(trade)
                
                # Open new
                active_trades.append({
                    'entry_time': timestamp,
                    'entry_price': signal['entry_price'],
                    'direction': signal['direction']
                })
                signals.append(signal)
        
        # Calculate stats
        if closed_trades:
            wins = [t for t in closed_trades if t['pnl_pct'] > 0]
            win_rate = len(wins) / len(closed_trades) * 100
            net_pnl = sum([t['pnl_pct'] for t in closed_trades]) * 100
            avg_trade = net_pnl / len(closed_trades)
        else:
            win_rate = 0
            net_pnl = 0
            avg_trade = 0
        
        results[profile] = {
            'signals': len(signals),
            'trades': len(closed_trades),
            'win_rate': win_rate,
            'net_pnl': net_pnl,
            'avg_trade': avg_trade,
            'signals_per_hour': len(signals) / 8
        }
        
        print(f"  Signals: {len(signals)} ({len(signals)/8:.1f}/hour)")
        print(f"  Trades closed: {len(closed_trades)}")
        print(f"  Win rate: {win_rate:.1f}%")
        print(f"  Net PnL: {net_pnl:+.2f}%")
        print(f"  Avg trade: {avg_trade:+.3f}%")
    
    # Summary table
    print("\n" + "="*80)
    print("PROFILE COMPARISON")
    print("="*80)
    print(f"{'Profile':<12} {'Signals':<10} {'Sig/Hr':<10} {'WR%':<10} {'Net PnL':<12} {'Avg Trade':<12}")
    print("-"*80)
    
    for profile in ['RELAXED', 'MODERATE', 'STRICT', 'EXTREME']:
        r = results[profile]
        print(f"{profile:<12} {r['signals']:<10} {r['signals_per_hour']:<10.1f} "
              f"{r['win_rate']:<10.1f} {r['net_pnl']:+<12.2f} {r['avg_trade']:+<12.3f}")
    
    print("="*80)
    
    # Find best by different metrics
    best_wr = max(results.items(), key=lambda x: x[1]['win_rate'])
    best_pnl = max(results.items(), key=lambda x: x[1]['net_pnl'])
    
    print(f"\n📊 Best win rate: {best_wr[0]} ({best_wr[1]['win_rate']:.1f}%)")
    print(f"💰 Best net PnL: {best_pnl[0]} ({best_pnl[1]['net_pnl']:+.2f}%)")
    
    return results

if __name__ == "__main__":
    results = test_all_profiles()
