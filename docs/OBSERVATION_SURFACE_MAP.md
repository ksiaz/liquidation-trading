# OBSERVATION SURFACE MAP

**Date:** 2026-01-06 13:23:00  
**Type:** Census (No Analysis)  
**Source:** ObservationSnapshot, UI Renderer, M5 Query

---

## FLAT TABLE: ALL EXPOSED OBSERVABLES

| Name | Display Location | Data Type | Update Frequency | Semantic Meaning |
|------|-----------------|-----------|------------------|------------------|
| **status** | UI (color + text) | `ObservationStatus` (enum) | 250ms | System operational state |
| **timestamp** | UI (text) | `float` | 250ms | Internal system clock (seconds since epoch) |
| **symbols_active** | Snapshot only | `List[str]` | 250ms | Whitelist of tracked symbols |
| **windows_processed** | UI (text) | `int` | Per window close (~1s) | Count of closed 1-second aggregation windows |
| **peak_pressure_events** | UI (text) | `int` | Per trade (if promoted) | Count of trades exceeding baseline threshold |
| **dropped_events.errors** | Snapshot only | `int` | Per normalization error | Count of M1 normalization failures |
| **dropped_events.rejected_pressure** | Snapshot only | `int` | Per trade (if rejected) | Count of trades failing promotion criteria |
| **ingestion_health.trades_rate** | Snapshot only | `float` | Not calculated (stub=0) | Trades per second |
| **ingestion_health.liquidations_rate** | Snapshot only | `float` | Not calculated (stub=0) | Liquidations per second |
| **ingestion_health.klines_rate** | Snapshot only | `float` | Not calculated (stub=0) | Klines per second |
| **ingestion_health.oi_rate** | Snapshot only | `float` | Not calculated (stub=0) | Open Interest updates per second |
| **ingestion_health.degraded** | Snapshot only | `bool` | Not calculated (stub=False) | Whether ingestion is degraded |
| **ingestion_health.degraded_reason** | Snapshot only | `str` | Not calculated (stub="") | Reason for degradation |
| **baseline_status.ready_symbols** | Snapshot only | `int` | Per baseline warmup (~10s) | Count of symbols with warm baseline |
| **baseline_status.total_symbols** | Snapshot only | `int` | Constant | Total symbols in whitelist |
| **promoted_events** | Snapshot only | `List[Dict]` | Per promotion | List of promoted trade events (full detail) |

---

## INTERNAL OBSERVABLES (Not Exposed via Snapshot)

| Name | Location | Data Type | Update Frequency | Semantic Meaning |
|------|----------|-----------|------------------|------------------|
| **_system_time** | M5 internal | `float` | 100ms (clock driver) | Internal time state |
| **_status** | M5 internal | `ObservationStatus` | On invariant change | Internal status before liveness check |
| **_failure_reason** | M5 internal | `str` | On FAILED trigger | Reason for system halt |
| **_m1.counters.trades** | M1 internal | `int` | Per trade | Raw trade count |
| **_m1.counters.liquidations** | M1 internal | `int` | Per liquidation | Raw liquidation count |
| **_m1.counters.klines** | M1 internal | `int` | Per kline | Raw kline count |
| **_m1.counters.oi** | M1 internal | `int` | Per OI update | Raw OI update count |
| **_m1.counters.errors** | M1 internal | `int` | Per error | M1 normalization error count |
| **_m3.stats.windows_processed** | M3 internal | `int` | Per window close | Internal window counter |
| **_m3.stats.peak_pressure_events** | M3 internal | `int` | Per promotion | Internal promotion counter |
| **_m3.stats.rejected_count** | M3 internal | `int` | Per rejection | Internal rejection counter |
| **_m3._baseline.window_sizes** | M3 internal | `deque` | Per window close | Rolling window sizes for baseline |
| **_m3._promoted_events** | M3 internal | `List` | Per promotion | Internal promoted event buffer |

---

## UI-ONLY OBSERVABLES

| Name | Display Location | Data Type | Update Frequency | Semantic Meaning |
|------|-----------------|-----------|------------------|------------------|
| **Background Color** | UI (stylesheet) | Color code | 250ms | Visual status indicator (Blue=SYNCING, Gray=STALE, Normal=OK) |
| **Status Text** | UI (label) | `str` | 250ms | Human-readable status description |
| **Red Screen** | UI (widget) | Widget visibility | On FAILED | Critical failure display |

---

## UPDATE FREQUENCY KEY

- **100ms**: Clock driver (advance_time)
- **250ms**: UI polling interval
- **~1s**: Window closure (M3 temporal)
- **Per event**: Triggered by incoming data
- **Not calculated**: Placeholder values (0/False/"")

---

## NOTES

1. `ingestion_health.*_rate` fields are currently **stubs** (hardcoded to 0)
2. `promoted_events` is a full list (unbounded growth potential)
3. `status` has **derived logic** (computed from internal state + wall clock lag)
4. All snapshot fields are **immutable** (frozen dataclass)

---

## END OF CENSUS
