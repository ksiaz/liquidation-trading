# M6 Mandate Template — v1.0

Status: Design-Level Artifact (No Logic)
Scope: Applies to all admissible M6 instances
Authority: Constrained by System Certification v1.0

---

## 1. Purpose of This Template

This document defines the **only admissible structural template** for M6 mandates.

An M6 mandate:

* does **not** encode strategy
* does **not** encode market semantics
* does **not** encode thresholds derived from memory
* does **not** interpret descriptive facts

It exists solely to **apply externally defined policy predicates** to **M5-approved descriptive outputs**.

---

## 2. Mandate Identity

Each M6 mandate MUST declare:

* `mandate_id` — unique, immutable identifier
* `mandate_type` — one of the allowed archetypes
* `mandate_scope` — what class of external actions it applies to

### Allowed Mandate Types

* POLICY_EVALUATOR
* CONSTRAINT_GATE
* STATE_CLASSIFIER
* ALERT_EMITTER

Any other type is invalid.

---

## 3. Inputs (Strict Contract)

An M6 mandate may receive **only** the following inputs.

### 3.1 External Action Token (Optional)

Used only by POLICY_EVALUATOR or CONSTRAINT_GATE mandates.

```
{
  "action_id": "string",
  "action_type": "opaque",
  "context": "opaque"
}
```

Rules:

* M6 must treat all fields as opaque
* No parsing or inference is allowed
* No market meaning may be assumed

---

### 3.2 M5-Approved Descriptive Snapshot (Required)

```
{
  "query_id": "string",
  "timestamp": "explicit",
  "descriptive_facts": { ... }
}
```

Properties:

* Deterministic
* Stateless
* Read-only
* No ranking
* No interpretation

M6 must not requery M5 dynamically.

---

## 4. Policy Predicate Declaration (Non-Executable)

Each mandate must declare its **policy predicate** as a structural specification, not executable logic.

Example form:

```
POLICY_PREDICATE:
  requires:
    - existence of fact_A
    - boolean equality on fact_B
  forbids:
    - absence of fact_C
```

Rules:

* Predicates may only test existence, equality, or category membership
* No arithmetic
* No aggregation
* No comparison operators (<, >, <=, >=)
* No thresholds learned from memory

---

## 5. Output Grammar (Exhaustive)

An M6 mandate may emit **only one** of the following output forms.

### 5.1 Permission Output

```
{
  "mandate_id": "string",
  "action_id": "string",
  "result": "ALLOWED" | "DENIED",
  "reason_code": "enum"
}
```

### 5.2 State Classification Output

```
{
  "mandate_id": "string",
  "state_id": "enum",
  "timestamp": "explicit"
}
```

### 5.3 Alert Output

```
{
  "mandate_id": "string",
  "alert_code": "enum",
  "timestamp": "explicit"
}
```

Forbidden:

* Natural language explanations
* Scores or rankings
* Probabilities or confidence
* Recommendations
* Next-step hints

---

## 6. Internal State Constraints

M6 mandates may maintain **only**:

* mandate configuration
* external policy parameters
* action history (non-market)

They may NOT maintain:

* cached descriptive facts
* learned statistics
* adaptive thresholds
* pattern memory

---

## 7. Non-Goals (Explicit)

An M6 mandate shall never:

* choose actions
* optimize outcomes
* predict future states
* rank alternatives
* label states as good/bad
* encode trading logic
* bypass M5 governance

---

## 8. Compliance Test (Required)

Each mandate must pass the following proof:

> Removing the mandate entirely does not alter any M1–M5 output.

If this is false, the mandate is invalid.

---

## 9. Versioning Rule

Any change to this template requires:

* new version identifier
* explicit justification
* re-certification

Silent evolution is prohibited.

---

End of Template
