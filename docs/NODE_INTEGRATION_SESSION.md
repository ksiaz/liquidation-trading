# Hyperliquid Node Integration Session

**Date:** 2026-01-19
**Purpose:** Integrate direct node data access to eliminate API rate limits

---

## Summary

This session established direct data access from a Hyperliquid non-validator node running on VM `64.176.65.252`. The goal was to bypass API rate limits that were causing stale position data in the trading app.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Trading App        │────>│  Node Proxy (HTTP)   │────>│  HL Node        │
│  (Windows local)    │     │  64.176.65.252:8080  │     │  (hl-visor)     │
└─────────────────────┘     └──────────────────────┘     └─────────────────┘
         │                           │
         │                           │
    node_client.py             node_proxy.py
    (receiver)                  (server)
```

## Components Created

### 1. Node Proxy Server (`scripts/node_proxy.py`)

Deployed to VM at `~/node_proxy.py`, running on port 8080.

**Endpoints:**
- `GET /mids` - All mid prices (from replica_cmds blocks)
- `GET /trades` - Recent trades
- `GET /health` - Node sync status
- `GET /positions/<wallet>` - Positions (placeholder)

**How it works:**
- Reads from `~/hl/data/replica_cmds/` (line-delimited JSON blocks)
- Extracts prices from `order` and `batchModify` actions
- 500ms cache for performance

### 2. Node Client (`runtime/hyperliquid/node_client.py`)

Local client for fetching node data.

**Features:**
- `NodeClient` class with configurable timeout (5s default)
- 100ms price cache to reduce requests
- Asset ID to coin name mapping (47 assets)
- Singleton pattern via `get_node_client()`

**Key functions:**
```python
get_node_mids()     # Returns Dict[str, float] of coin -> price
get_node_trades()   # Returns List[Dict] of recent trades
get_node_health()   # Returns NodeStatus dataclass
```

### 3. Asset ID Mapping

Hyperliquid uses numeric asset IDs internally:
```python
ASSET_ID_TO_COIN = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX", 5: "SOL",
    6: "AVAX", 7: "BNB", 8: "APE", 9: "OP", 10: "LTC", 11: "ARB",
    12: "DOGE", 13: "INJ", 14: "SUI", 15: "kPEPE", 16: "XRP", 17: "LINK",
    ...
}
```

## Node Data Structure (abci_state.rmp)

The node stores full exchange state in `~/hl/hyperliquid_data/abci_state.rmp` (927MB msgpack).

**Structure:**
```
exchange/
├── user_states: list[1,455,522]     # All users
├── blp/                              # Perp clearinghouse
│   ├── u: list[3,480]               # Users with perp positions
│   │   └── [wallet, {o: {}, t: [[asset_id, [{b, s}, ...]]]}]
│   ├── p: float                      # Price factor
│   ├── r: dict                       # Rates/funding
│   └── b: dict                       # Book data
├── spot_clearinghouse/               # Spot data
├── vaults: list[8,934]              # Vault data
└── context/                          # Block context
    └── height, time, etc.
```

**Position format in blp/u:**
```json
{
  "b": 9999673699,    // Basis (scaled by 1e8)
  "s": 9999624005     // Size (scaled by 1e8)
}
```

## What Node Data Exposes

**Available:**
- Mid prices (extracted from order flow)
- Order book activity (orders, cancels, modifies)
- Block timestamps and sync status
- Full exchange state (positions, balances)

**Not directly available:**
- Liquidations (forceOrders) - system operations not in replica_cmds
- Must detect via position disappearance or price crossing liq price

## Integration Status

### Working:
- Node proxy serving prices on port 8080
- Node client integrated into main.py
- `fetch_mids_fast()` prefers node data, falls back to API
- Node health: ~1 second lag, synced

### Remaining Work:
- Position data parsing from abci_state.rmp not implemented
- Need to parse msgpack state file for full position data
- Liquidation detection via position monitoring

## Node Proxy Maintenance

**Start proxy:**
```bash
ssh root@64.176.65.252
nohup python3 ~/node_proxy.py > /tmp/proxy.log 2>&1 &
```

**Check status:**
```bash
curl http://64.176.65.252:8080/health
```

**View logs:**
```bash
ssh root@64.176.65.252 'tail -f /tmp/proxy.log'
```

## Known Issues

1. **429 Rate Limits on clearinghouseState**: Position fetching still uses API
2. **Stale positions**: Liquidated positions persist until refresh
3. **Position parsing incomplete**: abci_state.rmp structure documented but not parsed

## Next Steps

1. Implement position parsing from abci_state.rmp
2. Add `/all_positions` endpoint to node proxy
3. Wire WSPositionTracker to use node data exclusively
4. Remove all API fallbacks

## Files Modified

- `runtime/hyperliquid/node_client.py` (created)
- `runtime/native_app/main.py` (node integration)
- `scripts/node_proxy.py` (created, deployed to VM)

## Performance

- Node lag: ~1 second behind consensus
- Price updates: 101 assets available
- Block height: ~865,900,000
- Proxy memory: ~50MB typical
