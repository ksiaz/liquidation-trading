"""
Debug script to check signal generator state and test signal generation
"""
import sys
import os
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signal_generator import SignalGenerator
from database import DatabaseManager

def test_signal_generator():
    """Test signal generator initialization and state"""
    print("=" * 80)
    print("SIGNAL GENERATOR TEST")
    print("=" * 80)
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    for symbol in symbols:
        print(f"\n{'-' * 80}")
        print(f"Testing {symbol}")
        print(f"{'-' * 80}")
        
        try:
            # Initialize signal generator
            sig_gen = SignalGenerator(symbol=symbol)
            print(f"✓ SignalGenerator initialized for {symbol}")
            
            # Check detector state
            if sig_gen.detector:
                print(f"✓ EarlyReversalDetector initialized")
                print(f"  Timeframes: {sig_gen.detector.timeframes}")
                print(f"  Max lookback: {sig_gen.detector.max_lookback_seconds}s")
                
                # Check Tier 1 components
                if sig_gen.detector.predictor:
                    print(f"✓ LiquidationPredictor available")
                else:
                    print(f"  LiquidationPredictor: None (using fallback)")
                    
                if sig_gen.detector.impact_calc:
                    print(f"✓ MarketImpactCalculator available")
                else:
                    print(f"  MarketImpactCalculator: None (using fallback)")
            else:
                print(f"✗ EarlyReversalDetector NOT initialized")
            
            # Get recent signals from memory
            recent_signals = sig_gen.get_recent_signals(limit=5)
            print(f"\nSignals in memory: {len(recent_signals)}")
            
            if recent_signals:
                for i, sig in enumerate(recent_signals, 1):
                    print(f"  {i}. {sig.get('direction')} @ ${sig.get('entry_price', 0):.2f} "
                          f"(Conf: {sig.get('confidence', 0):.1f}%, SNR: {sig.get('snr', 0):.2f})")
            
            # Get stats
            stats = sig_gen.get_stats()
            print(f"\nStatistics:")
            print(f"  Total signals: {stats.get('total_signals', 0)}")
            print(f"  LONG signals: {stats.get('long_signals', 0)}")
            print(f"  SHORT signals: {stats.get('short_signals', 0)}")
            print(f"  Avg confidence: {stats.get('avg_confidence', 0):.1f}%")
            print(f"  Avg SNR: {stats.get('avg_snr', 0):.2f}")
            
        except Exception as e:
            print(f"✗ Error testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

def check_dashboard_server_state():
    """Check if dashboard server has signal generators initialized"""
    print("\n" + "=" * 80)
    print("DASHBOARD SERVER STATE CHECK")
    print("=" * 80)
    
    try:
        import requests
        response = requests.get("http://localhost:5000/api/trading_signals?symbol=BTCUSDT", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Dashboard server is running")
            print(f"  BTCUSDT endpoint returned {len(data)} signals")
            
            if data:
                print(f"\nSample signal data:")
                print(json.dumps(data[0], indent=2, default=str))
        else:
            print(f"✗ Dashboard server returned status {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("✗ Dashboard server not running or not accessible")
    except Exception as e:
        print(f"✗ Error checking dashboard server: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_signal_generator()
    check_dashboard_server_state()
