# DATA LANE INVENTORY

**Date:** 2026-02-01
**Purpose:** Document all data lanes with verification status
**Type:** Factual Inventory (Evidence-Based)

---

## LIVE DATA LANES (Verified Flowing)

### Lane 1: HL Node File Output

| Field | Value |
|-------|-------|
| **Source** | HL Node (localhost process) |
| **Transport** | File I/O |
| **Event Types** | SetGlobalAction (prices), Fills (liquidations) |
| **Schema** | NDJSON with action/fill structures |
| **Frequency** | Continuous (~8 sec/block) |
| **Timestamp Semantics** | Block time (nanoseconds) |
| **Persistence** | `~/hl/data/replica_cmds/` and `~/hl/data/node_fills/hourly/` |
| **Status** | ACTIVE - 24GB replica_cmds, 1.2GB node_fills today |

**Observed Schema (replica_cmds):**
```json
{"action":{"SetGlobalAction":{"prices":[[oracle,mark],...],"coin_index":idx}}}
```

**Observed Schema (node_fills):**
```json
[wallet_address, {"fill":{...}, "liquidation":{...optional...}}]
```

---

### Lane 2: HL Node Checkpoint

| Field | Value |
|-------|-------|
| **Source** | HL Node Adapter (when running) |
| **Transport** | File I/O |
| **Event Types** | Checkpoint state |
| **Schema** | JSON with session, positions, counts |
| **Frequency** | Periodic (~30 sec) |
| **Timestamp Semantics** | Unix timestamp |
| **Persistence** | `~/.hl-node-adapter/checkpoint.json` |
| **Status** | STALE - Last update 10:11 today |

**Observed Schema:**
```json
{
  "last_update": 1769935904,
  "price_session": "2026-02-01T08:43:07Z",
  "prices_emitted": 190,
  "liquidations_emitted": 0
}
```

---

## NOT FLOWING DATA LANES (Expected But Missing)

### Lane 3: gRPC Adapter Stream

| Field | Value |
|-------|-------|
| **Source** | gRPC Server (localhost:50051) |
| **Transport** | gRPC streaming |
| **Event Types** | PriceEvent, LiquidationEvent, SyncStatus |
| **Schema** | Protobuf (events.proto) |
| **Frequency** | Real-time |
| **Timestamp Semantics** | Preserved from node |
| **Persistence** | None (streaming) |
| **Status** | NOT FLOWING - Server not running |

**Why Not Flowing:**
- gRPC server process not started
- Port 50051 not listening
- NodeBridge cannot connect

---

### Lane 4: Binance WebSocket Liquidations

| Field | Value |
|-------|-------|
| **Source** | Binance Futures API |
| **Transport** | WebSocket (`wss://fstream.binance.com`) |
| **Event Types** | forceOrder (liquidations) |
| **Schema** | `{"e":"forceOrder","E":ts,"o":{...}}` |
| **Frequency** | Event-driven |
| **Timestamp Semantics** | Exchange time (milliseconds) |
| **Persistence** | `execution.db:liquidation_events` |
| **Status** | NOT FLOWING - Collector not running |

**Historical Evidence:**
- 7,614 liquidation events in database
- Last event: 2026-02-01 08:49:27 (2.5 hours ago)
- Stream was active, now stopped

---

### Lane 5: Binance WebSocket Trades

| Field | Value |
|-------|-------|
| **Source** | Binance Futures API |
| **Transport** | WebSocket |
| **Event Types** | aggTrade |
| **Schema** | `{"e":"aggTrade","E":ts,"p":price,"q":qty,...}` |
| **Frequency** | High-frequency |
| **Timestamp Semantics** | Exchange time (milliseconds) |
| **Persistence** | In-memory only (M1 buffers) |
| **Status** | NOT FLOWING - Collector not running |

---

### Lane 6: Binance WebSocket Depth

| Field | Value |
|-------|-------|
| **Source** | Binance Futures API |
| **Transport** | WebSocket |
| **Event Types** | depthUpdate |
| **Schema** | `{"e":"depthUpdate","b":[[price,qty],...],"a":[[price,qty],...]}` |
| **Frequency** | 100ms intervals |
| **Timestamp Semantics** | Exchange time (milliseconds) |
| **Persistence** | In-memory only |
| **Status** | NOT FLOWING - Collector not running |

---

## NEVER POPULATED DATA LANES

### Lane 7: HL Position Data

| Field | Value |
|-------|-------|
| **Source** | Hyperliquid REST/WebSocket |
| **Transport** | HTTP/WebSocket |
| **Event Types** | Position snapshots, wallet state |
| **Schema** | HyperliquidCollector format |
| **Frequency** | On-demand / streaming |
| **Timestamp Semantics** | Server time |
| **Persistence** | `execution.db:hl_positions` |
| **Status** | NEVER POPULATED - 0 rows |

**Evidence:**
- `hl_positions` table has 0 rows
- HyperliquidCollector code exists but never produced data
- WebSocket connection logs show "ping timeout" errors

---

### Lane 8: HL Cascade Events

| Field | Value |
|-------|-------|
| **Source** | CascadeDetector (internal) |
| **Transport** | In-process |
| **Event Types** | Cascade start, wave, exhaustion |
| **Schema** | CascadeEvent dataclass |
| **Frequency** | Event-driven |
| **Timestamp Semantics** | System time |
| **Persistence** | `execution.db:hl_cascade_events` |
| **Status** | NEVER POPULATED - 0 rows |

---

### Lane 9: HL Mark Prices

| Field | Value |
|-------|-------|
| **Source** | HyperliquidCollector |
| **Transport** | In-process |
| **Event Types** | Mark price updates |
| **Schema** | `{symbol, mark_price, timestamp}` |
| **Frequency** | Streaming |
| **Timestamp Semantics** | Server time |
| **Persistence** | `execution.db:hl_mark_prices_raw` |
| **Status** | NEVER POPULATED - 0 rows |

---

## INTERNAL DATA LANES (In-Memory Only)

### Lane 10: M1 → M2 Events

| Field | Value |
|-------|-------|
| **Source** | M1IngestionEngine |
| **Transport** | In-process function call |
| **Event Types** | Normalized TRADE, LIQUIDATION, DEPTH |
| **Schema** | Python dict |
| **Frequency** | Per event |
| **Timestamp Semantics** | Preserved from source |
| **Persistence** | None (in-memory buffers) |
| **Status** | WORKS WHEN COLLECTOR RUNS |

---

### Lane 11: M2 → M4 Primitives

| Field | Value |
|-------|-------|
| **Source** | M2 ContinuityMemoryStore |
| **Transport** | In-process function call |
| **Event Types** | M4PrimitiveBundle |
| **Schema** | Dataclass with 17+ primitive fields |
| **Frequency** | Per snapshot |
| **Timestamp Semantics** | System time |
| **Persistence** | `execution.db:primitive_values` (partial) |
| **Status** | WORKS WHEN COLLECTOR RUNS |

---

### Lane 12: M4 → PolicyAdapter Mandates

| Field | Value |
|-------|-------|
| **Source** | PolicyAdapter |
| **Transport** | In-process function call |
| **Event Types** | Mandate (ENTRY, EXIT, BLOCK) |
| **Schema** | Mandate dataclass |
| **Frequency** | Per cycle |
| **Timestamp Semantics** | System time |
| **Persistence** | `execution.db:mandates` |
| **Status** | WORKS WHEN COLLECTOR RUNS |

---

## SUMMARY TABLE

| Lane | Source | Transport | Status | Evidence |
|------|--------|-----------|--------|----------|
| HL Node Files | HL Node | File I/O | **ACTIVE** | 25GB data today |
| HL Checkpoint | Adapter | File I/O | STALE | Last update 10:11 |
| gRPC Stream | gRPC Server | gRPC | **NOT RUNNING** | Port 50051 closed |
| Binance Liquidations | Binance | WebSocket | **NOT RUNNING** | Last event 08:49 |
| Binance Trades | Binance | WebSocket | **NOT RUNNING** | Collector stopped |
| Binance Depth | Binance | WebSocket | **NOT RUNNING** | Collector stopped |
| HL Positions | HL API | HTTP/WS | **NEVER WORKED** | 0 rows |
| HL Cascade Events | Internal | In-process | **NEVER WORKED** | 0 rows |
| HL Mark Prices | HL API | In-process | **NEVER WORKED** | 0 rows |
| M1 → M2 | Internal | In-process | Works when running | 22M nodes |
| M2 → M4 | Internal | In-process | Works when running | 828K primitives |
| M4 → Mandates | Internal | In-process | Works when running | 10.5K mandates |

---

*This inventory reflects observed data flow, not intended design.*

*Generated: 2026-02-01*
