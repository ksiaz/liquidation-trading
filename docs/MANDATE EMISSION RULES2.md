MANDATE EMISSION RULES

(Raw-Data Grounded, Non-Interpretive, Stateless)

1. Purpose

Mandate Emission Rules define when a mandate may be emitted and when it must not.

A mandate is:

A proposal, not an action

Stateless

Symbol-local

Cycle-local

Non-persistent

Mandates do not:

Execute trades

Allocate capital

Override risk invariants

Encode strategy intent

They only express structurally admissible possibilities.

2. Mandate Types (Canonical Set)

Allowed mandate types are fixed:

ENTRY
EXIT
REDUCE
HOLD
BLOCK


No additional mandate types are permitted.

3. Raw-Data Grounding Invariant

Invariant M1 — Raw Data Only

A mandate may be emitted only if its trigger condition depends exclusively on:

Raw price stream (ticks, trades, candles without transformation)

Raw liquidation prints

Raw order book updates

Raw funding / mark price feeds

Forbidden inputs:

Indicators

Signals

Scores

Probabilities

Aggregates that encode interpretation

“Confidence”, “strength”, or “bias”

Violation → mandate emission is invalid.

4. Non-Interpretation Invariant

Invariant M2 — No Semantic Claims

Mandates must not encode meaning such as:

“Bullish / Bearish”

“Strong / Weak”

“Likely / Probable”

“Confirmed / Failed”

Mandates encode conditions, not conclusions.

5. Symbol-Locality Invariant

Invariant M3 — Symbol Isolation

Each mandate applies to exactly one symbol.

Forbidden:

Cross-symbol reasoning

Portfolio-level mandate emission

Correlated triggers

6. State-Aware Emission Constraint

Invariant M4 — Position State Compatibility

Mandates may be emitted only if compatible with current position state:

Position State	Allowed Emissions
FLAT	ENTRY, HOLD, BLOCK
ENTERING	EXIT, BLOCK
OPEN	REDUCE, EXIT, HOLD, BLOCK
REDUCING	REDUCE, EXIT
CLOSING	∅

Non-admissible mandates must not be emitted.

7. Risk Pre-Check Invariant

Invariant M5 — Risk Gate Before Emission

ENTRY and REDUCE mandates may be emitted only if:

All Risk & Exposure Invariants can be satisfied post-execution

Required sizing is computable deterministically

Liquidation buffers remain compliant

If risk cannot be evaluated → emission forbidden.

8. ENTRY Mandate Rules

Invariant M6 — ENTRY Preconditions

An ENTRY mandate may be emitted only if:

Position state = FLAT

No BLOCK mandate exists for symbol

Risk invariants admit at least one valid size

No EXIT mandate is simultaneously emitted

ENTRY does not imply direction superiority or expectation of profit.

9. EXIT Mandate Rules

Invariant M7 — EXIT Emission Conditions

EXIT mandates may be emitted when:

Risk invariants are violated or about to be violated

Structural invalidation occurs (raw condition failure)

Position lifecycle demands termination

EXIT requires no confirmation, no confidence, no priority check.

10. REDUCE Mandate Rules

Invariant M8 — REDUCE Semantics

REDUCE mandates:

Propose exposure reduction

Do not specify magnitude

Must improve compliance with risk invariants

REDUCE is forbidden if:

Reduction cannot restore compliance

Full EXIT is required

11. HOLD Mandate Rules

Invariant M9 — HOLD Is Neutral

HOLD means:

“No change proposed this cycle”

HOLD:

Carries no authority

Is suppressed by any other mandate

Cannot block ENTRY or EXIT

12. BLOCK Mandate Rules

Invariant M10 — BLOCK Semantics

BLOCK mandates:

Prevent ENTRY only

Do not affect existing positions

Do not imply danger or risk

BLOCK is used to enforce:

Cool-down

Structural invalidity

Zone exhaustion

13. Mutual Exclusivity Invariant

Invariant M11 — No Self-Conflict

A single emission source may not emit:

ENTRY + EXIT

EXIT + REDUCE

ENTRY + BLOCK

Conflict resolution is handled after emission, but emission itself must be minimal.

14. Statelessness Invariant

Invariant M12 — No Memory

Mandate emission must not depend on:

Prior mandates

Previous cycles

Cached conditions

Historical outcomes

Each cycle is evaluated independently.

15. Temporal Neutrality

Invariant M13 — No Time-Based Emission

Mandates must not depend on:

Time in trade

Time since signal

Session timing

Clock-based heuristics

Only raw event ordering is admissible.

16. Expiry Requirement

Invariant M14 — Explicit Expiry

Every mandate must declare:

A structural expiry condition

A raw-data invalidation rule

If expiry condition is met → mandate is discarded automatically.

17. Silence Rule

Invariant M15 — Silence Is Valid

If no admissible mandate exists:

Emit no mandate

Do not fabricate HOLD

Do not infer opportunity

Silence is a first-class outcome.

18. No Guarantee Invariant

Invariant M16 — No Outcome Assumptions

Mandates do not guarantee:

Fill

Profit

Continuation

Protection

They only authorize arbitration.

19. Auditability Requirement

Every mandate must be reconstructable from:

Raw inputs

Position state

Emission rules

No hidden logic.

20. Constitutional Lock

Any change to:

Mandate types

Emission admissibility

Raw-data requirements

Requires constitutional amendment.