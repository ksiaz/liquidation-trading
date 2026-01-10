"""
Comprehensive Liquidation Feed Diagnostic
Tests every component in the data flow chain
"""
import sys
import time
import queue
from datetime import datetime

print("=" * 80)
print("LIQUIDATION FEED DIAGNOSTIC")
print("=" * 80)

# Test 1: Binance Stream Connectivity
print("\n[1/6] Testing Binance WebSocket Connection...")
try:
    from liquidation_stream import BinanceLiquidationStream
    from config import SYMBOLS
    
    stream = BinanceLiquidationStream(symbols=SYMBOLS)
    stream.start()
    time.sleep(3)
    
    if stream.data_queue.qsize() > 0:
        sample = stream.data_queue.get()
        print(f"   ✅ Stream working - Sample: {sample['symbol']} {sample['side']} ${sample['value_usd']:.2f}")
    else:
        print("   ⚠️  No liquidations yet (market might be calm)")
    
    stream.stop()
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# Test 2: Database Connection
print("\n[2/6] Testing Database Connection...")
try:
    from database import DatabaseManager
    db = DatabaseManager()
    
    # Check recent liquidations
    recent = db.get_recent_liquidations(limit=5)
    if recent:
        print(f"   ✅ Database working - Found {len(recent)} recent liquidations")
        latest = recent[0]
        print(f"      Latest: {latest['symbol']} {latest['side']} ${latest['value_usd']:.2f} at {latest['timestamp']}")
    else:
        print("   ⚠️  No liquidations in database")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Monitor Callback
print("\n[3/6] Testing Monitor Callback...")
try:
    from monitor import LiquidationMonitor
    
    callback_triggered = False
    callback_data = None
    
    def test_callback(event):
        nonlocal callback_triggered, callback_data
        callback_triggered = True
        callback_data = event
    
    monitor = LiquidationMonitor(setup_signals=False, live_callback=test_callback)
    
    # Simulate event
    test_event = {
        'symbol': 'BTCUSDT',
        'side': 'SELL',
        'value_usd': 1000,
        'price': 95000,
        'quantity': 0.01,
        'timestamp': datetime.now().isoformat()
    }
    
    monitor._process_event(test_event)
    
    if callback_triggered:
        print(f"   ✅ Callback working - Received: {callback_data['symbol']}")
    else:
        print(f"   ❌ Callback NOT triggered")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Dashboard Queue
print("\n[4/6] Testing Dashboard Queue...")
try:
    from dashboard_server import liquidation_queue
    
    # Check queue size
    print(f"   Queue size: {liquidation_queue.qsize()}")
    
    # Try adding to queue
    test_liq = {
        'timestamp': datetime.now().isoformat(),
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'value_usd': 5000,
        'price': 95000,
        'quantity': 0.05
    }
    
    liquidation_queue.put(test_liq)
    print(f"   ✅ Queue accessible - Added test liquidation")
    
    # Retrieve it
    retrieved = liquidation_queue.get(timeout=1)
    print(f"   ✅ Queue working - Retrieved: {retrieved['symbol']}")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 5: SSE Stream Endpoint
print("\n[5/6] Testing SSE Stream Endpoint...")
try:
    import requests
    
    # Add test liquidation to queue first
    from dashboard_server import liquidation_queue
    liquidation_queue.put({
        'timestamp': datetime.now().isoformat(),
        'symbol': 'ETHUSDT',
        'side': 'SELL',
        'value_usd': 2000,
        'price': 3000,
        'quantity': 0.66
    })
    
    print("   ⚠️  SSE endpoint requires server to be running")
    print("   Test manually: curl -N http://localhost:5000/stream/liquidations")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 6: Integration Test
print("\n[6/6] Integration Test - Full Chain...")
try:
    from desktop_app import DesktopApp
    
    print("   Desktop app components:")
    app = DesktopApp()
    print(f"   ✅ DesktopApp initializes")
    print(f"   ✅ Port: {app.port}")
    print(f"   Note: start_monitor() wires callback to queue")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)

print("\n📋 **Summary:**")
print("1. If Binance stream works → Monitor can receive liquidations")
print("2. If callback works → Liquidations can reach dashboard queue")
print("3. If queue works → SSE can stream to dashboard")
print("4. If JavaScript has no errors → Dashboard can render")

print("\n🔍 **Next Steps:**")
print("1. Run this diagnostic while market is active")
print("2. Start desktop app: python desktop_app.py")
print("3. Check browser console (F12) for JavaScript errors")
print("4. Test SSE manually: curl -N http://localhost:5000/stream/liquidations")
