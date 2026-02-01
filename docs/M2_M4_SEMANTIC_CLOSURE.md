# M2 & M4 Semantic Closure & Change-Control Document

**Document Type:** Constitutional Amendment
**Effective Date:** 2026-02-01
**Status:** RATIFIED
**Authority:** This document supersedes all prior informal specifications of M2 and M4.

---

## 1. FORMAL DECLARATION OF CLOSURE

### 1.1 M2 (Structural Memory Layer)

**STATUS: CLOSED**

M2 is hereby declared architecturally complete. No further structural changes, feature additions, or behavioral modifications are permitted without explicit constitutional amendment.

**Scope of Closure:**
- `memory/m2_continuity_store.py`
- `memory/enriched_memory_node.py`
- `memory/m2_memory_state.py`
- `memory/m2_historical_evidence.py`
- `memory/m2_topology.py`
- `memory/m2_pressure.py`
- `observation/governance.py` (M2 population paths only: lines 415-523)

### 1.2 M4 (Structural Primitives Layer)

**STATUS: CLOSED**

M4 is hereby declared architecturally complete. No new primitives may be added, no existing primitives may be modified in semantic meaning, and no computation logic may be altered without explicit constitutional amendment.

**Scope of Closure:**
- `memory/m4_*.py` (all 27 primitive modules)
- `observation/types.py` (M4PrimitiveBundle definition)
- `observation/governance.py` (primitive computation: `_compute_primitives_for_symbol()`)

---

## 2. REPRESENTATIONAL BOUNDARIES

### 2.1 M2: What It Is Allowed to Represent

| Allowed | Description |
|---------|-------------|
| Price locations | Specific price levels where events occurred |
| Temporal facts | When events occurred (first_seen, last_interaction) |
| Event counts | How many interactions, trades, liquidations |
| Volume aggregates | Total volume, buyer/seller initiated volume |
| Lifecycle state | ACTIVE, DORMANT, ARCHIVED (based on decay) |
| Spatial relationships | Node clustering, gaps, density |
| Evidence dimensions | 4 factual dimensions per node |

### 2.2 M2: What It Must Never Represent

| Forbidden | Rationale |
|-----------|-----------|
| Quality scores | Implies ranking or desirability |
| Importance rankings | Implies preference |
| Opportunity flags | Implies action recommendation |
| Prediction of future behavior | Violates descriptive-only constraint |
| Expected price reaction | Teleological interpretation |
| "Strong" vs "weak" zones | Quality judgment |
| Trade recommendations | Action implication |
| Performance metrics | Optimization feedback |

### 2.3 M4: What It Is Allowed to Represent

| Allowed | Description |
|---------|-------------|
| Geometric facts | Zone penetration, displacement, traversal |
| Kinematic facts | Velocity, compactness, direction |
| Temporal patterns | Absence duration, persistence, bursts |
| Count aggregates | Event counts, trade counts, liquidation counts |
| Statistical distributions | Density, concentration, ratios |
| Lifecycle observations | Cascade phases (as backward-looking states) |
| Structural conditions | Pattern presence/absence based on thresholds |

### 2.4 M4: What It Must Never Represent

| Forbidden | Rationale |
|-----------|-----------|
| Probability of future events | Prediction violates descriptive constraint |
| Expected outcomes | Teleological interpretation |
| Quality of patterns | Implies ranking |
| Trade signals | Action implication |
| Entry/exit recommendations | Execution domain |
| "Good" vs "bad" setups | Value judgment |
| Edge quantification | Optimization metric |
| Win rate or expectancy | Performance feedback |

---

## 3. LOCKED INVARIANTS

### Invariant 1: Evidence-at-Creation

**Statement:**
> Every M2 node must have its causal evidence recorded at the moment of creation.

**Enforcement:**
- Nodes created from liquidation events MUST call `record_liquidation_at_node()` immediately after `add_or_update_node()`
- Nodes created from trade events MUST call `record_trade_at_node()` immediately after `add_or_update_node()`
- No node may exist in ACTIVE state with zero evidence of its creation cause

**Violation Response:** Immediate code correction required.

---

### Invariant 2: Descriptive-Only

**Statement:**
> M2 and M4 may only describe what IS or what WAS. They may never describe what WILL BE, what SHOULD BE, or what COULD BE.

**Enforcement:**
- All primitive names must be descriptive nouns or adjectives
- No primitive may contain verbs implying future action
- No primitive may contain probability or likelihood
- Documentation must not suggest predictive capability

**Violation Response:** Semantic audit and potential constitutional amendment.

---

### Invariant 3: No Optimization / No Intent

**Statement:**
> M2 and M4 must contain zero optimization logic, zero parameter tuning, zero intent inference, and zero desirability scoring.

**Enforcement:**
- No gradient descent or learning algorithms
- No threshold adjustment based on outcomes
- No "best" selection (except deterministic representative selection)
- No ranking by quality, importance, or opportunity
- Thresholds define structural conditions, not desirability

**Violation Response:** Immediate removal of offending logic.

---

### Invariant 4: No Execution Feedback

**Statement:**
> Information flow is strictly one-way: Raw Data → M1 → M2/M3 → M4 → Snapshot → Downstream. Execution outcomes must never flow back into observation layers.

**Enforcement:**
- M2 and M4 have no references to execution modules
- No trade result, P&L, or fill data enters observation
- No "performance" of primitives is tracked
- Observation is blind to what happens downstream

**Violation Response:** Architectural isolation breach; requires immediate correction.

---

### Invariant 5: Symbol Isolation

**Statement:**
> M2 nodes and M4 primitives are scoped to individual symbols. Cross-symbol inference or correlation is forbidden within these layers.

**Enforcement:**
- All queries are symbol-scoped
- No M2 node spans multiple symbols
- M4 primitives are computed per-symbol
- Cross-symbol analysis belongs to external policy layer

**Violation Response:** Scope expansion requires constitutional amendment.

---

## 4. ACCEPTABLE TERMINOLOGY

### 4.1 Conventional Names with Tolerated Usage

The following terms are inherited from market structure literature and are tolerated despite borderline teleological implications:

| Term | Tolerated In | Meaning (Strictly) |
|------|--------------|-------------------|
| "supply" | SupplyDemandZonePrimitive.zone_type | Cluster above current price |
| "demand" | SupplyDemandZonePrimitive.zone_type | Cluster below current price |
| "order block" | OrderBlockPrimitive | Price level with bursty interaction pattern |
| "absorption" | AbsorptionEvent, AbsorptionPhase | Consumption with limited price movement |
| "support" | (if used) | Cluster below price with interactions |
| "resistance" | (if used) | Cluster above price with interactions |

### 4.2 Mandatory Interpretation Disclaimer

All tolerated conventional terms carry this implicit disclaimer:

> **These names describe observed structural patterns only. They carry no implication of future price behavior, market reaction, or trading opportunity. The term is borrowed from market convention for recognizability, not for predictive meaning.**

### 4.3 Forbidden Terminology

The following terms are NEVER permitted in M2 or M4:

| Forbidden Term | Rationale |
|----------------|-----------|
| "signal" | Implies action recommendation |
| "opportunity" | Implies desirability |
| "edge" | Implies performance |
| "prediction" | Violates descriptive constraint |
| "forecast" | Violates descriptive constraint |
| "target" | Implies expected outcome |
| "invalidation" | Implies expectation violation |
| "confirmation" (as predictive) | Implies future validation |
| "quality" | Implies ranking |
| "score" | Implies ranking |
| "probability" | Implies prediction |
| "likely" / "unlikely" | Implies prediction |

---

## 5. CHANGE CONTROL RULES

### 5.1 Change Classification

| Change Type | Examples | Required Process |
|-------------|----------|------------------|
| **Bug Fix** | Evidence not recorded, calculation error | Code review + test |
| **Threshold Adjustment** | Changing min_interactions from 10 to 15 | Semantic audit |
| **New Field** | Adding a field to EnrichedLiquidityMemoryNode | Constitutional amendment |
| **New Primitive** | Adding a new M4 primitive | Constitutional amendment |
| **Semantic Change** | Changing what a primitive means | Constitutional amendment |
| **Invariant Modification** | Changing any invariant in Section 3 | Constitutional amendment + architectural review |

### 5.2 Semantic Audit Requirements

A semantic audit is required when:
- Any threshold is modified
- Any field name is changed
- Any documentation is updated that affects meaning
- Any tolerated conventional term is added

**Audit Must Confirm:**
1. Change does not introduce predictive language
2. Change does not introduce optimization logic
3. Change does not create feedback from execution
4. Change does not imply action recommendation

### 5.3 Constitutional Amendment Requirements

A constitutional amendment is required when:
- Any new primitive is proposed
- Any new M2 node field is proposed
- Any invariant is proposed for modification
- Any representational boundary is proposed for change

**Amendment Process:**
1. Written proposal with rationale
2. Impact analysis on downstream layers
3. Semantic audit of proposed changes
4. Explicit approval from architectural authority
5. Update to this document

### 5.4 Architectural Approval Authority

Changes requiring constitutional amendment must be approved by:
- System architect (human)
- Documented in version control with amendment reference
- This document updated to reflect amendment

---

## 6. FUTURE WORK CONSTRAINTS

### 6.1 What Future Work Must NOT Do

| Prohibited Action | Rationale |
|-------------------|-----------|
| Add new M4 primitives | Layer is closed |
| Modify primitive semantics | Constitutional violation |
| Tune thresholds for "better" results | Optimization forbidden |
| Add performance tracking to observation | Feedback forbidden |
| Create cross-symbol M2 nodes | Symbol isolation invariant |
| Add prediction logic | Descriptive-only invariant |
| Rank primitives by quality | No optimization invariant |
| Backtest primitives inside observation | Feedback forbidden |
| Use M4 values to adjust M2 behavior | Circular dependency |

### 6.2 Where Future Work Must Go

| Domain | Appropriate Layer |
|--------|-------------------|
| Strategy logic | External Policy (M6+) |
| Trade decisions | Execution Layer |
| Performance analysis | External analytics (outside runtime) |
| Threshold optimization | Research environment (not runtime) |
| Cross-symbol correlation | External policy or research |
| Backtesting | Separate backtesting harness |
| Parameter tuning | Research, then freeze in config |

### 6.3 Permitted Downstream Consumption

M4 primitives may be consumed by:
- Policy adapters (read-only)
- Mandate generators (read-only)
- External logging (write to DB, no feedback)
- Research tools (offline analysis)

Consumers must:
- Treat primitives as immutable facts
- Never send feedback to observation
- Never modify observation behavior based on outcomes

---

## 7. FORMAL STATEMENTS

### 7.1 Closure Declaration

> M2 (Structural Memory) and M4 (Structural Primitives) are hereby declared **ARCHITECTURALLY CLOSED** as of 2026-02-01. These layers are complete, audited, and constitutionally locked. No modifications are permitted without explicit constitutional amendment following the process defined in Section 5.

### 7.2 Immutability Statement

> The invariants defined in Section 3 are **IMMUTABLE** and may not be weakened, bypassed, or violated by any future work. Violation of any invariant constitutes a constitutional breach requiring immediate correction.

### 7.3 Downstream Directive

> All future development work must proceed **DOWNSTREAM** of M4. The observation layers (M1-M4) are inputs to the system, not subjects of optimization. Any attempt to re-enter these layers for performance improvement, signal enhancement, or behavioral modification is a constitutional violation.

### 7.4 Semantic Finality

> The semantic meaning of all M2 fields and M4 primitives is **FINAL** as documented. No reinterpretation, no "enhancement," no "clarification" that changes meaning is permitted. If a primitive's meaning is unclear, the resolution must be found in existing documentation, not invented.

---

## 8. AMENDMENT LOG

| Date | Amendment | Approver | Reference |
|------|-----------|----------|-----------|
| 2026-02-01 | Initial ratification | System | This document |

---

## 9. SIGNATURES

**Document Status:** RATIFIED

**Scope:** M2 (Structural Memory), M4 (Structural Primitives)

**Effective:** Immediately upon creation

**Authority:** This document is the canonical reference for M2 and M4 change control.

---

*End of Semantic Closure & Change-Control Document*
