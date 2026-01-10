# External Policy Interface Specification v1.0

Status: Authoritative
Scope: External to M1–M6
Compatibility: System v1.0 (Certified)

---

## 1. PURPOSE

This document defines the **formal interface contract** between the certified core system (M1–M6) and any **external policy, strategy, or decision engine**.

The goal is to enable unrestricted strategic experimentation **without contaminating memory, governance, or epistemic safety guarantees**.

---

## 2. HARD BOUNDARY STATEMENT (NON-NEGOTIABLE)

External Policy:

* SHALL consume **only** certified M6 outputs
* SHALL NOT access M1–M5 directly
* SHALL NOT mutate, enrich, or annotate memory
* SHALL NOT feed derived semantics back into M6

Violation of this boundary invalidates system certification.

---

## 3. INPUT CONTRACT (FROM M6)

External policy may receive only the following immutable output types.

### 3.1 PermissionOutput

```json
{
  "type": "PERMISSION",
  "result": "ALLOWED" | "DENIED",
  "reason_code": "STRING",
  "timestamp": "FLOAT"
}
```

Semantics:

* Indicates whether an external action is permitted under current mandates
* `reason_code` is opaque and non-evaluative

Prohibitions:

* Must not be interpreted as recommendation
* Must not be re-scored or ranked

---

### 3.2 StateClassificationOutput

```json
{
  "type": "STATE_CLASSIFICATION",
  "state_id": "STRING",
  "timestamp": "FLOAT"
}
```

Semantics:

* Represents a certified descriptive state
* State meaning exists **only inside external policy**

Prohibitions:

* State labels must not be reintroduced into M6

---

### 3.3 AlertOutput

```json
{
  "type": "ALERT",
  "alert_code": "STRING",
  "timestamp": "FLOAT"
}
```

Semantics:

* Signals a condition boundary crossing
* No implied urgency or direction

---

## 4. TEMPORAL RULES

* External policy MUST treat timestamps as authoritative
* Outputs MUST NOT be reused outside their timestamp context
* Policies must be robust to repeated identical outputs

---

## 5. EXTERNAL POLICY INTERNAL STRUCTURE (REFERENCE)

This structure is **recommended**, not enforced.

### EP-1: Interpreter Layer

Responsibilities:

* Map opaque M6 outputs to internal policy states
* Maintain one-way translation only

Example:

```text
STATE_12 → internal_context_A
ALERT_03 → review_trigger
```

---

### EP-2: Decision Logic Layer

Responsibilities:

* Apply strategy logic
* Use thresholds, probabilities, heuristics, or models
* Combine multiple M6 outputs if desired

All evaluative logic MUST live here.

---

### EP-3: Action Layer

Responsibilities:

* Execute trades, alerts, or decisions
* Enforce risk controls
* Log decisions with input provenance

---

## 6. LOGGING & AUDITABILITY (STRONGLY RECOMMENDED)

Each action should log:

* M6 output(s) consumed
* Policy version
* Decision taken
* Timestamp

This enables post-hoc analysis without altering memory.

---

## 7. VERSIONING RULES

* External policies must be versioned independently
* Changes to policy logic do NOT require system recertification
* M6 mandates may be reused across policy versions

---

## 8. FAILURE MODES & HANDLING

External policy MUST gracefully handle:

* Repeated DENIED permissions
* Missing or delayed alerts
* Identical state classifications over time

External policy MUST NOT:

* Retry by altering inputs
* Infer missing data

---

## 9. EXPLICIT PROHIBITIONS

External policy MUST NOT:

* Store long-term derived beliefs about memory
* Feed conclusions back into M6
* Attempt to infer intent from reason codes

---

## 10. CERTIFICATION STATEMENT

This interface preserves:

* Memory purity
* Governance authority
* Determinism guarantees

Any external system conforming to this specification may integrate with System v1.0 without invalidating certification.

---

End of External Policy Interface Specification v1.0
