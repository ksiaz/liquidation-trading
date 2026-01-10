Semantic Leak Exhaustive Catalog

(Normative – Enforcement-Oriented)

0. Definition

A semantic leak occurs when meaning that is not provable from raw data alone becomes:

externally visible,

action-influencing,

persistent,

or structurally implied.

Semantic leaks are not bugs.
They are category errors.

1. Leak Classes (Complete Set)

Every semantic leak falls into exactly one of the classes below.

No new class may be added without constitutional amendment.

1.1 Interpretive Meaning Leaks
Definition

Any construct that assigns meaning, significance, or interpretation to data.

Examples (non-exhaustive)

“signal”

“strength”

“confidence”

“pressure”

“momentum”

“trend”

“bias”

“quality”

“setup”

“opportunity”

Why Forbidden

Interpretation is not falsifiable from raw data.
Two agents may disagree without contradiction.

Leak Vectors

Variable names

Field names

Log messages

Comments crossing module boundaries

Snapshot fields

Public method names

Rule Mapping

Category: Vocabulary & Semantics

Scope: LINE

Trigger: LEXICAL

Strictness: HARD

1.2 Predictive Meaning Leaks
Definition

Any construct that implies future expectation, probability, or outcome.

Examples

“likely”

“expected”

“forecast”

“probability”

“chance”

“anticipate”

“will move”

“target”

Why Forbidden

Prediction introduces unverifiable future claims.
The system must remain reactive, not prophetic.

Leak Vectors

UI text

Logs

Mandate rationale

Documentation exposed to execution

Strategy metadata

Rule Mapping

Vocabulary & Semantics

LINE

LEXICAL

HARD

1.3 Evaluative Judgement Leaks
Definition

Any construct that grades, scores, or ranks conditions.

Examples

“good / bad”

“strong / weak”

“high-quality”

“optimal”

“favorable”

numeric scores without raw unit meaning

Why Forbidden

Evaluation collapses multi-dimensional uncertainty into opinion.

Leak Vectors

Scores

Rankings

Flags

Boolean “is_good” style fields

Threshold labels

Rule Mapping

Vocabulary & Semantics

LINE

LEXICAL

HARD

1.4 Derived Data Leaks (Pre-Interpretation)
Definition

Any data that has already undergone semantic compression before entry.

Examples

Indicators (RSI, MACD, VWAP, etc.)

Aggregated signals

“Features”

Model outputs

Normalized scores

Why Forbidden

Derived data embeds assumptions outside the constitution.

Leak Vectors

Input adapters

Ingestion schemas

Snapshot fields

External feeds

Rule Mapping

Raw-Data Purity (Annex A)

FILE

BOUNDARY

HARD

1.5 Temporal Meaning Leaks
Definition

Any construct that implies time-based interpretation beyond raw timestamps.

Examples

“recent”

“old”

“late”

“early”

“stale”

“fast”

“slow”

Why Forbidden

Temporal meaning depends on context, not data.

Leak Vectors

Status labels

Logs

Metrics

State names beyond the PSM

Rule Mapping

Vocabulary & Semantics

LINE

LEXICAL

HARD

1.6 Causal Attribution Leaks
Definition

Any construct that implies cause-and-effect relationships.

Examples

“because”

“caused by”

“due to”

“result of”

“led to”

Why Forbidden

Causality cannot be proven from observation alone.

Leak Vectors

Logs

Post-hoc explanations

Strategy commentary

Debug output

Rule Mapping

Vocabulary & Semantics

LINE

LEXICAL

HARD

1.7 Memory & Persistence Leaks
Definition

Any construct that remembers, accumulates, or references past evaluations.

Examples

Rolling confidence

Historical mandate context

Cached interpretations

Stateful “learning”

Why Forbidden

Violates stateless, single-cycle determinism.

Leak Vectors

Stored fields

Static variables

Caches

Cross-cycle references

Rule Mapping

Mandate / Arbitration / Execution

FILE

STRUCTURAL

HARD

1.8 Cross-Layer Meaning Leaks
Definition

Any construct where internal semantics escape their layer.

Examples

Observation concepts influencing execution directly

Strategy naming bleeding into execution

Execution exposing interpretation

Why Forbidden

Layers exist to contain meaning.

Leak Vectors

Imports

Shared types

Public APIs

Callbacks

Rule Mapping

Exposure Boundary Rules

FILE

BOUNDARY

ESCALATE

1.9 Naming-Implied Semantics
Definition

Meaning implied solely by identifier names, even if values are null.

Examples

peak_pressure_events = None

signal_strength = 0

confidence = None

Why Forbidden

Names communicate meaning even without values.

Leak Vectors

Public schemas

Snapshots

API contracts

Rule Mapping

Vocabulary & Semantics

LINE

LEXICAL

HARD

1.10 Documentation Leakage
Definition

Meaning that leaks through documentation consumed by enforcement layers.

Examples

Comments parsed by tooling

Docstrings used by execution

Strategy docs imported as config

Why Forbidden

Documentation must never influence runtime behavior.

Leak Vectors

Structured comments

Embedded DSLs

Annotations

Rule Mapping

Exposure Boundary

FILE

BOUNDARY

ESCALATE

2. Exhaustiveness Guarantee

This catalog is exhaustive because:

All leaks reduce to meaning introduction

Meaning can only enter via:

words

structure

memory

boundaries

There are no other channels.

3. Default Rule

If a construct’s meaning cannot be derived from raw data + constitution alone, it is a semantic leak.

No intent-based exceptions exist.

4. Lock Statement

This catalog is constitutionally binding.

Any of the following require amendment:

Adding a new leak class

Weakening a definition

Introducing “safe interpretation”

Allowing derived meaning “with justification”