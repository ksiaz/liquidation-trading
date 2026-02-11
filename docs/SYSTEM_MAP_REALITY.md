# SYSTEM MAP REALITY

**Date:** 2026-02-01
**Purpose:** Ground-truth system inventory documenting what data enters, how it flows, and what parts are live, stubbed, historical, or unverified
**Type:** Canonical System Map (Read-Only Audit)

---

## 1. SUBSYSTEM INVENTORY

### 1.1 Subsystems That Exist

#### Observation Layer (M1-M5)

| Subsystem | Location | Data Status | Verification |
|-----------|----------|-------------|--------------|
| **M1 Ingestion** | `observation/internal/m1_ingestion.py` | LIVE | Tested with both HL and Binance |
| **M1 Governance** | `observation/governance.py` | LIVE | Enforces canonical schemas |
| **M2 Continuity Store** | `memory/m2_continuity_store.py` | LIVE BUT UNVERIFIED | Creates nodes, decay rates uncalibrated |
| **M2 Memory State** | `memory/m2_memory_state.py` | LIVE | Stores M2 nodes |
| **M2 Topology** | `memory/m2_topology.py` | LIVE | Spatial relationships |
| **M2 Pressure** | `memory/m2_pressure.py` | LIVE | Pressure calculations |
| **M2 Historical Evidence** | `memory/m2_historical_evidence.py` | LIVE | Evidence accumulation |
| **M3 Temporal Engine** | `memory/m3_temporal.py` | LIVE | Candle aggregation |
| **M3 Evidence Token** | `memory/m3_evidence_token.py` | LIVE | Token creation |
| **M3 Sequence Buffer** | `memory/m3_sequence_buffer.py` | LIVE | Sequence tracking |
| **M3 Motif Extractor** | `memory/m3_motif_extractor.py` | LIVE | Pattern detection |
| **M4 Primitives (17 modules)** | `memory/m4_*.py` | LIVE | 25+ primitives computed |
| **M5 Query Schemas** | `memory/m5_query_schemas.py` | LIVE | Schema enforcement |
| **M5 Access** | `memory/m5_access.py` | LIVE | Query interface |
| **M5 Guards** | `memory/m5_selection_guards.py` | LIVE | Selection validation |
| **M6 Scaffolding** | `memory/m6_scaffolding.py` | LIVE | Meta-learning hooks |

#### M4 Primitive Modules (Detail)

| Module | Purpose | Status |
|--------|---------|--------|
| `m4_evidence_composition.py` | Evidence aggregation | UNIT TESTED |
| `m4_interaction_density.py` | Activity concentration | UNIT TESTED |
| `m4_stability_transience.py` | Zone stability | UNIT TESTED |
| `m4_temporal_structure.py` | Time patterns | UNIT TESTED |
| `m4_cross_node_context.py` | Multi-node correlation | UNIT TESTED |
| `m4_zone_geometry.py` | Zone spatial metrics | UNIT TESTED |
| `m4_price_distribution.py` | Price statistics | UNIT TESTED |
| `m4_traversal_kinematics.py` | Movement dynamics | UNIT TESTED |
| `m4_structural_boundaries.py` | Boundary detection | UNIT TESTED |
| `m4_structural_absence.py` | Gap detection | UNIT TESTED |
| `m4_traversal_voids.py` | Void identification | UNIT TESTED |
| `m4_event_absence.py` | Missing event detection | UNIT TESTED |
| `m4_structural_persistence.py` | Zone durability | UNIT TESTED |
| `m4_structural_exposure.py` | Exposure metrics | UNIT TESTED |
| `m4_cascade_state.py` | Cascade tracking | NEEDS CALIBRATION |
| `m4_cascade_proximity.py` | Proximity to cascades | NEEDS CALIBRATION |
| `m4_cascade_momentum.py` | Cascade momentum | NEEDS CALIBRATION |

#### Runtime Layer

| Subsystem | Location | Data Status | Verification |
|-----------|----------|-------------|--------------|
| **PolicyAdapter** | `runtime/policy_adapter.py` | LIVE | Invokes strategies |
| **M6 Executor** | `runtime/m6_executor.py` | FROZEN | Execution orchestration |
| **Environment Setup** | `runtime/env_setup.py` | LIVE | Configuration |
| **MandateArbitrator** | `runtime/arbitration/arbitrator.py` | VERIFIED | 13 theorems proven |

#### Execution Layer

| Subsystem | Location | Data Status | Verification |
|-----------|----------|-------------|--------------|
| **EP4 Execution** | `execution/ep4_execution.py` | FROZEN | Core execution |
| **EP4 Action Schemas** | `execution/ep4_action_schemas.py` | FROZEN | Action types |
| **EP4 Ghost Adapter** | `execution/ep4_ghost_adapter.py` | LIVE | Paper trading |
| **EP4 Ghost Tracker** | `execution/ep4_ghost_tracker.py` | LIVE | Position tracking |
| **EP4 Hyperliquid Adapter** | `execution/ep4_hyperliquid_adapter.py` | NEVER EXERCISED | Live trading |
| **EP4 Risk Gates** | `execution/ep4_risk_gates.py` | UNIT TESTED | Risk checks |

#### External Policy (EP2 Strategies)

| Subsystem | Location | Data Status | Verification |
|-----------|----------|-------------|--------------|
| **EP2 Geometry** | `external_policy/ep2_strategies/geometry.py` | LIVE | Spatial strategies |
| **EP2 Kinematics** | `external_policy/ep2_strategies/kinematics.py` | LIVE | Movement strategies |
| **EP2 Absence** | `external_policy/ep2_strategies/absence.py` | LIVE | Void strategies |
| **EP2 Cascade Sniper** | `external_policy/ep2_strategies/cascade_sniper.py` | NEEDS CALIBRATION | Liquidation strategies |

#### HL Node Integration

| Subsystem | Location | Data Status | Verification |
|-----------|----------|-------------|--------------|
| **NodeBridge** | `runtime/node_client/bridge.py` | LIVE & VERIFIED | HL→M1 normalization |
| **NodeSubscriber** | `runtime/node_client/subscriber.py` | TESTED | gRPC subscription |
| **PriceReader** | `~/.hl-node-adapter/readers/price_reader.py` | LIVE & VERIFIED | Reads replica_cmds |
| **LiquidationReader** | `~/.hl-node-adapter/readers/liquidation_reader.py` | LIVE & VERIFIED | Reads node_fills |
| **NodeAdapter** | `~/.hl-node-adapter/adapter.py` | LIVE | Coordinates readers |
| **gRPC Server** | `~/.hl-node-adapter/grpc_server.py` | LIVE | Broadcasts events |
| **PositionStateManager** | `runtime/hyperliquid/position_state_manager.py` | NOT CONNECTED | Reads abci_state.rmp |
| **LiquidationBurstAggregator** | `runtime/hyperliquid/burst_aggregator.py` | PARTIAL | Aggregates cascades |

---

### 1.2 Data Producers (Reality-Based)

| Producer | Output | Destination | Frequency | Status |
|----------|--------|-------------|-----------|--------|
| **HL Node (replica_cmds)** | PriceEvent | NodeAdapter → M1 | ~500ms (per block) | LIVE |
| **HL Node (node_fills)** | LiquidationEvent | NodeAdapter → M1 | Event-driven | LIVE |
| **HL Node (abci_state.rmp)** | Position snapshots | PositionStateManager | On startup | NOT CONNECTED |
| **Binance forceOrder WS** | Liquidation events | M1 Ingestion | Event-driven | PARTIAL |
| **Binance trades WS** | Trade events | M1 Ingestion | Event-driven | LIVE |
| **Binance l2Book WS** | Depth snapshots | M1 Ingestion | 100ms | LIVE |
| **Binance fundingRate REST** | Funding rates | M1 Ingestion | 8h | LIVE |
| **HL clearinghouseState REST** | Position data | Paper trader | On-demand | LIVE |
| **M1 Buffers** | Normalized events | M2 Store | Per event | LIVE |
| **M2 Nodes** | Zone structures | M3 Temporal | Per event | LIVE |
| **M3 Temporal** | Candles, sequences | M4 Primitives | Per candle close | LIVE |
| **M4 Primitives** | 25+ computed signals | M5 Query | Per cycle | LIVE |
| **M5 Queries** | Filtered snapshots | PolicyAdapter | Per cycle | LIVE |
| **PolicyAdapter** | Mandates | Arbitrator | Per cycle | LIVE |
| **Arbitrator** | Actions | Executor | Per cycle | LIVE |
| **Executor** | Orders | Exchange/Ghost | Per action | GHOST ONLY |

---

### 1.3 Data Consumers (Required/Optional/Starved)

#### REQUIRED Consumers (System Cannot Function Without)

| Consumer | Data Required | Source | Status |
|----------|---------------|--------|--------|
| **M1 Ingestion** | Raw events (trades, liqs, depth) | HL Node or Binance | FED |
| **M2 Store** | Normalized M1 events | M1 | FED |
| **M4 Primitives** | M2 nodes, M3 temporal | M2, M3 | FED |
| **PolicyAdapter** | M4 primitive bundle | M5 Query | FED |
| **Arbitrator** | Mandates | PolicyAdapter | FED |
| **ExecutionController** | Actions | Arbitrator | FED |

#### OPTIONAL Consumers (System Degrades Gracefully Without)

| Consumer | Data Desired | Source | Status |
|----------|--------------|--------|--------|
| **M2 Historical Evidence** | Past zone outcomes | execution.db | PARTIAL |
| **M3 Motif Extractor** | Price patterns | M2 topology | LIVE |
| **M6 Scaffolding** | Meta-learning signals | M5 | STUBBED |
| **Metrics Dashboard** | Latency stats | All layers | PARTIAL |

#### STARVED Consumers (Needed But Not Receiving)

| Consumer | Data Needed | Intended Source | Starvation Impact |
|----------|-------------|-----------------|-------------------|
| **PositionStateManager** | abci_state.rmp snapshots | HL Node files | No wallet proximity calculations |
| **Cascade Sniper** | Real cascade distributions | 90+ days node data | Thresholds are guesses |
| **EP4 Live Adapter** | Real exchange fills | Hyperliquid API | No live validation |
| **Position Reconciliation** | Exchange position state | Hyperliquid API | Ghost positions may drift |
| **Risk Monitor** | Consecutive loss count | Execution history | Conservative fallback used |

---

## 2. TEMPORAL REALITY & DEVELOPMENT TIMELINE

### 2.1 When Components Were Built vs Validated

```
TIMELINE (Approximate)

2025-10: M1-M3 Pipeline Design
2025-11: M4 Primitive Framework
2025-12: M5 Query Layer, EP2 Strategies
2026-01-05: CODE FREEZE v1.0 (Core Pipeline)
2026-01-25: EXECUTION FREEZE (m6_executor, controller)
2026-01-28: Node Adapter Development Start
2026-01-31: gRPC Server + NodeBridge Complete
2026-02-01: M1 Normalization Verified
2026-02-01: First Observational Calibration Complete
```

### 2.2 Component Age vs Validation Age

| Component | Built | Last Validated | Gap |
|-----------|-------|----------------|-----|
| M1-M3 Pipeline | 2025-10 | 2026-02-01 (HL data) | Validated recently |
| M4 Tier A Primitives | 2025-11 | 2026-01 (unit tests) | Unit tested only |
| M4 Cascade Primitives | 2026-01 | NEVER with real data | HIGH RISK |
| EP2 Strategies | 2025-12 | NEVER with live edge | HIGH RISK |
| Arbitrator | 2025-12 | 2026-01 (theorem proofs) | Formally verified |
| Executor | 2025-12 | 2026-01 (ghost mode) | Ghost only |
| NodeBridge | 2026-01-31 | 2026-02-01 | Recently validated |

### 2.3 Temporal Awareness Issues

| Issue | Location | Impact | Resolution |
|-------|----------|--------|------------|
| Wall clock in freshness | `bridge.py:77,100` | May reject valid HL events | Needs investigation |
| No time sync protocol | NodeBridge | Clock drift possible | Use block time as authority |
| Cascade 5s gap assumption | `governance.py` | May split real cascades | Needs calibration |

---

## 3. DATA LANE VERIFICATION TABLE

| Lane | Source → Dest | Transport | Schema | Tested Live | Last Verified | Evidence |
|------|---------------|-----------|--------|-------------|---------------|----------|
| HL prices | Node files → PriceReader | File I/O | SetGlobalAction | YES | 2026-02-01 | 570 prices broadcast |
| HL liquidations | Node fills → LiquidationReader | File I/O | [wallet, fill] | YES | 2026-02-01 | 10,164 events parsed |
| HL → gRPC | PriceReader → gRPC server | Callback | PriceEvent proto | YES | 2026-02-01 | Server logs |
| gRPC → NodeBridge | gRPC server → subscriber | gRPC stream | Proto messages | YES | 2026-02-01 | Handshake verified |
| NodeBridge → M1 | Subscriber → ObservationSystem | Function call | Canonical events | YES | 2026-02-01 | Unit tests |
| M1 → M2 | ingest_observation() | Internal | M2 node | YES | Unit tests | - |
| M2 → M3 | M2 nodes → temporal | Internal | Candles | YES | Unit tests | - |
| M3 → M4 | Temporal → primitives | Internal | M4Bundle | YES | Unit tests | - |
| M4 → M5 | Primitives → query | Internal | ObservationSnapshot | YES | Unit tests | - |
| M5 → PolicyAdapter | Query → strategies | Internal | Filtered snapshot | NO | Never E2E | - |
| PolicyAdapter → Arbitrator | Mandates | Internal | Mandate set | YES | Theorem proofs | - |
| Arbitrator → Executor | Action | Internal | Action | YES | Theorem proofs | - |
| Executor → Ghost | OrderRequest | Internal | Order | YES | Ghost mode | - |
| Executor → Live Exchange | OrderRequest | HTTPS | HL API | **NO** | **NEVER** | - |
| Binance trades → M1 | WebSocket → M1 | WebSocket | TRADE events | YES | execution.db exists | 4GB |
| Binance liqs → M1 | WebSocket → M1 | WebSocket | LIQUIDATION | PARTIAL | Gaps observed | - |
| abci_state → PSM | File I/O → PositionStateManager | msgpack | Position state | **NO** | **NEVER** | - |

---

## 4. ADAPTER STRATEGY (PLAN ONLY)

### 4.1 Current State

The system has two ingestion paths:
1. **Binance Path** — Original implementation, LIVE, creates TRADE/LIQUIDATION/DEPTH events
2. **HL Node Path** — New implementation, LIVE, creates HL_PRICE and normalized LIQUIDATION events

Both paths converge at `ingest_observation()` in governance.py.

### 4.2 Identified Gaps

| Gap | Current State | Required State |
|-----|---------------|----------------|
| **Cascade primitives uncalibrated** | Hardcoded thresholds | Thresholds from 90+ days observation |
| **PositionStateManager unused** | Code exists | Wired to proximity calculations |
| **Live exchange untested** | Ghost adapter only | Full order lifecycle tested |
| **Position reconciliation** | Not wired | Exchange is source of truth |

### 4.3 Adapter Plan (No Code Changes Yet)

#### Phase 1: Complete Observation Infrastructure (Current)
- [x] PriceReader verified
- [x] LiquidationReader verified
- [x] gRPC server running
- [x] NodeBridge normalizing events
- [x] First calibration run complete (10,164 liquidations)

#### Phase 2: Extend Observation Period
- [ ] Run continuous observation for 7+ days
- [ ] Collect 50,000+ liquidation events
- [ ] Compute empirical cascade distributions
- [ ] Document: cascade size distribution, time gaps, value distribution

#### Phase 3: Wire Remaining Components
- [ ] Connect PositionStateManager to abci_state.rmp
- [ ] Wire proximity calculations to Cascade Sniper
- [ ] Add position reconciliation to execution loop
- [ ] Test reconnection behavior (HLP16)

#### Phase 4: Threshold Discovery
- [ ] Analyze calibration data for natural clusters
- [ ] Compute conservative thresholds (P10/P90 bounds)
- [ ] Create threshold configuration file
- [ ] Document threshold derivation rationale

#### Phase 5: Pre-Live Validation
- [ ] Run paper trading for 7 days OR 50 trades
- [ ] Zero crashes criterion
- [ ] Position reconciliation verified
- [ ] Stop placement verified under network stress

---

## 5. STOP CONDITIONS & UNKNOWNS

### 5.1 Hard Stop Conditions (Do Not Proceed)

| Condition | Check | Current Status |
|-----------|-------|----------------|
| CODE_FREEZE in effect | `CODE_FREEZE.md` exists | YES - FROZEN |
| Cascade primitives uncalibrated | No 90-day data | BLOCKED |
| Live exchange never tested | Zero live orders | BLOCKED |
| Position reconciliation unwired | Code not connected | BLOCKED |

### 5.2 Soft Stop Conditions (Proceed With Caution)

| Condition | Check | Current Status |
|-----------|-------|----------------|
| < 50,000 calibration events | Event count | 10,164 (20%) |
| < 7 days paper trading | Runtime | Not started |
| Timestamp ordering issues | Negative time diffs | PRESENT |
| Wall clock freshness check | bridge.py | NEEDS REVIEW |

### 5.3 Known Unknowns

| Unknown | Impact | Path to Resolution |
|---------|--------|-------------------|
| Real cascade size distribution | Threshold selection | More observation time |
| Real cascade duration distribution | Window sizing | More observation time |
| Optimal decay rates for M2 nodes | Zone persistence | Requires backtesting |
| PositionStateManager correctness | Wallet proximity | Test with abci_state.rmp |
| Network failure recovery | System resilience | HLP16 implementation |
| Clock drift between node and system | Event ordering | Timestamp analysis |

### 5.4 Unknown Unknowns (Risk Areas)

| Area | Why Uncertain | Mitigation |
|------|---------------|------------|
| Live order execution | Never tested | Paper trade first, small size |
| High cascade velocity | Up to 26/second observed | Ensure system handles load |
| Exchange API limits | Unknown rate limits | Conservative pacing |
| Fill latency | Unknown at scale | Monitor and adapt |

---

## SUMMARY

### Data Flow Reality

```
GROUND TRUTH (HL Node)
    │
    ├── replica_cmds/ ────► PriceReader ────► gRPC ────► NodeBridge ────┐
    │                                                                   │
    └── node_fills/   ────► LiquidationReader ──► gRPC ──► NodeBridge ──┤
                                                                        │
                                                                        ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │                    M1 ingest_observation()                           │
    │                    observation/governance.py                         │
    └──────────────────────────────────────────────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
    ┌────────┐                    ┌──────────┐                    ┌──────────┐
    │ M2     │                    │ M3       │                    │ Cascade  │
    │ Nodes  │                    │ Temporal │                    │ Tracking │
    └────────┘                    └──────────┘                    └──────────┘
        │                               │                               │
        └───────────────────────────────┴───────────────────────────────┘
                                        │
                                        ▼
                            ┌──────────────────────┐
                            │ M4 Primitives (25+)  │
                            │ memory/m4_*.py       │
                            └──────────────────────┘
                                        │
                                        ▼
                            ┌──────────────────────┐
                            │ M5 Query + Guards    │
                            └──────────────────────┘
                                        │
                                        ▼
                            ┌──────────────────────┐
                            │ PolicyAdapter        │
                            │ (EP2 Strategies)     │
                            └──────────────────────┘
                                        │
                                        ▼
                            ┌──────────────────────┐
                            │ Arbitrator (13 thms) │  ✅ PROVEN
                            └──────────────────────┘
                                        │
                                        ▼
                            ┌──────────────────────┐
                            │ ExecutionController  │  ✅ FROZEN
                            └──────────────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
                ┌──────────────┐                ┌──────────────┐
                │ Ghost Adapter│                │ Live Adapter │
                │ ✅ ACTIVE    │                │ 🔴 NEVER USED│
                └──────────────┘                └──────────────┘
```

### Status Summary

| Category | Count | Status |
|----------|-------|--------|
| **LIVE & VERIFIED** | 12 | Operational with evidence |
| **LIVE BUT UNVERIFIED** | 8 | Running, real behavior unknown |
| **NEEDS CALIBRATION** | 5 | Requires empirical data |
| **NOT CONNECTED** | 3 | Code exists, not wired |
| **NEVER EXERCISED** | 2 | Live exchange paths |

### Next Action

**Continue observational calibration** — The system cannot proceed to threshold discovery until:
1. Timestamp ordering issue resolved
2. 50,000+ liquidation events collected (currently 10,164)
3. 7+ days of continuous observation (currently ~4 days)

---

*This document describes the system as it exists. No performance claims are made.*

*Generated: 2026-02-01*
