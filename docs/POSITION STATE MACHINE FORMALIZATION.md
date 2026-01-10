POSITION STATE MACHINE FORMALIZATION

(Symbol-Local, Deterministic, Non-Interpretive)

1. Scope

The Position State Machine (PSM):

Is symbol-local

Is single-position

Is single-direction

Governs only lifecycle state, not intent or sizing

Is enforced by Execution, not Arbitration

No layer may bypass or weaken this machine.

2. State Set

The complete and exclusive set of position states is:

PositionState ∈ {
    FLAT,
    ENTERING,
    OPEN,
    REDUCING,
    CLOSING
}


No additional states are permitted.

3. State Definitions
3.1 FLAT

Definition:

No open position

No pending exposure

Properties:

Entry is possible

Reduction and exit are impossible

3.2 ENTERING

Definition:

Entry order submitted

Position not yet confirmed as open

Properties:

Exposure intent exists

Fill may be partial or pending

Notes:

ENTERING is transient

ENTERING is not OPEN

3.3 OPEN

Definition:

Position fully or partially open

Exposure exists

Properties:

Reduction is possible

Exit is possible

Entry is forbidden

3.4 REDUCING

Definition:

Reduction order submitted

Position still exists

Properties:

Further reduction may occur

Exit is still possible

3.5 CLOSING

Definition:

Full exit order submitted

Position teardown in progress

Properties:

Terminal transitional state

No other actions permitted

4. Legal Transitions (Complete Graph)

The only legal transitions are:

FLAT       → ENTERING
ENTERING   → OPEN
ENTERING   → CLOSING
OPEN       → REDUCING
OPEN       → CLOSING
REDUCING   → OPEN
REDUCING   → CLOSING
CLOSING    → FLAT


No other transitions exist.

5. Forbidden Transitions

The following transitions are strictly forbidden:

FLAT       → OPEN
FLAT       → REDUCING
FLAT       → CLOSING

ENTERING   → FLAT   (without CLOSING)
OPEN       → ENTERING

REDUCING   → ENTERING
CLOSING    → OPEN
CLOSING    → REDUCING


Any attempt to perform a forbidden transition is a hard invariant violation.

6. Action ↔ State Compatibility
Action	Required Current State	Resulting State
ENTRY	FLAT	ENTERING
EXIT	ENTERING, OPEN, REDUCING	CLOSING
REDUCE	OPEN, REDUCING	REDUCING
HOLD	Any	No change
NO_ACTION	Any	No change

Execution must validate compatibility before action submission.

7. Single-Position Invariant

At most one position per symbol may exist.

Therefore:

ENTRY while not FLAT is forbidden

Multiple concurrent ENTERING states are forbidden

Directional flipping without EXIT is forbidden

8. Direction Invariance

Once a position enters ENTERING:

Direction is fixed until FLAT

No reversal without full EXIT

REDUCE does not alter direction

9. Terminality of EXIT

EXIT is terminal for the current lifecycle.

Once CLOSING is entered:

No REDUCE

No ENTRY

No HOLD override

Only transition permitted: CLOSING → FLAT

10. Failure Semantics

If execution fails during:

ENTERING → state remains ENTERING

REDUCING → state remains REDUCING

CLOSING → state remains CLOSING

No rollback or reinterpretation is permitted.

11. Determinism Invariant

Given:

Current state

One execution action

The resulting state is deterministic.

No probabilistic or heuristic transitions are allowed.

12. No Implicit Transitions

State transitions occur only via:

Confirmed exchange interaction

Explicit execution action

Time, silence, or inference may not cause transitions.

13. State Observability

Position state is:

Externally observable

Queryable

Not derived

Not inferred

Execution must not fabricate or infer state.

14. Completeness Statement

This state machine is:

Closed

Minimal

Exhaustive

Non-overlapping

Strategy-agnostic

No additional lifecycle logic is permitted outside this specification.

15. Constitutional Lock

Any change to:

State set

Transitions

Action compatibility

Requires constitutional amendment, not implementation discretion.