# External Policy Example — v1.0 (Non-Market)

Status: External to Observation System
Authority: Consumes M6 outputs only
Scope: Demonstrative / Replaceable

---

## 1. Purpose

This document defines an **external policy** that consumes **M6 outputs only**.

It does **not** access M1–M5.
It does **not** interpret market data.
It does **not** influence memory.

The policy exists to prove safe separation between:

* observation (M1–M5)
* condition evaluation (M6)
* action selection (external)

---

## 2. Policy Inputs

The policy accepts **only** the following inputs:

### 2.1 M6 Output Token

One of:

* Permission Output
* State Classification Output
* Alert Output

Example:

```
{
  "mandate_id": "M6-EXAMPLE-001",
  "action_id": "ACTION-001",
  "result": "ALLOWED",
  "reason_code": "PREDICATE_SATISFIED"
}
```

No other inputs are permitted.

---

## 3. Policy Logic (Explicitly External)

The policy logic is **opaque to the system** and may include:

* organizational rules
* risk appetite
* compliance requirements
* operational constraints

Crucially:

* The policy does not know *why* M6 returned a result
* The policy does not know *what facts* were evaluated

It reacts only to the **type** of output.

---

## 4. Policy Decision Table (Illustrative)

| M6 Result | External Policy Action       |
| --------- | ---------------------------- |
| ALLOWED   | Action may proceed           |
| DENIED    | Action is blocked            |
| STATE_X   | Enter policy-defined state X |
| ALERT_Y   | Notify external system       |

Notes:

* No market semantics
* No optimization
* No inference

---

## 5. Responsibility Boundaries

### M6 Responsibilities

* Evaluate predicates
* Emit constrained outputs
* Guarantee determinism

### External Policy Responsibilities

* Decide what to do
* Accept risk
* Handle outcomes

No responsibility overlaps are allowed.

---

## 6. Failure Handling

If M6 output is:

* malformed
* unknown
* version-incompatible

Then:

* policy must fail closed
* no fallback behavior

---

## 7. Replaceability Guarantee

This policy may be:

* replaced
* rewritten
* removed

Without modifying:

* M1–M5
* M6
* mandate templates

This is intentional.

---

## 8. Non-Implications (Explicit)

This policy does NOT:

* define strategies
* interpret observations
* justify decisions
* influence memory

All meaning exists **outside** the system.

---

## 9. Certification Note

This example proves:

* the system can be used safely
* decision logic can exist externally
* observation integrity is preserved

---

End of External Policy Example — v1.0
