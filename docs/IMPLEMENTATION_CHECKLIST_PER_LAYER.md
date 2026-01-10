CONCRETE IMPLEMENTATION CHECKLIST PER LAYER

Scope:
All production code implementing the constitutional trading system.

Authority:

EPISTEMIC_CONSTITUTION.md

RAW_DATA_PRIMITIVES.md

POSITION_AND_EXECUTION_CONSTITUTION.md

SEMANTIC_LEAK_EXHAUSTIVE_AUDIT.md

Purpose:
Ensure every layer remains non-interpretive, stateless where required, and constitutionally compliant.

GLOBAL CHECKS (APPLY TO ALL LAYERS)

A change must be rejected if it introduces:

Probabilities

Confidence scores

Weights

Rankings (other than mandate authority)

“Signal strength”

Adaptive thresholds

Learned parameters

Reinforcement logic

Feedback loops

Semantic naming

Search red flags:

confidence
probability
strength
score
quality
bias
signal
trend
pressure
safe
optimal

1. RAW DATA INGESTION LAYER
Purpose

Ingest exchange-emitted facts only.

Must Do

Consume raw events exactly as emitted

Preserve event atomicity

Preserve original timestamps

Preserve raw price, size, side

Must NOT Do

Aggregate events

Normalize data

Bin volumes

Compute deltas

Compute averages

Compute rates

Label events

Review Checklist

Each input corresponds to one exchange event

No rolling buffers

No windows

No derived metrics

No interpretation in variable names

Example (Allowed)
TradeEvent(price, size, side, timestamp)

Example (Forbidden)
HighVolumeTrade(price, size)

2. OBSERVATION LAYER
Purpose

Expose raw facts, not meaning.

Must Do

Count events

Track presence / absence

Track timestamps

Emit UNINITIALIZED / FAILED only

Must NOT Do

Compute rates

Compute baselines

Compute trends

Compute zones

Classify events

Review Checklist

Every field maps to a raw fact

No ratios

No percentiles

No rolling statistics

No inferred states

Allowed Field Types

int

bool

timestamp

opaque identifier

Forbidden Field Types

float representing rate

confidence

strength

score

3. MANDATE EMISSION LAYER
Purpose

Emit boolean intent claims, not trade decisions.

Must Do

Emit mandates only when conditions are met

Remain stateless

Use deterministic logic

Emit zero or more mandates per cycle

Must NOT Do

Rank mandates by quality

Combine signals

Accumulate confidence

Delay emission

Recall previous emissions

Review Checklist

Mandate emission is stateless

No historical memory

Conditions are boolean

No numeric weighting

No “best” mandate selection

Allowed
if condition_A and condition_B:
    emit(ENTRY)

Forbidden
if confidence > 0.7:
    emit(ENTRY)

4. MANDATE ARBITRATION LAYER
Purpose

Resolve conflicts mechanically, not intelligently.

Must Do

Enforce authority ordering

Enforce single-action invariant

Filter by position state

Emit exactly one action or NO_ACTION

Must NOT Do

Access raw data

Access observations

Score mandates

Evaluate outcomes

Choose “better” action

Review Checklist

Only mandate metadata is accessed

Authority ordering is total and static

No conditional weighting

Exactly one result emitted

5. EXECUTION LAYER
Purpose

Translate action → exchange interaction.

Must Do

Validate action/state compatibility

Submit order

Track execution state

Update position state deterministically

Must NOT Do

Interpret fills

Adjust size based on outcome

Retry adaptively

Infer intent from partial fills

Review Checklist

Action compatibility enforced

No sizing logic here

No performance metrics

No execution “quality” evaluation

6. POSITION STATE MACHINE
Purpose

Enforce lifecycle legality.

Must Do

Enforce legal transitions only

Enforce single-position invariant

Enforce direction invariance

Enforce EXIT terminality

Must NOT Do

Infer state

Auto-transition on time

Skip transitional states

Combine states

Review Checklist

State transitions exactly match constitution

No hidden transitions

No inferred state

Execution validates every transition

7. RISK & EXPOSURE LAYER
Purpose

Prevent systemic failure, not optimize returns.

Must Do

Enforce hard limits

Block illegal actions

Prevent liquidation exposure

Enforce caps deterministically

Must NOT Do

Recommend actions

Adjust risk dynamically

Predict volatility

Classify conditions as “safe”

Review Checklist

Risk only vetoes actions

No advisory outputs

No adaptive logic

Limits are static and explicit

8. CROSS-LAYER INTEGRITY CHECKS
Must Be True

Observation never references execution

Execution never references raw data

Mandates never persist

Arbitration has no memory

Risk has veto power only

Reject If

Any layer imports a non-adjacent layer

Any feedback loop exists

Any state leaks across cycles

9. FINAL ACCEPTANCE CHECK

A change is acceptable only if:

All layer checklists pass

No semantic naming introduced

No interpretation introduced

No adaptive behavior introduced

No memory introduced where forbidden

10. Enforcement Statement

This checklist is:

Binding

Exhaustive

Non-negotiable

Failure to satisfy any item is a hard rejection, not a warning.

End of Implementation Checklist