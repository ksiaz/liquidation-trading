# M6 OBSERVATION DEPENDENCY & FAILURE PROPAGATION DECLARATION

**Status:** Binding Constitutional Law  
**Authority:** Supersedes all M6 implementation decisions  
**Governed By:** M6_CONSUMPTION_CONTRACT.md, EPISTEMIC_CONSTITUTION.md  
**Effect:** Permanent and Non-Negotiable

---

## SECTION 1: DEPENDENCY CLASSIFICATION

### Declaration

M6's dependency on Observation is: **HARD**

### Justification

M6 exists to consume observation structural input for execution purposes.

Without observation, M6 has no input.

Without input, M6 has no basis for existence.

M6 is not an autonomous system.

M6 is not a fallback system.

M6 is not a standalone system.

M6 is a dependent subsystem that requires observation input to have any purpose.

### Implications of Hard Dependency

M6 must not exist in a state where it claims capability without observation.

M6 must not exist in a state where it operates independently of observation.

M6 must not exist in a state where it substitutes for observation.

M6 must terminate or halt when observation is unavailable or failed.

---

## SECTION 2: FAILURE PROPAGATION RULES

### Rule Set A: When Observation Status is FAILED

**A1: Termination Requirement**
M6 must cease all operations immediately upon receiving FAILED status from observation.

**A2: No Downgrade Permission**
M6 must not convert FAILED to any non-terminal state.

**A3: No Exception Suppression**
M6 must not catch and suppress SystemHaltedException from observation.

**A4: No Continuation Permission**
M6 must not continue any execution path after observation FAILED is detected.

**A5: No Recovery Attempt**
M6 must not attempt to restart, reset, or recover observation state.

**A6: External Propagation Requirement**
M6 must propagate FAILED status to all external systems without interpretation.

**A7: State Invalidation Requirement**
M6 must treat all previously cached or stored observation data as invalid.

**A8: No Degraded Mode Permission**
M6 must not enter "safe mode", "degraded mode", or any operational state claiming reduced functionality.

**A9: Terminal State Requirement**
M6 must enter a terminal halted state that requires external intervention to clear.

**A10: No Automatic Restart Permission**
M6 must not automatically restart or reinitialize when observation FAILED state clears.

---

### Rule Set B: When Observation Status is UNINITIALIZED

**B1: No Operation Permission**
M6 must not perform any execution operations when observation is UNINITIALIZED.

**B2: No Initialization Assumption**
M6 must not assume UNINITIALIZED is a temporary startup state.

**B3: No Wait-and-Retry Permission**
M6 must not wait for observation to transition from UNINITIALIZED.

**B4: No Default Substitution**
M6 must not use default values as substitutes for absent observation data.

**B5: No Cached Data Permission**
M6 must not use previously cached observation data when status is UNINITIALIZED.

**B6: External Notification Requirement**
M6 must notify external systems that M6 is non-operational due to UNINITIALIZED observation.

**B7: No Capability Claim Permission**
M6 must not claim readiness, capability, or availability when observation is UNINITIALIZED.

**B8: Indefinite Wait Tolerance Requirement**
M6 must tolerate UNINITIALIZED state indefinitely without timeout or fallback.

**B9: No Status Inference Permission**
M6 must not infer that UNINITIALIZED means "starting up" or "will become available".

**B10: No Partial Operation Permission**
M6 must not operate with "reduced functionality" claiming partial observation availability.

---

### Rule Set C: When Observation is Silent (Empty Buffers, No Events)

**C1: No Silence Interpretation Permission**
M6 must not interpret observation silence as market condition or data quality.

**C2: No Cached Substitution Permission**
M6 must not substitute previous non-silent observation data when current data is silent.

**C3: No Default Injection Permission**
M6 must not inject default or assumed values when observation provides none.

**C4: No Interpolation Permission**
M6 must not interpolate or extrapolate from historical observation data.

**C5: No "Safe Assumption" Permission**
M6 must not proceed on assumptions when observation is silent.

**C6: Explicit Silence Acknowledgment Requirement**
M6 must externally acknowledge when operating with silent observation.

**C7: No Activity Inference Permission**
M6 must not infer market activity levels from observation silence.

**C8: No Quality Inference Permission**
M6 must not infer data quality from presence or absence of observation data.

**C9: No Continuation Implication**
M6 must not imply that operation can continue normally when observation is silent.

**C10: Logic-Defined Response Requirement**
M6 response to silence must be explicitly defined in M6 logic, not assumed or defaulted.

---

## SECTION 3: PROHIBITED WORKAROUNDS

### Category 1: Retry Mechanisms

**Prohibited:**
- Automatic retry of observation queries
- Exponential backoff retry strategies
- Periodic polling with retry count
- Timeout-based retry loops
- Circuit breaker patterns that retry after cooldown
- Health check retries
- Liveness probe retries
- Any mechanism that assumes observation will recover via repeated querying

---

### Category 2: Caching Mechanisms

**Prohibited:**
- Caching last known good observation state
- Caching observation data with time-to-live
- Caching observation data with staleness tolerance
- In-memory observation data buffers used as fallback
- Persistent storage of observation state for replay
- "Last known state" retrieval on observation failure
- Any mechanism that uses stale observation data as current

---

### Category 3: Fallback Mechanisms

**Prohibited:**
- Fallback to default values
- Fallback to historical averages
- Fallback to statistical estimates
- Fallback to hardcoded constants
- Fallback to previous observation state
- Fallback to alternative data sources
- Fallback to "safe" operational modes
- Any mechanism that substitutes for absent observation

---

### Category 4: Degradation Modes

**Prohibited:**
- "Safe mode" operation
- "Degraded mode" operation
- "Reduced functionality" mode
- "Conservative mode" operation
- "Observation-optional" mode
- "Manual override" mode
- Any operational mode claiming functionality without observation

---

### Category 5: Default Values

**Prohibited:**
- Zero as default for absent counters
- Empty list as default for absent events
- False as default for absent flags
- NULL/None with assumed safe interpretation
- "No data" as meaningful value
- Any default that enables continued operation

---

### Category 6: Timeout Mechanisms

**Prohibited:**
- Timeout waiting for observation initialization
- Timeout waiting for observation recovery
- Timeout for observation query response
- Timeout-triggered fallback behavior
- Timeout-triggered default substitution
- Any timeout that ends in continued M6 operation

---

### Category 7: State Downgrade

**Prohibited:**
- Converting FAILED to WARNING
- Converting FAILED to DEGRADED
- Converting FAILED to RECOVERING
- Converting SystemHaltedException to boolean flag
- Converting SystemHaltedException to error code
- Logging FAILED as informational
- Any mechanism that reduces FAILED severity

---

### Category 8: Assumption-Based Continuation

**Prohibited:**
- "Observation is probably fine" assumptions
- "Silence means no activity" assumptions
- "UNINITIALIZED is temporary" assumptions
- "We can continue for a bit" assumptions
- "This is safe enough" assumptions
- "Operator will notice if wrong" assumptions
- Any assumption that permits M6 operation without valid observation

---

### Category 9: Alternative Data Sources

**Prohibited:**
- Querying market data directly
- Bypassing observation layer
- Reading from observation internal state when external interface fails
- Using M6 internal state as observation substitute
- Using external APIs as observation replacement
- Any data source that is not the observation external interface

---

### Category 10: Operator Override

**Prohibited:**
- "Force start" commands that bypass observation checks
- "Manual mode" that operates without observation
- Configuration flags that disable observation requirement
- Emergency overrides that weaken hard dependency
- Administration commands that restart M6 without observation validation
- Any mechanism that allows operator to bypass observation dependency

---

### Category 11: Gradual Degradation

**Prohibited:**
- Reducing position sizes when observation degrades
- Limiting actions when observation is uncertain
- Scaling back operations when observation is silent
- Progressive reduction of functionality
- Any gradual response that implies continued operation

---

### Category 12: Health Check Bypasses

**Prohibited:**
- Assuming observation is healthy if query succeeds
- Assuming observation is operational if not FAILED
- Inverting absence of failure into presence of health
- Converting lack of error into positive readiness claim
- Any health inference from non-failure state

---

## BINDING NATURE

This declaration is constitutionally binding.

No M6 implementation may weaken these constraints.

No operational pressure justifies violation of these rules.

No "one-time exception" is permitted.

No "testing mode" may bypass these constraints.

No "manual intervention" may override hard dependency.

Violation of this declaration voids M6 trustworthiness permanently.

---

## AMENDMENT PROHIBITION

This declaration may not be amended to:
- Weaken hard dependency classification
- Add conditional or soft dependency modes
- Introduce exception cases
- Add timeout-based fallbacks
- Permit any form of observation substitution
- Reduce failure propagation requirements

Amendments may only strengthen constraints, never weaken them.

---

**END OF DEPENDENCY & FAILURE PROPAGATION DECLARATION**

M6 depends absolutely on Observation.
M6 must fail loudly when Observation fails.
M6 must remain silent when Observation is absent.
M6 must never operate on assumptions.
