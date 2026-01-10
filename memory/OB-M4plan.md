PHASE M4 — CONTEXTUAL READ MODELS (PLANNING DOCUMENT)

Status: PLANNING ONLY
Implementation: ❌ NOT AUTHORIZED
Audience: Coding agent (familiarization only)
Precondition: M3 frozen (✔ satisfied)

1. Purpose of M4 (Why It Exists)
Problem M4 Solves

After M3, the system has rich but raw perception:

Thousands of memory nodes

Each node with:

Accumulated evidence (M2)

Temporal ordering (M3)

All data is factual but low-level

If strategies consume this directly, they will:

Re-interpret the same data differently

Duplicate logic

Drift over time

Accidentally embed bias

M4’s Role

M4 is a read-only projection layer.

It converts raw memory into standardized, factual context views that are:

Stable

Reusable

Comparable

Strategy-agnostic

M4 answers:
“How should raw memory be described, not acted upon?”

2. What M4 IS (Strict Definition)

M4 consists of derived views over M2 + M3 memory.

Each view is:

Deterministic

Retrospective

Non-predictive

Read-only

Stateless (recomputable)

Key Principle

M4 never stores new beliefs.
It only summarizes existing beliefs.

3. What M4 Is NOT (Hard Prohibitions)

M4 must NOT:

❌ Generate signals

❌ Predict outcomes

❌ Rank importance

❌ Score quality

❌ Recommend actions

❌ Classify regimes

❌ Infer direction (bullish/bearish)

❌ Decide relevance

❌ Apply thresholds for “good/bad”

If a question sounds like:

“Should we trade?”

“Is this strong?”

“Is this important?”

It is not allowed in M4.

4. Conceptual Model of M4
Mental Model

M1–M3: Memory (what the market did)

M4: Language (how we describe what happened)

Think of M4 as:

A lens

A summary

A map

Not a brain. Not a decision-maker.

5. Categories of M4 Read Models (High-Level)

These are categories, not implementations.

5.1 Temporal Structure Views

Describe how evidence unfolds over time at a level.

Examples (descriptive, not evaluative):

Average sequence length

Token diversity over time

Typical ordering shapes (e.g., entry → interaction → exit)

Purpose:

Give structure to temporal complexity

Without calling it “good” or “bad”

5.2 Interaction Density Views

Describe how concentrated activity is, historically.

Examples:

Interactions per hour at node

Time gaps between interactions

Burstiness descriptors (purely statistical)

Purpose:

Distinguish sparse vs busy levels

Without inferring opportunity

5.3 Evidence Composition Views

Describe what kinds of evidence dominate.

Examples:

Trade-heavy vs liquidation-heavy nodes

Orderbook-only vs execution-backed nodes

Mix ratios (counts only)

Purpose:

Characterize nodes by composition, not meaning

5.4 Stability vs Transience Views

Describe memory persistence characteristics.

Examples:

Time spent ACTIVE vs DORMANT

Average decay trajectory

Revisit frequency

Purpose:

Understand historical continuity

Without labeling levels as “strong”

5.5 Cross-Node Context Views

Describe relationships across memory.

Examples:

Density maps

Cluster overlap statistics

Motif spread across nodes

Purpose:

Provide global context

Without prioritization

6. Output Philosophy
What M4 Outputs Look Like

Dictionaries

Lists

Histograms

Time-series summaries

Ratios and counts

What They Never Include

Scores

Rankings

Threshold judgments

Labels like “support”, “resistance”, “important”

Any field that implies action

7. Relationship to Strategies (Critical Boundary)

Strategies:

MAY consume M4 outputs

MUST NOT modify them

MUST NOT back-propagate logic into M4

M4 is downstream of memory, upstream of strategy, and never bidirectional.

8. Validation Philosophy for M4 (Preview Only)

When M4 is eventually implemented, it will require:

Deterministic recomputation tests

No-growth-without-memory-change tests

Prohibition scans (same as M2/M3)

Equivalence tests (same memory → same view)

Zero strategy coupling tests

But no validation is defined yet — this is planning only.

9. Why M4 Comes Before Any Strategy Work

Without M4:

Every strategy invents its own perception

Results are incomparable

Debugging becomes impossible

You never know why a strategy acted

With M4:

Strategies consume shared context

Failures are explainable

Behavior is auditable

Research becomes cumulative

10. Phase Boundary Declaration
M4 Planning Status

✔ Concept defined

✔ Scope bounded

✔ Prohibitions explicit

✔ No implementation authorized

✔ No prompts generated

Next Authorized Step (Later)

Formal M4 specification

Then prompt design

Then gated implementation