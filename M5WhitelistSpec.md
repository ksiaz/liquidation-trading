Below is a formal, implementation-ready M5 Whitelist Specification for M4 Tier A primitives.
It is written explicitly for coding agent + auditor context, not as narrative documentation.

M5 Whitelist Specification — M4 Tier A Structural Primitives

Version: v1.0
Status: DRAFT (Pending Implementation & Certification)
Authority: M4 Structural Primitive Canon v1.0, System Certification v1.0
Scope: Governance exposure rules for M4 Phase 1 (Tier A) primitives

1. Purpose

This document defines exactly which M4 Tier A structural primitives may be exposed through M5, under what query types, and with what field-level constraints.

The whitelist guarantees that:

Tier A primitives are accessible

No semantic, evaluative, or selective leakage occurs

All existing M5 epistemic safety guarantees remain intact

This document does not modify M4 or M6.
It extends M5 only.

2. Governing Principles (Non-Negotiable)

Field-Level Whitelisting Only
M5 SHALL expose only explicitly listed output fields.
No composite, derived, ranked, or filtered outputs are permitted.

No Predicate Assistance
M5 SHALL NOT:

Interpret primitive values

Apply thresholds

Label values as meaningful

Filter based on magnitude or direction

Read-Only Enforcement
All Tier A access is read-only, identical to existing M4 exposure.

Determinism Preservation
Identical inputs → identical outputs across M4 → M5 → M6.

Semantic Neutrality
No field names, query names, or parameters may imply:

Trend

Strength

Quality

Opportunity

Prediction

3. Exposure Model

Tier A primitives are exposed only via structured M5 queries, never directly.

Allowed Exposure Mechanisms

LocalContextQuery

TemporalSequenceQuery (where time-bounded)

No new free-form query types are introduced in v1.0.

4. Whitelisted Tier A Primitives
A1 — Structural Boundary Violation

Source: m4_structural_boundaries.py

M5 Exposure Name: STRUCTURAL_BOUNDARY_VIOLATION

Query Type: LocalContextQuery

Exposed Fields:

violation_depth: float

violation_start_ts: float

violation_end_ts: float

violation_duration: float

Returns:

None if no violation

Single immutable record if present

Explicit Non-Implications:

NOT reversal

NOT rejection

NOT failure

NOT trap

NOT liquidity intent

A2 — Structural Conversion Failure

Source: m4_structural_boundaries.py

M5 Exposure Name: STRUCTURAL_CONVERSION_FAILURE

Query Type: TemporalSequenceQuery

Exposed Fields:

reversion_ts: float

conversion_window: float

Returns:

None or single record

Explicit Non-Implications:

NOT false breakout

NOT weakness

NOT deception

A3 — Price Traversal Velocity

Source: m4_traversal_kinematics.py

M5 Exposure Name: PRICE_TRAVERSAL_VELOCITY

Query Type: TemporalSequenceQuery

Exposed Fields:

price_delta: float

time_delta: float

velocity: float

Explicit Non-Implications:

NOT momentum

NOT strength

NOT acceleration quality

A4 — Traversal Compactness

Source: m4_traversal_kinematics.py

M5 Exposure Name: TRAVERSAL_COMPACTNESS

Query Type: TemporalSequenceQuery

Exposed Fields:

net_displacement: float

total_path_length: float

compactness_ratio: float

Explicit Non-Implications:

NOT efficiency

NOT quality

NOT decisiveness

A5 — Price Acceptance Ratio

Source: m4_price_distribution.py

M5 Exposure Name: PRICE_ACCEPTANCE_RATIO

Query Type: LocalContextQuery

Exposed Fields:

accepted_range: float

rejected_range: float

acceptance_ratio: float

Explicit Non-Implications:

NOT conviction

NOT participation quality

NOT validation

A6 — Zone Penetration Depth

Source: m4_zone_geometry.py

M5 Exposure Name: ZONE_PENETRATION_DEPTH

Query Type: LocalContextQuery

Exposed Fields:

penetration_depth: float

Returns:

None if no penetration

Explicit Non-Implications:

NOT invalidation

NOT failure

NOT defense

A7 — Displacement Origin Anchor

Source: m4_zone_geometry.py

M5 Exposure Name: DISPLACEMENT_ORIGIN_ANCHOR

Query Type: TemporalSequenceQuery

Exposed Fields:

anchor_low: float

anchor_high: float

anchor_dwell_time: float

Explicit Non-Implications:

NOT institutional activity

NOT accumulation

NOT preparation

A8 — Central Tendency Deviation

Source: m4_price_distribution.py

M5 Exposure Name: CENTRAL_TENDENCY_DEVIATION

Query Type: LocalContextQuery

Exposed Fields:

deviation_value: float

Explicit Non-Implications:

NOT overextension

NOT mean reversion likelihood

5. Forbidden M5 Behaviors (Tier A)

M5 MUST NOT:

Sort Tier A outputs

Rank Tier A outputs

Filter Tier A outputs by value

Label outputs (e.g., “large”, “small”)

Combine multiple primitives into composite objects

Inject thresholds or comparisons

Collapse multiple nodes into “best” or “worst”

Violations are Type-2 Certification Breaches.

6. Schema Requirements

All Tier A query schemas SHALL:

Be explicitly typed

Reject unknown fields

Reject forbidden parameter names

Require explicit timestamps where applicable

Return immutable payloads only

7. Determinism & Reproducibility

M5 Tier A queries MUST satisfy:

Given:
  identical M4 inputs
  identical query parameters
Then:
  identical M5 outputs (byte-equivalent)


No caching, sampling, or inference allowed.

8. Certification Impact
Component	Impact
M4	NONE (already frozen)
M5	EXTENSION ONLY
M6	NONE
EP-2	ENABLED
EP-3	UNAFFECTED
9. Authorization State

This whitelist is safe to implement immediately.

Post-implementation requirements:

M5 unit tests for each Tier A query

M5–M4 integration tests (Tier A only)

Updated M5 Compliance Audit addendum

10. Formal Statement

This whitelist exposes structural facts only.
Meaning, interpretation, and decision authority remain external.
M5 continues to function as an epistemic firewall.

END OF SPEC