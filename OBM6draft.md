# M6 Access Contract & Prohibition Charter

**Status:** Draft v1.0

**Scope:** This document formally defines:

1. What the M6 layer is *allowed* to ask of the memory system (via M5), and
2. What the M6 layer is *explicitly forbidden* from doing.

This document is **binding**. Any M6 design, implementation, or experiment that violates these rules invalidates the system.

---

## 1. Role Definition: What M6 Is

M6 is a **decision or policy layer** that exists **entirely outside** the memory system.

M6:

* does not observe raw market data directly,
* does not mutate memory,
* does not infer meaning inside memory,
* does not redefine primitives.

M6 consumes **descriptive outputs only**, strictly through M5.

Memory remains epistemically neutral.
Decision remains external.

---

## 2. Legal Access Boundary

M6 may access memory **only through M5**.

M6:

* cannot bypass M5,
* cannot access M1–M4 directly,
* cannot cache or accumulate memory state across queries.

Every M6 query must be:

* schema-valid,
* stateless,
* deterministic,
* independently interpretable.

---

## 3. What M6 Is Allowed to Ask

M6 may ask **only descriptive questions** of the following form:

### 3.1 Event Description Queries

Examples (abstract form):

* "What interactions occurred between time T1 and T2 relative to reference R?"
* "Which reference objects were interacted with during interval I?"
* "In what order did observable events occur within scope S?"

Allowed outputs:

* timestamps
* identifiers
* ordered lists
* counts

---

### 3.2 Temporal & Duration Queries

Examples:

* "How long did price remain within reference R during interval I?"
* "What was the duration of absence from reference R after interaction E?"

Allowed outputs:

* durations
* time deltas

---

### 3.3 Geometric Queries

Examples:

* "What was the distance between price and reference R at time T?"
* "What was the normalized position of price within span S during interval I?"

Allowed outputs:

* distances
* normalized ratios

---

### 3.4 Sequence & Ordering Queries

Examples:

* "Did event A occur before event B within scope S?"
* "What was the ordinal position of event E in sequence Q?"

Allowed outputs:

* boolean ordering results
* ordinal indices

---

### 3.5 Cross-Scale Visibility Queries

Examples:

* "Does event E exist at scale X?"
* "At which scales is interaction I observable?"

Allowed outputs:

* booleans
* scale identifiers

---

### 3.6 Reference Lifecycle Queries

Examples:

* "What is the current lifecycle state of reference R?"
* "Which references were superseded during interval I?"

Allowed outputs:

* lifecycle states
* supersession mappings

---

### 3.7 Divergence Acknowledgement Queries

Examples:

* "Has this descriptive state occurred with different outcomes historically?"

Allowed outputs:

* boolean markers
* outcome identifiers (no frequencies)

---

## 4. What M6 Is Explicitly Forbidden to Ask

M6 must **never** ask queries that:

### 4.1 Imply Prediction or Future Expectation

Forbidden forms:

* "What is likely to happen next?"
* "Will price return to R?"
* "Is this expected to break?"

---

### 4.2 Imply Evaluation, Ranking, or Importance

Forbidden forms:

* "Which level is strongest?"
* "Which zone matters most?"
* "Top / best / worst / weakest"

---

### 4.3 Collapse Descriptions into Scores or Signals

Forbidden forms:

* composite metrics
* confidence scores
* probabilities
* expectancy
* quality ratings

---

### 4.4 Encode Strategy or Action Logic

Forbidden forms:

* "Is this a buy/sell setup?"
* "Is this a valid entry?"
* "Should action X be taken?"

---

### 4.5 Introduce Semantic Labels

Forbidden labels (non-exhaustive):

* support / resistance
* breakout / fakeout
* reversal / continuation
* manipulation
* momentum strength

Renaming does not make them admissible.

---

### 4.6 Accumulate or Learn Inside Memory

Forbidden behaviors:

* caching query results
* adapting queries based on past results
* updating thresholds dynamically

M6 may learn *externally* only.

---

## 5. Determinism & Repeatability Rules

* Same query + same memory state → same output
* No system clock access
* No randomness
* No hidden state

M6 may not request:

* "current time"
* "latest" without explicit timestamp

---

## 6. Responsibility Split (Hard Boundary)

| Concern           | Layer |
| ----------------- | ----- |
| Observation       | M1–M4 |
| Description       | M4    |
| Governance        | M5    |
| Decision / Policy | M6    |

Memory never decides.
Decision never observes directly.

---

## 7. Violation Handling

If an M6 query:

* violates any prohibition above,
* implies forbidden intent,
* or attempts semantic leakage,

Then:

* M5 must reject the query
* rejection must be explicit
* no interpretation or correction is allowed

---

## 8. Final Authority Statement

This document defines the **only legal interface** between memory and decision.

Any attempt to:

* simplify these rules,
* bypass governance,
* or "make it more useful",

breaks the system by collapsing observation into strategy.

**Certified Boundary:**
M1–M5 (Observation) ⟂ M6 (Decision)

---

**End of Document**
