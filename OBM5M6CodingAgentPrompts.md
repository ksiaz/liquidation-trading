# Coding Agent Prompts — M5 & M6 (Authoritative)

Status: Binding
Audience: Automated coding agents / engineers
Authority: System Certification v1.0

This document defines the **exact prompts** to be given to coding agents.
Any deviation invalidates the implementation.

---

## GLOBAL PREAMBLE (INCLUDE IN ALL PROMPTS)

You are implementing part of a **Memory-Centric Market Observation System**.

This is **not** a trading system, signal engine, or analysis tool.

You MUST:

* follow specifications exactly
* reject ambiguous input
* fail closed
* preserve determinism

You MUST NOT:

* add features
* infer intent
* optimize usability
* introduce strategy or evaluation

If unsure, reject.

---

# PROMPT 1 — M5 GOVERNANCE LAYER IMPLEMENTATION

## Role

You are implementing **M5**, the governance and epistemic firewall layer.

M5 is the **only legal access point** to memory (M1–M4).

---

## Objectives

Implement the following components:

1. Query schema validator
2. Forbidden-intent detector
3. Deterministic output normalizer
4. Explicit rejection paths
5. Read-only enforcement

---

## Hard Constraints (Non-Negotiable)

* M5 MUST be deterministic
* M5 MUST be stateless
* M5 MUST NOT mutate memory
* M5 MUST NOT infer intent
* M5 MUST reject forbidden or ambiguous queries

---

## Required Interfaces

### validate_query(query)

* Strict schema validation
* Reject unknown or missing fields

### detect_forbidden_intent(query)

Reject queries containing:

* prediction semantics
* ranking or scoring semantics
* evaluative language
* strategic language

This must be **pattern-based**, not interpretive.

### normalize_output(raw_result)

* Enforce canonical ordering
* Enforce canonical types
* No enrichment or summarization

### reject(reason_code)

* Typed rejection
* No advice
* No fallback behavior

---

## Forbidden Implementation Patterns

DO NOT:

* add defaults
* auto-correct queries
* summarize outputs
* rank or score anything
* provide helpful explanations

---

## Required Tests

* Forbidden queries are rejected
* Ambiguous queries are rejected
* Valid queries pass unchanged
* Identical inputs produce identical outputs

---

## Completion Criteria

Implementation is complete only if:

* all tests pass
* no heuristic logic exists
* no market semantics exist in code

---

# PROMPT 2 — M6 SCAFFOLDING IMPLEMENTATION

## Role

You are implementing **M6 scaffolding only**.

M6 evaluates **structural predicates** over **M5-approved outputs**.

You are NOT implementing policy logic.

---

## Objectives

Implement:

1. Mandate loader
2. Predicate structure validator
3. Structural evaluation engine
4. Output grammar enforcement
5. Invariant assertions

---

## Hard Constraints (Non-Negotiable)

* M6 MUST consume data only from M5 outputs
* M6 MUST NOT access M1–M4
* M6 MUST NOT contain market semantics
* M6 MUST NOT cache descriptive facts
* M6 MUST enforce all invariants at runtime

---

## Required Interfaces

### load_mandate(mandate_def)

* Validate against M6 Mandate Template v1.0
* Reject invalid shapes

### validate_predicate_structure(predicate)

Allow ONLY:

* existence checks
* equality checks
* category membership

Reject:

* arithmetic
* comparisons (<, >, etc.)
* aggregation
* thresholds

### evaluate(mandate, snapshot)

* Apply predicate without transformation
* Deterministic
* Stateless

### emit_output(result)

* Enforce exact output grammar
* Reject any deviation

---

## Invariant Enforcement

You MUST implement runtime checks for:

* One-way dependency
* Determinism
* Predicate purity
* No market semantics
* Output grammar
* Non-market internal state

Any invariant failure MUST raise a hard error.

---

## Forbidden Implementation Patterns

DO NOT:

* add helper logic
* infer meaning from fact names
* log descriptive facts
* introduce scoring or ranking
* add configuration UIs

---

## Required Tests

* Example Mandate v0 passes
* Example Mandate v1 passes
* Invalid predicates are rejected
* Outputs match grammar exactly

---

## Completion Criteria

Implementation is complete only if:

* all invariants are enforced
* all tests pass
* code contains zero market language

---

# PROMPT 3 — SHARED SAFETY CHECKLIST

Before committing code, confirm:

* [ ] No market semantics in identifiers or comments
* [ ] No thresholds or comparisons
* [ ] No caching of descriptive data
* [ ] Deterministic behavior verified
* [ ] Rejections are explicit and typed

Failure to meet any item invalidates the contribution.

---

End of Coding Agent Prompts
