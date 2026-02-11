# System Map with Temporal Context

**Date:** 2026-02-01
**Purpose:** Document what exists, when it was built, and under what assumptions
**Author:** System Archaeologist (Claude)

---

## Preamble

This system was developed before the Hyperliquid node was fully operational. As a result:
- Some components were designed speculatively
- Some were implemented without live node data
- Some may be correct but never validated against reality
- There is no single timestamp that cleanly separates "node-less" vs "node-backed" development

This document makes these facts explicit rather than attempting to resolve them.

---

## STEP 1: Component Inventory (AS-IS)

### 1.1 Data Ingestion Layer

| Component | Location | Responsibility | Inputs | Outputs | Requires Live Node? |
|-----------|----------|----------------|--------|---------|---------------------|
| NodeAdapter | `hl-node-adapter/adapter.py` | Read HL node files, emit JSON events | `replica_cmds/`, `node_fills/` files | PriceEvent, LiquidationEvent | YES |
| AdapterServer | `hl-node-adapter/server.py` | Serve events over gRPC | NodeAdapter events | gRPC streams | YES |
| PriceReader | `hl-node-adapter/readers/price_reader.py` | Parse SetGlobalAction for oracle prices | Block files from `replica_cmds/` | PriceEvent dataclass | YES |
| LiquidationReader | `hl-node-adapter/readers/liquidation_reader.py` | Parse node_fills for liquidations | Hourly fill files | LiquidationEvent dataclass | YES |
| NodeSubscriber | `runtime/node_client/subscriber.py` | Subscribe to gRPC streams | gRPC server address | Callbacks with typed events | YES |
| NodeBridge | `runtime/node_client/bridge.py` | Convert gRPC events to M1 format | NodeSubscriber events | `ingest_observation()` calls | YES |
| BinanceCollector | `runtime/binance/collector.py` | Binance WebSocket ingestion | Binance WebSocket | Trade/orderbook events | NO (uses Binance) |
| HyperliquidClient | `runtime/hyperliquid/client.py` | REST/WebSocket for HL API | HL API endpoints | Position, trade data | NO (uses API) |

### 1.2 Observation System (M1-M6)

| Component | Location | Responsibility | Inputs | Outputs | Requires Live Node? |
|-----------|----------|----------------|--------|---------|---------------------|
| M1 Ingestion | `observation/internal/m1_ingestion.py` | Raw event normalization | Exchange events | Normalized observations | NO |
| M2 Continuity | `memory/m2_*.py` (multiple) | Event continuity, node tracking | M1 events | Persistent state | NO |
| M3 Temporal | `observation/internal/m3_temporal.py` | Temporal ordering, candles | M2 state | Time-ordered data | NO |
| M4 Primitives | `memory/m4_*.py` (17 modules) | Contextual primitives | M3 data | M4PrimitiveBundle | NO |
| M5 Governance | `memory/m5_*.py` | Query schemas, whitelist | M4 primitives | ObservationSnapshot | NO |
| M6 Mandate | `memory/m6_*.py` | Mandate evaluation | M5 snapshots | Mandate candidates | NO |

### 1.3 External Policy Layer (EP1-4)

| Component | Location | Responsibility | Inputs | Outputs | Requires Live Node? |
|-----------|----------|----------------|--------|---------|---------------------|
| EP1 Oracle Volatility | `external_policy/ep1_oracle_volatility.py` | Volatility thresholds | Price data | Volatility signals | NO (STUB) |
| EP2 Geometry Strategy | `external_policy/ep2_strategy_geometry.py` | Zone geometry signals | M4PrimitiveBundle | Mandate proposals | NO |
| EP2 Kinematics Strategy | `external_policy/ep2_strategy_kinematics.py` | Post-liquidation inventory | M4PrimitiveBundle | Mandate proposals | NO |
| EP2 Absence Strategy | `external_policy/ep2_strategy_absence.py` | Structural absence | M4PrimitiveBundle | Mandate proposals | NO |
| EP2 Cascade Sniper | `external_policy/ep2_strategy_cascade_sniper.py` | Liquidation cascade | M4PrimitiveBundle + proximity | Mandate proposals | PARTIAL (enhanced with node) |
| EP3 Arbitration | `external_policy/ep3_arbitration.py` | Mandate resolution | Mandate list | Single mandate per symbol | NO |
| EP4 Execution | `external_policy/ep4_execution.py` | 6-step execution | Arbitrated mandates | Exchange actions | NO |

### 1.4 Runtime Execution

| Component | Location | Responsibility | Inputs | Outputs | Requires Live Node? |
|-----------|----------|----------------|--------|---------|---------------------|
| MandateArbitrator | `runtime/arbitration/arbitrator.py` | Deterministic mandate resolution | Mandate list | Single Action per symbol | NO |
| ExecutionController | `runtime/executor/controller.py` | Theorem-verified execution | Arbitrated actions | Position changes | NO |
| PositionStateMachine | `runtime/position/state_machine.py` | Position lifecycle (8 transitions) | Execution requests | State transitions | NO |
| RiskMonitor | `runtime/risk/monitor.py` | Risk invariant enforcement | Account state | Protective mandates | NO |
| CollectorService | `runtime/collector/service.py` | Main runtime loop driver | All data sources | System orchestration | PARTIAL |

### 1.5 Monitoring & Analytics

| Component | Location | Responsibility | Inputs | Outputs | Requires Live Node? |
|-----------|----------|----------------|--------|---------|---------------------|
| HealthDashboard | `runtime/monitoring/health_dashboard.py` | Real-time health | System metrics | Health status | NO |
| LatencyProfiler | `runtime/monitoring/latency_profiler.py` | 7-stage latency | Execution events | Latency metrics | NO |
| MetricsCollector | `runtime/analytics/metrics_collector.py` | System metrics | All components | Aggregated metrics | NO |
| GhostPositionTracker | `execution/ep4_ghost_tracker.py` | Paper trading | Execution events | Simulated positions | NO |

---

## STEP 2: Temporal Classification

### PRE-NODE (Built before working node existed)

| Component | Evidence | Assumptions Made |
|-----------|----------|------------------|
| M1-M6 Observation Pipeline | Code freeze 2026-01-05, no node references | Events come from Binance-style WebSocket |
| EP2 Geometry Strategy | Zone geometry primitives from Binance data | Price zones detectable from trade stream |
| EP2 Kinematics Strategy | Post-liquidation detection | Liquidations visible in trade flow |
| EP2 Absence Strategy | Structural absence detection | Duration patterns from exchange data |
| MandateArbitrator | 13 theorems, no node data types | Authority hierarchy sufficient |
| ExecutionController | 13 theorems, frozen 2026-01-25 | Position state machine covers all cases |
| PositionStateMachine | 8 transitions defined pre-node | Transition rules are exchange-agnostic |
| RiskMonitor | 4 invariants, exchange-agnostic | Risk logic doesn't need node data |

### NODE-AGNOSTIC (Does not depend on node data directly)

| Component | Reason |
|-----------|--------|
| Governance layer (M5) | Enforces rules on any data source |
| Risk calculations | Based on position state, not data source |
| Position state machine | Transition rules are exchange-independent |
| Analytics & metrics | Instrument any execution path |
| Ghost trading | Simulates without live exchange |

### POST-NODE (UNVALIDATED) - Built after node work began, not validated with live data

| Component | Evidence | Validation Status |
|-----------|----------|-------------------|
| EP2 Cascade Sniper | References `cascade_state`, `proximity` | Schema assumed, not validated |
| LiquidationBurstAggregator | Aggregates `HL_LIQUIDATION` events | Format assumed from node_fills parsing |
| PositionStateManager | Designed for `abci_state.rmp` | File format documented but not exercised |
| ObservationBridge (old) | `adapter_pb2` references | Different proto schema than current |

### POST-NODE (VALIDATED) - Built and tested against live node data

| Component | Validation Date | Evidence |
|-----------|-----------------|----------|
| PriceReader | 2026-02-01 | Tested with live `replica_cmds` files |
| LiquidationReader | 2026-02-01 | Parsed real `node_fills` data |
| NodeAdapter | 2026-02-01 | Streamed 6080 prices in 12 seconds |
| gRPC Server | 2026-02-01 | Handshake verified, status RPC works |
| NodeBridge | 2026-02-01 | 75 HL_PRICE events ingested to mock ObservationSystem |
| Asset Mapping | 2026-02-01 | 228 assets verified from SetGlobalAction |

### TEMPORAL STATUS: UNKNOWN

| Component | Uncertainty |
|-----------|-------------|
| M4 Cascade Primitives | Built to spec, but spec was assumed |
| Proximity calculations | Algorithm exists, real data ranges unknown |
| Leverage concentration | Formula exists, real distributions unknown |
| OI bias detection | Logic exists, real patterns unobserved |

---

## STEP 3: Data Flow Map (Real, Not Intended)

### 3.1 Currently Exercised Flows

| Source | Destination | Data Structure | Source Type | Exercised? |
|--------|-------------|----------------|-------------|------------|
| HL Node Files | PriceReader | JSON lines (SetGlobalAction) | REAL | YES |
| HL Node Files | LiquidationReader | JSON lines (fills with liquidation field) | REAL | YES |
| PriceReader | NodeAdapter | PriceEvent dataclass | REAL | YES |
| LiquidationReader | NodeAdapter | LiquidationEvent dataclass | REAL | YES |
| NodeAdapter | gRPC Server | Proto messages | REAL | YES |
| gRPC Server | NodeSubscriber | gRPC stream | REAL | YES |
| NodeSubscriber | NodeBridge | PriceEvent/LiquidationEvent | REAL | YES |
| NodeBridge | ObservationSystem.ingest_observation() | Dict payload | REAL | YES (tested) |
| Binance WS | M1 Ingestion | Trade/orderbook events | REAL | YES |

### 3.2 Partially Exercised Flows

| Source | Destination | Data Structure | Source Type | Exercised? |
|--------|-------------|----------------|-------------|------------|
| M1 | M2-M6 pipeline | Observation events | REAL (Binance) | YES |
| M4 | EP2 Strategies | M4PrimitiveBundle | COMPUTED | YES (from Binance) |
| EP2 | Arbitrator | Mandate proposals | COMPUTED | YES |
| Arbitrator | Executor | Action | COMPUTED | YES (ghost mode) |

### 3.3 Not Currently Exercised

| Source | Destination | Data Structure | Source Type | Exercised? |
|--------|-------------|----------------|-------------|------------|
| NodeBridge | Full M1-M6 pipeline | HL_PRICE, HL_LIQUIDATION | REAL | NO (just tested with mock) |
| PositionStateManager | Cascade Sniper | Proximity data | ASSUMED | NO |
| abci_state.rmp | Position parsing | Msgpack binary | ASSUMED | NO |
| Executor | Live Hyperliquid | Order API | REAL | NO (ghost only) |

---

## STEP 4: Development-Time Assumptions

### Assumptions Inferred from Code

| Assumption | Location | Basis |
|------------|----------|-------|
| SetGlobalAction contains 228 assets in fixed order | `asset_mapping.py` | Observed from live data |
| Price is `[oracle_price, mark_price]` tuple | `price_reader.py` | Observed from live data |
| node_fills format is `[wallet, fill_dict]` | `liquidation_reader.py` | Observed from live data |
| Fill has `liquidation` key when forced | `liquidation_reader.py` | Observed from live data |
| Block height is sequential and monotonic | `checkpoint.py` | Assumed, not verified |
| Hourly files roll at hour boundaries | `liquidation_reader.py` | Assumed from naming |
| Session directories are timestamped | `price_reader.py` | Observed from directory names |

### Assumptions NOT Yet Verified

| Assumption | Risk If Wrong |
|------------|---------------|
| All 228 assets always present in SetGlobalAction | Missing prices for some assets |
| Liquidation events always have `markPx` | NullPointer on mark price access |
| Fill IDs are globally unique | Duplicate detection fails |
| Files are not rotated mid-write | Partial reads cause corruption |
| Timestamps are in UTC | Time zone bugs in ordering |

### Assumed Event Frequency

| Event Type | Assumed Frequency | Basis |
|------------|-------------------|-------|
| Price updates | Every block (~500ms) | Observed from block files |
| Liquidations | Variable, clustered | Observed from hour files |
| Session rotation | On node restart | Observed from directory structure |
| Hourly file rotation | Every hour | Naming convention |

### Assumed Ordering Guarantees

| Guarantee | Assumed? | Verified? |
|-----------|----------|-----------|
| Prices ordered by block height | YES | YES (within file) |
| Prices ordered across files | YES | NO |
| Liquidations ordered by fill_id | YES | NO |
| Liquidations ordered by timestamp | YES | NO |
| Cross-stream ordering | NO | N/A |

---

## STEP 5: System Loop Status

### Is there a closed runtime loop today?

**PARTIAL**

### Where does data currently stop?

```
HL Node Files
    ↓ (VALIDATED)
PriceReader/LiquidationReader
    ↓ (VALIDATED)
gRPC Server
    ↓ (VALIDATED)
NodeBridge
    ↓ (TESTED with mock)
ObservationSystem.ingest_observation()
    ↓ (NOT YET EXERCISED with node data)
M1-M6 Pipeline
    ↓ (EXERCISED with Binance data only)
EP2 Strategies
    ↓ (EXERCISED with Binance data only)
Executor
    ↓ (EXERCISED in ghost mode only)
[STOP - No live execution]
```

### Which parts can run end-to-end without node data?

- Full Binance → M1 → M6 → Strategies → Arbitration → Execution (Ghost) loop
- All monitoring and analytics
- Position state machine transitions
- Risk invariant enforcement

### Which parts require node data to be meaningful?

- Cascade Sniper proximity calculations (enhanced mode)
- HL_PRICE and HL_LIQUIDATION event types in M1
- Position proximity for large wallets
- Ground-truth liquidation detection (vs derived from trades)

---

## STEP 6: Timeline Summary (Approximate)

Based on code freeze dates, commit messages, and component structure:

### Phase 1: Core Observation & Governance (Pre-Node)
- M1-M6 observation pipeline
- Constitutional governance layer
- Whitelist query schemas
- **Frozen:** 2026-01-05

### Phase 2: Strategy & Execution Logic (Pre-Node)
- EP2 strategies (geometry, kinematics, absence)
- EP3 arbitration rules (13 theorems)
- EP4 execution pipeline
- Position state machine (8 transitions)
- **Frozen:** 2026-01-25

### Phase 3: Risk & Safety Hardening (Pre-Node)
- Risk monitor with 4 invariants
- Protective mandate emission
- Emergency exit (X3-A)
- Closing timeout (X6-A)

### Phase 4: Node Adapter Design (Node Not Yet Stable)
- Initial `node_adapter/` in runtime (OLD, removed)
- Proto schema design
- PositionStateManager design
- ObservationBridge design

### Phase 5: Node Becomes Operational (2026-01-31 to 2026-02-01)
- Node syncing and writing data
- File format discovery
- Asset mapping creation

### Phase 6: New Out-of-Process Adapter (2026-02-01)
- `hl-node-adapter/` created
- gRPC server implementation
- PriceReader/LiquidationReader validated
- NodeBridge integration tested
- Old `node_adapter/` removed

### Ordering Uncertainty
- Exact dates for Phase 1-4 are unclear
- HLP implementation phases (1039+ tests) span multiple weeks
- Some Phase 4 components may have been designed speculatively

---

## STEP 7: Wired vs Assumed

### WIRED (Backed by Real Data Today)

| Component | Real Data Source | Validation |
|-----------|------------------|------------|
| PriceReader | `replica_cmds/session/date/blockfile` | 6080 prices streamed |
| LiquidationReader | `node_fills/hourly/YYYYMMDD/HH` | 13 liquidations parsed |
| Asset Mapping | SetGlobalAction from live blocks | 228 assets confirmed |
| gRPC Streaming | Server broadcasting events | Handshake verified |
| NodeBridge | gRPC to ingest_observation | 75 HL_PRICE events |
| Binance Collector | Binance WebSocket | Production-validated |

### ASSUMED / PLACEHOLDER

| Component | What's Assumed | Risk |
|-----------|----------------|------|
| PositionStateManager | `abci_state.rmp` msgpack schema | Not exercised |
| Cascade proximity data | Position distances from node | Not wired to strategies |
| Leverage concentration | Calculated from positions | No live data source |
| OI bias | Derived from position aggregates | No live data source |
| EP1 Oracle Volatility | Entire module is STUB | No implementation |
| Live execution | Hyperliquid order API | Ghost mode only |

### Components with MIXED Status

| Component | Wired Part | Assumed Part |
|-----------|------------|--------------|
| EP2 Cascade Sniper | Strategy logic | Proximity data source |
| M4 Cascade Primitives | Computation logic | Input data schema |
| CollectorService | Binance integration | Node integration (USE_HL_NODE path) |

---

## STEP 8: Open Questions

### Questions That Cannot Be Answered from Codebase Alone

#### Node Data Schema Questions
1. Does SetGlobalAction always contain exactly 228 assets, or can it vary?
2. Are there ever blocks without SetGlobalAction?
3. Is the asset order in SetGlobalAction guaranteed stable across sessions?
4. Can `mark_price` be null for some assets? Which ones?

#### Liquidation Event Questions
5. Is `markPx` always present in the `liquidation` field?
6. Can `method` have values other than "market" and "backstop"?
7. Are fill IDs globally unique across all time, or just within a session?
8. Is there a delay between trade execution and appearance in `node_fills`?

#### Ordering & Timing Questions
9. Are events within a block strictly ordered?
10. Can two blocks have the same height?
11. What is the maximum observed block interval?
12. Can liquidations from the same trade appear in different hour files?

#### File System Questions
13. Can files be modified after creation (appended but not rewritten)?
14. How long after hour end does the hour file become complete?
15. Is there a maximum file size before rotation?
16. Can session directories be deleted while node is running?

#### Position State Questions
17. What is the update frequency of `abci_state.rmp`?
18. Is position data eventually consistent or strongly consistent with blocks?
19. Are closed positions removed from state or marked as closed?
20. What is the maximum number of positions per wallet?

### Data Collection Requirements

To answer these questions, the following data collection is needed:

1. **Schema validation**: Run adapter for 24+ hours, log all field variations
2. **Ordering verification**: Compare timestamps across event types
3. **Gap detection**: Monitor for missing block heights or time gaps
4. **Edge case discovery**: Log all parse errors and their causes
5. **Volume profiling**: Measure event rates under various market conditions

---

## Summary

### What We Know
- Node files exist and are parseable
- Price and liquidation readers work with live data
- gRPC transport layer is functional
- Asset mapping is correct for current 228 assets
- Basic event flow to observation system is wired

### What We Don't Know
- Long-term schema stability
- Edge case handling requirements
- Ordering guarantees across streams
- Position state integration requirements

### What's Working
- Out-of-process adapter architecture
- Checkpoint/restart capability
- Multi-client gRPC streaming
- Event type conversion

### What's Not Validated
- Full M1-M6 pipeline with node data
- Strategy behavior with node-sourced primitives
- Position proximity calculations
- Live execution path

---

## Document Status

This document represents system state as of **2026-02-01 09:50 CET**.

It is intended for informed discussion, not judgment.

The system can be exercised further to answer open questions, but this requires runtime observation, not code analysis.
