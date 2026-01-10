# External Liquidity-Based Policy Module Design v1.0

Status: Authoritative (External System)
Scope: External Policy Layer (EP-2)
Compatibility: System v1.0 (Certified Core)
Audience: Coding Agent (Strategy Module Implementation)

---

## 1. PURPOSE

This document specifies the **first external strategy module** to be implemented on top of the External Policy Skeleton.

The module is **liquidity-based**, but deliberately **non-executive**:

* It interprets *contexts* (not raw data)
* It produces *intent proposals* (not actions)
* It never bypasses arbitration, risk, or M6 permissions

---

## 2. POSITION IN ARCHITECTURE

```
[M6 Outputs]
   ↓
[EP-0 Adapter]
   ↓
[EP-1 Context Router]
   ↓
[EP-2 Liquidity Policy Module]  ← THIS DOCUMENT
   ↓
[EP-3 Arbitration & Risk Gate]
   ↓
[EP-4 Execution / Simulation]
```

This module has **no authority** to execute trades.

---

## 3. INPUT CONTRACT

### Inputs (Read-Only)

* `ContextState` from EP-1
* Explicit timestamps

The module MUST NOT:

* Access M6 outputs directly
* Access M1–M5 data
* Modify contexts

---

## 4. OUTPUT CONTRACT

### Output Type: IntentProposal

```python
IntentProposal(
    source="LIQUIDITY_POLICY",
    intent_type="LONG" | "SHORT" | "FLAT" | "IGNORE",
    confidence: float,        # 0.0 – 1.0 (local, non-binding)
    rationale: str | None,    # optional, internal/debug only
    timestamp: float
)
```

Rules:

* Confidence is advisory only
* IntentProposal does not imply execution
* Arbitration may discard this entirely

---

## 5. CONTEXT DEPENDENCIES (DECLARATIVE)

This module reacts ONLY to the presence/absence of specific contexts.

### Example Contexts (Opaque)

* `CONTEXT_LIQUIDITY_SWEEP`
* `CONTEXT_RANGE_COMPRESSION`
* `CONTEXT_INDUCEMENT_ZONE`
* `CONTEXT_STRUCTURE_BOUNDARY`

**Important:** These context names are *internal labels*, not market facts.

---

## 6. DECISION LOGIC (NON-EVALUATIVE)

### Core Principle

The module expresses **directional hypotheses** based on liquidity-related contexts, without asserting correctness or priority.

### Illustrative Rules (Not Exhaustive)

| Active Contexts                      | Proposed Intent                                  |
| ------------------------------------ | ------------------------------------------------ |
| LIQUIDITY_SWEEP + STRUCTURE_BOUNDARY | LONG or SHORT (configurable polarity)            |
| LIQUIDITY_SWEEP only                 | IGNORE                                           |
| RANGE_COMPRESSION + INDUCEMENT_ZONE  | PREPARE (expressed as FLAT with high confidence) |
| No liquidity-related contexts        | IGNORE                                           |

The module MUST:

* Avoid ranking outcomes
* Avoid thresholds implying certainty
* Avoid persistence across time without re-evaluation

---

## 7. TEMPORAL BEHAVIOR

* Stateless by default
* Evaluated on each new ContextState
* No memory of past intents unless explicitly allowed later

---

## 8. CONFIGURATION SURFACE (ALLOWED)

The following parameters may be configurable **externally**:

* Context → intent polarity mapping
* Maximum confidence cap (e.g., 0.6)
* Whether conflicting contexts suppress output

Configuration MUST:

* Be static at runtime (no learning)
* Not depend on market values

---

## 9. EXPLICIT PROHIBITIONS

This module MUST NOT:

* Execute trades
* Enforce risk limits
* Override M6 PermissionOutput
* Aggregate across time
* Learn or adapt
* Use price, volume, or indicator values

---

## 10. TESTING REQUIREMENTS

The coding agent MUST provide:

* Unit tests for each context combination
* Tests proving no output when contexts absent
* Tests proving determinism (same input → same output)

---

## 11. SUCCESS CRITERIA

The module is considered complete when:

* It produces IntentProposals solely from contexts
* It can be added/removed without affecting other modules
* Arbitration correctly receives and may ignore its outputs

---

## 12. HANDOFF NOTE TO CODING AGENT

This is **not** a trading strategy.

It is a *hypothesis generator* constrained by architecture.

If you feel tempted to add execution logic, risk logic, or memory — stop.

That would violate the system’s core design.

---

End of External Liquidity-Based Policy Module Design v1.0
