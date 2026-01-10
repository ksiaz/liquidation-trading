# KILL-LIST FOR TRUST RESTORATION
**Role:** Governance Agent
**Date:** 2026-01-06
**Status:** **BLOCKING LIVE RUN**

This document defines the specific, non-negotiable fixes required to restore architectural trust.
**Rule:** Any item affecting Determinism, Causality, or Governance CANNOT be deferred.

---

## CATEGORY 1: MUST FIX BEFORE ANY TRADING (The Firewall)

These items prevent the system from accepting trading logic or executing orders.

| ID | Item | Problem | Rationale |
|----|------|---------|-----------|
| **K-01** | **Physical Package Isolation** | `scripts/` mixes M1, M5, and IO. | Cannot audit what you cannot see. File separation is mandatory. |
| **K-02** | **Abolish Global SystemState** | `SystemState` is a global singleton. | Prevents parallel testing, replay, and creates hidden dependencies. |
| **K-03** | **Implement M5 Gate** | No centralized validation exists. | Without a gate, there is no governance. M5 MUST exist. |
| **K-04** | **Eradicate Internal Clocks** | `time.time()` used in logic. | Destroys determinism. Time must be injected, not sampled. |
| **K-05** | **Sever Execution Links** | `LiveGhostMonitor` imports execution. | Observation must be pure. Mixing "Doing" with "Seeing" is fatal. |
| **K-06** | **Atomic Invariant Checks** | No failure mode exists. | "Silence" looks like "Health". System must crash on violation. |

---

## CATEGORY 2: MUST FIX BEFORE UI TRUST ( The Red Screen)

These items prevent the UI from lying to the operator.

| ID | Item | Problem | Rationale |
|----|------|---------|-----------|
| **K-07** | **Liveness Monitoring** | UI stays "OK" when data stops. | "Active" counters must turn to "STALE" or "SYNCING". |
| **K-08** | **Red Screen Logic** | Native App catches all errors. | UI must explicitly hide invalid data behind an error screen. |
| **K-09** | **Refactor Collector Split** | Collector does too much (Norm+IO). | Collector should only IO. M1 should only Normalize. |

---

## CATEGORY 3: CAN BE DEFERRED (Explicitly Justified)

| ID | Item | Justification |
|----|------|---------------|
| **D-01** | **Parquet History Migration** | Can verify system on fresh data. History is nice-to-have for now. |
| **D-02** | **Advanced M4 Views** | Basic counters are sufficient for "Trust". Complex views can wait. |
| **D-03** | **OI Polling Refactor** | 5s poll is coarse but safe enough for now. |

---

## REMEDIATION ORDER (PHASE 5 EXECUTION)

The Remediation Agent will execute these in strictly sequential order to maintain system compilability.

1.  **[K-01 Structure]** Create `observation/` package skeleton.
2.  **[K-02/03 Gate]** Implement `M5` Governance Class & Types.
3.  **[K-04 Time]** Port `TradePromoter` (M3) to `observation/internal/` (No Clocks).
4.  **[K-09/01 Ingest]** Port `MarketEventLogger` logic (M1) to `observation/internal/`.
5.  **[K-06/07 Status]** Implement `ObservationStatus` & Invariants.
6.  **[K-05 Monitor]** Rewrite `LiveGhostMonitor` to use `M5` (or delete if redundant).
7.  **[K-08 UI]** Update `Native App` to use `M5` & `Red Screen`.
8.  **[Cleanup]** Delete legacy `scripts/*` files.

**STOP CONDITION:**
If at any point a new ambiguity is found, Remediation HALTS.
No "Quick Fixes".
