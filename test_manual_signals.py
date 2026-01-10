"""
Manual test to verify signal generation is working
"""
import sys
import os
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signal_generator import SignalGenerator
from database import DatabaseManager

def test_signal_generation_with_real_data():
    """Test signal generation using real orderbook data from database"""
    print("=" * 80)
    print("MANUAL SIGNAL GENERATION TEST")
    print("=" * 80)
    
    # Initialize database
    db = DatabaseManager()
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    for symbol in symbols:
        print(f"\n{'-' * 80}")
        print(f"Testing {symbol}")
        print(f"{'-' * 80}")
        
        try:
            # Initialize signal generator
            sig_gen = SignalGenerator(db, symbol=symbol)
            print(f"✓ SignalGenerator initialized")
            
            # Get recent orderbook snapshots from database
            query = """
            SELECT timestamp, best_bid, best_ask, spread_pct,
                   bid_volume_10, ask_volume_10, imbalance
            FROM orderbook_snapshots
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT 300
            """
            
            db.cursor.execute(query, (symbol,))
            snapshots = db.cursor.fetchall()
            
            print(f"✓ Retrieved {len(snapshots)} orderbook snapshots")
            
            if not snapshots:
                print(f"✗ No orderbook data available for {symbol}")
                continue
            
            # Process snapshots (in reverse chronological order to simulate real-time)
            print(f"\nProcessing {len(snapshots)} snapshots...")
            signals_generated = 0
            
            for i, row in enumerate(reversed(snapshots)):
                timestamp, best_bid, best_ask, spread_pct, bid_vol, ask_vol, imbalance = row
                
                # Prepare orderbook data
                ob_data = {
                    'symbol': symbol,
                    'best_bid': float(best_bid),
                    'best_ask': float(best_ask),
                    'imbalance': float(imbalance) if imbalance else 0,
                    'bid_volume_10': float(bid_vol) if bid_vol else 0,
                    'ask_volume_10': float(ask_vol) if ask_vol else 0,
                    'spread_pct': float(spread_pct) if spread_pct else 0,
                    'timestamp': timestamp
                }
                
                # Process for signal generation
                signal = sig_gen.process_orderbook(ob_data)
                
                if signal:
                    signals_generated += 1
                    print(f"\n  ✓ Signal #{signals_generated} generated at snapshot {i+1}/{len(snapshots)}:")
                    print(f"    Direction: {signal['direction']}")
                    print(f"    Entry: ${signal['entry_price']:,.2f}")
                    print(f"    Confidence: {signal['confidence']:.1f}%")
                    print(f"    SNR: {signal['snr']:.2f}")
                    print(f"    Timeframe: {signal['timeframe']}s")
                    print(f"    Signals: {signal['signals_confirmed']}/{signal['signals_total']}")
                
                # Progress indicator every 50 snapshots
                if (i + 1) % 50 == 0:
                    print(f"  Processed {i+1}/{len(snapshots)} snapshots...")
            
            print(f"\n✓ Test complete for {symbol}")
            print(f"  Total signals generated: {signals_generated}")
            
            # Get stats
            stats = sig_gen.get_stats()
            print(f"\n  Generator Stats:")
            print(f"    Total signals: {stats.get('total_signals', 0)}")
            print(f"    LONG: {stats.get('long_signals', 0)}")
            print(f"    SHORT: {stats.get('short_signals', 0)}")
            print(f"    Avg Confidence: {stats.get('avg_confidence', 0):.1f}%")
            print(f"    Avg SNR: {stats.get('avg_snr', 0):.2f}")
            
            # Check database for saved signals
            db.cursor.execute("""
                SELECT COUNT(*) FROM trading_signals WHERE symbol = %s
            """, (symbol,))
            db_count = db.cursor.fetchone()[0]
            print(f"\n  Signals in database: {db_count}")
            
        except Exception as e:
            print(f"✗ Error testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    
    db.close()

if __name__ == "__main__":
    test_signal_generation_with_real_data()
