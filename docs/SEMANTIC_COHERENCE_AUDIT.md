# SEMANTIC COHERENCE & OPERATOR TRUST AUDIT

**Date:** 2026-01-06 13:32:35  
**Type:** Human-Centered Semantic Analysis  
**Perspective:** Operator Trust & Interpretability

---

## EXECUTIVE SUMMARY

**Human Confusion Points:** 8 identified  
**Misleading Names:** 3  
**Ambiguous States:** 2  
**Silence vs Failure Risks:** 1  

**Epistemic Honesty Score:** 6/10 (Improvable)

---

## CONFUSION POINT #1: "SYSTEM OK" Status

### Current Implementation
```python
if snapshot.status == ObservationStatus.OK:
    self.status_label.setText(f"SYSTEM OK\n...")
```

### Human Interpretation Risk
**What operator sees:** "SYSTEM OK"  
**What operator might think:** "Everything is working correctly and I can trust the data"  
**What it actually means:** "Liveness check passed (data < 5s old)"

**Problem:**
- Implies overall system health, but only verifies liveness
- Does NOT mean "data is valid", "baseline is ready", or "detection is reliable"
- Operator might make trading decisions based on "OK" without checking baseline status

**Severity:** ⚠️ **HIGH** - Can cause premature trust

### Recommended Fix
**Name:** `OK` → `LIVE`  
**UI Text:** `"SYSTEM OK"` → `"DATA LIVE"`

**Rationale:** "LIVE" is more accurate - it means data is flowing, not that everything is "OK"

---

## CONFUSION POINT #2: "windows_processed" Counter

### Current Name
```python
windows_processed: int  # Count of closed 1-second aggregation windows
```

### Human Interpretation Risk
**What operator sees:** `Windows: 45`  
**What operator might think:** "45 windows have been analyzed for pressure"  
**What it actually means:** "45 time-windows closed (even if empty)"

**Problem:**
- Windows close even if NO trades occurred
- High window count does NOT mean high activity
- Operator might think system is "working hard" when market is dead

**Severity:** ⚠️ **MEDIUM** - Misleading activity indicator

### Recommended Fix
**Name:** `windows_processed` → `time_windows_elapsed`  
**UI Label:** `Windows: N` → `Time Windows: N` or `Seconds Elapsed: N`

**Rationale:** Emphasizes that this is a TIME metric, not an ACTIVITY metric

---

## CONFUSION POINT #3: "peak_pressure_events" Name

### Current Name
```python
peak_pressure_events: int
```

### Human Interpretation Risk
**What operator sees:** `Peak Pressure Events: 22`  
**What operator might think:** "22 confirmed peak pressure situations"  
**What it actually means:** "22 trades exceeded the baseline threshold"

**Problem:**
- "Peak" implies significance or turning points
- "Events" implies rare occurrences
- Actually just statistical outliers (sigma > 2.0)
- Does NOT guarantee price impact or actionability

**Severity:** ⚠️ **HIGH** - Overstates significance

### Recommended Fix
**Name:** `peak_pressure_events` → `threshold_exceedances` or `sigma_outliers`  
**UI Label:** `Peak Pressure Events: N` → `Baseline Outliers: N` or `Threshold Crosses: N`

**Rationale:** More accurate - these are statistical observations, not confirmed "events"

---

## CONFUSION POINT #4: "SYNCING" Status Ambiguity

### Current Implementation
```python
if snapshot.status == ObservationStatus.SYNCING:
    self.status_label.setText(f"SYNCING - Waiting for data...\n...")
```

### Human Interpretation Risk
**What operator sees:** "SYNCING - Waiting for data..."  
**What operator might think:** "System is catching up to real-time"  
**What it actually means:** "Initial state, no data yet" OR "Recovering from halt"

**Problem:**
- "SYNCING" implies active synchronization (like database sync)
- Could mean "backfilling" or just "starting up"
- Unclear if this is normal startup or error recovery

**Severity:** ⚠️ **LOW** - Slightly misleading but not dangerous

### Recommended Fix
**State Name:** `SYNCING` → `WARMING_UP` or `INITIALIZING`  
**UI Text:** `"SYNCING - Waiting for data..."` → `"INITIALIZING - Waiting for first data..."`

**Rationale:** Clearer that this is startup, not synchronization

---

## CONFUSION POINT #5: "STALE" vs Silence

### Current Implementation
```python
if snapshot.status == ObservationStatus.STALE:
    self.status_label.setText(f"STALE DATA (Lag > 5s)\n...")
```

### Human Interpretation Risk
**What operator sees:** "STALE DATA (Lag > 5s)"  
**What operator might think:** "The data I'm seeing is old"  
**What might be unclear:** "Is this a pause in the market or a system failure?"

**Problem:**
- "STALE" could mean: network outage, WebSocket disconnect, or genuinely quiet market
- Operator doesn't know if they should:
  - Wait for recovery (network issue)
  - Restart the system (failure)
  - Ignore it (market is

 quiet, but data is actually current)

**Severity:** ⚠️ **MEDIUM** - Ambiguous cause

### Recommended Fix
**Add Context to UI:**
```python
f"DATA STALE (>5s lag)\n"
f"Last Update: {lag:.1f}s ago\n"
f"Check: Network connection"
```

**Alternative State Names:**
- `STALE` → `NO_UPDATES` (clearer that updates stopped)
- Or keep `STALE` but add diagnostic info

**Rationale:** Helps operator distinguish between failure modes

---

## CONFUSION POINT #6: Zero Values Ambiguity

### Current Behavior
```python
ingestion_health=IngestionHealth(0,0,0,0,False,"")  # All zeros (stub)
```

### Human Interpretation Risk
**What operator sees:** `Trades Rate: 0.0/s`  
**What operator might think:** "Market is quiet" OR "System is broken"  
**What it actually means:** "Not implemented yet (placeholder)"

**Problem:**
- Zero could mean THREE different things:
  1. Market has no activity (true zero)
  2. Metric not calculated (stub)
  3. System failure (broken counter)
- Impossible to distinguish

**Severity:** ⚠️ **HIGH** - Critical ambiguity

### Recommended Fix
**Option 1:** Display `--` instead of `0.0` for unimplemented metrics
```python
trades_rate = m1_stats.get('trades_rate', None)
display = f"{trades_rate:.1f}/s" if trades_rate is not None else "--.-"
```

**Option 2:** Add explicit "Not Available" field
```python
class IngestionHealth:
    available: bool  # If False, ignore other fields
```

**Rationale:** Distinguishes "not implemented" from "actually zero"

---

## CONFUSION POINT #7: "baseline_status.ready_symbols"

### Current Name
```python
baseline_status.ready_symbols: int  # Count of symbols with warm baseline
```

### Human Interpretation Risk
**What operator sees:** `Baseline Ready: 1 / 10`  
**What operator might think:** "Only 1 symbol is ready to trade"  
**What it actually means:** "Baseline is warmed for 1 symbol (global aggregated baseline)"

**Problem:**
- Implies per-symbol readiness
- Actually system uses GLOBAL baseline (all symbols aggregated)
- The "1" is just a simplified boolean (0 or 1)

**Severity:** ⚠️ **MEDIUM** - Misleading granularity

### Recommended Fix
**Name:** `ready_symbols` → `baseline_ready` (boolean)  
**UI Display:**
```python
# Instead of: "Baseline Ready: 1 / 10"
# Show: "Baseline: WARM" or "Baseline: COLD"
```

**Rationale:** Matches actual implementation (global baseline, not per-symbol)

---

## CONFUSION POINT #8: "dropped_events" Negative Framing

### Current Name
```python
dropped_events: Dict[str, int]  # 'errors', 'rejected_pressure'
```

### Human Interpretation Risk
**What operator sees:** `Dropped Events: 150`  
**What operator might think:** "System is losing data! Bad!"  
**What it actually means:** "150 trades didn't meet promotion criteria (expected)"

**Problem:**
- "Dropped" implies data loss or system failure
- "Rejected" trades are EXPECTED behavior (most trades fail promotion)
- High "dropped" count is NORMAL, not alarming

**Severity:** ⚠️ **MEDIUM** - Causes unnecessary alarm

### Recommended Fix
**Name:** `dropped_events.rejected_pressure` → `filtered_trades` or `below_threshold`  
**Name:** `dropped_events.errors` → `normalization_failures`

**UI Display:**
```python
# Instead of: "Dropped: 150"
# Show: "Filtered: 150 (below threshold)"
```

**Rationale:** "Filtered" is neutral, "Dropped" sounds like failure

---

## SILENCE VS FAILURE ANALYSIS

### Scenario: Market is Quiet (No Trades)

**Current Behavior:**
- Status: OK
- Windows: Incrementing
- Peak Pressure Events: 0
- Trades Rate: 0.0 (or stub)

**Operator Confusion:**
"Is the system working, or is the WebSocket disconnected?"

### Scenario: WebSocket Disconnected

**Current Behavior:**
- Status: STALE (after 5s)
- Windows: Stopped incrementing
- Rest: Frozen

**Problem:** If operator only glances at "Windows" metric, they might not notice STALE status

### Recommended Fix
**Add "Last Event" timestamp:**
```python
f"Last Trade: 3.2s ago"
```

**Or add "Heartbeat" counter:**
- Increments even if no trades (proves system is alive)

---

## PROPOSED SEMANTIC CORRECTIONS SUMMARY

| Current Name | Issue | Recommended Change | Logic Change? |
|--------------|-------|-------------------|---------------|
| `ObservationStatus.OK` | Overstates | → `LIVE` | ❌ NO |
| `windows_processed` | Misleading activity | → `time_windows_elapsed` | ❌ NO |
| `peak_pressure_events` | Overstates significance | → `threshold_exceedances` | ❌ NO |
| `ObservationStatus.SYNCING` | Unclear meaning | → `INITIALIZING` | ❌ NO |
| `ingestion_health` zeros | Ambiguous | Display `--` for stubs | ❌ NO |
| `baseline_status.ready_symbols` | Wrong granularity | → `baseline_ready` (bool) | ❌ NO |
| `dropped_events` | Negative framing | → `filtered_trades` | ❌ NO |
| `STALE` status | Missing context | Add "Last Update: Xs ago" | ❌ NO |

**Total Recommendations:** 8  
**All semantic-only:** ✅ YES

---

## EPISTEMIC HONESTY IMPROVEMENTS

### Before (Current)
```
SYSTEM OK
Time: 1767701280.52
Windows: 45
Peak Pressure Events: 22
```

**Operator Interpretation:**  
"System is healthy, 45 windows analyzed, 22 significant events detected"

**Reality:**  
"Data is fresh (< 5s), 45 seconds elapsed, 22 trades were outliers (may not be significant)"

---

### After (Proposed)
```
DATA LIVE
Time: 1767701280.52
Time Windows: 45s
Threshold Crosses: 22
Last Trade: 0.3s ago
```

**Operator Interpretation:**  
"Data feed is active, 45 seconds of monitoring, 22 statistical outliers, recent activity"

**Reality:**  
Same as before, but NAMING matches reality

---

## HUMAN TRUST SCORE

### Current System
| Trust Dimension | Score | Issue |
|-----------------|-------|-------|
| Clarity | 5/10 | Ambiguous names |
| Honesty | 6/10 | "OK" overstates |
| Actionability | 4/10 | Hard to diagnose |
| Transparency | 7/10 | Most metrics visible |

**Overall:** 5.5/10 ⚠️

### After Corrections
| Trust Dimension | Score | Improvement |
|-----------------|-------|-------------|
| Clarity | 8/10 | ✅ Descriptive names |
| Honesty | 9/10 | ✅ "LIVE" not "OK" |
| Actionability | 7/10 | ✅ Diagnostic hints |
| Transparency | 7/10 | (unchanged) |

**Overall:** 7.75/10 ✅

---

## IMPLEMENTATION PRIORITY

### High Priority (Do First)
1. ✅ **Rename `OK` → `LIVE`** - Prevents overconfidence
2. ✅ **Rename `peak_pressure_events` → `threshold_exceedances`** - Prevents misinterpretation
3. ✅ **Display `--` for unimplemented metrics** - Prevents zero ambiguity

### Medium Priority
4. Rename `windows_processed` → `time_windows_elapsed`
5. Rename `SYNCING` → `INITIALIZING`
6. Add "Last Event" timestamp to UI

### Low Priority
7. Rename `dropped_events` → `filtered_trades`
8. Refactor `ready_symbols` to boolean

---

## FINAL RECOMMENDATION

**Apply High Priority changes immediately.**  
These are critical for operator trust and prevent dangerous misinterpretations.

**Medium/Low Priority changes can be batched in UI polish pass.**

All changes are **semantic only** - no logic modifications required.

---

**END OF SEMANTIC AUDIT**
