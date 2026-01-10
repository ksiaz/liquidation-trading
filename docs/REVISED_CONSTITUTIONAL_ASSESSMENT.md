# REVISED CONSTITUTIONAL COMPLIANCE ASSESSMENT

**Date:** 2026-01-06 15:33:45  
**Type:** Constitutional Boundary Correction & Re-evaluation  
**Authority:** System Architect Clarification

---

## SECTION 1: CORRECT BOUNDARY DEFINITION

### External Speech (Constitutional Constraints Apply)

**ObservationSnapshot Exposure:**
- Field values returned in ObservationSnapshot
- Field names in ObservationSnapshot (if values are non-None)

**UI/Human-Visible:**
- Window titles
- Status labels
- Error messages displayed to user
- Dashboard text
- Any QLabel.setText() content

**Logs:**
- logger.info() messages
- logger.error() messages  
- logger.warning() messages
- print() statements visible to operators

**Exceptions:**
- Exception messages raised outside observation/
- SystemHaltedException text surfaced to UI

**M6 Consumption:**
- Any value or field consumed by execution layer
- Any API response
- Any CLI output

---

### Internal Computation (Constitutional Constraints Do NOT Apply)

**Internal Code:**
- Variable names (e.g., `baseline`, `pressure`, `_is_warm`)
- Class names (e.g., `BaselineCalculator`, `PromotedEventInternal`)
- Method names (e.g., `get_baseline()`, `is_warm()`)
- Function names (e.g., `_update_liveness()`)
- Parameter names

**Internal Documentation:**
- Comments within code
- Docstrings for internal methods
- Internal annotations
- Type hints

**Internal State:**
- Counter names (e.g., `'peak_pressure_events': 0` in internal dict)
- Internal dataclass fields not exposed externally
- Private attributes (e.g., `self._baseline`)
- Internal buffers, deques, lists

**Statistical Concepts:**
- baseline, mean, stddev calculations
- threshold comparisons
- sigma distances
- warmth/readiness checks (internal only)

---

## SECTION 2: RE-EVALUATION OF PRIOR VIOLATIONS

### VIOLATION 1: observation/types.py Line 23
**Original Finding:**
```python
peak_pressure_events: Optional[int]
```

**Re-evaluation:**
- **Location:** SystemCounters dataclass, part of ObservationSnapshot
- **Boundary:** External (field in public snapshot structure)
- **Current Value:** Always None (never populated per governance.py:127)
- **Assertion Made:** Field name exists in structure, but value is None (maximum silence)

**VERDICT:** **QUESTIONABLE**
- Field is part of external structure (crosses boundary)
- However, value is always None (no assertion of measurement)
- Field name is structural metadata, not an active claim
- **DEFER TO ARCHITECT:** Does unpopulated field name constitute assertion?

---

### VIOLATION 2: observation/internal/m3_temporal.py (20+ occurrences)
**Original Finding:** "baseline", "pressure", "is_warm" throughout internal code

**Re-evaluation:**
- **Location:** observation/internal/ (internal computation module)
- **Boundary:** Internal only - not exposed in ObservationSnapshot
- **Examples:**
  - `class BaselineCalculator` (internal class)
  - `def get_baseline()` (internal method)
  - `self._baseline.is_warm()` (internal readiness check)
  - `baseline_mean: float` (internal dataclass field)
  - `'peak_pressure_events': 0` (internal counter dict)

**VERDICT:** **INVALID**
- All references are internal computation
- Never cross external boundary
- Statistical calculation is permitted internally
- Constitution forbids assertion, not computation

---

### VIOLATION 3: observation/governance.py Lines 53, 79, 107-108, 127
**Original Finding:** "Pressure" comment, "liveness" method, field name

**Re-evaluation:**

**Line 53:** `# Dispatch to M3 (Temporal & Pressure) if it's a trade`
- **Boundary:** Internal comment
- **VERDICT:** **INVALID** (internal documentation)

**Lines 79, 107-108:** `_update_liveness()` method and docstring
- **Boundary:** Internal method name and docstring
- **VERDICT:** **INVALID** (internal code)

**Line 127:** `peak_pressure_events=None,` in _get_snapshot()
- **Boundary:** External (populates ObservationSnapshot field)
- **Value:** None (silenced)
- **VERDICT:** **Same as VIOLATION 1** (structural field with None value)

**OVERALL:** Most INVALID (internal), one questionable (field name)

---

### VIOLATION 4: runtime/native_app/main.py Lines 2, 43
**Original Finding:** "Peak Pressure Detector" in docstring and window title

**Re-evaluation:**

**Line 2:** `New Peak Pressure Detector App (Remediated)`
- **Boundary:** Module docstring (internal documentation)
- **VERDICT:** **INVALID** (internal comment)

**Line 43:** `self.setWindowTitle("Peak Pressure Detector (Sealedv1.0)")`
- **Boundary:** External (user-visible window title)
- **VERDICT:** **VALID** - Window title is human-visible UI element

---

### VIOLATION 5: runtime/collector/service.py Lines 76, 108
**Original Finding:** Log statements

**Re-evaluation:**

**Line 76:** `self._logger.info(f"Connecting to {stream_url}")`
- **Boundary:** External (log visible to operators)
- **Assertion:** "Connecting to" implies activity state
- **VERDICT:** **VALID** - Logs are external speech

**Line 108:** `self._logger.error(f"WS Error: {e}")`
- **Boundary:** External (log visible to operators)
- **Assertion:** "Error" interprets exception as error quality
- **VERDICT:** **VALID** - Logs are external speech

---

## SECTION 3: RESIDUAL TRUE VIOLATIONS

After boundary correction, the following violations cross external boundaries:

### VALID VIOLATION 1
**FILE:** runtime/native_app/main.py  
**LINE:** 43  
**CODE:** `self.setWindowTitle("Peak Pressure Detector (Sealedv1.0)")`  
**BOUNDARY:** User-visible window title  
**WHY VIOLATION:** "Peak Pressure Detector" uses interpretive terms "peak" and "pressure" in external UI

### VALID VIOLATION 2
**FILE:** runtime/collector/service.py  
**LINE:** 76  
**CODE:** `self._logger.info(f"Connecting to {stream_url}")`  
**BOUNDARY:** Operator-visible log  
**WHY VIOLATION:** "Connecting to" asserts activity state

### VALID VIOLATION 3
**FILE:** runtime/collector/service.py  
**LINE:** 108  
**CODE:** `self._logger.error(f"WS Error: {e}")`  
**BOUNDARY:** Operator-visible log  
**WHY VIOLATION:** "Error" interprets exception as quality assessment

### QUESTIONABLE (DEFERRED TO ARCHITECT)
**FILE:** observation/types.py  
**LINE:** 23, 32  
**CODE:** `peak_pressure_events: Optional[int]` in SystemCounters, exposed in ObservationSnapshot  
**BOUNDARY:** External structure field name  
**VALUE:** Always None (silenced)  
**QUESTION:** Does field name constitute assertion when value is always None?

---

## FORMAL WITHDRAWAL OF INVALID FINDINGS

The following prior findings are **formally withdrawn** as invalid:

1. ❌ Internal references to "baseline" in observation/internal/m3_temporal.py
2. ❌ Internal references to "pressure" in observation/internal/m3_temporal.py
3. ❌ Internal method names like `_update_liveness()`, `is_warm()`, `get_baseline()`
4. ❌ Internal class name `BaselineCalculator`
5. ❌ Internal comments containing "pressure" or "liveness"
6. ❌ Internal counter dictionary keys
7. ❌ Module docstrings

These are internal computation mechanisms and do not cross external boundaries.

---

## KEY UNDERSTANDING DEMONSTRATED

**The Constitution governs what the system claims — not how it thinks.**

- ✅ Internal statistical calculations (baseline, mean, stddev) are permitted
- ✅ Internal readiness checks (is_warm, warmth) are permitted
- ✅ Internal naming (pressure, threshold, promotion) is permitted
- ❌ External UI text must not assert interpretation
- ❌ External logs must not assert activity/quality
- ❌ External field values must not assert meaning (they are already None)

**Residual violations:** 3 confirmed (window title + 2 logs) + 1 questionable (field name)

---

END OF REVISED ASSESSMENT
