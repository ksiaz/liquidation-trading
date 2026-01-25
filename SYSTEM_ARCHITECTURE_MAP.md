# SYSTEM ARCHITECTURE MAP
**Status:** Cartography Report
**Date:** 2026-01-25
**Purpose:** Navigation Manual for Agent & Human Understanding
**Authority:** Code Inspection + Constitutional Documents

---

## 0. CRITICAL READING NOTES

**This document is a map, not a specification.**
- It describes what EXISTS, not what SHOULD exist
- It marks UNCERTAIN where code behavior is ambiguous
- It identifies MISMATCHES between constitution and implementation
- It does NOT propose fixes or improvements

**For Future Agents:**
- Read this FIRST before touching code
- Trust marked uncertainties
- Do not assume standard trading system behavior
- Verify every claim against current code if in doubt

---

## 1. SYSTEM BOUNDARY ENUMERATION

### 1.1 M1 — Ingestion Layer

**Location:** `observation/internal/m1_ingestion.py`

**Responsibility:**
- Normalize raw external event payloads (Binance format → canonical schema)
- Maintain fixed-size raw event buffers (per symbol)
- Track ingestion counters

**Inputs:**
- Raw Binance WebSocket payloads (trades, liquidations, depth, mark_price, kline, OI)
- Symbol string
- Event type discriminator

**Outputs:**
- Normalized event dictionaries with fields:
  - `timestamp` (float, seconds)
  - `symbol` (str)
  - `price` (float)
  - `quantity` (float)
  - `side` ("BUY" | "SELL")
  - Event-specific fields

**Forbidden Knowledge:**
- Must NOT filter by "importance"
- Must NOT make time-based decisions
- Must NOT label events semantically
- Must NOT rank or score events

**State:**
- Stateful (maintains buffers)
- Counters: trades, liquidations, klines, oi, depth_updates, mark_price_updates, errors

**Constitution Compliance:** ✓ (Observation only, no interpretation)

---

### 1.2 M2 — Continuity Memory

**Location:** `memory/m2_continuity_store.py`

**Responsibility:**
- Track price-based memory node identity over time
- Manage three-state lifecycle: ACTIVE → DORMANT → ARCHIVED
- Maintain node presence intervals
- Apply time-based decay
- Store trade/liquidation interaction evidence

**Inputs:**
- `ingest_trade()`: symbol, price, side, volume, is_buyer_maker, timestamp
- `ingest_liquidation()`: symbol, price, side, volume, timestamp
- `update_orderbook_state()`: symbol, price, size, side, timestamp
- `update_mark_price_state()`: symbol, mark_price, index_price, timestamp
- `advance_time()`: current timestamp

**Outputs:**
- `get_active_nodes(symbol)`: List[EnrichedLiquidityMemoryNode]
- `get_node(node_id)`: EnrichedLiquidityMemoryNode | None
- `get_metrics()`: Dict (node counts by state)

**Forbidden Knowledge:**
- Must NOT rank nodes by "strength" or "quality"
- Must NOT predict node lifecycle transitions
- Must NOT label nodes semantically ("strong", "will persist")

**State:**
- Stateful (maintains 3 collections: _active_nodes, _dormant_nodes, _archived_nodes)
- Tracks: total_nodes_created, total_interactions, last_state_update_ts

**Memory Node Structure (EnrichedLiquidityMemoryNode):**
- `id`: str (unique identifier)
- `symbol`: str
- `price_center`: float
- `price_band`: float
- `side`: str ("BID" | "ASK")
- `first_seen_ts`: float
- `last_interaction_ts`: float
- `strength`: float (0-1, decays over time)
- `confidence`: float (0-1)
- `creation_reason`: str (audit trail)
- `active`: bool
- `decay_rate`: float
- `liquidation_count`: int
- `trade_execution_count`: int
- `presence_intervals`: List[Tuple[float, float]]
- `interaction_timestamps`: List[float]
- `resting_size_bid/ask`: float
- `previous_resting_size_bid/ask`: float
- `last_orderbook_update_ts`: float | None

**Constitutional Concern:**
⚠️ SEMANTIC LEAK: Node contains `strength` and `confidence` fields which are evaluative metrics.
- MITIGATION: These are internal only, NOT exposed via M5 queries or observation snapshots
- STATUS: Acceptable per internal-only exception

---

### 1.3 M3 — Temporal Ordering

**Location:** `observation/internal/m3_temporal.py`

**Responsibility:**
- Maintain chronological sequence of evidence tokens
- Enforce time window boundaries
- Track recent price history (for M4 primitives)
- Provide candle snapshots (OHLC)

**Inputs:**
- `process_trade()`: timestamp, symbol, price, quantity, side
- `advance_time()`: new_timestamp

**Outputs:**
- `get_recent_prices(symbol, max_count)`: List[float]
- `get_current_candle(symbol)`: Dict | None (keys: open, high, low, close)

**Forbidden Knowledge:**
- Must NOT score event importance
- Must NOT infer causality
- Must NOT predict next event

**State:**
- Stateful (maintains sequence buffers per symbol)
- Buffer type: UNCERTAIN (likely deque or similar)

**Constitution Compliance:** ✓ (Temporal ordering only, no interpretation)

---

### 1.4 M4 — Contextual Views (Primitives)

**Location:** `memory/m4_*.py` (17 primitive modules)

**Responsibility:**
- Compute read-only analytical perspectives on memory state
- Return frozen dataclass primitives
- Validate inputs, return None if insufficient data

**Primitive Catalog:**

**Tier A — Zone Geometry:**
- `m4_zone_geometry`: ZonePenetrationDepth, DisplacementOriginAnchor
  - `compute_zone_penetration_depth()`
  - `identify_displacement_origin_anchor()`

**Tier A — Traversal Kinematics:**
- `m4_traversal_kinematics`: PriceTraversalVelocity, TraversalCompactness
  - `compute_price_traversal_velocity()`
  - `compute_traversal_compactness()`

**Tier A — Price Distribution:**
- `m4_price_distribution`: PriceAcceptanceRatio, CentralTendencyDeviation
  - `compute_price_acceptance_ratio()`
  - `compute_central_tendency_deviation()`

**Tier B-1 — Structural Absence:**
- `m4_structural_absence`: StructuralAbsenceDuration
- `m4_traversal_voids`: TraversalVoidSpan
- `m4_event_absence`: EventNonOccurrenceCounter

**Tier B-2 — Structural Persistence:**
- `m4_structural_persistence`: StructuralPersistenceDuration
- `m4_structural_exposure`: StructuralExposureCount

**Order Book Primitives:**
- `m4_orderbook`: RestingSizeAtPrice, OrderConsumption, AbsorptionEvent, RefillEvent

**Additional Primitives:**
- `m4_liquidation_density`: LiquidationDensity
- `m4_directional_continuity`: DirectionalContinuity
- `m4_trade_burst`: TradeBurst

**Inputs:**
- M2 node state (read-only queries)
- M3 price sequences
- Timestamps, price ranges, node IDs

**Outputs:**
- Frozen dataclasses (immutable)
- OR None (if insufficient data or no structural condition)

**Forbidden Knowledge:**
- Must NOT rank views by quality
- Must NOT interpret metrics as signals
- Must NOT combine into composite scores

**Constitution Compliance:** ✓ (Pure computation, no interpretation)

---

### 1.5 M5 — Governance & Access Control

**Location:** `memory/m5_access.py`, `memory/m5_query_schemas.py`

**Responsibility:**
- Sole legal interface to observation state
- Validate query schemas
- Reject forbidden semantics
- Enforce epistemic safety
- Route queries to M2/M3/M4

**Inputs:**
- Query type string (e.g., "IDENTITY_QUERY")
- Query parameters dict

**Query Types Allowed:**
- `IdentityQuery`: Get node by ID
- `LocalContextQuery`: Get M4 view for node
- `TemporalSequenceQuery`: Get evidence tokens
- `SpatialGroupQuery`: Get nodes in price range
- `StateDistributionQuery`: Get node counts by state
- `ProximityQuery`: Get nodes near price
- M4 primitive queries (17 types)

**Outputs:**
- Query results (dicts or lists)
- Normalized, epistemic-safe data

**Forbidden Queries (Rejected):**
- `{"sort_by": "strength"}`
- `{"filter": "profitable_zones"}`
- `{"top_n": 10, "ranked_by": "activity"}`
- Any query with: STRONG_, WEAK_, BUY, SELL, PROFIT, LOSS, SCORE, RANK, GOOD, BAD, BULL, BEAR, ENTRY, EXIT

**Enforcement Mechanism:**
- `run_guards()`: Pre-validation on raw params
- Schema validation: Dataclass instantiation
- Type enforcement: Runtime primitive checks
- Normalization: Clean output

**Constitution Compliance:** ✓ (Firewall enforcement active)

---

### 1.6 Observation System (Sealed Facade)

**Location:** `observation/governance.py`

**Responsibility:**
- Orchestrate M1, M2, M3, M5
- Manage system time (advance_time)
- Produce ObservationSnapshot
- Compute M4 primitives ONCE per symbol per snapshot
- Track system status (UNINITIALIZED | ACTIVE | FAILED)

**Inputs:**
- `ingest_observation()`: timestamp, symbol, event_type, payload
- `advance_time()`: new_timestamp
- `query()`: query_spec dict

**Outputs:**
- `ObservationSnapshot` (frozen dataclass):
  - `status`: ObservationStatus
  - `timestamp`: float
  - `symbols_active`: List[str]
  - `counters`: SystemCounters (intervals_processed, dropped_events)
  - `promoted_events`: List[Dict] | None (UNUSED, always None)
  - `primitives`: Dict[str, M4PrimitiveBundle]

**M4PrimitiveBundle:**
Contains pre-computed primitives for ONE symbol:
- All 17 primitives (or None if insufficient data)

**System States:**
- `UNINITIALIZED`: Before first advance_time
- `ACTIVE`: Normal operation
- `FAILED`: Invariant violated (time regression, exception)

**Failure Triggers:**
- Time regression (new_timestamp < system_time)
- Unhandled exception in M1/M2/M3
- Invariant violation

**Constitution Compliance:** ✓ (Status enforcement, failure handling)

---

### 1.7 M6 — Execution Orchestrator (Stub)

**Location:** `runtime/m6_executor.py`

**Responsibility:**
- Consume ObservationSnapshot
- Invoke external policies (via PolicyAdapter)
- Trigger arbitration and execution
- Stateless, event-scoped

**Current Implementation:**
- MINIMAL STUB
- Validates observation status
- Raises SystemHaltedException if FAILED
- No actual execution logic

**Intended Behavior (NOT YET IMPLEMENTED):**
- Query primitives via M5
- Invoke external policies
- Collect mandates
- Pass to arbitration
- Execute actions

**Constitution Compliance:** ⚠️ INCOMPLETE (Stub only, not yet wired)

---

### 1.8 Runtime Collector Service

**Location:** `runtime/collector/service.py`

**Responsibility:**
- Drive system time (call advance_time every 100ms)
- Connect to Binance WebSocket streams
- Feed raw data to observation system
- Execute M6 cycle

**Inputs:**
- Binance WebSocket events (trades, liquidations, depth, mark_price)

**Outputs:**
- Observation snapshots
- M6 execution cycles (mandates, actions, results)

**M6 Execution Cycle:**
```
1. advance_time(current_time)
2. query snapshot
3. IF snapshot.status == ACTIVE:
   - Generate mandates (via PolicyAdapter)
   - Arbitrate mandates
   - Execute actions
   - Log results
```

**Constitution Compliance:** ✓ (Driver role, no interpretation)

---

### 1.9 Policy Adapter (Wiring Layer)

**Location:** `runtime/policy_adapter.py`

**Responsibility:**
- Pure wiring between observation and execution
- Extract M4 primitives from snapshot
- Invoke frozen external policies
- Convert proposals to mandates
- NO interpretation, NO aggregation

**Inputs:**
- `ObservationSnapshot`
- `symbol`: str
- `timestamp`: float

**Outputs:**
- `List[Mandate]`

**Process:**
```
1. Extract primitives from snapshot
2. Invoke external policies:
   - ep2_strategy_geometry
   - ep2_strategy_kinematics
   - ep2_strategy_absence
3. Convert proposals to Mandates
4. Return mandates
```

**Critical Logic:**
- `_extract_primitives()`: Reads pre-computed bundle from snapshot.primitives[symbol]
- Case-sensitivity handling: Tries symbol, symbol.lower(), symbol.upper()

**Constitution Compliance:** ✓ (Pure wiring, no decisions)

---

### 1.10 External Policies (Frozen)

**Location:** `external_policy/ep2_strategy_*.py`

**Strategies:**
1. **Geometry** (`ep2_strategy_geometry.py`):
   - Inputs: zone_penetration, traversal_compactness, central_tendency_deviation
   - Proposal: If ALL three non-null AND structural conditions met
   - Conditions: depth > 0, compactness > 0, deviation != 0

2. **Kinematics** (`ep2_strategy_kinematics.py`):
   - Inputs: velocity, compactness, acceptance
   - Proposal: If velocity, compactness present and conditions met

3. **Absence** (`ep2_strategy_absence.py`):
   - Inputs: absence, persistence, geometry
   - Proposal: If absence/persistence thresholds met

**Output:** `StrategyProposal` (frozen dataclass)
- `strategy_id`: str
- `action_type`: str (opaque)
- `confidence`: str (opaque label, NOT numeric)
- `justification_ref`: str
- `timestamp`: float

**Constitution Compliance:** ✓ (Stateless, frozen, no interpretation exposed)

---

### 1.11 Arbitration Layer

**Location:** `runtime/arbitration/arbitrator.py`

**Responsibility:**
- Resolve conflicting mandates deterministically
- Enforce EXIT supremacy
- BLOCK prevents ENTRY
- One action per symbol per cycle

**Inputs:**
- Set[Mandate] (for single symbol)

**Mandate Types:**
- ENTRY (priority 2)
- EXIT (priority 5, supreme)
- REDUCE (priority 3)
- HOLD (priority 1)
- BLOCK (priority 4, non-actionable)

**Outputs:**
- `Action` (single action per symbol)
- `ActionType`: ENTRY | EXIT | REDUCE | NO_ACTION

**Resolution Rules:**
1. EXIT always wins (Theorem 2.2)
2. BLOCK filters out ENTRY (Theorem 2.3)
3. Highest authority wins within type
4. Hierarchy: EXIT > REDUCE > ENTRY > HOLD

**Constitution Compliance:** ✓ (Deterministic, proven theorems)

---

### 1.12 Position State Machine

**Location:** `runtime/position/state_machine.py`

**Responsibility:**
- Enforce position lifecycle invariants
- Validate state transitions
- Maintain single-position-per-symbol invariant

**States:**
- FLAT (no position)
- ENTERING (order submitted)
- OPEN (position active)
- REDUCING (partial exit in progress)
- CLOSING (full exit in progress)

**Allowed Transitions (10):**
```
FLAT --[ENTRY]--> ENTERING
ENTERING --[SUCCESS]--> OPEN
ENTERING --[FAILURE]--> FLAT
OPEN --[REDUCE]--> REDUCING
OPEN --[EXIT]--> CLOSING
REDUCING --[PARTIAL]--> OPEN
REDUCING --[COMPLETE]--> CLOSING
CLOSING --[SUCCESS]--> FLAT
# X3-A Emergency Exit (cancel pending + market close)
ENTERING --[EMERGENCY_EXIT]--> CLOSING
REDUCING --[EMERGENCY_EXIT]--> CLOSING
```

**Forbidden Transitions (15):**
- All other combinations (rejected with InvariantViolation)

**Invariants Enforced:**
- Theorem 3.1: One position per symbol
- Theorem 4.1: Direction preservation (no reversal without EXIT)
- Theorem 7.1: REDUCE decreases quantity monotonically

**Constitution Compliance:** ✓ (Formally proven, deterministic)

---

### 1.13 Execution Controller

**Location:** `runtime/executor/controller.py`

**Responsibility:**
- Orchestrate mandate → action → execution flow
- Validate actions against state machine
- Enforce risk constraints
- Log execution results

**Process:**
```
1. Receive mandates from policies
2. Check risk invariants → emit protective mandates
3. Arbitrate all mandates
4. Validate ENTRY against risk
5. Validate action against state machine
6. Execute action → update position state
7. Log results
```

**Constitution Compliance:** ✓ (Orchestration only, no interpretation)

---

### 1.14 Execution Database (Research Logging)

**Location:** `runtime/logging/execution_db.py`

**Responsibility:**
- Log all execution cycles for research
- Capture M2 state, M4 primitives, mandates, arbitration, execution results
- 9 tables: cycles, m2_nodes, primitives, mandates, policy_evaluations, arbitration, actions, positions, equity

**NOT EXPOSED EXTERNALLY** (research only)

**Constitution Compliance:** ✓ (Internal logging, no external exposure)

---

### 1.15 Persistence Layer (P1-P7 Hardenings)

**Location:** `runtime/persistence/`

**Files:**
- `execution_state_repository.py` - SQLite persistence for execution state
- `startup_reconciler.py` - Startup reconciliation with exchange

**Responsibility:**
- P1: Stop order lifecycle persistence (PENDING → PLACED → TRIGGERED → FILLED)
- P2: Trailing stop state persistence (with config JSON)
- P3: Fill ID deduplication (prevents duplicate fill processing)
- P4: CLOSING timeout tracking (recovers stuck positions)
- P5: Startup reconciliation (sync local state with exchange)
- P6: Atomic transaction support (multi-write consistency)
- P7: Tracked position persistence (for detection/UI layer)

**Tables:**
```sql
stop_orders          -- Stop order lifecycle state
trailing_stops       -- Trailing stop configurations
seen_fill_ids        -- Fill deduplication (global)
closing_timeouts     -- CLOSING state timeout tracking
tracked_positions    -- SharedPositionState persistence
```

**Key Classes:**
- `ExecutionStateRepository` - Unified persistence interface
- `StartupReconciler` - Detects and resolves state discrepancies
- `AtomicTransaction` - Context manager for atomic writes

**Discrepancy Types (Reconciliation):**
- GHOST_POSITION: Local has position, exchange doesn't
- ORPHAN_POSITION: Exchange has position, local doesn't
- SIZE_MISMATCH: Both have position, sizes differ
- DIRECTION_MISMATCH: Both have position, directions differ
- STATE_MISMATCH: Local in transitional state

**Constitution Compliance:** ✓ (State persistence, no interpretation)

---

### 1.16 Exchange Infrastructure

**Location:** `runtime/exchange/`

**Files:**
- `order_executor.py` - Order submission and tracking
- `trailing_stop_manager.py` - Trailing stop management
- `fill_tracker.py` - Fill event processing and deduplication

**Responsibility:**
- Submit orders to exchange
- Track order lifecycle
- Manage trailing stops with price updates
- Process fill events
- Deduplicate fills (prevent double-processing)

**Trailing Stop Manager:**
- Registers trailing stops with initial config
- Updates stop price on favorable price movement
- Persists state via ExecutionStateRepository
- Tracks: activation_price, current_stop, trailing_pct, trigger_pct

**Fill Tracker:**
- Processes fill events from exchange
- Maintains global seen_fill_ids set
- Persists fill IDs to database
- Prevents duplicate fill processing across restarts

**Constitution Compliance:** ✓ (Execution infrastructure, no interpretation)

---

### 1.17 Hyperliquid Integration

**Location:** `runtime/hyperliquid/`

**Files:**
- `shared_state.py` - Thread-safe shared state for detection/UI
- `live_tracker.py` - Live position tracking
- `indexer/` - Hyperliquid indexer integration

**SharedPositionState:**
- Thread-safe state between detection loop and UI
- Detection writes: update_position(), add_alert()
- UI reads: get_all_positions(), get_danger_positions()
- Persistence via ExecutionStateRepository (P7)

**Position Tracking:**
- PositionSnapshot: wallet, coin, side, size, notional, liq_price, distance_pct
- DangerAlert: danger zone notifications
- Danger levels: 0=safe, 1=watch, 2=warning, 3=critical

**Constitution Compliance:** ✓ (Data tracking, no interpretation)

---

### 1.18 Analysis & Validation Pipeline (HLP25)

**Location:** `analysis/`

**Files:**
- `cascade_labeler.py` - Mechanical cascade event detection
- `wave_detector.py` - Wave structure detection within cascades
- `validators/` - Hypothesis validators

**Validators:**
- `wave_structure.py` - HLP25 Part 2: Cascades occur in 3-5 waves
- `absorption.py` - HLP25 Part 3: Absorption predicts exhaustion
- `oi_concentration.py` - HLP25 Part 4: Top 10 wallets >40% = high risk
- `cross_asset.py` - HLP25 Part 6: BTC→ETH→Alts lead time

**Cascade Labeling (Mechanical Definition):**
- OI dropped >10% in <60 seconds
- At least 2 liquidation events detected
- No interpretation, pure observable facts

**ValidationResult:**
- hypothesis_name: str
- total_events: int
- supporting_events: int
- success_rate: float
- status: VALIDATED | FAILED | INSUFFICIENT_DATA

**Constitution Compliance:** ✓ (Mechanical labeling, no prediction)

---

### 1.19 EFFCS & SLBRS Strategies

**Location:** `external_policy/`

**Files:**
- `ep2_effcs_strategy.py` - Expansion-Focused Flow Continuation Strategy
- `ep2_slbrs_strategy.py` - Sideways Liquidity Band Reversion Strategy

**EFFCS (Expansion Regime):**
- Regime gate: Only active in EXPANSION regime
- Impulse detection: >2% move in <10 candles
- Pullback filtering: 20-50% retracement
- Entry: Continuation in impulse direction
- Exit: Liquidations stopped OR volatility contraction

**SLBRS (Sideways Regime):**
- Regime gate: Only active in SIDEWAYS regime
- First test detection: Initial band touch
- Retest entry: Price returns to band with absorption
- Invalidation: Volatility expansion OR price acceptance beyond band
- Exit: Opposite band approach OR invalidation

**Mutual Exclusion:**
- Only ONE strategy active at a time
- Regime change forces exit of active strategy
- No overlap period allowed

**Constitution Compliance:** ✓ (Stateless evaluation, no prediction)

---

## 2. DEPENDENCY GRAPH (DIRECTIONAL)

### 2.1 Hard Dependencies (Required)

```
CollectorService → ObservationSystem [HARD]
  Purpose: Drive time, ingest data, query snapshots
  Artifact: function calls (advance_time, ingest_observation, query)

ObservationSystem → M1IngestionEngine [HARD]
  Purpose: Normalize raw events
  Artifact: normalized event dicts

ObservationSystem → M3TemporalEngine [HARD]
  Purpose: Process trades, track price history
  Artifact: function calls (process_trade, advance_time)

ObservationSystem → ContinuityMemoryStore [HARD]
  Purpose: Ingest trades/liquidations, query nodes
  Artifact: function calls (ingest_trade, ingest_liquidation, get_active_nodes, advance_time)

ObservationSystem → MemoryAccess [HARD]
  Purpose: Query M4 primitives (NOT USED DIRECTLY, primitives computed inline)
  Status: UNCERTAIN — M5 imported but only used for initialization

ObservationSystem → M4 Primitives [HARD]
  Purpose: Compute primitives at snapshot time
  Artifact: Direct function calls in _compute_primitives_for_symbol()
  Modules: m4_zone_geometry, m4_traversal_kinematics, m4_price_distribution,
           m4_structural_absence, m4_structural_persistence, m4_traversal_voids,
           m4_orderbook, m4_liquidation_density, m4_directional_continuity, m4_trade_burst

CollectorService → PolicyAdapter [HARD]
  Purpose: Generate mandates
  Artifact: generate_mandates() call

PolicyAdapter → ObservationSnapshot [HARD]
  Purpose: Extract primitives
  Artifact: snapshot.primitives[symbol]

PolicyAdapter → ExternalPolicies [HARD]
  Purpose: Invoke strategy proposals
  Artifact: function calls (generate_*_proposal)

ExternalPolicies → M4PrimitiveBundle [HARD]
  Purpose: Read primitive values
  Artifact: Direct field access (e.g., zone_penetration.penetration_depth)

CollectorService → MandateArbitrator [HARD]
  Purpose: Resolve mandates to actions
  Artifact: arbitrate_all() call

CollectorService → ExecutionController [HARD]
  Purpose: Execute actions
  Artifact: process_cycle() call

ExecutionController → PositionStateMachine [HARD]
  Purpose: Validate transitions, update state
  Artifact: transition() call

ExecutionController → MandateArbitrator [HARD]
  Purpose: Arbitrate mandates
  Artifact: arbitrate_all() call

ExecutionController → RiskMonitor [HARD]
  Purpose: Check risk constraints, emit protective mandates
  Artifact: check_and_emit(), validate_entry()

ContinuityMemoryStore → EnrichedLiquidityMemoryNode [HARD]
  Purpose: Store/retrieve nodes
  Artifact: Node instantiation, collection storage
```

### 2.2 Soft Dependencies (Optional)

```
CollectorService → ResearchDatabase [SOFT]
  Purpose: Log execution cycles for research
  Artifact: log_cycle(), log_mandate(), log_arbitration_round()
  Conditional: If _execution_db attribute exists

ContinuityMemoryStore → ResearchDatabase [SOFT]
  Purpose: Log M2 events (node creation, state transitions)
  Artifact: _event_logger attribute
  Conditional: If _event_logger is not None

ExecutionController → ExecutionStateRepository [SOFT]
  Purpose: Persist state machine timeouts
  Artifact: save_closing_timeout(), delete_closing_timeout()
  Conditional: If repository provided

TrailingStopManager → ExecutionStateRepository [SOFT]
  Purpose: Persist trailing stop state
  Artifact: save_trailing_stop(), load_trailing_stops()
  Conditional: If repository provided

FillTracker → ExecutionStateRepository [SOFT]
  Purpose: Persist seen fill IDs
  Artifact: save_fill_id(), has_fill_id()
  Conditional: If repository provided

SharedPositionState → ExecutionStateRepository [SOFT]
  Purpose: Persist tracked positions
  Artifact: save_tracked_position(), load_tracked_positions()
  Conditional: If repository provided
```

### 2.3 Circular Dependencies (Red Flags)

**NONE DETECTED** ✓

All dependencies flow in one direction:
```
Collector → Observation → Memory → Primitives
         ↓
     PolicyAdapter → Policies → Mandates
         ↓
     Arbitration → StateMachine → Execution
```

### 2.4 Hidden Dependencies (Implicit)

**Case-Sensitivity Mismatch:**
- CollectorService uses UPPERCASE symbols ("BTCUSDT")
- ObservationSystem creates primitives with symbols AS PROVIDED
- PolicyAdapter must try symbol, symbol.lower(), symbol.upper() to find bundle
- Status: WORKAROUND IN PLACE (policy_adapter.py:256-264)

**Timestamp Source:**
- CollectorService uses Binance event timestamps (`raw_payload['E']` or `raw_payload['T']`)
- ObservationSystem uses this as system_time
- All timestamps are float seconds (not milliseconds)
- Status: CONSISTENT

---

## 3. IMPORT MAP (CODE-LEVEL)

### 3.1 observation/governance.py

**Direct Imports:**
```python
from .types import ObservationSnapshot, SystemCounters, ObservationStatus, SystemHaltedException, M4PrimitiveBundle
from .internal.m1_ingestion import M1IngestionEngine
from .internal.m3_temporal import M3TemporalEngine
from memory.m2_continuity_store import ContinuityMemoryStore
from memory.m5_access import MemoryAccess
from memory.m4_zone_geometry import compute_zone_penetration_depth, identify_displacement_origin_anchor
from memory.m4_traversal_kinematics import compute_price_traversal_velocity, compute_traversal_compactness
from memory.m4_structural_absence import compute_structural_absence_duration
from memory.m4_structural_persistence import compute_structural_persistence_duration
from memory.m4_price_distribution import compute_price_acceptance_ratio, compute_central_tendency_deviation
from memory.m4_traversal_voids import compute_traversal_void_span
from memory.m4_orderbook import compute_resting_size, detect_order_consumption, detect_absorption_event, detect_refill_event
from memory.m4_liquidation_density import compute_liquidation_density
from memory.m4_directional_continuity import compute_directional_continuity
from memory.m4_trade_burst import compute_trade_burst
```

**Indirect Imports:**
- Via observation.types: All M4 primitive dataclass types
- Via memory modules: All M4 computation functions

**Boundary Violations:** NONE ✓

---

### 3.2 runtime/policy_adapter.py

**Direct Imports:**
```python
from observation.types import ObservationSnapshot, ObservationStatus
from runtime.arbitration.types import Mandate, MandateType
from external_policy.ep2_strategy_geometry import generate_geometry_proposal, StrategyContext, PermissionOutput, StrategyProposal
from external_policy.ep2_strategy_kinematics import generate_kinematics_proposal
from external_policy.ep2_strategy_absence import generate_absence_proposal
```

**Boundary Check:** ✓ (No observation internals accessed)

---

### 3.3 runtime/collector/service.py

**Direct Imports:**
```python
from observation.governance import ObservationSystem
from observation.types import ObservationSnapshot, ObservationStatus
from runtime.policy_adapter import PolicyAdapter, AdapterConfig
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.executor.controller import ExecutionController
from runtime.risk.types import RiskConfig, AccountState
from runtime.logging.execution_db import ResearchDatabase
```

**Boundary Check:** ✓ (Only uses public facades)

---

### 3.4 external_policy/ep2_strategy_geometry.py

**Direct Imports:**
```python
from dataclasses import dataclass
from typing import Optional
```

**Primitive Access:**
- Via function parameters (passed by PolicyAdapter)
- No direct imports of M4 modules
- Accesses primitive fields (e.g., `zone_penetration.penetration_depth`)

**Boundary Check:** ✓ (Receives primitives, doesn't query)

---

### 3.5 Choke Points (Files Imported Everywhere)

1. **observation/types.py** (13+ importers)
   - Defines: ObservationSnapshot, M4PrimitiveBundle, ObservationStatus
   - Critical for system-wide type coordination

2. **runtime/arbitration/types.py** (5+ importers)
   - Defines: Mandate, MandateType, Action, ActionType

3. **runtime/position/types.py** (4+ importers)
   - Defines: Position, PositionState, Direction, InvariantViolation

---

### 3.6 Constitution-Critical Files (Must Not Import Upward)

**Observation Layer (M1-M5):**
- `observation/internal/m1_ingestion.py`: ✓ No upward imports
- `observation/internal/m3_temporal.py`: ✓ No upward imports
- `memory/m2_continuity_store.py`: ✓ No upward imports
- `memory/m4_*.py` (all primitives): ✓ No upward imports
- `memory/m5_access.py`: ✓ No upward imports

**Execution Layer:**
- `runtime/arbitration/arbitrator.py`: ✓ No observation imports
- `runtime/position/state_machine.py`: ✓ No observation imports

**Compliance:** ✓ ALL VERIFIED

---

## 4. LOGIC FLOW MAP (CANONICAL PATH)

### 4.1 Data Ingestion Pipeline

```
RAW DATA (Binance WebSocket)
  ↓
CollectorService._run_binance_stream()
  - Receives: trade, liquidation, depth, mark_price events
  - Extracts: raw_payload, symbol, event_type
  ↓
CollectorService → ObservationSystem.ingest_observation()
  - Parameters: timestamp, symbol, event_type, payload
  - Governance: Symbol whitelist check
  - Causality: Time window validation (± tolerance)
  ↓
M1IngestionEngine.normalize_*()
  - normalize_trade() → {timestamp, symbol, price, quantity, side, ...}
  - normalize_liquidation() → {timestamp, symbol, price, quantity, side, ...}
  - normalize_depth() → {bids: [(price, size)], asks: [(price, size)]}
  - normalize_mark_price() → {mark_price, index_price}
  ↓
Event Dispatch:
  IF event_type == 'TRADE':
    → M3TemporalEngine.process_trade()
      - Updates: sequence buffer, recent prices, candle state
    → ContinuityMemoryStore.ingest_trade()
      - Spatial matching: Find/create node at price
      - Update: node.trade_execution_count++
      - Update: interaction_timestamps

  IF event_type == 'LIQUIDATION':
    → ContinuityMemoryStore.ingest_liquidation()
      - Spatial matching: Find/create node at price
      - Update: node.liquidation_count++
      - Update: interaction_timestamps

  IF event_type == 'DEPTH':
    → ContinuityMemoryStore.update_orderbook_state()
      - Update: node.resting_size_bid/ask
      - Track: previous_resting_size for consumption detection

  IF event_type == 'MARK_PRICE':
    → ContinuityMemoryStore.update_mark_price_state()
      - Update: symbol-level mark/index price cache
```

**Invariants Enforced:**
- Time monotonicity (no backwards time)
- Symbol whitelist (reject unknown symbols)
- Schema validation (catch malformed payloads)

**Failure Modes:**
- Exception in M1 → FAILED state
- Exception in M2/M3 → FAILED state
- Time regression → FAILED state

---

### 4.2 Time Advancement Pipeline

```
CollectorService._drive_clock() [Every 100ms]
  ↓
ObservationSystem.advance_time(current_timestamp)
  - Validate: current_timestamp >= system_time (monotonicity)
  - Update: system_time = current_timestamp
  - Transition: UNINITIALIZED → ACTIVE (on first call)
  ↓
M3TemporalEngine.advance_time()
  - Close: time windows
  - Trim: old evidence tokens
  ↓
ContinuityMemoryStore.advance_time()
  - update_memory_states(): Check ACTIVE → DORMANT → ARCHIVED transitions
  - decay_nodes(): Apply time-based decay to strength
  ↓
System Status Update:
  IF exception raised:
    → _trigger_failure(reason)
    → status = FAILED
    → failure_reason = reason
    → Irreversible
```

---

### 4.3 Snapshot Creation Pipeline

```
CollectorService._drive_clock()
  ↓
ObservationSystem.query({'type': 'snapshot'})
  ↓
ObservationSystem._get_snapshot()
  ↓
FOR EACH symbol IN allowed_symbols:
  ↓
  _compute_primitives_for_symbol(symbol)
    ↓
    Query M2: active_nodes = m2_store.get_active_nodes(symbol)
    Query M3: recent_prices = m3.get_recent_prices(symbol, max_count=100)
    Query M3: candle = m3.get_current_candle(symbol)
    ↓
    Compute 17 Primitives:
      1. Zone Penetration (A6)
         - Input: active_nodes (zones), recent_prices (traversal)
         - Logic: For each node, compute penetration depth
         - Output: Max penetration across all nodes OR None

      2. Displacement Origin Anchor (A7)
         - Input: recent_prices[:mid_point] (pre-traversal)
         - Output: DisplacementOriginAnchor OR None

      3. Price Traversal Velocity (A3)
         - Input: recent_prices[0], recent_prices[-1], timestamps
         - Output: PriceTraversalVelocity OR None

      4. Traversal Compactness (A4)
         - Input: recent_prices (ordered sequence)
         - Output: TraversalCompactness OR None

      5. Price Acceptance Ratio (A5)
         - Input: candle (OHLC)
         - Output: PriceAcceptanceRatio OR None

      6. Central Tendency Deviation (A8)
         - Input: recent_prices[-1] (current), avg(node.price_center)
         - Output: CentralTendencyDeviation OR None

      7. Structural Absence Duration (B1.1)
         - Input: node.presence_intervals, observation_start/end
         - Output: StructuralAbsenceDuration OR None

      8. Structural Persistence Duration (B2.1)
         - Input: node.presence_intervals, observation_start/end
         - Output: StructuralPersistenceDuration OR None

      9. Traversal Void Span (B1.2)
         - Input: node.interaction_timestamps
         - Output: float (max void duration) OR None

      10. Event Non-Occurrence Counter (B1.3)
          - Input: active_nodes (expected), stale_threshold
          - Logic: Count nodes not interacted with recently
          - Output: int (stale count) OR None

      11-14. Order Book Primitives (OB)
          - Resting Size (node.resting_size_bid/ask)
          - Order Consumption (previous_size - current_size)
          - Absorption Event (consumption + price stability)
          - Refill Event (size increase)

      15. Liquidation Density (Phase 6.4)
          - Input: node.liquidation_proximity_count, price range
          - Output: LiquidationDensity OR None

      16. Directional Continuity (Phase 4.3)
          - Input: recent_prices (direction sequence)
          - Output: DirectionalContinuity OR None

      17. Trade Burst (Phase 5.4)
          - Input: node.trade_execution_count, window_duration
          - Output: TradeBurst OR None
    ↓
    Return M4PrimitiveBundle(symbol, primitive1, primitive2, ..., primitive17)
  ↓
primitives[symbol] = bundle
  ↓
Return ObservationSnapshot(
  status=ACTIVE,
  timestamp=system_time,
  symbols_active=allowed_symbols,
  counters=SystemCounters(...),
  promoted_events=None,
  primitives=primitives
)
```

**Critical Properties:**
- Primitives computed ONCE per snapshot
- Primitives are pre-computed (NOT queried on-demand)
- Primitives may be None (absence of structural fact)
- Snapshot is frozen (immutable after creation)

---

### 4.4 M6 Execution Cycle

```
CollectorService._drive_clock()
  ↓
IF snapshot.status == ACTIVE:
  ↓
  CollectorService._execute_m6_cycle(snapshot, timestamp)
    ↓
    1. Log Cycle to Database
       cycle_id = execution_db.log_cycle(...)
    ↓
    2. Generate Mandates (Per Symbol)
       FOR EACH symbol IN snapshot.symbols_active:
         ↓
         PolicyAdapter.generate_mandates(snapshot, symbol, timestamp, cycle_id)
           ↓
           Extract Primitives:
             bundle = snapshot.primitives[symbol]
             primitives = {
               "zone_penetration": bundle.zone_penetration,
               "traversal_compactness": bundle.traversal_compactness,
               ...
             }
           ↓
           Invoke External Policies:
             IF config.enable_geometry:
               proposal = generate_geometry_proposal(
                 zone_penetration=primitives["zone_penetration"],
                 traversal_compactness=primitives["traversal_compactness"],
                 central_tendency_deviation=primitives["central_tendency_deviation"],
                 context=StrategyContext(...),
                 permission=PermissionOutput(...)
               )
               IF proposal: mandates.append(Mandate(...))

             IF config.enable_kinematics:
               proposal = generate_kinematics_proposal(...)
               IF proposal: mandates.append(Mandate(...))

             IF config.enable_absence:
               proposal = generate_absence_proposal(...)
               IF proposal: mandates.append(Mandate(...))
           ↓
           Convert Proposals to Mandates:
             FOR EACH proposal:
               mandate = Mandate(
                 symbol=symbol,
                 type=MandateType.ENTRY,  # Hardcoded in V1
                 authority=5.0,
                 timestamp=timestamp
               )
           ↓
           Return List[Mandate]
         ↓
         all_mandates.extend(mandates)
    ↓
    3. Arbitrate Mandates
       actions_by_symbol = arbitrator.arbitrate_all(all_mandates)
         ↓
         Group mandates by symbol
         FOR EACH symbol, mandates:
           ↓
           arbitrator.arbitrate(mandates)
             ↓
             1. Check EXIT supremacy → return EXIT
             2. Filter ENTRY if BLOCK present
             3. Group by type, select highest authority
             4. Apply hierarchy: EXIT > REDUCE > ENTRY > HOLD
             5. Return Action
         ↓
         Return {symbol: Action}
    ↓
    4. Execute Actions
       executor.process_cycle(all_mandates, account, mark_prices)
         ↓
         1. Risk Monitor Check:
            risk_mandates = risk_monitor.check_and_emit(account, positions, mark_prices)
            all_mandates = mandates + risk_mandates
         ↓
         2. Arbitrate (again, with risk mandates)
            actions = arbitrator.arbitrate_all(all_mandates)
         ↓
         3. Execute Per Symbol:
            FOR EACH symbol, action:
              ↓
              IF action.type == NO_ACTION: continue
              ↓
              IF action.type == ENTRY:
                valid, error = risk_monitor.validate_entry(...)
                IF NOT valid: reject, log, continue
              ↓
              executor.execute_action(symbol, action, mark_prices)
                ↓
                Validate Against State Machine:
                  position = state_machine.get_position(symbol)
                  transition_key = (position.state, action.type)
                  IF transition_key NOT allowed:
                    → Reject (InvariantViolation)
                ↓
                Execute Transition:
                  new_position = state_machine.transition(symbol, action.type, **kwargs)
                ↓
                Log Result:
                  execution_log.append(ExecutionResult(...))
              ↓
              IF success: actions_executed++
              ELSE: actions_rejected++
         ↓
         Return CycleStats(mandates_received, actions_executed, actions_rejected, symbols_processed)
    ↓
    5. Log Mandates & Arbitration to Database
       execution_db.log_mandate(cycle_id, ...)
       execution_db.log_arbitration_round(cycle_id, ...)
```

**Critical Properties:**
- One cycle per clock tick (100ms)
- Symbol-local execution (independent)
- Deterministic arbitration
- State machine validation
- Risk constraints enforced

---

## 5. DOCUMENTATION ↔ CODE CORRESPONDENCE

### 5.1 EPISTEMIC_CONSTITUTION.md

| Section | Code Location | Mapping Status |
|---------|---------------|----------------|
| Article I: Sole Purpose | `observation/governance.py` | EXACT |
| Article II: Explicit Negations | Enforced by M5, no "health" fields exposed | EXACT |
| Article III: Epistemic Ceiling | `observation/types.py` — SystemCounters fields are Optional[...] | PARTIAL — counters exist but None |
| Article IV: Silence Rule | ObservationSystem._get_snapshot() — returns None for missing data | EXACT |
| Article V: Failure Rule | ObservationSystem._trigger_failure() — FAILED state | EXACT |
| Article VI: Exposure Rule | ObservationSnapshot exposes: status, timestamp, symbols_active | EXACT |
| Article VII: M6 Rule | M6 consumes snapshot internally, exposes actions only | PARTIAL — M6 stub incomplete |
| Article VIII: Removal Invariant | No counters, rates, health exposed | EXACT |
| Article IX: Amendment Prohibition | N/A (policy) | N/A |
| Article X: Enforcement | All status beyond UNINITIALIZED/FAILED is ACTIVE only | EXACT |

**Violations:** NONE DETECTED ✓

**Concerns:**
- SystemCounters fields (intervals_processed, dropped_events) always None — SAFE (no claims made)
- promoted_events always None — SAFE (no claims made)

---

### 5.2 SYSTEM_CANON.md

| Section | Code Location | Mapping Status |
|---------|---------------|----------------|
| 1. Origin & Intent | Enforced by architecture | ALIGNED |
| 2.1 Observation vs Decision | Observation (M1-M5) separate from Execution (M6+) | EXACT |
| 2.2 Silence Rules | Primitives return None when no structural condition | EXACT |
| 3. Canonical Vocabulary | No forbidden words in exposed types | EXACT |
| 4. System Layers (M1-M6) | All layers implemented | EXACT |
| 5. Governance & Arbitration | M5 as firewall, arbitration deterministic | EXACT |
| 6. Determinism, Simulation, Replay | No time.time(), clock-injected only | EXACT |
| 7. Failure Modes & Truthfulness | ObservationStatus: UNINITIALIZED | ACTIVE | FAILED | EXACT |
| 8. Rejected Paths | No web UI, no self-verification | COMPLIANT |
| 9. Agent Operating Rules | N/A (policy for agents) | N/A |

**Compliance:** ✓ FULL

---

### 5.3 SYSTEM_GUIDANCE.md

| Section | Code Location | Mapping Status |
|---------|---------------|----------------|
| 2. Layer Responsibilities | All layers match descriptions | EXACT |
| 3. Epistemic Safety Principles | No prediction, probability, ranking, scoring | EXACT |
| 3.1 No Prediction | Primitives are post-fact only | EXACT |
| 3.2 No Probability | No confidence intervals | EXACT |
| 3.3 No Ranking | M5 rejects "sort_by", "top_n" | EXACT |
| 3.4 No Strategy/Signals | Observation emits primitives, not signals | EXACT |
| 3.5 No Directional Bias | M2 tracks both sides symmetrically | EXACT |
| 3.6 No Semantic Interpretation | Node fields are factual (price, volume, timestamps) | EXACT |
| 4. Determinism & Purity Rules | No time.now(), no randomness | EXACT |
| 5. Governance Authority (M5) | M5 is sole entry point | EXACT |
| 6. Prohibited Evolution Paths | None of the 7 forbidden paths detected | COMPLIANT |

**Violations:** NONE DETECTED ✓

**Internal Concern:**
- M2 nodes contain `strength` and `confidence` fields (evaluative)
- MITIGATION: Not exposed via M5 queries or snapshots
- STATUS: Acceptable per internal-only exception

---

### 5.4 CODE_FREEZE.md

| Frozen Component | Current Status | Compliance |
|------------------|----------------|------------|
| M1 Ingestion | observation/internal/m1_ingestion.py | FROZEN |
| M2 Memory Store | memory/m2_continuity_store.py | FROZEN |
| M3 Temporal | observation/internal/m3_temporal.py | FROZEN |
| M4 Primitives (Tier A) | memory/m4_*.py | FROZEN |
| M4 Primitives (Tier B-1) | memory/m4_structural_absence.py, m4_traversal_voids.py, m4_event_absence.py | FROZEN |
| M4 Primitives (Tier B-2) | memory/m4_structural_persistence.py, m4_structural_exposure.py | FROZEN |
| M5 Governance | memory/m5_access.py, m5_query_schemas.py | FROZEN |
| M6 Mandate | runtime/m6_executor.py | STUB (not yet wired) |
| External Policies | external_policy/ep2_strategy_*.py | FROZEN |
| Arbitration | runtime/arbitration/arbitrator.py | FROZEN |
| Execution | runtime/executor/controller.py | FROZEN |
| Position State Machine | runtime/position/state_machine.py | FROZEN |

**Modification Authority:** Logged evidence from live runs required

**Compliance:** ✓ All frozen components identified

---

### 5.5 PROJECT SPECIFICATION — CONSTITUTIONAL EXECUTION SYSTEM.md

| Section | Code Status | Mapping |
|---------|-------------|---------|
| 1.1 What the System Is | Implemented | EXACT |
| 1.2 What the System Is Not | Enforced by architecture | EXACT |
| 2.1 Observation Layer | M1-M5 implemented | EXACT |
| 2.2 Mandate Layer | runtime/arbitration/ implemented | EXACT |
| 2.3 Arbitration Layer | runtime/arbitration/arbitrator.py | EXACT |
| 2.4 Execution Layer | runtime/executor/ implemented | EXACT |
| 3. Position Lifecycle | runtime/position/state_machine.py | EXACT |
| 4. Risk & Exposure Model | runtime/risk/ implemented | PARTIAL — leverage constraints incomplete |
| 5. Epistemic Constitution | Observation layer enforces | EXACT |
| 6. Semantic Leak Control | In Progress | PARTIAL — CI not yet wired |
| 7. Enforcement & Tooling | Planned | MISSING |
| 8. Formal Verification | Not Started | MISSING |

**Completion Status:**
- Complete & Locked: ✓ Observation, Mandate, Arbitration, Position, M6 constraints
- In Progress: Risk mathematics, Semantic leak audit
- Not Started: Formal proofs, CI enforcement

---

## 6. STATE MACHINES & INVARIANTS

### 6.1 Position Lifecycle State Machine

**Location:** `runtime/position/state_machine.py`

**States (5):**
```
FLAT       — No position exists
ENTERING   — Order submitted, awaiting fill
OPEN       — Position active
REDUCING   — Partial exit in progress
CLOSING    — Full exit in progress
```

**Allowed Transitions (10):**
```
FLAT --[ENTRY]--> ENTERING
ENTERING --[SUCCESS]--> OPEN
ENTERING --[FAILURE]--> FLAT
OPEN --[REDUCE]--> REDUCING
OPEN --[EXIT]--> CLOSING
REDUCING --[PARTIAL]--> OPEN
REDUCING --[COMPLETE]--> CLOSING
CLOSING --[SUCCESS]--> FLAT
# X3-A Emergency Exit (cancel pending + market close)
ENTERING --[EMERGENCY_EXIT]--> CLOSING
REDUCING --[EMERGENCY_EXIT]--> CLOSING
```

**Invariants Enforced:**

**Theorem 3.1 — Single Position Per Symbol:**
- Enforcement: `_positions: Dict[str, Position]` (dict uniqueness)
- Validation: `validate_entry()` checks `position.state == FLAT`

**Theorem 4.1 — Direction Preservation:**
- Enforcement: `validate_direction_preserved(current, new)`
- Logic: `current_direction == new_direction` (no reversal without EXIT)

**Theorem 7.1 — Quantity Monotonicity (REDUCE):**
- Enforcement: `_handle_reduce_partial()`
- Logic: `abs(new_quantity) < abs(current.quantity)`
- Validation: `(new_quantity > 0) == (current.quantity > 0)` (sign preserved)

**Theorem 2.1 — Deterministic Transitions:**
- Enforcement: `ALLOWED_TRANSITIONS` dict (hardcoded)
- Raises: `InvariantViolation` if transition not in dict

**Theorem 6.1 — All Paths Lead to FLAT:**
- Property: Only FLAT has no outgoing transitions to self
- Proof: Manual inspection of transition table

**Forbidden Transitions (17):**
All combinations NOT in `ALLOWED_TRANSITIONS` are rejected:
- FLAT → OPEN (must go through ENTERING)
- OPEN → FLAT (must go through CLOSING)
- ENTERING → REDUCING (impossible)
- etc.

**State Data:**
```python
@dataclass
class Position:
    symbol: str
    state: PositionState
    direction: Direction  # LONG | SHORT
    quantity: Decimal
    entry_price: Optional[Decimal]
```

---

### 6.2 Mandate Arbitration Invariants

**Location:** `runtime/arbitration/arbitrator.py`

**Mandate Priority (5 levels):**
```
EXIT:   5 (supreme)
BLOCK:  4 (non-actionable, filters ENTRY)
REDUCE: 3
ENTRY:  2
HOLD:   1
```

**Arbitration Invariants:**

**Theorem 2.2 — EXIT Supremacy:**
- Enforcement: Step 1 in arbitrate()
- Logic: `if exit_mandates: return Action(EXIT)`

**Theorem 2.3 — BLOCK Prevents ENTRY:**
- Enforcement: Step 2 in arbitrate()
- Logic: `if BLOCK in mandates: mandates = filter(type != ENTRY)`

**Theorem 3.1 — Deterministic Resolution:**
- Enforcement: Highest authority wins within type
- Logic: `mandate.authority > by_type[mandate.type].authority`

**Theorem 4.1 — Exactly One Action:**
- Enforcement: arbitrate() returns single Action
- Logic: Hierarchy traversal (EXIT > REDUCE > ENTRY > HOLD)

**Theorem 5.1 — Symbol-Local Independence:**
- Enforcement: `arbitrate_all()` groups by symbol
- Logic: `for symbol, mandates in by_symbol.items(): arbitrate(mandates)`

**Theorem 8.1 — Always Completes:**
- Enforcement: Default return `Action(NO_ACTION)`
- Property: No infinite loops, no exceptions

---

### 6.3 Observation System Status Transitions

**Location:** `observation/governance.py`

**States (3):**
```
UNINITIALIZED — Before first advance_time()
ACTIVE        — Normal operation
FAILED        — Invariant violated
```

**Transitions:**
```
UNINITIALIZED --[advance_time()]--> ACTIVE
ACTIVE --[time regression]--> FAILED
ACTIVE --[exception]--> FAILED
FAILED --[NO TRANSITIONS]--> (terminal state)
```

**Failure Triggers:**
- Time regression: `new_timestamp < system_time`
- Unhandled exception in M1, M2, M3
- Invariant violation (explicit call to `_trigger_failure()`)

**Recovery:** NONE (FAILED is irreversible per constitution)

---

### 6.4 Memory Node Lifecycle (M2)

**Location:** `memory/m2_continuity_store.py`

**States (3):**
```
ACTIVE    — Recently interacted, high strength
DORMANT   — Low strength or timeout, preserved
ARCHIVED  — Very low strength or extended timeout
```

**Transitions:**
```
[CREATE] --> ACTIVE
ACTIVE --[low strength OR timeout]--> DORMANT
DORMANT --[reinforce]--> ACTIVE (revival)
DORMANT --[very low strength OR extended timeout]--> ARCHIVED
ARCHIVED --[NO AUTO-REVIVAL]
```

**Thresholds:**
```python
class MemoryStateThresholds:
    DORMANT_STRENGTH_THRESHOLD = 0.2
    DORMANT_TIMEOUT_SEC = 300  # 5 minutes
    ARCHIVE_STRENGTH_THRESHOLD = 0.05
    ARCHIVE_TIMEOUT_SEC = 1800  # 30 minutes
    ACTIVE_DECAY_RATE = 0.01
    DORMANT_DECAY_RATE = 0.005
```

**Node Creation Rule:**
- ONLY on liquidation events (per Phase 5 Canon)
- Spatial matching: Check overlap with existing nodes
- If overlap → reinforce
- If no overlap → create new

**Decay Logic:**
- Applied on `advance_time()`
- State-aware: ACTIVE decays faster than DORMANT
- Formula: `strength *= (1 - decay_rate)`

---

## 7. FAILURE MODES & AGENT TRAPS

### 7.1 Common Agent Confusion Points

**TRAP 1: Primitive Computation Location**
- **Confusion:** Agent assumes primitives are queried via M5
- **Reality:** Primitives are computed INLINE in `governance.py:_compute_primitives_for_symbol()`
- **Evidence:** M5 is imported but not used for primitive queries
- **Consequence:** Agent may try to wire M5 queries, breaking pre-computation model

**TRAP 2: Case-Sensitivity Mismatch**
- **Confusion:** Agent assumes symbol keys are consistent
- **Reality:** Service uses UPPERCASE, observation may use as-provided, policy adapter tries 3 variants
- **Evidence:** `policy_adapter.py:256-264` has fallback logic
- **Consequence:** Mandates may not generate if symbol case mismatches

**TRAP 3: Snapshot Mutability**
- **Confusion:** Agent assumes snapshot is live/queryable
- **Reality:** ObservationSnapshot is frozen dataclass (immutable)
- **Evidence:** `@dataclass(frozen=True)`
- **Consequence:** Agent cannot modify snapshot, must re-query

**TRAP 4: M6 Execution Trigger**
- **Confusion:** Agent assumes M6 runs independently
- **Reality:** M6 cycle is driven by CollectorService._drive_clock()
- **Evidence:** `service.py:108-115`
- **Consequence:** M6 won't execute if clock driver not running

**TRAP 5: State Machine Action Names**
- **Confusion:** Agent confuses MandateType (ENTRY/EXIT) with state_machine.Action (ENTRY/SUCCESS/FAILURE)
- **Reality:** Two different enums with overlapping names
- **Evidence:** `runtime/arbitration/types.py:MandateType` vs `runtime/position/state_machine.py:Action`
- **Consequence:** Invalid transition attempts

**TRAP 6: Mandate Authority Defaults**
- **Confusion:** Agent assumes mandate authority is computed
- **Reality:** PolicyAdapter hardcodes authority=5.0 for all mandates
- **Evidence:** `policy_adapter.py:332`
- **Consequence:** No priority differentiation between policies

**TRAP 7: External Policy Statelessness**
- **Confusion:** Agent assumes policies track history
- **Reality:** Policies are pure functions (no state, no memory)
- **Evidence:** `ep2_strategy_geometry.py:57-119` (single function, no class)
- **Consequence:** Agent cannot add "learning" or "adaptation"

---

### 7.2 Name Collisions & Semantic Drift Points

**Collision 1: "Action" Type**
- `runtime/arbitration/types.py:Action` (arbitration output)
- `runtime/position/state_machine.py:Action` (state transition input)
- `execution/ep4_action_schemas.py:Action` (execution schema)
- **Danger:** Agent imports wrong Action type

**Collision 2: "Mandate" vs "Action" vs "Proposal"**
- `StrategyProposal` (external policy output)
- `Mandate` (arbitration input)
- `Action` (arbitration output)
- **Danger:** Agent confuses pipeline stages

**Collision 3: "Timestamp" Units**
- Binance: milliseconds (`raw_payload['E']`)
- System: float seconds (`timestamp / 1000.0`)
- **Danger:** Off-by-1000x errors

**Collision 4: "Side" Semantics**
- M1 Trade: "BUY"/"SELL" (taker perspective)
- M1 Liquidation: "BUY"/"SELL" (liquidation direction)
- M2 Node: "BID"/"ASK" (order book side)
- **Danger:** Semantic mismatch in aggregation

---

### 7.3 Logic Split Across Files

**Split 1: Primitive Computation**
- **Defined:** `memory/m4_*.py` (17 modules)
- **Invoked:** `observation/governance.py:_compute_primitives_for_symbol()`
- **Danger:** Agent modifying M4 module without understanding governance.py calls it

**Split 2: M6 Execution Cycle**
- **Triggered:** `runtime/collector/service.py:_execute_m6_cycle()`
- **Policy Invocation:** `runtime/policy_adapter.py:generate_mandates()`
- **Arbitration:** `runtime/arbitration/arbitrator.py:arbitrate_all()`
- **Execution:** `runtime/executor/controller.py:process_cycle()`
- **Danger:** Agent missing any step breaks cycle

**Split 3: Risk Constraints**
- **Emitted:** `runtime/risk/monitor.py:check_and_emit()`
- **Validated:** `runtime/executor/controller.py:validate_entry()`
- **Danger:** Agent bypassing risk validation

---

### 7.4 Documentation Stricter Than Code

**Case 1: M6 Consumption Contract**
- **Doc:** M6 must never expose observation interpretations
- **Code:** M6 is stub (doesn't expose anything)
- **Risk:** Future implementation may violate

**Case 2: M5 Query Rejection**
- **Doc:** M5 must reject evaluative queries
- **Code:** M5 has guards, but no exhaustive regex enforcement
- **Risk:** New query types may bypass guards

**Case 3: Position State Machine Proofs**
- **Doc:** 13 formal theorems proven
- **Code:** Transition table hardcoded, but no runtime proof checking
- **Risk:** Code change may violate theorem without detection

---

### 7.5 Code More Permissive Than Documentation

**Case 1: M2 Node Fields**
- **Doc:** No evaluative metrics allowed
- **Code:** M2 nodes contain `strength`, `confidence` (internal only)
- **Mitigation:** Not exposed via M5 or snapshot
- **Risk:** Agent may expose these fields

**Case 2: Strategy Confidence**
- **Doc:** No confidence values allowed
- **Code:** StrategyProposal has `confidence` field (but opaque string, not numeric)
- **Mitigation:** Not interpreted as probability
- **Risk:** Agent may convert to numeric

**Case 3: Execution Database**
- **Doc:** No external exposure of observation quality
- **Code:** ResearchDatabase logs everything (M2 state, primitives, mandates)
- **Mitigation:** Research only, not exposed to runtime
- **Risk:** Agent may use DB for runtime decisions

---

### 7.6 Missing Wiring / Incomplete Flows

**INCOMPLETE 1: M6 Executor Stub**
- **Location:** `runtime/m6_executor.py`
- **Status:** Minimal stub, only validates status
- **Missing:** Actual execution logic
- **Impact:** M6 path exists but doesn't execute

**INCOMPLETE 2: Entry Size Calculation**
- **Location:** `runtime/executor/controller.py:96-110`
- **Status:** Placeholder size=0.1
- **Missing:** Actual size from mandate/action
- **Impact:** Risk validation uses wrong size

**INCOMPLETE 3: Execution Adapter**
- **Location:** `execution/ep4_exchange_adapter.py`
- **Status:** MockedExchangeAdapter only
- **Missing:** Real Binance execution
- **Impact:** No live trading possible

**INCOMPLETE 4: CI Enforcement**
- **Doc:** `docs/CI_ENFORCEMENT_DESIGN.md`
- **Status:** Design only, not wired to GitHub Actions
- **Missing:** Actual pre-commit/CI hooks
- **Impact:** Semantic leaks not blocked

---

### 7.7 What to NEVER Assume

**NEVER ASSUME 1: Standard Trading System Behavior**
- This is NOT a traditional signal-based system
- Primitives are NOT signals
- Observation does NOT predict
- Strategies do NOT optimize

**NEVER ASSUME 2: Convenience Methods Exist**
- No "get best entry" functions
- No "calculate position size" helpers
- No "compute profit" utilities
- Everything is explicit, verbose

**NEVER ASSUME 3: Auto-Recovery**
- ObservationSystem FAILED state is terminal
- No auto-restart, no degraded mode
- System must be externally restarted

**NEVER ASSUME 4: Time is Now**
- No `time.time()` or `datetime.now()`
- All time is injected via `advance_time()`
- System has no awareness of wall clock

**NEVER ASSUME 5: Data is Recent**
- ObservationSnapshot has timestamp
- No guarantees on data freshness
- System may be silent/stale and still return ACTIVE

**NEVER ASSUME 6: Mandates Execute**
- Mandates are proposals
- Arbitration may reject
- State machine may reject
- Risk gates may reject
- BLOCK mandates are not actionable

**NEVER ASSUME 7: Symbol Case**
- May be UPPERCASE, lowercase, or MixedCase
- Must handle all variants
- PolicyAdapter has workaround

---

## 8. CRITICAL GAPS & UNCERTAINTIES

### 8.1 Architectural Gaps

**GAP 1: M6 Execution Wiring**
- `runtime/m6_executor.py` is stub only
- CollectorService calls PolicyAdapter directly
- M6 contract unclear

**GAP 2: Mandate → Action Parameters**
- Mandate has no size/price fields
- Action has no size/price fields
- How does ExecutionController know what size to execute?
- UNCERTAIN: Missing parameter flow

**GAP 3: Mark Price Source**
- CollectorService tracks mark_prices dict
- Updated from trade stream (estimated)
- Real mark_price events normalized but not used
- UNCERTAIN: Which source is authoritative?

---

### 8.2 Behavioral Uncertainties

**UNCERTAIN 1: M3 Buffer Size**
- get_recent_prices(max_count=100)
- What is actual M3 buffer capacity?
- What happens if buffer < 100?

**UNCERTAIN 2: Node Spatial Matching Logic**
- M2 has "spatial matching" for liquidations
- Exact overlap detection algorithm UNCERTAIN
- price_band calculation UNCERTAIN

**UNCERTAIN 3: Dormant Node Revival Strength**
- `compute_revival_strength()` exists
- How is it used in revival logic?
- Threshold for revival UNCERTAIN

**UNCERTAIN 4: Execution Adapter Behavior**
- MockedExchangeAdapter always succeeds?
- Or simulates failures?
- Impact on state machine transitions UNCERTAIN

---

### 8.3 Mismatches Detected

**MISMATCH 1: promoted_events Always None**
- ObservationSnapshot has promoted_events field
- Always set to None in _get_snapshot()
- Documentation mentions promoted events
- CODE vs DOC: Field exists but unused

**MISMATCH 2: SystemCounters Always None**
- intervals_processed: None
- dropped_events: None
- Code comment says "not tracked"
- DOC vs CODE: Counters defined but not populated

**MISMATCH 3: M5 Imported but Not Used**
- governance.py imports MemoryAccess
- MemoryAccess initialized in __init__
- Never called in _compute_primitives_for_symbol()
- CODE vs INTENT: Import suggests M5 query path, but primitives computed inline

---

## 9. NAVIGATION RECOMMENDATIONS

### For Future Agents:

**DO:**
- Read this document FIRST
- Trust marked uncertainties
- Verify claims against current code
- Ask for clarification when uncertain
- Mark new uncertainties explicitly

**DON'T:**
- Assume standard trading patterns
- Guess parameter values
- Infer intent from names
- Modify frozen components without evidence
- Expose internal metrics externally

**VERIFY BEFORE MODIFYING:**
- Is this component frozen? (Check CODE_FREEZE.md)
- Does this change violate constitution? (Check EPISTEMIC_CONSTITUTION.md)
- Does this expose evaluative data? (Check boundary rules)
- Does this break state machine? (Check POSITION_STATE_MACHINE_PROOFS.md)
- Does this bypass M5 governance? (Check access paths)

**WHEN STUCK:**
- Re-read section 7 (Failure Modes & Agent Traps)
- Check import map (section 3)
- Trace logic flow (section 4)
- Verify state machine (section 6)

---

## 10. SUMMARY METRICS

**Total Subsystems:** 19 (updated 2026-01-25)
**Frozen Components:** 23
**Constitutional Documents:** 5
**State Machines:** 3 (Position, Arbitration, Observation)
**Primitives (M4):** 17
**External Policies:** 5 (3 original + EFFCS + SLBRS)
**Mandate Types:** 5
**Position States:** 5
**Allowed Transitions:** 10 (8 original + 2 X3-A emergency exit)
**Forbidden Transitions:** 15
**Proven Theorems:** 26 (13 position + 13 arbitration)

**New Subsystems (2026-01-25):**
- Persistence Layer (P1-P7)
- Exchange Infrastructure
- Hyperliquid Integration
- Analysis/Validation Pipeline (HLP25)
- EFFCS/SLBRS Strategies

**Constitution Compliance:** ✓ FULL (observation layer)
**Code Freeze Compliance:** ✓ ALL FROZEN COMPONENTS IDENTIFIED
**Documentation-Code Alignment:** ✓ HIGH (few mismatches, all documented)

**Critical Gaps:** 3 (M6 wiring, parameter flow, mark price source)
**Behavioral Uncertainties:** 4 (M3 buffer, spatial matching, revival logic, adapter)
**Detected Mismatches:** 3 (promoted_events, counters, M5 import)

---

**END OF SYSTEM ARCHITECTURE MAP**

This document is a navigation tool, not a specification.
It describes what EXISTS, not what SHOULD exist.
Silence on a topic means UNCERTAIN, not "doesn't matter."
Verify all claims against current code when in doubt.
