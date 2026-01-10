Semantic Leak Exhaustive Audit

Status: Draft (Design)
Scope: Whole Repository
Authority: Epistemic Constitution, Position & Execution Constitution
Purpose: Identify, classify, and prevent semantic leakage — situations where meaning, interpretation, or conclusions leak across constitutional boundaries.

1. Definition of Semantic Leak

A semantic leak occurs when:

Information that implies meaning, interpretation, quality, readiness, causality, or intent crosses a boundary where only raw facts or neutral state are permitted.

A semantic leak may occur even if no explicit claim is made.

Silence is not sufficient if structure, naming, or aggregation implies meaning.

2. Why Semantic Leaks Are Existentially Dangerous

Semantic leaks:

Undermine epistemic guarantees silently

Reintroduce interpretation under the guise of “data”

Make downstream logic appear deterministic while actually heuristic

Cannot be reliably reasoned about or verified

Most trading systems fail here.
This project explicitly refuses to.

3. Leak Taxonomy (Exhaustive)
3.1 Linguistic Leaks (Naming-Based)

Leak occurs via identifier choice, regardless of value.

Examples (forbidden at boundaries):

pressure

strength

confidence

signal

setup

bias

opportunity

weak, strong

support, resistance (when implying efficacy)

good, bad, healthy, stale

validated, confirmed

Key insight:
A field named peak_pressure_events = None is still a semantic leak — the name itself asserts meaning.

3.2 Structural Leaks (Schema-Based)

Leak occurs because structure encodes meaning, even if values are raw.

Examples:

Aggregated counters implying significance

Ratios without explicit dimensional grounding

Buckets or bins that imply categorization

Boolean flags whose truth implies interpretation (is_valid, is_ready, is_warm)

Rule:
If a consumer must interpret why a field exists, it is already leaking semantics.

3.3 Aggregation Leaks (Derived Meaning)

Leak occurs when multiple raw events are collapsed into a value that:

Loses provenance

Implies summary judgment

Encodes temporal assumptions

Examples:

Rolling averages

Baselines

Percentiles

Volatility metrics

“Zones” computed upstream

Important:
Aggregation is allowed internally, but must not cross constitutional boundaries.

3.4 Temporal Leaks

Leak occurs when time relationships imply:

Freshness

Delay

Synchronization

Validity windows

Examples:

“recent”

“lag”

“outdated”

“rolling”

“window”

“cooldown”

“debounce”

Observation layer may expose timestamps only — never judgments about them.

3.5 Causal Leaks

Leak occurs when structure implies cause-effect.

Examples:

“triggered_by”

“due_to”

“because”

“led_to”

“response_to”

Even without text, ordering + naming can encode causality.

3.6 Absence-as-Signal Leaks

Leak occurs when absence of data is treated as meaning.

Examples:

No events ⇒ “quiet market”

No failures ⇒ “healthy”

No exits ⇒ “safe”

Silence interpreted as HOLD

Silence must remain silence.
Only explicit mandates may act.

3.7 Threshold Leaks

Leak occurs when numeric boundaries imply judgment.

Examples:

> threshold

max_allowed

safe_limit

danger_zone

Thresholds are allowed only as hard invariants, never as interpretive guidance.

3.8 Statistical Framing Leaks

Leak occurs when statistics imply normality or abnormality.

Examples:

Mean / stddev exposed

Z-scores

Outliers

“Unusual activity”

Statistics may exist internally; never externally visible.

3.9 Cross-Layer Knowledge Leaks

Leak occurs when:

Observation “knows” execution intent

Execution infers observation confidence

Mandates encode strategy knowledge

One layer assumes guarantees from another

This includes:

Observer patterns

Callbacks

Shared mutable state

Implicit contracts not written in constitution

4. Boundary Map (Where Leaks Are Forbidden)
Boundary	Leak Tolerance
Raw Ingestion	None (raw only)
Observation → Execution	Zero
Mandate Emission	Zero
Arbitration	Zero
Execution → Exchange	Zero
UI / Logs	Zero
Internal Computation	Allowed (contained)
5. Allowed vs Forbidden (Clarification)
Allowed

Internal statistical computation

Internal heuristics

Internal naming that never escapes

Internal comments and docstrings

Internal counters with no exposure

Forbidden

Any semantic naming crossing boundaries

Any aggregated meaning crossing boundaries

Any inference expressed structurally

Any UI/log message implying interpretation

Any field whose existence implies meaning

6. Leak Detection Principles

Semantic leaks are detected by asking:

Does this require interpretation by a consumer?

Does the name imply meaning beyond raw fact?

Would two humans independently infer the same “idea”?

Does absence or presence change behavior implicitly?

Could this be used as a signal without saying so?

If yes to any, it is a leak.

7. Constitutional Enforcement Rule

If a construct cannot be explained without using interpretive language, it is forbidden at the boundary.

No exceptions without constitutional amendment.

8. Relationship to Annex A (Raw-Data Exclusivity)

This audit operationalizes Annex A:

Raw data is admissible

Interpretation is permitted only internally

Exposure is facts only

Semantics must die at boundaries