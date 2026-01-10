MANDATE EMISSION RULES

(Constitution-Compliant, Non-Interpretive)

0. Purpose and Boundary

Mandate Emission is a pure functional layer that transforms raw-data primitives into mandates, subject to constitutional constraints.

Mandate emission:

Does not execute actions

Does not know arbitration outcomes

Does not know execution success

Does not carry state across cycles

Does not rank mandates (that is arbitration’s role)

It only emits candidates.

1. Inputs

Mandate emission may consume only:

Raw-data primitives (as defined in RAW-DATA PRIMITIVES)

Current position state (symbol-local, finite)

Static configuration parameters (constants, not learned)

Explicitly forbidden inputs:

PnL

Win rate

Confidence

“Signal strength”

Past mandates

Past arbitration results

Execution feedback

2. Output

Mandate emission produces zero or more mandates per symbol per cycle.

Each mandate is independent, stateless, and ephemeral.

3. Mandate Types (Closed Set)

Mandate emission may emit only:

ENTRY
EXIT
REDUCE
HOLD
BLOCK


No other mandate types are permitted.

4. Mandate Emission Invariants
4.1 Statelessness

No mandate may depend on previous mandates

No mandate may persist across cycles

Emission is recomputed from scratch every cycle

4.2 Symbol Locality

Mandates are emitted per symbol

No cross-symbol logic

No portfolio-level reasoning

4.3 Multi-Mandate Allowance

Multiple mandates may be emitted for the same symbol

Conflict resolution is not performed here

Arbitration resolves conflicts later

5. Emission Conditions (General Form)

Every mandate must satisfy the following structure:

IF
    (Primitive Condition Set)
AND
    (Position State Constraint)
AND
    (Temporal Validity Condition)
THEN
    Emit Mandate(type, direction?, metadata)


If any clause fails, mandate is not emitted.

6. ENTRY Mandate Rules
6.1 Preconditions

An ENTRY mandate may be emitted only if:

Position state ∈ { FLAT }

No EXIT mandate condition holds

No BLOCK mandate condition holds

6.2 Primitive Requirements

ENTRY mandates must be justified by explicit raw primitives, e.g.:

Region Revisit of prior raw event

Liquidation Cluster occurrence

Absorption Event presence

Trade Burst presence

Price Velocity exceeding configured threshold

At least one raw-data primitive must be present.

6.3 Direction Constraint

If direction is specified:

It must be derived mechanically from raw primitives

Direction may be LONG, SHORT, or UNSPECIFIED

No bias language permitted.

7. EXIT Mandate Rules
7.1 Preconditions

An EXIT mandate may be emitted only if:

Position state ∈ { ENTERING, OPEN, REDUCING }

7.2 Trigger Conditions (Non-Interpretive)

Examples of valid EXIT triggers:

Region Revisit of prior adverse raw event

Liquidation Cluster opposite to position direction

Price Velocity spike exceeding configured limit

Raw event invalidating original entry condition

No “take profit” or “stop loss” semantics allowed here.

7.3 Supremacy Note

EXIT mandates do not suppress other mandates at emission time.
Supremacy is enforced during arbitration.

8. REDUCE Mandate Rules
8.1 Preconditions

A REDUCE mandate may be emitted only if:

Position state ∈ { OPEN }

8.2 Reduction Semantics

REDUCE mandates do not specify:

Size

Percentage

Quantity

They only state intent to reduce.

Sizing is execution-layer responsibility.

8.3 Trigger Examples

Region Revisit of historically dense liquidation zone

Repeated absorption events without price continuation

High liquidation density without directional price change

Still factual, not interpretive.

9. HOLD Mandate Rules
9.1 Purpose

HOLD expresses explicit non-action, not neutrality.

9.2 Preconditions

HOLD may be emitted when:

Position exists

No ENTRY, EXIT, or REDUCE condition is triggered

No BLOCK condition is triggered

9.3 HOLD Is Optional

HOLD emission is optional.
Absence of HOLD is equivalent to silence.

10. BLOCK Mandate Rules
10.1 Purpose

BLOCK prevents ENTRY under explicitly defined conditions.

10.2 Trigger Examples

Raw data invalid or missing

Volatility exceeding absolute bounds

External constraint windows (e.g. funding, maintenance)

BLOCK does not:

Force EXIT

Force REDUCE

11. Mandate Metadata (Strictly Limited)

Mandates may include opaque metadata:

Trigger identifiers

Primitive references

Timestamp

Metadata must not contain:

Scores

Rankings

Confidence

Semantic labels

12. Temporal Validity

Every mandate must include an expiry condition, such as:

Time window expiration

Price leaving region

Primitive no longer present

Expired mandates are invalid automatically.

13. Forbidden Emission Patterns

❌ Emitting ENTRY and EXIT from same condition
❌ Emitting mandates based on “expected move”
❌ Emitting mandates using derived indicators
❌ Emitting mandates based on prior mandate outcomes
❌ Emitting mandates without raw primitive justification

14. Relationship to Arbitration

Mandate emission:

Does not resolve conflicts

Does not choose actions

Does not enforce authority

It produces a set of candidates.

Arbitration decides what actually happens.

15. Completion Statement

This document fully defines how mandates may be emitted and what they may depend on.

No additional emission logic is permitted outside this specification.