# SYSTEM MAP REALITY REPORT

**Date:** 2026-02-01
**Purpose:** Document what is real, assumed, missing, and dangerous to assume "done"
**Type:** Systems Integration Audit (Read-Only)

---

## TERMINATION CHECK

**Can this system be meaningfully evaluated?**

**VERDICT: YES, WITH CAVEATS**

The system CAN be evaluated because:
1. HL node is operational and writing data (`~/hl/data/replica_cmds/`, `~/hl/data/node_fills/`)
2. The gRPC adapter has been tested live (2026-02-01)
3. The NodeBridge → ObservationSystem path has been unit-tested
4. execution.db exists and is 4GB (evidence of substantial runtime)

**CAVEATS:**
- No evidence of full end-to-end HL liquidation → execution flow in production
- M4 cascade primitives untested against real distributions
- Live trading never executed (ghost mode only per CODE_FREEZE.md)

---

## STEP 1 — DATA LANES INVENTORY

### 1.1 Hyperliquid Node (Primary Ground Truth)

| Lane | Transport | Event Types | Schema Shape | Timestamp | Status |
|------|-----------|-------------|--------------|-----------|--------|
| `replica_cmds/` files | File I/O | SetGlobalAction (prices) | `{action: {SetGlobalAction: {prices: [[oracle, mark], ...]}}}` | Block time (ns) | **LIVE** |
| `node_fills/hourly/` files | File I/O | Liquidation fills | `[wallet, {fill with liquidation field}]` | Fill timestamp (ms) | **LIVE** |
| gRPC adapter | gRPC stream | PriceEvent, LiquidationEvent, SyncStatus | Proto (events.proto v1.0.0) | Preserved from source | **LIVE** |

**Evidence of LIVE status:**
- Directory `~/hl/data/replica_cmds/` has 71 session directories as of 2026-02-01
- `node_fills/hourly/` has date directories through 20260129
- Server log shows "Broadcast: prices=570" in last run

### 1.2 Hyperliquid REST/WebSocket API

| Lane | Transport | Event Types | Timestamp | Status |
|------|-----------|-------------|-----------|--------|
| clearinghouseState | HTTPS REST | Position data | Request time | **LIVE** |
| allMids | WebSocket | Mid prices | Server time | **LIVE** |
| activeAssetCtx | WebSocket | OI, funding, volume | Server time | **LIVE** |
| l2Book | WebSocket | Order book snapshots | Server time | **LIVE** |
| webData2 | WebSocket | Position updates (10 wallets) | Server time | **PARTIAL** |
| trades | WebSocket | Trade events | Server time | **LIVE** |

### 1.3 Binance

| Lane | Transport | Event Types | Timestamp | Status |
|------|-----------|-------------|-----------|--------|
| `!forceOrder@arr` | WebSocket | Liquidation events (all symbols) | Event time (ms) | **PARTIAL** |
| `/fapi/v1/premiumIndex` | REST | Funding rates | Request time | **LIVE** |
| `/fapi/v1/klines` | REST | OHLCV candles | Candle time | **LIVE** |

### 1.4 Local Persistence

| Lane | Path | Schema | Status |
|------|------|--------|--------|
| execution.db | `logs/execution.db` | 10+ tables (cycles, m2_nodes, primitives, etc.) | **LIVE** (4GB) |
| HL data store | Via execution_db | Raw position snapshots | **LIVE** |
| Paper trade store | SQLite | Paper trades with context | **PARTIAL** |
| Signal database | `liquidation_data.db` | Legacy signals | **HISTORICAL** |

### 1.5 Lanes in Code But Never Observed Live

| Lane | Location | Status |
|------|----------|--------|
| S3 block indexer | `runtime/hyperliquid/indexer/` | **STUBBED** - Optional wallet discovery |
| Coinglass API | `coinglass_api.py` | **PARTIAL** - Used for research, not production |
| Discord exporter | `scripts/discord_exporter.py` | **EXPERIMENTAL** |
| `abci_state.rmp` parser | PositionStateManager | **UNVERIFIED** - Code exists, never exercised |

---

## STEP 2 — CANONICAL CONTRACT VERIFICATION

### 2.1 M1 Observation Contract

**Definition Location:** `observation/internal/m1_ingestion.py`

**Enforcement Location:** `observation/governance.py:251-335`

#### Canonical Schemas (Binance = Reference)

| Event Type | Fields | Enforced By |
|------------|--------|-------------|
| TRADE | timestamp, symbol, price, quantity, side, base_qty, quote_qty, side_validation | `normalize_trade()` |
| LIQUIDATION | timestamp, symbol, price, quantity, side, base_qty, quote_qty | `normalize_liquidation()` |
| DEPTH | timestamp, symbol, bid_size, ask_size, best_bid_price, best_ask_price, bid_levels, ask_levels | `normalize_depth()` |

#### HL-Specific Schemas (Separate Path)

| Event Type | Fields | Status |
|------------|--------|--------|
| HL_PRICE | timestamp, symbol, oracle_price, mark_price, event_type, exchange | Separate buffer |
| HL_LIQUIDATION | DEPRECATED - Now normalized to LIQUIDATION | Backward compat |
| HL_POSITION | timestamp, symbol, wallet_address, position_size, etc. | Separate buffer |

### 2.2 Source-Dependent Branching STILL PRESENT

| Location | Branching Pattern | Risk |
|----------|-------------------|------|
| `governance.py:419-426` | `normalized_event.get('price') or normalized_event.get('liquidation_price', 0)` | Low - Fallback logic |
| `governance.py:333-339` | `event_type == 'HL_LIQUIDATION'` branch | Low - Deprecated path |
| `m1_ingestion.py` (multiple) | `'exchange': 'HYPERLIQUID'` field in HL events | Medium - Source marker exists |
| `bridge.py:126-134` | `_hl_metadata` dict | Low - Metadata only |

### 2.3 Normalization Status

| Mapping | Status | Evidence |
|---------|--------|----------|
| HL LIQUIDATION → Canonical LIQUIDATION | **IMPLEMENTED** | bridge.py:97-141, tested 2026-02-01 |
| HL side (LONG/SHORT) → order side (BUY/SELL) | **IMPLEMENTED** | bridge.py:108-110 |
| HL_PRICE → HL_PRICE (no Binance equiv) | **SEPARATE** | Intentionally different data type |
| Binance trades → TRADE | **CANONICAL** | Original implementation |

---

## STEP 3 — TEMPORAL AWARENESS & TIMELINE MAP

### 3.1 Development Phases

| Phase | Date Range | Key Events |
|-------|------------|------------|
| Pre-Node | Before 2026-01-05 | M1-M6 pipeline, EP2 strategies, arbitrator, position state machine |
| Code Freeze v1.0 | 2026-01-05 | Hard freeze on core components |
| Execution Layer Freeze | 2026-01-25 | `m6_executor.py`, `controller.py` frozen |
| Node Adapter Work | 2026-01-28 to 2026-02-01 | gRPC adapter, NodeBridge, M1 normalization |
| M1 Normalization | 2026-02-01 | HL liquidations → canonical format |

### 3.2 Component Build Timeline

```
PRE-NODE (Speculative, no live node data):
├── M1-M6 Observation Pipeline
├── EP2 Strategies (Geometry, Kinematics, Absence)
├── EP3 Arbitration
├── EP4 Execution (Ghost)
├── Position State Machine (8 transitions)
├── Risk Monitor (4 invariants)
└── MandateArbitrator (13 theorems)

NODE-AGNOSTIC (Works with any data source):
├── Governance layer (M5)
├── Risk calculations
├── Analytics & metrics
└── Ghost trading infrastructure

POST-NODE - UNVALIDATED (Schema assumed):
├── EP2 Cascade Sniper (cascade_state, proximity)
├── LiquidationBurstAggregator
├── PositionStateManager (abci_state.rmp)
└── M4 Cascade Primitives

POST-NODE - VALIDATED (Tested with live data):
├── PriceReader (2026-02-01)
├── LiquidationReader (2026-02-01)
├── NodeAdapter + gRPC Server (2026-02-01)
├── NodeBridge (2026-02-01)
└── M1 Normalization (2026-02-01)
```

### 3.3 Time Alignment Risks

| Domain | Source | Timestamp Type | Risk |
|--------|--------|----------------|------|
| Node prices | Block time | Nanoseconds | None - authoritative |
| Node liquidations | Fill timestamp | Milliseconds | None - authoritative |
| Binance trades | Event time | Milliseconds | ~100ms network latency |
| Binance liquidations | Event time | Milliseconds | Delayed vs HL node |
| Local system | Wall clock | Seconds | Used for freshness checks |

**Critical Gap:** No explicit time synchronization between HL node time and local wall clock. NodeBridge uses `time.time()` for governance freshness check (bridge.py:77, 100).

---

## STEP 4 — LIVE PATH TRACE

### Trace: HL Liquidation Event → Execution Decision

```
HL Node Files
    │
    │ File I/O: ~/hl/data/node_fills/hourly/{date}/{hour}
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ LiquidationReader.read_fills()                                  │
│ hl-node-adapter/readers/liquidation_reader.py:45-85             │
│ Input: JSON line with [wallet, fill_dict]                       │
│ Output: LiquidationEvent dataclass                              │
│ STATUS: ✅ OBSERVED LIVE (2026-02-01)                           │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ NodeAdapter._emit_event()                                       │
│ hl-node-adapter/adapter.py:120-135                              │
│ Input: LiquidationEvent                                         │
│ Output: Callback invocation                                     │
│ STATUS: ✅ OBSERVED LIVE                                        │
└─────────────────────────────────────────────────────────────────┘
    │
    │ gRPC stream: localhost:50051
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ EventBroadcaster.broadcast_liquidation()                        │
│ hl-node-adapter/grpc_server.py:45-70                            │
│ Input: LiquidationEvent                                         │
│ Output: Proto message to subscribers                            │
│ STATUS: ✅ OBSERVED LIVE (server logs show subscribers)         │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ NodeSubscriber._handle_liquidation()                            │
│ runtime/node_client/subscriber.py:95-115                        │
│ Input: Proto message                                            │
│ Output: LiquidationEvent callback                               │
│ STATUS: ✅ TESTED (mock ObservationSystem)                      │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ NodeBridge._handle_liquidation()                                │
│ runtime/node_client/bridge.py:97-141                            │
│ Input: LiquidationEvent (LONG/SHORT side)                       │
│ Output: ingest_observation(event_type='LIQUIDATION', ...)       │
│ Transform: LONG→SELL, SHORT→BUY                                 │
│ STATUS: ✅ TESTED (unit tests pass)                             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ObservationSystem.ingest_observation()                          │
│ observation/governance.py:251-335                               │
│ Input: timestamp, symbol, event_type='LIQUIDATION', payload     │
│ Output: M1 buffer update, M2 node creation, cascade tracking    │
│ STATUS: ✅ TESTED (unit tests)                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ├────────────────────────────────────────────────────────────────
    │ M1: normalize_liquidation() → raw_liquidations buffer
    │ M2: _create_or_update_node_from_liquidation() → M2 node
    │ Cascade: record_hl_liquidation() → _hl_liquidation_timestamps
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ _get_snapshot() → _compute_primitives_for_symbol()              │
│ observation/governance.py:513-1082                              │
│ Input: M1 buffers, M2 nodes, M3 temporal state                  │
│ Output: M4PrimitiveBundle (25+ primitives)                      │
│ STATUS: 🟡 LIVE BUT UNVERIFIED (computation runs, real          │
│         distributions unknown)                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ PolicyAdapter.generate_mandates()                               │
│ runtime/policy_adapter.py:45-180                                │
│ Input: ObservationSnapshot, symbol, timestamp                   │
│ Output: List[Mandate] from enabled strategies                   │
│ STATUS: 🟡 LIVE BUT UNVERIFIED (strategies run, cascade_sniper  │
│         needs real proximity data)                              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ MandateArbitrator.arbitrate()                                   │
│ runtime/arbitration/arbitrator.py:25-120                        │
│ Input: Set[Mandate]                                             │
│ Output: Single Action per symbol                                │
│ STATUS: ✅ LIVE & VERIFIED (13 theorems, deterministic)         │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ExecutionController.execute()                                   │
│ runtime/executor/controller.py:45-200                           │
│ Input: Action from arbitrator                                   │
│ Output: Position state change                                   │
│ STATUS: ✅ LIVE & VERIFIED (13 theorems, canonical, frozen)     │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ GhostExchangeAdapter / OrderExecutor                            │
│ execution/ep4_ghost_adapter.py (ghost mode)                     │
│ runtime/exchange/order_executor.py (live mode)                  │
│ Input: OrderRequest                                             │
│ Output: Simulated fill (ghost) or real order (live)             │
│ STATUS: 🔴 GHOST ONLY - Live execution never exercised          │
└─────────────────────────────────────────────────────────────────┘
```

### Path Verification Summary

| Hop | Status | Last Verified |
|-----|--------|---------------|
| Node Files → LiquidationReader | ✅ LIVE | 2026-02-01 |
| LiquidationReader → NodeAdapter | ✅ LIVE | 2026-02-01 |
| NodeAdapter → gRPC Server | ✅ LIVE | 2026-02-01 |
| gRPC Server → NodeSubscriber | ✅ TESTED | 2026-02-01 |
| NodeSubscriber → NodeBridge | ✅ TESTED | 2026-02-01 |
| NodeBridge → ObservationSystem | ✅ TESTED | 2026-02-01 |
| M1 → M4 Primitives | 🟡 UNVERIFIED | Never with HL data |
| M4 → PolicyAdapter | 🟡 UNVERIFIED | Never with HL data |
| PolicyAdapter → Arbitrator | ✅ VERIFIED | Theorem-proven |
| Arbitrator → ExecutionController | ✅ VERIFIED | Theorem-proven |
| ExecutionController → Live Exchange | 🔴 NEVER EXERCISED | Ghost only |

---

## STEP 5 — SYSTEM STATE CLASSIFICATION

| Subsystem | Status | Evidence |
|-----------|--------|----------|
| HL Node Data Ingestion | ✅ LIVE & VERIFIED | 570 prices broadcast, reader tested |
| gRPC Adapter | ✅ LIVE & VERIFIED | Server logs, handshake works |
| NodeBridge → M1 | ✅ LIVE & VERIFIED | Unit tests pass, normalization works |
| M1 Ingestion (Binance) | ✅ LIVE & VERIFIED | 4GB execution.db |
| M1 Ingestion (HL) | 🟡 LIVE BUT UNVERIFIED | Code works, never full pipeline |
| M2 Continuity Store | 🟡 LIVE BUT UNVERIFIED | Creates nodes, real behavior unknown |
| M3 Temporal Engine | ✅ LIVE & VERIFIED | Candle aggregation tested |
| M4 Primitives (Tier A) | ✅ LIVE & VERIFIED | 17 modules, unit tested |
| M4 Cascade Primitives | 🟠 PARTIAL | Code exists, real distributions unknown |
| M5 Governance | ✅ LIVE & VERIFIED | Query schemas enforced |
| EP2 Strategies | 🟡 LIVE BUT UNVERIFIED | Run in ghost, no real edge validation |
| EP2 Cascade Sniper | 🟠 PARTIAL | Needs real proximity data |
| Arbitration | ✅ LIVE & VERIFIED | 13 theorems proven |
| Execution Controller | ✅ LIVE & VERIFIED | 13 theorems, frozen |
| Risk Governors | 🟡 LIVE BUT UNVERIFIED | Complete code, no production stress |
| Order Executor | 🟡 LIVE BUT UNVERIFIED | E1-E4 hardenings, ghost only |
| Position Reconciliation | 🔴 NOT CONNECTED | Code exists, never used |
| Live Exchange Execution | 🔴 NOT CONNECTED | Ghost mode only |
| PositionStateManager (abci_state) | 🔴 NOT CONNECTED | Code exists, file never parsed |
| Metrics/Latency Tracking | 🟡 LIVE BUT UNVERIFIED | 7-stage profiling exists |
| Paper Trade Persistence | 🟡 LIVE BUT UNVERIFIED | SQLite store works |

---

## STEP 6 — INTEGRATION RISKS & BLOCKERS

### TIER 1 — CRITICAL (Could cause loss of capital)

| Risk | Impact | Location | Mitigation Status |
|------|--------|----------|-------------------|
| **Live execution never tested** | Full capital exposure on first trade | Order executor | CODE_FREEZE prevents live |
| **Position reconciliation unused** | Ghost positions, orphan orders | `reconciliation.py` | Code exists, not wired |
| **Stop placement after fill** | Unprotected entries on network failure | `order_executor.py:E4` | Code exists, not live tested |
| **Cascade primitives untested** | Wrong proximity thresholds | M4 cascade modules | Need 90+ days data (HLP12) |

### TIER 2 — HIGH (Could cause incorrect decisions)

| Risk | Impact | Location | Mitigation Status |
|------|--------|----------|-------------------|
| **HL → M4 path untested** | Primitives may not trigger correctly | Full pipeline | Only unit tested |
| **Timebase mismatch** | Freshness checks may drop good data | bridge.py uses wall clock | Needs validation |
| **M2 node decay rates** | Wrong zone persistence | `m2_continuity_store.py` | Hardcoded, not calibrated |
| **Strategy thresholds hardcoded** | No empirical basis | All EP2 strategies | HLP23 incomplete (10%) |

### TIER 3 — MEDIUM (Could cause operational issues)

| Risk | Impact | Location | Mitigation Status |
|------|--------|----------|-------------------|
| **Partial HL_LIQUIDATION path** | Duplicate events possible | governance.py:333-339 | Deprecated but not removed |
| **No sequence gap detection** | Missing events on disconnect | NodeSubscriber | Not implemented |
| **No full state snapshot on reconnect** | Stale state after network failure | HLP16 | 30% implemented |
| **Database retention not enforced** | Disk exhaustion | execution.db (4GB) | No pruning |

### TIER 4 — LOW (Could cause confusion)

| Risk | Impact | Location | Mitigation Status |
|------|--------|----------|-------------------|
| **Source markers in HL events** | Code could branch on source | `'exchange': 'HYPERLIQUID'` | Low risk, metadata only |
| **_hl_metadata not documented** | Future maintainer confusion | bridge.py | Not in schema docs |
| **Frozen code not clearly marked** | Accidental modification | Multiple files | CODE_FREEZE.md exists |

---

## FINAL SUMMARY

### What is REAL

1. **HL node is operational** — Files written, prices readable
2. **gRPC adapter works** — 570+ prices broadcast, handshake verified
3. **M1 normalization works** — HL liquidations → canonical format
4. **Arbitrator is proven** — 13 theorems, deterministic
5. **Execution controller is proven** — 13 theorems, frozen
6. **4GB of execution.db** — Substantial runtime history

### What is ASSUMED

1. **M4 primitives produce correct signals** — Logic exists, real distributions unknown
2. **Cascade thresholds are correct** — No empirical validation (HLP23 at 10%)
3. **Strategy edge exists** — Ghost tested, no real PnL
4. **Risk governors work under stress** — Complete code, no production pressure
5. **Wallet proximity calculations are accurate** — Formula exists, never exercised

### What is MISSING

1. **Live exchange execution** — Ghost mode only (per CODE_FREEZE.md)
2. **Position reconciliation** — Code exists, not wired
3. **Full HL → execution pipeline test** — Unit tested only
4. **90+ days of position data** — Required for wallet tracking (HLP12)
5. **Threshold discovery** — HLP23 at 10%
6. **Failure recovery** — HLP16 at 30%

### What is DANGEROUS to Assume "Done"

| Component | Danger |
|-----------|--------|
| **Cascade Sniper strategy** | Thresholds assumed, not discovered |
| **Position sizing** | Missing volatility adjustment, consecutive loss handling |
| **Stop placement** | E4 hardening exists but never live tested |
| **M4 cascade primitives** | Built to spec, spec was assumed |
| **Live order execution** | Zero live orders ever placed |

---

## MINIMUM CONDITIONS TO CONTINUE

Before any live trading:

1. **Full pipeline test** — HL node → M1 → M4 → Strategy → Arbitrator → Ghost execution
2. **Position reconciliation wired** — Exchange is source of truth
3. **Stop placement verified** — E4 hardening under network stress
4. **Threshold discovery** — At minimum, conservative defaults from HLP23
5. **Paper trading criteria met** — 7 days OR 50 trades, zero crashes (HLP20)
6. **CODE_FREEZE lifted** — With logged evidence per freeze policy

---

**END OF REPORT**

*This document was generated from code inspection and file system observation only. No modifications were made to any code.*
