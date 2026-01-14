# Constitutional Execution System

## Overview

The **Constitutional Execution System** is a formally constrained trading execution substrate that operates under strict epistemic and architectural rules. It observes market structure through a layered observation stack (M1-M6), evaluates conditions via policy strategies (EP2-EP4), and executes via ghost trading with constitutional risk constraints.

**Core Principle**: This system is constitution-driven. It does not interpret, predict, or make discretionary decisions. All behavior is deterministic and provably constrained.

---

## System Architecture

### Observation Layers (M1-M5)

```
M1: Ingestion Engine
├── Raw market data (trades, liquidations, orderbook)
├── Event normalization
└── Temporal sequencing

M2: Continuity Memory
├── Price level memory nodes
├── Liquidity structure tracking
└── Node lifecycle management (ACTIVE → DORMANT → ARCHIVED)

M3: Temporal Engine
├── Event sequencing
├── Time monotonicity enforcement
└── Causality preservation

M4: Primitive Computation (19 primitives)
├── Zone Geometry: penetration depth, displacement anchor
├── Traversal Kinematics: velocity, compactness
├── Central Tendency: price distribution deviation
├── Structural Absence/Persistence: node presence over time
├── Trade Flow: directional continuity, burst detection
├── Liquidation Clustering: spatial concentration
└── Order Book: resting size, consumption, absorption, refill

M5: Governance Layer
├── Orchestrates M4 primitive computation
├── Generates observation snapshots
├── Enforces invariants (time monotonicity, data completeness)
└── Exposes ONLY: status (UNINITIALIZED or FAILED), timestamp, symbols
```

### Policy & Execution Layers (EP2-EP4, M6)

```
EP2: Strategy Policies
├── Geometry Strategy: zone penetration conditions
├── Kinematics Strategy: traversal velocity/compactness conditions
└── Absence Strategy: structural absence/persistence conditions

EP3: Arbitration
├── Deterministic mandate conflict resolution
├── EXIT supremacy enforcement
└── Single action emission per cycle

EP4: Execution
├── Ghost Trading: simulated position lifecycle
├── Risk Gates: R1-R15 invariant validation
├── Exchange Adapter: order submission (future)
└── Position Tracking: FLAT → ENTERING → OPEN → REDUCING → EXITING

M6: Permission Layer
├── Execution permission enforcement
├── Constitutional constraint validation
└── No observation interpretation
```

---

## Quick Start

### Prerequisites

```bash
# Python 3.11+
python --version

# Install dependencies
pip install websockets requests pandas

# Verify database exists
ls logs/execution.db
```

### Launch System

**Ghost Trading Mode** (no real capital):

```bash
# Start collector service (runtime/collector/service.py)
python runtime/native_app/main.py

# System will:
# 1. Connect to Hyperliquid WebSocket streams
# 2. Populate M1-M5 observation layers
# 3. Compute 19 M4 primitives per cycle
# 4. Evaluate EP2 strategy policies
# 5. Arbitrate mandates (EP3)
# 6. Execute ghost trades (EP4)
# 7. Log all data to logs/execution.db
```

**Expected Output**:
```
[INFO] ObservationSystem initialized for 10 symbols
[INFO] Warmup period: 300 seconds
[INFO] Cycle 1: 8 primitives computed
[INFO] Ghost trade opened: BTC LONG @ $43250.50
[INFO] Ghost trade exited: BTC LONG @ $43275.20 | PNL: $24.70
```

---

## Database Schema

All system activity logged to `logs/execution.db`:

```
execution_cycles      - Cycle metadata, timestamps
m2_nodes              - Memory node state snapshots
primitive_values      - All 19 M4 primitive values (per cycle, per symbol)
policy_evaluations    - Policy decision tracking
mandates              - Mandate generation log (ENTRY, EXIT, REDUCE)
arbitration_results   - Arbitration outcomes
ghost_trades          - Ghost trade lifecycle (entry_ts, exit_ts, pnl)
policy_outcomes       - Trade outcome attribution
```

---

## Key Concepts

### Constitutional Constraints

**Epistemic Constitution (EPISTEMIC_CONSTITUTION.md)**:
- System may NEVER claim: health, readiness, correctness, quality
- Silence Rule: Say nothing when truth cannot be proven
- Failure Rule: Halt on time reversal, invariant violation
- Exposure Rule: Only expose status (UNINITIALIZED or FAILED), timestamp, symbols

**Semantic Canon (SYSTEM_CANON.md)**:
- Allowed vocabulary: Observation, Structure, Event, Threshold exceedance
- Forbidden vocabulary: Signal, Setup, Opportunity, Bias, Edge, Confidence

### Risk Mathematics (R1-R15 Invariants)

All position sizing and risk management governed by 15 constitutional invariants:

- **R1**: MaxLoss(symbol) ≤ RiskFraction × Equity
- **R2**: Leverage(symbol) ≤ MaxLeverage
- **R3**: DistanceToLiquidation(symbol) ≥ MinLiquidationBuffer
- **R5**: Σ PositionNotional(all symbols) ≤ ExposureCap × Equity
- **R6**: PositionNotional(symbol) ≤ SymbolExposureCap × Equity
- **R7**: Risk limits apply identically to LONG and SHORT
- **R9**: REDUCE must be attempted before EXIT
- **R12**: Partial exits only if post-reduce state satisfies all invariants
- **R13**: No additional ENTRY if it increases MaxLoss or reduces buffer
- **R14**: FreeMargin ≥ MinFreeMargin

See: `docs/RISK&EXPOSUREINVARIANTS.md`

### Primitive Computation

19 M4 primitives computed per cycle, per symbol:

| Primitive | Category | Description |
|-----------|----------|-------------|
| zone_penetration | Geometry | Price penetration into historical zones |
| displacement_origin_anchor | Geometry | Pre-traversal anchor region |
| price_traversal_velocity | Kinematics | Rate of price movement |
| traversal_compactness | Kinematics | Trade density over price range |
| central_tendency_deviation | Distribution | Deviation from price center |
| structural_absence_duration | Absence | Duration nodes absent from observation window |
| traversal_void_span | Absence | Maximum gap between trade timestamps |
| event_non_occurrence_counter | Absence | Expected vs observed symbol count |
| structural_persistence_duration | Persistence | Duration nodes present in observation window |
| price_acceptance_ratio | Acceptance | OHLC body vs wick ratio |
| liquidation_density | Liquidation | Spatial concentration of liquidations |
| directional_continuity | Trade Flow | Consistency of trade direction |
| trade_burst | Trade Flow | Maximum trade density in 1s window |
| resting_size | Order Book | Size at best bid/ask |
| order_consumption | Order Book | Reduction in resting size |
| absorption_event | Order Book | Complete level consumption |
| refill_event | Order Book | Level replenishment |
| order_block | Pattern | M2 node concentration |
| supply_demand_zone | Pattern | M2 cluster formation |

---

## Ghost Trading

**Purpose**: Validate system logic without real capital risk.

**Lifecycle**:
1. **ENTRY**: Mandate generated when primitives exceed thresholds
2. **OPEN**: Ghost position tracked with simulated entry price
3. **EXIT**: Mandate generated when entry conditions no longer met
4. **PNL**: Calculated as (exit_price - entry_price) × quantity

**Database**: `ghost_trades` table tracks all entry/exit pairs with PNL.

---

## Configuration

### Risk Parameters (runtime/risk/types.py)

```python
RiskConfig(
    L_max=10.0,              # Maximum total leverage
    L_target=8.0,            # Operational target leverage
    L_symbol_max=5.0,        # Per-symbol maximum leverage
    D_min_safe=0.08,         # 8% minimum liquidation distance
    D_critical=0.03,         # 3% immediate exit threshold
    risk_fraction_per_trade=0.02,  # 2% max loss per trade
    min_free_margin_pct=0.10       # 10% minimum free margin
)
```

### Symbols (runtime/collector/service.py)

```python
TOP_10_SYMBOLS = [
    'BTC', 'ETH', 'SOL', 'ARB', 'OP',
    'AVAX', 'MATIC', 'DOGE', 'XRP', 'ADA'
]
```

---

## Testing

### Unit Tests

```bash
# M4 primitive tests
pytest memory/test_m4_*.py -v

# Policy strategy tests
pytest external_policy/test_ep2_*.py -v

# Arbitration tests
pytest external_policy/test_ep3_*.py -v

# Execution tests
pytest execution/test_ep4_*.py -v

# Risk invariant tests
pytest runtime/risk/tests/test_invariants.py -v
```

### Integration Tests

```bash
# Full observation system test
pytest tests/integration/test_observation_system.py -v

# Exit lifecycle test
pytest runtime/executor/tests/test_exit_lifecycle.py -v
```

---

## Operational Stages

### Stage 1A: Baseline Collection (24-48 hours)

**Goal**: Establish primitive value distributions

```bash
# Run with permissive thresholds
python scripts/stage_1a_baseline_collection.py --duration 48h

# Analyze distributions
python scripts/analyze_stage_1a_distributions.py
```

**Output**: Percentile tables (P1, P5, P10, P25, P50, P75, P90, P95, P99) per primitive.

### Stage 1B: Test Thresholds (12-24 hours)

**Goal**: Generate ghost trades for outcome attribution

```bash
# Apply P95 thresholds from Stage 1A
# Verify EXIT mandates generating
# Collect 100+ completed trades
```

### Stage 2: Threshold Sweep (7-14 days)

**Goal**: Test 125 threshold combinations, identify Pareto frontier

**Method**: Adaptive pruning (eliminate bottom quartile every 24h)

---

## Key Files

```
observation/
├── governance.py              # M5 orchestration
├── internal/
│   ├── m1_ingestion.py       # Raw data ingestion
│   └── m3_temporal.py        # Event sequencing
└── types.py                  # Core types

memory/
├── m2_continuity_store.py    # Memory node store
├── m4_*.py                   # Primitive computation modules
└── M3_MASTER_SPECIFICATION.md

external_policy/
├── ep2_strategy_geometry.py  # Zone geometry policy
├── ep2_strategy_kinematics.py # Traversal kinematics policy
└── ep2_strategy_absence.py   # Structural absence policy

execution/
├── ep4_execution.py          # Core execution logic
├── ep4_ghost_adapter.py      # Ghost trading adapter
└── ep4_risk_gates.py         # Risk invariant gates

runtime/
├── collector/service.py      # Main collector service
├── policy_adapter.py         # Policy routing
├── m6_executor.py            # Permission layer
└── risk/
    ├── invariants.py         # R1-R15 validators
    ├── calculator.py         # Risk calculations
    └── types.py              # Risk data structures

docs/
├── EPISTEMIC_CONSTITUTION.md # Absolute epistemic rules
├── SYSTEM_CANON.md           # Single source of truth
├── RISK&EXPOSUREINVARIANTS.md # 15 risk invariants
└── PROJECT SPECIFICATION — CONSTITUTIONAL EXECUTION SYSTEM.md
```

---

## System Status

| Component | Status | Notes |
|-----------|--------|-------|
| **M1-M5 Observation Stack** | ✅ Operational | All 19 primitives computing |
| **EP2-EP4 Policy/Execution** | ✅ Operational | Ghost trading functional |
| **Risk Mathematics (R1-R15)** | ✅ Implemented | Formal invariant validators |
| **Ghost Trading** | ✅ Operational | Entry/exit lifecycle complete |
| **Real Execution** | ⏳ Pending | Exchange adapter not connected |
| **Threshold Calibration** | ⏳ Pending | Stage 1A baseline collection |

---

## What This System Does NOT Do

❌ Make predictions about future price movements
❌ Interpret market conditions as "bullish" or "bearish"
❌ Use indicators, machine learning, or pattern recognition
❌ Provide investment advice or trading signals
❌ Claim any edge, alpha, or statistical advantage
❌ Optimize for profitability or win rate
❌ Trade without explicit constitutional authorization

**This system observes structure and executes under constraint. Nothing more.**

---

## Frozen Components (CODE_FREEZE.md)

**No modifications without logged evidence**:
- All M1-M5 observation layers
- All M4 primitive computation
- M6 permission layer
- All EP2-EP4 policy/execution modules

**To modify frozen code**:
1. Provide logged evidence from live runs
2. Document specific timestamp of failure
3. Show primitive outputs revealing structural ambiguity
4. Obtain authorization

---

## Documentation

### Constitutional Documents
- **[EPISTEMIC_CONSTITUTION.md](docs/EPISTEMIC_CONSTITUTION.md)** - Absolute epistemic rules
- **[SYSTEM_CANON.md](docs/SYSTEM_CANON.md)** - Vocabulary, layer definitions, rejected paths
- **[CODE_FREEZE.md](docs/CODE_FREEZE.md)** - Frozen component policy

### Technical Specifications
- **[PROJECT SPECIFICATION.md](docs/PROJECT%20SPECIFICATION%20%E2%80%94%20CONSTITUTIONAL%20EXECUTION%20SYSTEM.md)** - Complete system spec
- **[RISK&EXPOSUREINVARIANTS.md](docs/RISK&EXPOSUREINVARIANTS.md)** - 15 risk invariants (R1-R15)
- **[M3_MASTER_SPECIFICATION.md](memory/M3_MASTER_SPECIFICATION.md)** - Temporal engine spec

### Implementation Status
- **[MISSING_COMPONENTS_AUDIT.md](MISSING_COMPONENTS_AUDIT.md)** - P1-P3 priority gaps
- **[PRIMITIVE_IMPLEMENTATION_STATUS.md](PRIMITIVE_IMPLEMENTATION_STATUS.md)** - All 19 M4 primitives

---

## Troubleshooting

### Database locked error
```bash
# Another process accessing logs/execution.db
# Stop all python processes
taskkill /F /IM python.exe

# Remove lock file
rm logs/execution.db-wal
```

### Primitives not computing
```bash
# Check database
python check_primitives_quick.py

# Expected: 8+ primitives at 90% rate
# If 0%, check M1 ingestion
```

### Ghost trades exit immediately
**Cause**: EXIT mandates generating due to None primitive values being treated as "conditions false"

**Fix**: Verify primitive extraction in `runtime/collector/service.py`

### Time regression error
**Cause**: Websocket timestamp < last processed timestamp

**System will HALT** (constitutional requirement). Restart collector.

---

## License & Disclaimer

**Internal Research Use Only**

This system is a research prototype for exploring constitutional constraints in automated trading systems. It is NOT production-ready and does NOT provide investment advice.

**All trading involves risk of loss. Use at your own risk.**

---

## Contact

For questions about frozen layer modifications, constitutional interpretation, or system architecture, refer to:
- `docs/EPISTEMIC_CONSTITUTION.md` (authority on epistemic rules)
- `docs/SYSTEM_CANON.md` (authority on vocabulary and layer boundaries)
- `CODE_FREEZE.md` (authority on modification policy)

**This system is frozen by design. Correctness > features. Silence > speculation.**
