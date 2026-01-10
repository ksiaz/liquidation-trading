"""
Backtest Fill Tracker Impact

Compare signal generation:
1. WITHOUT fill tracker (current system)
2. WITH fill tracker (new system)

Period: 04:30-05:27 (the -0.47% move)
"""

import sys
sys.path.insert(0, 'd:/liquidation-trading')

import psycopg2
from datetime import datetime, timedelta
import numpy as np
from fill_tracker import FillTracker

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)

start_time = datetime(2026, 1, 1, 4, 30, 0)
end_time = datetime(2026, 1, 1, 5, 27, 0)
symbol = 'BTCUSDT'

# Get orderbook data
query = """
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        imbalance,
        bid_volume_10,
        ask_volume_10,
        bid_volume_20,
        ask_volume_20
    FROM orderbook_snapshots
    WHERE symbol = %s
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
"""

cur = conn.cursor()
cur.execute(query, (symbol, start_time, end_time))
rows = cur.fetchall()

print("=" * 120)
print("FILL TRACKER BACKTEST")
print("=" * 120)
print(f"\nTesting period: {start_time} to {end_time}")
print(f"Snapshots: {len(rows)}")

# Initialize fill tracker
tracker = FillTracker(lookback_seconds=60)

# Track signals
signals_generated = []

# Process each snapshot
for i, row in enumerate(rows):
    timestamp, best_bid, best_ask, imbalance, bid_vol_10, ask_vol_10, bid_vol_20, ask_vol_20 = row
    
    mid_price = (float(best_bid) + float(best_ask)) / 2
    
    # Create orderbook data
    orderbook_data = {
        'timestamp': timestamp,
        'bid_volume_10': float(bid_vol_10) if bid_vol_10 else 0,
        'ask_volume_10': float(ask_vol_10) if ask_vol_10 else 0,
        'bid_volume_20': float(bid_vol_20) if bid_vol_20 else 0,
        'ask_volume_20': float(ask_vol_20) if ask_vol_20 else 0
    }
    
    # Update tracker
    tracker.update(orderbook_data)
    
    # Get prediction
    prediction, confidence, reason = tracker.predict_balance_flip()
    
    if prediction and confidence > 0.5:
        # Calculate actual price move 30s later
        future_idx = min(i + 30, len(rows) - 1)
        future_price = (float(rows[future_idx][1]) + float(rows[future_idx][2])) / 2
        price_move_30s = ((future_price - mid_price) / mid_price * 100)
        
        # Determine if prediction was correct
        if prediction == 'FLIP_TO_BID' and price_move_30s > 0:
            correct = True
        elif prediction == 'FLIP_TO_ASK' and price_move_30s < 0:
            correct = True
        else:
            correct = False
        
        signals_generated.append({
            'timestamp': timestamp,
            'prediction': prediction,
            'confidence': confidence,
            'reason': reason,
            'price': mid_price,
            'price_move_30s': price_move_30s,
            'correct': correct
        })

print(f"\n{'=' * 120}")
print("RESULTS")
print(f"{'=' * 120}")

print(f"\nSignals Generated: {len(signals_generated)}")

if signals_generated:
    # Group by prediction type
    flip_to_bid = [s for s in signals_generated if s['prediction'] == 'FLIP_TO_BID']
    flip_to_ask = [s for s in signals_generated if s['prediction'] == 'FLIP_TO_ASK']
    
    print(f"\nFLIP_TO_BID signals: {len(flip_to_bid)}")
    print(f"FLIP_TO_ASK signals: {len(flip_to_ask)}")
    
    # Accuracy
    correct_signals = [s for s in signals_generated if s['correct']]
    accuracy = len(correct_signals) / len(signals_generated) * 100
    
    print(f"\nAccuracy: {accuracy:.1f}% ({len(correct_signals)}/{len(signals_generated)})")
    
    # Average confidence
    avg_confidence = np.mean([s['confidence'] for s in signals_generated])
    print(f"Average Confidence: {avg_confidence:.2%}")
    
    # Average price move
    avg_move = np.mean([abs(s['price_move_30s']) for s in signals_generated])
    print(f"Average Price Move (30s): {avg_move:.3f}%")
    
    # Correct vs incorrect moves
    correct_moves = [abs(s['price_move_30s']) for s in signals_generated if s['correct']]
    incorrect_moves = [abs(s['price_move_30s']) for s in signals_generated if not s['correct']]
    
    if correct_moves:
        print(f"Avg move when CORRECT: {np.mean(correct_moves):.3f}%")
    if incorrect_moves:
        print(f"Avg move when INCORRECT: {np.mean(incorrect_moves):.3f}%")
    
    # Show top signals by confidence
    print(f"\n{'=' * 120}")
    print("TOP 10 SIGNALS (by confidence)")
    print(f"{'=' * 120}")
    print(f"{'Time':<20} {'Prediction':<15} {'Conf':<8} {'Price':<12} {'Move 30s':<12} {'Correct':<10}")
    print("-" * 120)
    
    sorted_signals = sorted(signals_generated, key=lambda x: x['confidence'], reverse=True)[:10]
    for sig in sorted_signals:
        print(f"{sig['timestamp'].strftime('%H:%M:%S'):<20} "
              f"{sig['prediction']:<15} "
              f"{sig['confidence']:>7.1%} "
              f"${sig['price']:>10,.2f} "
              f"{sig['price_move_30s']:>+11.3f}% "
              f"{'✓' if sig['correct'] else '✗':<10}")
    
    # Breakdown by confidence level
    print(f"\n{'=' * 120}")
    print("PERFORMANCE BY CONFIDENCE LEVEL")
    print(f"{'=' * 120}")
    
    high_conf = [s for s in signals_generated if s['confidence'] >= 0.7]
    med_conf = [s for s in signals_generated if 0.5 <= s['confidence'] < 0.7]
    
    if high_conf:
        high_correct = len([s for s in high_conf if s['correct']])
        print(f"\nHigh Confidence (≥70%): {len(high_conf)} signals")
        print(f"   Accuracy: {high_correct/len(high_conf)*100:.1f}%")
        print(f"   Avg Move: {np.mean([abs(s['price_move_30s']) for s in high_conf]):.3f}%")
    
    if med_conf:
        med_correct = len([s for s in med_conf if s['correct']])
        print(f"\nMedium Confidence (50-70%): {len(med_conf)} signals")
        print(f"   Accuracy: {med_correct/len(med_conf)*100:.1f}%")
        print(f"   Avg Move: {np.mean([abs(s['price_move_30s']) for s in med_conf]):.3f}%")
    
    # Show signal distribution over time
    print(f"\n{'=' * 120}")
    print("SIGNAL TIMELINE")
    print(f"{'=' * 120}")
    
    # Group by 10-minute windows
    time_windows = {}
    for sig in signals_generated:
        window = sig['timestamp'].replace(second=0, microsecond=0)
        window = window.replace(minute=(window.minute // 10) * 10)
        
        if window not in time_windows:
            time_windows[window] = []
        time_windows[window].append(sig)
    
    for window in sorted(time_windows.keys()):
        sigs = time_windows[window]
        correct = len([s for s in sigs if s['correct']])
        print(f"{window.strftime('%H:%M')}: {len(sigs)} signals ({correct} correct, {correct/len(sigs)*100:.0f}%)")

else:
    print("\n❌ No signals generated")
    print("\nPossible reasons:")
    print("  - Conviction threshold too high (>0.5)")
    print("  - Not enough filled orders detected")
    print("  - Fill patterns not strong enough")

# Get final tracker stats
print(f"\n{'=' * 120}")
print("FILL TRACKER STATS")
print(f"{'=' * 120}")

stats = tracker.get_stats()
for key, value in stats.items():
    print(f"  {key}: {value}")

conn.close()

print(f"\n{'=' * 120}\n")
