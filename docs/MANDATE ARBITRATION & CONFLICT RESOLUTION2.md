MANDATE ARBITRATION & CONFLICT RESOLUTION

(Deterministic, Stateless, Authority-Bound)

1. Purpose

Mandate Arbitration exists to resolve simultaneous mandates emitted within a single evaluation cycle into at most one execution action per symbol.

Arbitration:

Does not generate mandates

Does not interpret market meaning

Does not evaluate profitability

Does not override risk invariants

It is a pure resolution mechanism.

2. Arbitration Scope Invariants

Invariant A1 — Symbol Locality

Arbitration operates per symbol, independently.

No cross-symbol arbitration is permitted.

Invariant A2 — Single-Cycle Scope

Arbitration consumes only:

Mandates emitted in the current cycle

Current position state

Current snapshot

No historical mandates, memory, or carryover is allowed.

Invariant A3 — Statelessness

Arbitration holds no internal state.

Given identical inputs → identical output.

3. Mandate Primitive (Input)

Each mandate has the following attributes:

mandate_type ∈ { ENTRY, EXIT, REDUCE, HOLD, BLOCK }
authority_rank ∈ ℕ  (strict total order)
trigger_id          (opaque)
expiry_condition


Mandates are:

Stateless

Non-persistent

Evaluated atomically

4. Authority Ordering Invariant

Invariant A4 — Total Authority Order

Mandate types are totally ordered by authority:

EXIT
REDUCE
BLOCK
HOLD
ENTRY


Higher authority mandates suppress lower authority mandates.

No mandate may override a higher-ranked mandate.

5. Single-Action Invariant

Invariant A5 — One Action Per Symbol Per Cycle

Arbitration may emit at most one execution action per symbol.

Forbidden outputs include:

ENTRY + REDUCE

REDUCE + EXIT

Multiple EXITs

Multiple REDUCEs

NO_ACTION is a valid and complete outcome.

6. State-Aware Arbitration Filter

Before arbitration, mandates are filtered by position state.

Position State	Admissible Mandates
FLAT	ENTRY, HOLD, BLOCK
ENTERING	EXIT, BLOCK
OPEN	REDUCE, EXIT, HOLD, BLOCK
REDUCING	REDUCE, EXIT
CLOSING	∅

Non-admissible mandates are discarded immediately.

Discarded mandates are not considered further.

7. Arbitration Resolution Algorithm

Input:
Set M of admissible mandates

Steps:

If M = ∅ → emit NO_ACTION

Determine highest authority rank R in M

Let S = { m ∈ M | m.authority_rank = R }

Resolve S using same-type conflict rules

Emit resulting action (or NO_ACTION)

8. Same-Type Conflict Rules
8.1 ENTRY Conflicts

If multiple ENTRY mandates exist:

Different directions → NO_ACTION

Same direction → retain exactly one (identity arbitrary but stable)

ENTRY never overrides EXIT or REDUCE.

8.2 REDUCE Conflicts

Multiple REDUCE mandates collapse into one REDUCE.

Reduction magnitude is not resolved here.

8.3 EXIT Conflicts

Multiple EXIT mandates collapse into one EXIT.

EXIT is idempotent.

8.4 HOLD Conflicts

HOLD is:

Ignored if any higher-authority mandate exists

Never emitted alongside another action

8.5 BLOCK Conflicts

BLOCK:

Suppresses ENTRY and HOLD

Does not suppress EXIT

Does not suppress REDUCE

BLOCK does not trigger execution.

9. EXIT Supremacy Invariant

Invariant A6 — EXIT Dominance

If any EXIT mandate survives filtering:

EXIT is emitted

All other mandates are suppressed

EXIT terminates the current position lifecycle

EXIT cannot be overridden.

10. BLOCK Isolation Rule

Invariant A7 — BLOCK Scope

BLOCK:

Prevents ENTRY

Prevents re-ENTRY

Suppresses HOLD

BLOCK does not:

Trigger EXIT

Trigger REDUCE

Modify position state

11. Mandate Expiry Constraint

Invariant A8 — Mandatory Expiry

Every mandate must declare an expiry condition.

A mandate is invalidated when:

Trigger condition no longer holds

Position state becomes incompatible

Zone or structural boundary is exited

No mandate persists by default.

12. Arbitration Output Primitive

Arbitration produces an explicit result, even if no action is taken.

Arbitration Result Fields:

symbol
position_state
input_mandates
discarded_mandates
selected_mandate_type | NO_ACTION


Output emission is mandatory every cycle.

13. Forbidden Arbitration States

The following are constitutional violations:

Emitting multiple actions

Emitting action without a mandate

Emitting ENTRY when EXIT exists

Retaining mandates across cycles

Using scores, confidence, or “strength”

Using PnL, expectancy, or outcomes

14. Determinism Guarantee

Invariant A9 — Deterministic Resolution

Arbitration outcome is fully determined by:

Mandate set

Authority ordering

Position state

No randomness, heuristics, or discretion permitted.

15. Constitutional Lock

Any change to:

Authority ordering

Conflict rules

Single-action invariant

Requires a constitutional amendment.