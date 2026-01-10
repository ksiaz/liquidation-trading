# M6 EXISTENCE & LIFECYCLE DETERMINATION

**Status:** Constitutional Determination  
**Authority:** Fixes M6 existence form permanently  
**Governed By:** EPISTEMIC_CONSTITUTION.md, M6_CONSUMPTION_CONTRACT.md, M6_DEPENDENCY_DECLARATION.md  
**Effect:** Binding

---

## SECTION 1: EXISTENCE MODELS CONSIDERED

### Model 1: Long-Lived Process
Description: M6 exists as persistent daemon process running continuously.

Compatibility: **INCOMPATIBLE**

Reasons:
- Persists across observation FAILED states (violates termination requirement)
- Persists across observation silence (creates opportunity for cached state)
- Enables hidden internal state accumulation
- Survives observation lifecycle independently
- Cannot guarantee state reset on observation state changes

---

### Model 2: Short-Lived Process
Description: M6 exists as process that starts and stops but maintains no state between invocations.

Compatibility: **COMPATIBLE**

Reasons:
- Can terminate when observation FAILED
- Can refuse to start when observation UNINITIALIZED
- Forces process boundary prevents state persistence
- Operating system enforces lifecycle boundaries

---

### Model 3: Stateless Invocation
Description: M6 exists only during function call execution, no process persistence.

Compatibility: **COMPATIBLE**

Reasons:
- No state survives invocation boundary
- Terminates immediately after execution
- Cannot persist across observation state changes
- Minimal existence window reduces epistemic risk

---

### Model 4: Event-Scoped Execution
Description: M6 exists only for duration of single observation event processing.

Compatibility: **COMPATIBLE**

Reasons:
- Lifetime bounded by observation event
- Terminates when observation becomes silent
- Cannot accumulate state across events
- Forces observation dependency per event

---

### Model 5: Supervisor/Child Model
Description: Supervisor process manages M6 child processes, restarts on failure.

Compatibility: **INCOMPATIBLE**

Reasons:
- Supervisor enables automatic restart after FAILED (violates no-recovery rule)
- Supervisor introduces retry logic (violates retry prohibition)
- Supervisor persists across observation FAILED
- Creates mechanism for observation failure bypass

---

### Model 6: Persistent State Machine
Description: M6 maintains explicit state machine across observation interactions.

Compatibility: **INCOMPATIBLE**

Reasons:
- State persists across observation FAILED (violates state invalidation requirement)
- State persists across observation silence (enables cached assumptions)
- Creates memory across observation lifecycle
- Enables gradual degradation patterns

---

### Model 7: Database-Backed Execution
Description: M6 stores state in external database, reads at each invocation.

Compatibility: **INCOMPATIBLE**

Reasons:
- Database state persists across observation FAILED
- Enables retrieval of previous observation data
- Creates external memory mechanism
- Violates state invalidation requirement

---

### Model 8: Message-Driven Ephemeral Execution
Description: M6 spawned per message/query, dies after response.

Compatibility: **COMPATIBLE**

Reasons:
- Existence tied to single request/response
- No state survives message boundary
- Cannot persist observation data
- Forced re-evaluation per invocation

---

## SECTION 2: MINIMAL COMPATIBLE MODEL

### Selected Model: Event-Scoped Stateless Invocation

### Definition
M6 exists only during execution of single observation-consuming function call.
M6 ceases to exist when function returns.
M6 maintains no state between invocations.

### Justification (Failure Containment)
- Observation FAILED cannot be survived because M6 does not exist between invocations
- Cannot retry observation queries because M6 terminates after single query
- Cannot cache observation data because M6 has no persistent storage
- Failure propagates immediately because execution context terminates

### Justification (Silence Preservation)
- Cannot operate during observation silence because invocation requires observation input
- Cannot substitute cached values because no cache exists
- Cannot assume previous state because no previous state persists
- Silence forces non-invocation

### Justification (Impossibility of Hidden State)
- All state visible within single function scope
- No persistent memory across invocations
- No hidden accumulators
- No gradual degradation possible
- No recovery loops possible
- Operating system or runtime enforces state destruction at function exit

### Constitutional Alignment
- Hard dependency enforced: M6 cannot be invoked without observation parameter
- Failure propagation enforced: M6 terminates when function exits, cannot continue
- Silence handling enforced: M6 not invoked when observation has no data
- State invalidation enforced: All state destroyed at function boundary

---

## SECTION 3: FORBIDDEN LIFECYCLE PROPERTIES

### Category A: Persistence Across Observation State Changes

M6 must never:
- Persist across observation transition to FAILED
- Persist across observation transition to UNINITIALIZED
- Persist across observation silence periods
- Maintain state when observation status changes
- Survive observation termination

---

### Category B: Memory Across Invocations

M6 must never:
- Remember previous observation states
- Accumulate counters across invocations
- Cache observation data between calls
- Maintain historical buffers
- Store decision history
- Aggregate statistics over time
- Track performance metrics across executions

---

### Category C: Automatic Recovery Mechanisms

M6 must never:
- Auto-restart after termination
- Auto-retry after failure
- Auto-resume after pause
- Auto-reconnect after disconnect
- Self-heal after error
- Automatically clear FAILED state

---

### Category D: Graceful Degradation

M6 must never:
- Gradually reduce functionality over time
- Slowly degrade in response to observation issues
- Transition between "modes" based on observation health
- Scale back operations based on observation availability
- Implement fallback tiers

---

### Category E: Supervision and Watchdogs

M6 must never:
- Have supervisor process that restarts M6
- Have watchdog that monitors M6 health
- Have orchestrator that manages M6 lifecycle
- Have parent process that survives M6 termination
- Have external restart mechanism

---

### Category F: State Serialization

M6 must never:
- Serialize state to disk
- Serialize state to database
- Serialize state to network storage
- Serialize state to shared memory
- Checkpoint execution state
- Persist partial results

---

### Category G: Cross-Invocation Communication

M6 must never:
- Pass messages between invocations
- Share memory between invocations
- Use queues that survive invocations
- Use channels that persist across calls
- Communicate via files between executions

---

### Category H: Warmth or Calibration

M6 must never:
- Have "warm-up period"
- Require calibration across invocations
- Track "readiness" across calls
- Accumulate confidence over time
- Build internal models across invocations

---

### Category I: Timeout-Based Survival

M6 must never:
- Wait for timeout before terminating
- Delay termination hoping for observation recovery
- Persist during grace period
- Continue operating during countdown
- Implement keep-alive mechanisms

---

### Category J: External State Dependencies

M6 must never:
- Depend on external state that persists across invocations
- Depend on configuration that changes M6 lifecycle
- Depend on flags that enable persistence
- Depend on operator commands that extend lifetime
- Depend on external signaling for termination

---

## PERMANENT DETERMINATION

M6 existence form is permanently fixed as: **Event-Scoped Stateless Invocation**

This determination is constitutional and binding.

M6 is not a service.
M6 is not a daemon.
M6 is not a persistent process.
M6 is not a state machine.

M6 is a pure function execution context that exists momentarily and vanishes completely.

---

**END OF EXISTENCE & LIFECYCLE DETERMINATION**

M6 may exist only ephemerally.
M6 must forget completely between invocations.
M6 must terminate cleanly and absolutely.
