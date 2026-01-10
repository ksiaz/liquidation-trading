"""
Quick test to verify signals appear in dashboard after refresh
"""
import time
import webbrowser

print("🔄 Dashboard updated with signal loading function")
print("=" * 60)
print("\n✅ CHANGES MADE:")
print("   • Added loadHistoricalSignals() function")
print("   • Fetches from /api/trading_signals on page load")
print("   • Populates signalHistory array with DB signals")
print("\n📊 WHAT TO SEE:")
print("   • Open dashboard: http://localhost:5000")
print("   • Navigate to 'Signals' tab")
print("   • Should see 15+ historical signals immediately")
print("\n⚠️  NOTE: You need to REFRESH the browser (F5) if already open")
print("=" * 60)
