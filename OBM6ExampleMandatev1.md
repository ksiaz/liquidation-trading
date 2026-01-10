# M6 Example Mandate v1 — Non-Empty Abstract Predicate

Status: Example / Non-Market / Non-Operational
Purpose: Prove predicate wiring without semantic leakage
Authority: Must conform to:

* M6 Mandate Template v1.0
* M6 Implementation Invariants v1.0

---

## 1. Mandate Declaration

```
mandate_id: M6-EXAMPLE-001
mandate_type: CONSTRAINT_GATE
mandate_scope: EXTERNAL_ACTION_GENERIC
```

This mandate introduces a **non-empty predicate** while remaining fully abstract.

---

## 2. Inputs

### 2.1 External Action Token

```
{
  "action_id": "ACTION-001",
  "action_type": "OPAQUE",
  "context": "OPAQUE"
}
```

Rules:

* Action semantics are opaque
* No inference is allowed

---

### 2.2 M5-Approved Descriptive Snapshot

```
{
  "query_id": "QUERY-001",
  "timestamp": "EXPLICIT",
  "descriptive_facts": {
    "fact_X": true,
    "fact_Y": "CATEGORY_A",
    "fact_Z": {
      "exists": true
    }
  }
}
```

Notes:

* Fact names are placeholders
* No market meaning is implied

---

## 3. Policy Predicate (Declared)

```
POLICY_PREDICATE:
  requires:
    - fact_X == true
    - fact_Y ∈ { CATEGORY_A, CATEGORY_B }
  forbids:
    - absence of fact_Z
```

Properties:

* Uses only existence, equality, and category membership
* No arithmetic
* No ordering
* No aggregation
* No thresholds

---

## 4. Evaluation Semantics

Evaluation proceeds as follows:

* Predicate is evaluated against the descriptive snapshot
* No transformation of facts occurs
* No caching or enrichment occurs

If all `requires` are satisfied and no `forbids` are violated:

* Result = ALLOWED

Otherwise:

* Result = DENIED

No other outcomes are possible.

---

## 5. Output Grammar

### 5.1 Allowed Outcome

```
{
  "mandate_id": "M6-EXAMPLE-001",
  "action_id": "ACTION-001",
  "result": "ALLOWED",
  "reason_code": "PREDICATE_SATISFIED"
}
```

### 5.2 Denied Outcome

```
{
  "mandate_id": "M6-EXAMPLE-001",
  "action_id": "ACTION-001",
  "result": "DENIED",
  "reason_code": "PREDICATE_VIOLATED"
}
```

Notes:

* reason_code is symbolic, not explanatory
* No natural language emitted

---

## 6. Internal State

Internal state is restricted to:

* mandate_id
* predicate declaration

No descriptive facts are stored.
No historical data is retained.

---

## 7. One-Way Contract Proof

Removing this mandate:

* Does not alter M1–M4 memory
* Does not alter M5 governance
* Does not alter descriptive outputs

This mandate is a pure consumer.

---

## 8. Non-Implications (Explicit)

This mandate does NOT imply:

* that fact_X is good or bad
* that CATEGORY_A is preferred
* that denial is negative
* that allowance is recommendation
* that any action should be taken

---

## 9. Certification Note

This example proves:

* Non-empty predicates are possible
* Predicate logic can be enforced
* No market semantics are required
* No strategy leakage occurs

---

End of Example Mandate v1
