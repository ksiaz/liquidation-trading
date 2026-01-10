# External Arbitration & Risk Gate Design v1.0

Status: Authoritative (External System)
Scope: External Policy Layer (EP-3)
Compatibility: System v1.0 (Certified Core)
Audience: Coding Agent (Arbitration & Risk Implementation)

---

## 1. PURPOSE

This document defines the **Arbitration & Risk Gate** responsible for resolving intent proposals from external strategy modules and enforcing hard safety constraints **before any execution**.

This layer is the **sole decision choke point** in the external system.

---

## 2. POSITION IN ARCHITECTURE

```
[M6 Outputs]
   ↓
[EP-0 Adapter]
   ↓
[EP-1 Context Router]
   ↓
[EP-2 Strategy Modules]
   ↓
[EP-3 Arbitration & Risk Gate]  ← THIS DOCUMENT
   ↓
[EP-4 Execution / Simulation]
```

No module may bypass EP-3.

---

## 3. NON-NEGOTIABLE CONSTRAINTS

The Arbitration & Risk Gate:

* SHALL respect M6 `PermissionOutput(DENIED)` as an absolute veto
* SHALL be deterministic (same inputs → same outputs)
* SHALL be strategy-agnostic
* SHALL not access M1–M6 directly
* SHALL not mutate upstream data

---

## 4. INPUT CONTRACT

### 4.1 Inputs

* `ContextState` (from EP-1)
* `List[IntentProposal]` (from EP-2 modules)
* Explicit `timestamp`

### 4.2 IntentProposal (Reminder)

```python
IntentProposal(
    source: str,
    intent_type: "LONG" | "SHORT" | "FLAT" | "IGNORE",
    confidence: float,
    rationale: str | None,
    timestamp: float
)
```

---

## 5. OUTPUT CONTRACT

### Output Type: PolicyDecision

```python
PolicyDecision(
    decision: "ALLOW" | "DENY" | "NO_ACTION",
    selected_intent: IntentProposal | None,
    reason: str,
    timestamp: float
)
```

Rules:

* `ALLOW` does **not** imply execution (EP-4 decides)
* `DENY` blocks all action for the timestamp
* `NO_ACTION` indicates abstention

---

## 6. ARBITRATION PIPELINE (ORDERED)

Arbitration MUST proceed in the following strict order.

### STEP 1 — M6 VETO CHECK (HARD)

If active contexts include `CONTEXT_ACTION_BLOCKED`:

* Output: `PolicyDecision(DENY)`
* Reason: "M6_PERMISSION_DENIED"
* Skip all further processing

This rule is **absolute**.

---

### STEP 2 — SANITY & CONSISTENCY CHECKS

* Reject intents with mismatched timestamps
* Reject intents outside allowed intent set
* Deduplicate identical intents from same source

Invalid intents are discarded, not corrected.

---

### STEP 3 — CONFLICT DETECTION

Identify conflicts:

* LONG vs SHORT present simultaneously
* Non-FLAT intent + IGNORE coexistence

If conflicts detected:

* Default action: `NO_ACTION`
* Reason: "INTENT_CONFLICT"

No priority or weighting at v1.0.

---

### STEP 4 — RISK GATING (STATIC)

Risk checks are **binary and static** at v1.0.

Examples (illustrative):

* Max active positions reached → DENY
* Cooldown window active → NO_ACTION

Rules:

* No dynamic sizing
* No volatility or exposure modeling
* No probability adjustment

---

### STEP 5 — INTENT SELECTION (MINIMAL)

If exactly one non-FLAT, non-IGNORE intent remains:

* Select that intent
* Output: `ALLOW`

If only FLAT or IGNORE intents remain:

* Output: `NO_ACTION`

---

## 7. DETERMINISM REQUIREMENTS

* No random tie-breaking
* No confidence-based sorting
* No time-based decay

If resolution is ambiguous, abstain.

---

## 8. LOGGING & AUDITABILITY

Each arbitration cycle MUST log:

* Timestamp
* Active contexts
* All received IntentProposals
* Final PolicyDecision
* Rejection or abstention reason

Logs are append-only.

---

## 9. CONFIGURATION SURFACE (ALLOWED)

* Max active intents (default: 1)
* Cooldown duration (static)
* Conflict resolution policy (ABSTAIN only at v1.0)

All configuration MUST be static and versioned.

---

## 10. EXPLICIT PROHIBITIONS

The Arbitration & Risk Gate MUST NOT:

* Rank strategies by performance
* Weight intents by confidence
* Optimize expected value
* Learn from outcomes
* Inspect market data

---

## 11. TESTING REQUIREMENTS

The coding agent MUST provide tests for:

* M6 veto propagation
* Conflict abstention
* Deterministic selection
* Risk gate denial
* No-intent abstention

---

## 12. SUCCESS CRITERIA

This layer is complete when:

* All intents pass through a single choke point
* M6 veto is enforced unconditionally
* Conflicts never result in action
* The system remains strategy-agnostic

---

## 13. HANDOFF NOTE TO CODING AGENT

This layer exists to **say no more often than yes**.

Abstention is a feature, not a failure.

If you feel tempted to "pick the best" intent — stop.

That belongs to v2.0, not here.

---

End of External Arbitration & Risk Gate Design v1.0
