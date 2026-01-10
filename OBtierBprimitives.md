Below is a formal Tier B implementation phasing plan, written as a coding-agent–ready guidance document and consistent with how Tier A was executed, certified, and integrated.

This plan is deliberately conservative, admissibility-first, and aligned with your stated goal: guarantee expressive completeness without semantic leakage.

Tier B Structural Primitives
Implementation Phasing Plan v1.0

Authority:
M4 Structural Primitive Canon (Tier A v1.0)
Tier B Primitive Enumeration v0.1
M5 Governance Model v1.0
System Certification v1.0

0. Design Principles (Non-Negotiable)

Tier B implementation MUST preserve all global invariants already enforced:

Pure description only

No evaluation, ranking, thresholds, or heuristics

Determinism

Identical inputs → identical outputs

Semantic neutrality

Zero market terms (explicitly forbidden)

Statelessness

No memory across calls

Immutability

Frozen dataclasses only

M5-first exposure

No primitive is usable unless whitelisted and governed

Unused primitives are acceptable

Missing primitives are not

Tier B Overview

Tier B primitives expand expressive coverage, not strategy power.

They answer questions Tier A cannot express:

What did not happen?

How long did something persist?

What followed a structural event?

They are grouped into five sub-tiers for controlled rollout.

Phase B-1: Absence & Void Primitives
(Lowest Risk, Highest Foundational Value)
Primitives

B1.1 structural_absence_duration

B1.2 traversal_void_span

B1.3 event_non_occurrence_counter

Rationale

Purely negative measurement (absence ≠ interpretation)

No dependency on future or derived primitives

Required to express inducement / sweep without semantics

Implementation Notes

Inputs: explicit windows, explicit traversal arrays

Outputs: durations, counts, ratios only

No assumptions about why absence occurred

Deliverables

1–2 modules (e.g. m4_absence_metrics.py)

~3–5 frozen dataclasses

Unit tests:

zero absence

full absence

partial absence

determinism

Dependencies

None beyond Tier A data shapes

Phase B-2: Exposure & Persistence Primitives
(Medium Risk, High Expressive Gain)
Primitives

B2.1 boundary_exposure_duration

B2.2 zone_residency_profile

B2.3 recurrence_interval_distribution

Rationale

Required by “holding”, “reaction”, “respect” research themes

Still descriptive if framed as time accounting

No thresholds or judgments embedded

Implementation Notes

Multiple entries allowed

Output distributions, not summaries

Ratios allowed only as mechanical fractions

Deliverables

1–2 modules (e.g. m4_exposure_profiles.py)

Entry counts, durations, intervals

Tests:

single entry

repeated entry

overlapping windows

determinism

Dependencies

Tier A traversal / boundary primitives

No cross-primitive inference

Phase B-3: Structural After-Effect Primitives
(Higher Risk, Must Be Strictly Controlled)
Primitives

B3.1 post_violation_reentry_latency

B3.2 post_event_displacement_extent

B3.3 structural_followthrough_ratio

Rationale

Directly required by reversal / fake-break research

Dangerous if misnamed — must remain mechanical

Must NOT imply confirmation or failure

Implementation Notes

Event timestamps must be explicit inputs

“Pre” and “post” defined only by caller

Ratios allowed only as arithmetic outputs

Deliverables

1 module (e.g. m4_post_event_metrics.py)

Clear separation between event definition and measurement

Tests:

no reentry

immediate reentry

symmetric movement

determinism

Dependencies

Tier A A1/A2 (once traversal infra exists)

Caller-supplied sequences allowed initially

Phase B-4: Stability & Variance Refinement
(Low Risk, Analytical Enrichment)
Primitives

B4.1 path_variance_density

B4.2 dwell_variance

Rationale

Complements Tier A compactness

Enables richer M6 predicates without semantics

Pure statistical dispersion only

Implementation Notes

Variance only — no classification

No normalization against “expected” values

Deliverables

1 module (e.g. m4_variance_metrics.py)

Tests:

zero variance

uniform variance

determinism

Dependencies

Tier A traversal inputs

Phase B-5: Cross-Primitive Co-Occurrence
(Highest Expressive Power, Last to Implement)
Primitives

B5.1 structural_cooccurrence_matrix

Rationale

Enables complex conditions without inference

Must remain count-based only

Easily abused if implemented too early

Implementation Notes

Counts only, no weighting

No directionality or ordering implied

No causation logic

Deliverables

1 module (e.g. m4_structural_cooccurrence.py)

Tests:

single event

multiple overlapping events

determinism

Dependencies

All prior Tier B primitives stable

M5 & M6 Integration Policy (Per Phase)

Each phase follows the same certification ladder used in Tier A:

Implement M4 primitives

Freeze function signatures

Expose via M5 schema whitelist

Add M5 → M4 routing

Integration tests

Only then allow M6 predicates / EP-2 usage

No phase may skip steps.

Why This Phasing Is Correct

Prevents semantic creep

Preserves certification guarantees

Allows early expressive gains without strategy coupling

Matches how Tier A succeeded technically and philosophically

Most importantly:

This plan guarantees you will never need to “reinterpret” the past research later.
Everything becomes representable before strategy complexity increases.