# Constitutional Answer: Exit Logic

**Status:** Canonical
**Authority:** System Architecture
**Purpose:** Document exit path from observation to order submission

---

## Question

How does the system ensure positions can always be exited?

---

## Answer

### Exit Path

```
Strategy Proposal
    ↓
PolicyAdapter.evaluate_strategies()
    ↓
MandateType.EXIT (runtime/policy_adapter.py:445)
    ↓
Arbitrator.arbitrate()
    ↓
ExecutionController.process_cycle()
    ↓
Order Submission
```

### Exit Supremacy

EXIT mandates have the highest priority in the arbitration hierarchy:

```
EXIT > BLOCK > REDUCE > ENTRY > HOLD
```

**Source:** `runtime/arbitration/types.py:6`

```python
class MandateType(Enum):
    HOLD = 1      # No action needed
    ENTRY = 2     # Open new position
    REDUCE = 3    # Reduce position size
    BLOCK = 4     # Risk constraint violation
    EXIT = 5      # Close position (HIGHEST)
```

### Exit Always Allowed

Even in degraded system states, exits are permitted:

| Trust State | Trading | Entries | Exits |
|-------------|---------|---------|-------|
| OPERATIONAL | Yes | Yes | **Yes** |
| DEGRADED | Yes | Yes | **Yes** |
| WARNING | Yes | Reduced | **Yes** |
| CRITICAL | No | No | **Yes** |
| UNKNOWN_THREAT | No | No | **Yes** |

**Source:** `runtime/governance/meta_governor.py:443-447`

### Exit Sources

1. **Strategy Proposals** → PolicyAdapter transforms to EXIT mandate
2. **Risk Monitor** → Emits EXIT when `D_liq < D_critical` (`runtime/risk/monitor.py:132`)
3. **Stress Conditions** → Risk layer emits EXIT/REDUCE (`runtime/risk/tests/test_stress.py`)

### Arbitration Rules

From `runtime/arbitration/arbitrator.py`:

```python
# Step 1: EXIT always wins
exit_mandates = [m for m in mandates if m.type == MandateType.EXIT]
if exit_mandates:
    return Action(ActionType.EXIT, ...)
```

### Implementation Locations

| Component | File | Line |
|-----------|------|------|
| EXIT mandate type | `runtime/arbitration/types.py` | 24 |
| EXIT priority rule | `runtime/arbitration/arbitrator.py` | 50-53 |
| PolicyAdapter EXIT | `runtime/policy_adapter.py` | 445 |
| Risk monitor EXIT | `runtime/risk/monitor.py` | 132, 157, 168 |
| M6 EXIT processing | `runtime/m6_executor.py` | 356 |
| Controller process_cycle | `runtime/executor/controller.py` | 82 |
| Meta-governor allows_exits | `runtime/governance/meta_governor.py` | 446-447 |

### Tests Verifying Exit Logic

| Test File | Purpose |
|-----------|---------|
| `runtime/arbitration/tests/test_arbitration.py` | EXIT supremacy over BLOCK |
| `runtime/executor/tests/test_exit_lifecycle.py` | Full exit lifecycle |
| `runtime/executor/tests/test_integration.py` | EXIT mandate execution |
| `runtime/risk/tests/test_monitor.py` | Risk-triggered EXIT |
| `tests/integration/test_data_flow_coherence.py` | End-to-end exit flow |

### Constitutional Constraints

1. **EXIT cannot be blocked by lower-priority mandates**
2. **EXIT is always allowed regardless of trust state**
3. **Meta-governor cannot disable exits** (only entries)
4. **Capital governor scaling does not affect exit ability**

---

## Verification

```bash
# Verify EXIT priority
grep -n "EXIT.*5" runtime/arbitration/types.py

# Verify EXIT supremacy in arbitrator
grep -n "exit_mandates" runtime/arbitration/arbitrator.py

# Verify exits allowed in all trust states
grep -A5 "def _get_allowed_actions" runtime/governance/meta_governor.py

# Run exit lifecycle tests
pytest runtime/executor/tests/test_exit_lifecycle.py -v
```

---

## Doctrinal Statement

The system prioritizes SURVIVAL above all else. Exit logic is designed such that:

1. Exits can never be prevented by internal system state
2. Exits take precedence over all other mandate types
3. Even in CRITICAL or UNKNOWN_THREAT states, exits execute
4. No governance layer may disable exit capability

This ensures capital can always be recovered regardless of system degradation.
