# System Audit: Data Sources & Primitive Computation

**Date:** 2026-01-12
**Status:** CRITICAL GAPS FOUND
**Authority:** Constitutional verification against frozen external policies

---

## Executive Summary

**CRITICAL FINDINGS:**
1. ❌ **2 primitives required by frozen policies are NOT being computed**
2. ❌ **Price Acceptance Ratio** - Required by kinematics policy, NOT in computation pipeline
3. ❌ **Structural Persistence Duration** - Required by absence policy, NOT in computation pipeline
4. ✓ **All 3 data sources operational** (trades, liquidations, order book)
5. ⚠️ **Frozen policies cannot generate proposals without missing primitives**

---

## Part 1: Data Sources Audit

### 1.1 Data Sources Configured

**CollectorService ([runtime/collector/service.py](runtime/collector/service.py:69-75)):**
```python
streams = [
    f"{s.lower()}@aggTrade" for s in TOP_10_SYMBOLS      # TRADES
] + [
    f"{s.lower()}@forceOrder" for s in TOP_10_SYMBOLS    # LIQUIDATIONS
] + [
    f"{s.lower()}@depth@100ms" for s in TOP_10_SYMBOLS   # ORDER BOOK
]
```

**Status:** ✓ All 3 data sources subscribed

### 1.2 Data Source Ingestion

| Data Source | M1 Normalization | M2 Processing | Used By Primitives |
|-------------|------------------|---------------|---------------------|
| **Trades** | ✓ M1.normalize_trade() | ✓ M2.ingest_trade() | M3 price history, node updates |
| **Liquidations** | ✓ M1.normalize_liquidation() | ✓ M2.ingest_liquidation() | M2 node creation, liquidation_density |
| **Order Book** | ✓ M1.normalize_depth() | ✓ M2.update_node_orderbook() | resting_size, consumption, absorption, refill |

**Status:** ✓ All data sources fully integrated into M1-M2 pipeline

### 1.3 Data Source Usage Verification

**From overnight trace (trace_overnight.json):**
- 20 execution events
- All 3 frozen policies activated (Geometry, Kinematics, Absence)
- Multi-symbol execution (9 symbols)
- **Conclusion:** Data sources are being received and processed

---

## Part 2: Primitive Computation Audit

### 2.1 Primitives Currently Being Computed

**Source:** [observation/governance.py:278-523](observation/governance.py:278-523)

| # | Primitive | Computed | Data Source | Policy Usage |
|---|-----------|----------|-------------|--------------|
| 1 | zone_penetration | ✓ | M2 nodes + M3 prices | Geometry, Absence (optional) |
| 2 | displacement_origin_anchor | ✓ | M3 prices | - |
| 3 | price_traversal_velocity | ✓ | M3 prices | Kinematics |
| 4 | traversal_compactness | ✓ | M3 prices | Geometry, Kinematics |
| 5 | central_tendency_deviation | ✓ | M2 nodes + M3 prices | Geometry |
| 6 | structural_absence_duration | ✓ | M2 nodes | Absence |
| 7 | traversal_void_span | ✓ | M2 nodes | - |
| 8 | event_non_occurrence_counter | ✓ | M2 nodes | - |
| 9 | resting_size | ✓ | M2 order book | - |
| 10 | order_consumption | ✓ | M2 order book | - |
| 11 | absorption_event | ✓ | M2 order book + M3 prices | - |
| 12 | refill_event | ✓ | M2 order book | - |
| 13 | liquidation_density | ✓ | M2 nodes + M3 prices | - |
| 14 | directional_continuity | ✓ | M3 prices | - |
| 15 | trade_burst | ✓ | M2 nodes | - |

**Total Computed:** 15/17 (2 missing)

### 2.2 Primitives NOT Being Computed

| # | Primitive | Exists in Code? | Required By | Impact |
|---|-----------|-----------------|-------------|---------|
| 16 | **price_acceptance_ratio** | ✓ [memory/m4_price_distribution.py](memory/m4_price_distribution.py:32-89) | **Kinematics Policy** | ❌ CRITICAL - Policy cannot generate proposals |
| 17 | **structural_persistence_duration** | ✓ [constitutional-clean/memory/m4_structural_persistence.py](constitutional-clean/memory/m4_structural_persistence.py:31-36) | **Absence Policy** | ❌ CRITICAL - Policy cannot generate proposals |

**Status:** ❌ **CRITICAL GAP - 2 frozen policy dependencies missing**

---

## Part 3: Frozen Policy Requirements

### 3.1 Geometry Policy

**File:** [external_policy/ep2_strategy_geometry.py](external_policy/ep2_strategy_geometry.py:58-65)

**Required Primitives:**
- `zone_penetration` ✓ Computed
- `traversal_compactness` ✓ Computed
- `central_tendency_deviation` ✓ Computed

**Status:** ✓ All dependencies satisfied

### 3.2 Kinematics Policy

**File:** [external_policy/ep2_strategy_kinematics.py](external_policy/ep2_strategy_kinematics.py:58-65)

**Required Primitives:**
- `velocity` (price_traversal_velocity) ✓ Computed
- `compactness` (traversal_compactness) ✓ Computed
- `acceptance` (**price_acceptance_ratio**) ❌ **NOT COMPUTED**

**Status:** ❌ **BROKEN - Missing price_acceptance_ratio**

**Proposal Condition:**
```python
# Proposes only if ALL three conditions are true:
# 1. Velocity is non-zero (velocity != 0)
# 2. Compactness is non-degenerate (compactness_ratio > 0)
# 3. Acceptance is non-zero (acceptance_ratio > 0)  # ← ALWAYS None!
```

**Impact:** Kinematics policy **CANNOT** generate proposals (acceptance is always None)

### 3.3 Absence Policy

**File:** [external_policy/ep2_strategy_absence.py](external_policy/ep2_strategy_absence.py:60-67)

**Required Primitives:**
- `absence` (structural_absence_duration) ✓ Computed
- `persistence` (**structural_persistence_duration**) ❌ **NOT COMPUTED**
- `geometry` (zone_penetration) ✓ Computed (optional)

**Status:** ❌ **BROKEN - Missing structural_persistence_duration**

**Proposal Condition:**
```python
# Proposes only if ALL required conditions are true:
# 1. Absence exists (absence_duration > 0)
# 2. Persistence exists (total_persistence_duration > 0)  # ← ALWAYS None!
# 3. Absence is not total (absence_ratio < 1.0)
```

**Impact:** Absence policy **CANNOT** generate proposals (persistence is always None)

---

## Part 4: Overnight Trace Reconciliation

### 4.1 Trace Claims vs Reality

**Trace shows:**
- EP2-KINEMATICS-V1: 5 ENTRY mandates
- EP2-ABSENCE-V1: 8 EXIT mandates
- EP2-GEOMETRY-V1: 7 mandates

**But our audit shows:**
- Kinematics policy requires `acceptance` which is NOT computed
- Absence policy requires `persistence` which is NOT computed

**Conclusion:** ⚠️ **Trace is from constitutional-clean/ directory**, not current working system!

Let me verify:
```json
{
  "trace_version": "1.0",
  "constitutional_notice": "This trace contains factual records only...",
```

File location: `d:\liquidation-trading\constitutional-clean\trace_overnight.json`

**The overnight trace is from a DIFFERENT system version (constitutional-clean/).**

---

## Part 5: Data Interpretation Completeness

### 5.1 Trade Data

**M1 Normalization:** [observation/internal/m1_ingestion.py](observation/internal/m1_ingestion.py)

**Fields Extracted:**
- ✓ Timestamp
- ✓ Symbol
- ✓ Price
- ✓ Quantity
- ✓ Aggressor side (BUY/SELL)

**M2 Processing:**
- ✓ Updates existing nodes (trade-to-node proximity)
- ✓ Records trade executions on nodes
- ✓ Feeds M3 price history

**M3 Temporal:**
- ✓ Windowing (1 second default)
- ✓ Price history buffer (get_recent_prices)
- ✗ **OHLC aggregation NOT implemented** ← Required for price_acceptance_ratio

**Status:** ⚠️ Trade data is ingested but **OHLC candles are NOT being created**

### 5.2 Liquidation Data

**M1 Normalization:** ✓ Complete

**Fields Extracted:**
- ✓ Timestamp
- ✓ Symbol
- ✓ Price
- ✓ Quantity
- ✓ Side (BUY/SELL)

**M2 Processing:**
- ✓ Creates new nodes
- ✓ Reinforces existing nodes
- ✓ Records liquidation events

**Status:** ✓ Fully interpreted

### 5.3 Order Book Data

**M1 Normalization:** ✓ Complete

**Fields Extracted:**
- ✓ Timestamp
- ✓ Symbol
- ✓ Best bid/ask prices
- ✓ Best bid/ask sizes

**M2 Processing:**
- ✓ Updates node order book state
- ✓ Tracks previous resting sizes
- ✓ Enables consumption/absorption/refill detection

**Status:** ✓ Fully interpreted

---

## Part 6: Missing Infrastructure

### 6.1 OHLC Candle Generation

**Required For:** price_acceptance_ratio computation

**Current State:** ❌ NOT IMPLEMENTED

**What's Missing:**
- M3 does not aggregate trades into OHLC candles
- No candle_open, candle_high, candle_low, candle_close fields
- price_acceptance_ratio cannot be computed without candles

**Implementation Location:** Should be in [observation/internal/m3_temporal.py](observation/internal/m3_temporal.py)

### 6.2 Structural Persistence Tracking

**Required For:** structural_persistence_duration computation

**Current State:** ❌ NOT IMPLEMENTED

**What's Missing:**
- M2 nodes track creation time and interactions
- M2 nodes do NOT track "presence intervals" (when node was ACTIVE vs DORMANT)
- structural_persistence_duration needs presence_intervals tuples

**Implementation Location:** Should be in [memory/m2_continuity_store.py](memory/m2_continuity_store.py)

---

## Part 7: Calibration & Adjustment Requirements

### 7.1 Constitutional Guidance

**From CLAUDE.md Section 0:**
> "This system is constitution-driven. My task is to faithfully realize frozen design, not to interpret intent, improve ergonomics, or add convenience."

**From CODE_FREEZE.md:**
> "To modify frozen code, I must provide:
> 1. Logged evidence from Phase V1-LIVE runs
> 2. Specific timestamp of failure
> 3. Primitive outputs showing structural ambiguity
> 4. Proposed change with justification"

### 7.2 What Was Originally Planned

**User's question:** "what about adjustments, we were supposed to gather data and adjust accordingly"

**Historical Context:** The system was designed to:
1. Run in observation mode
2. Collect real market data
3. Verify primitives compute correctly
4. Identify structural ambiguities
5. Make evidence-based adjustments

### 7.3 Current Situation

**What We Have:**
- ✓ All data sources operational
- ✓ M1-M2-M3 pipeline working
- ✓ 15/17 primitives computing
- ✓ Frozen policies integrated
- ❌ 2 primitives missing from computation pipeline
- ❌ OHLC infrastructure not implemented
- ❌ Persistence interval tracking not implemented

**What We Need:**
1. **Implement price_acceptance_ratio computation**
   - Add OHLC candle aggregation to M3
   - Import compute_price_acceptance_ratio in governance.py
   - Add to M4PrimitiveBundle

2. **Implement structural_persistence_duration computation**
   - Add presence interval tracking to M2 nodes
   - Import compute_structural_persistence_duration in governance.py
   - Add to M4PrimitiveBundle

3. **No calibration can occur** until missing primitives are implemented

---

## Part 8: Recommendations

### 8.1 Immediate Actions Required

**Priority 1: Fix Broken Policy Dependencies**

1. Add `price_acceptance_ratio` to M4PrimitiveBundle
2. Add `structural_persistence_duration` to M4PrimitiveBundle
3. Implement OHLC candle generation in M3
4. Implement presence interval tracking in M2
5. Add computation logic to governance.py
6. Update PolicyAdapter to pass new primitives

**Priority 2: Verify Real System State**

1. Run comprehensive test with ALL primitives
2. Verify frozen policies can now generate proposals
3. Export new execution trace from CURRENT system (not constitutional-clean/)

**Priority 3: Evidence Collection**

1. Run 24-hour observation period
2. Log primitive coverage per symbol
3. Identify if any primitives remain None in real market conditions
4. Document structural patterns that emerge

### 8.2 Constitutional Compliance

**Current Status:** ❌ **NON-COMPLIANT**

**Violation:**
- Frozen external policies expect primitives that system doesn't provide
- PolicyAdapter passes None for required parameters
- Policies return None (no proposals) due to missing data
- This creates false confidence that system is working

**To Restore Compliance:**
- Implement ALL primitives that frozen policies require
- Ensure no required primitive is ever None unless structurally absent
- Verify policies can evaluate conditions as designed

---

## Part 9: Summary

**Data Sources:** ✓ 3/3 operational (trades, liquidations, order book)

**Data Interpretation:** ⚠️ Partial
- Trades: ingested but OHLC not aggregated
- Liquidations: fully interpreted
- Order book: fully interpreted

**Primitives:** ❌ 15/17 computed (2 critical missing)
- Missing: price_acceptance_ratio, structural_persistence_duration
- Impact: 2 frozen policies cannot generate proposals

**Policy Dependencies:** ❌ 2/3 policies broken
- Geometry: ✓ Working
- Kinematics: ❌ Broken (missing acceptance)
- Absence: ❌ Broken (missing persistence)

**Next Step:** Implement missing primitives to restore frozen policy functionality.

---

**CONSTITUTIONAL NOTICE:** This audit contains factual findings only. System is NOT ready for live trading until all frozen policy dependencies are satisfied.
