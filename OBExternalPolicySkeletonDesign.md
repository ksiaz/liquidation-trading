# External Policy Skeleton Design v1.0

Status: Authoritative (External System)
Scope: External to M1–M6
Compatibility: System v1.0 (Certified & Frozen)
Audience: Coding Agent (External Policy Implementation)

---

## 1. PURPOSE

This document defines the **minimal, strategy-agnostic external policy skeleton** that integrates with the certified core system (M1–M6).

The skeleton establishes:

* One-way data flow from M6
* Context routing without interpretation
* Arbitration and risk gating without strategy logic

No trading logic, optimization, or market semantics are implemented at this stage.

---

## 2. NON-NEGOTIABLE CONSTRAINTS

The external policy skeleton:

* SHALL consume **only M6 outputs**
* SHALL NOT access M1–M5
* SHALL NOT mutate memory or M6 outputs
* SHALL NOT embed market semantics in routing or arbitration
* SHALL remain deterministic given identical inputs

Violation of these constraints invalidates system integration.

---

## 3. HIGH-LEVEL ARCHITECTURE

```
[M6 Output Stream]
        ↓
[EP-0 Adapter]
        ↓
[EP-1 Context Router]
        ↓
[EP-3 Arbitration & Risk Gate]
        ↓
[EP-4 Execution Stub / Simulator]
```

EP-2 (Strategy Modules) are intentionally excluded at this stage.

---

## 4. EP-0: M6 ADAPTER

### Responsibility

* Subscribe to certified M6 outputs
* Normalize outputs into internal event objects
* Preserve timestamps and immutability

### Input

* PermissionOutput
* StateClassificationOutput
* AlertOutput

### Output

```python
ExternalEvent(
    source="M6",
    event_type="PERMISSION" | "STATE" | "ALERT",
    code: str,
    timestamp: float
)
```

### Prohibitions

* No interpretation of codes
* No caching beyond ordered event queue
* No enrichment or tagging

---

## 5. EP-1: CONTEXT ROUTER

### Responsibility

* Map ExternalEvent objects to **internal, opaque contexts**
* Maintain reversible, declarative mappings

### Example Mapping (Illustrative)

```text
STATE_12  → CONTEXT_A
ALERT_03  → CONTEXT_B
PERMISSION:DENIED → CONTEXT_ACTION_BLOCKED
```

### Rules

* Contexts carry no market meaning
* Multiple contexts may be active simultaneously
* No temporal inference beyond event timestamps

### Output

```python
ContextState(
    active_contexts: set[str],
    timestamp: float
)
```

---

## 6. EP-3: ARBITRATION & RISK GATE

### Responsibility

* Act as the **sole decision choke point**
* Enforce hard veto rules
* Aggregate (future) intent proposals

### Initial Capabilities (Skeleton Only)

* If any active context == ACTION_BLOCKED → deny action
* Otherwise → allow neutral pass-through

### Determinism

* Arbitration must be deterministic
* No probabilistic resolution at this stage

### Output

```python
PolicyDecision(
    decision: "ALLOW" | "DENY" | "NO_ACTION",
    reason: str,
    timestamp: float
)
```

---

## 7. EP-4: EXECUTION STUB / SIMULATOR

### Responsibility

* Receive PolicyDecision
* Log decision and provenance
* Perform no real-world action

### Logging Requirements

Each log entry must include:

* M6 event(s) consumed
* Active contexts
* Final policy decision
* Timestamps

---

## 8. EXPLICIT EXCLUSIONS (DO NOT IMPLEMENT)

At this stage, the coding agent MUST NOT:

* Implement strategy logic (EP-2)
* Rank or score contexts
* Optimize decisions
* Use thresholds or indicators
* Persist long-term beliefs
* Interact with trading APIs

---

## 9. SUCCESS CRITERIA

The policy skeleton is considered complete when:

* M6 outputs flow end-to-end without mutation
* Context routing functions without semantics
* Arbitration enforces hard veto correctly
* System is extensible for future strategy modules

---

## 10. HANDOFF NOTE TO CODING AGENT

This skeleton is **intentionally minimal**.

Do not attempt to be helpful.
Do not anticipate strategies.
Do not add abstractions "for later".

The value of this layer is **containment and optionality**, not intelligence.

---

End of External Policy Skeleton Design v1.0
