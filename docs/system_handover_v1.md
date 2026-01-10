# System v1.0 - Authoritative Handover Documentation

## Document Purpose

This is the **single source of truth** for System v1.0 architecture, constraints, and operational behavior.

**Target Audience**: Engineers, operators, and future maintainers who need to understand what exists, why it exists, and what must never be changed casually.

**Last Updated**: 2026-01-06  
**System Status**: FROZEN (Peak Pressure logic)  
**Observability Layer**: Native App (v1.0)

---

## System Purpose

### What This System Observes

System v1.0 is a **mechanical market structure observer** that detects rare multi-stream stress coincidences in cryptocurrency futures markets.

It **observes**:
- Trade flow volume surges
- Large trade participation  
- Price compression/expansion patterns
- External stress (liquidations + open interest changes)

It **promotes** events to "Peak Pressure" status when ALL four conditions coincide within a 1-second window.

### What It Explicitly Does Not Do

❌ **No trading signals**: Peak Pressure events are NOT actionable  
❌ **No predictions**: System does not forecast future behavior  
❌ **No optimization**: No ML, no parameter tuning, no heuristics  
❌ **No execution logic**: Zero connection to order placement  
❌ **No chart analysis**: No visual patterns, no indicators  

### Why Peak Pressure Is Not a Trading Signal

**Critical Understanding**: Peak Pressure detection is **purely observational**.

- Events describe what **already happened** (past tense)
- Metadata fields (`dominant_side`, `stress_sources`) are **informational only**
- No causality is implied or inferred
- Rare by design (< 5-20 events/day under normal conditions)

**Silence is the expected state.** Most market activity does NOT meet promotion criteria.

---

## High-Level Architecture

### One-Process Design

```
Single Process (peak_pressure_system)
    ├── Collector (background threads)
    │     ├── WebSocket streams (trades, liquidations, klines)
    │     ├── OI polling (5s interval)
    │     └── Symbol filter (TOP_10 only)
    ├── Detector (deterministic, per-symbol)
    │     ├── Window aggregation (1s fixed)
    │     ├── Baseline calculation (rolling 60 windows)
    │     └── Promotion check (4 required conditions)
    ├── SystemState (double-buffered)
    │     ├── staging (write by collector/detector)
    │     ├── active (read by UI)
    │     └── commit() every 500ms
    └── Native App (PySide6, main thread)
          ├── Status bar
          ├── Health panel
          ├── Raw feed tables
          └── Promoted events panel
```

**Key Property**: No runtime dependency on HTTP, browser, or FastAPI for UI correctness.

### Data Flow

```
Market Event → Collector logs → SystemState.update_staging()
                                        ↓
                                  Every 500ms: commit()
                                        ↓
                                  Swap staging → active
                                        ↓
                            UI pulls snapshot (passive)
                                        ↓
                                  Render truth
```

**No mutations from UI. Ever.**

---

## Frozen Layers

### M1–M6 Status

| Layer | Status | Reason |
|-------|--------|--------|
| **M1**: Market Event Schema | FROZEN | Normalization contract established |
| **M2**: Trade Aggregation | FROZEN | Window boundaries deterministic |
| **M3**: Peak Pressure Logic | **FROZEN** | 4-condition promotion rule immutable |
| **M4**: Baseline Calculation | FROZEN | P90/P95 rolling windows deterministic |
| **M5**: (Reserved) | N/A | Not implemented |
| **M6**: External Policy | EXTENSIBLE | Can add predicates above M3 |

### Peak Pressure Logic Immutability

**The 4 required conditions are FROZEN**:
1. Trade flow surge (abs_flow ≥ baseline P90)
2. Large trade participation (≥ 1 trade above baseline P95)
3. Price compression OR expansion (kline body ratio)
4. External stress (liquidations in 60s window OR OI change)

**These may NOT be modified without executive approval.**

Rationale: Changing promotion rules invalidates all historical comparisons and breaks observational continuity.

### What Changes Require Re-Authorization

**Frozen (requires approval)**:
- Promotion condition logic
- Window size (1s fixed)
- Baseline period (60 windows)
- Symbol count (TOP_10 fixed)
- Percentile thresholds (P90, P95)

**Extensible (no approval needed)**:
- UI layout/colors
- Logging verbosity
- Debug output formats
- Inspection surface enhancements
- Documentation updates

---

## Native Observability App

### Why Web UI Was Removed

**Problem**: Browser-based UI introduced **systemic risk during live runs**:
- Multi-process desynchronization (collector ↔ API ↔ browser)
- File locking conflicts (FastAPI reading parquet during collector write)
- HTTP 404/500 errors blocking UI rendering
- Race conditions between ingestion and display
- Debugging friction under live market stress

**Decision**: Replace with single-process native Windows desktop app.

### Snapshot-Based Design

**Core Mechanism**: Double-buffered SystemState

```python
SystemState
    ├── _active: read by UI (frozen snapshot)
    ├── _staging: write by collector/detector (mutable)
    └── commit(): atomic swap every 500ms
```

**Rules**:
- UI reads **only** from `_active`
- Collector/Detector write **only** to `_staging`
- Commit swaps buffers atomically
- **No partial visibility, ever**

### Threading Model

| Component | Thread | Responsibilities |
|-----------|--------|------------------|
| **Collector** | Background threads | Ingest events, update staging |
| **Detector** | Deterministic (sync) | Process windows, update staging |
| **SystemState** | Class methods (locked) | Swap staging ↔ active |
| **UI** | Main Qt thread | Read active, render (passive) |

**Critical Rule**: Detector **NEVER** emits Qt signals. Detector isolated from UI.

### File Structure

```
d:/liquidation-trading/
├── scripts/
│   ├── system_state.py         # Double-buffered state
│   ├── market_event_collector.py  # Ingestion + staging updates
│   ├── peak_pressure_detector.py  # Detection + staging updates
│   └── inspection_surface.py   # Optional debug snapshots
├── native_app/
│   └── main.py                 # PySide6 desktop app
└── debug/
    └── latest_snapshot.json    # 5s dumps (inspection only)
```

---

## Symbol Isolation Rules

### TOP_10 Selection Logic

**Source**: Binance Futures 24h ticker API (`/fapi/v1/ticker/24hr`)  
**Method**: Query at startup, sort by `quoteVolume` descending, select top 10  
**Criteria**: USDT-margined perpetuals only  

**Example**:
```
1. BTCUSDT - $13.8B
2. ETHUSDT - $12.3B
3. SOLUSDT - $3.6B
...
10. ZECUSDT - $710M
```

**Immutable Until Restart**: Symbol list frozen for entire run.

### Why Symbol Creep Is Forbidden

**Rationale**: Prevents scope dilution and maintains observational consistency.

- Baselines are **symbol-scoped** (not cross-symbol)
- Adding symbols mid-run would introduce unwarmed baselines
- Removing symbols would invalidate historical promotion context
- Dynamic symbols would break determinism

**Enforcement**: Non-TOP_10 events dropped immediately, counted in `dropped_events.symbol_not_allowed`.

### How Drops Are Counted and Exposed

**Dropped Event Categories**:
- `symbol_not_allowed`: Events for non-TOP_10 symbols
- `baseline_not_ready`: Promotion failed due to baseline warmup
- `window_not_closed`: Invalid timestamp alignment
- `missing_streams`: Required stream data unavailable

**Visibility**:
- Exposed in SystemState snapshot (`counters.dropped_events`)
- Displayed in native app health panel
- Written to `debug/latest_snapshot.json` every 5s

---

## Peak Pressure Detection (Read-Only Description)

### The 4 Required Conditions

**ALL must be true for promotion** (logical AND):

1. **Trade Flow Surge**
   - `window.abs_flow ≥ baseline.get_abs_flow_p90()`
   - Measures total buy + sell volume vs rolling 60-window P90

2. **Large Trade Participation**
   - `window.large_trade_count ≥ 1`
   - At least one trade ≥ baseline trade size P95

3. **Price Compression OR Expansion**
   - `window.compressed OR window.expanded`
   - Kline body ratio thresholds (see M3 spec)

4. **External Stress Presence**
   - `(liquidations in 60s buffer) OR (OI change in window)`
   - Persistent liquidation buffer (60s retention)

**If ANY condition fails**: Event not promoted. Counters incremented for diagnosis.

### Multi-Stream Coincidence Requirement

**Key Property**: Peak Pressure events require **temporal coincidence** across independent streams.

- Trade flow (internal market activity)
- Liquidations (forced position closures)
- Klines (price action structure)
- Open Interest (derivative positioning changes)

**Rarity by Design**: This multi-stream requirement ensures < 1% of windows promote.

### Metadata Fields (Informational Only)

**Allowed Metadata**:
- `dominant_side`: "BUY" or "SELL" (based on `net_aggression` sign)
- `stress_sources`: List of ["liquidations", "oi_change"]
- `window_size`: Always 1.0s (fixed)
- `timestamp`: Window end time

**Critical Rule**: Metadata **MUST NEVER** affect promotion decisions.

These fields exist for **post-hoc analysis only**. They describe promoted events but do not influence what gets promoted.

---

## Interpreting Silence

### Why "0 Peak Pressure Events" Is Normal

**Expected Causes of Silence**:

1. **Baseline Warmup** (first 60 windows per symbol)
   - Detector cannot calculate P90/P95 without history
   - Promotions disabled until `baseline.is_warm() == True`
   - UI shows: "Baselines ready: X / 10"

2. **Normal Market Conditions**
   - Price action within baseline bounds
   - No large trades detected
   - No liquidation/OI coincidence
   - **This is healthy and expected**

3. **Missing Stream Conditions**
   - OI polling delayed (>5s timeout)
   - WebSocket reconnection in progress
   - Liquidation buffer empty (no forced closures in 60s)

### UI Empty State Messaging

When `promoted_events` list is empty, native app displays:

```
=== NO PEAK PRESSURE EVENTS DETECTED ===

This is expected during:
- Baseline warmup (X / 10 symbols ready)
- Normal market conditions
- No multi-stream coincidence
```

**This is correct behavior, not a bug.**

### When Silence Is Suspicious

**Red Flags** (investigate if all true):
- Baselines ready: 10 / 10
- Windows processed: > 1000
- Ingestion health: OK
- Promoted events: 0
- **AND** high volatility visible in raw feed

**Diagnosis**:
1. Check `counters.flow_surge_failed` (flow below P90)
2. Check `counters.large_trade_failed` (no large trades)
3. Check `counters.compression_failed` (price range normal)
4. Check `counters.stress_failed` (no liquidations/OI change)

**Most likely**: Conditions 1-3 met but no external stress (healthy market structure).

---

## Failure Modes & Recovery

### Stream Degradation

**Symptom**: `ingestion_health: DEGRADED`

**Causes**:
- WebSocket disconnection/reconnection
- High packet loss
- Binance API rate limiting

**Impact**:
- Events dropped (counted in `dropped_events`)
- Promotion decisions unaffected (windows still close deterministically)
- Raw feed may show gaps

**Recovery**: Automatic (WebSocket reconnects, OI polling retries)

### OI Polling Delay

**Symptom**: "OI Polling: DEGRADED (last update >5s ago)"

**Causes**:
- API timeout (>5s)
- Network latency spike
- Binance API degradation

**Impact**:
- `window.oi_change_present` remains `False` until data arrives
- Promotions requiring OI may fail (Condition 4)
- This is **correct behavior** (no OI change if no data)

**Recovery**: Polling continues every 5s. No manual intervention needed.

### Restart Procedure

**Clean Shutdown**:
1. Close native app (window X button)
2. Ctrl+C in collector terminal
3. Wait for "Application shutdown complete"

**Restart**:
1. `cd d:\liquidation-trading\scripts`
2. `python market_event_collector.py`
3. Wait for `[NATIVE APP] SystemState initialized with TOP_10 symbols`
4. `cd d:\liquidation-trading\native_app`
5. `python main.py`

**Expected Behavior**:
- Native app shows "LOADING..." initially
- Status bar populates within 1-2 seconds
- Baselines warmup from 0/10 → 10/10 over ~60 seconds
- Raw feed tables populate immediately

### Health Verification Post-Restart

**Checklist**:
- [ ] Status bar shows "Mode: LIVE_PEAK_PRESSURE"
- [ ] Symbols list shows 10 symbols
- [ ] Baselines counter increments (X / 10)
- [ ] Windows processed counter increments
- [ ] Raw feed tables populate (trades + liquidations)
- [ ] Ingestion health: OK or STARTING
- [ ] No console errors about file locking

**Debug Snapshot Check**:
```powershell
Get-Content d:\liquidation-trading\debug\latest_snapshot.json
```

Should show `timestamp` updating every 5 seconds.

---

## Non-Goals (Hard Constraints)

### Prohibited Features

The following are **explicitly forbidden** without executive re-authorization:

❌ **Charts/Graphs**
- No candlestick charts
- No volume histograms  
- No trend lines
- Rationale: Adds interpretation layer, violates "render truth" mandate

❌ **Predictions/Forecasts**
- No ML models
- No regression analysis
- No "next window" estimates
- Rationale: System observes past, never predicts future

❌ **Heuristics**
- No fuzzy logic
- No probabilistic thresholds
- No adaptive parameters
- Rationale: Breaks determinism, invalidates historical comparison

❌ **Execution Logic**
- No order placement
- No position sizing
- No risk management
- Rationale: System is observational only

❌ **Optimization**
- No parameter tuning
- No backtesting modifications to improve "event count"
- No threshold adjustments to "reduce false positives"
- Rationale: There are no "false positives" - events are mechanical observations

### Design Rationale

**Core Philosophy**: The system **renders truth** about market structure.

- Adding predictions would introduce bias
- Adding optimization would corrupt observational integrity
- Adding execution would create feedback loops

**If you want trading logic, build it as a separate layer (M6+) that consumes Peak Pressure observations as inputs.**

**Do not modify M3.**

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-01-06 | Native app implementation complete, web UI deprecated |
| v0.9 | 2025-12-XX | Peak Pressure logic frozen (M3) |
| v0.8 | 2025-11-XX | Symbol isolation (TOP_10 lockdown) |

---

## Contact & Escalation

**For system issues**:
- Check `debug/latest_snapshot.json` first
- Review collector console output
- Verify ingestion health in native app

**For frozen layer modification requests**:
- Document exact proposed change
- Justify why change is necessary
- Provide impact analysis on historical data
- Await executive approval before implementing

**This system is FROZEN by design. Stability > features.**
