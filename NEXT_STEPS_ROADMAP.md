# Next Steps Roadmap - Post Phase 4

**Current State:** Phase 4 Complete - M2/M5 wired to ObservationSystem
**Date:** 2026-01-10
**Branch:** phase-3-clean-history

---

## Current System Capabilities

### ✅ What Works Now

1. **Complete Observation → Execution Pipeline**
   - M1 (Ingestion) → M3 (Temporal) → M5 (Governance) → M6 (Execution)
   - ObservationSnapshot carries M4 primitive bundles
   - PolicyAdapter converts observations to mandates
   - ExecutionController processes mandates
   - RiskSystem validates actions

2. **Constitutional Compliance**
   - Epistemic boundaries enforced
   - M6 → M5 import prohibition active
   - Semantic leak prevention (CI enforcement)
   - Code freeze compliance

3. **Testing Infrastructure**
   - 16 runtime tests passing
   - Mock M2 population capability
   - End-to-end integration tests
   - CI/CD with pre-commit hooks

### ⚠️ Current Limitations

1. **M2 Store Empty**
   - No mechanism to create nodes from M1/M3 events
   - No liquidation → node creation logic
   - No trade → node association
   - All primitives return None

2. **Primitive Computation Stub**
   - `_compute_primitives_for_symbol()` returns None
   - No actual M5 queries executed
   - No real primitive values computed

3. **No Symbol-Specific Nodes**
   - Nodes lack symbol field
   - Cannot query "nodes for BTCUSDT"
   - Cannot compute symbol-specific primitives

---

## Phase 5: M1/M3 → M2 Node Population

**Objective:** Enable M2 node creation and maintenance from market data

**Status:** 🟡 Requires Architectural Decision

### Critical Design Questions

#### Q1: When to Create Nodes?

**Options:**
1. **On Liquidation Event** (Recommended)
   - Pro: Liquidations mark structural zones
   - Pro: Clear trigger condition
   - Con: Requires liquidation stream

2. **On Price Level Repetition**
   - Pro: Discovers support/resistance organically
   - Con: Complex detection logic
   - Con: Unclear threshold for "repetition"

3. **On M3 Window Closure**
   - Pro: Integrates with existing temporal logic
   - Con: Delayed node creation
   - Con: No direct liquidation association

**Recommendation:** Option 1 (On Liquidation Event)

#### Q2: How to Associate Trades with Nodes?

**Options:**
1. **Spatial Matching** (price within node band)
   - Pro: Simple, fast
   - Con: Overlapping nodes ambiguous

2. **Temporal + Spatial** (recent + near price)
   - Pro: More precise
   - Con: Requires timestamp tracking

3. **Volume-Weighted** (allocate by proximity)
   - Pro: Handles overlaps
   - Con: Complex computation

**Recommendation:** Option 1 initially (Spatial), upgrade to Option 2 if needed

#### Q3: Node Lifecycle Management?

**Node States:** ACTIVE → DORMANT → ARCHIVED

**Trigger Conditions:**
- ACTIVE → DORMANT: strength < 0.15 OR idle > 300s
- DORMANT → ARCHIVED: strength < 0.01 OR idle > 3600s

**Decay Strategy:**
- Active: 0.01/second
- Dormant: 0.001/second

**Question:** Should `advance_time()` trigger state updates?
- Pro: Deterministic, testable
- Con: Requires frequent calls

**Recommendation:** Yes, trigger on `advance_time()` every N seconds

### Implementation Tasks

#### 5.1: Add Symbol to Node Schema

**File:** `memory/enriched_memory_node.py`

```python
@dataclass
class EnrichedLiquidityMemoryNode:
    # ... existing fields ...
    symbol: str  # NEW FIELD
```

**Impact:**
- Update all node creation calls
- Update M2 store queries
- Update M5 query interfaces

#### 5.2: Implement Node Creation from Liquidation

**File:** `observation/governance.py`

```python
def ingest_observation(self, timestamp, symbol, event_type, payload):
    # ... existing code ...

    if event_type == 'LIQUIDATION':
        normalized_event = self._m1.normalize_liquidation(symbol, payload)
        if normalized_event:
            # Create M2 node
            self._create_node_from_liquidation(
                symbol=normalized_event['symbol'],
                price=normalized_event['price'],
                side=normalized_event['side'],
                timestamp=normalized_event['timestamp'],
                volume=normalized_event['quote_qty']
            )
```

**Design Decision Needed:**
- What should `node_id` be?
  - Format: `{symbol}_{side}_{price_bucket}`?
  - Example: `BTCUSDT_bid_50000`
- What should `price_band` be?
  - Fixed percentage (0.1%)?
  - Adaptive based on volatility?

#### 5.3: Implement Trade → Node Association

**File:** `observation/governance.py`

```python
def ingest_observation(self, timestamp, symbol, event_type, payload):
    # ... existing code ...

    if event_type == 'TRADE' and normalized_event:
        # Find nearby nodes
        nearby_nodes = self._m2_store.get_active_nodes(
            current_price=normalized_event['price'],
            radius=100.0  # Design decision: what radius?
        )

        # Update nodes with trade evidence
        for node in nearby_nodes:
            if node.symbol == symbol:  # NEW: symbol filter
                self._m2_store.update_with_trade(
                    node_id=node.id,
                    timestamp=timestamp,
                    volume=normalized_event['quote_qty'],
                    is_buyer_maker=normalized_event['side'] == 'SELL'
                )
```

**Design Decision Needed:**
- What radius for spatial matching?
- Handle overlapping nodes how?

#### 5.4: Implement Node Lifecycle Management

**File:** `observation/governance.py`

```python
def advance_time(self, new_timestamp: float):
    # ... existing code ...

    # Update M2 node states
    if self._system_time % 10.0 < new_timestamp % 10.0:  # Every 10 seconds
        self._m2_store.update_memory_states(new_timestamp)
        self._m2_store.decay_nodes(new_timestamp)
```

**Design Decision Needed:**
- How often to run state updates?
- Should decay run every advance_time() or batched?

### Testing Strategy

1. **Unit Tests:** Node creation from liquidation
2. **Integration Tests:** Trade association with nodes
3. **Lifecycle Tests:** State transitions over time
4. **Mock Data Tests:** Full M1 → M2 flow

### Blockers

**Architectural Decisions Required:**
1. Node ID format strategy
2. Price band calculation method
3. Spatial matching radius
4. State update frequency

**Authority Needed:**
- Approval to modify frozen `EnrichedLiquidityMemoryNode`
- Approval for node creation strategy
- Approval for lifecycle management triggers

---

## Phase 6: Actual Primitive Computation

**Objective:** Compute real M4 primitive values from populated M2

**Status:** 🔴 Blocked by Phase 5

**Dependency:** Requires M2 to be populated with nodes

### Implementation Approach

#### 6.1: Implement Zone Penetration

**File:** `observation/governance.py`

```python
def _compute_primitives_for_symbol(self, symbol: str) -> M4PrimitiveBundle:
    # Get active nodes for symbol
    nodes = self._m2_store.get_active_nodes()
    symbol_nodes = [n for n in nodes if n.symbol == symbol]

    if not symbol_nodes:
        return M4PrimitiveBundle(symbol=symbol, <all None>)

    # Pick strongest node as zone
    primary_node = symbol_nodes[0]  # Already sorted by strength

    # Get recent price data from M3
    recent_trades = self._m3.get_recent_trades(symbol)  # NEW METHOD NEEDED
    traversal_prices = [t['price'] for t in recent_trades]

    # Query M5 for zone penetration
    zone_penetration = self._m5_access.execute_query(
        "ZONE_PENETRATION_DEPTH",
        {
            "node_id": primary_node.id,
            "zone_low": primary_node.price_center - primary_node.price_band,
            "zone_high": primary_node.price_center + primary_node.price_band,
            "observed_low": min(traversal_prices) if traversal_prices else 0.0,
            "observed_high": max(traversal_prices) if traversal_prices else 0.0
        }
    )

    return M4PrimitiveBundle(
        symbol=symbol,
        zone_penetration=zone_penetration,  # REAL VALUE
        # ... rest None for now
    )
```

**New Requirements:**
- M3 needs `get_recent_trades()` method
- Decision: how far back to look? (last N trades? last N seconds?)

#### 6.2: Implement Displacement Origin Anchor

**Query Requirements:**
- Pre-traversal price sequence
- Pre-traversal timestamp sequence

**Data Source:** M3 temporal windows or M1 raw buffers?

#### 6.3: Implement Traversal Velocity

**Query Requirements:**
- Start price, end price
- Start timestamp, end timestamp
- Node ID

**Data Source:** M3 window aggregates?

### Design Questions

1. **Which primitive first?**
   - Recommend: Zone Penetration (simplest, clear data source)

2. **How to select "primary node" per symbol?**
   - Highest strength?
   - Most recent interaction?
   - Closest to current price?

3. **How to handle multiple nodes?**
   - Compute primitive for each, return strongest?
   - Compute only for primary node?
   - Aggregate across nodes?

4. **What if data insufficient?**
   - Return None (graceful degradation) ✅
   - Return partial result?
   - Raise exception?

### Testing Strategy

1. **Mock M2 + Mock M3:** Verify query construction
2. **Real M2 + Mock M3:** Test with populated nodes
3. **Real M2 + Real M3:** End-to-end with actual data
4. **Insufficient Data:** Verify graceful None return

---

## Phase 7: External Policy Activation

**Objective:** Enable frozen policies to use real primitives

**Status:** 🔴 Blocked by Phase 6

**Dependency:** Requires actual primitive values

### Verification Tasks

1. **Policy Evaluation Tests**
   - Verify policies handle None primitives correctly ✅ (already done)
   - Verify policies evaluate real primitives correctly
   - Verify mandate authority calculation

2. **Mandate Generation Tests**
   - Verify correct mandate types from primitives
   - Verify authority ordering respected
   - Verify arbitration resolution

3. **Execution Integration Tests**
   - Verify mandates reach ExecutionController
   - Verify position state machine transitions
   - Verify risk system validation

### Policy-Specific Testing

Each frozen policy needs validation:

**P1: Geometry Policy** (`runtime/external_policies/geometry_policy.py`)
- Requires: zone_penetration, displacement_origin_anchor
- Test: Sufficient/insufficient data cases

**P2: Kinematics Policy** (`runtime/external_policies/kinematics_policy.py`)
- Requires: price_traversal_velocity, traversal_compactness
- Test: Velocity thresholds

**P3: Absence Policy** (`runtime/external_policies/absence_policy.py`)
- Requires: structural_absence_duration
- Test: Absence detection

---

## Alternative: Fast Path to Live Testing

**If you want to test execution without full M2 population:**

### Option A: Manual M2 Seeding

Create a script to manually populate M2 with test nodes:

```python
# scripts/seed_m2_for_testing.py
obs_system = ObservationSystem(["BTCUSDT"])

# Manually create nodes at known price levels
obs_system._m2_store.add_or_update_node(
    node_id="BTCUSDT_bid_50000",
    price_center=50000.0,
    price_band=50.0,
    side="bid",
    symbol="BTCUSDT",  # NEW FIELD
    timestamp=1000.0,
    creation_reason="manual_seed",
    initial_strength=0.8,
    initial_confidence=0.7
)

# Get snapshot - will have real nodes
snapshot = obs_system.query({"type": "snapshot"})
```

**Pros:**
- Immediate primitive computation testing
- No need for M1/M3 → M2 wiring
- Can test policy evaluation quickly

**Cons:**
- Not production-ready
- Manual data creation tedious
- Doesn't test node creation logic

### Option B: Historical Data Replay

Load historical liquidation data and populate M2:

```python
# Load historical liquidations
liquidations = pd.read_parquet("historical_liquidations.parquet")

# Replay into observation system
for _, liq in liquidations.iterrows():
    obs_system.ingest_observation(
        timestamp=liq.timestamp,
        symbol=liq.symbol,
        event_type="LIQUIDATION",
        payload={...}
    )
```

**Requires:** Node creation from liquidation (Phase 5.2)

---

## Immediate Next Action Recommendations

### Path 1: Full Implementation (Recommended)

**Next Step:** Phase 5.1 - Add symbol field to nodes
1. Modify `EnrichedLiquidityMemoryNode` dataclass
2. Update all node creation sites
3. Add symbol filter to M2 queries
4. Run tests, verify no breakage

**Estimated Effort:** 1-2 hours
**Blockers:** None (code change, no architectural decisions)

### Path 2: Fast Testing Path

**Next Step:** Create manual M2 seeding script
1. Write `scripts/seed_m2_test.py`
2. Manually create 3-5 test nodes
3. Implement zone_penetration computation
4. Test end-to-end with seeded data

**Estimated Effort:** 2-3 hours
**Blockers:** Need M3 recent trades method (or mock it)

### Path 3: Architectural Planning

**Next Step:** Design document for M1/M3 → M2 integration
1. Document node creation strategy
2. Document trade association logic
3. Document lifecycle management
4. Get architectural approval
5. Implement Phase 5

**Estimated Effort:** Planning 1-2 hours, Implementation 4-6 hours
**Blockers:** Requires architectural decisions

---

## My Recommendation

**Start with Path 1 (Add symbol field to nodes)** because:
1. ✅ No blockers - pure code change
2. ✅ Necessary for all future work
3. ✅ Can be tested immediately
4. ✅ Enables both fast path and full implementation
5. ✅ Low risk (straightforward change)

After symbol field is added, you can choose:
- Path 2 (manual seeding) for quick validation
- Path 3 (full implementation) for production readiness

---

**Ready to proceed with:** Adding symbol field to nodes (Phase 5.1)

**Awaiting:** User confirmation to proceed
