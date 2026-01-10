# M6 CONSUMPTION CONTRACT

**Status:** Constitutional  
**Authority:** Binding on all execution systems  
**Governed By:** EPISTEMIC_CONSTITUTION.md, SYSTEM_CANON.md  
**Effect:** Permanent

---

## ARTICLE I: WHAT M6 MAY READ FROM OBSERVATION

### External Surface (via ObservationSnapshot)
- `status` (ObservationStatus enum)
- `timestamp` (float)
- `symbols_active` (List[str])

### Internal State (direct access to observation internals)
- M1 raw event buffers (raw_trades, raw_liquidations)
- M1 counters (trades, liquidations, klines, oi, errors)
- M3 current windows (partial aggregations)
- M3 baseline state (window_sizes deque)
- M3 promoted events list
- M3 statistics (windows_processed, peak_pressure_events, rejected_count)
- M5 system_time (internal clock)
- M5 failure_reason (terminal error message)

### Prohibition
M6 must never modify observation state.
M6 must never call observation write methods.
M6 must never inject synthetic events into observation.

---

## ARTICLE II: WHAT M6 MUST TREAT AS UNKNOWABLE

M6 must treat the following as fundamentally unknowable:
- Whether observation data is fresh
- Whether observation data is complete
- Whether observation data is valid
- Whether baseline is warm
- Whether baseline is ready
- Whether promoted events are significant
- Whether counters represent meaningful activity
- Whether observation is operational
- Whether observation is healthy
- Whether observation will continue functioning
- Whether observation silence means absence or failure
- Whether any time gap represents data loss or quiet market

---

## ARTICLE III: M6 BEHAVIOR WHEN OBSERVATION IS SILENT

### Definition of Silence
Observation is silent when:
- Status is UNINITIALIZED
- Internal counters are zero
- Internal buffers are empty
- No events in promoted_events list

### Required M6 Behavior
M6 must:
- Treat silence as absence of information
- Make no assumptions about external market state
- Make no assumptions about observation health
- Make no assumptions about future data arrival
- Continue only if M6 logic explicitly tolerates complete absence of observation data

M6 must not:
- Interpret silence as "safe to proceed"
- Interpret silence as "market is quiet"
- Interpret silence as "no opportunities"
- Assume observation will resume
- Cache stale observation data as current

---

## ARTICLE IV: M6 BEHAVIOR WHEN OBSERVATION IS FAILED

### Definition of FAILED
Observation status is ObservationStatus.FAILED.

### Required M6 Behavior
M6 must:
- Immediately cease all new execution decisions
- Treat all cached observation data as invalid
- Surface FAILED status to operator without interpretation
- Enter safe degraded mode or halt entirely

M6 must not:
- Continue operating on last known observation state
- Attempt to restart or recover observation
- Bypass observation failure
- Make execution decisions without observation
- Assume observation failure is transient

---

## ARTICLE V: WHAT M6 MUST NEVER EXPOSE EXTERNALLY

### Prohibited External Exposures
M6 must never expose externally:
- "Observation is healthy"
- "Observation is ready"
- "Data is fresh"
- "Data quality is good"
- "Baseline is warm"
- "Confidence in observation"
- "Observation reliability score"
- "Data completeness percentage"
- "Observation uptime"
- "Liveness status"

### Prohibited Derived Claims
M6 must never expose externally:
- "Trade signal strength" (derived from observation)
- "Market condition assessment" (derived from observation)
- "Opportunity quality" (derived from observation)
- "Confidence level" (derived from observation)
- "Edge magnitude" (derived from observation)

### Allowed External Exposures
M6 may expose externally:
- "M6 status: [executing | halted | degraded]"
- "M6 action taken: [specific execution action]"
- "M6 failure: [specific execution failure]"
- "Observation status: [UNINITIALIZED | FAILED]" (pass-through only, no interpretation)

---

## ARTICLE VI: INTERNAL CONSUMPTION VS EXTERNAL ASSERTION

### Internal Use Permitted
M6 may use observation data internally for:
- Decision logic execution
- Threshold comparison
- State machine transitions
- Execution timing
- Position sizing
- Entry/exit determination

### External Assertion Forbidden
M6 must not assert externally:
- That observation data justified the decision
- That observation data was sufficient
- That observation data was reliable
- That the decision was confident
- That the observation supported the action

### Separation Requirement
M6 internal decision-making processes are opaque.
M6 external statements are factual actions only.

---

## ARTICLE VII: OBSERVATION DEPENDENCY DECLARATION

### M6 Must Declare
M6 must explicitly declare whether it:
- Requires observation to function (hard dependency)
- Can function without observation (soft dependency)
- Can function with degraded observation (partial dependency)

### Hard Dependency Rule
If M6 declares hard dependency on observation:
- M6 must halt when observation is FAILED
- M6 must halt when observation is UNINITIALIZED beyond defined timeout
- M6 must surface observation status without interpretation

### Soft Dependency Rule
If M6 declares soft dependency on observation:
- M6 must document fallback behavior when observation is absent
- M6 must not claim observation-derived properties when operating in fallback mode
- M6 must surface when operating without observation data

---

## ARTICLE VIII: FAILURE PROPAGATION REQUIREMENT

### Observation FAILED → M6 FAILED
When observation transitions to FAILED:
- M6 must propagate failure upward
- M6 must not downgrade to warning
- M6 must not suppress failure

### Observation Silent → M6 Explicit
When observation is silent (UNINITIALIZED, empty buffers):
- M6 must explicitly surface "operating without observation"
- M6 must not imply observation is functioning
- M6 must not claim derived confidence

---

## ARTICLE IX: TEMPORAL ASSUMPTIONS PROHIBITION

M6 must not assume:
- Observation timestamp represents wall clock time
- Observation timestamp represents data freshness
- Observation timestamp represents market time
- Time gaps represent specific durations of market activity
- Observation will advance at consistent rate
- Observation clock correlates with execution clock

---

## ARTICLE X: INTERPRETIVE PROHIBITION

M6 must not interpret:
- Observation silence as meaning
- Observation counters as significance
- Observation events as opportunities
- Observation thresholds as edges
- Observation baselines as predictions
- Observation state as market state

M6 may only consume observation as raw structural input to predefined decision logic.

---

## ENFORCEMENT

Violation of this contract voids M6 trustworthiness.

Any M6 external claim about observation quality, health, or readiness is a contract violation.

Any M6 continuation after observation FAILED is a contract violation.

Any M6 interpretation of observation silence is a contract violation.

---

**END OF M6 CONSUMPTION CONTRACT**

This contract is permanent and may not be weakened.

M6 is a consumer, not an interpreter.
M6 may act, but may not assert understanding.
