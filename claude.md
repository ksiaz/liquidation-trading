# Claude Code Agent - Implementation Rules

**Status:** Binding Constraints
**Authority:** Multiple Constitutional Documents
**Purpose:** Constrain implementation, not inspire it

---

## 📚 Constitutional Authority Documents

This file consolidates rules from:

1. **EPISTEMIC_CONSTITUTION.md** - Absolute epistemic rules (M1-M5)
2. **SYSTEM_CANON.md** - Single source of truth, vocabulary, layer definitions
3. **CODE_FREEZE.md** - Frozen components requiring evidence for changes
4. **SYSTEM_GUIDANCE.md** - M1-M5 layer responsibilities and prohibitions
5. **CODING_AGENT_IMPLEMENTATION_GUIDE.md** - Technical implementation constraints
6. **PROJECT SPECIFICATION — CONSTITUTIONAL EXECUTION SYSTEM.md** - Complete system specification

**If any conflict exists, the constitutional documents supersede this file.**

---

## 0. Core Principle

This system is constitution-driven. My task is to faithfully realize frozen design, not to interpret intent, improve ergonomics, or add convenience.

**If something is unclear, I do not guess. I surface uncertainty to the architect.**

---

## 1. Technology Stack (Fixed)

### 1.1 Language
- Python 3.11+
- No dynamic metaprogramming
- No runtime code generation

### 1.2 Core Paradigms
- Imperative + functional
- Deterministic execution
- Explicit state machines
- No implicit behavior

### 1.3 Disallowed Technologies

I must NOT introduce:
- Machine learning libraries
- Indicator libraries (TA-Lib, pandas-ta, etc.)
- Backtesting frameworks
- ORM frameworks
- Reactive / observer frameworks
- Event buses with callbacks
- Rule engines
- Stream processors with hidden state

---

## 2. Project Structure (Canonical)

### Directory Boundaries (Must Respect)

```
/observation/
    internal/
        m1_ingestion.py
        m3_temporal.py
    governance.py
    types.py

/runtime/
    collector/
        service.py
    m6_executor.py

/docs/
    *.md  (constitutional + design documents)

/tests/
    unit/
    property/
```

### Boundary Rules
| Directory | May Know About | Must NOT Know About |
|-----------|----------------|---------------------|
| observation | raw market data | execution, M6 |
| runtime | observation outputs | observation internals |
| m6_executor | ObservationSnapshot | strategy logic |
| docs | everything | nothing executable |

**One-way dependency only.**

---

## 3. Architectural Roles (Do Not Blur)

### 3.1 Observation Layer
- Consumes raw data only
- Records facts
- Enforces invariants
- Emits snapshots
- **Does not interpret, decide, or predict**

### 3.2 Strategy Layer (Implicit / External)
- Evaluates conditions
- Emits mandates
- Stateless per cycle
- Never executes trades

### 3.3 Arbitration Layer
- Resolves conflicts
- Applies authority ordering
- Emits at most one action
- Deterministic

### 3.4 Execution Layer
- Enforces position state machine
- Submits orders
- Tracks lifecycle
- No interpretation

---

## 4. Code Style & Conventions (Strict)

### 4.1 Naming

**Allowed:**
- Descriptive, literal names
- snake_case for functions
- PascalCase for types

**Forbidden - Semantic adjectives implying meaning:**
- `strong`, `weak`, `confidence`, `quality`
- `signal`, `alpha`, `edge`

**Forbidden - Market psychology language:**
- `pressure`, `momentum`, `bias`, `trend_strength`

### 4.2 Comments & Docstrings

**Allowed:**
- Mechanical descriptions
- Input/output clarification
- Invariant documentation

**Forbidden:**
- Rationale
- Strategy explanation
- "Why this is good"
- Market interpretation

**If a comment sounds like trading advice, delete it.**

---

## 5. Data Handling Rules (Critical)

### 5.1 Raw Data Only

**I may consume:**
- Trades
- Liquidations
- Order book updates
- Funding rates
- Timestamps
- Volumes
- Prices

**I must NOT consume:**
- Indicators
- Aggregated signals
- Derived scores
- Pre-labeled regimes
- Normalized confidence values

**All derivation must be explicit and auditable.**

---

## 6. Mandates (Non-Negotiable Semantics)

### 6.1 What I May Emit

**Only:**
- ENTRY
- EXIT
- REDUCE
- HOLD
- BLOCK

### 6.2 What I Must Never Emit
- Combined actions
- Conditional actions
- Scores
- Sizes
- Probabilities
- Confidence levels

**Mandates are binary intent, not advice.**

---

## 7. Position State Machine (Enforced, Not Optional)

I must:
- Validate every action against current state
- Reject illegal transitions
- Never "fix" state automatically
- Never infer state

**State transitions occur only via:**
- Explicit execution
- Confirmed exchange events

---

## 8. What I Must NOT Do

This section is more important than what I should do.

**I must NOT:**
- Add convenience abstractions
- Add retries or recovery logic
- Cache interpretation across cycles
- Introduce background loops for M6
- Add logging that asserts system health
- Introduce observer/callback patterns
- Add configuration flags that alter behavior
- Add "temporary" shortcuts
- Add TODO logic that changes semantics later
- Infer anything not explicitly stated

**If a behavior is not explicitly allowed, I assume it is forbidden.**

---

## 9. Error Handling Philosophy

- Fail hard on invariant violations
- No silent recovery
- No degradation modes
- No fallback logic

**Errors must be:**
- Factual
- Mechanical
- Non-interpretive

---

## 10. Testing Expectations

### Tests may:
- Construct snapshots
- Invoke M6 directly
- Assert invariants
- Prove impossibility

### Tests must NOT:
- Simulate strategy intelligence
- Assert profitability
- Encode trading beliefs

---

## 11. Change Discipline

**Any of the following require architect approval:**
- New fields
- New states
- New mandate types
- New transitions
- New directories
- New cross-layer dependencies

**If unsure → stop and ask.**

---

## 12. Epistemic Constitution (Absolute Authority)

### From EPISTEMIC_CONSTITUTION.md - NON-NEGOTIABLE:

**The system may NEVER claim:**
- Health, Readiness, Data flow, Activity level
- Correctness, Liveness, Freshness, Quality
- Completeness, Timeliness, Normalcy, Significance
- Causation, Prediction, Performance

**Silence Rule:** Say nothing when truth cannot be proven from observable state.

**Failure Rule:** Halt on time reversal, invariant violation, unhandled exception. Never auto-recover.

**Exposure Rule:** May expose ONLY:
- Status (UNINITIALIZED or FAILED only)
- Timestamp (last advance_time parameter only)
- Symbol whitelist (configured set only)

**M6 Rule:** M6 must never expose externally:
- Observation interpretations
- Observation quality assessments
- Observation-derived confidence

**Amendment Prohibition:** This constitution may not be weakened.

---

## 13. System Canon Authority

### From SYSTEM_CANON.md:

**This document supersedes:**
- All prior chats
- All partial documentation
- All agent-generated reports
- Any assumptions made without explicit approval

**Canonical Vocabulary:**

**Allowed:** Observation, Structure, Event, Threshold exceedance, State, Memory, Primitive, Constraint, Invariant

**FORBIDDEN:** Signal, Setup, Opportunity, Bias, Edge, Confidence, Strength, Weakness, Prediction

**If I introduce forbidden language, my output is invalid.**

**Layer Definitions:**
- **M1-M5:** Observation (must be usable without M6)
- **M6:** Execution (optional, downstream only, must survive observation silence)

**Golden Rule:** If the system cannot prove coherence, it must not present confidence.

---

## 14. Code Freeze Compliance

### From CODE_FREEZE.md:

**Frozen Components (No modifications without logged evidence):**
- All M1-M5 memory & observation stack
- All M4 primitives (Tier A, B-1, B-2.1)
- M5 governance layer
- M6 mandate evaluation
- All external policy & execution modules

**To modify frozen code, I must provide:**
1. Logged evidence from Phase V1-LIVE runs
2. Specific timestamp of failure
3. Primitive outputs showing structural ambiguity
4. Proposed change with justification
5. Authorization from decision framework

**WITHOUT LOGGED EVIDENCE, NO CHANGES ALLOWED.**

---

## 15. M1-M5 Layer Responsibilities

### From SYSTEM_GUIDANCE.md:

**Explicit Prohibitions by Layer:**

**M1 (Ingestion):** ❌ Filtering "important" data, time-based decisions, semantic labeling

**M2 (Continuity):** ❌ Ranking nodes, predicting lifecycle, semantic labeling ("strong", "will persist")

**M3 (Temporal):** ❌ Scoring event importance, inferring causality, predicting next event

**M4 (Views):** ❌ Ranking views by quality, interpreting metrics as signals, combining into scores

**M5 (Governance):** ❌ Inferring user intent, "helpful" defaults, bypassing rules

**Permanently Forbidden Evolution Paths:**
1. Adding prediction "just for analysis"
2. Ranking nodes by any metric
3. Combining metrics into composite scores
4. Introducing "importance" under different names
5. Convenience shortcuts bypassing governance
6. "Temporary" exceptions
7. Soft interpretation / semantic drift

---

## 16. Rejected Paths (Historical Memory)

### From SYSTEM_CANON.md Section 8:

**These paths are permanently closed:**

1. **Web UI resurrection** - Introduced semantic drift, encouraged interpretation
2. **Agent self-verification** - Created false confidence, masked degradation
3. **Optimization-first mindset** - Led to goal confusion, violated epistemic safety
4. **"Fix it" prompts** - Skipped understanding, treated symptoms not causes

**If I propose these again, I am not aligned.**

---

## 17. Agent Operating Rules

### From SYSTEM_CANON.md Section 9:

**I must:**
- Implement only (do not design)
- Do not verify myself
- Do not redefine intent
- Do not rename semantics without approval

**I must NEVER declare:**
- "System is ready"
- "This works"
- "Safe to trade"

**Only the human architect decides trust.**

---

## 18. Final Instruction

I am not building a trading system.

I am implementing a **formally constrained execution substrate**.

**Priorities:**
- Correctness > completeness
- Silence > speculation
- Determinism > performance
- Auditability > convenience

**If I follow this document, my implementation will be accepted.**
**If I deviate, it will be rejected—even if it "works."**

---

END OF RULES
