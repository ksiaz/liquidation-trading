IMPLEMENTATION CORRECTNESS CHECKLIST

Document Class: Engineering Verification
Purpose: Ensure any concrete implementation strictly conforms to the frozen constitution
Scope: Observation → Primitives → Mandates → Arbitration → Execution
Audience: Implementers, reviewers, auditors

0. Meta-Rules for This Checklist

This checklist is exhaustive: every item must be satisfied.

Failure of any single item is a hard constitutional violation.

“Not applicable” is not permitted unless explicitly stated.

Silence is acceptable only where constitutionally defined.

1. Data Ingestion (Raw Data Compliance)
1.1 Source Validation

All inputs originate from raw exchange streams only

trades

order book updates

liquidations

No derived feeds (VWAP, indicators, funding rate summaries, signals)

No broker-side aggregates

No third-party analytics

Fail Condition: Any pre-interpreted data enters the system.

1.2 Timestamp Handling

Exchange timestamps are preserved verbatim

No wall-clock time usage

No latency inference

No “time since event” semantics

2. Observation Layer
2.1 Structural Integrity

ObservationSnapshot exposes only constitutionally allowed fields

All exposed fields are either:

raw-derived

structural

or explicitly NULL

No semantic labels in field names

2.2 Silence Handling

Missing data results in NULL, not substitution

No default values

No inferred continuity

No “assume unchanged” logic

2.3 Failure Semantics

Any invariant breach → FAILED

FAILED is terminal upstream

No recovery, retry, or downgrade

3. Primitive Construction
3.1 Raw Derivability

For every primitive:

Can be recomputed solely from raw inputs

Uses only arithmetic or ordering

No classification, scoring, or interpretation

No thresholds without declared mechanical origin

3.2 Naming Discipline

No semantic or intent-laden names

No “signal”, “strength”, “pressure”, “trend”, “bias”

Names describe what is measured, not what it means

3.3 Null Discipline

If a primitive cannot be computed → NULL

NULL never coerced

NULL never interpreted as absence or weakness

4. Memory & Historical Access
4.1 Memory Constraints

Memory is read-only

Memory contains only raw-derived primitives

No learned parameters

No adaptive thresholds

4.2 Comparative Use Only

Memory used only for comparison

No prediction, projection, or expectation

No future inference

5. Mandate Emission
5.1 Mandate Purity

For every mandate:

Stateless

Non-persistent

Cycle-local

Derived from current primitives only

5.2 Mandate Types

Mandate type ∈ { ENTRY, EXIT, REDUCE, HOLD, BLOCK }

No custom mandate types

No hybrid actions

5.3 Expiry Enforcement

Every mandate declares expiry conditions

Expiry evaluated every cycle

No mandate survives expiry

6. Arbitration
6.1 Input Constraints

Arbitration consumes only:

current position state

current cycle mandates

No historical mandate access

6.2 Authority Ordering

Authority order is total and fixed

EXIT supremacy enforced

Lower authority mandates fully suppressed

6.3 Single-Action Invariant

At most one action emitted per symbol per cycle

Conflicts collapse deterministically

Unresolvable conflicts → NO_ACTION

6.4 Forbidden Arbitration States

No multiple actions

No action without mandate

No ENTRY when EXIT exists

No mandate persistence

7. Position Lifecycle
7.1 State Machine Integrity

All transitions are explicitly defined

No implicit transitions

No skipping states

No back-edges without EXIT

7.2 Position Constraints

Max one position per symbol

Opposite ENTRY requires EXIT first

REDUCE does not invert position

EXIT is terminal

8. Risk & Exposure
8.1 Exposure Limits

Leverage bounded by invariant

Exposure calculated mechanically

No PnL-based sizing

No confidence-based sizing

8.2 Liquidation Safety

Liquidation price computed deterministically

Position sizing prevents liquidation at entry

No assumption of favorable movement

9. Execution (M6)
9.1 Structural Constraints

Event-scoped invocation only

Stateless function

No loops

No scheduling

No retries

9.2 Dependency Discipline

Execution consumes ObservationSnapshot only

No observation logic inside execution

No feedback into observation

9.3 Failure Propagation

Observation FAILED → immediate halt

No execution during UNINITIALIZED

No silent continuation

10. External Speech & Side Effects

No logs with interpretive language

No UI assertions

No metrics implying correctness or quality

No alerts without explicit mandate

11. Testing Discipline
11.1 Allowed Tests

Determinism tests

Invariant violation tests

Arbitration conflict tests

Failure propagation tests

11.2 Forbidden Tests

Performance-based assertions

Win-rate expectations

Strategy outcome tests

Learning or adaptation tests

12. Review & Change Control

No constitutional files modified

All changes reviewed against this checklist

Any extension requires new annex, not modification

Amendments may only strengthen constraints

FINAL VERIFICATION STATEMENT

An implementation is constitutionally valid if and only if:

Every item in this checklist is satisfied.

Failure of a single item constitutes a hard violation.
