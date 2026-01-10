# SYSTEM GUIDANCE
## Memory-Centric Market Observation System (M1–M5)

**Version:** 2.0  
**Status:** Authoritative  
**Authority:** This document supersedes all informal understanding and serves as the definitive contract for system behavior.

**SCOPE CLARIFICATION (2026-01-06):**  
This document governs the **M1–M5 Memory-Centric Market Observation System** (orderbook nodes, evidence tokens, governance layer). It does **NOT** govern the **Peak Pressure Detection System (v1.0)**, which is a separate frozen detector documented in `docs/system_handover_v1.md`. Peak Pressure is **NOT** part of M1-M5 and has its own immutable rules.

---

## 1. Purpose of the System

### What the System Is

The Memory-Centric Market Observation System is a **factual recording and retrieval architecture** for market data. It captures, organizes, and makes observable what occurred in the market, without interpretation, evaluation, or recommendation.

**Core Principles:**
- Memory is perception, not decision-making.
- The system describes what happened, not what should happen.
- All outputs are observations, not predictions.

### What the System Is Not

The system is not:
- A trading strategy
- A signal generator
- A prediction engine
- A recommendation system
- An opportunity detector
- A pattern classifier with semantic meaning

---

## 2. Layer Responsibilities (M1–M5)

| Layer | Primary Responsibility | Allowed Operations | Explicit Prohibitions | Valid Output Example | Invalid Behavior Example |
|-------|------------------------|-------------------|----------------------|---------------------|-------------------------|
| **M1: Ingestion** | Receive and normalize raw market data | Parse messages, convert types, validate schemas | Adding calculated fields, filtering "important" data, time-based decisions | `{"price": 100.0, "volume": 1.5, "timestamp": 1609459200.0}` | Discarding trades below threshold, flagging "suspicious" activity |
| **M2: Continuity** | Track identity and lifecycle of price-based memory nodes | Create nodes, update timestamps, archive inactive nodes | Ranking nodes, predicting lifecycle transitions, semantic labeling | Node exists at price X with creation time T | "Node is strong", "Node will persist" |
| **M3: Temporal Ordering** | Maintain chronological sequence of evidence tokens | Append events, enforce time windows, trim old events | Scoring event importance, inferring causality, predicting next event | `[TRADE_EXEC at 1000.0, OB_APPEAR at 1001.0]` | "High-value sequence", "Bullish pattern detected" |
| **M4: Contextual Views** | Provide read-only analytical perspectives on memory state | Calculate factual metrics (count, duration, rate), aggregate statistics | Ranking views by quality, interpreting metrics as signals, combining into scores | `{"interactions_per_hour": 5.2, "burstiness_coefficient": 0.3}` | "Best view for entry", "Confidence score: 0.85" |
| **M5: Governance** | Enforce epistemic safety via query validation | Validate schemas, reject forbidden parameters, normalize outputs | Inferring user intent, providing "helpful" defaults, bypassing rules | Accept `{"node_id": "X"}`, Reject `{"sort_by": "strength"}` | Silently converting "top 10" to limit=10, allowing evaluative queries |

---

## 3. Epistemic Safety Principles (NON-NEGOTIABLE)

The following principles are absolute and non-negotiable. **Any violation invalidates the system.**

### 3.1 No Prediction
The system does not forecast, extrapolate, or project future states. All outputs describe past or current observations only.

### 3.2 No Probability
The system does not assign likelihoods, confidence intervals, or probabilistic assessments to events or patterns.

### 3.3 No Importance, Ranking, or Scoring
The system does not evaluate relative importance, rank items by quality, or combine metrics into composite scores. All ordering is by neutral keys (time, price, ID).

### 3.4 No Strategy, Signals, or Recommendations
The system does not suggest actions, identify opportunities, or generate trading signals. It does not label observations as "bullish", "bearish", "entry", or "exit".

### 3.5 No Directional Bias
The system does not treat price increases differently from decreases, or buying differently from selling, except as factual descriptors of observed events.

### 3.6 No Semantic Interpretation
The system does not assign meaning to price levels ("support", "resistance"), patterns ("breakout"), or behaviors ("accumulation"). Terms are purely descriptive of raw data structure.

**Enforcement:** M5 acts as the sole enforcement layer for these principles. Queries violating these rules must be rejected, not accommodated.

---

## 4. Determinism & Purity Rules

### 4.1 Stateless Read Models
All M4 views and M5 queries are pure functions. No internal state persists between calls.

### 4.2 Deterministic Outputs
Identical inputs produce identical outputs. No randomness, no dependency on external state.

### 4.3 No System Clock Usage
Temporal context is provided via explicit parameters (`current_ts`, `query_end_ts`). The system does not call `time.now()` or equivalent.

### 4.4 No Mutation from Read Layers
M4 and M5 are read-only. They do not modify M1, M2, or M3 state.

### 4.5 Explicit Time References Only
All time-dependent logic requires explicit timestamp parameters. No implicit "now" or "latest".

---

## 5. Governance Authority (M5)

### 5.1 M5 as the Only Legal Entry Point

M5 is the **sole interface** between non-memory layers (strategies, controllers) and the memory system. Direct access to M2, M3, or M4 from external layers is prohibited.

### 5.2 M5 is a Firewall, Not a Convenience Layer

M5's purpose is to **reject invalid queries**, not to make querying easier. "Helpful" behavior that violates epistemic safety is still a violation.

### 5.3 Examples of Queries That Must Be Rejected

- `{"sort_by": "strength"}`
- `{"filter": "profitable_zones"}`
- `{"top_n": 10, "ranked_by": "activity"}`
- `{"prediction_horizon": 60}`
- `{"min_confidence": 0.7}`
- Any query containing: `"STRONG_"`, `"WEAK_"`, `"BUY"`, `"SELL"`, `"PROFIT"`, `"LOSS"`, `"SCORE"`, `"RANK"`, `"GOOD"`, `"BAD"`, `"BULL"`, `"BEAR"`, `"ENTRY"`, `"EXIT"`, `"POSITIVE"`, `"NEGATIVE"`

### 5.4 Examples of Allowed Neutral Queries

- `{"node_id": "abc123"}` (identity lookup)
- `{"min_price": 100.0, "max_price": 200.0, "current_ts": 1000.0}` (spatial range)
- `{"query_end_ts": 2000.0, "lookback_seconds": 3600}` (temporal window)
- `{"view_type": "DENSITY", "node_id": "xyz"}` (factual metric view)

### 5.5 Explicit Statement on "Helpful" Violations

Adding convenience features that bypass M5 governance (e.g., "quick access" methods, cached evaluative queries, implicit time resolution) is a violation, even if intended to improve developer experience.

---

## 6. Prohibited Evolution Paths

The following changes are **permanently forbidden**, regardless of justification:

1. **Adding Prediction "Just for Analysis"**  
   No forecasting, extrapolation, or forward-looking logic, even if labeled as "experimental" or "for testing".

2. **Ranking Nodes by Any Metric**  
   No "top N by activity", "most important zones", or "best candidates". All lists are ordered by neutral keys only.

3. **Combining Metrics into Composite Scores**  
   No aggregation of M4 metrics into single quality/importance/confidence values.

4. **Introducing "Importance" Under Different Names**  
   Renaming prohibited concepts ("relevance", "salience", "priority") does not make them permissible.

5. **Adding Convenience Shortcuts That Bypass Governance**  
   No direct M4 access for "performance", no cached evaluative results, no implicit query defaults.

6. **"Temporary" Exceptions**  
   No time-limited violations. Rules apply permanently.

7. **Soft Interpretation**  
   No gradual semantic drift (e.g., "high activity" → "strong zone" → "buy signal").

**This section serves as a safety lock. Violations require full system re-authorization.**

---

## 7. What the System Does NOT Guarantee

The system does not guarantee:

- **Profitability:** Observations do not imply trading edge.
- **Relevance:** The system records all events neutrally; it does not filter for "important" data.
- **Pattern Validity:** Detected structures are descriptive, not predictive.
- **Trading Edge:** The system provides no competitive advantage by design.
- **Judgment Replacement:** Users must interpret observations; the system does not decide.

**Purpose:** Prevent over-trust and misuse of neutral observations as actionable signals.

---

## 8. Recovery & Continuity Instructions

### 8.1 Authority of This Document

This document supersedes all informal understanding, previous conversations, and undocumented assumptions. In case of uncertainty, this document is the source of truth.

### 8.2 Pre-Change Protocol

Before any major change to the system:
1. Reread this document in full.
2. Verify the proposed change does not violate Section 3, 4, or 6.
3. If the change touches M5, verify it does not weaken governance.

### 8.3 Frozen Layers

**M1–M4 are frozen.** Modifications to these layers are prohibited except for:
- Bug fixes that restore documented behavior
- Performance optimizations that preserve determinism
- Schema migrations explicitly approved by the user

### 8.4 New Layer Interaction

Any new layer (M6+) must:
- Interact with memory **only** via M5
- Not bypass M5 governance
- Not introduce evaluative logic disguised as observation

---

## 9. Change Control Clause

### 9.1 Allowed Without Re-Authorization

- Bug fixes in M1–M5 that restore documented behavior
- Performance optimizations that preserve determinism and output
- Addition of new **neutral** M5 query types (if they pass epistemic safety review)
- Documentation updates that clarify existing rules

### 9.2 Requires Explicit User Approval

- Adding new M4 views
- Modifying M5 query schemas
- Changing M2 lifecycle logic
- Altering M3 evidence token definitions
- Any change to epistemic safety rules

### 9.3 Forbidden Outright

- Weakening M5 governance
- Introducing prediction, ranking, or scoring
- Bypassing M5 access control
- Adding evaluative semantics to M1–M4
- "Soft" violations of Section 3 principles

---

## 10. Final Authority Statement

This document defines the immutable contract of the Memory-Centric Market Observation System. It is not aspirational, not negotiable, and not subject to interpretation.

Violations are not "close enough" or "pragmatic compromises"—they are failures.

**Signed:** System Architect  
**Date:** 2026-01-04  
**Certification:** M1–M5 Complete & Frozen
