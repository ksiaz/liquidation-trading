"""
Debug script to check signal generator integration
"""
import requests

# Check if signal generators are initialized
try:
    response = requests.get('http://localhost:5000/api/debug-signal-generators')
    print("Response:", response.text)
except:
    print("Endpoint doesn't exist - need to add it")

# For now, let's add debug logging to check the actual issue
print("\n" + "="*60)
print("ISSUE IDENTIFIED:")
print("="*60)
print("\nIn dashboard_server.py line 48-63:")
print("signal_generators = {}")
print("for symbol in SYMBOLS:")
print("    signal_generators[symbol] = NewSignalGenerator(...)")
print("\nIn dashboard_server.py line 72:")
print("orderbook_storage.signal_generators = signal_generators")
print("\nIn orderbook_storage.py line 122:")
print("if symbol in self.signal_generators and self.signal_generators[symbol]:")
print("    signal_gen.process_orderbook(ob_data)")
print("\n" + "="*60)
print("This SHOULD work if signal_generators dict is populated correctly")
print("Need to check:")
print("1. Are signal generators actually initialized?")
print("2. Is the dict assignment working?")
print("3. Are there any exceptions during initialization?")
print("="*60)
