EXECUTION ACTION CONTRACT

(Mechanical Translation Layer — No Semantics)

0. Purpose and Boundary

Execution is a pure actuator layer.

It translates a single arbitration output into exchange-level operations.

Execution:

Does not evaluate signals

Does not inspect raw data

Does not arbitrate mandates

Does not infer intent

Does not optimize outcomes

Execution either:

Performs the exact permitted action, or

Fails atomically

1. Inputs

Execution consumes exactly one input per symbol per cycle:

ExecutionAction ∈ { ENTRY, EXIT, REDUCE, HOLD, NO_ACTION }


Plus:

Current position state

Exchange connectivity state

No other inputs are permitted.

2. Outputs

Execution produces one of:

Exchange order(s)

No operation

Terminal failure signal

Execution never emits mandates, signals, or interpretations.

3. Global Execution Invariants
3.1 Single-Action Invariant

Execution may perform at most one logical action per symbol per cycle.

Forbidden:

ENTRY + REDUCE

EXIT + REDUCE

Partial branching

3.2 Atomicity

Each execution action is atomic:

Either fully submitted

Or not submitted at all

Partial execution is forbidden.

3.3 Idempotence (Cycle-Scoped)

If the same action is presented multiple times within the same cycle, execution must behave identically.

Execution must not infer retries or escalation.

3.4 Statelessness

Execution retains no internal memory beyond:

Open exchange orders

Current position state (external fact)

Execution must not store:

Past actions

Past failures

Past fills

4. Action Semantics
4.1 ENTRY

Preconditions:

Position state = FLAT

No open position exists for symbol

Execution Behavior:

Submit entry order(s) as defined by execution configuration

Entry direction is taken from mandate payload

Stop / protection orders are allowed only if explicitly attached

Postconditions:

Position state transitions to ENTERING

Forbidden:

Scaling logic

Conditional entries

Multi-direction entries

4.2 EXIT

Preconditions:

Position state ∈ { ENTERING, OPEN, REDUCING }

Execution Behavior:

Submit full-size close order

Cancel any resting child orders if required by exchange semantics

Postconditions:

Position state transitions to CLOSING

Properties:

EXIT is terminal

EXIT cannot be overridden or deferred

4.3 REDUCE

Preconditions:

Position state ∈ { OPEN, REDUCING }

Execution Behavior:

Submit reduction order

Reduction magnitude must be explicitly provided

No inference or sizing logic permitted here

Postconditions:

Position state transitions to REDUCING

Forbidden:

Full exit via REDUCE

Implicit conversion to EXIT

4.4 HOLD

Execution Behavior:

No exchange interaction

No state change

Properties:

HOLD is explicit inaction

HOLD is not a default

HOLD is suppressed by higher-authority actions

4.5 NO_ACTION

Execution Behavior:

No exchange interaction

No state change

Properties:

NO_ACTION is a valid outcome

Indicates absence of admissible mandates

5. Position State Transitions

Execution enforces only the following transitions:

FLAT       → ENTERING
ENTERING   → OPEN | CLOSING
OPEN       → REDUCING | CLOSING
REDUCING   → OPEN | CLOSING
CLOSING    → FLAT


Execution must not invent or skip states.

6. Failure Semantics

Execution failure is terminal for the cycle.

6.1 Failure Conditions

Exchange rejection

Connectivity loss

Invalid order parameters

Inconsistent position state

6.2 Failure Handling Rules

Failure must be surfaced immediately

No retries are permitted at this layer

No silent fallbacks

No partial state updates

Failure propagation is mandatory.

7. Prohibited Execution Behaviors

❌ Interpreting market conditions
❌ Adjusting size based on confidence
❌ Delaying EXIT
❌ Combining actions
❌ Retry loops
❌ Recovery heuristics
❌ Strategy-specific logic

Execution is not smart. It is obedient.

8. Separation of Concerns (Hard Boundary)
Layer	Allowed Responsibility
Observation	Record facts
Mandate Emission	Express intent
Arbitration	Select action
Execution	Perform action

Execution must never leak upward or downward.

9. Execution Contract Completeness

If arbitration outputs a valid action:

Execution must attempt to perform it

Execution must not reinterpret it

Execution must not block it except on hard failure

10. Completion Statement

This contract fully defines execution behavior.

Together with:

RAW-DATA PRIMITIVES

MANDATE EMISSION RULES

MANDATE ARBITRATION & CONFLICT RESOLUTION

…it completes the end-to-end decision pipeline from raw data to exchange action.

No additional execution logic is permitted outside this contract.