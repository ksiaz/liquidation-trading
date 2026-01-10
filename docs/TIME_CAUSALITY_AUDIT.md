# TIME & CAUSALITY AUDIT REPORT

**Date:** 2026-01-06 13:26:40  
**Type:** Time Source & Causality Integrity Audit  
**Scope:** Full Codebase (Focus: observation/ and runtime/)

---

## EXECUTIVE SUMMARY

**Time Sources Found in NEW Code:** 5 locations  
**Time Sources Found in LEGACY Code:** 300+ locations  
**Critical Violations:** 0  
**Minor Violations:** 1

**Verdict:** ✅ **observation/ is DETERMINISTIC** | ⚠️ **runtime/ has acceptable wall-clock dependency**

---

## TIME SOURCE INVENTORY

### NEW CODE (observation/ + runtime/)

| File | Function | Line | Time Source | Type | Injected/Sampled | Severity |
|------|----------|------|-------------|------|------------------|----------|
| `observation/governance.py` | `_get_snapshot()` | 127 | `time.time()` | Wall clock read | **SAMPLED** | ⚠️ MINOR |
| `runtime/collector/service.py` | `_drive_clock()` | 57 | `time.time()` | Wall clock read | **SAMPLED** | ✅ OK |
| `runtime/collector/service.py` | `_run_binance_stream()` | 100 | `time.time()` | Fallback timestamp | **SAMPLED** | ✅ OK |
| `runtime/collector/service.py` | `_drive_clock()` | 64 | `asyncio.sleep(0.1)` | Timer | N/A | ✅ OK |
| `runtime/collector/service.py` | `_run_binance_stream()` | 111 | `asyncio.sleep(1)` | Error backoff | N/A | ✅ OK |
| `runtime/native_app/main.py` | `__init__()` | 70-72 | `QTimer()` | UI refresh (250ms) | N/A | ✅ OK |

---

### TIMESTAMP ORIGIN ANALYSIS (observation/)

| Source | File | Line | Origin | Injected? | Causality Preserved? |
|--------|------|------|--------|-----------|---------------------|
| **Trade Timestamp** | `m1_ingestion.py` | 42 | `payload['T']` (Binance) | ✅ YES | ✅ YES |
| **Liquidation Timestamp** | `m1_ingestion.py` | 76 | `payload['E']` (Binance) | ✅ YES | ✅ YES |
| **System Time** | `governance.py` | 81 | `advance_time(new_timestamp)` parameter | ✅ YES | ✅ YES |

**All observation timestamps are INJECTED from external sources.** ✅

---

## DETERMINISM ANALYSIS BY COMPONENT

### ✅ observation/ - **DETERMINISTIC**

**Time Sources:** 1 (wall clock read for liveness check)

**Analysis:**
- `time.time()` at line 127 in `_get_snapshot()` is used ONLY for **liveness check**
- This is **read-only** and does NOT affect metric values
- It computes `lag = wall_clock - self._system_time`
- The lag check determines `ObservationStatus.STALE` vs `OK`
- **Causality:** Preserved (status is derived, not mutated state)
- **Replay:** Deterministic IF `_system_time` is replayed correctly

**Verdict:** ✅ **PASS** - Deterministic core logic

**Replay Determinism:**
- ✅ **YES** - IF time is injected via `advance_time()` during replay
- ⚠️ **PARTIAL** - Status (STALE vs OK) depends on wall clock during query
  - This is **acceptable** for liveness semantics
  - STALE status is a **real-time assertion**, not a data property

---

### ✅ runtime/collector/ - **ACCEPTABLE NON-DETERMINISM**

**Time Sources:** 4 (2x wall clock reads, 2x async sleeps)

**Analysis:**
- `time.time()` in `_drive_clock()` (line 57): **Expected** - This IS the clock source
- `time.time()` in `_run_binance_stream()` (line 100): Fallback if payload lacks timestamp
- `asyncio.sleep(0.1)`: Clock drive interval (100ms heartbeat)
- `asyncio.sleep(1)`: Error backoff delay

**Causality:** Preserved (time flows forward, injected into observation)

**Replay:** **NOT DETERMINISTIC** (but not required)
- Runtime is the **driver**, not the **logic**
- For replay, substitute `CollectorService` with a **replay driver**
- The observation/ core remains deterministic

**Verdict:** ✅ **PASS** - Acceptable runtime behavior

---

### ✅ runtime/native_app/ - **UI REFRESH (NON-DETERMINISTIC BY DESIGN)**

**Time Sources:** 1 (QTimer 250ms)

**Analysis:**
- `QTimer` triggers UI updates every 250ms
- This is a **display concern**, not a logic concern
- Does not affect observation state

**Verdict:** ✅ **PASS** - UI refresh is acceptable

---

## LEGACY CODE CONTAMINATION

**Time Sources in scripts/:** 300+ locations

**Examples:**
- `scripts/peak_pressure_detector.py`: `import time` (NO uses in pressuredet logic)
- `scripts/market_event_collector.py`: `time.time()` for logging timestamps
- `scripts/system_state.py`: `import time` (not used in state mutations)

**Impact:** ❌ **NONE** (legacy code unreachable per PROMPT 0)

---

## IMPLICIT CLOCK DETECTION

### Window Closures (M3)

**Location:** `observation/internal/m3_temporal.py`, `_manage_windows()`  
**Line:** 145-147

**Mechanism:**
```python
while current_ts >= self._current_window_start + self._window_seconds:
    self._close_window()
    self._current_window_start += self._window_seconds
```

**Analysis:**
- Windows close based on **event timestamp** (current_ts)
- Window duration = 1 second (configurable)
- **NOT an implicit clock** - Driven by injected timestamps

**Verdict:** ✅ **DETERMINISTIC**

---

### Baseline Calculation (M3)

**Location:** `observation/internal/m3_temporal.py`, `BaselineCalculator`

**Mechanism:**
- Rolling deque of window sizes (lookback=60)
- No time-based expiration
- **NOT an implicit clock** - Driven by window count

**Verdict:** ✅ **DETERMINISTIC**

---

## CAUSALITY PRESERVATION CHECK

| Component | Causality Rule | Enforced? | Evidence |
|-----------|----------------|-----------|----------|
| **M1 Ingestion** | Timestamps from payload | ✅ YES | Lines 42, 76 |
| **M3 Temporal** | No backward time | ✅ YES | `_manage_windows()` uses event ts |
| **M5 Governance** | Monotonic time | ✅ YES | Line 76-79 (regression check) |
| **Runtime Driver** | Forward-only clock | ✅ YES | `advance_time()` only increases |

**All causal chains preserved.** ✅

---

## REPLAY DETERMINISM VERDICT

### Can replay produce identical results?

**Component-Level Analysis:**

| Component | Replay Deterministic? | Requirements |
|-----------|----------------------|--------------|
| **M1 Ingestion** | ✅ YES | Replay events in order with original timestamps |
| **M3 Temporal** | ✅ YES | Replay timestamps trigger same window closures |
| **M5 Governance** | ⚠️ PARTIAL | Liveness check depends on replay wall-clock |
| **Runtime Driver** | ❌ NO (not needed) | Replace with replay driver |

**Overall Verdict:** ✅ **YES** - Observation core is replay-deterministic

**Caveats:**
1. `ObservationStatus.STALE` may differ between replay and original run (acceptable)
2. Must use replay driver instead of live runtime
3. Must inject same timestamps in same order

---

## SEVERITY CLASSIFICATION

### ⚠️ MINOR VIOLATIONS

| Violation | Location | Severity | Impact | Acceptable? |
|-----------|----------|----------|--------|-------------|
| Wall clock read in query | `governance.py:127` | **MINOR** | Status=STALE vs OK | ✅ YES |

**Justification:**
- Liveness is a **real-time property**, not a data property
- STALE status is **informational**, not operational
- Does not affect metric values or event detection

### ✅ NO CRITICAL VIOLATIONS

---

## RECOMMENDATIONS

### 1. Replay Mode Support (Future)
Add optional `replay_mode` flag to `ObservationSystem`:
```python
def __init__(self, allowed_symbols, replay_mode=False):
    self._replay_mode = replay_mode
```

If `replay_mode=True`, skip wall clock check in `_get_snapshot()`.

### 2. Document Time Sources
Add docstring to `advance_time()`:
```
This is the ONLY way time advances in  the observation system.
All temporal logic reacts to this injected timestamp.
```

### 3. Legacy Cleanup
Move `scripts/` to `archive/` to prevent accidental imports.

---

## FINAL VERDICT

**Determinism:** ✅ **ENFORCED** in observation/ core  
**Causality:** ✅ **PRESERVED** across all layers  
**Replay:** ✅ **DETERMINISTIC** with replay driver

**System Status:** **TRUSTED** for time & causality integrity.

---

## TIME SOURCE SUMMARY TABLE

| Layer | Time Source | Count | Purpose | Deterministic? |
|-------|-------------|-------|---------|----------------|
| **M1** | Payload extraction | 2 | Event timestamps | ✅ YES |
| **M3** | None (uses M1) | 0 | Temporal logic | ✅ YES |
| **M5** | Wall clock (liveness) | 1 | Staleness check | ⚠️ PARTIAL |
| **Runtime** | Wall clock | 2 | Clock driver | ❌ NO (expected) |
| **UI** | QTimer | 1 | Refresh rate | ❌ NO (expected) |

**Total NEW code:** 6 time sources  
**Critical for observation logic:** 2 (payload timestamps - both injected)
