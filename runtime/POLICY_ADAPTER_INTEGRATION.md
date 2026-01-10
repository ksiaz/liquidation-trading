# Policy Adapter Integration

**Status:** Implemented
**Date:** 2026-01-10
**Phase:** Phase 2 - Observation Layer Integration
**Authority:** Architectural ruling 2026-01-10

---

## Purpose

The `PolicyAdapter` module is a **pure wiring layer** that connects the observation system (M1-M5) to the execution system (runtime/) while maintaining constitutional boundaries.

---

## Architecture

```
ObservationSystem (M1-M5)
      ↓
  M4 Primitives
      ↓
  PolicyAdapter  ← This module (pure wiring)
      ↓
External Policies (EP2, frozen)
      ↓
  Policy Proposals
      ↓
Mandate Normalization
      ↓
ExecutionController
      ↓
  Position State Machine + Risk Enforcement
```

---

## What PolicyAdapter Does

### 1. Query M4 Primitives from Observation
- Reads `ObservationSnapshot` status
- Extracts M4 structural primitives (via M5 governance)
- Does NOT interpret observation data

### 2. Invoke Frozen External Policies
- Calls `ep2_strategy_geometry`, `ep2_strategy_kinematics`, `ep2_strategy_absence`
- Passes primitives as-is
- Does NOT modify or reinterpret policy outputs

### 3. Normalize Proposals to Mandates
- Converts `StrategyProposal` → `Mandate`
- Mechanical mapping only
- No scoring, no ranking, no aggregation

### 4. Handle Observation Status
- `FAILED` → emit BLOCK mandate (maximum authority)
- `UNINITIALIZED` → emit no mandates
- Per `M6_CONSUMPTION_CONTRACT.md`

---

## What PolicyAdapter Does NOT Do

❌ **Strategy Logic** - In `external_policy/`, frozen
❌ **Risk Constraints** - In `runtime/risk/`, separate concern
❌ **Arbitration** - In `runtime/arbitration/`, separate concern
❌ **State Management** - In `runtime/position/`, separate concern
❌ **Interpretation** - Observation fields treated as opaque
❌ **Caching/Memory** - Stateless, no state between calls
❌ **Scoring/Ranking** - Pure pass-through

---

## Constitutional Compliance

### Epistemic Boundary Enforcement

✅ **Internal semantics stay internal**
- `strength`, `confidence` in `memory/` do NOT cross boundary
- Only raw primitives (counts, timestamps, prices) exposed
- Per architect ruling: "Internal semantics allowed; exported semantics forbidden"

✅ **No semantic leakage**
- CI scanner: 0 violations
- Test suite: Verified no forbidden fields in Mandates
- Per `EPISTEMIC_CONSTITUTION.md` Article VIII

✅ **Observation ignorance**
- ExecutionController does NOT query observation directly
- PolicyAdapter acts as translation layer
- Per `SYSTEM_CANON.md` separation of concerns

✅ **Frozen component respect**
- No modifications to `external_policy/`
- No modifications to `observation/`
- No modifications to `memory/` (M1-M5)
- Per `CODE_FREEZE.md`

---

## API Reference

### PolicyAdapter Class

```python
class PolicyAdapter:
    def __init__(self, config: Optional[AdapterConfig] = None)

    def generate_mandates(
        self,
        observation_snapshot: ObservationSnapshot,
        symbol: str,
        timestamp: float
    ) -> List[Mandate]
```

**Properties:**
- Stateless: No instance variables modified
- Deterministic: Same inputs → same outputs
- Pure: No side effects

### AdapterConfig

```python
@dataclass(frozen=True)
class AdapterConfig:
    default_authority: float = 5.0
    enable_geometry: bool = True
    enable_kinematics: bool = True
    enable_absence: bool = True
```

---

## Integration Points

### Input Boundary: Observation

**From:** `observation/types.py` → `ObservationSnapshot`

**Fields used:**
- `status` (ObservationStatus enum)
- `timestamp` (float)
- `symbols_active` (List[str])
- `counters` (NOT interpreted, only presence checked)
- `promoted_events` (NOT interpreted)

**Contract:** Per `M6_CONSUMPTION_CONTRACT.md`
- Treat observation as potentially silent/failed
- Never interpret counters as "health"
- Never interpret events as "significance"

### Output Boundary: Execution

**To:** `runtime/arbitration/types.py` → `Mandate`

**Fields emitted:**
- `symbol` (str)
- `type` (MandateType enum: ENTRY/EXIT/REDUCE/HOLD/BLOCK)
- `authority` (float, mechanical mapping)
- `timestamp` (float)

**Contract:** Per `MANDATE_ARBITRATION_PROOFS.md`
- One mandate per policy per symbol
- No confidence scores
- No semantic fields

---

## Testing

### Test Coverage: 8 tests, 100% pass

**Test Categories:**
1. **Observation Status Handling** (2 tests)
   - FAILED → BLOCK mandate
   - UNINITIALIZED → no mandates

2. **Wiring Behavior** (3 tests)
   - Stateless operation
   - Missing primitives handled gracefully
   - Configuration disables policies

3. **Semantic Leakage Prevention** (2 tests)
   - No interpretation of observation fields
   - No semantic fields in output

4. **Integration** (1 test)
   - End-to-end: Observation → Adapter → ExecutionController

**Verification:**
- ✅ All tests passing
- ✅ CI semantic leak scanner: 0 violations
- ✅ No forbidden terms in code

---

## Current Limitations (Known Stubs)

### 1. M4 Primitive Extraction (Stub)

**Current:** Returns `None` for all primitives

**Location:** `PolicyAdapter._extract_primitives()`

**Why:** M5 query interface not yet wired

**Impact:** External policies return no proposals (all primitives None)

**Future:** Wire M5 governance layer to query actual M4 primitives

### 2. M6 Permission (Stub)

**Current:** Always returns "ALLOWED"

**Location:** `PolicyAdapter.generate_mandates()` (permission object)

**Why:** M6 scaffolding not yet implemented

**Impact:** No M6 governance enforcement

**Future:** Implement M6 permission checking per frozen external policy contracts

### 3. Action Type Mapping (Simplified)

**Current:** All proposals map to `MandateType.ENTRY`

**Location:** `PolicyAdapter._map_action_to_mandate()`

**Why:** Simplified for initial wiring

**Impact:** No EXIT/REDUCE mandates from policies

**Future:** Enhance mapping based on proposal action_type semantics

---

## Next Steps

### Immediate
1. ✅ PolicyAdapter implemented
2. ✅ Tests passing
3. ✅ Semantic leak verification passed
4. ⏭️ Wire M5 query interface for actual primitive extraction

### Future Enhancements
1. Implement M6 scaffolding for permission checking
2. Enhance action type mapping
3. Add performance monitoring (logging only, no interpretation)
4. Add replay/simulation support

---

## File Locations

**Implementation:**
- `runtime/policy_adapter.py` (226 lines)

**Tests:**
- `runtime/tests/test_policy_adapter.py` (213 lines, 8 tests)

**Dependencies:**
- `observation/types.py` (ObservationSnapshot)
- `runtime/arbitration/types.py` (Mandate)
- `external_policy/ep2_strategy_*.py` (frozen, read-only)

---

## Maintenance Rules

### Allowed Modifications
- ✅ Add logging (metrics only, no interpretation)
- ✅ Add performance instrumentation
- ✅ Add tests
- ✅ Fix bugs in wiring logic

### Forbidden Modifications
- ❌ Add strategy logic (goes in `external_policy/`)
- ❌ Add risk logic (goes in `runtime/risk/`)
- ❌ Add arbitration logic (goes in `runtime/arbitration/`)
- ❌ Add caching/memory
- ❌ Add interpretation/scoring
- ❌ Modify frozen external policies

**If unsure → stop and ask architect**

---

## Constitutional Traceability

**Authority Chain:**
```
EPISTEMIC_CONSTITUTION.md (Observation exposure rules)
    ↓
SYSTEM_CANON.md (Layer separation)
    ↓
CODE_FREEZE.md (Frozen component respect)
    ↓
Architectural Ruling 2026-01-10 (Integration layer necessity)
    ↓
runtime/policy_adapter.py (Implementation)
```

All design decisions trace back to constitutional authority.

---

**Status:** ✅ Complete for Phase 2
**Constitutional Compliance:** ✅ Verified
**Test Coverage:** ✅ 100% (8/8 tests passing)
**Semantic Leakage:** ✅ None detected

---

END OF DOCUMENTATION
