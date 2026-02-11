# SYSTEM REALITY MAP

**Date:** 2026-02-01
**Purpose:** Ground truth about what actually runs with live data
**Type:** Factual System State (No Assumptions)

---

## STEP 1 — TEMPORAL CONTEXT

### When Was the Node Non-Operational?

| Period | Status |
|--------|--------|
| 2026-01-10 to 2026-01-25 | Node did NOT exist. All development was speculative. |
| 2026-01-26 | Node became operational. First trades data appeared. |
| 2026-01-28 | First liquidation fills data appeared. |
| 2026-02-01 | Node validated with live gRPC adapter. |

### Which Modules Predate Node Availability?

| Module | Created | Node Available | Gap |
|--------|---------|----------------|-----|
| `observation/governance.py` | 2026-01-10 | 2026-01-26 | 16 days |
| `runtime/policy_adapter.py` | 2026-01-10 | 2026-01-26 | 16 days |
| `memory/m4_cascade_proximity.py` | 2026-01-16 | 2026-01-26 | 10 days |
| `memory/m4_cascade_state.py` | 2026-01-25 | 2026-01-26 | 1 day |
| `runtime/node_client/bridge.py` | 2026-01-26 | 2026-01-26 | 0 days |

**Conclusion:** 95% of the codebase was built BEFORE node data existed. The M1-M6 pipeline, all strategies, and cascade primitives were designed speculatively.

### Which Modules Could Not Possibly Have Been Exercised Live?

1. **Cascade primitives** (`m4_cascade_*.py`) — Built 2026-01-16 to 2026-01-25, require HL collector data that has never flowed
2. **Cascade Sniper strategy** — Requires proximity data that has 0 records in database
3. **SLBRS/EFFCS strategies** — Require regime classification that rarely activates
4. **PositionStateManager** — References a class that doesn't exist

---

## STEP 2 — CURRENT SYSTEM STATE

### What Is Running RIGHT NOW?

| Component | Status | Evidence |
|-----------|--------|----------|
| **HL Node** | RUNNING | PID 820414, processing blocks at ~8 sec/block |
| **gRPC Server** | NOT RUNNING | Port 50051 not listening |
| **Collector Service** | NOT RUNNING | Logs stale since Jan 14 |
| **Binance WebSocket** | NOT RUNNING | No active connections |

### What Data Exists RIGHT NOW?

| Data Source | Location | Status | Freshness |
|-------------|----------|--------|-----------|
| HL replica_cmds | `~/hl/data/replica_cmds/` | ACTIVE | Updated 11:12 today |
| HL node_fills | `~/hl/data/node_fills/hourly/` | ACTIVE | Hourly files through hour 10 |
| execution.db | `logs/execution.db` | EXISTS | Last modified 08:56 today |
| execution.db HL tables | 6 tables | EMPTY | 0 rows in all HL-specific tables |

---

## STEP 3 — DATA FLOW REALITY

### Path A: HL Node → System

```
hl-node (RUNNING, producing files)
    ↓
~/hl/data/replica_cmds/  ← ACTIVE (24GB today)
~/hl/data/node_fills/    ← ACTIVE (1.2GB today)
    ↓
gRPC Server (NOT RUNNING)
    ↓
NodeBridge (NOT CONNECTED)
    ↓
ObservationSystem (NOT RECEIVING HL DATA)
```

**Status:** BROKEN at gRPC layer. Node produces data, but nothing consumes it.

### Path B: Binance → System

```
Binance WebSocket (NOT CONNECTED)
    ↓
CollectorService (NOT RUNNING)
    ↓
ObservationSystem (NOT RECEIVING BINANCE DATA)
```

**Status:** BROKEN at collector layer. No process is running to consume Binance data.

### Path C: Historical State (execution.db)

| Table | Rows | Interpretation |
|-------|------|----------------|
| `liquidation_events` | 7,614 | Binance liquidations (historical, stopped 08:49 today) |
| `mandates` | 10,583 | 99.7% ENTRY (geometry strategy only) |
| `m2_nodes` | 22,052,434 | M2 memory working (historical) |
| `execution_cycles` | 14,761 | Normal cycle operation (historical) |
| `hl_liquidation_events_raw` | 0 | NEVER populated |
| `hl_mark_prices_raw` | 0 | NEVER populated |
| `hl_cascade_events` | 0 | NEVER populated |

**Status:** System HAS run historically with Binance data. HL integration has NEVER worked.

---

## STEP 4 — WHAT ACTUALLY WORKS

### Verified Working (When Collector Runs)

1. **M1 Ingestion** — Normalizes Binance TRADE, LIQUIDATION, DEPTH events
2. **M2 Memory Store** — 22M+ nodes created, decay working
3. **M3 Temporal Engine** — Candle aggregation functional
4. **M4 Tier A Primitives** — Zone geometry, kinematics computed
5. **Geometry Strategy** — Produces ~99% of all mandates
6. **Ghost Execution** — Paper trading works

### Never Worked

1. **HL Collector Integration** — 0 rows in all HL tables
2. **Cascade Primitives** — Always None (collector never wired)
3. **Cascade Sniper Strategy** — 0 mandates ever generated
4. **SLBRS/EFFCS Strategies** — Regime rarely activates
5. **Position Reconciliation** — Code exists, never called

### Currently Broken

1. **All data ingestion** — No collector process running
2. **gRPC server** — Not running, port 50051 closed
3. **Real-time observation** — System is idle

---

## STEP 5 — WHAT IS IMAGINARY

Components that exist in code but have never received real data:

| Component | Why Imaginary |
|-----------|---------------|
| `LiquidationCascadeProximity` primitive | Requires HL collector data that doesn't flow |
| `CascadeStateObservation` primitive | Requires proximity data with 0 records |
| `LeverageConcentrationRatio` primitive | Requires position data with 0 records |
| `OpenInterestDirectionalBias` primitive | Requires position data with 0 records |
| `cascade_sniper_proposal()` | Requires proximity data that doesn't exist |
| `generate_slbrs_proposal()` | Requires SIDEWAYS regime that rarely occurs |
| `generate_effcs_proposal()` | Requires EXPANSION regime that rarely occurs |
| `PositionReconciler` | Defined but never instantiated |
| `PositionStateManager` | Referenced but class doesn't exist |

---

## STEP 6 — SUMMARY

### The Reality

**What exists:** A system that CAN ingest Binance data, compute M2/M3/M4 primitives, generate geometry-based mandates, and execute ghost trades.

**What doesn't exist:** Any integration with Hyperliquid node data. The cascade detection, proximity tracking, and higher-tier strategies are all dead code.

**Current state:** The system is IDLE. No processes are running to ingest data.

### The Gap

| Intended | Actual |
|----------|--------|
| HL node → gRPC → Bridge → M1 | HL node → files → NOTHING |
| Cascade primitives computed | Cascade primitives always None |
| Multi-strategy arbitration | Single strategy (geometry) |
| Real-time observation | No observation process running |

---

*This document describes what IS, not what SHOULD BE.*

*Generated: 2026-02-01*
