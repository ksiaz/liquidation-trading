# RUNTIME SYSTEM MAP (LIVE)

**Date:** 2026-02-01
**Purpose:** Document actual running processes and data paths
**Type:** Archaeological Evidence (Observed, Not Assumed)

---

## ACTIVE PROCESSES

| Process | PID | Port | Status | Evidence |
|---------|-----|------|--------|----------|
| gRPC Server | 948783 | 50051 | RUNNING | `ss -tlnp \| grep 50051` |
| Paper Trade Loop | — | — | NOT RUNNING | No process matching `run_paper_trade` |
| Collector Service | — | — | NOT RUNNING | No process matching `collector` |
| HL Node | 820414 | — | RUNNING | Producing data to ~/hl/data |

---

## ACTUAL DATA PATHS (VERIFIED)

### Path 1: HL Node → gRPC Server → NodeSubscriber

```
HL Node Files
├── ~/hl/data/replica_cmds/  (prices, 24GB today)
└── ~/hl/data/node_fills/hourly/  (fills, 1.2GB today)
         │
         ▼
[hl-node-adapter/server.py]  PID 948783
├── readers/price_reader.py
│   └── Reads SetGlobalAction → extracts oracle/mark prices
├── readers/liquidation_reader.py
│   └── Reads node_fills → filters for liquidation field
└── grpc_server.py
    └── Broadcasts on :50051
         │
         ▼
[runtime/node_client/subscriber.py]
└── NodeSubscriber
    ├── StreamPrices() → on_price callback
    └── StreamLiquidations() → on_liquidation callback
```

**VERIFIED:** 570 prices received in 10 seconds via test script.

---

### Path 2: NodeSubscriber → NodeBridge → ingest_observation()

```
NodeSubscriber
│
├── on_price(PriceEvent) ──────────────┐
│                                      ▼
│                          [runtime/node_client/bridge.py]
│                          NodeBridge._handle_price()
│                               │
│                               ▼
│                          ingest_observation(
│                              timestamp=time.time(),
│                              symbol=event.symbol,
│                              event_type='HL_PRICE',
│                              payload={oracle_price, mark_price, ...}
│                          )
│
└── on_liquidation(LiquidationEvent) ──┐
                                       ▼
                          NodeBridge._handle_liquidation()
                               │
                               ▼
                          ingest_observation(
                              timestamp=time.time(),
                              symbol=event.symbol,
                              event_type='LIQUIDATION',
                              payload={p, q, S, ...} (Binance-compatible)
                          )
```

**VERIFIED:** 570 HL_PRICE events reached ingest_observation() via mock ObservationSystem.

---

### Path 3: ingest_observation() → M1 Buffers

```
ingest_observation(event_type='HL_PRICE')
│
└── observation/governance.py:290-291
    │
    └── self._m1.normalize_hl_price(symbol, payload)
        │
        └── observation/internal/m1_ingestion.py:449-491
            │
            ├── self.hl_prices[symbol].append(event)  ← BUFFER (100 max)
            ├── self.latest_hl_prices[symbol] = {...}  ← LATEST CACHE
            └── self.counters['hl_prices'] += 1

ingest_observation(event_type='LIQUIDATION')
│
└── observation/governance.py:282-283
    │
    └── self._m1.normalize_liquidation(symbol, payload)
        │
        └── observation/internal/m1_ingestion.py:162-191
            │
            ├── self.raw_liquidations[symbol].append(event)  ← BUFFER
            └── self.counters['liquidations'] += 1

    Also → governance.py:314-321
        │
        └── self._create_or_update_node_from_liquidation()  ← M2 node creation
        └── self.record_hl_liquidation()  ← Cascade tracking
```

---

## CONSUMER TRACING (CRITICAL)

### Who Reads HL_PRICE Data?

| Method | Location | Called By | Status |
|--------|----------|-----------|--------|
| `get_hl_oracle_price(symbol)` | governance.py:237 | **NOBODY** | DEAD |
| `get_all_hl_prices()` | governance.py:246 | **NOBODY** | DEAD |
| `latest_hl_prices` | m1_ingestion.py:42 | Internal only | STORED BUT UNUSED |

**FINDING: HL_PRICE events are stored in M1 buffers but NO production code reads them.**

### Who Reads LIQUIDATION Data?

| Method | Location | Called By | Status |
|--------|----------|-----------|--------|
| `raw_liquidations[symbol]` | m1_ingestion.py:24 | Tests only | STORED BUT UNUSED |
| `_create_or_update_node_from_liquidation()` | governance.py:415 | ingest_observation | **ACTIVE** |
| `record_hl_liquidation()` | governance.py:162 | ingest_observation | **ACTIVE** |

**FINDING: LIQUIDATION events create M2 nodes and populate cascade tracking. This path IS active.**

---

## BROKEN WIRING (CRITICAL BUG)

### run_paper_trade.py Expects Non-Existent Methods

```python
# Line 266: Calls method that doesn't exist
prices_dict = service._node_bridge.get_latest_prices()  # AttributeError

# Line 268: References key that doesn't exist
metrics["prices_forwarded"]  # KeyError (actual key: prices_ingested)

# Line 270: References key that doesn't exist
metrics["proximity_alerts"]  # KeyError (not in NodeBridge.get_metrics())
```

### service.py Also Broken

```python
# Line 518: Calls method that doesn't exist
node_prices = self._node_bridge.get_latest_prices()  # AttributeError
```

**CONSEQUENCE: USE_HL_NODE=true mode has never worked. The code crashes before data flows.**

---

## WHAT ACTUALLY CONSUMES M1 DATA

### M3 Temporal Engine

```
ingest_observation(event_type='TRADE')
│
└── governance.py:300-307
    │
    └── self._m3.process_trade(...)  ← ONLY TRADES, NOT HL_PRICE
```

**FINDING: M3 only processes TRADE events. HL_PRICE events do NOT flow to M3.**

### M2 Continuity Store

```
ingest_observation(event_type='LIQUIDATION')
│
└── governance.py:314-315
    │
    └── self._create_or_update_node_from_liquidation()
        │
        └── self._m2_store.add_or_update_node(...)  ← M2 node created
```

**FINDING: LIQUIDATION events create M2 nodes. This path IS wired and works.**

### M2 Orderbook State

```
ingest_observation(event_type='DEPTH')
│
└── governance.py:324-332
    │
    └── self._m2_store.update_orderbook_state(...)
```

**FINDING: DEPTH events update M2. But no DEPTH events from HL node (only Binance).**

---

## SUMMARY TABLE

| Data Source | Event Type | Reaches M1 | Consumed By M2 | Consumed By M3 | Consumed By Strategies |
|-------------|------------|------------|----------------|----------------|------------------------|
| HL Node Prices | HL_PRICE | ✅ YES | ❌ NO | ❌ NO | ❌ NO |
| HL Node Liquidations | LIQUIDATION | ✅ YES | ✅ YES (nodes) | ❌ NO | ❌ NO |
| Binance Trades | TRADE | ✅ YES | ✅ YES (associate) | ✅ YES | ✅ YES |
| Binance Liquidations | LIQUIDATION | ✅ YES | ✅ YES (nodes) | ❌ NO | ✅ YES |
| Binance Depth | DEPTH | ✅ YES | ✅ YES | ❌ NO | ✅ YES |

---

## THE ACTUAL STATE

1. **gRPC Server is running** and broadcasting prices/liquidations
2. **NodeSubscriber can receive data** (verified with test)
3. **NodeBridge can forward to ingest_observation()** (verified with mock)
4. **BUT: The paper trading script is broken** and cannot use node mode
5. **AND: HL_PRICE data has no consumers** - it's stored and ignored
6. **LIQUIDATION data DOES work** - creates M2 nodes correctly

---

*This map reflects observed behavior, not intended design.*

*Generated: 2026-02-01*
