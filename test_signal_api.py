"""
Test if signal API endpoint is working
"""
import requests
import json

url = "http://localhost:5000/api/trading_signals"

for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
    try:
        response = requests.get(url, params={'symbol': symbol, 'limit': 10})
        print(f"\n{'='*60}")
        print(f"Testing: {symbol}")
        print(f"{'='*60}")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {data.keys()}")
            
            if 'signals' in data:
                signals = data['signals']
                print(f"Signals count: {len(signals)}")
                if signals:
                    print(f"First signal: {signals[0]}")
                else:
                    print("✅ API working but no signals (market is flat)")
            else:
                print(f"⚠️ Unexpected response: {data}")
        else:
            print(f"❌ Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

print(f"\n{'='*60}")
print("If API returns 200 with empty signals list, the UI is working correctly.")
print("The 'Waiting for signals...' message means NO signals exist yet.")
print("='*60}")
