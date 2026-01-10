# Coding Agent Prompt — M6 Scaffolding Initial Implementation (Certified v1.0)

Status: Binding
System State: Certified & Frozen v1.0
Audience: Automated coding agent
Authority: System Certification v1.0

This prompt authorizes the **initial creation of M6 scaffolding code only**.

M6 logic, strategy, optimization, or market semantics are **strictly forbidden**.

---

## GLOBAL PREAMBLE (MANDATORY)

You are implementing **M6 scaffolding** for a certified system.

Assume:

* M1–M5 already exist and are frozen
* M5 is the only legal source of descriptive data
* M6 is a boundary evaluator, not a decision-maker

You MUST:

* follow specifications exactly
* fail closed
* preserve determinism
* enforce invariants at runtime

You MUST NOT:

* add strategy or policy logic
* add thresholds, arithmetic, or ranking
* interpret market meaning
* add convenience features

If uncertain, STOP and REPORT.

---

## ROLE

You are implementing **M6 scaffolding from scratch**, constrained by:

* M6 Mandate Template v1.0
* M6 Implementation Invariants v1.0
* Example Mandate v0 and v1

This is structural code only.

---

## OBJECTIVES

Implement the following components:

1. Mandate loader
2. Predicate structure validator
3. Structural evaluation engine
4. Output grammar enforcement
5. Runtime invariant assertions

No other components are permitted.

---

## REQUIRED MODULES / FUNCTIONS

### 1. Mandate Loader

**Purpose:** Load and validate mandate definitions.

Requirements:

* Validate mandate shape against template
* Reject unknown fields
* Reject invalid mandate_type
* Mandates are immutable after load

---

### 2. Predicate Structure Validator

**Purpose:** Enforce predicate admissibility.

Allow ONLY:

* existence checks
* equality checks
* category membership checks

Reject:

* arithmetic of any kind
* comparisons (<, >, <=, >=)
* aggregation (count, sum, avg, etc.)
* thresholds

Validation must be structural, not semantic.

---

### 3. Structural Evaluation Engine

**Purpose:** Apply predicates to M5 snapshots.

Requirements:

* Input: mandate + M5-approved snapshot
* Output: boolean or categorical result
* No mutation
* No caching
* No learning
* Deterministic

---

### 4. Output Grammar Enforcement

**Purpose:** Emit only certified M6 outputs.

Allowed outputs:

* Permission output
* State classification output
* Alert output

Reject any deviation from grammar.

---

### 5. Runtime Invariant Assertions

You MUST assert and enforce:

* One-way dependency (no access to M1–M4)
* Determinism (no clocks, randomness)
* Predicate purity
* No market semantics in identifiers
* No descriptive data stored internally

Invariant failure MUST raise a hard error.

---

## FORBIDDEN IMPLEMENTATION PATTERNS

DO NOT:

* infer meaning from fact names
* log descriptive facts
* add helper or convenience logic
* add configuration UIs
* add metrics or scoring

---

## REQUIRED TESTS

You MUST include tests that prove:

* Example Mandate v0 evaluates correctly
* Example Mandate v1 evaluates correctly
* Invalid predicates are rejected
* Invalid output shapes are rejected
* Identical inputs produce identical outputs

---

## COMPLETION CRITERIA

Implementation is complete ONLY IF:

* All required components exist
* All invariants are enforced
* All tests pass
* Code contains ZERO market semantics

---

## HARD STOP

If at any point you believe:

* logic is required
* a threshold would help
* semantics are missing

STOP.
DO NOT IMPLEMENT.
REPORT BLOCKER.

---

End of M6 Scaffolding Initial Implementation Prompt
