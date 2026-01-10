"""
Quick test to verify live position tracking is working
"""
import time
import requests

print("🔄 Testing Live Position Tracking Fix")
print("=" * 60)
print("\n✅ FIX APPLIED:")
print("   • Changed signal['symbol'] → self.symbol")
print("   • Changed type 'EARLY_REVERSAL' → 'LIQUIDITY_DRAIN'")
print("\n📊 WHAT SHOULD HAPPEN:")
print("   • New signals will be added to performance_tracker.active_signals")
print("   • /api/live-positions will return active positions")
print("   • Dashboard 'Live Positions' section will populate")
print("\n🧪 TEST:")
print("   1. Restart desktop_app.py")
print("   2. Wait for a new signal to generate")
print("   3. Check dashboard - signal should appear in Live Positions (not just history)")
print("\n" + "=" * 60)

# Test the API
time.sleep(2)
try:
    response = requests.get("http://localhost:5000/api/live-positions", timeout=5)
    data = response.json()
    print(f"\n📡 API Response:")
    print(f"   Status: {response.status_code}")
    print(f"   Positions count: {data.get('count', 0)}")
    
    if data.get('count', 0) > 0:
        print(f"\n✅ LIVE POSITIONS FOUND:")
        for pos in data.get('positions', []):
            print(f"   • {pos['symbol']} {pos['direction']} @ ${pos['entry']} ({pos['unrealized_pnl']:+.2f}%)")
    else:
        print(f"\n⏳ No live positions yet (wait for next signal)")
except Exception as e:
    print(f"\n⚠️  Error: {e}")
    print(f"   (Desktop app might not be running yet)")
