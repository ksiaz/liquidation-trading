# Peak Pressure Detection System - v1.0

## Overview

**System v1.0** is a mechanical market structure observer for cryptocurrency futures markets. It detects rare multi-stream stress coincidences called "Peak Pressure events."

**This system observes market structure. It does not trade, predict, or generate signals.**

---

## Quick Start

### Prerequisites

```powershell
# Install Python dependencies
pip install PySide6 pandas websockets requests

# Verify installation
python --version  # Should be 3.9+
```

### Launch System

**Step 1: Start Collector**

```powershell
cd scripts
python market_event_collector.py
```

Wait for: `[NATIVE APP] SystemState initialized with TOP_10 symbols`

**Step 2: Launch Native Observability App**

```powershell
cd native_app
python main.py
```

Window opens (1600×1000) showing live market data.

---

## Architecture

### Single-Process Design

```
Peak Pressure System (one process)
├── Collector (background threads)
│   ├── Trade stream (WebSocket)
│   ├── Liquidation stream (WebSocket)
│   ├── Kline stream (WebSocket, 1s)
│   └── Open Interest (HTTP poll, 5s)
├── Detector (deterministic)
│   ├── Window aggregation (1s fixed)
│   ├── Baseline calculation (rolling 60)
│   └── Promotion check (4 required conditions)
├── SystemState (double-buffered)
│   ├── staging (write)
│   ├── active (read)
│   └── commit() every 500ms
└── Native App (PySide6, read-only UI)
    ├── Status bar
    ├── System health panel
    ├── Raw market feed
    └── Promoted events
```

**Key Property**: No browser, no FastAPI runtime dependency for UI.

---

## What System v1.0 Guarantees

✅ **Deterministic observation**: Same data → same promoted events  
✅ **Symbol isolation**: TOP_10 only, resolved at startup  
✅ **Frozen detection logic**: M3 Peak Pressure rules immutable  
✅ **Event rarity**: < 5-20 events/day under normal conditions  
✅ **Silence is valid**: Zero events may be correct (explained in UI)  
✅ **No predictions**: System describes past, never forecasts future  

---

## Documentation

### For Operators

- **[Live Run Guidance](docs/live_run_guidance.md)**: How to start, monitor, and interpret system behavior
- **[Observability UI Reference](docs/observability_ui_reference.md)**: What each UI panel means

### For Engineers

- **[System Handover v1.0](docs/system_handover_v1.md)**: Authoritative architecture, frozen layers, constraints
- **[Native App Plan](native_app_plan.md)**: Implementation details for PySide6 app

### Legacy (Deprecated)

- **[Web UI README](ui/README.md)**: Old browser-based interface (replaced by native app)

---

## System Status

| Component | Status | Version | Notes |
|-----------|--------|---------|-------|
| **Peak Pressure Logic** | FROZEN | M3 | Immutable without approval |
| **Native Observability App** | ACTIVE | v1.0 | Primary interface |
| **Web UI** | DEPRECATED | - | Replaced Jan 2026 |
| **Baseline Calculation** | FROZEN | M4 | 60-window rolling P90/P95 |
| **Symbol Scope** | FROZEN | TOP_10 | Binance Futures 24h volume |

---

## Non-Goals (Explicit)

This system **does NOT**:

❌ Generate trading signals  
❌ Provide entry/exit recommendations  
❌ Predict future price movements  
❌ Execute trades  
❌ Optimize for event count  
❌ Include charts, indicators, or ML  

**Peak Pressure events are observational data, not actionable signals.**

---

## Understanding Silence

### Why "0 Events" Is Normal

**Peak Pressure requires ALL 4 conditions simultaneously**:
1. Trade flow surge (≥ baseline P90)
2. Large trade participation (≥ 1 trade above P95)
3. Price compression OR expansion
4. External stress (liquidations OR open interest change)

**Multi-stream coincidence is rare by design.**

Most market activity does NOT meet promotion criteria. This is expected.

### When to Investigate

**If all true for > 2 hours**:
- Baselines ready: 10 / 10 ✅
- Windows processed: > 1000 ✅  
- Ingestion health: OK ✅
- High volatility visible in raw feed ✅
- **AND** promoted events: 0

**Then**: Check `debug/latest_snapshot.json` → `counters` to see which condition fails most.

**Most likely**: `stress_failed` (no liquidations/OI coinciding with flow surge).

---

## Key Files

### Core System

```
scripts/
├── market_event_collector.py   # Ingestion engine
├── peak_pressure_detector.py   # Detection logic (FROZEN)
├── system_state.py              # Double-buffered state
├── symbol_config.py             # TOP_10 resolution
└── inspection_surface.py        # Debug snapshots

native_app/
└── main.py                      # PySide6 desktop app

debug/
└── latest_snapshot.json         # 5s state dumps (inspection)
```

### Data Outputs

```
data/v1_live_validation/
├── market_events/
│   └── market_events.parquet    # Normalized events archive
└── runtime_stats/
    └── collector_stats.json     # Ingestion metrics (IPC)
```

---

## Frozen Layers (Do Not Modify)

| Layer | What's Frozen | Why |
|-------|---------------|-----|
| **M3** | Peak Pressure promotion rules | Observational continuity |
| **Baseline** | 60-window rolling P90/P95 | Statistical validity |
| **Symbols** | TOP_10 (per run) | Scope discipline |
| **Windows** | 1s fixed size | Temporal determinism |

**Changing these requires executive approval.**

---

## Troubleshooting

### Collector won't start

```powershell
# Check if another instance is running
tasklist | findstr python

# Kill if needed
taskkill /F /IM python.exe

# Remove temp files
cd data\v1_live_validation\market_events
Remove-Item *.tmp
```

### Native app shows "LOADING..."

**Cause**: SystemState not initialized (collector not running or failed).

**Fix**: Start collector first, wait for "SystemState initialized" message.

### Baselines stuck at X/10 after 15 min

**Cause**: Some symbols not receiving stream data.

**Fix**:
1. Check System Health panel for degraded streams
2. Restart collector (baselines reset to 0/10)

### Zero events after 1 hour

**This is probably correct.** Check `debug/latest_snapshot.json`:

```powershell
Get-Content debug\latest_snapshot.json
```

Look at `counters` → `flow_surge_failed`, `stress_failed` etc. to see why.

---

## Contact & Support

**Before reporting issues**:
1. Check `debug/latest_snapshot.json` for system state
2. Verify ingestion health in native app
3. Read [Live Run Guidance](docs/live_run_guidance.md)

**For frozen layer modifications**:
- Document proposed change
- Justify necessity
- Analyze historical data impact
- Request executive approval

**This system is frozen by design. Stability > features.**

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **v1.0** | 2026-01-06 | Native app complete, web UI deprecated |
| v0.9 | 2025-12-XX | Peak Pressure logic frozen (M3) |
| v0.8 | 2025-11-XX | Symbol isolation (TOP_10) implemented |

---

## License & Usage

**Internal Research Use Only**

This system observes cryptocurrency futures markets for research purposes. It does not provide investment advice, trading signals, or financial recommendations.

**Peak Pressure events describe past market structure. They are not predictions.**
