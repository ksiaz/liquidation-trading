# M6 EXECUTION PATH IMMUNITY AUDIT

**Date:** 2026-01-06 16:06:45  
**Type:** Repository-Wide Invocation Safety Audit  
**Authority:** M6 Constitutional Documents

---

## SECTION A: CONFIRMED INVOCATION PATHS

**NONE**

No confirmed invocation paths found.

No imports of `m6_executor` exist in any file.

No calls to `execute()` from `runtime.m6_executor` exist in any file.

---

## SECTION B: POTENTIAL ACCIDENTAL INVOCATION VECTORS

### Vector 1: Legacy M6 Scaffolding Code

**File:** `memory/m6_scaffolding.py`  
**Lines:** 1-453 (entire file)  
**Why Dangerous:** Contains complete M6 mandate evaluation framework (EvaluationEngine, MandateLoader, OutputEnforcer, etc.) but is UNRELATED to constitutional `runtime/m6_executor.py`

**Currently Reachable:** NO  
**Reason:** This is a separate, legacy M6 framework used for M5-M6 mandate-based evaluation. It does NOT import or reference `runtime/m6_executor.py`. It operates on `M5DescriptiveSnapshot` inputs (different from `ObservationSnapshot`). No wiring exists between this legacy code and the new constitutional M6 executor.

---

### Vector 2: Legacy M6 Test Files

**File:** `memory/test_m6_m5_integration.py`  
**Lines:** 1-360  
**Why Dangerous:** Tests legacy M6 scaffolding framework

**Currently Reachable:** NO  
**Reason:** Only tests `memory.m6_scaffolding` module, not `runtime.m6_executor`. No imports of constitutional M6 exist.

**File:** `memory/test_m6_scaffolding.py`  
**Lines:** 1-423  
**Why Dangerous:** Tests legacy M6 mandate framework

**Currently Reachable:** NO  
**Reason:** Only tests `memory.m6_scaffolding` module, not `runtime.m6_executor`. No imports of constitutional M6 exist.

---

### Vector 3: M6 Call-Site Marker Comment

**File:** `runtime/collector/service.py`  
**Line:** 106  
**Code:** `# M6 MAY be invoked here with an explicit ObservationSnapshot`

**Why Dangerous:** Marks explicit location where M6 invocation COULD occur

**Currently Reachable:** NO  
**Reason:** This is a comment only. No code follows it. No import of `m6_executor` exists. No call to `execute()` exists. The comment is a placeholder for future explicit architect-approved wiring.

---

### Vector 4: Generic "execute" Function Search

**Files Containing `def execute(`:**
- `runtime/m6_executor.py:4` (constitutional M6 only)

**Why Dangerous:** Generic name could be confused

**Currently Reachable:** NO  
**Reason:** Only the constitutional `execute()` function exists in `runtime/m6_executor.py`. No other files define an `execute()` function that could be confused with M6's execution path.

---

## SECTION C: STRUCTURAL GUARANTEES

### Why M6 Cannot Be Executed Today

1. **No Imports Exist**
   - Zero imports of `m6_executor` in any file
   - Zero imports of `runtime.m6_executor` in any file
   - Module is isolated

2. **No Function Calls Exist**
   - Zero calls to `execute()` with ObservationSnapshot parameter
   - Call-site marker is comment-only, no code

3. **No Automatic Mechanisms**
   - No timers
   - No async tasks
   - No background loops
   - No observers
   - No callbacks
   - No hooks

4. **Type Isolation**
   - `m6_executor.execute()` requires `ObservationSnapshot` (from observation.types)
   - Legacy `m6_scaffolding` uses `M5DescriptiveSnapshot` (incompatible type)
   - Type system prevents accidental invocation of wrong M6 framework

5. **Hard Dependency Not Satisfied**
   - M6 requires explicit ObservationSnapshot parameter
   - No code path constructs ObservationSnapshot and passes to M6
   - Query to ObservationSystem exists (line 83 of native

_app/main.py) but snapshot is consumed only by UI, not passed to M6

---

### What Exact Change Would Be Required to Execute M6

To execute the constitutional M6 (`runtime/m6_executor.py`), ALL of the following must occur:

1. **Import Statement**
   - Add: `from runtime.m6_executor import execute` to a runtime file

2. **ObservationSnapshot Query**
   - Query ObservationSystem: `snapshot = obs_system.query({'type': 'snapshot'})`

3. **Explicit Invocation**
   - Add: `execute(snapshot)` after obtaining snapshot

4. **Exception Handling**
   - Handle `SystemHaltedException` if observation FAILED

**Minimum Code Required (Example):**
```python
from runtime.m6_executor import execute
from observation.types import SystemHaltedException

# ... in collector service after line 106 ...
try:
    snapshot = self._obs.query({'type': 'snapshot'})
    execute(snapshot)  # <-- EXPLICIT INVOCATION REQUIRED
except SystemHaltedException:
    # Handle observation failure
    pass
```

**All 4 steps above are currently ABSENT from the codebase.**

---

## LEGACY CODE ISOLATION VERIFICATION

### Legacy M6 Framework (`memory/m6_scaffolding.py`)

**Status:** Isolated

**Why Safe:**
- Uses different input type (`M5DescriptiveSnapshot` not `ObservationSnapshot`)
- Uses different module path (`memory.m6_scaffolding` not `runtime.m6_executor`)
- No imports of constitutional M6
- No cross-references

**Test Files:**
- `memory/test_m6_scaffolding.py` - tests legacy only
- `memory/test_m6_m5_integration.py` - tests legacy only
- No tests for constitutional `runtime/m6_executor.py`

---

## FINAL STATEMENT

**"M6 cannot run unless the architect explicitly wires it."**

**Proof:**
1. Zero imports of `m6_executor` exist
2. Zero function calls to `execute()` exist
3. Zero automatic invocation mechanisms exist
4. Call-site marker is comment-only
5. ObservationSnapshot is queried but NOT passed to M6
6. Legacy M6 code (m6_scaffolding) uses incompatible types
7. Type system enforces hard dependency on ObservationSnapshot
8. Explicit 4-step wiring required (currently absent)

M6 invocation requires explicit, architect-approved code changes in at least 4 places.

---

END OF IMMUNITY AUDIT
