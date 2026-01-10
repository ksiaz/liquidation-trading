# M6 Example Mandate v0 — Empty Predicate

Status: Example / Non-Operational
Purpose: Wiring proof only
Authority: Must conform to M6 Mandate Template v1.0

---

## 1. Mandate Declaration

```
mandate_id: M6-EXAMPLE-000
mandate_type: CONSTRAINT_GATE
mandate_scope: EXTERNAL_ACTION_GENERIC
```

This mandate exists solely to prove end-to-end wiring.
It encodes **no decision logic**.

---

## 2. Inputs

### 2.1 External Action Token

```
{
  "action_id": "ACTION-000",
  "action_type": "OPAQUE",
  "context": "OPAQUE"
}
```

Rules:

* Action semantics are not inspected
* Fields are passed through unchanged

---

### 2.2 M5-Approved Descriptive Snapshot

```
{
  "query_id": "QUERY-000",
  "timestamp": "EXPLICIT",
  "descriptive_facts": { }
}
```

Notes:

* Empty fact set is valid
* Snapshot is read-only

---

## 3. Policy Predicate (EMPTY)

```
POLICY_PREDICATE: NONE
```

Interpretation:

* No conditions are asserted
* No conditions are forbidden
* Predicate always evaluates to neutral

This is intentional.

---

## 4. Evaluation Semantics

Because the predicate is empty:

* No descriptive fact is tested
* No market state is implied
* No filtering or inference occurs

Evaluation outcome is **structural only**.

---

## 5. Output Grammar

### 5.1 Emitted Output

```
{
  "mandate_id": "M6-EXAMPLE-000",
  "action_id": "ACTION-000",
  "result": "ALLOWED",
  "reason_code": "NO_CONSTRAINT_DEFINED"
}
```

Properties:

* Deterministic
* Non-evaluative
* Non-actionable

---

## 6. Internal State

Internal state is limited to:

* mandate_id
* mandate_type

No descriptive facts are stored.
No historical memory is retained.

---

## 7. One-Way Contract Proof

Removing this mandate:

* Does not affect M1 ingestion
* Does not affect M2 continuity
* Does not affect M3 sequencing
* Does not affect M4 read models
* Does not affect M5 governance

Mandate is a pure consumer.

---

## 8. Non-Goals (Reaffirmed)

This mandate does NOT:

* Gate real actions
* Encode thresholds
* Encode strategy
* Encode market logic
* Perform analysis

---

## 9. Certification Note

This example is:

* structurally valid
* policy-empty
* safe to delete

It exists only to validate wiring.

---

End of Example Mandate v0
