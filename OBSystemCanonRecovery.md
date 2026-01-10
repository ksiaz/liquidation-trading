# SYSTEM_CANON.md  
## Canonical Continuity & Authority Document  
**Project:** Memory-Centric Market Observation & Execution System  
**Status:** Authoritative / Non-Negotiable  
**Audience:** Human Architect, Any AI Coding or Analysis Agent  
**Purpose:** Full context restoration, epistemic firewall, and drift prevention  

---

## 0. AUTHORITY & SCOPE

This document is the **single source of truth** for this project.

It supersedes:
- All prior chats
- All partial documentation
- All agent-generated reports
- Any assumptions made without explicit architectural approval

If any agent output conflicts with this document, **the agent is wrong**.

If this document is violated, the system must be considered **untrusted** and **halted**.

This document exists to:
- Preserve original intent
- Prevent semantic drift
- Prevent agent self-approval
- Allow lossless restart of context in a new session

---

## 1. ORIGIN & INTENT (PRE-CODE)

This system was conceived as a **machine-first, emotionless, deterministic observer** of market structure.

It was **not** created to:
- Predict markets
- Optimize profitability
- Provide “signals”
- Provide comfort or reassurance to humans

It exists to:
- Observe structure
- Record facts
- Enforce discipline
- Act only when explicitly permitted

Silence is not failure.  
But **ambiguity is failure**.

---

## 2. EPISTEMIC CONTRACT

### 2.1 Observation vs Decision

Observation:
- Describes what has happened or is happening
- Is post-fact acceptable
- May be live, but must never imply foresight

Decision:
- Is downstream
- Is constrained
- Must never contaminate observation

Observation may **inform** execution.  
Execution must **never shape** observation.

---

### 2.2 Silence Rules

The system is expected to be silent most of the time.

Silence means:
- No structural condition met
- No action warranted
- No opinion expressed

Silence does **not** mean:
- Broken
- Idle
- Safe to assume correctness without checks

---

## 3. CANONICAL VOCABULARY & PRIMITIVES

Words matter. Renaming is corruption.

### Allowed:
- Observation
- Structure
- Event
- Threshold exceedance
- State
- Memory
- Primitive
- Constraint
- Invariant

### Forbidden:
- Signal
- Setup
- Opportunity
- Bias
- Edge
- Confidence
- Strength
- Weakness
- Prediction

If an agent introduces forbidden language, its output is invalid.

---

## 4. SYSTEM LAYERS (M1–M6)

### M1 — Ingestion
- Receives raw external facts
- Normalizes schema only
- No filtering by importance
- No decisions

### M2 — Continuity
- Tracks identity over time
- Maintains lifecycles
- No scoring, no ranking

### M3 — Temporal Ordering
- Orders evidence
- Closes windows
- Enforces causality
- No meaning assignment

### M4 — Contextual Views
- Read-only
- Aggregations allowed
- No composite scoring
- No ranking

### M5 — Governance (CRITICAL)
- Sole legal interface to observation
- Validates all queries
- Rejects forbidden semantics
- Enforces invariants
- Controls failure states

### M6 — Execution (SEPARATE)
- Optional
- Downstream only
- Must assume observation may halt
- Must survive observation silence

**Observation (M1–M5) must be usable without M6.**

---

## 5. GOVERNANCE & ARBITRATION

M5 is not a helper.  
M5 is a **firewall**.

M5 must:
- Reject invalid queries
- Reject implicit time
- Reject ranking
- Reject evaluative semantics

M5 must not:
- Guess intent
- Be “helpful”
- Auto-correct queries

Any bypass of M5 invalidates trust.

---

## 6. DETERMINISM, SIMULATION, REPLAY

The observation core must be:
- Deterministic
- Replayable
- Clock-injected only

Forbidden:
- time.time()
- datetime.now()
- implicit “now”

Allowed:
- Explicit timestamps
- External clock drivers
- Replay drivers

If the same data produces different observation outputs, the system is corrupt.

---

## 7. FAILURE MODES & TRUTHFULNESS

### Golden Rule:
**If the system cannot prove coherence, it must not present confidence.**

### States:
- LIVE: Data flowing and recent
- STALE: Data old but valid
- SYNCING: Recovering / backfilling
- FAILED: Invariant broken — halt

### Absolute requirement:
Data freshness must be measured by **last observed event time**, not clock ticks.

A system showing “OK” with no data is lying.

Lying systems are worse than broken systems.

---

## 8. REJECTED PATHS & DEAD ENDS (HISTORICAL MEMORY)

These paths are permanently closed:

1. **Web UI resurrection**
   - Introduced semantic drift
   - Encouraged interpretation
   - Corrupted intent

2. **Agent self-verification**
   - Agents approving their own fixes
   - Created false confidence
   - Masked degradation

3. **Optimization-first mindset**
   - Led to goal confusion
   - Encouraged shortcuts
   - Violated epistemic safety

4. **“Fix it” prompts**
   - Skipped understanding
   - Treated symptoms, not causes

If an agent proposes these again, it is not aligned.

---

## 9. AGENT OPERATING RULES

Coding agents:
- Implement only
- Do not design
- Do not verify themselves
- Do not redefine intent
- Do not rename semantics without approval

Analysis agents:
- May audit
- May expose contradictions
- May not authorize progression

No agent may declare:
- “System is ready”
- “This works”
- “Safe to trade”

Only the human architect decides trust.

---

## 10. HUMAN OPERATING RULES

You trust the system only when:
- It tells you when it is blind
- It halts loudly on incoherence
- It remains silent otherwise

You stop everything when:
- Observation lies
- Status remains green under failure
- You feel reassured instead of informed

Comfort is not a feature.

---

## 11. CONTINUITY INSTRUCTIONS (NEW CHAT PROTOCOL)

If starting a new chat:

1. Paste this entire document first.
2. State: “This is the canonical authority.”
3. Do **not** summarize.
4. Do **not** ask the agent to “understand” — assume enforcement.
5. Proceed only with architecture-level questions first.

If an agent deviates:
- Stop
- Re-anchor to this document
- Do not continue forward

---

## FINAL STATEMENT

This system is not a product.
It is not a tool.
It is a **discipline mechanism**.

If it ever feels helpful, intuitive, or reassuring,
it has already failed.

**End of Canon.**
