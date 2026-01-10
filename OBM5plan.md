PHASE M5 — ACCESS DISCIPLINE & EPISTEMIC SAFETY LAYER

Status: PLANNED
Purpose: Enforce how memory may be queried, not what memory contains
Position in Stack: Above M4, below any strategy or research layer
Mutability: Read-only, stateless, deterministic

1. WHY M5 EXISTS

M1–M4 answer progressively richer factual questions:

M1: What happened?

M2: What persisted?

M3: In what order did evidence accumulate?

M4: How does this look, factually?

At this point, the danger is no longer missing information —
the danger is misuse of correct information.

Core Risk M5 Addresses

Without M5, a downstream consumer can:

Cherry-pick views

Query memory in biased ways

Implicitly rank or select “good” nodes

Reconstruct signals by query composition

M5 exists to discipline access, not enrich content.

M5 does not add knowledge.
M5 constrains epistemology.

2. WHAT M5 IS (POSITIVE DEFINITION)

M5 is a Query Governance & Access Control Layer that:

Defines allowed question shapes

Enforces neutral defaults

Prevents evaluative or selective querying

Makes all information requests auditable and reproducible

M5 answers:

“What kinds of questions is the system allowed to ask about memory?”

3. WHAT M5 IS NOT (STRICT PROHIBITIONS)

M5 is NOT:

A strategy layer

A filtering or ranking layer

A recommendation engine

A scoring or weighting system

A caching or optimization layer

M5 must not:

Add new metrics

Combine metrics into composite values

Select “top”, “best”, “strongest”, “most relevant”

Infer intent, direction, or opportunity

4. CORE RESPONSIBILITIES OF M5
Responsibility 1: Query Shape Enforcement

M5 defines explicit query archetypes, e.g.:

“Describe all nodes in a price range”

“Describe all motifs observed in a time window”

“Describe distribution of node states”

It explicitly forbids:

Queries that select based on strength, volume, density

Queries that return only a subset without neutral criteria

Responsibility 2: Neutral Default Enforcement

Any parameter that could bias interpretation must:

Be explicitly provided by caller

Have a neutral, non-selective default

Examples:

Parameter	Allowed Default	Forbidden Default
min_count	1	5
time_window	explicit	“recent”
node_limit	None	10
sort_order	ID / price	strength
Responsibility 3: Deterministic Framing

M5 guarantees:

Same inputs → same outputs

No implicit time references

No environment dependence

No internal state accumulation

M5 functions must be pure.

Responsibility 4: Access Transparency

Every M5 query must be:

Fully reproducible

Explainable as a factual request

Auditable by inspecting parameters alone

No hidden logic.

5. M5 DOES NOT TOUCH MEMORY CONTENT

Critical boundary rule:

M5 may not modify, annotate, enrich, or cache M1–M4 outputs.

No writes

No mutation

No field addition

No shadow state

M5 is a lens, not a layer of memory.

6. M5 ARCHITECTURE (HIGH LEVEL)
Inputs

M2 nodes (read-only)

M3 temporal data (read-only)

M4 contextual views (read-only)

Explicit query parameters

Outputs

Structured, neutral descriptions

Lists, dicts, scalars only

No scores, no rankings

Internal State

NONE (stateless by design)

7. PROPOSED M5 MODULE FAMILIES
M5-A: Query Schemas

Defines allowed query types and parameter validation.

Explicit schemas

Type-checked

Rejects ambiguous or evaluative requests

M5-B: Neutral Selection Guards

Ensures:

No implicit filtering

No strength-based slicing

No ordering by evaluative metrics

M5-C: Output Normalization

Ensures:

Consistent field names

Stable ordering (ID / price)

No derived “importance”

M5-D: Audit Metadata (Optional but Recommended)

Attach metadata such as:

Query type

Parameters used

Timestamp supplied by caller

No logging, no persistence — metadata travels with response only.

8. EXAMPLES (ALLOWED vs FORBIDDEN)
✅ ALLOWED

“Describe all nodes between price 2.05 and 2.10.”

“Describe motif counts for all nodes observed in the last 6 hours.”

“Return node state distribution at timestamp T.”

❌ FORBIDDEN

“Show me the strongest nodes.”

“Which motifs matter most?”

“Give top 10 nodes by relevance.”

“Where should I trade?”

9. FAILURE CONDITIONS (IMMEDIATE STOP)

Implementation must be rejected if any one occurs:

Any ranking or sorting by evaluative metric

Any composite score

Any hidden default that filters

Any mutation of M1–M4 data

Any use of system time instead of provided timestamps

Any state retained between calls

Any language implying action, importance, or intent

10. RELATIONSHIP TO STRATEGIES (IMPORTANT)

Strategies:

May call M5

May not bypass M5 to reach M1–M4

Are treated as untrusted consumers

M5 is the firewall.

11. SUCCESS CRITERIA FOR M5

M5 is successful if:

Two different strategies issuing the same M5 query receive identical outputs

A human auditor can explain every output field without inference

Removing all strategies does not change M5 behavior

M5 cannot be used to reconstruct signals without adding external logic

12. PHASE STATUS

Planning: COMPLETE

Design: LOCKED

Implementation: NOT STARTED

Risk Level: HIGH (must be conservative)

Change Policy: Strict — changes require justification

FINAL SUMMARY (FOR CODING AGENT)

M5 is not about seeing more.
M5 is about seeing safely.

You are not adding intelligence.
You are preventing misuse of intelligence that already exists.