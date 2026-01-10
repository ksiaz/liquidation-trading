import requests
import json

print("Testing /api/trading_signals endpoint...")
print("=" * 60)

try:
    # Test BTCUSDT
    response = requests.get("http://localhost:5000/api/trading_signals?symbol=BTCUSDT", timeout=5)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        signals = data.get('signals', [])
        
        print(f"\nTotal signals returned: {len(signals)}")
        
        if signals:
            print("\nFirst 5 signals:")
            for i, sig in enumerate(signals[:5], 1):
                print(f"{i}. {sig.get('symbol')} {sig.get('direction')} @ ${sig.get('entry_price'):,.2f} "
                      f"(Conf: {sig.get('confidence')}%) - {sig.get('timestamp')}")
        else:
            print("\n❌ NO SIGNALS IN API RESPONSE")
            print("\nFull response:")
            print(json.dumps(data, indent=2))
    else:
        print(f"\n❌ HTTP Error: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
