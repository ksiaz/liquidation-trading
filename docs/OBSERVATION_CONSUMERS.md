# OBSERVATION CONSUMERS

**Date:** 2026-02-01
**Purpose:** List every component that reads from M1/M2/M3
**Type:** Consumer Inventory

---

## M1 BUFFER CONSUMERS

### raw_trades Buffer

| Consumer | File | Method | Event Type | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| M3 Temporal Engine | governance.py:300-307 | `process_trade()` | TRADE | YES (when collector runs) | Trade pressure, windows |
| M2 Node Association | governance.py:462-491 | `_associate_trade_with_nodes()` | TRADE | YES (when collector runs) | M2 node updates |
| Side Validation | m1_ingestion.py:107-160 | `_validate_trade_side()` | TRADE | YES (when depth exists) | Validation counters |

**Status:** Works when Binance collector is running.

---

### raw_liquidations Buffer

| Consumer | File | Method | Event Type | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| M2 Node Creation | governance.py:415-460 | `_create_or_update_node_from_liquidation()` | LIQUIDATION | ✅ YES | M2 nodes |
| Cascade Tracking | governance.py:162-195 | `record_hl_liquidation()` | LIQUIDATION | ✅ YES | Cascade timestamps |
| Liquidation Density | m4_liquidation_clustering.py | `compute_liquidation_density()` | LIQUIDATION | DORMANT | LiquidationDensity |

**Status:** Liquidation → M2 path works. Cascade tracking works. Density primitive is dormant.

---

### raw_depth Buffer

| Consumer | File | Method | Event Type | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| M2 Orderbook State | governance.py:324-332 | `_m2_store.update_orderbook_state()` | DEPTH | YES (when collector runs) | Orderbook state |
| Side Validation | m1_ingestion.py:130-142 | Cross-reference | DEPTH | YES | Trade side validation |
| Absorption Detection | m4_absorption_confirmation.py | `detect_absorption_event()` | DEPTH | GATED (no history) | None |

**Status:** Works when Binance collector runs. Absorption detection gated by missing depth history.

---

### hl_prices Buffer (CRITICAL)

| Consumer | File | Method | Event Type | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| **NONE** | — | — | HL_PRICE | — | — |

**Status:** **NO CONSUMERS.** Data is stored but never read.

Methods exist but are never called:
- `get_hl_oracle_price(symbol)` — 0 callers
- `get_all_hl_prices()` — 0 callers

---

### hl_positions Buffer

| Consumer | File | Method | Event Type | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| **NONE** | — | — | HL_POSITION | — | — |

**Status:** **NO DATA SOURCE.** HyperliquidCollector not producing data.

---

### hl_liquidations Buffer

| Consumer | File | Method | Event Type | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| Cascade State | governance.py:162-195 | `record_hl_liquidation()` | HL_LIQUIDATION | YES | Cascade tracking |

**Status:** HL_LIQUIDATION events are recorded for cascade state. But cascade primitives require HyperliquidCollector data which is missing.

---

## M2 CONSUMERS

### ContinuityMemoryStore

| Consumer | File | Method | Reads What | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| Zone Geometry | m4_zone_geometry.py | `compute_zone_penetration_depth()` | M2 nodes | YES | ZonePenetrationDepth |
| Structural Persistence | m4_structural_persistence.py | `compute_structural_persistence_duration()` | M2 nodes | YES | Duration |
| PolicyAdapter | policy_adapter.py | via snapshot | M2 summary | YES | Mandates |
| Geometry Strategy | ep2_strategy_geometry.py | `generate_geometry_proposal()` | Zone context | YES | Proposals |

**Status:** M2 is the most actively consumed layer. All zone-based strategies depend on it.

---

## M3 CONSUMERS

### M3TemporalEngine

| Consumer | File | Method | Reads What | Alive? | Produces Output? |
|----------|------|--------|------------|--------|------------------|
| Trade Pressure | m3_temporal.py | `get_recent_pressure()` | Trade windows | YES | Pressure metrics |
| Kinematics Strategy | ep2_strategy_kinematics.py | `generate_kinematics_proposal()` | Pressure | DORMANT | Proposals |
| EFFCS Strategy | ep2_effcs_strategy.py | `generate_effcs_proposal()` | Pressure | DORMANT | Proposals |

**Status:** M3 works when trades flow. Kinematics and EFFCS strategies are dormant (wrong regime).

---

## M4 PRIMITIVE CONSUMERS

### Snapshot Bundle

| Consumer | File | Reads Which Primitives | Alive? | Produces Output? |
|----------|------|------------------------|--------|------------------|
| Geometry Strategy | ep2_strategy_geometry.py | zone_penetration_depth | YES | Mandates |
| SLBRS Strategy | ep2_slbrs_strategy.py | regime_state | DORMANT | — |
| EFFCS Strategy | ep2_effcs_strategy.py | regime_state | DORMANT | — |
| Cascade Sniper | ep2_strategy_cascade_sniper.py | proximity_data | DEAD | — |

**Status:**
- Geometry strategy is the ONLY active mandate producer
- Regime-based strategies need specific regime states (never triggered)
- Cascade sniper needs proximity data (never populated)

---

## CASCADE PRIMITIVE CONSUMERS

### LiquidationCascadeProximity

| Consumer | File | Reads What | Alive? | Produces Output? |
|----------|------|------------|--------|------------------|
| Cascade Sniper | ep2_strategy_cascade_sniper.py | Proximity values | DEAD | — |
| Cascade State | m4_cascade_state.py | Proximity for phase | DEAD | — |

**Why Dead:** Requires HyperliquidCollector producing position data. Collector not running.

---

### CascadeStateObservation

| Consumer | File | Reads What | Alive? | Produces Output? |
|----------|------|------------|--------|------------------|
| Cascade Sniper | ep2_strategy_cascade_sniper.py | Cascade phase | DEAD | — |

**Why Dead:** Depends on LiquidationCascadeProximity which is dead.

---

## STRATEGY CONSUMERS (FINAL OUTPUT)

| Strategy | File | Reads From | Alive? | Mandates Generated |
|----------|------|------------|--------|-------------------|
| Geometry | ep2_strategy_geometry.py | M2 nodes, M4 zone primitives | ✅ YES | 99.7% of all mandates |
| Kinematics | ep2_strategy_kinematics.py | M3 pressure, M4 velocity | DISABLED | 0 |
| Absence | ep2_strategy_absence.py | M4 absence primitives | DISABLED | 0 |
| Orderbook Test | ep2_strategy_orderbook_test.py | M4 orderbook primitives | DISABLED | 0 |
| SLBRS | ep2_slbrs_strategy.py | Regime state | ENABLED but dormant | 0 |
| EFFCS | ep2_effcs_strategy.py | Regime state | ENABLED but dormant | 0 |
| Cascade Sniper | ep2_strategy_cascade_sniper.py | Proximity, cascade state | ENABLED but dead | 0 |

**Finding:** Only Geometry strategy produces mandates. All others are dormant or dead.

---

## SUMMARY: WHO IS LISTENING?

### For HL_PRICE Events

**NOBODY.** Events are stored in:
- `M1.hl_prices[symbol]` buffer (100 events max)
- `M1.latest_hl_prices[symbol]` cache (latest only)

But no code reads these values. The accessor methods exist but have zero callers.

### For LIQUIDATION Events

1. **M2 Node Creation** — Creates/updates zone nodes (ACTIVE)
2. **Cascade Timestamp Tracking** — Records for cascade state (ACTIVE but cascade primitives dead)

### For TRADE Events

1. **M3 Temporal Engine** — Pressure calculation (ACTIVE when collector runs)
2. **M2 Node Association** — Associates trades with zones (ACTIVE when collector runs)
3. **Side Validation** — Cross-references with depth (ACTIVE when depth exists)

### For DEPTH Events

1. **M2 Orderbook State** — Updates orderbook snapshot (ACTIVE when collector runs)
2. **Side Validation** — Provides bid/ask for trade validation (ACTIVE)

---

## THE CRITICAL QUESTION

> "If a liquidation happens now, what code reacts?"

**Answer:**

1. ✅ gRPC Server receives it from node_fills
2. ✅ NodeSubscriber receives it via StreamLiquidations
3. ✅ NodeBridge normalizes to LIQUIDATION event
4. ✅ ingest_observation() dispatches to M1
5. ✅ M1.normalize_liquidation() stores in raw_liquidations
6. ✅ governance._create_or_update_node_from_liquidation() creates M2 node
7. ✅ governance.record_hl_liquidation() records timestamp for cascade tracking
8. ❌ **BUT:** Cascade primitives cannot compute (no position data)
9. ❌ **AND:** Cascade Sniper strategy cannot generate mandates (no proximity data)
10. ❌ **SO:** No trading action occurs

**Net Effect:** Liquidation creates an M2 node but no mandate is generated from it.

---

> "If a price event happens now, what code reacts?"

**Answer:**

1. ✅ gRPC Server receives it from replica_cmds
2. ✅ NodeSubscriber receives it via StreamPrices
3. ✅ NodeBridge normalizes to HL_PRICE event
4. ✅ ingest_observation() dispatches to M1
5. ✅ M1.normalize_hl_price() stores in buffers
6. ❌ **END.** No consumer reads the stored data.

**Net Effect:** Price is stored but completely ignored.

---

*This inventory documents what actually consumes observation data.*

*Generated: 2026-02-01*
