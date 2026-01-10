# Live Run Guidance - System v1.0

## Purpose

This guide explains how to run System v1.0 live without misinterpreting normal behavior.

**Target Audience**: Operators, researchers, and anyone monitoring live market runs.

---

## Startup Checklist

### Prerequisites

✅ Python 3.9+ installed  
✅ PySide6 installed (`pip install PySide6`)  
✅ Network connectivity to Binance Futures API  
✅ No other processes using ports 8000-8001 (if web UI fallback needed)  

### Step 1: Start Collector

```powershell
cd d:\liquidation-trading\scripts
python market_event_collector.py
```

**Expected Output**:
```
================================================================================
MARKET EVENT COLLECTOR - Peak Pressure Infrastructure
================================================================================
Symbol Scope: TOP_10 (hard-coded allowlist)
Symbols: BTCUSDT, ETHUSDT, SOLUSDT, ...
Output: d:\liquidation-trading\data\v1_live_validation\market_events
Streams: Trades, Liquidations, Klines (1s), OI (5s poll)
================================================================================

[SYMBOL CONFIG] Fetched TOP 10 symbols by 24h volume:
  1. BTCUSDT - $13.8B
  2. ETHUSDT - $12.3B
  ...

[NATIVE APP] SystemState initialized with TOP_10 symbols
```

**Wait for**: "SystemState initialized" message before launching UI.

### Step 2: Launch Native App

```powershell
cd d:\liquidation-trading\native_app
python main.py
```

**Expected Output**:
```
================================================================================
NATIVE WINDOWS OBSERVABILITY APP - Peak Pressure System v1.0
================================================================================
Mode: LIVE (Read-Only)
Refresh: 500ms passive snapshot pull
================================================================================

[NATIVE APP] Window initialized. Refresh: 500ms
```

**Window should open** (1600x1000) and populate within 2 seconds.

### Step 3: Verify System Health

Check native app status bar:
- Mode: LIVE_PEAK_PRESSURE ✅
- Symbols: BTCUSDT, ETHUSDT, ... (10 total) ✅
- Baselines: 0 → 10 / 10 (increments over 60s) ✅
- Health: STARTING → OK ✅
- Windows: 0 → 100+ (increments continuously) ✅

---

## Expected First 5 Minutes Behavior

### Minute 1: Initialization

**Status Bar**:
- Mode: LIVE_PEAK_PRESSURE
- Symbols: 10 symbols listed
- Baselines: 0 / 10 (or 1-5 / 10)
- Health: STARTING or OK
- Windows: 10-60
- Events: 0

**Health Panel**:
```
Trades rate: 150-500/s
Liquidations rate: 1-10/min
Klines rate: 10/s
OI rate: 2/min
```

**Raw Feed Tables**: Populating with trades and liquidations

**Promoted Events**: Shows "NO PEAK PRESSURE EVENTS DETECTED" with warmup message

### Minutes 2-5: Baseline Warmup

**Baselines Counter**: Increments gradually
- 2/10 at 120s
- 5/10 at 300s
- 10/10 at ~600s (10 minutes total)

**Why 10 minutes?** Each symbol requires 60 windows × 1s = 60 seconds minimum. Staggered stream starts cause delays.

**Windows Counter**: Should reach 100+ by minute 2, 500+ by minute 5

**Events**: Still likely 0 (normal market conditions)

### After 10 Minutes: Steady State

**All Baselines Ready**: 10 / 10

**Promotion Eligible**: System can now detect Peak Pressure events

**Event Count**: Likely still 0-2 (silence is expected)

---

## Baseline Warmup Explanation

### What Is Baseline Warmup?

**Baseline** = Rolling window of last 60 observations per symbol

**Metrics Calculated**:
- P90 of `abs_flow` (total buy + sell volume)
- P95 of mean trade size

**Warmup Requirement**: Need ≥60 windows before P90/P95 are statistically valid

### Why Promotions Are Disabled During Warmup

**Problem**: Cannot calculate "surge above P90" without knowing what P90 is.

**Solution**: Detector checks `baseline.is_warm()` before promotion.

**If not warm**:
- Event counted in `counters.baseline_not_warm`
- No promotion (correct behavior)
- UI shows "Baselines ready: X / 10"

### Per-Symbol Warmup

**Important**: Each symbol has independent baseline.

- BTCUSDT might warm at 60s
- ETHUSDT might warm at 65s (if stream started late)
- SOLUSDT might warm at 75s

**This is why "Baselines ready" increments gradually.**

---

## What "0 Peak Pressure Events" Means

### Three Valid Reasons for Zero Events

1. **Baseline Warmup** (first 5-10 minutes)
   - UI explicitly shows: "Baseline warmup (X / 10 symbols ready)"
   - This is **temporary and expected**

2. **Normal Market Conditions** (most common)
   - Price action within baseline bounds
   - No large trades detected
   - No liquidation/OI stress coincidence
   - **This is healthy stability**

3. **Partial Condition Satisfaction**
   - Flow surge ✅ but no large trades ❌
   - Large trades ✅ but no compression ❌
   - Compression ✅ but no external stress ❌
   - **Requires ALL 4 conditions to promote**

### When Zero Events Is Suspicious

**Red flags** (investigate if all true simultaneously):
- Baselines ready: 10 / 10 ✅
- Windows processed: > 1000 ✅
- Ingestion health: OK ✅
- High volatility visible in raw feed ✅
- **AND** promoted events: 0 for > 2 hours

**Diagnosis Steps**:
1. Check `debug/latest_snapshot.json`
2. Look at `counters` → `flow_surge_failed`, `large_trade_failed`, etc.
3. Most likely: No external stress (healthy market, no liquidations)

**Do NOT "fix" by lowering thresholds.** Zero events may be correct.

---

## What Counters to Watch

### Status Bar (Primary)

| Counter | Healthy Range | Warning If |
|---------|---------------|------------|
| Baselines ready | 10 / 10 (after 10 min) | Stuck at < 10 after 15 min |
| Health | OK | DEGRADED for > 2 min |
| Windows | Incrementing continuously | Frozen or decreasing |
| Events | 0-20 per hour | N/A (silence is valid) |

### Health Panel (Secondary)

| Metric | Healthy Range | Warning If |
|--------|---------------|------------|
| Trades rate | 100-1000/s | < 10/s or > 5000/s |
| Liquidations rate | 0.5-50/min | 0 for > 10 min |
| Klines rate | ~10/s | < 1/s |
| OI rate | ~2/min | < 0.2/min |

### Dropped Events (Diagnostic)

| Counter | Expected | Investigate If |
|---------|----------|---------------|
| symbol_not_allowed | 1000s-100,000s | > 1M/hour (symbol creep?) |
| baseline_not_ready | 100s early, 0 after warmup | > 100 after 20 min |
| window_not_closed | 0-10 | > 100 (timing issue?) |
| missing_streams | 0-50 | > 500 (connectivity?) |

---

## How to Confirm Ingestion Health

### Method 1: Status Bar (Quickest)

**Health: OK** = All streams nominal  
**Health: DEGRADED** = At least one stream below threshold

### Method 2: Health Panel (Detailed)

Check each stream rate:
```
Trades rate: 427.3/s      ← Should be 100-1000/s
Liquidations rate: 3.2/min  ← Varies widely, 0-50/min
Klines rate: 10.1/s        ← Should be ~10/s (1 per symbol)
OI rate: 2.1/min           ← Should be ~2/min (1 per 5s poll)
```

### Method 3: Debug Snapshot (Most Detailed)

```powershell
Get-Content d:\liquidation-trading\debug\latest_snapshot.json
```

Look for `ingestion_health`:
```json
{
  "ingestion_health": {
    "trades_rate": 427.3,
    "liquidations_rate": 3.2,
    "klines_rate": 10.1,
    "oi_rate": 2.1,
    "degraded": false,
    "degraded_reason": ""
  }
}
```

**If degraded**: Check `degraded_reason` field for cause.

---

## When Silence Is Healthy

### Scenario: No Events for 4 Hours

**Conditions**:
- Baselines ready: 10 / 10 ✅
- Windows processed: 14,400 (4 hours × 3600s) ✅
- Ingestion health: OK ✅
- Raw feed shows normal trading activity ✅

**Interpretation**: **This is normal.**

**Why?** Peak Pressure requires rare multi-stream coincidence:
- Flow surge (happens frequently)
- **AND** large trades (less frequent)
- **AND** compression/expansion (less frequent)
- **AND** liquidations or OI change (rare)

**All 4 together? Very rare.**

### Scenario: Sudden Event Cluster

**Observation**: 0 events for 2 hours, then 8 events in 15 minutes

**Conditions**:
- All events from same symbol (e.g., BTCUSDT)
- `stress_sources` include "liquidations"
- Raw feed shows liquidation spike

**Interpretation**: **Cascade detected correctly.**

**Why cluster?** Once liquidations start, they often trigger more liquidations (cascade effect). System observes each qualifying window independently.

**This is correct behavior, not a bug.**

---

## When Silence Is Suspicious

### Red Flag Checklist

If **ALL** of these are true, investigate:

- [ ] Baselines ready: 10 / 10 (fully warmed)
- [ ] Windows processed: > 5000 (> 90 minutes)
- [ ] Ingestion health: OK (all streams nominal)
- [ ] Raw feed shows high volatility (large price swings visible)
- [ ] Large liquidations visible in liquidations table
- [ ] **AND** promoted events: 0

**Diagnosis**:
1. Open `debug/latest_snapshot.json`
2. Check `counters`:
   ```json
   {
     "flow_surge_failed": 4523,
     "large_trade_failed": 89,
     "compression_failed": 3821,
     "stress_failed": 1092
   }
   ```

3. Identify which condition is failing most

**Most common cause**: `stress_failed` (no liquidations within 60s of flow surge)

**Action**: **None.** If conditions aren't met, events aren't promoted. This is correct.

---

## Restart Recovery Checklist

### After Planned Restart

✅ Collector starts without errors  
✅ "SystemState initialized" message appears  
✅ Native app connects within 2 seconds  
✅ Status bar populates (Mode, Symbols, Health)  
✅ Baselines reset to 0 / 10 (warmup restarts)  
✅ Raw feed tables populate immediately  

**Expected Reset**:
- Windows processed: Resets to 0
- Events: Previous events lost (not persisted)
- Baselines: Warmup from scratch

### After Crash/Kill

**Check for**:
- Orphaned Python processes (`tasklist | findstr python`)
- Locked parquet files (`market_events.parquet.tmp` leftover)
- Stale snapshot (`latest_snapshot.json` timestamp > 10s old)

**Clean recovery**:
```powershell
# Kill all Python processes
taskkill /F /IM python.exe

# Remove temp files
cd d:\liquidation-trading\data\v1_live_validation\market_events
Remove-Item *.tmp

# Restart
cd d:\liquidation-trading\scripts
python market_event_collector.py
```

---

## Common Misinterpretations

### ❌ "System must be broken, no events for 1 hour"

**Reality**: Silence is the expected state. < 5-20 events/day is normal.

### ❌ "Baseline warmup is too slow"

**Reality**: 60-second minimum per symbol is deterministic and correct.

### ❌ "We should lower thresholds to get more events"

**Reality**: This breaks observational integrity. Do not modify M3.

### ❌ "Event clustering is a bug"

**Reality**: Cascades trigger multiple qualifying windows. Correct behavior.

### ❌ "Raw feed is too noisy"

**Reality**: Raw feed shows ALL trades/liquidations (by design). Promoted panel shows filtered structural events.

---

## Emergency Procedures

### If Collector Freezes

1. Check console for error messages
2. Ctrl+C to interrupt
3. Check network connectivity (`ping fapi.binance.com`)
4. Restart collector
5. Native app should resume updating within 2 seconds

### If Native App Freezes

1. Check if collector is still running
2. Close native app (X button)
3. Relaunch `python main.py`
4. UI should repopulate from active SystemState snapshot

### If Ingestion Health = DEGRADED

1. Check which stream is degraded (Health Panel)
2. If trades: WebSocket reconnecting (wait 10-30s)
3. If OI: API timeout (wait for next 5s poll)
4. If prolonged (> 5 min): Restart collector

### If "Baselines ready" stuck at X/10

1. Check collector console for stream errors
2. Verify all symbols in `symbols_active` list
3. Check `debug/latest_snapshot.json` → `baseline_status`
4. If stuck > 15 min: Restart collector (baselines reset)

---

## Success Indicators

**System is operating correctly if**:

✅ Status bar shows 10 symbols  
✅ Baselines reach 10/10 within 10-15 minutes  
✅ Windows counter increments ~1/second  
✅ Ingestion health: OK or STARTING  
✅ Raw feed tables populate continuously  
✅ No console errors about file locking  
✅ Debug snapshot timestamp updates every 5s  

**Event count is NOT a success indicator.** Zero events may be correct.

---

## Final Reminders

1. **Silence is normal**. Do not expect constant events.
2. **Warmup takes time**. 10 minutes is required, not optional.
3. **Do not modify thresholds**. System is observational, not optimizable.
4. **Read the snapshot**. `debug/latest_snapshot.json` is authoritative.
5. **Trust the counters**. `flow_surge_failed` etc. explain why no promotion.

**This system renders truth. It does not tell you what you want to hear.**
