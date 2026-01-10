# EPISTEMIC CONSTITUTION OF THE OBSERVATION SYSTEM

**Status:** Constitutional  
**Authority:** Absolute  
**Scope:** All observation layers (M1-M5)  
**Effect:** Permanent

---

## ARTICLE I: SOLE PURPOSE

The system exists to record external facts and enforce invariants.

---

## ARTICLE II: EXPLICIT NEGATIONS

The system is NOT:
- A health monitor
- A readiness indicator
- A quality assessor
- A liveness detector
- A data flow validator
- A timing oracle
- A confidence estimator
- A condition evaluator

---

## ARTICLE III: EPISTEMIC CEILING

The system may never claim:
- Health
- Readiness
- Data flow
- Activity level
- Correctness
- Liveness
- Freshness
- Quality
- Completeness
- Timeliness
- Normalcy
- Significance
- Causation
- Prediction
- Performance

---

## ARTICLE IV: SILENCE RULE

The system must say nothing when:
- It cannot prove the statement from its own observable state
- The statement depends on external conditions not directly measured
- The statement depends on temporal assumptions
- The statement depends on unvalidated internal conditions
- The statement implies correctness without proof

---

## ARTICLE V: FAILURE RULE

The system must halt when:
- Time moves backward
- Internal processing raises unhandled exception
- Any invariant is violated

The system must never:
- Auto-recover from FAILED state
- Suppress invariant violations
- Continue operation after halt condition

---

## ARTICLE VI: EXPOSURE RULE

The system may expose externally:
- Status (UNINITIALIZED or FAILED only)
- Timestamp (last advance_time parameter only)
- Symbol whitelist (configured set only)

The system must never expose:
- Counters (all context-dependent)
- Rates (all unimplemented or unknowable)
- Health metrics (all unvalidable)
- Baseline status (warmth not tracked)
- Processing indicators (activity not provable)
- Event lists (meaningfulness unvalidated)

---

## ARTICLE VII: M6 RULE

M6 may consume internally:
- Any observation state for decision-making

M6 may expose externally:
- Execution actions taken
- Execution state changes
- Execution failures

M6 must never expose externally:
- Observation interpretations
- Observation quality assessments
- Observation-derived confidence

---

## ARTICLE VIII: REMOVAL INVARIANT

If a field's truthfulness depends on any condition not directly observable in the field's own value, that field must be immediately removed from external exposure.

---

## ARTICLE IX: AMENDMENT PROHIBITION

This constitution may not be weakened.

Additions to the Epistemic Ceiling are prohibited.

Exceptions to the Silence Rule are prohibited.

Relaxations of the Failure Rule are prohibited.

Expansions of the Exposure Rule require proof that the new field satisfies Article VIII.

---

## ARTICLE X: ENFORCEMENT

Any code that violates this constitution is epistemically illegal.

Any status assertion beyond UNINITIALIZED or FAILED is epistemically illegal.

Any claim of health, readiness, or liveness is epistemically illegal.

Epistemic illegality voids system trustworthiness.

---

**END OF CONSTITUTION**

This document supersedes all implementation decisions, design preferences, and operational convenience arguments.

Silence is mandatory when truth cannot be proven.
