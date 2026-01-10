# Loose Ends & Readiness Exposure Report — Peak Pressure System v1.0

**Date:** 2026-01-06
**System Version:** v1.0 (Frozen/Remediated)
**Scope:** Native Observability App, Collector/Detector Runtime
**Status:** **DIAGNOSTIC EXPOSURE ONLY**

---

## 1. Assessment Context

The system is currently running in **Single-Process Mode** (Native App + Internal Collector).
Behavior is observed to be functional but skeletal.
This report exposes operational friction, missing feedback loops, and potential confusion points for a human operator. It is **not** a compliance audit or a bug list.

## 2. Startup & Initialization Gaps

*   **Ambiguous "LOADING..." State:** The status bar labels initialize to "LOADING..." but immediately switch to default values. There is no visual confirmation that the collector has actually established WebSocket connections successfully (e.g., no "Connected" indicator per stream).
*   **Silent Initialization:** If the Internet is disconnected or Binance API is unreachable during startup, the UI will likely open with "Health: OK" (see Section 3) but zero data, giving no indication of the failure.
*   **Symbol List Opacity:** The UI shows "Symbols: BTCUSDT... (+5 more)". An operator cannot verify *which* 5 others are active without checking logs or waiting for events to appear in the raw feed.

## 3. Data Flow & Liveness Ambiguities

*   **Phantom "OK" Health:** The UI displays `Health: OK` by default. The system logic does not appear to actively calculate a `degraded` state based on connectivity or data stagnation. **Silence is reported as Health.**
*   **Zero Rates:** The `task.md` indicates "Calculate ingestion rates (every 1s)" is `[ ]` (unchecked). The UI expects `trades_rate`, `liquidations_rate`, etc., but if these are not computed in the collector, the Health Panel will permanently display:
    ```
    Trades rate: 0.0/s
    Liquidations rate: 0.00/min
    ```
    even when trades are visibly scrolling in the "Recent Trades" table.
    *   *Operator Risk:* Operator assumes data is broken because rates are zero, despite raw feed moving.
*   **Raw Feed vs. Processed Disconnect:** The "Recent Trades" table updates from the raw buffer. The "Events" counter updates from the detector. If the detector crashes but the collector survives (in the same process loop), the raw feed might continue while detection silently halts.

## 4. UI Semantics That May Mislead Humans

*   **"Peak Pressure Events: 0":** In a quiet market, this counter remains at 0 indefinitely. A human operator has no way to distinguish between "System Logic Broken" and "Market Quiet".
    *   *Exposure:* The "Windows" counter increments, which is the *only* heartbeat, but it's subtle.
*   **"Baselines: 5/10":** This shows readiness. However, once it hits "10/10", it provides no reassurance that baselines are *still* valid or being updated, just that they *were* ready.
*   **Empty Promoted Panel:** The message "NO PEAK PRESSURE EVENTS DETECTED... This is expected" is helpful, but static. It does not prove the detector is currently evaluating windows.

## 5. Partial or Stubbed Functionality

*   **Ingestion Rate Calculation:** appears to be unimplemented (stubbed or missing logic in `market_event_collector.py`).
    *   *Symptom:* Rate metrics in Health Panel are likely non-functional (permanently zero).
*   **Dropped Event Categorization:** The counters exist, but the visual breakdown in the Health Panel might barely move if the filters are working upstream (e.g., symbols filtered before counting).
*   **OI Polling Visibility:** Open Interest is polled every 5s. There is no UI feedback for "OI Updated" or "OI Stale".

## 6. Debuggability & Transparency Gaps

*   **Log Visibility:** The collected logs (`[TRADES] Connected...`) verify connection, but they are buried in the starting terminal. The Native UI has no "Log" tab.
*   **Snapshot Inspection:** The `debug/latest_snapshot.json` file is generated, but the Operator has to manually find and open this file to see internal state that isn't on the UI (like specific P90 thresholds).
*   **Error Hiding:** The UI's `try/except` block around snapshot reading ensures the UI doesn't crash, but it might also hide read errors, causing the UI to silently freeze its values ("Zombie UI").

## 7. Human-Friendliness Gaps (Non-Design)

*   **Anxiety of Silence:** The system is designed to be silent (Peak Pressure is rare). This creates high operator anxiety ("Is it working?").
*   **No "Last Heartbeat" Time:** The Status Bar shows data, but no explicit "Last Updated: HH:MM:SS" timestamp. If the UI thread logic freezes but the window remains responsive (unlikely in single-threaded, but possible if data stops), the operator won't know the data is stale.
*   **Cognitive Load of Tables:** The raw feed tables scroll (or replace) rapidly. Without a "Pause" button, they are inspection-only, not analysis-ready.

## 8. Summary of Loose Ends

*   **Operational:**
    *   Default "Health: OK" is misleading (No active health check).
    *   Ingestion Rates likely permanently zero (Missing calculation logic).
    *   No connectivity loss indicator.
*   **Diagnostic:**
    *   No UI-accessible logs.
    *   "Zombie UI" risk if IPC fails silently.
*   **Conceptual:**
    *   Silence (Observation) vs. failure (Broken) is indistinguishable to a casual user.

## 9. Readiness Statement

**System is architecturally promising but operationally rough.**

The core Single-Process architecture removes the major fragility of the previous web version. However, the lack of active health monitoring (rates availability, connectivity checks) and specific operator feedback mechanisms (heartbeats, connection status) makes it difficult to trust during extended unattended runs without external supervision (checking logs).
