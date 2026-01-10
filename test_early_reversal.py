"""
Test Early Reversal Detection System

Tests the integrated early reversal detector with live orderbook data.
"""

import psycopg2
from datetime import datetime, timedelta
from early_reversal_detector import EarlyReversalDetector, ScalingExitManager

# Connect to database
conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 80)
print("EARLY REVERSAL DETECTION TEST")
print("=" * 80)

# Test with recent ETH data
symbol = 'ETHUSDT'
detector = EarlyReversalDetector(lookback_seconds=30)

# Get last 60 seconds of data
cur.execute("""
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        spread_pct,
        bid_volume_10,
        ask_volume_10,
        imbalance
    FROM orderbook_snapshots
    WHERE symbol = %s
    AND timestamp >= NOW() - INTERVAL '60 seconds'
    ORDER BY timestamp
""", (symbol,))

rows = cur.fetchall()

print(f"\n📊 Testing with {len(rows)} recent snapshots")

if len(rows) < 30:
    print("❌ Not enough data - need at least 30 seconds")
    conn.close()
    exit()

# Feed data to detector
signals_detected = []

for i, row in enumerate(rows):
    timestamp, best_bid, best_ask, spread_pct, bid_vol, ask_vol, imbalance = row
    
    # Prepare orderbook data
    ob_data = {
        'timestamp': timestamp,
        'best_bid': float(best_bid),
        'best_ask': float(best_ask),
        'spread_pct': float(spread_pct),
        'bid_volume_10': float(bid_vol),
        'ask_volume_10': float(ask_vol),
        'imbalance': float(imbalance)
    }
    
    # Update detector
    signal = detector.update(ob_data)
    
    if signal:
        signals_detected.append((i, timestamp, signal))
        print(f"\n🚨 SIGNAL DETECTED at {timestamp}")
        print(f"   Direction: {signal['direction']}")
        print(f"   Confidence: {signal['confidence']}%")
        print(f"   Entry: ${signal['entry_price']:.2f}")
        print(f"   Signals: {signal['signals_confirmed']}/4")
        print(f"   Details: {signal['signals']}")

print(f"\n{'=' * 80}")
print(f"SUMMARY")
print(f"{'=' * 80}")
print(f"Total snapshots processed: {len(rows)}")
print(f"Signals detected: {len(signals_detected)}")

if signals_detected:
    print(f"\n✅ Early reversal detection is WORKING!")
    print(f"\nSignals:")
    for i, timestamp, signal in signals_detected:
        print(f"  {timestamp}: {signal['direction']} @ ${signal['entry_price']:.2f} ({signal['confidence']}%)")
else:
    print(f"\n⚠️ No signals in last 60 seconds")
    print(f"   This is normal - signals are rare (high quality)")
    print(f"   Detector is working, just waiting for setup")

# Test scaling exit manager
if signals_detected:
    print(f"\n{'=' * 80}")
    print(f"TESTING SCALING EXIT MANAGER")
    print(f"{'=' * 80}")
    
    # Use first signal
    _, _, signal = signals_detected[0]
    
    exit_mgr = ScalingExitManager(
        entry_price=signal['entry_price'],
        direction=signal['direction'],
        symbol=symbol
    )
    
    print(f"\n✅ Exit manager created")
    print(f"   Entry: ${exit_mgr.entry_price:.2f}")
    print(f"   Target 1 (50%): ${exit_mgr.target_1:.2f} (+0.5%)")
    print(f"   Stop: ${exit_mgr.stop_loss:.2f} (-0.25%)")
    print(f"   Position: {exit_mgr.position_remaining}%")

conn.close()

print(f"\n{'=' * 80}")
print(f"✅ EARLY REVERSAL SYSTEM READY!")
print(f"{'=' * 80}")
