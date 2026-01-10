MANDATE ARBITRATION & CONFLICT RESOLUTION

(Deterministic, Stateless, Symbol-Local)

0. Purpose and Boundary

Mandate Arbitration is a deterministic reduction function.

It transforms:

A set of mandates (emitted in the same evaluation cycle)

The current position state

Into:

At most one execution action, or

NO_ACTION

Arbitration:

Does not emit mandates

Does not access raw data

Does not access historical context

Does not access execution outcomes

Does not modify state

1. Inputs

Arbitration consumes only:

Mandates emitted in the current cycle (symbol-local)

Current position lifecycle state

No other inputs are permitted.

2. Outputs

Arbitration emits exactly one of:

ENTRY
EXIT
REDUCE
HOLD
NO_ACTION


Per symbol, per cycle.

3. Arbitration Invariants
3.1 Determinism

Given identical inputs, arbitration must always produce the same output.

No randomness.
No heuristics.
No thresholds.

3.2 Statelessness

No mandate survives beyond the current cycle

Arbitration retains no memory

Past arbitration outcomes are inaccessible

3.3 Symbol Isolation

Arbitration is strictly per symbol

No cross-symbol coordination

No portfolio-level reasoning

4. Authority Ordering (Total Order)

Mandates are ordered by strict authority, highest first:

EXIT
REDUCE
BLOCK
HOLD
ENTRY


This order is:

Total

Strict

Non-negotiable

Higher authority mandates suppress lower authority mandates.

5. Position-State Admissibility Filter

Before arbitration, mandates are filtered by position lifecycle state.

5.1 Admissible Mandates by State
Position State	Admissible Mandates
FLAT	ENTRY, HOLD, BLOCK
ENTERING	EXIT, BLOCK
OPEN	EXIT, REDUCE, HOLD, BLOCK
REDUCING	EXIT, REDUCE
CLOSING	∅

Mandates not admissible in the current state are discarded.

Discarding is silent and final.

6. Empty-Set Rule

If no mandates remain after filtering:

→ NO_ACTION


This is a valid and expected outcome.

7. Primary Resolution Algorithm

Given a non-empty admissible mandate set M:

Identify highest authority rank present in M

Retain only mandates of that rank

Apply same-type conflict rules (Section 8)

Emit resulting action or NO_ACTION

8. Same-Type Conflict Resolution
8.1 EXIT Conflicts

If ≥1 EXIT mandates exist:

Collapse into a single EXIT

All other mandates are discarded

EXIT is terminal for the cycle.

8.2 REDUCE Conflicts

If multiple REDUCE mandates exist:

Collapse into a single REDUCE

Reduction magnitude is not resolved here

8.3 BLOCK Conflicts

BLOCK:

Suppresses ENTRY and HOLD

Does not suppress EXIT or REDUCE

Does not emit an action itself

If BLOCK is highest authority remaining:

→ NO_ACTION

8.4 HOLD Conflicts

HOLD:

Is ignored if any higher-authority mandate exists

Never suppresses other mandates

If HOLD is the only remaining mandate:

→ HOLD

8.5 ENTRY Conflicts

If multiple ENTRY mandates exist:

If directions differ → NO_ACTION

If directions match → retain one (identity arbitrary but stable)

ENTRY may only be emitted if no higher authority mandate exists.

9. Single-Action Invariant

Arbitration must never emit:

Multiple actions

Combined actions

Conditional actions

Exactly one of:

ENTRY | EXIT | REDUCE | HOLD | NO_ACTION

10. EXIT Supremacy Rule

If an EXIT mandate survives admissibility filtering:

EXIT is emitted

All other mandates are suppressed

No exceptions

11. BLOCK Isolation Rule

BLOCK:

Prevents ENTRY

Prevents HOLD

Does not trigger EXIT

Does not trigger REDUCE

BLOCK is purely preventative, never assertive.

12. Temporal Scope

Arbitration operates over mandates from one evaluation cycle only.

It is forbidden to:

Accumulate mandates across cycles

Re-evaluate expired mandates

Carry unresolved conflicts forward

13. Forbidden Arbitration Behaviors

❌ Using mandate metadata for ranking
❌ Using PnL, risk, confidence, or scores
❌ Partial execution (e.g. ENTRY + REDUCE)
❌ Emitting action without mandate
❌ Re-ordering authority dynamically
❌ Introducing tie-breakers beyond spec

14. Arbitration Output Record (Optional)

For auditing only (non-decision-making), an arbitration record may include:

Input mandates

Discarded mandates

Selected mandate (or NO_ACTION)

Position state

This record must not influence future cycles.

15. Completion Statement

This document fully specifies mandate arbitration and conflict resolution.

Combined with:

RAW-DATA PRIMITIVES

MANDATE EMISSION RULES

It completes the Observation → Mandate → Action decision boundary.

No additional arbitration logic is permitted outside this specification.