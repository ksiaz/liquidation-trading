# PROMPT 1: M1–M5 Wiring Audit Report (FORENSIC)

**Date:** 2026-01-06
**Auditor:** Forensic Audit Agent
**Scope:** `scripts/` and `native_app/`
**Status:** **CRITICAL VIOLATIONS DETECTED**

---

## 1. File Layer Mapping & Classification

| File Path | Component / Function | Claimed Layer | Actual Behavior (Audit) | Status |
|-----------|----------------------|---------------|-------------------------|--------|
| `scripts/market_event_collector.py` | `MarketEventLogger` | **M1** (Ingestion) | **M1 + M5 + IO**<br>- Normalizes data (M1)<br>- Filters symbols (M5/Governance)<br>- Broadcasts to UI (IO)<br>- Writes Parquet (Persistence) | **HYBRID** |
| `scripts/system_state.py` | `SystemState` | **M5** (Governance) | **Global Mutable State**<br>- Stores Raw Buffers (M1)<br>- Stores Metrics (M4)<br>- Uses `threading.Lock` (Concurrency)<br>- **Not Governance** (No query validation) | **ILLEGAL** |
| `scripts/trade_promoter.py` | `TradePromoter` | **M3** (Temporal) | **M3 + M4 + Clock**<br>- Windowing (M3)<br>- Statistical Baseline (M4)<br>- `time.time()` for rates (Clock Violation) | **HYBRID** |
| `scripts/live_ghost_monitor.py` | `LiveGhostMonitor` | **M2** (Continuity) | **M1 + Execution**<br>- Captures snapshots (M1)<br>- Imports `GhostExchangeAdapter` (Execution!)<br>- Infinite loop with `sleep` (Runtime) | **ILLEGAL** |
| `native_app/main.py` | `ObservabilityApp` | **UI** (Center) | **M4 Consumer**<br>- Reads `SystemState`<br>- Renders State<br>- compliant as view only | **PASS** |

---

## 2. Implicit Clock Usage & Side Effects

The **"No System Clock Usage" (Rule 4.3)** is universally violated.

### A. Implicit Time (`time.time()` / `datetime.now()`)
*   **`scripts/system_state.py`**:
    *   L143: `timestamp=time.time()` in `_get_default_snapshot` (State creation relies on wall clock).
    *   L131: `timestamp=time.time()` in docstring example (encouraged usage).
*   **`scripts/market_event_collector.py`**:
    *   L379: `timestamp=time.time()` in `write_runtime_stats`.
    *   L332/L355: `timestamp=time.time()` in `_sync_raw_buffers_to_state`.
*   **`scripts/trade_promoter.py`**:
    *   L50: `last_reset_time = field(default_factory=time.time)`.
    *   L62: `elapsed = time.time() - self.last_reset_time`. **CRITICAL:** Rate calculation depends on wall clock, not event time.
*   **`scripts/live_ghost_monitor.py`**:
    *   L106: `start_time = time.time()`.
    *   L115: `current_time = time.time()`.
    *   L132: `time.sleep(SNAPSHOT_INTERVAL)`.

### B. Global/Shared State Mutation
*   **`scripts/system_state.py`**:
    *   `_active` and `_staging` are **Global Class Variables**.
    *   Any import of `SystemState` shares this memory.
    *   Violates "Stateless Read Models" (Rule 4.1) because the *model* itself (SystemState) is a mutable singleton.

---

## 3. Explicit Violations of System Guidance

### Violation 1: Conflation of Observation and Execution
**File:** `scripts/live_ghost_monitor.py`
**Evidence:** Imports `execution.ep4_ghost_adapter`.
**Verdict:** The "Monitor" (Observation) is directly driving "Ghost Execution". This breaches the "Observation is Read-Only" contract.

### Violation 2: M5 is Missing / Misidentified
**File:** `scripts/system_state.py`
**Evidence:** Claims to be "SystemState" but performs **Zero Query Validation**.
**Verdict:** Real M5 (Governance/Epistemic Safety) does not exist in the audited code. `SystemState` is just a data bag. There is no layer rejecting `{"sort_by": "strength"}`.

### Violation 3: M1 Performing Governance
**File:** `scripts/market_event_collector.py`
**Evidence:** `if symbol not in TOP_10_SYMBOLS: return`.
**Verdict:** Ingestion Layer (M1) is hard-coded to reject data based on business logic (Whitelist), bypassing M5.

### Violation 4: Non-Deterministic Metrics
**File:** `scripts/trade_promoter.py`
**Evidence:** `get_rates()` uses `time.time()`.
**Verdict:** If you replay the same data twice at different speeds, the "Rates" metric will change. **Violates Determinism (4.2).**

---

## 4. Conclusion

The "Memory-Centric Market Observation System" currently exists only as **Intent**, not **Implementation**.
Current implementation is a **Hybrid Real-Time App** pattern:
1.  Ingest Data (Filtered)
2.  Update Mutable Global Singleton (`SystemState`)
3.  Update Wall-Clock Metrics
4.  Render UI

**Architecture Status:** **UNTRUSTED**
**Recommendation:** Proceed to Phase 2 (Isolation).
