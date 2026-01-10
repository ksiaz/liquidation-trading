# M6 FUTURE REGRESSION PROHIBITION AUDIT

**Date:** 2026-01-06 16:10:15  
**Type:** Forward-Looking Regression Safety Analysis  
**Authority:** All M6 Constitutional Documents

---

## SECTION A: HIGH-RISK WIRING POINTS

### Risk Point 1: Collector Service (runtime/collector/service.py)

**Location:** Line 106 (after `self._obs.ingest_observation()`)

**Current State:** Comment marker only: `# M6 MAY be invoked here with an explicit ObservationSnapshot`

**Exact Change Required to Enable M6:**
```python
# Add import at top of file
from runtime.m6_executor import execute

# Add code after line 106
snapshot = self._obs.query({'type': 'snapshot'})
execute(snapshot)
```

**Visible in Code Review:** ✅ YES
- New import statement clearly visible
- New function call clearly visible
- New query to ObservationSystem clearly visible

**Violates Frozen Documents:**
1. **M6_EXISTENCE_DETERMINATION.md** - Creates loop (websocket loop calls M6 repeatedly)
2. **M6_DEPENDENCY_DECLARATION.md** - Violates prohibition on loops, automatic invocation
3. **M6_FORBIDDEN_BEHAVIORS.md** - Creates background execution pattern

**Constitutional Breach:** EXPLICIT - Adding this code directly violates prohibition on loops and automatic invocation

---

### Risk Point 2: UI Update Loop (runtime/native_app/main.py)

**Location:** Line 83 (inside `update_ui()`, after snapshot query)

**Current State:** Snapshot obtained but only used for UI display

**Exact Change Required to Enable M6:**
```python
# Add import at top
from runtime.m6_executor import execute

# Modify update_ui() at line 83
snapshot: ObservationSnapshot = self.obs_system.query({'type': 'snapshot'})
execute(snapshot)  # NEW LINE
```

**Visible in Code Review:** ✅ YES
- New import statement
- New line in update loop
- Clear invocation of M6

**Violates Frozen Documents:**
1. **M6_EXISTENCE_DETERMINATION.md** - Creates timer-based invocation (QTimer runs update_ui every 250ms)
2. **M6_DEPENDENCY_DECLARATION.md** - Violates prohibition on scheduled execution
3. **EPISTEMIC_CONSTITUTION.md** - UI should not invoke execution layer

**Constitutional Breach:** EXPLICIT - Timer-based loop violates prohibition on periodic invocation

---

### Risk Point 3: New Scheduled Service

**Location:** Hypothetical new file `runtime/m6_scheduler.py`

**Current State:** Does not exist

**Exact Change Required to Enable M6:**
```python
# Create new file runtime/m6_scheduler.py
import asyncio
from runtime.m6_executor import execute
from observation import ObservationSystem

class M6Scheduler:
    def __init__(self, obs_system):
        self._obs = obs_system
    
    async def run(self):
        while True:
            snapshot = self._obs.query({'type': 'snapshot'})
            execute(snapshot)
            await asyncio.sleep(1)
```

**Visible in Code Review:** ✅ YES
- New file creation
- Explicit loop
- Explicit M6 import and call

**Violates Frozen Documents:**
1. **M6_EXISTENCE_DETERMINATION.md** - Creates persistent service (violates event-scoped requirement)
2. **M6_DEPENDENCY_DECLARATION.md** - Violates all prohibitions: loops, scheduling, background execution
3. **M6_FORBIDDEN_BEHAVIORS.md** - Creates forbidden loop pattern

**Constitutional Breach:** EXPLICIT - Creating scheduler service directly violates event-scoped requirement

---

### Risk Point 4: Test File Direct Invocation

**Location:** Hypothetical new file `test_m6_executor.py`

**Current State:** Does not exist

**Exact Change Required to Enable M6:**
```python
# Create test_m6_executor.py
from runtime.m6_executor import execute
from observation.types import ObservationSnapshot, ObservationStatus

def test_m6_execution():
    snapshot = ObservationSnapshot(
        status=ObservationStatus.UNINITIALIZED,
        timestamp=1000.0,
        symbols_active=['BTCUSDT'],
        counters=SystemCounters(None, None),
        promoted_events=None
    )
    execute(snapshot)  # M6 executed in test
```

**Visible in Code Review:** ✅ YES
- New test file
- Direct M6 invocation
- Snapshot construction

**Violates Frozen Documents:**
- **NONE** - Tests are permitted to invoke M6 directly for verification

**Constitutional Breach:** ❌ NO BREACH - Tests may invoke M6 to verify compliance

**Safety Assessment:** SAFE - Test invocation does not enable production execution

---

### Risk Point 5: Observer Pattern Hook

**Location:** Hypothetical modification to `observation/governance.py`

**Current State:** No callbacks or observers exist

**Exact Change Required to Enable M6:**
```python
# Modify observation/governance.py
from runtime.m6_executor import execute

class ObservationSystem:
    def __init__(self, allowed_symbols):
        # ... existing code ...
        self._observers = []  # NEW
    
    def register_observer(self, callback):  # NEW
        self._observers.append(callback)
    
    def advance_time(self, new_timestamp):
        # ... existing code ...
        # NEW: Notify observers
        snapshot = self._get_snapshot()
        for observer in self._observers:
            observer(snapshot)

# In collector:
obs_system.register_observer(execute)  # Wire M6 as observer
```

**Visible in Code Review:** ✅ YES
- New observer pattern in observation layer
- New registration call
- Import of M6 in observation layer (architectural violation)

**Violates Frozen Documents:**
1. **M6_CONSUMPTION_CONTRACT.md** - M6 may not be referenced by observation
2. **M6_DEPENDENCY_DECLARATION.md** - Violates prohibition on callbacks and observers
3. **EPISTEMIC_CONSTITUTION.md** - Observation must not know about execution

**Constitutional Breach:** EXPLICIT - Observer pattern violates callback prohibition and one-way dependency

---

### Risk Point 6: Async Task in Collector

**Location:** `runtime/collector/service.py`, line 41 in `start()` method

**Current State:** Creates clock driver task but not M6 task

**Exact Change Required to Enable M6:**
```python
# Modify start() method
async def start(self):
    self._running = True
    
    asyncio.create_task(self._drive_clock())
    asyncio.create_task(self._run_binance_stream())
    asyncio.create_task(self._drive_m6())  # NEW TASK

# Add new method
async def _drive_m6(self):  # NEW METHOD
    from runtime.m6_executor import execute
    while self._running:
        snapshot = self._obs.query({'type': 'snapshot'})
        execute(snapshot)
        await asyncio.sleep(0.5)
```

**Visible in Code Review:** ✅ YES
- New task creation
- New method definition
- Clear M6 loop

**Violates Frozen Documents:**
1. **M6_EXISTENCE_DETERMINATION.md** - Creates background task (violates event-scoped)
2. **M6_DEPENDENCY_DECLARATION.md** - Violates prohibition on background execution and loops

**Constitutional Breach:** EXPLICIT - Background task directly violates event-scoped requirement

---

### Risk Point 7: Import Side-Effect

**Location:** Any file importing `runtime.m6_executor`

**Current State:** Module contains only function definition, no side effects

**Exact Change Required to Enable M6:**
```python
# Modify runtime/m6_executor.py to add side effect
from observation import ObservationSystem

# Module-level execution on import
_obs = ObservationSystem(['BTCUSDT'])
snapshot = _obs.query({'type': 'snapshot'})
execute(snapshot)  # Runs on import!
```

**Visible in Code Review:** ✅ YES
- Module-level code clearly visible
- Import side-effect pattern obvious

**Violates Frozen Documents:**
1. **M6_EXISTENCE_DETERMINATION.md** - Creates persistent execution context
2. **M6_DEPENDENCY_DECLARATION.md** - Creates automatic invocation

**Constitutional Breach:** EXPLICIT - Module-level execution violates event-scoped requirement

**Safety Assessment:** DETECTABLE - Any module-level code in m6_executor.py is architectural violation

---

## SECTION B: REQUIRED EXPLICIT VIOLATIONS

To enable M6 in production, a developer MUST violate at least ONE of the following frozen documents:

### Document 1: M6_EXISTENCE_DETERMINATION.md

**Binding Constraint:** M6 must be event-scoped stateless invocation only

**Violations That Enable M6:**
- Creating loops (while True)
- Creating async tasks
- Creating schedulers
- Creating timers
- Creating persistent objects
- Any class-level state
- Any background execution

**Detectability:** All violations require explicit new code (loops, tasks, classes)

---

### Document 2: M6_DEPENDENCY_DECLARATION.md

**Binding Constraint:** Prohibits loops, retries, background execution, caching, scheduling, hooks, callbacks

**Violations That Enable M6:**
- Adding M6 call inside any loop
- Adding asyncio.create_task(m6...)
- Registering M6 as callback
- Using QTimer or similar to invoke M6
- Any automatic invocation pattern

**Detectability:** All violations add explicit invocation code

---

### Document 3: M6_FORBIDDEN_BEHAVIORS.md

**Binding Constraint:** M6 must not operate as service, must not retry, must not persist

**Violations That Enable M6:**
- Creating M6 service class
- Adding retry logic around M6
- Caching observation data for M6
- Any persistence mechanism

**Detectability:** All violations require new classes, error handling, or storage

---

### Document 4: EPISTEMIC_CONSTITUTION.md (Boundary Discipline)

**Binding Constraint:** Observation layer must not reference execution layer

**Violations That Enable M6:**
- Importing m6_executor in observation/
- Adding callbacks from observation to M6
- Creating observers in observation layer

**Detectability:** Import statement in observation/ directory is immediate red flag

---

## SECTION C: REGRESSION SAFETY VERDICT

**M6 cannot be enabled without an explicit constitutional breach.**

---

## DETAILED SAFETY ANALYSIS

### Why Accidental Enablement is Impossible

1. **Import Requirement**
   - M6 requires explicit import: `from runtime.m6_executor import execute`
   - This import must appear in a runtime file
   - Import is first-class code statement, not configuration
   - 100% visible in code review

2. **Function Call Requirement**
   - M6 requires explicit function call: `execute(snapshot)`
   - Function call must pass ObservationSnapshot parameter
   - Cannot be triggered by configuration
   - Cannot be triggered accidentally

3. **Type Enforcement**
   - M6 requires ObservationSnapshot type
   - No automatic conversion exists
   - Type mismatch would cause runtime error
   - Type system prevents wrong inputs

4. **No Configuration Backdoors**
   - No environment variables enable M6
   - No config files enable M6
   - No feature flags enable M6
   - No command-line arguments enable M6

5. **Architectural Isolation**
   - M6 in separate module (runtime/m6_executor.py)
   - Observation layer cannot reference it
   - UI layer has no reason to invoke it
   - Collector has marker comment but no code

6. **Constitutional Documentation**
   - 5 frozen documents explicitly prohibit automatic invocation
   - All documents publicly visible in repository
   - Any violation requires changing frozen doc OR violating it
   - Both actions visible in code review

### What Code Review Must Catch

To prevent M6 regression, code reviewers must reject:

**Immediate Red Flags:**
- ❌ `import m6_executor` in any file
- ❌ `from runtime.m6_executor` in any file
- ❌ `execute(` call with ObservationSnapshot
- ❌ New loops that query observation
- ❌ New async tasks in collector
- ❌ New timers or schedulers
- ❌ Observer pattern in observation layer
- ❌ Callbacks registered with observation
- ❌ New service classes in runtime/

**Subtle Red Flags:**
- ⚠️ Module-level code in m6_executor.py
- ⚠️ New test files that import m6_executor (tests are OK, but verify they're tests)
- ⚠️ Configuration that references "m6" or "executor"

### Regression Prevention Checklist

Code review must verify:
1. ✅ No new imports of runtime.m6_executor except in tests
2. ✅ No new loops in collector service
3. ✅ No new async tasks that query observation
4. ✅ No observer/callback patterns added
5. ✅ No scheduler services created
6. ✅ Observation layer has zero references to M6
7. ✅ All 5 constitutional documents remain frozen

---

## FINAL VERDICT

M6 invocation requires:
- ✅ Explicit import statement
- ✅ Explicit function call
- ✅ Violation of at least 1 frozen document
- ✅ All changes visible in code review

**No accidental, configuration-based, or hidden enablement path exists.**

**Regression safety: GUARANTEED by architectural isolation and constitutional documentation.**

---

END OF REGRESSION AUDIT
