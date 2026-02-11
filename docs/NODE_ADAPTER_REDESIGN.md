# Node Data Exposure Re-Design

## Design Note — 2026-02-01

---

## STEP 1 — ABANDONMENT OF CURRENT PATH

### What the current path is:

The existing implementation in `runtime/hyperliquid/node_adapter/` consists of:

1. **DirectIntegration** - reads `replica_cmds/` files synchronously inside async methods
2. **PositionStateManager** - reads `abci_state.rmp` (100+ MB msgpack) with partial thread pool usage
3. **ObservationBridge** - attempts to coordinate data flow to observation system
4. **TradeFileReader** - tails `node_fills/` for liquidation events
5. **StreamingStateParser** - parses position state with blocking I/O

All components run **in-process** with the main trading event loop. Multiple modules access node files independently.

### The current approach is abandoned.

### Why it is wrong:

| Problem | Evidence |
|---------|----------|
| **Tight coupling to node internals** | Code directly references `replica_cmds/session_*/date/block_file` structure, `abci_state.rmp` msgpack schema, `node_fills/hourly/YYYYMMDD/HH` paths |
| **Duplicated parsing across modules** | `DirectIntegration._process_block()` parses SetGlobalAction. `StreamingStateParser.iter_positions_batch()` parses positions. `TradeFileReader.read_new_liquidations()` parses fills. Three parsers, three failure points. |
| **Schema drift risk** | No canonical event definition. Each consumer interprets raw data differently. If HL node format changes, breakage is scattered and silent. |
| **Inability to replay/debug** | Data is consumed and transformed immediately. Cannot answer "what did the system see at time T?" |
| **Silent data inconsistency risk** | `_process_file()` reads files synchronously. If read fails partway, position in file is corrupted. No checkpointing. |
| **Inability to fan out safely** | ObservationBridge, CollectorService, and UIServer all need prices. Currently solved by passing object references and hoping state is synchronized. |
| **Event loop blocking** | Synchronous `open()`, `msgpack.unpack()`, directory iteration all block the async event loop. API server becomes unresponsive (29-second timeouts observed). |

---

## STEP 2 — REFRAME THE PROBLEM

### Problem statement:

**We need to expose Hyperliquid node data to many independent parts of the system, safely, consistently, and without leaking node-specific complexity.**

### Single source of truth:

One adapter process reads the node. All consumers receive data from this adapter. No exceptions.

### Consumers identified:

| Consumer | Needs |
|----------|-------|
| Observation Layer (M1-M5) | Price events |
| Alpha Logic (EFFCS, Cascade Sniper) | Prices, liquidation events |
| Risk / Liquidation Distance | Position states, prices |
| Governance | Health metrics, sync status |
| Execution Sanity | Price freshness |
| Analytics / Logging | All events (audit trail) |
| UI Server | Prices, liquidations, health |

**Count: 7 independent consumers.**

### Required guarantees:

- **Ordering**: Events emitted in block order. Consumers process in order received.
- **Freshness**: Prices must reflect latest block. Stale = unsafe.
- **Completeness**: No silent drops. If adapter fails, consumers know.
- **Consistency**: All consumers see identical event stream.

### What must never happen:

- Trading on stale price (execution uses price from 10 blocks ago)
- Divergent views (risk sees position closed, execution sees it open)
- Hidden coupling (alpha logic imports node-specific parser)
- Silent corruption (file read fails, system continues with partial data)

---

## STEP 3 — INVENTORY REALITY

### What the node actually provides:

| Feed | Content | Update Frequency |
|------|---------|------------------|
| `replica_cmds/` | SetGlobalAction with oracle prices for 228 assets | Every block (~500ms) |
| `node_fills/hourly/` | Trade fills including `forceOrder` liquidations | Per trade |
| `abci_state.rmp` | Full state snapshot: positions, margin, leverage | Updated per block |
| `node_trades/` | Raw trade data | Per trade |

### What the system actually expects:

| Expectation | Current Source |
|-------------|----------------|
| Normalized prices (symbol, price, timestamp_ns) | SetGlobalAction parsing |
| Liquidation events (symbol, side, size, price, wallet) | node_fills parsing |
| Position proximity (wallet, symbol, liq_price, distance) | abci_state.rmp parsing |
| Sync status (blocks behind, last update) | File modification times |

### Explicitly out of scope at this stage:

- Historical backfill (correctness first, history later)
- Order book depth (not available from node)
- Funding rates (using Binance API, separate concern)
- Trade-by-trade flow analysis (not required for current strategies)
- Wallet discovery heuristics (alpha concern, not data layer)

---

## STEP 4 — ARCHITECTURAL OPTIONS

### Option A: In-Process Adapter with Dedicated Thread Pool

**Description:**
Keep adapter in same process but isolate all blocking I/O to a dedicated thread pool. Main event loop receives events via thread-safe queue.

**Data flow:**
```
[Thread Pool]              [Main Event Loop]
  │                              │
  ├─ read files ──────────────► queue.put(event)
  │                              │
  │                        queue.get() ──► consumers
```

**Pros:**
- No IPC overhead
- Simpler deployment (one process)
- Shared memory access

**Cons:**
- Thread pool exhaustion affects whole process
- GIL contention for CPU-bound parsing
- Single point of failure
- Cannot restart adapter without restarting trading

**Failure modes:**
- Thread pool deadlock blocks entire system
- Memory corruption in parser affects trading
- OOM in parser kills trading process

**Assessment:** Acceptable for prototypes. Not appropriate here — system is past prototype stage and needs isolation.

---

### Option B: Out-of-Process Adapter with gRPC Streaming

**Description:**
Standalone adapter process reads node, emits canonical events over gRPC streams. Trading process subscribes to streams. No direct node access from trading process.

**Data flow:**
```
[HL Node Files]
       │
       ▼
[Adapter Process]
  ├── reads replica_cmds
  ├── reads node_fills
  ├── parses, normalizes
  └── emits via gRPC streams
           │
           ▼
    ┌──────┴──────┐
    │ gRPC Server │
    └──────┬──────┘
           │
    ┌──────┴──────────────┐
    │                     │
[Trading Process]    [Analytics Process]
    │                     │
 subscribers           subscribers
```

**Pros:**
- Complete isolation (different process, different memory space)
- Can restart adapter without losing trading state
- gRPC provides typing, backpressure, multiplexing
- Natural fan-out to multiple consumers
- Can record stream for replay
- Binance adapter can emit same event types later

**Cons:**
- IPC latency (~1-5ms per event)
- More operational complexity (two processes)
- Schema must be defined upfront (proto files)
- Requires gRPC dependency

**Failure modes:**
- Adapter crash: Consumers detect disconnect, enter safe mode
- Network partition: gRPC timeout, consumers know
- Slow consumer: Backpressure handled by gRPC

**Assessment:** Correct choice for this system. Matches complexity level and multi-consumer requirement.

---

### Option C: Shared Memory / Memory-Mapped Files

**Description:**
Adapter writes events to memory-mapped file. Consumers read from same mapped region. Lock-free ring buffer pattern.

**Data flow:**
```
[Adapter Process]
       │
       ▼
[Shared Memory Region]
       │
       ├──► Consumer 1
       ├──► Consumer 2
       └──► Consumer 3
```

**Pros:**
- Lowest latency (sub-microsecond)
- Zero copy

**Cons:**
- Complex synchronization
- Platform-specific
- Hard to debug
- No built-in schema enforcement
- Replay requires separate mechanism

**Failure modes:**
- Memory corruption propagates to all consumers
- Reader/writer race conditions
- No backpressure

**Assessment:** Overkill for this use case. Latency is not the constraint — correctness is.

---

## STEP 5 — SELECTED APPROACH

### Recommendation: Option B — Out-of-Process Adapter with gRPC Streaming

### Justification:

| Requirement | How Option B Addresses It |
|-------------|---------------------------|
| **Multiple consumers** | gRPC streaming supports N subscribers. Each receives same ordered events. Natural fan-out. |
| **Future Binance integration** | Binance adapter emits same `MarketPriceEvent` type. Trading process doesn't know/care about source. |
| **Replay/debug needs** | gRPC stream can be recorded to file. Replay = re-emit same events. Answer "what did system see at T?" |
| **Schema stability** | Proto files define contract. Breaking change = compilation failure. No silent drift. |
| **Operational safety** | Adapter crash: trading process detects, enters safe mode. Adapter restart: no trading state lost. Clear failure boundaries. |

### Why not Option A:

The current blocking I/O issues demonstrate that in-process isolation is insufficient. Thread pool exhaustion, GIL contention, and shared failure modes are unacceptable for a system handling real capital.

### Why not Option C:

We are not latency-constrained at the microsecond level. The complexity cost of shared memory is not justified. Correctness and debuggability outweigh raw speed.

---

## STEP 6 — MINIMAL SCOPE DEFINITION

### First version will:

| Included | Rationale |
|----------|-----------|
| Read `replica_cmds/` | Source of oracle prices. Required for all trading. |
| Read `node_fills/hourly/` | Source of liquidation events. Required for cascade detection. |
| Emit `MarketPriceEvent` | Symbol, oracle_price, timestamp_ns, block_height |
| Emit `LiquidationEvent` | Symbol, side, size_usd, price, wallet, timestamp_ns |
| Emit `SyncStatusEvent` | Blocks behind, last block time, adapter health |
| Expose gRPC streaming endpoint | One endpoint per event type |

### First version will NOT:

| Excluded | Rationale |
|----------|-----------|
| `abci_state.rmp` parsing | Too complex for v1. Position proximity is valuable but not critical path. Add in v2. |
| Position events | Depends on abci_state. Deferred. |
| Order events | Not needed for current strategies. |
| Historical backfill | Forward correctness first. History later. |
| Any trading logic | Adapter must remain boring. |
| Any filtering/aggregation | Raw events only. Consumers aggregate. |
| Wallet discovery | Alpha concern. Does not belong in data layer. |

### Adapter is explicitly forbidden from:

- Making trading decisions
- Filtering events based on symbol or size
- Aggregating events (e.g., OHLC candles)
- Holding state beyond file positions
- Importing any trading system code
- Accessing Binance or any external API

---

## STEP 7 — PHASED EXECUTION PLAN

### Phase 0: Preconditions

**Goal:** Verify node data accessibility and define event schemas.

**Tasks:**
- Confirm `replica_cmds/` and `node_fills/` paths are accessible
- Document current file formats with examples
- Draft proto schema for 3 event types
- Identify gRPC library (grpcio)

**Success criteria:**
- Can manually read and parse latest block file
- Proto schema compiles
- No ambiguity in field definitions

**Not done yet:**
- No adapter code
- No server implementation
- No client code

---

### Phase 1: Standalone Adapter Process

**Goal:** Adapter reads node files and prints canonical events to stdout.

**Tasks:**
- Create `hl-node-adapter/` directory (separate from trading system)
- Implement file readers for replica_cmds and node_fills
- Implement parsers that emit typed events
- Print events as JSON to stdout

**Success criteria:**
- Run adapter, see stream of events in terminal
- Events match expected schema
- Can Ctrl+C and restart without losing position (checkpointing)

**Not done yet:**
- No gRPC server
- No network communication
- Trading system unchanged

---

### Phase 2: Event Schema Finalization

**Goal:** Lock down proto definitions before any integration.

**Tasks:**
- Finalize `events.proto` with all v1 event types
- Generate Python bindings
- Write schema documentation
- Add schema version field

**Success criteria:**
- Proto compiles without warnings
- Generated code imports cleanly
- Schema reviewed and frozen

**Not done yet:**
- No gRPC server
- No client integration

---

### Phase 3: gRPC Server Implementation

**Goal:** Adapter serves events over gRPC streaming.

**Tasks:**
- Implement gRPC server in adapter process
- One streaming RPC per event type
- Add health check RPC
- Add metrics (events emitted, latency, errors)

**Success criteria:**
- Can connect with `grpcurl` and see events streaming
- Multiple clients can connect simultaneously
- Disconnecting client doesn't affect others

**Not done yet:**
- Trading system still uses old node_adapter
- No production traffic

---

### Phase 4: First Consumer Hookup

**Goal:** Trading system receives events from adapter instead of reading files directly.

**Tasks:**
- Create `runtime/node_client/subscriber.py`
- Subscribe to MarketPriceEvent and LiquidationEvent streams
- Wire to ObservationBridge (replace direct file reads)
- Remove old `node_adapter/` usage from critical path

**Success criteria:**
- Trading system receives prices from adapter
- No direct file access from trading process
- API server responds instantly (no blocking I/O)
- Liquidation events flow through to cascade detection

**Not done yet:**
- Position state (v2)
- Full removal of old code (deprecation period)
- Production deployment

---

## Summary

| Item | Decision |
|------|----------|
| Current approach | **Abandoned** — blocking I/O, tight coupling, no fan-out |
| Architecture | Out-of-process adapter with gRPC streaming |
| V1 scope | Prices + liquidations only. No positions. |
| Event types | MarketPriceEvent, LiquidationEvent, SyncStatusEvent |
| Phases | 5 phases, correctness-first progression |

**Next action:** Execute Phase 0 (preconditions and proto schema).
