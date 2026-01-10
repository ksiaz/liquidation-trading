"""
CCXT Paper Trading - Mainnet Data, Simulated Execution
Uses real Binance data but simulates all trades locally (no API keys needed)
"""

import ccxt
import time
from datetime import datetime
from pivot_detector import PivotDetector

# ==================== CONFIGURATION ====================
PORTFOLIO_SIZE = 1000.0   # $1,000 simulated capital
MAX_POSITION_PCT = 0.02   # Max 2% per position
STOP_LOSS_PCT = 10.0      # 10% stop loss
TARGET_PCT = 0.5          # 0.5% target (per backtest)
FILL_RATE = 0.45          # 45% fill rate (per framework)
# No session limits - rely on capital constraints (crypto is 24/7)

print("="*80)
print("PAPER TRADING SYSTEM - MAINNET DATA, SIMULATED EXECUTION")
print("="*80)
print(f"Portfolio: ${PORTFOLIO_SIZE:,.2f}")
print(f"Max Position: {MAX_POSITION_PCT*100:.2f}% (${PORTFOLIO_SIZE * MAX_POSITION_PCT:,.2f})")
print(f"Risk: {STOP_LOSS_PCT:.1f}% stop, {TARGET_PCT:.2f}% target")
print("="*80)

# Initialize exchange (NO API KEYS = read-only, no trades possible)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}  # Use spot for accurate data
})
print("[OK] Exchange: Binance MAINNET (read-only, no API keys)")

# Initialize detector
# Initialize pivot detectors (one per symbol)
detectors = {}
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

for symbol in symbols:
    detectors[symbol] = PivotDetector(symbol)
    
print(f"[OK] PivotDetectors initialized for {symbols}")

# Portfolio state
portfolio = {
    'capital': PORTFOLIO_SIZE,
    'available': PORTFOLIO_SIZE,
    'positions': {},  # symbol -> position dict
    'closed_trades': [],
    'total_trades': 0,
    'wins': 0,
    'losses': 0,
    'peak_capital': PORTFOLIO_SIZE,  # For drawdown
    'max_drawdown': 0.0,
}

# Session tracking
current_session = None
session_signals = {'ASIA': 0, 'EUROPE': 0, 'US': 0}

def detect_session():
    """Detect trading session based on UTC time."""
    from datetime import datetime
    hour_utc = datetime.utcnow().hour
    
    if 0 <= hour_utc < 8:  # 00:00-08:00 UTC
        return 'ASIA'
    elif 8 <= hour_utc < 16:  # 08:00-16:00 UTC
        return 'EUROPE'
    else:  # 16:00-00:00 UTC
        return 'US'

def calculate_position_size(signal_confidence):
    """Calculate position size based on confidence."""
    # Base: 0.25% of portfolio per signal
    # Scale by confidence: 80% conf = 0.8x, 90% = 0.9x, etc
    base_pct = 0.0025  # 0.25%
    confidence_mult = signal_confidence / 100.0
    size_pct = base_pct * confidence_mult
    
    # Cap at max position size
    size_pct = min(size_pct, MAX_POSITION_PCT)
    
    return portfolio['capital'] * size_pct

def simulate_entry(symbol, signal, current_price):
    """Simulate position entry with fill rate."""
    import random
    
    # Simulate fill rate (45% chance of fill)
    if random.random() > FILL_RATE:
        return None  # No fill
    # Calculate size
    position_value = calculate_position_size(signal['confidence'])
    amount = position_value / current_price
    
    # Check if enough capital
    if position_value > portfolio['available']:
        return None
    
    # Apply slippage (0.03% as per your system)
    if signal['direction'] == 'LONG':
        fill_price = current_price * 1.0003  # Buy higher
    else:
        fill_price = current_price * 0.9997  # Sell lower
    
    # Deduct from available capital
    portfolio['available'] -= position_value
    
    # Create position
    position = {
        'symbol': symbol,
        'side': signal['direction'],
        'amount': amount,
        'entry_price': fill_price,
        'position_value': position_value,
        'entry_time': datetime.now(),
        'signal': signal,
        'peak_pnl': 0.0,
        'worst_pnl': 0.0,
    }
    
    portfolio['positions'][symbol] = position
    portfolio['total_trades'] += 1
    
    return position

def check_and_update_positions():
    """Check all positions for exits and update P&L."""
    to_close = []
    
    for symbol, pos in portfolio['positions'].items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # Calculate P&L
            if pos['side'] == 'LONG':
                pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
            else:
                pnl_pct = ((pos['entry_price'] - current_price) / pos['entry_price']) * 100
            
            # Update peak/worst
            pos['peak_pnl'] = max(pos['peak_pnl'], pnl_pct)
            pos['worst_pnl'] = min(pos['worst_pnl'], pnl_pct)
            
            # Check exit conditions
            exit_reason = None
            
            if pnl_pct <= -STOP_LOSS_PCT:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= TARGET_PCT:
                exit_reason = "TARGET"
            
            if exit_reason:
                # Simulate exit with slippage
                if pos['side'] == 'LONG':
                    exit_price = current_price * 0.9997  # Sell lower
                else:
                    exit_price = current_price * 1.0003  # Buy higher
                
                # Recalculate final P&L with exit slippage
                if pos['side'] == 'LONG':
                    final_pnl_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                else:
                    final_pnl_pct = ((pos['entry_price'] - exit_price) / pos['entry_price']) * 100
                
                # Apply fees (0.08% total = 0.04% entry + 0.04% exit)
                final_pnl_pct -= 0.08
                
                # Calculate USD P&L
                pnl_usd = (final_pnl_pct / 100.0) * pos['position_value']
                
                # Return capital + P&L
                portfolio['available'] += pos['position_value'] + pnl_usd
                portfolio['capital'] += pnl_usd
                
                # Track result
                if final_pnl_pct > 0:
                    portfolio['wins'] += 1
                    result_emoji = "✅"
                else:
                    portfolio['losses'] += 1
                    result_emoji = "❌"
                
                portfolio['closed_trades'].append({
                    'symbol': symbol,
                    'side': pos['side'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'pnl_pct': final_pnl_pct,
                    'pnl_usd': pnl_usd,
                    'exit_reason': exit_reason,
                    'hold_time': (datetime.now() - pos['entry_time']).total_seconds(),
                    'mfe': pos['peak_pnl'],  # Max Favorable Excursion
                    'mae': pos['worst_pnl'],  # Max Adverse Excursion
                })
                
                # Update max drawdown
                portfolio['peak_capital'] = max(portfolio['peak_capital'], portfolio['capital'])
                drawdown = (portfolio['peak_capital'] - portfolio['capital']) / portfolio['peak_capital']
                portfolio['max_drawdown'] = max(portfolio['max_drawdown'], drawdown)
                
                # Log exit
                print(f"{result_emoji} EXIT: {symbol} {pos['side']} | {exit_reason} | P&L: {final_pnl_pct:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Capital: ${portfolio['capital']:,.2f} | Win Rate: {portfolio['wins']}/{portfolio['total_trades']}")
                
                to_close.append(symbol)
        
        except Exception as e:
            print(f"⚠️ Error checking {symbol}: {e}")
    
    # Close positions
    for symbol in to_close:
        del portfolio['positions'][symbol]

def calculate_sharpe_ratio():
    """Calculate Sharpe ratio from closed trades."""
    if len(portfolio['closed_trades']) < 3:
        return 0.0
    
    returns = [t['pnl_pct'] for t in portfolio['closed_trades']]
    mean_return = sum(returns) / len(returns)
    
    # Calculate standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_dev = variance ** 0.5 if variance > 0 else 0.0001
    
    # Annualize (assuming ~10 trades per day, 252 trading days)
    sharpe = (mean_return / std_dev) * (252 ** 0.5) if std_dev > 0 else 0
    return sharpe

# Symbols already defined during detector initialization
print(f"[OK] Monitoring: {symbols}")
print("="*80)
print()

# Main loop
iteration = 0
last_status_time = time.time()

while True:
    iteration += 1
    current_time = time.time()
    
    # Status update every 60 seconds
    if current_time - last_status_time >= 60:
        total = portfolio['total_trades']
        wr = (portfolio['wins'] / total * 100) if total > 0 else 0
        pnl = portfolio['capital'] - PORTFOLIO_SIZE
        pnl_pct = (pnl / PORTFOLIO_SIZE) * 100
        sharpe = calculate_sharpe_ratio()
        
        # Get current session
        session = detect_session()
        
        print(f"[STATUS] Session: {session} | Capital: ${portfolio['capital']:,.2f} ({pnl_pct:+.2f}%) | "
              f"DD: {portfolio['max_drawdown']*100:.2f}% | "
              f"Positions: {len(portfolio['positions'])} | "
              f"Trades: {total} (WR: {wr:.1f}%) | Sharpe: {sharpe:.2f}")
        
        # Show open position P&L
        if portfolio['positions']:
            print("   Open Positions:")
            for sym, pos in portfolio['positions'].items():
                try:
                    ticker = exchange.fetch_ticker(sym)
                    current_price = ticker['last']
                    
                    # Calculate current P&L
                    if pos['side'] == 'LONG':
                        current_pnl = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                        target_price = pos['entry_price'] * (1 + TARGET_PCT/100)
                        stop_price = pos['entry_price'] * (1 - STOP_LOSS_PCT/100)
                    else:
                        current_pnl = ((pos['entry_price'] - current_price) / pos['entry_price']) * 100
                        target_price = pos['entry_price'] * (1 - TARGET_PCT/100)
                        stop_price = pos['entry_price'] * (1 + STOP_LOSS_PCT/100)
                    
                    # Apply fees for net P&L
                    net_pnl = current_pnl - 0.08
                    
                    emoji = "🟢" if net_pnl > 0 else "🔴"
                    print(f"   {emoji} {sym} {pos['side']}: {net_pnl:+.2f}% | "
                          f"Entry: ${pos['entry_price']:,.2f} | Current: ${current_price:,.2f} | "
                          f"Target: ${target_price:,.2f} ({TARGET_PCT}%) | Stop: ${stop_price:,.2f} ({STOP_LOSS_PCT}%)")
                except:
                    pass
        
        last_status_time = current_time
    
    # Check position exits
    check_and_update_positions()
    
    # Check for new signals
    for symbol in symbols:
        # Skip if already in position
        if symbol in portfolio['positions']:
            continue
        
        signal = None  # Initialize to avoid UnboundLocalError
        try:
            # Fetch real mainnet data
            orderbook = exchange.fetch_order_book(symbol, limit=20)
            ticker = exchange.fetch_ticker(symbol)
            
            # Prepare detector data
            bid_volume = sum([float(q) for p, q in orderbook['bids'][:20]])
            ask_volume = sum([float(q) for p, q in orderbook['asks'][:20]])
            total_volume = bid_volume + ask_volume
            
            detector_data = {
                'symbol': symbol,
                'timestamp': datetime.now(),
                'best_bid': float(orderbook['bids'][0][0]),
                'best_ask': float(orderbook['asks'][0][0]),
                'imbalance': (bid_volume - ask_volume) / total_volume if total_volume > 0 else 0,
                'bid_volume_10': bid_volume,
                'ask_volume_10': ask_volume,
                'spread_pct': ((float(orderbook['asks'][0][0]) - float(orderbook['bids'][0][0])) 
                              / float(orderbook['bids'][0][0])) * 100,
            }
            
            # Check for pivot signal using symbol-specific detector
            signal = detectors[symbol].update(detector_data)
            
            if signal:
                # Track session (for metrics, not limits)
                session = detect_session()
                
                current_price = ticker['last']
                position = simulate_entry(symbol, signal, current_price)
                
                if position:
                    session_signals[session] += 1  # Track signal count
                    print(f"✅ ENTRY: {symbol} {signal['direction']} @ ${current_price:,.2f}")
                    print(f"   Size: ${position['position_value']:,.2f} ({position['amount']:.6f} {symbol[:3]})")
                    print(f"   Confidence: {signal['confidence']}% | SNR: {signal['snr']:.2f} | TF: {signal['timeframe']}s")
                    
                    # Log EXACT signals that triggered
                    print(f"   Signals Confirmed ({signal['signals_confirmed']}):")
                    for sig_name, triggered in signal['signals'].items():
                        if triggered:
                            snr_val = signal['signal_strengths'].get(sig_name, 0)
                            print(f"      ✓ {sig_name}: SNR={snr_val:.2f}")
                    print()
                else:
                    # No fill (due to fill rate or capital)
                    if iteration % 60 == 0 and signal:  # Log occasionally
                        print(f"⚪ NO_FILL: {symbol} {signal['direction']} (fill rate: {FILL_RATE*100:.0f}%)")
        
        except Exception as e:
            # Only log errors occasionally to avoid spam
            if iteration % 300 == 0:  # Every 5 minutes
                print(f"⚠️ Error processing {symbol}: {e}")
    
    # Sleep briefly (1 second polling)
    time.sleep(1)
