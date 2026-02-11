# Runtime Operation Contract

**Document Type:** Architectural Specification
**Phase:** E — Operational Canonicalization
**Status:** DESIGN ONLY
**Date:** 2026-02-01
**Prerequisite:** Phases A–D COMPLETE and VERIFIED

---

## 1. Purpose & Scope

### Definition

"Live paper operation" means:
- The system processes real-time market data from external sources
- The system emits mandates, performs arbitration, and produces actions
- Actions are logged but NOT transmitted to any exchange
- All execution is simulated (paper mode)
- Behavioral stability is observed passively

### Constitutional Meaning

Live paper operation is an **observation exercise**, not a trading exercise.
The system demonstrates that:
- Data flows through all layers without corruption
- Mandates are emitted according to frozen policy logic
- Arbitration resolves mandates deterministically
- Execution state machine transitions are valid
- No stability anomalies occur (storms, oscillations, deadlocks)

### Explicit Non-Goals

- User interface of any kind
- Operator intervention or control
- Performance measurement or scoring
- Parameter tuning or optimization
- Strategy comparison or selection
- P&L calculation or display
- Alert routing or escalation
- Feedback from observation to execution

---

## 2. Canonical Entry Point

### Authoritative Runtime

**Name:** `scripts/run_paper_trade.py`

**Role:** Single canonical process that composes and starts all runtime components.

**Authority:** This script is the ONLY authorized way to run live paper operation.

### What This Process Starts

- ObservationSystem
- CollectorService (with node bridge if available)
- ResourceMonitor
- CleanupCoordinator
- StabilityObserver (to be attached)

### What MUST NOT Be Started Independently

- PolicyAdapter (instantiated within CollectorService cycle)
- MandateArbitrator (instantiated within execution path)
- ExecutionController (instantiated within CollectorService)
- Any UI server, dashboard, or visualization process
- Any secondary collector process
- Any analytics or metrics aggregation process

### Process Isolation

The canonical runtime SHALL be a single OS process.
No child processes, subprocesses, or parallel executors are permitted.
All async operations occur within a single event loop.

---

## 3. Mandatory Runtime Components

### Component Registry

| Component | Module | Instantiation | Cardinality |
|-----------|--------|---------------|-------------|
| ObservationSystem | `observation.governance` | Startup | Exactly 1 |
| CollectorService | `runtime.collector.service` | Startup | Exactly 1 |
| ResourceMonitor | `runtime.monitoring` | Startup | Exactly 1 |
| CleanupCoordinator | `runtime.monitoring` | Startup | Exactly 1 |
| StabilityObserver | `runtime.stability_observer` | Startup | Exactly 1 |
| PolicyAdapter | `runtime.policy_adapter` | Per-cycle | Exactly 1 |
| MandateArbitrator | `runtime.arbitration.arbitrator` | Per-cycle | Exactly 1 |
| ExecutionController | `runtime.executor.controller` | Per-cycle | Exactly 1 |

### Collector Constraints

- CollectorService MAY operate in node mode (`USE_HL_NODE=true`) or Binance mode
- Node mode requires `~/hl/data` directory with replica data
- Binance mode uses WebSocket subscriptions
- Only ONE collector mode SHALL be active per runtime instance
- Collector failure SHALL NOT halt the runtime; degraded operation is permitted

### Component Ownership

- ObservationSystem owns M1, M2, M4 layers (read-only to downstream)
- CollectorService owns data ingestion and primitive computation
- PolicyAdapter owns policy invocation (frozen policies, no modification)
- MandateArbitrator owns mandate resolution (deterministic, theorem-verified)
- ExecutionController owns state machine transitions (paper mode only)
- StabilityObserver owns behavioral tracking (read-only, no control)

---

## 4. One-Way Data Flow (Invariant)

### Directed Data Graph

```
External Data Sources
        │
        ▼
┌─────────────────┐
│ CollectorService │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ObservationSystem│ (M1 → M2 → M4)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PolicyAdapter  │ (invokes frozen policies)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│MandateArbitrator│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ExecutionController│ (paper mode)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Persistence   │ (SQLite, logs)
└─────────────────┘
```

### Forbidden Reverse Flows

Data MUST NOT flow:
- From ExecutionController to PolicyAdapter
- From ExecutionController to ObservationSystem
- From Persistence to any runtime component
- From StabilityObserver to any component
- From any downstream component to any upstream component

### Observer Attachment Points

StabilityObserver observes at:
- PolicyAdapter output (mandates)
- MandateArbitrator output (actions)

StabilityObserver MUST NOT:
- Modify mandates
- Block arbitration
- Influence execution
- Write to persistence (except its own diagnostic log if configured)

---

## 5. Lifecycle Semantics

### Startup Sequence

1. **Environment validation**
   - Verify `USE_HL_NODE` or Binance mode
   - Verify data paths exist (if node mode)
   - Verify database paths writable

2. **Component instantiation** (strict order)
   - ObservationSystem (with allowed_symbols)
   - CollectorService (with ObservationSystem reference)
   - ResourceMonitor
   - CleanupCoordinator
   - StabilityObserver

3. **Component registration**
   - Register components with ResourceMonitor
   - Register pruners with CleanupCoordinator
   - Attach StabilityObserver to execution path

4. **Service start**
   - Start ResourceMonitor (background)
   - Start CleanupCoordinator (background)
   - Start CollectorService (main loop)

5. **Ready state**
   - System enters steady-state when CollectorService emits first price

### Steady-State Behavior

- CollectorService polls/receives data continuously
- Each data event triggers observation update
- Observation snapshots flow to PolicyAdapter on configured cadence
- PolicyAdapter invokes policies, emits mandates
- StabilityObserver records each mandate
- Arbitrator resolves mandates to actions
- StabilityObserver records each action
- ExecutionController updates state machine (paper mode)
- Results persist to database

### Shutdown Semantics

**Graceful shutdown** (SIGINT, SIGTERM):
1. Set shutdown flag
2. Stop CollectorService (drain pending events)
3. Stop CleanupCoordinator
4. Stop ResourceMonitor
5. Flush pending database writes
6. Log final StabilityObserver summary
7. Exit with code 0

**Failure shutdown** (uncaught exception):
1. Log exception with full traceback
2. Log StabilityObserver summary (if available)
3. Exit with code 1

**Hard shutdown** (SIGKILL):
- No cleanup possible
- Database may have unflushed writes
- Acceptable; system recovers on next start

---

## 6. Stability Attachment

### Attachment Location

StabilityObserver SHALL be attached at two points:

**Point 1: Mandate emission**
- After PolicyAdapter.generate_mandates() returns
- Before mandates enter arbitration
- Record: mandate type, symbol, direction, timestamp

**Point 2: Action production**
- After MandateArbitrator.arbitrate_all() returns
- Before actions enter ExecutionController
- Record: action type, symbol, timestamp

### What StabilityObserver Observes

- Mandate counts per type per symbol
- Action counts per type per symbol
- Temporal spacing between emissions
- Direction changes (LONG ↔ SHORT)
- ENTRY/EXIT cycle frequency

### What StabilityObserver Detects

- Mandate storms (>50 mandates in 60s window)
- Oscillations (>3 ENTRY/EXIT cycles in 30s)
- Direction flips (>3 reversals)
- Deadlocks (no mandates for 300s)
- Corruption (invalid types, missing required fields)

### What StabilityObserver Is Forbidden To Do

- Block any mandate
- Modify any mandate
- Halt arbitration
- Halt execution
- Emit mandates
- Influence any component
- Write to execution database
- Communicate with external systems

---

## 7. Observability Contract

### What Is Externally Observable

| Data | Surface | Format | Access |
|------|---------|--------|--------|
| Execution cycles | `execution.db` | SQLite rows | Read-only |
| Mandates | `execution.db` | SQLite rows | Read-only |
| Arbitration rounds | `execution.db` | SQLite rows | Read-only |
| Position states | `execution.db` | SQLite rows | Read-only |
| Liquidation events | `execution.db` | SQLite rows | Read-only |
| Skip events | stdout (if DIAG_PRINT=1) | JSON lines | Read-only |
| Stability status | In-memory | Dict | Query only |
| Resource metrics | Logger | Text | Read-only |

### Persistence Surfaces

- **Primary:** `logs/execution.db` (SQLite)
- **Secondary:** `paper_trade.log` (text log)
- **Diagnostic:** stdout/stderr (if enabled)

### What Is Explicitly NOT Observable

- Internal state machine transitions (only outcomes)
- Primitive computation intermediates
- Policy invocation internals
- Arbitration algorithm steps
- Real-time memory structures (except via ResourceMonitor)

---

## 8. Failure & Degradation Rules

### Data Silence

**Definition:** No new data received for >60 seconds

**Behavior:**
- System continues running
- No mandates emitted (no data = no primitives = no proposals)
- StabilityObserver MAY flag as potential deadlock after 300s
- No automatic halt or intervention

### Collector Failure

**Definition:** CollectorService throws exception or disconnects

**Behavior:**
- Log error
- Attempt reconnection (if WebSocket mode)
- Continue with stale data (degraded mode)
- No automatic halt
- StabilityObserver records absence of new data

### Execution Failure

**Definition:** ExecutionController rejects action or state machine violation

**Behavior:**
- Log rejection with reason
- Record to database
- Continue processing next symbol
- No halt, no retry, no escalation

### What NEVER Triggers Halts

- Data staleness
- Empty mandate sets
- Rejected actions
- State machine constraint violations
- StabilityObserver warnings
- StabilityObserver CRITICAL status
- Memory warnings (cleanup triggered instead)
- Any single-symbol failure

### What MAY Trigger Halts

- Unrecoverable process-level exception
- SIGINT/SIGTERM signals
- Memory CRITICAL with cleanup failure
- Disk full with database write failure

---

## 9. UI Boundary Definition

### What Any Future UI May Read

- All tables in `execution.db` (read-only)
- `paper_trade.log` (read-only)
- StabilityObserver.summary() via IPC (if implemented)
- ResourceMonitor metrics via IPC (if implemented)

### What UI May Never Influence

- Mandate generation
- Arbitration resolution
- Execution decisions
- Policy parameters
- Symbol selection
- Risk thresholds
- Any runtime state

### Process Isolation Guarantees

- UI SHALL run as separate OS process
- UI SHALL NOT share memory with runtime
- UI SHALL NOT have write access to `execution.db`
- UI communication (if any) SHALL be via read-only IPC or file polling
- Runtime SHALL function identically with or without UI process

---

## 10. Constitutional Closure

### No New Authority

This phase introduces:
- No new mandate types
- No new arbitration rules
- No new execution paths
- No new data sources
- No new feedback mechanisms
- No new control surfaces

This phase defines ONLY:
- Component composition
- Startup/shutdown sequence
- Attachment points for existing StabilityObserver
- Boundaries for future (out-of-scope) UI

### Phases A–D Untouched

| Phase | Status | This Phase Modifies |
|-------|--------|---------------------|
| A: Policy Validation | COMPLETE | Nothing |
| B: Arbitration Verification | COMPLETE | Nothing |
| C: Stability Infrastructure | COMPLETE | Nothing |
| D: Integration Testing | COMPLETE | Nothing |

### Phase E Completion Criteria

Phase E is COMPLETE when:

1. This document exists at `docs/RUNTIME_OPERATION_CONTRACT.md`
2. `run_paper_trade.py` imports and attaches StabilityObserver
3. StabilityObserver.record_mandate() called after mandate generation
4. StabilityObserver.record_action() called after arbitration
5. StabilityObserver.summary() logged on shutdown
6. No other changes to any file in observation/, external_policy/, runtime/arbitration/

### Verification

Phase E completion is verified by:
- Document review (this file)
- Code diff showing ONLY StabilityObserver attachment
- Test run demonstrating stability logging
- No test regressions in Phases A–D (123 tests pass)

---

## Appendix: Symbol Configuration

### Canonical Symbol Set

```
BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT,
AVAXUSDT, LINKUSDT, HYPEUSDT, ADAUSDT, NEARUSDT
```

Plus HL-format equivalents:
```
BTC, ETH, SOL, XRP, DOGE, AVAX, LINK, HYPE, ADA, NEAR
```

### Symbol Set Authority

Symbol set is defined in `run_paper_trade.py` and is the ONLY authoritative source.
No other component may independently define or filter symbols.

---

*End of Runtime Operation Contract*
