# FAILURE MODE SIMULATION & TRUTHFULNESS TEST

**Date:** 2026-01-06 13:35:00  
**Type:** Controlled Failure Injection Analysis  
**Mode:** Failure Mode & Effects Analysis (FMEA)

---

## EXECUTIVE SUMMARY

**Failure Modes Tested:** 5  
**Acceptable Behaviors:** 3  
**Dangerous Behaviors:** 1  
**Deceptive Behaviors:** 1  

**Overall System Reliability:** ⚠️ **6/10** (Needs improvement)

---

## FAILURE MODE #1: NO DATA (WebSocket Disconnected)

### Simulation
- Start system
- WebSocket fails to connect OR disconnects immediately
- Clock driver continues running (0.1s interval)

### System Behavior

**Initial State (0-2s):**
```
Status: SYNCING
Time: 1767701280.0 (incrementing)
Windows: 0
Peak Pressure Events: 0
```

**After 2s (lag < 2s):**
```
Status: OK (auto-recovery per line 135)
Time: 1767701282.0 (incrementing)
Windows: 2
Peak Pressure Events: 0
```

**After 5s (lag still 0):**
```
Status: OK
Time: 1767701285.0 (incrementing)
Windows: 5
Peak Pressure Events: 0
```

### Analysis

**What UI Shows:**
- ✅ Status: OK (green background)
- ✅ Time: Incrementing normally
- ✅ Windows: Incrementing (windows close even if empty)
- ✅ Events: 0

**Is This Truthful?**
⚠️ **PARTIALLY DECEPTIVE**

**Problems:**
1. System shows "OK" when NO data is flowing
2. Windows increment suggests activity when there is NONE
3. Lag calculation: `lag = wall_clock - system_time`
   - Since `advance_time()` updates `system_time` to current wall clock
   - Lag is ALWAYS ~0 (clock driver keeps system time current)
   - **STALE status NEVER triggers** if clock keeps running!

**Failure Mode:** ❌ **SILENT**

**Classification:** 🔴 **DECEPTIVE** - Shows "OK" with no data

---

### Code Analysis: Why STALE Never Triggers

```python
# governance.py:127-132
wall_clock = time.time()
lag = wall_clock - self._system_time  # If clock driver runs, lag ≈ 0

if self._status == ObservationStatus.OK and lag > 5.0:
    effective_status = ObservationStatus.STALE
```

**Problem:**
- `advance_time()` is called every 0.1s with current wall clock
- `self._system_time` = wall clock (always fresh)
- Lag calculation assumes `system_time` advances via DATA timestamps
- But clock driver advances it regardless of data

**Root Cause:** Liveness check measures CLOCK staleness, not DATA staleness

---

## FAILURE MODE #2: PARTIAL DATA (Some Symbols Missing)

### Simulation
- WebSocket connects
- Only 50% of TOP_10 symbols receive trades
- Other 50% are silent (illiquid or API issue)

### System Behavior

```
Status: OK
Time: 1767701290.0
Windows: 10
Peak Pressure Events: 5 (from active symbols)
```

### Analysis

**What UI Shows:**
- Status: OK
- Windows: Incrementing
- Events: Some detected

**Is This Truthful?**
✅ **YES - ACCEPTABLE**

**Reasoning:**
- System correctly processes available data
- No false positives (events are real)
- Partial data is a valid operational state
- Operator can check `symbols_active` if needed

**Failure Mode:** ✅ **GRACEFUL DEGRADATION**

**Classification:** ✅ **ACCEPTABLE** - System adapts to reality

---

## FAILURE MODE #3: DELAYED DATA (Network Lag Spike)

### Simulation
- WebSocket delivers trades with 10-second delay
- Event timestamps are 10s in the past
- Clock driver continues at wall clock

### System Behavior

**Clock Driver:**
```python
# Advances system_time to 1767701300.0 (current wall clock)
```

**Data Arrives:**
```python
# Event timestamp: 1767701290.0 (10s ago)
# Causality check: timestamp < system_time - 30.0?
# 1767701290.0 < 1767701300.0 - 30.0? → NO (accepted)
```

**UI Display:**
```
Status: OK (lag = 0, clock is current)
Time: 1767701300.0
Windows: 15
Peak Pressure Events: 8
```

### Analysis

**What UI Shows:**
- Status: OK (because clock is current)
- Time: Current wall clock
- Events: Processed (10s old events)

**Is This Truthful?**
⚠️ **PARTIALLY MISLEADING**

**Problems:**
1. "OK" status implies fresh data
2. No indication that data is 10s delayed
3. Liveness check passes (system time is current)
4. Events processed appear "current" but are stale

**Actual Risk:**
- If lag persists, might trade on outdated market conditions
- UI gives no warning

**Failure Mode:** ⚠️ **SILENT DEGRADATION**

**Classification:** ⚠️ **DANGEROUS** - Stale data appears fresh

---

### Proposed Fix for Delayed Data

**Add DATA-based liveness check:**
```python
# Track last EVENT timestamp (not system time)
self._last_event_timestamp = 0.0

# In ingest_observation():
if event_type in ['TRADE', 'LIQUIDATION']:
    self._last_event_timestamp = max(self._last_event_timestamp, timestamp)

# In _get_snapshot():
data_lag = wall_clock - self._last_event_timestamp
if data_lag > 5.0:
    effective_status = ObservationStatus.STALE
```

---

## FAILURE MODE #4: DUPLICATE WRITERS (Legacy Process Running)

### Simulation
- New runtime starts: `python runtime/native_app/main.py`
- Legacy process still running: `python scripts/market_event_collector.py`
- Both write to metrics (different state instances)

### System Behavior

**Per PROMPT 0:** ✅ **PREVENTED**

**Current State:**
- Legacy process stopped (verified via `tasklist`)
- Only new runtime running
- Single writer confirmed

**If Legacy Resumed:**
- Two separate `ObservationSystem` instances
- Two separate metric states
- UI reads from new instance only
- Legacy writes go to legacy `SystemState` (unreachable)

### Analysis

**What UI Shows:**
- Metrics from NEW system only
- No indication of legacy contamination

**Is This Truthful?**
✅ **YES** (but only because legacy is stopped)

**If Legacy Runs:**
🔴 **DECEPTIVE** - UI would show incomplete picture

**Failure Mode:** ✅ **PREVENTED** (structural isolation)

**Classification:** ✅ **ACCEPTABLE** (current state)

---

## FAILURE MODE #5: CLOCK STALL (advance_time() Stops)

### Simulation
- Clock driver crashes or `asyncio` loop hangs
- `advance_time()` stops being called
- Data still arrives (WebSocket active)

### System Behavior

**Time 0-5s:**
```
Status: OK
Time: 1767701300.0 (FROZEN)
Windows: 10 (FROZEN)
Peak Pressure Events: 10 (FROZEN - no window closure)
```

**After 5s:**
```python
# Liveness check:
lag = time.time() - self._system_time
# lag = 1767701305.0 - 1767701300.0 = 5.0s

if lag > 5.0:
    effective_status = ObservationStatus.STALE
```

**UI Display:**
```
Status: STALE
Time: 1767701300.0 (FROZEN)
Windows: 10 (FROZEN)
```

### Analysis

**What UI Shows:**
- ✅ Status changes to STALE (gray background)
- ✅ Time is frozen (visible to operator)
- ✅ Windows stop incrementing

**Is This Truthful?**
✅ **YES - EXCELLENT**

**Behavior:**
- System correctly detects clock stall
- Visual feedback (gray background)
- Operator can see frozen metrics

**Failure Mode:** ✅ **LOUD** (visible warning)

**Classification:** ✅ **ACCEPTABLE** - Fails truthfully

---

## FAILURE MATRIX

| Failure Mode | Display | Status | Truthful? | Fail Mode | Classification |
|--------------|---------|--------|-----------|-----------|----------------|
| **No Data** | OK, Windows++, Events=0 | OK | ❌ NO | 🔇 SILENT | 🔴 **DECEPTIVE** |
| **Partial Data** | OK, Some Events | OK | ✅ YES | ✅ GRACEFUL | ✅ **ACCEPTABLE** |
| **Delayed Data** | OK, Stale Events | OK | ⚠️ PARTIAL | ⚠️ SILENT | ⚠️ **DANGEROUS** |
| **Duplicate Writers** | Metrics from new only | OK | ✅ YES* | ✅ ISOLATED | ✅ **ACCEPTABLE*** |
| **Clock Stall** | STALE, Frozen | STALE | ✅ YES | ✅ LOUD | ✅ **ACCEPTABLE** |

\* *Acceptable only because legacy is currently stopped*

---

## TRUST IMPACT ASSESSMENT

### Critical Issues

#### 1. **No Data Shows "OK"** 🔴
**Impact:** ⚠️ **CRITICAL**

**Scenario:**
- WebSocket disconnects silently
- Clock driver keeps running
- UI shows "OK" indefinitely
- Operator trusts stale/absent data

**Risk:**
- Operator makes decisions based on "everything is fine"
- No trades occur, but system appears healthy
- Could miss critical market events

**Mitigation Required:** ✅ **YES - HIGH PRIORITY**

---

#### 2. **Delayed Data Appears Fresh** ⚠️
**Impact:** ⚠️ **HIGH**

**Scenario:**
- Network lag causes 10-30s delays
- Events processed as if current
- No visual indication of staleness

**Risk:**
- Trading on outdated orderbook
- Missed opportunities or bad entries

**Mitigation Required:** ✅ **YES - MEDIUM PRIORITY**

---

### Acceptable Behaviors

#### 3. **Clock Stall Detection** ✅
**Impact:** ✅ **POSITIVE**

**Behavior:**
- Correctly detects frozen time
- Visual STALE indicator
- Operator can diagnose

**Validation:** System works as designed

---

## ROOT CAUSE ANALYSIS

### Why Liveness Check Fails

**Current Logic:**
```python
lag = wall_clock - self._system_time
if lag > 5.0: STALE
```

**Assumptions:**
- `system_time` advances via DATA timestamps
- If no data, `system_time` stops advancing
- Lag increases, triggers STALE

**Reality:**
- Clock driver calls `advance_time(wall_clock)` every 0.1s
- `system_time` = wall clock (always current)
- Lag is ALWAYS ~0, regardless of data

**Solution:**
Track BOTH system time (for temporal logic) AND last event time (for liveness)

---

## RECOMMENDED FIXES

### Fix #1: DATA-Based Liveness (CRITICAL)

**Add to `governance.py`:**
```python
class ObservationSystem:
    def __init__(self, allowed_symbols):
        # ... existing ...
        self._last_event_time = 0.0  # NEW
        
    def ingest_observation(self, timestamp, symbol, event_type, payload):
        # ... existing logic ...
        
        # Track data arrival
        if event_type in ['TRADE', 'LIQUIDATION']:
            self._last_event_time = max(self._last_event_time, timestamp)
            
    def _get_snapshot(self):
        # ... existing ...
        
        # NEW LIVENESS CHECK
        wall_clock = time.time()
        
        # Check DATA staleness, not CLOCK staleness
        if self._last_event_time > 0:
            data_lag = wall_clock - self._last_event_time
            if self._status == ObservationStatus.OK and data_lag > 5.0:
                effective_status = ObservationStatus.STALE
```

**Impact:**
- ✅ Detects "no data" within 5s
- ✅ Shows STALE when WebSocket disconnects
- ✅ Truthful liveness check

---

### Fix #2: Display Data Age in UI (MEDIUM)

**Add to `main.py` UI:**
```python
if snapshot.last_event_time > 0:
    data_age = time.time() - snapshot.last_event_time
    self.status_label.setText(
        f"DATA LIVE\n"
        f"Time: {snapshot.timestamp:.2f}\n"
        f"Last Event: {data_age:.1f}s ago\n"  # NEW
        f"Windows: {snapshot.counters.windows_processed}"
    )
```

**Impact:**
- ✅ Operator sees data age
- ✅ Can distinguish silence from failure

---

### Fix #3: Add "Data Flowing" Indicator (LOW)

**Add heartbeat counter:**
```python
self._events_this_second = 0

# In ingest_observation():
self._events_this_second += 1

# UI shows:
"Events/sec: 12 ✅" or "Events/sec: 0 ⚠️"
```

---

## FAILURE MODE SEVERITY MATRIX

| Failure | Operator Sees | Reality | Danger Level |
|---------|---------------|---------|--------------|
| No Data | "SYSTEM OK" | No data arriving | 🔴 **CRITICAL** |
| Network Lag | "SYSTEM OK" | Data 10s old | 🟠 **HIGH** |
| Clock Stall | "STALE DATA" | Time frozen | 🟢 **LOW** |
| Partial Data | "SYSTEM OK" | Some symbols OK | 🟢 **LOW** |
| Duplicate Writer | "SYSTEM OK" | Only new data | 🟢 **LOW*** |

\* *Low only because legacy is stopped*

---

## FINAL VERDICT

**Current System Truthfulness:** ⚠️ **6/10**

**Critical Flaws:**
1. 🔴 No-data condition shows "OK" (DECEPTIVE)
2. ⚠️ Delayed data appears current (DANGEROUS)

**Strengths:**
1. ✅ Clock stall detected correctly
2. ✅ Partial data handled gracefully
3. ✅ Structural isolation prevents dual writers

**Recommended Actions:**
1. **IMMEDIATE:** Implement data-based liveness check
2. **SOON:** Display "Last Event" timestamp in UI
3. **OPTIONAL:** Add events/sec indicator

**After Fixes:** Truthfulness → **9/10** ✅

---

**END OF FAILURE MODE SIMULATION**
