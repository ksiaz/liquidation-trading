"""
Pivot Detection Backtest on Historical Data

Replays 88 hours of orderbook data through the PivotDetector
to see how many pivots it would have detected.
"""

import psycopg2
import numpy as np
from datetime import datetime
from collections import defaultdict
from pivot_detector import PivotDetector

# Connect to database
conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

# Configuration
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

print("=" * 100)
print("PIVOT DETECTION BACKTEST - Historical Data Replay")
print("=" * 100)
print()

# Initialize detectors
detectors = {}
for symbol in SYMBOLS:
    detectors[symbol] = PivotDetector(symbol)

# Track results
results = defaultdict(lambda: {
    'pivots_detected': [],
    'exhaustion_zones': 0,
    'total_snapshots': 0,
    'pivot_lows': 0,
    'pivot_highs': 0
})

for symbol in SYMBOLS:
    print(f"\n{'=' * 100}")
    print(f"REPLAYING: {symbol}")
    print(f"{'=' * 100}\n")
    
    # Fetch all orderbook snapshots for this symbol
    cur.execute("""
        SELECT 
            timestamp,
            best_bid,
            best_ask,
            imbalance
        FROM orderbook_snapshots
        WHERE symbol = %s
        ORDER BY timestamp
    """, (symbol,))
    
    snapshots = cur.fetchall()
    total = len(snapshots)
    
    print(f"📊 Total snapshots: {total:,}")
    print(f"   Replaying through PivotDetector...\n")
    
    results[symbol]['total_snapshots'] = total
    
    # Process each snapshot
    for i, (timestamp, best_bid, best_ask, imbalance) in enumerate(snapshots):
        # Prepare detector data
        detector_data = {
            'timestamp': timestamp,
            'best_bid': float(best_bid),
            'best_ask': float(best_ask),
            'imbalance': float(imbalance),
            'bid_volume_10': 1000,  # Placeholder - we don't have volume in DB
            'ask_volume_10': 1000,
        }
        
        # Update detector
        signal = detectors[symbol].update(detector_data)
        
        # Track if entered exhaustion zone
        if detectors[symbol].in_pivot_zone and not hasattr(detectors[symbol], '_zone_logged'):
            results[symbol]['exhaustion_zones'] += 1
            detectors[symbol]._zone_logged = True
        elif not detectors[symbol].in_pivot_zone:
            if hasattr(detectors[symbol], '_zone_logged'):
                delattr(detectors[symbol], '_zone_logged')
        
        # If pivot detected, log it
        if signal:
            mid_price = (detector_data['best_bid'] + detector_data['best_ask']) / 2
            
            results[symbol]['pivots_detected'].append({
                'timestamp': timestamp,
                'price': mid_price,
                'pivot_type': signal['pivot_type'],
                'direction': signal['direction'],
                'confidence': signal['confidence'],
                'details': signal['details']
            })
            
            if signal['pivot_type'] == 'LOW':
                results[symbol]['pivot_lows'] += 1
            else:
                results[symbol]['pivot_highs'] += 1
            
            print(f"🎯 PIVOT {signal['pivot_type']} @ {timestamp}")
            print(f"   Price: ${mid_price:.2f} | Direction: {signal['direction']}")
            print(f"   Confidence: {signal['confidence']:.2f}")
            print(f"   Imbalance flip: {signal['details']['imbalance_flip']:.2f}")
            print(f"   Zone duration: {signal['details']['zone_duration']:.0f}s")
            print()
        
        # Progress indicator
        if (i + 1) % 10000 == 0:
            print(f"   Processed {i+1:,}/{total:,} snapshots...")

cur.close()
conn.close()

# Final summary
print("\n" + "=" * 100)
print("BACKTEST RESULTS SUMMARY")
print("=" * 100)
print()

total_pivots = 0
total_snapshots = 0

for symbol in SYMBOLS:
    r = results[symbol]
    total_pivots += len(r['pivots_detected'])
    total_snapshots += r['total_snapshots']
    
    duration_hours = r['total_snapshots'] / 3600  # Assuming 1 snapshot/second
    pivots_per_hour = len(r['pivots_detected']) / duration_hours if duration_hours > 0 else 0
    
    print(f"📊 {symbol}")
    print(f"   Snapshots processed: {r['total_snapshots']:,}")
    print(f"   Duration: ~{duration_hours:.1f} hours")
    print(f"   Exhaustion zones entered: {r['exhaustion_zones']}")
    print(f"   Pivots detected: {len(r['pivots_detected'])}")
    print(f"      - Pivot LOWS: {r['pivot_lows']}")
    print(f"      - Pivot HIGHS: {r['pivot_highs']}")
    print(f"   Frequency: {pivots_per_hour:.2f} pivots/hour")
    print()
    
    # Show first few pivots as examples
    if r['pivots_detected']:
        print(f"   Sample Pivots:")
        for pivot in r['pivots_detected'][:3]:
            print(f"      {pivot['timestamp']} | {pivot['pivot_type']} @ ${pivot['price']:.2f} "
                  f"| Confidence: {pivot['confidence']:.2f}")
        if len(r['pivots_detected']) > 3:
            print(f"      ... and {len(r['pivots_detected']) - 3} more")
        print()

print(f"{'=' * 100}")
print(f"TOTAL ACROSS ALL SYMBOLS")
print(f"   Total snapshots: {total_snapshots:,}")
print(f"   Total pivots: {total_pivots}")
print(f"   Detection rate: {total_pivots/total_snapshots*100:.4f}% of snapshots")
print(f"{'=' * 100}")
print()

# Analysis
if total_pivots == 0:
    print("⚠️ NO PIVOTS DETECTED!")
    print("\nPossible reasons:")
    print("1. Thresholds are too strict")
    print("2. Market didn't have clear V-shaped reversals in this period")
    print("3. Need to adjust exhaustion/flip criteria")
    print("\nRecommendation: Review thresholds in pivot_detector.py")
elif total_pivots < 10:
    print("⚠️ Very few pivots detected")
    print("\nThis might indicate:")
    print("- Thresholds are quite strict (good for quality, bad for quantity)")
    print("- Consider loosening if you want more opportunities")
else:
    avg_per_day = (total_pivots / (total_snapshots / 3600 / 24))
    print(f"✅ Detected {total_pivots} pivots")
    print(f"   Average: {avg_per_day:.1f} pivots per day")
    print(f"\nThis seems {'reasonable' if 5 <= avg_per_day <= 20 else 'high' if avg_per_day > 20 else 'low'}")
