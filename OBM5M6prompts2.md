# Coding Agent Prompts — Audit & Verification (Certified System v1.0)

Status: Binding
System State: Certified & Frozen (v1.0)
Audience: Automated coding agents / reviewers
Authority: System Certification v1.0

This document **replaces** prior implementation prompts where they conflicted with the certified freeze.

It defines the **only admissible prompts** for work on M5 and M6 at this stage.

---

## GLOBAL PREAMBLE (MANDATORY)

You are operating on a **certified, frozen system**.

You MUST assume:

* M1–M5 are already implemented and certified
* Behavior is correct unless proven otherwise
* Any change risks invalidating certification

You MUST:

* audit, not redesign
* verify, not improve
* document, not reinterpret

You MUST NOT:

* reimplement components
* add features
* refactor for style or convenience
* introduce new semantics

If uncertainty exists, STOP and REPORT.

---

# PROMPT A — M5 COMPLIANCE AUDIT (PRIMARY)

## Role

You are auditing the **existing M5 implementation** (e.g. `memory/m5_*.py`).

This is a **verification task**, not an implementation task.

---

## Objective

Produce a **compliance report** evaluating whether the current M5 code conforms to:

* System Certification v1.0
* M5 Governance specification
* M6 Access Contract assumptions

---

## Audit Scope (Exhaustive)

You must verify the following properties:

1. **Schema Validation**

   * Queries are strictly validated
   * Unknown or missing fields are rejected

2. **Forbidden Intent Rejection**

   * Ranking, prediction, evaluation, strategy language is rejected
   * Detection is pattern-based, not inferential

3. **Determinism**

   * Identical inputs → identical outputs
   * No randomness, clocks, or adaptive behavior

4. **Read-Only Enforcement**

   * No mutation of M1–M4
   * No side effects

5. **Explicit Rejection Paths**

   * All rejections are typed
   * No silent fallbacks
   * No advisory language

6. **Semantic Purity**

   * No trader language in code or comments
   * No evaluative naming

---

## Required Output

Produce a report with the following structure:

```
SECTION: <Requirement Name>
- Code Locations: <files / functions>
- Status: PASS | FAIL | AMBIGUOUS
- Evidence: <specific lines or behaviors>
- Notes: <factual only>
```

Do NOT propose fixes unless explicitly requested.

---

## Classification Rules

If a violation is found, classify it as:

* Type 0 — Documentation / comment mismatch
* Type 1 — Bug violating documented behavior (fixable under freeze)
* Type 2 — Behavioral change (requires v1.1; DO NOT FIX)

---

## Forbidden Actions

DO NOT:

* modify code
* suggest refactors
* suggest optimizations
* suggest new features

---

## Completion Criteria

Audit is complete only when:

* all six properties are evaluated
* all findings are classified
* no speculative language is used

---

# PROMPT B — M6 SCAFFOLDING VERIFICATION

## Role

You are verifying **M6 scaffolding code** (if present) against certified design artifacts.

---

## Objective

Verify conformance to:

* M6 Mandate Template v1.0
* M6 Implementation Invariants v1.0
* Example Mandates v0 and v1

---

## Audit Scope

You must confirm:

1. Mandate loading rejects invalid shapes
2. Predicate validation allows only:

   * existence
   * equality
   * category membership
3. No arithmetic, thresholds, aggregation
4. No market semantics in identifiers
5. Output grammar is exact
6. Invariants are enforced at runtime

---

## Required Output

Use the same report format as PROMPT A.

---

## Forbidden Actions

DO NOT:

* add logic
* extend predicates
* interpret semantics

---

# PROMPT C — ALLOWED PATCH IMPLEMENTATION (ONLY IF AUTHORIZED)

## Preconditions

This prompt may be used **only if**:

* A Type 1 bug has been identified
* The bug violates documented certified behavior
* Explicit authorization is given

---

## Objective

Apply the **minimum change** necessary to restore certified behavior.

---

## Constraints

* No new functionality
* No refactors
* No behavior extension
* Change must be reversible

---

## Required Output

* Diff only
* Explanation referencing certification document
* Confirmation that behavior now matches spec

---

## Hard Stop

If the fix would alter system semantics:

STOP.
DO NOT IMPLEMENT.
FLAG AS v1.1 REQUIRED.

---

End of Coding Agent Prompts — Audit & Verification
