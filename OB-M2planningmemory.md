PHASE M2 — MEMORY CONTINUITY & TOPOLOGY

Status: DESIGN LOCK
Audience: Coding Agent
Purpose: Extend the Liquidity Memory Layer to preserve historical relevance across time, encode structural context, and increase extractable information density — without introducing signals, direction, or strategy logic.

0. NON-NEGOTIABLE PRINCIPLES (LAW)

The Memory Layer MUST remain:

❌ NOT a strategy

❌ NOT a signal generator

❌ NOT predictive

❌ NOT directional

❌ NOT interpretive

The Memory Layer IS:

✅ A factual belief state

✅ A historical compression mechanism

✅ A perception layer

✅ Time-continuous

✅ Strategy-agnostic

Any implementation that violates these rules is INVALID.

1. PROBLEM STATEMENT
Current Limitation (M1)

Memory nodes decay and are archived

Archived nodes lose structural continuity

If price revisits a level after long absence, history is forgotten

System restarts belief accumulation from zero

This conflates:

Relevance decay (temporary)

Historical erasure (permanent)

This results in information loss.

2. PHASE M2 OBJECTIVE

Introduce memory continuity and topology such that:

Historical evidence is retained even when inactive

Memory can reactivate with historical context

Structural relationships between nodes are explicitly represented

Information density increases without interpretation

3. MEMORY STATE MODEL (REQUIRED)
3.1 Memory Node States

Each memory node MUST exist in exactly one state:

State	Meaning
ACTIVE	Recently interacted, strength decaying normally
DORMANT	Inactive but historically relevant
ARCHIVED	Fully decayed, no longer queryable
3.2 State Transitions
ACTIVE → DORMANT

Triggered when:

Strength decays below active_threshold

No interaction within dormant_timeout

Effect:

Node removed from active queries

Historical evidence PRESERVED

Decay rate reduced

DORMANT → ACTIVE

Triggered when:

New factual interaction occurs near node price

Effect:

Strength re-computed from:

Historical evidence

New evidence

Node resumes ACTIVE state

⚠️ No automatic revival — requires NEW evidence.

DORMANT → ARCHIVED

Triggered when:

Strength decays below archive_threshold

No interaction for extended time window

Effect:

Node removed from all active memory graphs

Stored only in cold storage (optional)

4. HISTORICAL EVIDENCE RETENTION (MANDATORY)

Dormant nodes MUST retain:

4.1 Retained Fields

Total interactions (all types)

Total executed volume

Max single event volume

Liquidation proximity counts

Buyer / seller volume totals

Interaction timestamps (compressed form)

Interaction gap statistics

4.2 Discarded Fields

Short-term decay modifiers

Temporary strength boosts

Session-specific counters

Rationale:
Dormant memory is history, not state.

5. MEMORY CONTINUITY RULE

When price revisits a dormant node:

Evidence accumulation resumes

Historical evidence contributes

Strength starts above zero

No assumption of relevance is made

This guarantees:

No amnesia

No false confidence

No predictive resurrection

6. MEMORY TOPOLOGY LAYER (NEW)
6.1 Definition

Topology describes relationships between memory nodes, not interpretation.

6.2 Required Topological Constructs
6.2.1 Neighborhood Density

For each node:

Count neighboring nodes within price radius

Track strength-weighted density

6.2.2 Clustering

Group nodes by:

Price proximity

Temporal overlap

Evidence similarity (counts only)

6.2.3 Gaps

Identify:

Price regions with sparse or no memory

Width and duration of gaps

⚠️ No “support/resistance” labeling allowed.

7. MEMORY PRESSURE METRICS (GLOBAL)
7.1 Purpose

Quantify historical attention concentration.

7.2 Metrics

Events per price unit

Volume per price unit

Liquidations per price unit

Node density per price unit

7.3 Scope

Global (entire memory)

Local (price neighborhood)

⚠️ Pressure ≠ trade pressure
⚠️ Pressure ≠ directional bias

8. QUERY INTERFACE (READ-ONLY)

Memory MUST expose:

get_active_nodes(price, radius)
get_dormant_nodes(price, radius)
get_node_density(price_range)
get_pressure_map(price_range)
get_topological_clusters()


No query may return:

Trade suggestions

Direction

Bias

Regime labels

9. DECAY & SAFETY GUARANTEES

Decay MUST remain monotonic

No node can grow without new evidence

Dormant decay rate < Active decay rate

Archived nodes NEVER auto-revive

10. VALIDATION REQUIREMENTS

Phase M2 is considered COMPLETE only if:

Dormant nodes persist > 10× longer than active nodes

Revisited dormant nodes retain historical evidence

Topology graph builds without labels

Memory density increases measurably

Zero signal fields exist

11. EXPLICIT PROHIBITIONS (REITERATED)

❌ No strategy logic
❌ No signal generation
❌ No predictive fields
❌ No direction inference
❌ No market regime classification

Violations invalidate Phase M2.

12. PHASE M2 DELIVERABLES

Memory State Machine

Dormant Node Storage

Continuity Logic

Topology Graph

Density & Pressure Metrics

Validation Report

FINAL STATEMENT

Phase M2 transforms memory from ephemeral perception into time-continuous belief.
It does NOT trade.
It does NOT predict.
It only remembers — better.