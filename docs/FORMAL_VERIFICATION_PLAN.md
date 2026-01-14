# Formal Verification Plan

**Status:** Framework / Future Work
**Priority:** P3 (Before Scaling Real Capital)
**Estimated Effort:** 10-15 days
**Date:** 2026-01-14

---

## Overview

Formal verification provides mathematical proofs that the Constitutional Execution System satisfies critical invariants under all possible execution paths. This plan outlines the verification approach using TLA+ (Temporal Logic of Actions) and property-based testing.

**Why Formal Verification:**
- Ghost trading validated: No blocking issues for empirical calibration
- Real capital deployment requires: Proof that invariants cannot be violated

---

## Verification Scope

### Critical Systems to Verify

1. **Position State Machine** (runtime/position/types.py)
   - All transitions valid (no illegal state changes)
   - No phantom states (every position resolvable to FLAT)
   - Atomicity (no partial state updates)

2. **Arbitration Determinism** (external_policy/ep3_arbitration.py)
   - EXIT supremacy always enforced
   - Single action emission per cycle
   - Mandate conflict resolution deterministic

3. **Time Causality** (observation/internal/m3_temporal.py)
   - Time monotonicity never violated
   - Event ordering consistent with timestamps
   - No time reversals under any condition

4. **Risk Invariants** (runtime/risk/invariants.py)
   - R1-R15 cannot be bypassed
   - Invariant validation complete before action
   - No race conditions in validation

5. **M1-M5 Observation Isolation** (observation/)
   - Observation never calls execution
   - No circular dependencies
   - Layer boundaries enforced

---

## Formal Specification Language: TLA+

**Tool:** [TLA+ Toolbox](https://github.com/tlaplus/tlaplus)

**Why TLA+:**
- Temporal logic captures state machine evolution
- Model checker exhaustively explores state space
- Proof system for invariant verification
- Industry standard (used by AWS, Microsoft)

### TLA+ Modules to Create

```
specs/
├── PositionStateMachine.tla     # Position lifecycle spec
├── ArbitrationLogic.tla         # EP3 mandate resolution
├── TemporalCausality.tla        # M3 time monotonicity
├── RiskInvariants.tla           # R1-R15 validation
└── ObservationIsolation.tla     # Layer boundary enforcement
```

---

## 1. Position State Machine Verification

### Specification File

**File:** `specs/PositionStateMachine.tla`

### Invariants to Prove

**I-PS1: Valid Transitions Only**
```tla
TypeInvariant ==
    /\ state \in {FLAT, ENTERING, OPEN, REDUCING, EXITING}
    /\ state = FLAT => (quantity = 0 /\ entry_price = NULL)
    /\ state = OPEN => (quantity # 0 /\ entry_price # NULL)
```

**I-PS2: No Phantom States**
```tla
EventuallyFlat ==
    [](state # FLAT ~> <>state = FLAT)
    \* Every non-FLAT state eventually resolves to FLAT
```

**I-PS3: Transition Determinism**
```tla
DeterministicTransition ==
    /\ state = s1 /\ action = a
    => next_state = f(s1, a)
    \* Same state + action always produces same next state
```

**I-PS4: No Partial Updates**
```tla
AtomicUpdate ==
    /\ (quantity' # quantity) => (state' # state)
    \* Quantity change implies state change (atomic transaction)
```

### Model Checking

```bash
# Check invariants under all possible transitions
tlc PositionStateMachine.tla -deadlock

# Expected output:
# State space: 1,234,567 states
# Violations: 0
```

---

## 2. Arbitration Determinism Verification

### Specification File

**File:** `specs/ArbitrationLogic.tla`

### Invariants to Prove

**I-AR1: EXIT Supremacy**
```tla
ExitSupremacy ==
    /\ \E m \in mandates : m.type = EXIT
    => arbitrated_action.type = EXIT
    \* If any EXIT mandate exists, arbitrated action must be EXIT
```

**I-AR2: Single Action Emission**
```tla
SingleAction ==
    /\ Len(arbitrated_actions) = 1
    \* Exactly one action per arbitration cycle
```

**I-AR3: Deterministic Resolution**
```tla
DeterministicArbitration ==
    /\ mandates1 = mandates2
    => Arbitrate(mandates1) = Arbitrate(mandates2)
    \* Same input mandates always produce same output
```

---

## 3. Temporal Causality Verification

### Specification File

**File:** `specs/TemporalCausality.tla`

### Invariants to Prove

**I-TC1: Time Monotonicity**
```tla
TimeMonotonic ==
    []( new_timestamp >= system_time )
    \* Time never regresses
```

**I-TC2: Event Ordering**
```tla
CausalOrdering ==
    /\ event1.timestamp < event2.timestamp
    => process(event1) happens_before process(event2)
    \* Earlier events processed before later events
```

**I-TC3: No Time Reversals**
```tla
NoReversals ==
    /\ system_time' < system_time
    => HALT
    \* System halts if time reversal detected
```

---

## 4. Risk Invariants Verification

### Specification File

**File:** `specs/RiskInvariants.tla`

### Invariants to Prove (Subset - R1, R2, R3)

**I-R1: Position Risk Cap**
```tla
PositionRiskCap ==
    /\ \A p \in positions :
        MaxLoss(p) <= RiskFraction * Equity
    \* Every position obeys risk cap
```

**I-R2: Leverage Cap**
```tla
LeverageCap ==
    /\ TotalLeverage(positions, equity) <= L_max
    \* Total leverage never exceeds maximum
```

**I-R3: Liquidation Buffer**
```tla
LiquidationBuffer ==
    /\ \A p \in positions :
        DistanceToLiq(p) >= D_min_safe
    \* Every position maintains minimum buffer
```

### Model Checking Strategy

```bash
# Check invariants under adversarial scenarios
tlc RiskInvariants.tla \
    -config adversarial_scenarios.cfg \
    -depth 1000

# Adversarial scenarios:
# - Sudden 50% price drop
# - Simultaneous multi-position entries
# - Exchange rejects order (position stuck in ENTERING)
```

---

## 5. Observation Isolation Verification

### Specification File

**File:** `specs/ObservationIsolation.tla`

### Invariants to Prove

**I-OB1: No Execution Calls**
```tla
ObservationPurity ==
    /\ \A op \in ObservationOps :
        ~ InvokesExecution(op)
    \* No observation operation calls execution
```

**I-OB2: Layer Boundaries**
```tla
LayerBoundaries ==
    /\ M1_calls \subseteq {raw_data_sources}
    /\ M2_calls \subseteq {M1_outputs}
    /\ M5_calls \subseteq {M1, M2, M3, M4_outputs}
    /\ ~ (M5_calls \intersect {M6, EP2, EP3, EP4})
    \* One-way dependency only
```

---

## Property-Based Testing (Hypothesis)

### Framework

**Tool:** [Hypothesis](https://hypothesis.readthedocs.io/)

**Approach:** Generate random inputs, verify properties hold

### Test Files to Create

```
tests/property/
├── test_position_state_machine.py
├── test_arbitration_properties.py
├── test_risk_invariants.py
└── test_primitive_computation.py
```

### Example: Position State Machine Properties

**File:** `tests/property/test_position_state_machine.py`

```python
from hypothesis import given, strategies as st
from runtime.position.types import PositionState, Direction
from runtime.position.state_machine import PositionStateMachine

@given(
    initial_state=st.sampled_from(list(PositionState)),
    action=st.sampled_from(['ENTRY', 'SUCCESS', 'FAILURE', 'EXIT']),
    direction=st.sampled_from([Direction.LONG, Direction.SHORT]),
    quantity=st.decimals(min_value='0.001', max_value='100'),
    price=st.decimals(min_value='1', max_value='100000')
)
def test_position_transition_always_valid(initial_state, action, direction, quantity, price):
    """Property: Any transition either succeeds or raises ValidationError."""
    machine = PositionStateMachine()
    machine.set_state('TEST', initial_state)

    try:
        if action == 'ENTRY':
            machine.transition('TEST', action, direction=direction)
        elif action == 'SUCCESS':
            machine.transition('TEST', action, quantity=quantity, entry_price=price)
        else:
            machine.transition('TEST', action)

        # If succeeded, verify new state is valid
        new_state = machine.get_position('TEST').state
        assert new_state in PositionState
    except ValueError as e:
        # If failed, verify error message describes why
        assert 'invalid transition' in str(e).lower()

@given(
    actions=st.lists(
        st.sampled_from(['ENTRY', 'SUCCESS', 'EXIT', 'FAILURE']),
        min_size=1, max_size=20
    )
)
def test_position_eventually_reaches_flat(actions):
    """Property: After any sequence of actions, position eventually becomes FLAT."""
    machine = PositionStateMachine()

    for action in actions:
        try:
            if action == 'ENTRY':
                machine.transition('TEST', action, direction=Direction.LONG)
            elif action == 'SUCCESS':
                machine.transition('TEST', action,
                                 quantity=Decimal('1.0'),
                                 entry_price=Decimal('50000'))
            else:
                machine.transition('TEST', action)
        except ValueError:
            pass  # Skip invalid transitions

    # Property: Either FLAT now, or can reach FLAT with EXIT
    position = machine.get_position('TEST')
    if position.state != PositionState.FLAT:
        # Force EXIT
        machine.transition('TEST', 'EXIT')
        assert machine.get_position('TEST').state == PositionState.FLAT
```

---

## Executable Reference Model

### Purpose

Canonical implementation for cross-checking production code.

### Implementation

**File:** `reference/position_state_machine_ref.py`

```python
"""
Reference Implementation: Position State Machine

Pure functional implementation for formal verification.
No optimizations, maximum clarity.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal

class State(Enum):
    FLAT = 1
    ENTERING = 2
    OPEN = 3
    REDUCING = 4
    EXITING = 5

@dataclass(frozen=True)
class Position:
    state: State
    direction: Optional[str]  # 'LONG' | 'SHORT' | None
    quantity: Decimal
    entry_price: Optional[Decimal]

def transition(pos: Position, action: str, **kwargs) -> Position:
    """Pure transition function: (state, action) -> new_state."""

    if action == 'ENTRY':
        if pos.state != State.FLAT:
            raise ValueError(f"Cannot ENTRY from {pos.state}")
        return Position(
            state=State.ENTERING,
            direction=kwargs['direction'],
            quantity=Decimal('0'),
            entry_price=None
        )

    elif action == 'SUCCESS':
        if pos.state == State.ENTERING:
            return Position(
                state=State.OPEN,
                direction=pos.direction,
                quantity=kwargs['quantity'],
                entry_price=kwargs['entry_price']
            )
        elif pos.state == State.REDUCING:
            return Position(
                state=State.OPEN,
                direction=pos.direction,
                quantity=pos.quantity - kwargs['reduced_quantity'],
                entry_price=pos.entry_price
            )
        elif pos.state == State.EXITING:
            return Position(
                state=State.FLAT,
                direction=None,
                quantity=Decimal('0'),
                entry_price=None
            )
        else:
            raise ValueError(f"Cannot SUCCESS from {pos.state}")

    elif action == 'FAILURE':
        if pos.state in (State.ENTERING, State.REDUCING, State.EXITING):
            # Revert to previous logical state
            if pos.state == State.ENTERING:
                return Position(State.FLAT, None, Decimal('0'), None)
            else:  # REDUCING or EXITING
                return Position(State.OPEN, pos.direction, pos.quantity, pos.entry_price)
        else:
            raise ValueError(f"Cannot FAILURE from {pos.state}")

    elif action == 'EXIT':
        if pos.state != State.OPEN:
            raise ValueError(f"Cannot EXIT from {pos.state}")
        return Position(
            state=State.EXITING,
            direction=pos.direction,
            quantity=pos.quantity,
            entry_price=pos.entry_price
        )

    elif action == 'REDUCE':
        if pos.state != State.OPEN:
            raise ValueError(f"Cannot REDUCE from {pos.state}")
        return Position(
            state=State.REDUCING,
            direction=pos.direction,
            quantity=pos.quantity,
            entry_price=pos.entry_price
        )

    else:
        raise ValueError(f"Unknown action: {action}")
```

---

## Implementation Timeline

### Phase 1: TLA+ Specifications (5-7 days)

**Week 1:**
- Day 1-2: Position state machine spec + model checking
- Day 3: Arbitration logic spec + model checking
- Day 4: Temporal causality spec + model checking
- Day 5-7: Risk invariants spec (R1-R15) + adversarial scenarios

### Phase 2: Property-Based Tests (3-4 days)

**Week 2:**
- Day 1: Position state machine properties (Hypothesis)
- Day 2: Arbitration properties
- Day 3: Risk invariant properties
- Day 4: Primitive computation properties

### Phase 3: Executable Reference Models (2-3 days)

**Week 2-3:**
- Day 1: Position state machine reference
- Day 2: Arbitration reference
- Day 3: Cross-check production vs reference

**Total Estimated Effort:** 10-14 days

---

## Success Criteria

### Minimum Viable Verification

✅ TLA+ specs written for position state machine, arbitration, temporal causality
✅ Model checker finds zero invariant violations
✅ Property-based tests pass for 10,000+ random inputs
✅ Executable reference models match production behavior

### Adequate Verification

✅ All Minimum Viable criteria PLUS:
✅ Risk invariants (R1-R15) formally verified
✅ Adversarial scenario testing (price crashes, order rejections)
✅ Layer boundary isolation proven

### Full Verification (Production-Ready)

✅ All Adequate criteria PLUS:
✅ Proof that no deadlock states exist
✅ Liveness properties proven (eventually makes progress)
✅ Counterexample database (known failure modes documented)

---

## Tools Required

```bash
# Install TLA+ Toolbox
wget https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/TLAToolbox-1.8.0-linux.gtk.x86_64.zip
unzip TLAToolbox-*.zip

# Install Hypothesis for property-based testing
pip install hypothesis pytest

# Install model checker (TLC)
# Already included in TLA+ Toolbox
```

---

## References

- **TLA+ Homepage:** https://lamport.azurewebsites.net/tla/tla.html
- **TLA+ Video Course:** Leslie Lamport's video series
- **Hypothesis Documentation:** https://hypothesis.readthedocs.io/
- **Formal Methods in Industry:** AWS, Microsoft, CompCert case studies

---

## Status

**Current Status:** Framework created, no formal specs implemented

**Next Steps:**
1. Install TLA+ Toolbox
2. Write PositionStateMachine.tla spec (start here)
3. Run model checker, iterate until zero violations
4. Proceed to arbitration, temporal, risk specs

**Blocking Issues:** None - can start immediately

**Note:** Formal verification is future work (P3). System is operational without it for ghost trading calibration.
