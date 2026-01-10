# Peak Pressure System v1.0 - Strict Conformance Verification Report

**Date:** 2026-01-06
**System:** Peak Pressure Detection System v1.0
**Verification Scope:** Frozen Documentation vs. Implemented Codebase
**Status:** **NON-COMPLIANT**

---

## 1. Verification Scope & Methodology

Verification was performed strictly against the following authoritative frozen documents:
1.  `docs/system_handover_v1.md` (System Architecture & Logic)
2.  `docs/live_run_guidance.md` (Operational Procedures)
3.  `docs/observability_ui_reference.md` (UI Semantics)

**Methodology:**
- **Compliance** is defined as exact alignment between documented requirements and implementation behavior.
- **Non-Compliance** is any deviation, regardless of technical merit or fix stability.
- No "implied" or "experiential" compliance is accepted.

---

## 2. System Identity Verification

| Attribute | Documented | Observed | Status |
|-----------|------------|----------|--------|
| **System Name** | Peak Pressure Detection System v1.0 | Peak Pressure Observability - System v1.0 FROZEN | **PASS** |
| **Logic Status** | FROZEN (M3) | M3 Logic Implemented & Frozen | **PASS** |
| **Layer Isolation** | No M1-M5/M6 dependencies | Logic contained in `scripts/` | **PASS** |

**Identity Verdict: COMPLIANT**

---

## 3. Architecture Conformance

**Documented Requirement:**
> "Single Process (peak_pressure_system) ... Native App (PySide6, main thread)" [`system_handover_v1.md`:55]
> "UI reads ONLY from SystemState.get_snapshot()" [`system_handover_v1.md`:163]
> "latest_snapshot.json # 5s dumps (inspection only)" [`system_handover_v1.md`:191]

**Observed Implementation:**
- **Split-Process Architecture**: The system operates as two distinct OS processes:
    1.  `python market_event_collector.py` (Collector/Detector)
    2.  `python main.py` (UI)
- **File-Based IPC**: The UI reads data exclusively from `debug/latest_snapshot.json`.
- **Snapshot Role**: The snapshot file is the **primary data transport**, not an inspection-only sidecar.

**Deviation Analysis:**
The implementation fundamentally diverges from the "Single Process" specification in `system_handover_v1.md`. While `live_run_guidance.md` correctly instructs running two commands, the architectural definition is violated.

**Architecture Verdict: FAIL**

---

## 4. Detection Logic (M3) Conformance

**Documented Requirement:**
> "The 4 required conditions are FROZEN: 1. Trade flow surge... 2. Large trade participation... 3. Price compression OR expansion... 4. External stress" [`system_handover_v1.md`:110]

**Observed Implementation:**
(`scripts/peak_pressure_detector.py`)
1.  `if window.abs_flow < abs_flow_p90: return None` (Matches Rule 1)
2.  `if window.large_trade_count < 1: return None` (Matches Rule 2)
3.  `if not (window.compressed or window.expanded): return None` (Matches Rule 3)
4.  `if not (has_retained_liquidation or window.oi_change_present): return None` (Matches Rule 4)

**Logic Verdict: PASS**

---

## 5. Temporal & Baseline Semantics

**Documented Requirement:**
> "Warmup Requirement: Need ≥60 windows before P90/P95 are statistically valid" [`system_handover_v1.md`:296]

**Observed Implementation:**
(`scripts/peak_pressure_detector.py`:153)
```python
def is_warm(self) -> bool:
    """Check if baseline has enough data."""
    return len(self.abs_flow_history) >= 10  # AND trade_size_history >= 10
```
The code enables promotion after only **10 windows** (10 seconds), whereas the documentation mandates **60 windows** (60 seconds).

**Temporal Verdict: FAIL**

---

## 6. Symbol Scope & Isolation

**Documented Requirement:**
> "TOP_10 Selection Logic... Non-TOP_10 events dropped immediately" [`system_handover_v1.md`:224]

**Observed Implementation:**
- `market_event_collector.py` imports `TOP_10_SYMBOLS`.
- Explicit `if symbol not in TOP_10_SYMBOLS: return` checks in all ingestion points.
- `Symbol not allowed` counter implemented and incrementing.

**Symbol Verdict: PASS**

---

## 7. Observability & UI Conformance

**Documented Requirement:**
> "UI reads only from _active" [`system_handover_v1.md`:163]
> "Status bar semantics... Health indicators... Empty-state messaging"

**Observed Implementation:**
- UI visually matches `observability_ui_reference.md` exactly.
- However, UI reads from disk (`debug/latest_snapshot.json`), which technically violates the "reads from _active" memory contract of the single-process model.
- Visual content is Compliant. Data path is Non-Compliant (see Architecture).

**UI Visual Verdict: PASS**

---

## 8. Non-Goals Enforcement

**Verification:**
- **Trading**: No order execution code found. **PASS**
- **Prediction**: No forecasting logic found. **PASS**
- **Optimization**: No backtesting or parameter tuning modules found. **PASS**
- **ML**: No machine learning libraries (torch, tensorflow, sklearn) imported. **PASS**
- **Charts**: No charting libraries (matplotlib, plotly) used in UI. **PASS**

**Non-Goals Verdict: FULLY COMPLIANT**

---

## 9. Final Compliance Verdict

**VERDICT: NON-COMPLIANT (WITH FAILURES)**

The Peak Pressure System v1.0 logic and visual layer are correct, but the **Implementation Architecture** and **Baseline Configuration** violate the Authoritative Documentation.

**Specific Failures:**
1.  **Architecture**: Implementation is Multi-Process (File IPC); Documentation specifies Single-Process (Memory IPC).
2.  **Baseline Warmup**: Code uses 10-window threshhold; Documentation requires 60-window threshold.

**Recommendation:**
The system is operationally stable but technically non-compliant with its specification documents. Either the documentation must be updated to reflect the operational reality (Split-Process + 10s warmup), or the code must be patched to match the constraints.
