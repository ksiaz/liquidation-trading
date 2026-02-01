# M2 / M4 Architectural State Discovery Report

**Date:** 2026-02-01
**Type:** Constitutional Architecture Examination
**Role:** Witness (factual, non-interpretive)

---

## M2 CURRENT STATE

### Structures

| Component | File | Purpose |
|-----------|------|---------|
| `ContinuityMemoryStore` | `memory/m2_continuity_store.py` | Central M2 store with three-state model |
| `EnrichedLiquidityMemoryNode` | `memory/enriched_memory_node.py` | Node with 4 evidence dimensions |
| `MemoryState` | `memory/m2_memory_state.py` | Enum: ACTIVE, DORMANT, ARCHIVED |
| `HistoricalEvidence` | `memory/m2_historical_evidence.py` | Compressed evidence for dormant nodes |
| `MemoryTopology` | `memory/m2_topology.py` | Spatial analysis (clusters, gaps) |
| `PressureMap` | `memory/m2_pressure.py` | Density metrics per price region |

**Internal Collections (ContinuityMemoryStore):**
```python
_active_nodes: Dict[str, EnrichedLiquidityMemoryNode]
_dormant_nodes: Dict[str, EnrichedLiquidityMemoryNode]
_dormant_evidence: Dict[str, HistoricalEvidence]
_archived_nodes: Dict[str, EnrichedLiquidityMemoryNode]
```

**Node Fields (EnrichedLiquidityMemoryNode):**
- Identity: `id`, `symbol`, `price_center`, `price_band`, `side`
- Temporal: `first_seen_ts`, `last_interaction_ts`
- Memory: `strength`, `confidence`, `decay_rate`, `active`
- Dimension 1: `interaction_count`, `trade_execution_count`, `liquidation_proximity_count`, `volume_total`
- Dimension 2: `buyer_initiated_volume`, `seller_initiated_volume`
- Dimension 3: `interaction_timestamps`, `strength_history`
- Dimension 4: `liquidations_within_band`, `long_liquidations`, `short_liquidations`

### Population Mechanisms

| Path | Trigger | File:Line | Runtime Reachable |
|------|---------|-----------|-------------------|
| `_create_or_update_node_from_liquidation()` | LIQUIDATION event | governance.py:415 | **YES** |
| `_associate_trade_with_nodes()` | TRADE event (≥$1000) | governance.py:462 | **YES** |

**Evidence from execution.db:**
```
Nodes by creation_reason:
  large_trade: 6,294,501
  liquidation: 15,818,851
  TOTAL: 22,113,352 nodes
```

### Mutation

| Mechanism | Trigger | File:Line |
|-----------|---------|-----------|
| `decay_nodes(current_ts)` | Every 10 seconds via `advance_time()` | governance.py:366 |
| `update_memory_states(current_ts)` | Every 10 seconds via `advance_time()` | governance.py:368 |
| `record_trade_at_node()` | Trade near existing node | governance.py:486 |
| `record_liquidation_at_node()` | Liquidation matches existing node | governance.py:445 |

**Issue Observed:** Nodes created from liquidation events have `liquidation_count = 0`:
```
cur.execute('SELECT COUNT(*) FROM m2_nodes WHERE liquidation_count > 0')
Result: 0
```
This occurs because `_create_or_update_node_from_liquidation()` only calls `record_liquidation_at_node()` for **existing** nodes, not newly created ones.

### Symbol Scope

**YES** - Symbol is enforced as partitioning key:
- Nodes have `symbol` field set at creation
- Queries use `get_active_nodes_for_symbol(symbol)` at governance.py:752
- Node IDs include symbol: `{symbol}_{side}_{price_bucket}`

### Lifecycle Logic

| Transition | Condition | Threshold |
|------------|-----------|-----------|
| ACTIVE → DORMANT | `strength < 0.15` OR `idle > 3600s` | MemoryStateThresholds |
| DORMANT → ARCHIVED | `strength < 0.01` OR `idle > 86400s` | MemoryStateThresholds |
| DORMANT → ACTIVE | Revival on new evidence | `add_or_update_node()` checks dormant |

**Decay Rates:**
- ACTIVE: 0.0001 per second
- DORMANT: 0.00001 per second (10x slower)

### Runtime Reality

**POPULATED AND FUNCTIONALLY USED**

Evidence:
1. 22+ million M2 node records in execution.db
2. Nodes created from both liquidations (71%) and large trades (29%)
3. M4 pattern detection queries M2 at runtime (governance.py:752)
4. Cleanup coordinator has `m2_archived_nodes` pruner active

---

## M4 CURRENT STATE

### Defined Primitives

**M4PrimitiveBundle** (observation/types.py) contains 24 primitive fields:

| Tier | Primitive | Type |
|------|-----------|------|
| A | zone_penetration | ZonePenetrationDepth |
| A | displacement_origin_anchor | DisplacementOriginAnchor |
| A | price_traversal_velocity | PriceTraversalVelocity |
| A | traversal_compactness | TraversalCompactness |
| A | central_tendency_deviation | CentralTendencyDeviation |
| B-1 | structural_absence_duration | StructuralAbsenceDuration |
| B-1 | traversal_void_span | TraversalVoidSpan |
| B-1 | event_non_occurrence_counter | EventNonOccurrenceCounter |
| B-2 | structural_persistence_duration | StructuralPersistenceDuration |
| B-2.1 | resting_size | RestingSizeAtPrice |
| B-2.1 | order_consumption | OrderConsumption |
| B-2.1 | absorption_event | AbsorptionEvent |
| B-2.1 | refill_event | RefillEvent |
| B-2.2 | price_acceptance_ratio | PriceAcceptanceRatio |
| B-3 | liquidation_density | LiquidationDensity |
| B-4 | directional_continuity | DirectionalContinuity |
| B-4 | trade_burst | TradeBurst |
| B-5 | order_block | OrderBlockPrimitive |
| B-5 | supply_demand_zone | SupplyDemandZonePrimitive |
| B-6 | liquidation_cascade_proximity | LiquidationCascadeProximity |
| B-6 | cascade_state | CascadeStateObservation |
| B-6 | leverage_concentration_ratio | LeverageConcentrationRatio |
| B-6 | open_interest_directional_bias | OpenInterestDirectionalBias |

### Computation Sites

**Single Computation Point:** `_compute_primitives_for_symbol()` in governance.py:550-1136

Called from: `_get_snapshot()` at governance.py:536

**Computation Sources:**
| Primitive | Data Source | M2 Dependency |
|-----------|-------------|---------------|
| zone_penetration | M1 trades | NO |
| traversal_velocity | M1 trades | NO |
| traversal_compactness | M1 trades | NO |
| resting_size | M1 depth | NO |
| order_consumption | M1 depth (current vs previous) | NO |
| absorption_event | M1 depth + trades | NO |
| liquidation_density | M1 liquidations | NO |
| **order_block** | **M2 active_nodes** | **YES** |
| **supply_demand_zone** | **M2 active_nodes (clusters)** | **YES** |
| structural_absence | M2 node presence intervals | YES |
| structural_persistence | M2 node presence intervals | YES |
| cascade_proximity | HyperliquidCollector | NO (HL data) |
| cascade_state | HL liquidation tracking | NO (HL data) |

### Inputs

| Primitive | Input Source | Input Method |
|-----------|--------------|--------------|
| Tier A (kinematics) | M1 raw_trades | `self._m1.raw_trades.get(symbol)` |
| Tier B-2.1 (orderbook) | M1 latest_depth, previous_depth | `self._m1.latest_depth.get(symbol)` |
| Tier B-5 (patterns) | M2 active_nodes | `self._m2_store.get_active_nodes_for_symbol(symbol)` |
| Tier B-6 (cascade) | HyperliquidCollector | `self._hl_collector.get_proximity()` |

### Runtime Outputs

**Evidence from execution.db (primitive_values table):**

| Primitive | Non-null Count | Sample Value |
|-----------|----------------|--------------|
| zone_penetration_depth | 600,648 | 462.65 |
| price_velocity | 584,050 | 2.59 |
| traversal_compactness | 584,056 | 0.88 |
| acceptance_ratio | 584,056 | 0.94 |
| central_tendency_deviation | 600,551 | 0.60 |
| resting_size_bid | 750,698 | 10.356 |
| resting_size_ask | 750,698 | 1.125 |
| liquidation_density | 315,886 | 0.066 |
| directional_continuity | 600,646 | 9.0 |
| trade_burst_count | 600,648 | 10 |
| absorption_event | 627 | 1 (boolean) |
| refill_event | 290,027 | 1 (boolean) |

**Conclusion:** M4 primitives **ARE** producing runtime values.

### Snapshot Presence

**YES** - Primitives are included in ObservationSnapshot:
```python
# observation/types.py
@dataclass(frozen=True)
class ObservationSnapshot:
    primitives: Dict[str, M4PrimitiveBundle]  # symbol -> bundle
```

Populated at governance.py:547:
```python
primitives[symbol] = self._compute_primitives_for_symbol(symbol)
```

---

## M2 ⇄ M4 RELATIONSHIP

### Dependency Type

**PARTIAL** - M4 depends on M2 for pattern detection primitives only.

### Evidence

| M4 Primitive | M2 Usage | File:Line |
|--------------|----------|-----------|
| order_block | `detect_order_block(node, ...)` for each active node | governance.py:763-773 |
| supply_demand_zone | `find_node_clusters(active_nodes, ...)` | governance.py:784-813 |
| structural_absence | `node.first_seen_ts`, `node.last_interaction_ts` | governance.py:925-952 |
| structural_persistence | Same as above | governance.py:941-945 |

### Consequence

- **Tier A primitives** (zone, velocity, compactness): Work without M2
- **Tier B-2.1 primitives** (orderbook): Work without M2
- **Tier B-5 primitives** (order_block, supply_demand_zone): **REQUIRE M2**
- **Tier B-6 primitives** (cascade): Work without M2 (use HL data)

If M2 is empty, order_block and supply_demand_zone will always be None.
Since M2 **IS** populated, these primitives **CAN** produce values.

---

## EXECUTION CHAIN (AS-IS)

```
1. Raw data enters: ingest_observation(timestamp, symbol, event_type, payload)
   └── governance.py:254

2. M1 normalizes:
   ├── TRADE → normalize_trade() → trades buffer
   ├── LIQUIDATION → normalize_liquidation() → liquidations buffer
   ├── DEPTH → normalize_depth() → latest_depth/previous_depth
   └── HL_PRICE → normalize_hl_price() → HL price buffer

3. M2 is populated:
   ├── TRADE (large) → _associate_trade_with_nodes() → add_or_update_node()
   └── LIQUIDATION → _create_or_update_node_from_liquidation() → add_or_update_node()

4. M4 primitives computed (on snapshot request):
   └── _compute_primitives_for_symbol() returns M4PrimitiveBundle
       ├── Tier A: From M1 trades
       ├── Tier B-2.1: From M1 depth
       ├── Tier B-5: From M2 active_nodes
       └── Tier B-6: From HL collector

5. ObservationSnapshot returned:
   └── Contains primitives: Dict[str, M4PrimitiveBundle]
```

**Chain Status:** COMPLETE - Data flows from ingestion through M2 population to M4 computation.

---

## FIRST BLOCKER

### Description

The chain is **functionally complete**, but with a data quality issue:

**M2 nodes created from liquidation events do NOT record the liquidation evidence on the node itself.**

### Location

`governance.py:445-460`:
```python
if existing_node:
    # Update existing node - DOES record liquidation
    self._m2_store.record_liquidation_at_node(node_id, timestamp, side)
else:
    # Create new node - does NOT record liquidation
    self._m2_store.add_or_update_node(
        ...
        creation_reason="liquidation",
        initial_strength=0.5,
        volume=volume
    )
    # ← MISSING: record_liquidation_at_node() call
```

### Evidence

```sql
SELECT COUNT(*) FROM m2_nodes WHERE liquidation_count > 0;
-- Result: 0 (zero nodes have liquidation_count > 0)

SELECT COUNT(*) FROM m2_nodes WHERE creation_reason = 'liquidation';
-- Result: 15,818,851 (but none have liquidation_count recorded)
```

### Downstream Effect

- M2 nodes created from liquidations have `liquidation_count = 0`
- `liquidation_proximity_count = 0` for all nodes
- M4 primitives that rely on node-level liquidation evidence (if any) would receive incomplete data
- Pattern detection (order_block, supply_demand_zone) may underweight liquidation-origin nodes

---

## SECONDARY ISSUES

### Undefined Attributes

1. **`self._cycle_count`** - Referenced at governance.py:755 but never initialized
2. **`self._symbols`** - Referenced at governance.py:956 but never initialized (should be `self._observed_symbols` or `self._allowed_symbols`)

These would cause AttributeError if the code paths are reached.

### Diagnostic Mode Gating

`_DIAG_M2` flag gates useful diagnostic output but the diagnostic code has bugs (undefined attributes above).

---

## SUMMARY (NON-INTERPRETIVE)

M2 (Memory Layer) is structurally complete and populated at runtime with 22+ million nodes created from liquidation events (71%) and large trades (29%). Nodes transition through ACTIVE → DORMANT → ARCHIVED lifecycle with time-based decay. M4 (Structural Primitives) is functionally complete with 24 defined primitives, computed on-demand in `_compute_primitives_for_symbol()`. M4 primitives produce runtime values (600k+ non-null records). M4 depends on M2 **partially** for Tier B-5 pattern detection (order_block, supply_demand_zone). The execution chain from ingestion to snapshot is complete. One data quality issue exists: nodes created from liquidations do not record the liquidation evidence on the node itself, resulting in `liquidation_count = 0` for all nodes despite 15.8M being liquidation-origin.

---

*Report generated: 2026-02-01*
*Examination method: Code inspection + runtime evidence from execution.db*
