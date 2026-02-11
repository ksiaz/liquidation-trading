# EP-2 External Policy Contracts

**Version:** 1.0.0
**Status:** FROZEN (test-only interaction)
**Generated:** 2026-02-01

---

## Overview

This document defines the contracts for all 7 EP-2 external policies. These policies are **frozen** and must not be modified. Only testing and documentation updates are permitted per DOWNSTREAM_ACTIVATION_SPEC.md.

### Contract Invariants (Apply to ALL policies)

1. **Determinism**: Same inputs + same state → identical output
2. **Input Immutability**: Policies must not mutate input primitives
3. **Output Immutability**: All `StrategyProposal` outputs are frozen dataclasses
4. **M6 Gate**: Permission DENIED → always returns None
5. **Null Safety**: None inputs → no crash, returns None or valid proposal

---

## Policy Catalog

| ID | Policy | State | Regime Gate | Primitives |
|----|--------|-------|-------------|------------|
| 1 | Geometry | Stateless | None | ZonePenetration, TraversalCompactness, CentralTendencyDeviation |
| 2 | Kinematics | Stateless | None | PriceTraversalVelocity, TraversalCompactness, PriceAcceptanceRatio |
| 3 | Absence | Stateless | None | StructuralAbsenceDuration, StructuralPersistenceDuration, ZonePenetration* |
| 4 | Orderbook Test | Stateless | None | RestingSize, OrderConsumption, RefillEvent |
| 5 | SLBRS | **Stateful** | SIDEWAYS | ZonePenetration, RestingSize, OrderConsumption, StructuralPersistence |
| 6 | EFFCS | **Stateful** | EXPANSION | PriceVelocity, DisplacementOrigin, RegimeState |
| 7 | Cascade Sniper | **Stateful** | None | ProximityData, LiquidationBurst |

*Optional primitive

---

## Policy #1: Geometry-Driven Structural Proposal

**Module:** `ep2_strategy_geometry.py`
**Function:** `generate_geometry_proposal()`
**State:** Stateless

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| zone_penetration | `ZonePenetrationDepth` | Yes | A6 primitive - zone penetration depth |
| traversal_compactness | `TraversalCompactness` | Yes | A4 primitive - path efficiency ratio |
| central_tendency_deviation | `CentralTendencyDeviation` | Yes | A8 primitive - deviation from central tendency |
| context | `StrategyContext` | Yes | Execution context with timestamp |
| permission | `PermissionOutput` | Yes | M6 permission gate |

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| Any primitive None | `None` |
| penetration_depth == 0 | `None` |
| compactness_ratio == 0 | `None` |
| deviation_value == 0 | `None` |
| All conditions met | `StrategyProposal(strategy_id="EP2-GEOMETRY-V1", action_type="STRUCTURAL_GEOMETRY_EVENT", ...)` |

### Proposal Fields

```python
StrategyProposal(
    strategy_id="EP2-GEOMETRY-V1",
    action_type="STRUCTURAL_GEOMETRY_EVENT",
    confidence="STRUCTURAL_PRESENT",
    justification_ref="A6|A4|A8",
    timestamp=context.timestamp
)
```

---

## Policy #2: Kinematics-Driven Structural Proposal

**Module:** `ep2_strategy_kinematics.py`
**Function:** `generate_kinematics_proposal()`
**State:** Stateless

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| velocity | `PriceTraversalVelocity` | Yes | A3 primitive - price change rate |
| compactness | `TraversalCompactness` | Yes | A4 primitive - path efficiency |
| acceptance | `PriceAcceptanceRatio` | Yes | A5 primitive - price acceptance |
| context | `StrategyContext` | Yes | Execution context |
| permission | `PermissionOutput` | Yes | M6 permission gate |

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| Any primitive None | `None` |
| velocity == 0 | `None` |
| compactness_ratio == 0 | `None` |
| acceptance_ratio == 0 | `None` |
| All conditions met | `StrategyProposal(strategy_id="EP2-KINEMATICS-V1", ...)` |

### Proposal Fields

```python
StrategyProposal(
    strategy_id="EP2-KINEMATICS-V1",
    action_type="STRUCTURAL_KINEMATIC_EVENT",
    confidence="STRUCTURAL_PRESENT",
    justification_ref="A3|A4|A5",
    timestamp=context.timestamp
)
```

---

## Policy #3: Absence-Driven Structural Proposal

**Module:** `ep2_strategy_absence.py`
**Function:** `generate_absence_proposal()`
**State:** Stateless

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| absence | `StructuralAbsenceDuration` | Yes | B1.1 primitive - absence duration |
| persistence | `StructuralPersistenceDuration` | Yes | B2.1 primitive - persistence duration |
| geometry | `ZonePenetrationDepth` | No | A6 primitive (optional enrichment) |
| context | `StrategyContext` | Yes | Execution context |
| permission | `PermissionOutput` | Yes | M6 permission gate |

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| absence None | `None` |
| persistence None | `None` |
| absence_duration == 0 | `None` |
| persistence_duration == 0 | `None` |
| absence_ratio == 1.0 | `None` |
| All conditions met (no geometry) | `StrategyProposal(justification_ref="B1.1|B2.1", ...)` |
| All conditions met (with geometry) | `StrategyProposal(justification_ref="B1.1|B2.1|A6", ...)` |

### Proposal Fields

```python
StrategyProposal(
    strategy_id="EP2-ABSENCE-V1",
    action_type="STRUCTURAL_ABSENCE_EVENT",
    confidence="STRUCTURAL_PRESENT",
    justification_ref="B1.1|B2.1" or "B1.1|B2.1|A6",
    timestamp=context.timestamp
)
```

---

## Policy #4: Order Book Primitive Test

**Module:** `ep2_strategy_orderbook_test.py`
**Function:** `generate_orderbook_test_proposal()`
**State:** Stateless

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| resting_size | `RestingSize` | No | Order book resting size |
| order_consumption | `OrderConsumption` | No* | Order consumption event |
| refill_event | `RefillEvent` | No* | Order refill event |
| context | `StrategyContext` | Yes | Execution context |
| permission | `PermissionOutput` | Yes | M6 permission gate |
| position_state | `PositionState` | No | Current position state |

*Required for entry/exit respectively

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| No position + order_consumption exists | `StrategyProposal(action_type="ENTRY", ...)` |
| Position open + refill_event exists | `StrategyProposal(action_type="EXIT", ...)` |
| Otherwise | `None` |

### Proposal Fields

```python
# Entry
StrategyProposal(
    strategy_id="orderbook_test",
    action_type="ENTRY",
    confidence="TEST",
    timestamp=context.timestamp
)

# Exit
StrategyProposal(
    strategy_id="orderbook_test",
    action_type="EXIT",
    confidence="TEST",
    timestamp=context.timestamp
)
```

---

## Policy #5: SLBRS (Sideways Liquidity Block Reaction System)

**Module:** `ep2_slbrs_strategy.py`
**Function:** `generate_slbrs_proposal()`
**State:** **STATEFUL** - requires reset between test runs

### State Management

```python
from external_policy.ep2_slbrs_strategy import _slbrs_strategy

# Reset state before tests:
_slbrs_strategy._state.clear()
_slbrs_strategy._first_test.clear()

# Reset single symbol:
_slbrs_strategy.reset_state("BTCUSDT")
```

### State Machine

```
IDLE → BLOCK_FORMING → FIRST_TEST → REACTION → (success: IDLE, fail: IDLE)
```

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| symbol | `str` | Yes | Trading symbol |
| regime_state | `RegimeState` | Yes | Must be SIDEWAYS_ACTIVE |
| zone_penetration | `ZonePenetration` | Yes | Zone penetration data |
| resting_size | `RestingSize` | Yes | Resting order size |
| order_consumption | `OrderConsumption` | Yes | Order consumption data |
| structural_persistence | `StructuralPersistence` | Yes | Block persistence (>30s) |
| price | `float` | Yes | Current price |
| context | `StrategyContext` | Yes | Execution context |
| permission | `PermissionOutput` | Yes | M6 permission gate |
| position_state | `PositionState` | No | Current position state |

### Regime Gate

- **Allowed:** `SIDEWAYS_ACTIVE`
- **Blocked:** Any other regime, None

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| Regime not SIDEWAYS_ACTIVE | `None` |
| Required primitive None | `None` |
| persistence < 30s | `None` |
| State machine triggers entry | `StrategyProposal(action_type="ENTRY", ...)` |
| Position open + invalidation | `StrategyProposal(action_type="EXIT", ...)` |

---

## Policy #6: EFFCS (Expansion & Forced Flow Continuation System)

**Module:** `ep2_effcs_strategy.py`
**Function:** `generate_effcs_proposal()`
**State:** **STATEFUL** - requires reset between test runs

### State Management

```python
from external_policy.ep2_effcs_strategy import _effcs_strategy

# Reset state before tests:
_effcs_strategy._state.clear()
_effcs_strategy._impulse.clear()
_effcs_strategy._pullback.clear()

# Reset single symbol:
_effcs_strategy.reset_state("BTCUSDT")
```

### State Machine

```
IDLE → IMPULSE_DETECTED → PULLBACK_ZONE → ENTRY_TRIGGERED → (complete: IDLE)
```

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| symbol | `str` | Yes | Trading symbol |
| regime_state | `RegimeState` | Yes | Must be EXPANSION_ACTIVE |
| price_velocity | `PriceVelocity` | Yes | Price velocity data |
| displacement | `DisplacementOrigin` | No | Displacement anchor |
| liquidation_zscore | `float` | Yes | Liquidation z-score (>2.5 for impulse) |
| price | `float` | Yes | Current price |
| price_high | `float` | Yes | Recent high |
| price_low | `float` | Yes | Recent low |
| context | `StrategyContext` | Yes | Execution context |
| permission | `PermissionOutput` | Yes | M6 permission gate |
| position_state | `PositionState` | No | Current position state |

### Regime Gate

- **Allowed:** `EXPANSION_ACTIVE`
- **Blocked:** Any other regime, None

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| Regime not EXPANSION_ACTIVE | `None` |
| price_velocity None | `None` |
| liquidation_zscore < 2.5 | `None` (no impulse) |
| State machine triggers entry | `StrategyProposal(action_type="ENTRY", ...)` |
| Position open + exit condition | `StrategyProposal(action_type="EXIT", ...)` |

---

## Policy #7: Cascade Sniper (Liquidation Proximity)

**Module:** `ep2_strategy_cascade_sniper.py`
**Function:** `generate_cascade_sniper_proposal()`
**State:** **STATEFUL** - requires reset between test runs

### State Management

```python
from external_policy.ep2_strategy_cascade_sniper import reset_state, _get_state_machine

# Reset all state:
reset_state()

# Access state machine:
sm = _get_state_machine()
state = sm.get_state("BTCUSDT")  # Returns CascadeState enum
```

### State Machine

```
NONE → PRIMED → TRIGGERED → ABSORBING → EXHAUSTED → NONE
```

| State | Description |
|-------|-------------|
| NONE | No cascade detected |
| PRIMED | Liquidation cluster detected, watching |
| TRIGGERED | Liquidation burst confirmed cascade |
| ABSORBING | Monitoring for absorption (organic counter-flow) |
| EXHAUSTED | Cascade energy exhausted |

### Input Contract

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| proximity | `ProximityData` | Yes | Liquidation proximity data |
| liquidations | `LiquidationBurst` | No | Recent liquidation burst |
| context | `StrategyContext` | Yes | Execution context |
| permission | `PermissionOutput` | Yes | M6 permission gate |
| position_state | `PositionState` | No | Current position state |
| entry_mode | `EntryMode` | No | ABSORPTION_REVERSAL or CASCADE_MOMENTUM |

### Output Contract

| Condition | Output |
|-----------|--------|
| Permission DENIED | `None` |
| proximity None | `None` |
| Position already open | `None` (entry-only strategy) |
| Cluster below thresholds | `None` |
| State machine triggers entry | `StrategyProposal(action_type="ENTRY", ...)` |

### Configuration

```python
CascadeSniperConfig(
    min_cluster_positions=2,      # Minimum positions for cluster
    min_cluster_value=100000.0,   # Minimum USD value for cluster
    dominance_ratio=0.65          # Side dominance threshold
)
```

---

## Test Requirements

### All Policies (A3-A6)

1. **Determinism Test** (A3): After state reset, identical inputs produce identical output
2. **None-Handling Test** (A4): None inputs don't crash, return None or valid proposal
3. **Input Immutability Test** (A5): Policy doesn't mutate input primitives
4. **Side Effect Isolation Test** (A6): State changes for one symbol don't affect another

### Stateful Policies (Additional)

5. **State Reset Test**: Verify `reset_state()` clears all state
6. **State Machine Test**: Verify state transitions follow documented flow
7. **Symbol Isolation Test**: Different symbols have independent state

### Test File Locations

| Policy | Test File |
|--------|-----------|
| Geometry | `test_ep2_strategy_geometry.py` |
| Kinematics | `test_ep2_strategy_kinematics.py` |
| Absence | `test_ep2_strategy_absence.py` |
| Orderbook Test | `test_ep2_strategy_orderbook_test.py` |
| SLBRS | `test_ep2_slbrs_strategy.py` |
| EFFCS | `test_ep2_effcs_strategy.py` |
| Cascade Sniper | `test_ep2_strategy_cascade_sniper.py` |

---

## Appendix: Test Fixture Factories

Located in `external_policy/test_fixtures/`:

```python
# Primitive factories
from external_policy.test_fixtures import (
    create_zone_penetration,
    create_structural_persistence,
    create_resting_size,
    create_order_consumption,
    create_refill_event,
    create_price_velocity,
    create_displacement_origin,
    create_cascade_proximity,
    create_cascade_state,
    create_strategy_context,
    create_permission_allowed,
    create_permission_denied,
    create_regime_state_expansion,
    create_regime_state_sideways,
)

# M4 Bundle factories
from external_policy.test_fixtures import (
    create_empty_bundle,
    create_minimal_bundle,
    create_full_bundle,
)
```
