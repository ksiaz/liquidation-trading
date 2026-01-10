"""
Test multiple threshold configurations specifically for SOLUSDT.
Find optimal settings to restore 59% win rate performance.
"""

import psycopg2
from datetime import datetime, timedelta
from liquidity_drain_detector import LiquidityDrainDetector
import os
from dotenv import load_dotenv

load_dotenv()

def test_sol_configuration(depth_threshold, slope_pct, min_confidence, cooldown):
    """Test specific configuration on SOL."""
    
    # Create custom profile
    custom_profile = {
        'depth_threshold': depth_threshold,
        'slope_threshold': -200,  # Not used anymore but required
        'fake_pump_ticks': 3.0,
        'capitulation_ticks': 2.0,
        'min_confidence': min_confidence,
        'cooldown': cooldown,
        'slope_pct': slope_pct  # Custom field for percentage threshold
    }
    
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
    cursor.close()
    conn.close()
    
    # Manually apply custom slope threshold
    detector = LiquidityDrainDetector(profile='RELAXED')
    detector.config = custom_profile
    
    signals = []
    active_trades = []
    closed_trades = []
    
    for row in rows:
        sym, best_bid, best_ask, bid_vol, ask_vol, spread, timestamp = row
        mid_price = (float(best_bid) + float(best_ask)) / 2
        
        ob_data = {
            'symbol': sym,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'bid_volume_10': bid_vol,
            'ask_volume_10': ask_vol,
            'spread_pct': spread,
            'timestamp': timestamp
        }
        
        # Manage trades
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
            else:
                if mid_price <= entry_price * 0.9975:
                    pnl_pct = 0.0025
                    closed = True
                elif mid_price >= entry_price * 1.0025:
                    pnl_pct = -0.0025
                    closed = True
            
            if not closed and (timestamp - trade['entry_time']).total_seconds() > 3600:
                pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                pnl_pct = pnl
                closed = True
            
            if closed:
                trade['pnl_pct'] = pnl_pct
                closed_trades.append(trade)
                active_trades.remove(trade)
        
        # Detect
        signal = detector.update(ob_data)
        
        if signal:
            for trade in list(active_trades):
                if trade['direction'] != signal['direction']:
                    direction = trade['direction']
                    entry_price = trade['entry_price']
                    pnl = (mid_price - entry_price)/entry_price if direction == 'LONG' else (entry_price - mid_price)/entry_price
                    trade['pnl_pct'] = pnl
                    closed_trades.append(trade)
                    active_trades.remove(trade)
            
            active_trades.append({
                'entry_time': timestamp,
                'entry_price': signal['entry_price'],
                'direction': signal['direction']
            })
            signals.append(signal)
    
    # Stats
    if closed_trades:
        wins = [t for t in closed_trades if t['pnl_pct'] > 0]
        win_rate = len(wins) / len(closed_trades) * 100
        net_pnl = sum([t['pnl_pct'] for t in closed_trades]) * 100
        avg_trade = net_pnl / len(closed_trades)
    else:
        win_rate = 0
        net_pnl = 0
        avg_trade = 0
    
    return {
        'signals': len(signals),
        'trades': len(closed_trades),
        'win_rate': win_rate,
        'net_pnl': net_pnl,
        'avg_trade': avg_trade,
        'signals_per_hour': len(signals) / 8
    }

if __name__ == "__main__":
    print("="*80)
    print("SOL-SPECIFIC THRESHOLD OPTIMIZATION")
    print("="*80)
    
    # Test grid for SOL
    configs = [
        # (depth_threshold, slope_pct, min_confidence, cooldown)
        (0.96, -0.02, 60, 30),   # Current universal (baseline)
        (0.96, -0.03, 60, 30),   # Stricter slope
        (0.96, -0.05, 60, 30),   # Much stricter slope
        (0.94, -0.05, 70, 60),   # Stricter all around
        (0.92, -0.05, 80, 120),  # Very strict
        (0.96, -0.02, 70, 60),   # Higher confidence filter
        (0.96, -0.02, 80, 120),  # Much higher confidence
    ]
    
    results = []
    
    for idx, (depth, slope, conf, cool) in enumerate(configs, 1):
        print(f"\nConfig {idx}: depth={depth:.2f}, slope={slope:.2%}, conf={conf}, cool={cool}s")
        result = test_sol_configuration(depth, slope, conf, cool)
        result['config'] = f"D{depth:.2f}_S{abs(slope):.0%}_C{conf}_T{cool}"
        results.append(result)
        
        print(f"  Signals: {result['signals']} ({result['signals_per_hour']:.1f}/hr)")
        print(f"  Win Rate: {result['win_rate']:.1f}%")
        print(f"  Net PnL: {result['net_pnl']:+.2f}%")
    
    # Summary
    print("\n" + "="*80)
    print("SOL OPTIMIZATION RESULTS")
    print("="*80)
    print(f"{'Config':<20} {'Signals':<10} {'Sig/Hr':<10} {'WR%':<10} {'Net PnL':<12} {'Avg':<10}")
    print("-"*80)
    
    for r in results:
        print(f"{r['config']:<20} {r['signals']:<10} {r['signals_per_hour']:<10.1f} "
              f"{r['win_rate']:<10.1f} {r['net_pnl']:+<12.2f} {r['avg_trade']:+<10.3f}")
    
    print("="*80)
    
    # Find best
    best_wr = max(results, key=lambda x: x['win_rate'])
    best_pnl = max(results, key=lambda x: x['net_pnl'])
    
    print(f"\n🏆 Best Win Rate: {best_wr['config']} ({best_wr['win_rate']:.1f}%)")
    print(f"💰 Best Net PnL: {best_pnl['config']} ({best_pnl['net_pnl']:+.2f}%)")
