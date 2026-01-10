# DIRECTORY-SCOPED EXCEPTION FRAMEWORK

**Status:** Authoritative  
**Authority:** Epistemic Constitution, Semantic Leak Audit  
**Purpose:** Define explicit boundaries where semantic computation is permitted vs forbidden

---

## 1. FRAMEWORK PRINCIPLE

**The constitution governs what the system claims — not how it thinks.**

Internal computation may use semantic concepts, interpretive naming, and statistical methods **ONLY IF** they never cross constitutional boundaries.

This framework defines those boundaries directory-by-directory.

---

## 2. BOUNDARY CLASSIFICATION

### 2.1 Zero-Tolerance Boundaries (Forbidden)

These boundaries enforce **absolute semantic purity**. No semantic leaks permitted.

**Boundaries:**
- Raw data ingestion → Observation
- Observation → Execution (via ObservationSnapshot)
- Mandate emission → Arbitration
- Arbitration → Execution
- Execution → Exchange
- Any layer → UI/Logs/External

**Rule:** Any data crossing these boundaries must pass semantic leak audit (all 9 categories).

---

### 2.2 Internal Computation Zones (Permitted)

These zones may contain semantic concepts **that never escape**.

**Zones:**
- `observation/internal/` - Internal observation computation
- `execution/internal/` - Internal execution logic (if exists)
- `memory/` - Legacy M6 scaffolding (isolated)
- Test files - Verification only

**Rule:** Semantic naming allowed, but constructs must not be exposed externally.

---

## 3. DIRECTORY-LEVEL RULES

### 3.1 `observation/` (Root)

**Files:** `types.py`, `governance.py`, `__init__.py`

**Semantic Leak Tolerance:** **ZERO**

**Allowed:**
- Raw data types only
- ObservationStatus (UNINITIALIZED, FAILED)
- SystemCounters (neutral field names only)
- ObservationSnapshot (facts only)
- Timestamps (explicit values, no interpretation)
- Symbol lists

**Forbidden:**
- Interpretive field names (`peak_pressure_events`, `baseline_status`)
- Health/quality/confidence assertions
- Aggregated metrics in exposed types
- Readiness indicators
- Any semantic naming in public API

**Enforcement:** Constitutional compliance audits, CI scanning

---

### 3.2 `observation/internal/`

**Files:** `m1_ingestion.py`, `m3_temporal.py`, `m4_*.py`

**Semantic Leak Tolerance:** **CONTAINED**

**Allowed:**
- Internal class names: `BaselineCalculator`, `PromotedEventInternal`
- Internal method names: `get_baseline()`, `is_warm()`, `detect_pressure()`
- Internal field names: `baseline_mean`, `sigma_distance`, `peak_pressure_events` (in counters dict)
- Internal comments with semantic terms
- Statistical computation (mean, stddev, thresholds)
- Temporal windowing logic
- Internal heuristics

**Forbidden:**
- Exposing internal types via `observation/__init__.py`
- Returning internal dataclasses from `governance.py`
- Using internal semantic names in external-facing methods
- Leaking internal state to ObservationSnapshot

**Enforcement:** Import audits, type exposure checks

---

### 3.3 `runtime/`

**Files:** `collector/service.py`, `native_app/main.py`, `m6_executor.py`

**Semantic Leak Tolerance:** **ZERO** (external I/O boundary)

**Allowed:**
- Querying ObservationSystem
- Ingesting raw market data
- Driving system clock with `time.time()`
- UI display of raw ObservationSnapshot fields
- Exception handling (no interpretation in messages)

**Forbidden:**
- Interpretive log messages (`"Connected"`, `"Error"`, `"Starting"`)
- UI text with semantic claims (`"Peak Pressure Detector"`, `"Healthy"`)
- Activity assertions (`"Processing"`, `"Analyzing"`)
- Quality judgments in logs
- Window titles with interpretive terms

**Enforcement:** String-level purity audits, log message scanning

---

### 3.4 `runtime/m6_executor.py`

**Files:** `m6_executor.py`

**Semantic Leak Tolerance:** **ZERO**

**Allowed:**
- Reading `observation_snapshot.status`
- Raising `SystemHaltedException` on FAILED
- Returning immediately on UNINITIALIZED
- Pure function with no state

**Forbidden:**
- Any interpretation of observation data
- Any logging
- Any state persistence
- Any retry logic
- Any inference from silence
- Any exposure of internal logic

**Enforcement:** Constitutional M6 audits, execution immunity checks

---

### 3.5 `execution/`

**Files:** Position state machine, mandate arbitration, execution actions

**Semantic Leak Tolerance:** **ZERO** (constitutional boundary)

**Allowed:**
- Position state transitions (FLAT→ENTERING→etc)
- Mandate types (ENTRY/EXIT/REDUCE/HOLD/BLOCK)
- Deterministic arbitration logic
- Exchange order submission
- Invariant enforcement

**Forbidden:**
- Interpreting WHY mandates exist
- Confidence-based decisions
- Retries or recovery heuristics
- Interpreting observation data
- Semantic naming in external interfaces

**Enforcement:** Position state machine audits, mandate contract verification

---

### 3.6 `memory/`

**Files:** `m6_scaffolding.py`, `test_m6_*.py`, `m2_continuity_store.py`, etc.

**Semantic Leak Tolerance:** **ISOLATED**

**Status:** Legacy M6 mandate framework, separate from constitutional M6

**Allowed:**
- Full semantic computation (isolated)
- `M5DescriptiveSnapshot`, `MandateDefinition`, `EvaluationEngine`
- Internal statistical logic
- Predicate evaluation

**Forbidden:**
- Cross-contamination with `runtime/m6_executor.py`
- Exposure via runtime imports
- Confusion with constitutional M6

**Enforcement:** Import isolation checks, type incompatibility verification

---

### 3.7 `tests/` and `memory/test_*.py`

**Files:** All test files

**Semantic Leak Tolerance:** **VERIFICATION ONLY**

**Allowed:**
- Any semantic naming for test clarity
- Direct invocation of internal methods
- Mocking with interpretive names
- Test fixture naming

**Forbidden:**
- Tests that validate semantic leaks as "working correctly"
- Tests that bypass constitutional constraints
- Tests that assume interpretation is valid

**Enforcement:** Test review, constitutional compliance tests

---

### 3.8 `docs/`

**Files:** All markdown documentation

**Semantic Leak Tolerance:** **EXPLANATORY**

**Allowed:**
- Semantic terms in explanations
- Interpretive language for human understanding
- Examples using semantic names

**Forbidden:**
- Documentation that contradicts constitution
- Guides that teach semantic leak patterns
- Specs that relax boundaries

**Enforcement:** Manual review, constitutional consistency checks

---

## 4. CROSS-DIRECTORY RULES

### 4.1 Import Restrictions

**Rule:** Internal modules must never be imported across boundaries.

**Forbidden Imports:**
```python
# In observation/types.py or governance.py
from observation.internal.m3_temporal import BaselineCalculator  # FORBIDDEN

# In runtime/
from observation.internal.m1_ingestion import M1IngestionEngine  # FORBIDDEN

# In observation/
from runtime.m6_executor import execute  # FORBIDDEN
```

**Allowed Imports:**
```python
# In observation/internal/m3_temporal.py
from observation.types import ObservationStatus  # OK (public API)

# In runtime/m6_executor.py
from observation.types import ObservationSnapshot  # OK (public API)
```

---

### 4.2 Type Exposure Rules

**Rule:** Internal dataclasses must never appear in public method signatures.

**Forbidden:**
```python
# In observation/governance.py
def get_baseline(self) -> BaselineStatus:  # FORBIDDEN TYPE
    return self._m3.get_baseline_status()
```

**Allowed:**
```python
# In observation/governance.py
def query(self, query_spec: Dict) -> ObservationSnapshot:  # OK (public type)
    return self._get_snapshot()

# Internal method with internal types - OK
def _get_baseline(self) -> BaselineStatus:  # OK (internal only)
    return self._baseline.get_status()
```

---

### 4.3 Field Exposure Rules

**Rule:** ObservationSnapshot fields must be semantically pure.

**Audit Questions:**
1. Does the field name imply interpretation? → FORBIDDEN
2. Does the field value encode meaning? → FORBIDDEN
3. Can the field be explained without semantic terms? → REQUIRED

**Examples:**
- ❌ `peak_pressure_events: int` - Name implies interpretation
- ❌ `baseline_ready: bool` - Name implies readiness judgment
- ✅ `windows_processed: Optional[int]` - Neutral count
- ✅ `timestamp: float` - Raw fact
- ✅ `symbols_active: List[str]` - Raw list

---

## 5. EXCEPTION APPROVAL PROCESS

### 5.1 When Exceptions Are Needed

If new semantic computation is required:

1. **Determine location** - Internal vs boundary
2. **If internal** - Add to appropriate `internal/` directory
3. **If boundary-crossing** - Constitutional amendment required

### 5.2 Amendment Requirements

To add semantic exposure across boundaries:

**Required:**
- Explicit constitutional amendment
- Epistemic justification (why raw data insufficient)
- Boundary impact analysis
- Alternative raw-data approach rejected
- Architect approval

**Process:** Not ad-hoc. Requires frozen document update.

---

## 6. ENFORCEMENT STRATEGY

### 6.1 Static Analysis (CI)

**Directory-scoped regex patterns:**
- `observation/` (root) → Zero semantic terms in types
- `runtime/` → Zero semantic terms in logs/UI
- `observation/internal/` → No exports to parent
- `runtime/m6_executor.py` → No interpretation patterns

### 6.2 Import Audits

**Check:**
- No cross-boundary internal imports
- No `observation.internal` imports outside `observation/`
- No `m6_executor` imports except explicit wiring

### 6.3 Type Exposure Audits

**Check:**
- Public method signatures use only public types
- ObservationSnapshot fields semantically pure
- No internal dataclasses in return types

---

## 7. SUMMARY TABLE

| Directory | Semantic Tolerance | Boundary Type | Enforcement |
|-----------|-------------------|---------------|-------------|
| `observation/` (root) | **ZERO** | External | CI, audits |
| `observation/internal/` | **CONTAINED** | Internal | Import checks |
| `runtime/` | **ZERO** | External I/O | String audits |
| `runtime/m6_executor.py` | **ZERO** | Constitutional | M6 audits |
| `execution/` | **ZERO** | Constitutional | State machine audits |
| `memory/` | **ISOLATED** | Legacy | Isolation checks |
| `tests/` | **VERIFICATION** | Test-only | Review |
| `docs/` | **EXPLANATORY** | Documentation | Consistency |

---

## 8. CONSTITUTIONAL ALIGNMENT

This framework operationalizes:

- **Epistemic Constitution** - Observation exposes facts only
- **M6 Contracts** - No interpretation, event-scoped only
- **Semantic Leak Audit** - All 9 leak types prevented at boundaries
- **PROJECT SPECIFICATION** - Internal computation allowed, exposure forbidden

---

## 9. FINAL RULE

**If a construct crosses a ZERO-tolerance boundary, it must pass all 9 semantic leak tests.**

No exceptions without constitutional amendment.

---

END OF FRAMEWORK
