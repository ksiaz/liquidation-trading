# PHASE 6: VERIFICATION RUN PLAN

**Status:** READY TO EXECUTE  
**Date:** 2026-01-06  
**Trust Level:** System is TRUSTED for verification, NOT for live trading

---

## 1. Prerequisites (MUST Complete Before Launch)

### Stop Legacy Processes
```powershell
# Stop the following running terminals:
# - d:\liquidation-trading\scripts\market_event_collector.py
# - d:\liquidation-trading\native_app\main.py
```

**Why:** Prevents port conflicts and ensures clean environment.

---

## 2. Launch Command (Exact)

```powershell
cd d:\liquidation-trading
python runtime/native_app/main.py
```

**Expected:** Application window titled "Peak Pressure Detector (Sealedv1.0)" launches.

---

## 3. Mandatory Observation Checklist

You MUST observe and confirm ALL of the following behaviors.  
If ANY fails, Phase 5 is retroactively INVALIDATED.

### ✅ Test 1: Startup State
**Action:** Launch the application  
**Expected:**
- UI shows "SYNCING" or "Initializing..." status
- NO metrics displayed (counters should be 0 or hidden)
- NO premature "OK" state

**Pass Criteria:** System does not claim health before data arrives.

---

### ✅ Test 2: Heartbeat Behavior (Data Arrival)
**Action:** Wait for WebSocket connection to establish  
**Expected:**
- Status transitions from SYNCING → OK
- System Time (`timestamp`) begins advancing
- Counters (windows_processed, etc.) begin incrementing

**Pass Criteria:** System recognizes live data and reports OK only after ingestion starts.

---

### ✅ Test 3: Liveness (Staleness Detection)
**Action:** Disconnect internet OR pause data feed for >5 seconds  
**Expected:**
- UI transitions to **STALE** state
- Dashboard shows gray overlay or "CONNECTION LOST" banner
- Rates display "--.-" instead of "0.0"

**Pass Criteria:** System explicitly differentiates "No Activity" from "No Data".

---

### ✅ Test 4: Invariant Enforcement (Time Monotonicity)
**Action:** (Advanced) Artificially trigger time regression in code OR observe natural recovery  
**Expected:**
- If time regresses: System enters **FAILED** state
- UI shows **RED SCREEN OF DEATH**
- Query operations blocked with `SystemHaltedException`

**Pass Criteria:** System fails hard rather than rendering incoherent state.

---

### ✅ Test 5: Silence Semantics (Quiet Market vs Dead System)
**Action:** Observe during low-activity period  
**Expected:**
- **Scenario A:** Data flowing, zero events → Status = OK, Counters low
- **Scenario B:** Data stopped, time frozen → Status = STALE

**Pass Criteria:** System distinguishes "Nothing Happened" from "I Don't Know".

---

### ✅ Test 6: Zombie UI Prevention
**Action:** Kill the collector service mid-run  
**Expected:**
- Within 5 seconds: UI must NOT remain "Green/OK"
- Status shifts to STALE or FAILED

**Pass Criteria:** UI cannot lie about system health.

---

## 4. Verification Findings Template

After completing all tests, document results:

```markdown
## VERIFICATION RUN REPORT

**Date:** [timestamp]
**Duration:** [minutes]

### Test Results
- [ ] Test 1 (Startup): PASS / FAIL
- [ ] Test 2 (Heartbeat): PASS / FAIL
- [ ] Test 3 (Staleness): PASS / FAIL
- [ ] Test 4 (Invariants): PASS / FAIL
- [ ] Test 5 (Silence): PASS / FAIL
- [ ] Test 6 (Zombie): PASS / FAIL

### Observed Anomalies
[List any unexpected behaviors]

### Verdict
- [ ] System is APPROVED for M6 integration
- [ ] System REMAINS observation-only
- [ ] System FAILS verification (return to Phase 5)
```

---

## 5. What Happens Next

### If ALL Tests Pass:
**Proceed to Phase 7 Decision:**
- Option A: Approve for M6 (Trading Logic) integration
- Option B: Keep as observation-only system

### If ANY Test Fails:
**Return to Phase 5:**
- Identify violated invariant
- Re-execute Kill-List remediation
- Re-verify before next attempt

---

## 6. Explicitly Forbidden Actions

During verification, you MUST NOT:
- Enable M6 (trading, execution, automation)
- Add convenience shortcuts around M5 Gate
- Optimize performance before correctness is proven
- Treat "OK" status as profitability signal
- Backfill data without explicit SYNCING mode

**Violation = System re-enters UNTRUSTED state.**

---

## 7. Success Condition

The system passes Phase 6 when:
1. All 6 tests return PASS
2. Operator confirms: "This UI does not lie to me"
3. No silent failures observed during 10+ minute run

Only then may Phase 7 (M6 Design) commence.
