"""Debug script to check M3 price storage."""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem

obs = ObservationSystem(allowed_symbols=["BTCUSDT"])

# Create liquidation
obs.ingest_observation(
    timestamp=1000.0,
    symbol="BTCUSDT",
    event_type="LIQUIDATION",
    payload={
        "E": 1000000,
        "o": {
            "p": "50000.0",
            "q": "100.0",
            "S": "BUY"
        }
    }
)

# Trade
obs.ingest_observation(
    timestamp=1001.0,
    symbol="BTCUSDT",
    event_type="TRADE",
    payload={
        "p": "50025.0",
        "q": "10.0",
        "T": 1001000,
        "m": False
    }
)

# Check M2
nodes = obs._m2_store.get_active_nodes(symbol="BTCUSDT")
print(f"Active nodes: {len(nodes)}")
if nodes:
    print(f"Node 0: price={nodes[0].price_center}, band={nodes[0].price_band}")

# Check M3
prices = obs._m3.get_recent_prices(symbol="BTCUSDT")
print(f"Recent prices from M3: {prices}")

# Get snapshot
snapshot = obs.query({"type": "snapshot"})
print(f"Zone penetration: {snapshot.primitives['BTCUSDT'].zone_penetration}")
