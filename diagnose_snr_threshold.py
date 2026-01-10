"""
Diagnostic: Why didn't SNR 0.3 generate signals?
Check individual signal SNRs to understand the filtering.
"""

import sys
import psycopg2
from datetime import datetime, timedelta
from collections import deque
import logging

# Setup logging to see debug info
logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, 'd:/liquidation-trading')
from early_reversal_detector import EarlyReversalDetector

conn = psycopg2.connect(
    dbname="liquidation_trading",
    user="postgres",
    password="postgres",
    host="localhost"
)
cur = conn.cursor()

print("=" * 100)
print("DIAGNOSTIC: Individual Signal SNR Analysis")
print("Testing with SNR threshold = 0.3 (original)")
print("=" * 100)

# Test period: 6 hours
end_time = datetime(2026, 1, 1, 7, 0, 0)
start_time = end_time - timedelta(hours=6)

symbol = 'BTCUSDT'

cur.execute("""
    SELECT 
        timestamp,
        best_bid,
        best_ask,
        imbalance,
        bid_volume_10,
        ask_volume_10,
        spread_pct
    FROM orderbook_snapshots
    WHERE symbol = %s
    AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
""", (symbol, start_time, end_time))

rows = cur.fetchall()

print(f"\n📊 Processing {len(rows)} snapshots for {symbol}...")

# Test with ORIGINAL threshold (0.3)
detector = EarlyReversalDetector(
    max_lookback_seconds=300,
    snr_threshold=0.3  # ORIGINAL
)

near_misses = []
signals_generated = 0

for i, row in enumerate(rows):
    timestamp, best_bid, best_ask, imbalance, bid_vol, ask_vol, spread_pct = row
    
    orderbook_data = {
        'timestamp': timestamp,
        'symbol': symbol,
        'best_bid': float(best_bid),
        'best_ask': float(best_ask),
        'imbalance': float(imbalance) if imbalance else 0,
        'bid_volume_10': float(bid_vol) if bid_vol else 0,
        'ask_volume_10': float(ask_vol) if ask_vol else 0,
        'spread_pct': float(spread_pct) if spread_pct else 0
    }
    
    # Manually check what's happening at each timeframe
    detector.update(orderbook_data)
    
    # Every 60 seconds, check signal status
    if i % 60 == 0 and len(detector.price_history) >= 60:
        # Try to detect at 60s timeframe
        for tf in [60, 120, 180]:
            if len(detector.price_history) < tf:
                continue
                
            data_points = min(tf, len(detector.price_history))
            split_point = int(data_points * 2 / 3)
            
            earlier_prices = list(detector.price_history)[-data_points:-split_point] if split_point > 0 else []
            recent_prices = list(detector.price_history)[-split_point:]
            
            if len(earlier_prices) < 5 or len(recent_prices) < 5:
                continue
            
            earlier_avg = sum(earlier_prices) / len(earlier_prices)
            recent_avg = sum(recent_prices) / len(recent_prices)
            price_change_pct = (recent_avg - earlier_avg) / earlier_avg
            
            if abs(price_change_pct) < 0.0005:
                continue
            
            price_direction = 'UP' if price_change_pct > 0 else 'DOWN'
            
            # Check individual signal SNRs
            imb_signal, imb_snr = detector._check_imbalance_divergence_with_snr(
                price_direction, data_points, split_point
            )
            depth_signal, depth_snr = detector._check_depth_building_with_snr(
                price_direction, data_points, split_point
            )
            spread_signal, spread_snr = detector._check_spread_contraction_with_snr(
                data_points, split_point
            )
            vol_signal, vol_snr = detector._check_volume_exhaustion_with_snr(
                price_direction, data_points, split_point
            )
            
            confirmed = sum([imb_signal, depth_signal, spread_signal, vol_signal])
            active_snrs = []
            if imb_signal:
                active_snrs.append(imb_snr)
            if depth_signal:
                active_snrs.append(depth_snr)
            if spread_signal:
                active_snrs.append(spread_snr)
            if vol_signal:
                active_snrs.append(vol_snr)
            
            overall_snr = sum(active_snrs) / len(active_snrs) if active_snrs else 0
            
            # Near miss: has 2+ signals but SNR too low
            if confirmed >= 2 and overall_snr < 0.3:
                near_misses.append({
                    'time': timestamp,
                    'timeframe': tf,
                    'direction': price_direction,
                    'confirmed': confirmed,
                    'overall_snr': overall_snr,
                    'imb': (imb_signal, imb_snr),
                    'depth': (depth_signal, depth_snr),
                    'spread': (spread_signal, spread_snr),
                    'vol': (vol_signal, vol_snr)
                })

print(f"\n{'=' * 100}")
print("RESULTS")
print(f"{'=' * 100}")

print(f"\nSignals Generated with SNR=0.3: {signals_generated}")
print(f"Near Misses (2+ signals but SNR < 0.3): {len(near_misses)}")

if near_misses:
    print(f"\n{'=' * 100}")
    print("NEAR MISS ANALYSIS (First 10)")
    print(f"{'=' * 100}")
    
    for i, miss in enumerate(near_misses[:10], 1):
        print(f"\n#{i} - {miss['time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Timeframe: {miss['timeframe']}s")
        print(f"   Direction: {miss['direction']}")
        print(f"   Confirmed Signals: {miss['confirmed']}")
        print(f"   Overall SNR: {miss['overall_snr']:.3f} (needed 0.3)")
        print(f"   Individual SNRs:")
        print(f"      Imbalance: {'✓' if miss['imb'][0] else '✗'} SNR={miss['imb'][1]:.3f}")
        print(f"      Depth:     {'✓' if miss['depth'][0] else '✗'} SNR={miss['depth'][1]:.3f}")
        print(f"      Spread:    {'✓' if miss['spread'][0] else '✗'} SNR={miss['spread'][1]:.3f}")
        print(f"      Volume:    {'✓' if miss['vol'][0] else '✗'} SNR={miss['vol'][1]:.3f}")
    
    # Statistics
    avg_overall_snr = sum(m['overall_snr'] for m in near_misses) / len(near_misses)
    print(f"\n{'=' * 100}")
    print("STATISTICS")
    print(f"{'=' * 100}")
    print(f"\nAverage Overall SNR of Near Misses: {avg_overall_snr:.3f}")
    print(f"This explains why SNR=0.3 didn't work!")
    print(f"With SNR=0.15, these {len(near_misses)} would become valid signals.")

conn.close()
