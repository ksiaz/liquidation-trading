# FORENSIC AUDIT REPORT: METRIC WRITER EXPOSURE

**Date:** 2026-01-06  
**Auditor:** Forensic Code Auditor (Zero-Trust Mode)  
**Status:** **CRITICAL VIOLATION DETECTED**

---

## EXECUTIVE SUMMARY

**VERDICT:** **"Multiple or ungoverned metric writers exist. System state is untrusted."**

**Critical Finding:** Legacy process `market_event_collector.py` is still running (1h39m), creating DUAL WRITERS for the same metrics displayed in UI.

---

## 1. METRIC WRITER ENUMERATION

| Metric | File | Function | Line | Write Type | Layer | Status |
|--------|------|----------|------|------------|-------|--------|
| `peak_pressure_events` | `observation/internal/m3_temporal.py` | `process_trade()` | 124 | `+=` | M3 | ✅ NEW |
| `peak_pressure_events` | `scripts/peak_pressure_detector.py` | `_update_windows_processed_counter()` | 540 | assign | Legacy | ⚠️ LEGACY |
| `windows_processed` | `observation/internal/m3_temporal.py` | `_close_window()` | 157 | `+=` | M3 | ✅ NEW |
| `windows_processed` | `scripts/peak_pressure_detector.py` | `_update_windows_processed_counter()` | 539 | assign | Legacy | ⚠️ LEGACY |
| `counters.trades` | `observation/internal/m1_ingestion.py` | `normalize_trade()` | 59 | `+=` | M1 | ✅ NEW |
| `counters.liquidations` | `observation/internal/m1_ingestion.py` | `normalize_liquidation()` | 90 | `+=` | M1 | ✅ NEW |
| `ObservationStatus` | `observation/governance.py` | `_trigger_failure()` | 106 | assign | M5 | ✅ NEW |
| `ObservationStatus` | `observation/governance.py` | `_get_snapshot()` | 135 | assign | M5 | ✅ NEW |

---

## 2. SINGLE-WRITER ASSERTION RESULTS

### ❌ Q1: Does each metric have exactly one writer?
**NO** - `peak_pressure_events` and `windows_processed` have **2 writers each**

### ❌ Q2: Is that writer reachable only through M5?
**NO** - Legacy code calls `SystemState.update_staging()` directly (bypasses M5)

### ⚠️ Q3: Is that writer triggered only by explicit time advancement?
**PARTIAL** - NEW code: YES, LEGACY code: NO

### ❌ Q4: Is that writer impossible to reach from legacy code?
**NO** - Terminal evidence shows legacy process running

---

## 3. CONTRADICTIONS DETECTED

### CONTRADICTION #1: Dual State Writers
**Evidence:**
- NEW: Writes to `observation.M3TemporalEngine.stats`
- LEGACY: Writes to `scripts.system_state.SystemState`

**Impact:** Two separate state instances exist. UI may read from either or mix data unpredictably.

### OBSERVATION: Events > Windows
**Note:** Not a contradiction. M3 detects pressure on individual trades (instantaneous), not window closure. Windows increment separately when time advances. Naming is confusing but logic is correct.

---

## 4. LEGACY CONTAMINATION EVIDENCE

### Terminal Evidence
```
python market_event_collector.py (in d:\liquidation-trading\scripts, running for 1h39m)
```

### File Evidence
- `scripts/peak_pressure_detector.py:537-546` - Direct `SystemState.update_staging()` calls
- `scripts/system_state.py` - Defines duplicate counter structure
- Both old and new code define identical metric names

### Import Graph
```
market_event_collector.py (RUNNING)
  └─> imports peak_pressure_detector.py
      └─> writes to SystemState (UNGOVERNED)
```

---

## 5. REQUIRED REMEDIATION

**IMMEDIATE (Blocking Verification):**
1. **STOP legacy process:** `Ctrl+C` in terminal running `market_event_collector.py`
2. **Restart new app only:** `python runtime/native_app/main.py`
3. **Verify clean start:** Counters should start at 0

**STRUCTURAL (Before Live Run):**
1. Move `scripts/` to `archive/` or `legacy/`
2. Verify no imports of `scripts.*` exist in new code
3. Re-run this audit to confirm single-writer invariant

---

## CONCLUSION

The system **cannot pass Phase 6 Verification** while legacy process is running.
The fundamental trust property (single writer per metric) is violated.

**Next Action:** User must stop legacy process before verification can continue.
