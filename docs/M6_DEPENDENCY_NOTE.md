# M6 DEPENDENCY NOTE

**Authority:** M6_DEPENDENCY_DECLARATION.md, M6_EXISTENCE_DETERMINATION.md  
**Status:** Binding

---

## SECTION 1: INVOCATION CONTRACT

M6 is invoked only when an ObservationSnapshot is explicitly supplied.

M6 cannot be invoked without observation.

The signature `execute(observation_snapshot: ObservationSnapshot) -> None` enforces this dependency at the type level.

No alternate inputs are permitted.

---

## SECTION 2: PROHIBITED INVOCATION PATTERNS

The following invocation patterns are constitutionally forbidden:

**Loops:**
- M6 must not run in a loop
- No while/for constructs around M6 invocation
- No repeated automatic calls

**Retries:**
- M6 must not retry on failure
- No error recovery invocation
- No fallback invocation

**Background Execution:**
- M6 must not run as background task
- No asyncio.create_task(m6...)
- No threading
- No multiprocessing

**Caching:**
- M6 must not cache observation data
- No storage of previous snapshots
- No replay mechanisms

**Scheduling:**
- M6 must not be scheduled
- No timers
- No cron-like execution
- No periodic invocation

**Hooks & Callbacks:**
- M6 must not be registered as callback
- No observer pattern
- No event subscriptions
- No automatic triggers

---

## SECTION 3: FAILURE PROPAGATION STATEMENT

When `observation_snapshot.status == ObservationStatus.FAILED`:
- M6 halts immediately
- M6 raises SystemHaltedException
- This exception is terminal
- No recovery is permitted
- No downgrade is permitted
- No retry is permitted

M6 exists only as an ephemeral function execution context.

M6 terminates completely when the function returns.

---

END OF DEPENDENCY NOTE
