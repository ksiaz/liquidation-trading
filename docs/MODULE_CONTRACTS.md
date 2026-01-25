# Module Contracts

**Status:** Canonical Reference
**Authority:** System Integrity Guidelines
**Purpose:** Define input/output contracts for all modules

---

## Overview

This document specifies the contracts for each module in the system. Every module has:
- **Input Contract**: What the module receives
- **Output Contract**: What the module produces
- **Allowed Operations**: What the module may do
- **Forbidden Operations**: What the module must NOT do
- **Dependencies**: What other modules it relies on

**Rule:** If a contract is violated, the system must fail loudly, not silently continue.

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     LAYER 6: MONITORING                         │
│  runtime/analytics/  runtime/meta/  runtime/logging/           │
├─────────────────────────────────────────────────────────────────┤
│                     LAYER 5: EXECUTION                          │
│  runtime/exchange/  runtime/executor/  runtime/m6_executor.py  │
├─────────────────────────────────────────────────────────────────┤
│                     LAYER 4: RISK MANAGEMENT                    │
│  runtime/risk/  runtime/position/                              │
├─────────────────────────────────────────────────────────────────┤
│                     LAYER 3: ARBITRATION                        │
│  runtime/arbitration/                                          │
├─────────────────────────────────────────────────────────────────┤
│                     LAYER 2: ANALYSIS / FEATURES                │
│  analysis/  runtime/liquidations/  runtime/orderflow/          │
│  runtime/regime/  runtime/validation/                          │
├─────────────────────────────────────────────────────────────────┤
│                     LAYER 1: OBSERVATION / INGESTION            │
│  observation/  runtime/hyperliquid/  runtime/binance/          │
│  runtime/collector/                                            │
└─────────────────────────────────────────────────────────────────┘
```

**Data flows DOWN only (higher layers depend on lower layers).**

---

## Layer 1: Observation / Ingestion

### observation/types.py

**Purpose:** Core observation types for the M1-M5 system.

**Output Types:**
```python
@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus        # UNINITIALIZED or FAILED only
    timestamp: float                 # Last advance_time parameter
    symbols_active: List[str]        # Configured set only
    counters: SystemCounters         # Factual counts only
    promoted_events: List[Dict]      # Raw events
    primitives: Dict[str, M4PrimitiveBundle]  # Symbol -> primitives

@dataclass(frozen=True)
class M4PrimitiveBundle:
    symbol: str
    zone_penetration: Optional[ZonePenetrationDepth]
    # ... (all primitives may be None)
```

**Invariants:**
- All types are `frozen=True` (immutable after construction)
- `status` may only be UNINITIALIZED or FAILED
- `primitives` values may be None (absence of fact, not failure)

---

### runtime/hyperliquid/types.py

**Purpose:** Hyperliquid-specific data types.

**Output Types:** Exchange data structures for positions, orders, market data.

**Allowed:** Parse raw exchange responses, normalize to internal types.
**Forbidden:** Interpret data, assign meaning, compute features.

---

### runtime/hyperliquid/client.py

**Input Contract:**
- Raw HTTP/WebSocket responses from Hyperliquid API
- Credentials (API key, secret)

**Output Contract:**
- Normalized position data
- Order book snapshots
- Trade data
- Account state

**Allowed:**
- Parse JSON responses
- Normalize field names
- Convert timestamps to nanoseconds

**Forbidden:**
- Compute indicators
- Interpret positions as "strong" or "weak"
- Filter data by "importance"

---

### runtime/hyperliquid/collector.py

**Input Contract:**
- Connection to Hyperliquid WebSocket
- Symbol whitelist

**Output Contract:**
- Raw market data events
- Data timestamps

**Allowed:**
- Subscribe to data feeds
- Buffer incoming data
- Pass through events

**Forbidden:**
- Aggregate data
- Compute derived values
- Drop events silently

---

### observation/internal/m1_ingestion.py

**Input Contract:**
- Raw market events (trades, liquidations, order book)
- Timestamps

**Output Contract:**
- Normalized events in M1 format
- Event IDs for traceability

**Allowed:**
- Normalize field names
- Convert types
- Assign sequential IDs

**Forbidden:**
- Filter "unimportant" events
- Interpret event significance
- Drop data silently

---

## Layer 2: Analysis / Features

### analysis/cascade_labeler.py

**Input Contract:**
```python
# From database (runtime/logging/execution_db.py)
- hl_oi_snapshots: OI data over time
- hl_liquidations: Liquidation events
- hl_mark_prices: Price data
```

**Output Contract:**
```python
@dataclass
class LabeledCascade:
    cascade_id: int
    coin: str
    start_ts: int
    end_ts: int
    oi_drop_pct: Decimal
    liquidation_count: int
    wave_count: int
    price_start: Decimal
    price_end: Decimal
    outcome: str  # REVERSAL, CONTINUATION, NEUTRAL
```

**Allowed:**
- Detect cascades by mechanical rules (OI drop >X% in <Y seconds)
- Count liquidations
- Compute price changes

**Forbidden:**
- Predict future cascades
- Assign "quality" scores
- Interpret as "good" or "bad"

---

### analysis/wave_detector.py

**Input Contract:**
- List of liquidation events with timestamps
- Time gap threshold for wave separation

**Output Contract:**
```python
@dataclass
class WaveLabel:
    wave_num: int
    start_ts: int
    end_ts: int
    liquidation_count: int
    oi_drop_pct: Decimal
```

**Allowed:**
- Group liquidations by time gaps
- Count waves
- Compute per-wave metrics

**Forbidden:**
- Predict wave outcomes
- Assign wave "strength"

---

### analysis/validators/*.py

**Input Contract:**
- List of LabeledCascade events
- Historical price/OI data

**Output Contract:**
```python
@dataclass
class ValidationResult:
    hypothesis_name: str
    total_events: int
    supporting_events: int
    success_rate: float
    calibrated_threshold: Optional[float]
    status: str  # VALIDATED, FAILED, INSUFFICIENT_DATA
```

**Allowed:**
- Count events matching hypothesis criteria
- Calculate success rates
- Report raw statistics

**Forbidden:**
- Claim hypothesis is "correct"
- Predict future validity

---

### runtime/liquidations/burst_aggregator.py

**Input Contract:**
- Stream of liquidation events
- Aggregation window (seconds)

**Output Contract:**
- Liquidation bursts (grouped events)
- Burst statistics (count, total size)

**Forbidden:**
- Interpret burst as "strong signal"
- Predict cascade continuation

---

### runtime/regime/classifier.py

**Input Contract:**
- Market data (price, volume, OI)
- Observation snapshot

**Output Contract:**
```python
class RegimeType(Enum):
    UNKNOWN = "UNKNOWN"
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
```

**Allowed:**
- Classify current regime by factual metrics
- Return UNKNOWN if insufficient data

**Forbidden:**
- Predict regime changes
- Assign regime "confidence"

---

## Layer 3: Arbitration

### runtime/arbitration/types.py

**Types:**
```python
class MandateType(Enum):
    EXIT = 5      # Highest authority
    BLOCK = 4
    REDUCE = 3
    ENTRY = 2
    HOLD = 1      # Lowest

@dataclass(frozen=True)
class Mandate:
    symbol: str
    type: MandateType
    authority: float
    timestamp: float

@dataclass(frozen=True)
class Action:
    type: ActionType  # ENTRY, EXIT, REDUCE, HOLD, NO_ACTION
    symbol: str
    strategy_id: Optional[str]
```

---

### runtime/arbitration/arbitrator.py

**Input Contract:**
- List of Mandates from multiple strategies
- Current position state per symbol

**Output Contract:**
- Single Action per symbol (Theorem 4.1)
- Action selected by authority hierarchy

**Allowed:**
- Compare mandate authorities
- Select highest-authority mandate
- Convert mandate to action

**Forbidden:**
- Combine mandates
- Emit multiple actions per symbol
- Invent new action types

**Invariant:** Exactly one Action per symbol per cycle.

---

## Layer 4: Risk Management

### runtime/risk/types.py

**Types:**
```python
@dataclass(frozen=True)
class RiskConfig:
    L_max: float = 10.0           # Maximum leverage
    D_min_safe: float = 0.08      # 8% min liquidation distance
    D_critical: float = 0.03     # 3% emergency threshold
    stop_loss_pct: float = 0.02  # 2% position stop
    # ... (all constants, no runtime interpretation)

@dataclass(frozen=True)
class AccountState:
    equity: Decimal
    margin_available: Decimal
    timestamp: float

@dataclass(frozen=True)
class PositionRisk:
    symbol: str
    direction: Direction
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    liquidation_price: Decimal
    liquidation_distance: float

@dataclass(frozen=True)
class PortfolioRisk:
    total_leverage: float
    min_liquidation_distance: float
    # ... (pure calculations)

@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: Optional[str]
    violated_invariant: Optional[str]
    blocking: bool
```

---

### runtime/risk/calculator.py

**Input Contract:**
- AccountState
- List of PositionRisk

**Output Contract:**
- PortfolioRisk (aggregate metrics)

**Allowed:**
- Sum exposures
- Calculate leverage
- Find minimum liquidation distance

**Forbidden:**
- Interpret risk as "acceptable"
- Make trading decisions

---

### runtime/risk/capital_manager.py

**Input Contract:**
- AccountState
- RiskConfig
- Current positions

**Output Contract:**
- Maximum position size (Decimal)
- Available capital (Decimal)

**Allowed:**
- Calculate position sizing by formula
- Enforce capital limits

**Forbidden:**
- Override limits dynamically
- Interpret "safe" sizes

---

### runtime/risk/circuit_breaker.py

**Input Contract:**
- Trade history
- Loss thresholds

**Output Contract:**
- CircuitState: CLOSED (trading allowed) or OPEN (blocked)

**Allowed:**
- Count losses
- Trip breaker on threshold
- Emit BLOCK mandates

**Forbidden:**
- Auto-reset without explicit trigger
- Partial blocking

---

### runtime/position/types.py

**Types:**
```python
class PositionState(Enum):
    FLAT = "FLAT"
    ENTERING = "ENTERING"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSING = "CLOSING"

@dataclass(frozen=True)
class Position:
    symbol: str
    state: PositionState
    direction: Optional[Direction]
    quantity: Decimal
    entry_price: Optional[Decimal]
```

**Invariants (enforced in __post_init__):**
- I-PSM-1: FLAT ⟹ quantity=0 AND direction=None
- I-PSM-2: OPEN ⟹ quantity≠0 AND direction≠None

---

### runtime/position/state_machine.py

**Input Contract:**
- Current Position
- Action to execute
- Exchange fill events

**Output Contract:**
- New Position state
- InvariantViolation exception if illegal transition

**Allowed Transitions:**
```
FLAT → ENTERING (on ENTRY)
ENTERING → OPEN (on fill)
ENTERING → FLAT (on cancel/reject)
OPEN → REDUCING (on REDUCE)
OPEN → CLOSING (on EXIT)
REDUCING → OPEN (on partial fill)
REDUCING → FLAT (on complete fill)
CLOSING → FLAT (on complete fill)
```

**Forbidden:**
- Skip states (FLAT → OPEN directly)
- Infer state
- Auto-correct invalid states

---

## Layer 5: Execution

### runtime/exchange/types.py

**Types:**
```python
class OrderType(Enum):
    MARKET, LIMIT, STOP_MARKET, STOP_LIMIT, POST_ONLY, IOC

class OrderStatus(Enum):
    PENDING, SUBMITTED, ACKNOWLEDGED, PARTIAL, FILLED, CANCELED, REJECTED

@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float]
    # ...

@dataclass
class OrderResponse:
    success: bool
    order_id: Optional[str]
    status: OrderStatus
    error_message: Optional[str]

@dataclass
class OrderFill:
    order_id: str
    price: float
    size: float
    timestamp_ns: int
```

---

### runtime/exchange/order_executor.py

**Input Contract:**
- OrderRequest
- Exchange client

**Output Contract:**
- OrderResponse

**Allowed:**
- Validate order parameters
- Submit to exchange
- Return response

**Forbidden:**
- Modify order parameters silently
- Retry without explicit request

---

### runtime/exchange/fill_tracker.py

**Input Contract:**
- Order ID
- Exchange WebSocket / REST API

**Output Contract:**
- OrderFill events
- Timeout notification

**Allowed:**
- Poll for fills
- Track fill progress
- Detect timeout

**Forbidden:**
- Assume fills (must confirm)
- Auto-cancel without instruction

---

### runtime/exchange/position_reconciler.py

**Input Contract:**
- Local position state
- Exchange position query

**Output Contract:**
```python
@dataclass
class ReconciliationResult:
    symbol: str
    expected_size: float
    actual_size: float
    action: ReconciliationAction  # NONE, SYNC_LOCAL, EMERGENCY_CLOSE
    discrepancy: float
```

**Allowed:**
- Compare local vs exchange
- Recommend sync action
- Flag mismatches

**Forbidden:**
- Auto-close positions without explicit flag
- Silently ignore discrepancies

---

### runtime/executor/types.py

**Types:**
```python
@dataclass(frozen=True)
class ExecutionResult:
    symbol: str
    action: ActionType
    success: bool
    state_before: PositionState
    state_after: PositionState
    timestamp: float
    error: Optional[str]
    # Equity tracking fields for audit

@dataclass(frozen=True)
class CycleStats:
    mandates_received: int
    actions_executed: int
    actions_rejected: int
    symbols_processed: int
```

---

### runtime/executor/controller.py

**Input Contract:**
- List of Actions from arbitrator
- Current position states
- Exchange client

**Output Contract:**
- List of ExecutionResult
- CycleStats

**Allowed:**
- Validate action against position state
- Submit orders via exchange layer
- Log execution results

**Forbidden:**
- Re-interpret actions
- Skip validation
- Execute without logging

---

## Layer 6: Monitoring

### runtime/analytics/types.py

**Types:**
```python
@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    strategy: str
    direction: str
    entry_time_ns: int
    entry_price: float
    exit_time_ns: Optional[int]
    exit_price: Optional[float]
    realized_pnl: float
    net_pnl: float

@dataclass
class PerformanceSnapshot:
    total_trades: int
    win_rate: float
    sharpe_ratio_30d: float
    current_drawdown_pct: float
    # ...

@dataclass
class Alert:
    alert_id: str
    level: AlertLevel  # INFO, WARNING, ERROR, CRITICAL, EMERGENCY
    category: str
    message: str
```

---

### runtime/analytics/trade_journal.py

**Input Contract:**
- Trade open/close events
- PnL data

**Output Contract:**
- TradeRecord (complete trade history)
- DailyStats

**Allowed:**
- Record trades
- Calculate PnL
- Persist to file

**Forbidden:**
- Interpret trades
- Predict performance

---

### runtime/analytics/performance_tracker.py

**Input Contract:**
- Closed TradeRecord entries

**Output Contract:**
- PerformanceSnapshot
- Win rate, Sharpe, drawdown metrics

**Allowed:**
- Calculate statistics from history
- Track rolling metrics

**Forbidden:**
- Predict future performance
- Recommend actions

---

### runtime/meta/types.py

**Types:**
```python
@dataclass
class Assumption:
    name: str
    description: str
    category: str
    test_fn: Optional[Callable[[], bool]]
    status: AssumptionStatus  # UNTESTED, VALID, WARNING, INVALID, EXPIRED
    affected_components: List[str]

@dataclass
class CalibratedParameter:
    name: str
    value: float
    expected_mean: Optional[float]
    expected_std: Optional[float]
    health_status: ModelHealthStatus  # HEALTHY, DRIFTING, BROKEN

class SystemRegime(Enum):
    UNKNOWN, EDGE_PRESENT, EDGE_DECAYING, EDGE_GONE, REGIME_CHANGE
```

---

### runtime/meta/assumption_registry.py

**Input Contract:**
- Assumption definitions with test functions

**Output Contract:**
- Validation results per assumption
- List of invalid/expired assumptions
- Component safety status

**Allowed:**
- Run assumption tests
- Track validation history
- Report unsafe components

**Forbidden:**
- Auto-fix assumptions
- Silently ignore failures

---

## End-to-End Data Flow

```
1. INGESTION
   raw exchange data → runtime/hyperliquid/client.py
   → normalized events

2. OBSERVATION
   normalized events → observation/internal/m1_ingestion.py
   → M1 events → m3_temporal.py → ObservationSnapshot

3. ANALYSIS (offline)
   raw data → analysis/cascade_labeler.py → LabeledCascade
   → analysis/validators/ → ValidationResult

4. STRATEGY (external)
   ObservationSnapshot → external_policy/*.py → List[Mandate]

5. ARBITRATION
   List[Mandate] → runtime/arbitration/arbitrator.py → Action

6. RISK VALIDATION
   Action → runtime/risk/calculator.py → ValidationResult
   (BLOCK if invalid)

7. POSITION STATE
   Action → runtime/position/state_machine.py → Position transition

8. EXECUTION
   Action + Position → runtime/exchange/order_executor.py
   → OrderResponse → fill_tracker.py → OrderFill

9. RECONCILIATION
   Position + Exchange state → position_reconciler.py
   → ReconciliationResult

10. MONITORING
    TradeRecord → runtime/analytics/ → PerformanceSnapshot
    SystemState → runtime/meta/ → Assumption validation
```

---

## Contract Validation Checklist

Before modifying any module:

1. [ ] Identify input contract
2. [ ] Identify output contract
3. [ ] Verify change preserves both contracts
4. [ ] Check no silent data loss
5. [ ] Check no new fields without approval
6. [ ] Check no type changes
7. [ ] Check layer boundaries respected
8. [ ] Add tests for contract validation

---

## Schema Stability Rules

**NEVER without explicit approval:**
- Rename fields
- Remove fields
- Change types
- Add required fields

**ALLOWED:**
- Add Optional fields with default values
- Add new types (not modifying existing)
- Add validation methods

---

## Failure Modes

Each module must handle:

1. **Invalid Input:** Raise explicit error with details
2. **Missing Data:** Return None or empty result, never invent data
3. **Contract Violation:** Raise exception, never auto-correct
4. **Timeout:** Return explicit timeout error
5. **Unknown State:** Return UNKNOWN, never guess

**Rule:** Silent failure is worse than crashing.

---

## Identified Contract Gaps (2026-01-25)

### Gap 1: Position Persistence Not Implemented

**Location:** `runtime/executor/controller.py`

**Issue:** `ExecutionController` maintains position state in-memory only via `PositionStateMachine`. There is no persistence layer to save/load positions from database.

**Impact:**
- Positions are lost on restart
- Cannot implement "position recovery" on crash
- `test_position_persistence_synthetic` fails

**Resolution Options:**
1. Add position persistence to `ExecutionController` (requires db_path parameter)
2. Move persistence responsibility to `CollectorService`
3. Add separate `PositionRepository` class

**Status:** Known limitation, documented

---

### Gap 2: M4PrimitiveBundle Requires All Fields

**Location:** `observation/types.py`

**Issue:** `M4PrimitiveBundle` is a frozen dataclass without default values, requiring all 24 primitive fields to be explicitly provided.

**Impact:**
- Test code must use helper functions to create empty bundles
- Cannot partially construct bundles

**Resolution Options:**
1. Add factory function `M4PrimitiveBundle.empty(symbol)`
2. Add `field(default=None)` to all Optional fields

**Status:** Documented, helper function added to tests

---

### Gap 3: RiskConfig Internal Validation

**Location:** `runtime/risk/types.py`

**Issue:** `RiskConfig` has internal validation that requires:
- `L_target <= L_max`
- `L_symbol_max <= L_max`
- `D_critical < D_min_safe`

**Impact:**
- Cannot create arbitrary test configurations without respecting internal constraints
- Test code must use default config or carefully construct valid configs

**Resolution Options:**
1. Add `RiskConfig.for_testing()` factory with relaxed constraints
2. Document constraints in contract

**Status:** Documented

---

### Gap 4: Strategy Direction Not Passed Through

**Location:** `runtime/executor/controller.py`

**Issue:** When processing `ENTRY` action, the controller defaults to `Direction.LONG`. The actual direction from the strategy mandate is not passed through the arbitration layer.

**Code Location:** Lines 186-187
```python
new_position = self.state_machine.transition(
    symbol, state_action, direction=Direction.LONG  # Always LONG
)
```

**Impact:**
- SHORT positions cannot be opened via mandate flow
- Direction must be inferred elsewhere (e.g., ghost tracker)

**Resolution Options:**
1. Add `direction` field to `Action` type
2. Extract direction from original `Mandate` metadata

**Status:** Known limitation, documented

---

### Gap 5: Missing Test Coverage for Skipped Tests

**Location:** Various integration test files

**Issue:** 13 tests are marked as skipped, indicating incomplete functionality.

**Files:**
- `test_data_flow_coherence.py` - All tests pass
- `test_contract_boundaries.py` - All tests pass
- Other files may have conditional skips

**Resolution:** Review skipped tests and either implement or remove them.

**Status:** Documented for future review
