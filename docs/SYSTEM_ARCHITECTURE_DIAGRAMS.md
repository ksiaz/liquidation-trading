# System Architecture Diagrams

**Version:** 1.0
**Date:** 2026-01-14
**System:** Constitutional Execution System

---

## 1. Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Constitutional Execution System                         │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      Observation Layers (M1-M5)                       │ │
│  │                                                                       │ │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │ │
│  │  │    M1    │───▶│    M2    │───▶│    M3    │───▶│    M4    │──┐   │ │
│  │  │Ingestion │    │Continuity│    │ Temporal │    │Primitives│  │   │ │
│  │  │  Engine  │    │  Memory  │    │  Engine  │    │ (19 prms)│  │   │ │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │   │ │
│  │       ▲                                                          │   │ │
│  │       │                                                          ▼   │ │
│  │  WebSocket                                                  ┌────────┐│ │
│  │  Streams                                                    │   M5   ││ │
│  │  (Trades,                                                   │Govern- ││ │
│  │   Liq,                                                      │ ance   ││ │
│  │   Depth)                                                    └────────┘│ │
│  │                                                                  │    │ │
│  └──────────────────────────────────────────────────────────────────┼────┘ │
│                                                                     │      │
│                                             ObservationSnapshot     │      │
│                                                                     ▼      │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │             Policy & Execution Layers (EP2-EP4, M6)               │  │
│  │                                                                    │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐   │  │
│  │  │   EP2    │───▶│   EP3    │───▶│   EP4    │◀───│    M6    │   │  │
│  │  │Strategies│    │Arbitrat- │    │Execution │    │Permission│   │  │
│  │  │ (3 types)│    │   ion    │    │  Layer   │    │  Layer   │   │  │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘   │  │
│  │       │               │                │                          │  │
│  │   Mandates        Single           Ghost                          │  │
│  │  (ENTRY/EXIT)     Action           Trading                        │  │
│  │                                     + Risk                         │  │
│  │                                     Gates                          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                      logs/execution.db                             │  │
│  │  execution_cycles | m2_nodes | primitive_values | ghost_trades    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Observation Layer Detail (M1-M5)

```
                          M1: Ingestion Engine
                     ┌─────────────────────────────┐
                     │  WebSocket Streams:         │
                     │  • Trades (BTC, ETH, ...)   │
                     │  • Liquidations             │
Hyperliquid ========▶│  • Depth (Order Book)       │
 Exchange            │                             │
                     │  Normalization:             │
                     │  • Timestamp extraction     │
                     │  • Symbol routing           │
                     │  • Event validation         │
                     └──────────────┬──────────────┘
                                    │ Normalized Events
                                    ▼
                          M2: Continuity Memory
                     ┌─────────────────────────────┐
                     │  Memory Nodes:              │
                     │  • Price level tracking     │
                     │  • Node lifecycle:          │
                     │    ACTIVE→DORMANT→ARCHIVED  │
                     │  • Interaction recording    │
                     │  • Cluster detection        │
                     └──────────────┬──────────────┘
                                    │ Node State
                                    ▼
                          M3: Temporal Engine
                     ┌─────────────────────────────┐
                     │  Time Management:           │
                     │  • advance_time(ts)         │
                     │  • Monotonicity enforcement │
                     │  • Event sequencing         │
                     │  • Causality preservation   │
                     │  • HALT on time reversal    │
                     └──────────────┬──────────────┘
                                    │ Sequenced Events
                                    ▼
                      M4: Primitive Computation
        ┌────────────────────────────────────────────────────┐
        │  19 Primitives:                                    │
        │  ┌─────────────────┬──────────────────────────┐   │
        │  │ Zone Geometry   │ • penetration_depth      │   │
        │  │                 │ • displacement_anchor    │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Kinematics      │ • velocity               │   │
        │  │                 │ • compactness            │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Distribution    │ • central_tendency       │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Absence         │ • structural_absence     │   │
        │  │                 │ • void_span              │   │
        │  │                 │ • event_non_occurrence   │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Persistence     │ • structural_persistence │   │
        │  │                 │ • price_acceptance       │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Liquidation     │ • liquidation_density    │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Trade Flow      │ • directional_continuity │   │
        │  │                 │ • trade_burst            │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Order Book      │ • resting_size           │   │
        │  │                 │ • consumption            │   │
        │  │                 │ • absorption             │   │
        │  │                 │ • refill                 │   │
        │  ├─────────────────┼──────────────────────────┤   │
        │  │ Patterns        │ • order_block            │   │
        │  │                 │ • supply_demand_zone     │   │
        │  └─────────────────┴──────────────────────────┘   │
        └────────────────────────┬───────────────────────────┘
                                 │ M4PrimitiveBundle
                                 ▼
                         M5: Governance Layer
                    ┌──────────────────────────────┐
                    │  Orchestration:              │
                    │  • compute_snapshot()        │
                    │  • Invariant enforcement     │
                    │  • Snapshot generation       │
                    │                              │
                    │  Exposes ONLY:               │
                    │  • status (UNINITIALIZED     │
                    │    or FAILED)                │
                    │  • timestamp                 │
                    │  • symbol list               │
                    └──────────────┬───────────────┘
                                   │ ObservationSnapshot
                                   ▼
                            [To EP2-EP4]
```

---

## 3. Policy & Execution Flow (EP2-EP4, M6)

```
                        ObservationSnapshot
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   EP2: Strategies     │
                     │                       │
      ┌──────────────┤  • Geometry Strategy  │
      │              │  • Kinematics Strategy│
      │              │  • Absence Strategy   │
      │              └───────┬───────────────┘
      │                      │
      │                  Mandates
      │              (ENTRY, EXIT, HOLD)
      │                      │
      ▼                      ▼
┌───────────┐        ┌──────────────┐
│ Current   │───────▶│  EP3:        │
│ Position  │        │  Arbitration │
│ State     │        │              │
└───────────┘        │  Rules:      │
                     │  1. EXIT     │
                     │     supremacy │
                     │  2. Single   │
                     │     action   │
                     │  3. Determin-│
                     │     istic    │
                     └──────┬───────┘
                            │ Single Action
                            ▼
                     ┌──────────────┐
                     │  M6:         │
                     │  Permission  │◀──── Constitutional
                     │  Layer       │      Constraints
                     │              │
                     │  Validates:  │
                     │  • Action    │
                     │    legality  │
                     │  • Risk      │
                     │    bounds    │
                     └──────┬───────┘
                            │ Authorized Action
                            ▼
                     ┌──────────────┐
                     │  EP4:        │
                     │  Execution   │
                     │              │
     ┌───────────────┤  Components: │
     │               │  • Ghost     │
     │               │    Adapter   │
     │               │  • Risk      │
     │               │    Gates     │
     │               │  • Position  │
     │               │    Tracker   │
     │               │  • Exchange  │
     │               │    Adapter   │
     │               └──────┬───────┘
     │                      │
     │                  Execution
     │                  Outcome
     │                      │
     ▼                      ▼
┌───────────────────────────────────┐
│    logs/execution.db              │
│  • ghost_trades                   │
│  • policy_outcomes                │
│  • mandates                       │
│  • arbitration_results            │
└───────────────────────────────────┘
```

---

## 4. Position State Machine

```
                    ┌───────────────────┐
                    │       FLAT        │
                    │  (No Position)    │
                    └─────────┬─────────┘
                              │
                         ENTRY mandate
                              │
                              ▼
                    ┌───────────────────┐
            ┌───────│     ENTERING      │
            │       │  (Order Pending)  │
            │       └─────────┬─────────┘
            │                 │
       FAILURE            SUCCESS
     (Order Rejected)   (Order Filled)
            │                 │
            │                 ▼
            │       ┌───────────────────┐
            │       │       OPEN        │────┐
            │       │  (Position Active)│    │
            │       └─────────┬─────────┘    │
            │                 │               │
            │          EXIT mandate       REDUCE
            │                 │            mandate
            │                 ▼               │
            │       ┌───────────────────┐    │
            │   ┌───│      EXITING      │    │
            │   │   │  (Closing Order)  │    │
            │   │   └─────────┬─────────┘    │
            │   │             │               │
            │   │         SUCCESS             │
            │   │     (Order Filled)          │
            │   │             │               │
            │   │             ▼               │
            │   │   ┌───────────────────┐    │
            └───┼───│       FLAT        │    │
                │   │  (Position Closed)│    │
                │   └───────────────────┘    │
                │                             │
                │                             ▼
                │                   ┌───────────────────┐
                └───────────────────│     REDUCING      │
                    FAILURE         │  (Partial Close)  │
                (Order Rejected)    └─────────┬─────────┘
                                              │
                                          SUCCESS
                                      (Partial Filled)
                                              │
                                              ▼
                                    ┌───────────────────┐
                                    │       OPEN        │
                                    │  (Reduced Size)   │
                                    └───────────────────┘
```

---

## 5. Data Flow Diagram

```
┌─────────────┐
│ Hyperliquid │
│  Exchange   │
└──────┬──────┘
       │ WebSocket
       │ (trades, liq, depth)
       ▼
┌─────────────────────────┐
│  M1: Ingestion Engine   │
│  • Normalize events     │
│  • Route by symbol      │
└──────┬──────────────────┘
       │ Normalized Events
       ▼
┌─────────────────────────┐
│  M2: Continuity Memory  │
│  • Create/update nodes  │
│  • Track node lifecycle │
└──────┬──────────────────┘
       │ Node State
       ▼
┌─────────────────────────┐
│  M3: Temporal Engine    │
│  • Sequence events      │
│  • Enforce monotonicity │
└──────┬──────────────────┘
       │ Sequenced Events
       ▼
┌─────────────────────────┐
│ M4: Compute Primitives  │
│  • 19 primitives        │
│  • Per cycle, per sym   │
└──────┬──────────────────┘
       │ M4PrimitiveBundle
       ▼
┌─────────────────────────┐
│  M5: Governance Layer   │
│  • Orchestrate M4       │
│  • Generate snapshot    │
└──────┬──────────────────┘
       │ ObservationSnapshot
       │
       ├──────────────────────────────┐
       │                              │
       ▼                              ▼
┌─────────────────┐          ┌───────────────────┐
│ logs/execution  │          │  EP2: Strategies  │
│ .db             │          │  • Evaluate prims │
│ primitive_values│          │  • Generate       │
│ m2_nodes        │          │    mandates       │
│ execution_cycles│          └────────┬──────────┘
└─────────────────┘                   │ Mandates
                                      │
                                      ▼
                             ┌────────────────────┐
                             │ EP3: Arbitration   │
                             │  • Resolve         │
                             │    conflicts       │
                             │  • EXIT supremacy  │
                             └────────┬───────────┘
                                      │ Single Action
                                      ▼
                             ┌────────────────────┐
                             │  M6: Permission    │
                             │  • Validate action │
                             │  • Check invariants│
                             └────────┬───────────┘
                                      │ Authorized
                                      ▼
                             ┌────────────────────┐
                             │ EP4: Execution     │
                             │  • Ghost adapter   │
                             │  • Risk gates      │
                             │  • Position track  │
                             └────────┬───────────┘
                                      │ Outcome
                                      ▼
                             ┌────────────────────┐
                             │ logs/execution.db  │
                             │  ghost_trades      │
                             │  mandates          │
                             │  arbitration_res   │
                             │  policy_outcomes   │
                             └────────────────────┘
```

---

## 6. Risk Invariant Validation Flow

```
                        ENTRY Mandate
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Risk Invariant Validators    │
              │  (runtime/risk/invariants.py) │
              ├───────────────────────────────┤
              │                               │
              │  R1: Position Risk Cap        │◀─── RiskConfig
              │      MaxLoss ≤ RiskFraction×E │     (constants)
              │                               │
              │  R2: Leverage Cap             │
              │      Leverage ≤ L_max         │
              │                               │
              │  R3: Liquidation Buffer       │
              │      Distance ≥ D_min_safe    │
              │                               │
              │  R5: Total Exposure Cap       │
              │      Σ Exposure ≤ L_max × E   │
              │                               │
              │  R6: Symbol Exposure Cap      │
              │      Exposure ≤ L_symbol × E  │
              │                               │
              │  R13: No Averaging Down       │
              │       New entry ≥ Old entry   │
              │                               │
              │  R14: Free Margin Floor       │
              │       Free ≥ Min%              │
              └───────┬───────────────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
    PASS (valid=True)      FAIL (valid=False)
         │                         │
         │                    Block Action
         │                    Log Violation
         │                         │
         ▼                         ▼
    Continue to                  Return
    Execution                 ValidationResult
         │                    (blocking=True)
         ▼
┌────────────────────┐
│  EP4: Execution    │
│  • Ghost adapter   │
│  • Create position │
│  • Log ghost trade │
└────────────────────┘
```

---

## 7. Constitutional Layer Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                  OBSERVATION ZONE (M1-M5)                       │
│                                                                 │
│  Properties:                                                    │
│  • Pure observation (no execution calls)                        │
│  • No interpretation or prediction                              │
│  • Deterministic computation                                    │
│  • Constitutional silence (UNINITIALIZED or FAILED only)        │
│                                                                 │
│  May NOT:                                                       │
│  • Call execution functions                                     │
│  • Generate mandates                                            │
│  • Access position state                                        │
│  • Claim system health                                          │
│                                                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ ObservationSnapshot
                         │ (one-way boundary)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│            POLICY & EXECUTION ZONE (EP2-EP4, M6)               │
│                                                                 │
│  Properties:                                                    │
│  • Reads observation snapshots                                  │
│  • Generates mandates (EP2)                                     │
│  • Resolves conflicts (EP3)                                     │
│  • Enforces constraints (M6)                                    │
│  • Executes trades (EP4)                                        │
│                                                                 │
│  May NOT:                                                       │
│  • Call M1-M5 internal functions                                │
│  • Modify observation state                                     │
│  • Bypass risk invariants                                       │
│  • Claim interpretation                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

        Constitutional Enforcement:
        • Directory-scoped imports
        • Pre-commit hook validation
        • CI pipeline checks
```

---

## 8. Database Schema Relationships

```
┌──────────────────────────────────────────────────────────────────┐
│                     logs/execution.db                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  execution_cycles (cycle_id PK, start_ts, end_ts)              │
│         │                                                        │
│         ├──▶ m2_nodes (cycle_id FK, node_id, price_center, ...) │
│         │                                                        │
│         ├──▶ primitive_values (cycle_id FK, symbol,             │
│         │         zone_penetration_depth, velocity,              │
│         │         compactness, ... 25 columns)                   │
│         │                                                        │
│         ├──▶ policy_evaluations (cycle_id FK, symbol,           │
│         │         policy_type, proposed_action)                  │
│         │                                                        │
│         ├──▶ mandates (cycle_id FK, symbol, mandate_type,       │
│         │         policy_source, timestamp)                      │
│         │                                                        │
│         └──▶ arbitration_results (cycle_id FK, symbol,          │
│                 final_action, mandate_count)                     │
│                                                                  │
│  ghost_trades (trade_id PK, symbol, direction,                  │
│         entry_ts, exit_ts, entry_price, exit_price,             │
│         quantity, pnl, holding_duration_sec)                     │
│         │                                                        │
│         └──▶ policy_outcomes (trade_id FK, outcome_type,        │
│                 attribution_policy)                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Foreign Key Relationships:
• cycle_id ties all per-cycle tables together
• trade_id links ghost_trades to outcomes
• No circular dependencies
• Append-only logs (no updates)
```

---

## 9. File System Organization

```
liquidation-trading/
│
├── observation/                  # M1-M5 layers
│   ├── governance.py            # M5 orchestration
│   ├── types.py                 # Core observation types
│   └── internal/
│       ├── m1_ingestion.py      # Raw data ingestion
│       └── m3_temporal.py       # Event sequencing
│
├── memory/                       # M2 + M4 primitives
│   ├── m2_continuity_store.py   # Memory node store
│   ├── m4_zone_geometry.py      # Zone primitives
│   ├── m4_traversal_kinematics.py
│   ├── m4_price_distribution.py
│   ├── m4_structural_absence.py
│   ├── m4_structural_persistence.py
│   ├── m4_trade_flow.py
│   ├── m4_liquidation_clustering.py
│   └── ...                      # Other M4 modules
│
├── external_policy/              # EP2-EP3
│   ├── ep2_strategy_geometry.py
│   ├── ep2_strategy_kinematics.py
│   ├── ep2_strategy_absence.py
│   └── ep3_arbitration.py
│
├── execution/                    # EP4
│   ├── ep4_execution.py
│   ├── ep4_ghost_adapter.py
│   ├── ep4_risk_gates.py
│   └── ep4_exchange_adapter.py
│
├── runtime/                      # Integration & M6
│   ├── collector/
│   │   └── service.py           # Main collector
│   ├── policy_adapter.py        # Primitive routing
│   ├── m6_executor.py           # Permission layer
│   ├── position/
│   │   ├── types.py             # Position types
│   │   └── state_machine.py    # State transitions
│   └── risk/
│       ├── types.py             # Risk types
│       ├── calculator.py        # Risk calculations
│       └── invariants.py        # R1-R15 validators
│
├── logs/
│   └── execution.db             # SQLite database
│
└── docs/                         # Constitutional documents
    ├── EPISTEMIC_CONSTITUTION.md
    ├── SYSTEM_CANON.md
    ├── RISK&EXPOSUREINVARIANTS.md
    └── PROJECT SPECIFICATION.md
```

---

## 10. Calibration Workflow

```
                        Stage 1A: Baseline (24-48h)
                    ┌────────────────────────────┐
                    │  Permissive Thresholds     │
                    │  • zone > 0                │
                    │  • compactness > 0         │
                    │  • deviation > 0           │
                    └──────────┬─────────────────┘
                               │ Collect 10k+ cycles
                               ▼
                    ┌────────────────────────────┐
                    │  Percentile Analysis       │
                    │  • P50, P75, P90, P95, P99 │
                    │  • Per primitive           │
                    │  • Per symbol              │
                    └──────────┬─────────────────┘
                               │ Use P95 as test thresholds
                               ▼
                        Stage 1B: Test (12-24h)
                    ┌────────────────────────────┐
                    │  Restrictive Thresholds    │
                    │  • zone > P95              │
                    │  • compactness > P95       │
                    │  • deviation > P95         │
                    └──────────┬─────────────────┘
                               │ Collect 100+ trades
                               ▼
                    ┌────────────────────────────┐
                    │  Verify EXIT Logic         │
                    │  • EXIT mandates > 0       │
                    │  • Outcome diversity OK    │
                    │  • Trade frequency < 10/hr │
                    └──────────┬─────────────────┘
                               │ If EXIT working
                               ▼
                        Stage 2: Sweep (7-14 days)
      ┌────────────────────────────────────────────────────┐
      │  Test 125 Configurations                           │
      │  • 5 × 5 × 5 grid (P50, P70, P85, P95, P99)       │
      │  • Adaptive pruning (eliminate underperformers)    │
      │  • 20+ trades per config                           │
      └──────────┬─────────────────────────────────────────┘
                 │ Collect per-config metrics
                 ▼
      ┌────────────────────────────────────────────────────┐
      │  Pareto Frontier Analysis                          │
      │  • Selectivity (mandates/hour)                     │
      │  • Outcome diversity (win rate balance)            │
      │  • Duration consistency (low variance)             │
      │  • Identify 3-5 non-dominated configs              │
      └──────────┬─────────────────────────────────────────┘
                 │ Select configuration
                 ▼
      ┌────────────────────────────────────────────────────┐
      │  Hold-Out Validation                               │
      │  • Apply to last 25% of data                       │
      │  • Verify metrics stable                           │
      │  • K-S test for distribution similarity            │
      └──────────┬─────────────────────────────────────────┘
                 │ If validation passes
                 ▼
      ┌────────────────────────────────────────────────────┐
      │  Deployment                                        │
      │  • Update strategy thresholds                      │
      │  • 48-hour smoke test                              │
      │  • Monitor for stability                           │
      └────────────────────────────────────────────────────┘
```

---

## Legend

```
───▶   Data flow (one direction)
◀───   Bidirectional communication
 │     Vertical flow
 ▼     Downward flow
┌──┐   Component/Module
├──┤   List/Table row
FK     Foreign Key
PK     Primary Key
```

---

## Notes

These diagrams represent the **Constitutional Execution System as of 2026-01-14**.

**Changes require constitutional review:**
- Any new layer
- Any cross-layer dependency
- Any change to state machine transitions
- Any modification to risk invariants

**See:**
- `docs/CODE_FREEZE.md` for modification policy
- `docs/EPISTEMIC_CONSTITUTION.md` for epistemic rules
- `docs/SYSTEM_CANON.md` for vocabulary and boundaries
