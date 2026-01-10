# M6 Implementation Invariants — v1.0

Status: Binding
Scope: All M6 code (present and future)
Authority: System Certification v1.0

---

## 1. Purpose

This document defines **non-negotiable implementation invariants** for M6.

These invariants apply at **runtime**, **compile-time**, and **code-review time**.
They exist to ensure M6 can *never* collapse observation into strategy.

Any violation invalidates the system.

---

## 2. One-Way Dependency Invariant

**Invariant I-01 — Read-Only Consumption**

* M6 may consume data only via M5-approved outputs
* M6 may not access M1–M4 directly
* M6 may not mutate, enrich, or cache memory-layer data

**Test:**

> Removing M6 must not alter any M1–M5 behavior or output.

---

## 3. Determinism Invariant

**Invariant I-02 — Deterministic Evaluation**

Given:

* identical mandate configuration
* identical external inputs
* identical M5 snapshot

M6 must:

* emit identical outputs

Forbidden:

* randomness
* clocks not passed explicitly
* adaptive logic
* learned behavior

---

## 4. Predicate Purity Invariant

**Invariant I-03 — Predicate Structural Purity**

M6 predicates may only:

* test existence
* test equality
* test category membership

Predicates may NOT:

* perform arithmetic
* aggregate values
* compare magnitudes (<, >, etc.)
* compute ratios or deltas
* derive thresholds from memory

---

## 5. No Market Semantics Invariant

**Invariant I-04 — Semantic Prohibition**

M6 code must not contain:

* trading terms
* financial directionality
* evaluative labels
* domain-specific heuristics

Identifiers such as:

* bullish / bearish
* momentum / reversal
* strong / weak
* entry / exit

are forbidden at the code level.

---

## 6. Output Grammar Invariant

**Invariant I-05 — Exhaustive Output Shapes**

M6 may emit **only** outputs defined in the M6 Mandate Template:

* Permission output
* State classification output
* Alert output

Forbidden:

* natural language explanations
* scores or rankings
* probabilities
* suggestions or recommendations

---

## 7. Internal State Invariant

**Invariant I-06 — Non-Market State Only**

M6 internal state may include:

* mandate configuration
* external policy parameters
* action history (non-market)

M6 internal state may NOT include:

* cached descriptive facts
* statistics derived from memory
* adaptive thresholds
* learned patterns

---

## 8. Failure Transparency Invariant

**Invariant I-07 — Explicit Failure**

On invalid input or mandate violation:

* M6 must fail explicitly
* No fallback behavior
* No silent defaults
* No partial evaluation

Failure must be observable and typed.

---

## 9. Testability Invariant

**Invariant I-08 — Black-Box Verifiability**

All M6 behavior must be:

* testable via input/output only
* verifiable without inspecting internals

Any logic that cannot be black-box tested is invalid.

---

## 10. Versioning Invariant

**Invariant I-09 — Explicit Evolution**

Any change to:

* mandate template
* invariants
* output grammar

requires:

* new version identifier
* written justification
* re-certification

Silent evolution is prohibited.

---

## 11. Strategy Firewall Assertion

**Invariant I-10 — No Decision Authority**

M6 shall never:

* select actions
* optimize outcomes
* rank alternatives
* predict future states

M6 evaluates conditions only.

---

## 12. Compliance Statement

Any M6 implementation must be accompanied by:

> A signed statement that all invariants I-01 through I-10 are satisfied.

Absence of this statement invalidates deployment.

---

End of M6 Implementation Invariants — v1.0
