# PART I — ARCHITECTURAL RECOVERY PLAN
## From Untrusted Runtime → Governed Observation System

### Core Diagnosis (Restated Precisely)
You currently have:
1.  An observational system by intent
2.  A trading runtime by behavior
3.  A UI that renders incoherent hybrid state

Therefore, trust cannot be restored by incremental fixes.
It must be restored by **layer isolation + invariant enforcement + kill conditions**.

### Phase 0 — Hard Reset of Mental Model (Required)
Before touching code:
-   **Observation system (M1–M5) is sovereign**
-   Trading bot is a downstream consumer
-   UI is an M4/M5 view, not a runtime monitor
-   Any execution-style tolerance in M1–M5 is a violation

This plan enforces that reality.

### Phase 1 — Line-by-Line Audit of M1–M5 Wiring (No Changes)
**Objective:** Prove, with evidence, where observation purity is already broken.
**Output:** A written audit mapping:
-   code file → layer (M1–M5 or illegal)
-   data structures → ownership
-   clock usage → explicit or implicit
-   mutation paths → allowed vs forbidden

**Why First:** You cannot isolate or fix what you have not precisely located.

### Phase 2 — Physical Isolation of Observation Layer
**Objective:** Ensure zero execution or trading logic can mutate, time, or bypass observation state.
This means:
-   Separate modules / packages
-   Explicit interfaces
-   No shared globals
-   No callback-based mutation
-   No UI shortcuts
-   Observation becomes read-only memory, not a service.

### Phase 3 — Design & Implement Hard Failure Modes
**Objective:** Make incoherence impossible to ignore.
If any invariant breaks, the system must:
-   Refuse to render
-   Enter FAILED state
-   Expose explicit reason

**Silence ≠ failure**
**Contradiction = failure**

### Phase 4 — Kill-List Execution (Trust Restoration)
**Objective:** Define non-negotiable fixes that must be completed before:
-   any trading runtime is reattached
-   any live run is considered meaningful

# PART II — CODING-AGENT PROMPT CHAIN
Safe, Sequential, Non-Leaky Execution

## PROMPT 1 — M1–M5 Wiring Audit (READ-ONLY)
**ROLE:** Forensic Audit Agent
**TASK:** Perform a line-by-line audit of the codebase to map M1–M5 responsibilities.
**REQUIRED OUTPUT:**
1.  Table: File → Functions → Layer (M1–M5 or ILLEGAL)
2.  List of all places where implicit checks/mutations occur
3.  Explicit violations of Determinism, Stateless reads, Governance

## PROMPT 2 — Observation Layer Isolation Plan (DESIGN ONLY)
**ROLE:** System Architect Agent
**TASK:** Design a strict isolation boundary between Observation (M1–M5) and Trading.
**REQUIRED OUTPUT:**
1.  Module boundary diagram
2.  Explicit allowed interfaces
3.  Explicit forbidden access patterns

## PROMPT 3 — Hard Failure Mode Specification (DESIGN ONLY)
**ROLE:** Epistemic Safety Agent
**TASK:** Define hard failure modes for the observation system.
**REQUIRED OUTPUT:**
1.  List of invariants (formal, checkable)
2.  Failure states and triggers
3.  Display/Data requirements on failure

## PROMPT 4 — Kill-List Definition (DECISION ARTIFACT)
**ROLE:** Governance Agent
**TASK:** Produce a kill-list of fixes required before trust is restored.
**REQUIRED OUTPUT:**
-   Kill-List with Categories (Must Fix vs Defer)

## PROMPT 5 — Controlled Remediation Execution (CODE)
**ROLE:** Remediation Coding Agent
**TASK:** Implement ONLY the kill-list items, in order.
**STOP CONDITION:** If a fix introduces new ambiguity, stop immediately.

---
**FINAL ARCHITECT STATEMENT**
This plan does not try to make the system “better”.
It makes the system trustworthy or explicitly failed.
That is the only acceptable outcome under M1–M5.
