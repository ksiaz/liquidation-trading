Formal Rule Taxonomy

(Constitution → Semantic Enforcement Mapping)

0. Purpose of This Taxonomy

This taxonomy answers one precise question:

Given a change, which constitutional rules must be re-validated, and at what semantic scope?

It prevents:

over-scanning (noise, fatigue)

under-scanning (silent semantic leaks)

ad-hoc enforcement drift

This document is normative: if a rule is not classified here, it cannot be enforced automatically.

1. Rule Classification Axes

Every constitutional rule is classified along three orthogonal axes:

Axis A — Semantic Scope

What range of code must be inspected if this rule is implicated?

LINE — single line is sufficient

BLOCK — contiguous structural block required

FILE — entire file context required

Axis B — Trigger Type

What kind of change activates this rule?

LEXICAL — word / token / identifier appears

STRUCTURAL — control flow, state, ordering changes

BOUNDARY — crossing layer / module / responsibility boundary

Axis C — Enforcement Strictness

What happens on ambiguity?

HARD — ambiguity is a violation

ESCALATE — ambiguity widens scope

DEFER — ambiguity allowed (rare, explicit only)

2. Primary Rule Categories (Top-Level)

All constitutional rules fall into exactly one of the following categories.

No overlaps are permitted.

2.1 Vocabulary & Semantics Rules

What words may exist where.

Purpose

Prevent semantic leakage through naming, comments, or exposed identifiers.

Examples

“confidence”

“strength”

“signal quality”

“probability”

“expectation”

Taxonomy
Property	Value
Scope	LINE
Trigger	LEXICAL
Strictness	HARD
Justification

Vocabulary is local and explicit.
A single forbidden term is sufficient to violate.

2.2 Exposure Boundary Rules

What may cross module or layer boundaries.

Purpose

Prevent internal interpretation from becoming external assertion.

Examples

Observation → Execution imports

Internal counters exposed in snapshots

Derived metrics leaving ingestion

Taxonomy
Property	Value
Scope	FILE
Trigger	BOUNDARY
Strictness	ESCALATE
Justification

Boundary violations cannot be judged locally.
Ambiguity must widen scope to full file.

2.3 State Machine Integrity Rules

What transitions are legal.

Purpose

Guarantee determinism and lifecycle correctness.

Examples

ENTERING → OPEN

OPEN → REDUCING

CLOSING → FLAT

Taxonomy
Property	Value
Scope	BLOCK
Trigger	STRUCTURAL
Strictness	HARD
Justification

Transitions are contextual but bounded.
Block scope captures legality fully.

2.4 Mandate Emission Rules

When mandates may be emitted.

Purpose

Prevent implicit interpretation or memory.

Examples

Emitting ENTRY without trigger

Emitting multiple mandates per symbol

Emitting mandates outside evaluation cycle

Taxonomy
Property	Value
Scope	BLOCK
Trigger	STRUCTURAL
Strictness	HARD
2.5 Mandate Arbitration Rules

How mandates interact.

Purpose

Preserve authority ordering and determinism.

Examples

ENTRY surviving EXIT

Multiple actions emitted

Authority inversion

Taxonomy
Property	Value
Scope	BLOCK
Trigger	STRUCTURAL
Strictness	HARD
2.6 Execution Action Rules

What execution may do.

Purpose

Ensure execution is mechanical, not interpretive.

Examples

Partial exit without mandate

Direction flip without EXIT

Implicit sizing changes

Taxonomy
Property	Value
Scope	BLOCK
Trigger	STRUCTURAL
Strictness	HARD
2.7 Risk & Exposure Invariants

What must never be exceeded.

Purpose

Prevent undefined exposure, liquidation risk, or silent leverage drift.

Examples

Multiple positions per symbol

Leverage not tied to liquidation distance

Exposure without stop definition

Taxonomy
Property	Value
Scope	FILE
Trigger	STRUCTURAL
Strictness	ESCALATE
Justification

Risk invariants depend on global context within a module.

2.8 Raw-Data Purity Rules (Annex A)

What data sources are allowed.

Purpose

Prevent pre-interpreted data from entering the system.

Examples

Indicators

Aggregated signals

“Features”

Taxonomy
Property	Value
Scope	FILE
Trigger	BOUNDARY
Strictness	HARD
3. Meta-Rules (Rules About Rules)

These govern how rules themselves behave.

3.1 Scope Escalation Rule

If a rule’s scope cannot be determined with certainty:

Escalate to the next larger scope

LINE → BLOCK → FILE

No exceptions.

3.2 Rule Non-Overlap Invariant

A single change may trigger multiple rules, but:

Each rule is evaluated independently

The largest required scope wins

3.3 Silence Is Not Safety

If no rule applies, that is explicitly safe.

If applicability is uncertain, it is unsafe.

4. Why This Taxonomy Matters

This taxonomy ensures:

Every constitutional clause has a mechanical enforcement path

No “interpretation by reviewer”

No silent weakening

No magical heuristics

It also enables:

Diff-only scanning

CI gating

Pre-commit mirroring

Auditable enforcement evolution

5. Lock Statement

This taxonomy is constitutionally binding.

Any of the following require amendment:

Adding a new rule category

Changing scope classification

Weakening strictness

Introducing a new trigger type