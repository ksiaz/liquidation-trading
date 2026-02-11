# UNVERIFIED COMPONENTS

**Date:** 2026-02-01
**Purpose:** List components that have never been exercised with live data
**Type:** Integration Risk Inventory (Not Bugs)

---

## CATEGORY 1: DEAD COMPONENTS

Components that CANNOT work with current setup. Code exists but prerequisites are missing.

### 1.1 LiquidationCascadeProximity Primitive

| Attribute | Value |
|-----------|-------|
| **Location** | `memory/m4_cascade_proximity.py` |
| **Purpose** | Track positions at risk of liquidation |
| **Prerequisite** | HyperliquidCollector producing proximity data |
| **Current State** | Always returns None |
| **Evidence** | `hl_liquidation_proximity` table: 0 rows |
| **Diagnostic** | `ReasonCode.M4_PROXIMITY_DATA_MISSING` fires every cycle |

### 1.2 CascadeStateObservation Primitive

| Attribute | Value |
|-----------|-------|
| **Location** | `memory/m4_cascade_state.py` |
| **Purpose** | Detect cascade phases (PROXIMITY, LIQUIDATING, CASCADING, EXHAUSTED) |
| **Prerequisite** | Proximity data + liquidation timestamps |
| **Current State** | Always returns None |
| **Evidence** | `hl_cascade_events` table: 0 rows |
| **Diagnostic** | Computation block gated by `if hl_proximity:` |

### 1.3 LeverageConcentrationRatio Primitive

| Attribute | Value |
|-----------|-------|
| **Location** | `memory/m4_leverage_concentration.py` |
| **Purpose** | Measure leverage distribution across positions |
| **Prerequisite** | Position data from HL tracker |
| **Current State** | Always returns None |
| **Evidence** | `hl_positions` table: 0 rows |
| **Diagnostic** | `ReasonCode.M4_TRACKER_MISSING` fires every cycle |

### 1.4 OpenInterestDirectionalBias Primitive

| Attribute | Value |
|-----------|-------|
| **Location** | `memory/m4_open_interest_bias.py` |
| **Purpose** | Measure long/short position imbalance |
| **Prerequisite** | Position data from HL tracker |
| **Current State** | Always returns None |
| **Evidence** | `hl_positions` table: 0 rows |
| **Diagnostic** | `ReasonCode.M4_NO_POSITIONS` fires every cycle |

### 1.5 Cascade Sniper Strategy

| Attribute | Value |
|-----------|-------|
| **Location** | `external_policy/ep2_strategy_cascade_sniper.py` |
| **Purpose** | Trade cascade exhaustion events |
| **Prerequisite** | ProximityData + LiquidationBurst + AbsorptionAnalysis |
| **Current State** | Never generates proposals |
| **Evidence** | 0 mandates with strategy_id containing "cascade" |
| **Diagnostic** | `ReasonCode.PA_CASCADE_DATA_MISSING` fires every cycle |

### 1.6 PositionStateManager

| Attribute | Value |
|-----------|-------|
| **Location** | Referenced in `runtime/monitoring/resource_monitor.py` |
| **Purpose** | Parse `abci_state.rmp` for position snapshots |
| **Prerequisite** | Class definition (doesn't exist) |
| **Current State** | Cannot be instantiated |
| **Evidence** | Class never defined in codebase |
| **Diagnostic** | N/A (compile-time would fail if called) |

### 1.7 PositionReconciler

| Attribute | Value |
|-----------|-------|
| **Location** | `runtime/exchange/position_reconciler.py` |
| **Purpose** | Verify ghost positions match exchange |
| **Prerequisite** | Being instantiated and called |
| **Current State** | Code exists, never imported |
| **Evidence** | No imports found in codebase |
| **Diagnostic** | N/A (never runs) |

---

## CATEGORY 2: DORMANT COMPONENTS

Components that COULD work if external conditions change. Infrastructure exists but conditions not met.

### 2.1 SLBRS Strategy (Sideways Regime)

| Attribute | Value |
|-----------|-------|
| **Location** | `external_policy/ep2_slbrs_strategy.py` |
| **Purpose** | Trade in sideways/ranging markets |
| **Prerequisite** | Regime state = SIDEWAYS_ACTIVE |
| **Current State** | Enabled but never triggers |
| **Evidence** | Regime almost never classifies as SIDEWAYS_ACTIVE |
| **Diagnostic** | `ReasonCode.PA_REGIME_STATE_MISSING` when regime unavailable |

**Regime Conditions Required:**
- VWAP distance ≤ 1.25 × ATR_5m
- Volatility compressed (ATR_5m / ATR_30m < 0.80)
- Orderflow balanced (imbalance < 0.18)
- Liquidations subdued (zscore < 2.0)

### 2.2 EFFCS Strategy (Expansion Regime)

| Attribute | Value |
|-----------|-------|
| **Location** | `external_policy/ep2_effcs_strategy.py` |
| **Purpose** | Trade in expansion/trending markets |
| **Prerequisite** | Regime state = EXPANSION_ACTIVE |
| **Current State** | Enabled but never triggers |
| **Evidence** | Regime almost never classifies as EXPANSION_ACTIVE |
| **Diagnostic** | `ReasonCode.PA_REGIME_STATE_MISSING` when regime unavailable |

**Regime Conditions Required:**
- VWAP distance ≥ 1.5 × ATR_5m
- Volatility expanding (ATR_5m ≥ 1.0 × ATR_30m)
- Orderflow dominant (imbalance ≥ 0.35)
- Liquidations elevated (zscore ≥ 2.5)

### 2.3 HyperliquidCollector

| Attribute | Value |
|-----------|-------|
| **Location** | `runtime/hyperliquid/collector.py` |
| **Purpose** | Track HL positions and proximity |
| **Prerequisite** | Stable WebSocket connection |
| **Current State** | Code exists, connection fails |
| **Evidence** | Logs show "keepalive ping timeout" errors |
| **Diagnostic** | N/A (external failure) |

### 2.4 Node Bridge (gRPC Mode)

| Attribute | Value |
|-----------|-------|
| **Location** | `runtime/node_client/bridge.py` |
| **Purpose** | Receive HL node events via gRPC |
| **Prerequisite** | gRPC server running on :50051 |
| **Current State** | Code complete, server not running |
| **Evidence** | Port 50051 not listening |
| **Diagnostic** | Connection refused if started |

---

## CATEGORY 3: GATED PERMANENTLY

Components that are gated by conditions that are NEVER true in current configuration.

### 3.1 Absorption Analysis

| Attribute | Value |
|-----------|-------|
| **Location** | `memory/m4_absorption_confirmation.py` |
| **Purpose** | Detect orderbook absorption events |
| **Prerequisite** | Historical depth data |
| **Current State** | Never computed |
| **Evidence** | `orderbook_depth` table: 0 rows |
| **Gate** | `if current_depth and previous_depth:` |

### 3.2 Refill Event Detection

| Attribute | Value |
|-----------|-------|
| **Location** | `memory/m4_orderbook_primitives.py:detect_refill_event` |
| **Purpose** | Detect order refills after consumption |
| **Prerequisite** | Sequential depth snapshots |
| **Current State** | Never computed |
| **Evidence** | Depth data not persisted |
| **Gate** | Requires depth history that doesn't exist |

---

## CATEGORY 4: NEVER EMITTED DIAGNOSTICS

Components instrumented but diagnostics never observed in logs.

### 4.1 Grace Period Blocking

| Attribute | Value |
|-----------|-------|
| **Location** | `runtime/policy_adapter.py:512-527` |
| **Diagnostic** | `ReasonCode.PA_GRACE_PERIOD_BLOCKED` |
| **Purpose** | Prevent immediate EXIT after ENTRY |
| **Current State** | Exists but 34 EXITs = minimal blocking |
| **Evidence** | Only 34 EXIT mandates ever generated |

### 4.2 Risk Validation Failure

| Attribute | Value |
|-----------|-------|
| **Location** | `runtime/executor/controller.py:165-177` |
| **Diagnostic** | Logged to `_execution_log` |
| **Purpose** | Block entries violating risk constraints |
| **Current State** | Unknown if ever triggered |
| **Evidence** | Ghost execution only, no real risk constraints |

### 4.3 Single Position Invariant

| Attribute | Value |
|-----------|-------|
| **Location** | `runtime/m6_executor.py:295-310` |
| **Diagnostic** | `ReasonCode.M6_SINGLE_POSITION_VIOLATED` |
| **Purpose** | Block new entries when position exists |
| **Current State** | Logic exists, never observed |
| **Evidence** | Single symbol trading, constraint rarely hit |

---

## SUMMARY TABLE

| Component | Category | Can It Ever Work? |
|-----------|----------|-------------------|
| LiquidationCascadeProximity | DEAD | NO - requires HL collector data |
| CascadeStateObservation | DEAD | NO - requires proximity data |
| LeverageConcentrationRatio | DEAD | NO - requires position data |
| OpenInterestDirectionalBias | DEAD | NO - requires position data |
| Cascade Sniper Strategy | DEAD | NO - requires proximity data |
| PositionStateManager | DEAD | NO - class doesn't exist |
| PositionReconciler | DEAD | NO - never imported |
| SLBRS Strategy | DORMANT | YES - if regime enters SIDEWAYS |
| EFFCS Strategy | DORMANT | YES - if regime enters EXPANSION |
| HyperliquidCollector | DORMANT | YES - if WebSocket stabilizes |
| Node Bridge | DORMANT | YES - if gRPC server started |
| Absorption Analysis | GATED | NO - depth history not stored |
| Refill Event Detection | GATED | NO - depth history not stored |

---

## CONSEQUENCE ANALYSIS

### What the System CANNOT Do

1. **Detect liquidation cascades** — All cascade primitives are None
2. **Track position proximity** — No position data flows
3. **Execute cascade sniper trades** — Strategy prerequisites unmet
4. **Adapt to regime changes** — SLBRS/EFFCS never activate
5. **Reconcile ghost vs real positions** — Reconciler never called

### What the System CAN Do

1. **Ingest Binance liquidations** — When collector runs
2. **Compute zone geometry** — M2/M4 pipeline works
3. **Generate geometry mandates** — 99.7% of all mandates
4. **Execute ghost trades** — Paper trading functional
5. **Track M2 memory nodes** — 22M+ nodes created

---

*These are integration risks, not bugs. Do not fix them yet. Understand them first.*

*Generated: 2026-02-01*
