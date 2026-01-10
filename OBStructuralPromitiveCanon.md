# M4 Structural Primitive Canon v1.0

**Status:** AUTHORITATIVE CANON

**Authority:** System Certification v1.0

**Scope:** Memory Layer M4 (Descriptive Read Models)

**Purpose:**
This document canonizes **all structurally admissible descriptive primitives** extracted from research to guarantee expressive completeness **without strategy, evaluation, prediction, or intent**. Primitives are **declared exhaustively**, then **tiered** to separate conceptual admissibility from implementation order.

---

## Canon Rules (Non‑Negotiable)

All primitives in this canon:

* Are **descriptive only** (what happened, where, when, how much)
* Are **deterministic** (same inputs → same outputs)
* Are **stateless** (no accumulation across queries)
* Contain **explicit non‑implications**
* Are **permanently admissible** once declared

**Declaration ≠ Implementation.**

---

## Tier Definitions

### Tier A — Mandatory Structural Primitives

Without these, the system cannot describe core observed structure.

### Tier B — Enriching Descriptive Primitives

Expand expressive completeness; safe but not required for minimal operation.

### Tier C — Deferred / Meta Primitives

Valid but high governance or compositional cost. Declared only.

---

# TIER A — MANDATORY STRUCTURAL PRIMITIVES

## A1. structural_boundary_violation

**Describes:** A price traversal exceeding a previously established structural boundary.

**Derived From:** M2 node boundaries + M3 traversal events

**Fields:**

* boundary_id
* violation_depth (price delta)
* violation_duration (time)

**Cannot Imply:** reversal, deception, liquidity intent

---

## A2. structural_conversion_failure

**Describes:** A boundary violation that does not result in a new structural state.

**Fields:**

* boundary_id
* reversion_time

**Cannot Imply:** falseness, weakness, trapping

---

## A3. price_traversal_velocity

**Describes:** Rate of price change over time.

**Fields:**

* price_delta
* time_delta

**Units:** price / time

**Cannot Imply:** strength, momentum, direction

---

## A4. traversal_compactness

**Describes:** Ratio of directional movement to total oscillation during traversal.

**Fields:**

* net_displacement
* total_path_length

**Cannot Imply:** quality, efficiency

---

## A5. price_acceptance_ratio

**Describes:** Portion of traded range retained vs rejected (wick/body relationship).

**Fields:**

* accepted_range
* rejected_range

**Cannot Imply:** acceptance quality, conviction

---

## A6. zone_penetration_depth

**Describes:** Maximum depth price enters a defined zone.

**Fields:**

* zone_id
* penetration_depth

**Cannot Imply:** validity, failure, strength

---

## A7. displacement_origin_anchor

**Describes:** Price region immediately preceding a large directional traversal.

**Fields:**

* anchor_range
* anchor_dwell_time

**Cannot Imply:** institutional activity, future reaction

---

## A8. central_tendency_deviation

**Describes:** Distance from rolling central price tendency.

**Fields:**

* deviation_value

**Cannot Imply:** overextension, reversion likelihood

---

# TIER B — ENRICHING DESCRIPTIVE PRIMITIVES

## B1. post_violation_retraction_latency

**Describes:** Time between boundary violation and re‑entry into prior envelope.

**Fields:**

* latency

**Cannot Imply:** fake break, trap

---

## B2. violation_followthrough_absence

**Describes:** Absence of continued traversal after violation.

**Fields:**

* followthrough_event_count

**Cannot Imply:** weakness, failure

---

## B3. retracement_asymmetry

**Describes:** Speed and depth of retracement relative to prior traversal.

**Fields:**

* retracement_speed
* retracement_depth

**Cannot Imply:** healthy / unhealthy structure

---

## B4. zone_revisit_persistence

**Describes:** Frequency and duration of revisits to a zone.

**Fields:**

* revisit_count
* total_dwell_time

**Cannot Imply:** exhaustion, weakening

---

## B5. confirmation_latency

**Describes:** Time between structural event and subsequent confirming event.

**Fields:**

* latency

**Cannot Imply:** correctness, entry quality

---

## B6. structural_event_prematurity

**Describes:** Structural event occurring prior to higher‑order confirmation.

**Fields:**

* offset_from_parent_confirmation

**Cannot Imply:** error, mistake

---

## B7. structural_nesting_depth

**Describes:** Number of higher‑order structures containing the current node.

**Fields:**

* nesting_level

**Cannot Imply:** bias, dominance

---

## B8. cross_horizon_alignment

**Describes:** Relative orientation of structures across time horizons.

**Fields:**

* horizon_ids
* alignment_measure

**Cannot Imply:** trend direction

---

## B9. deviation_duration

**Describes:** Time spent away from central tendency.

**Fields:**

* duration

**Cannot Imply:** imbalance, correction

---

# TIER C — DEFERRED / META PRIMITIVES (DECLARED ONLY)

## C1. multi_boundary_violation_sequence

**Describes:** Ordered set of boundary violations within a window.

**Risk:** Combinatorial query surface

---

## C2. cross_zone_interaction_matrix

**Describes:** Interaction density between multiple zones.

**Risk:** Implicit importance inference

---

## C3. higher_order_traversal_pattern

**Describes:** Patterning across multiple traversal primitives.

**Risk:** Latent semantic emergence

---

# Implementation Status

* **Declared:** All primitives in this canon
* **Implemented:** None (pending M4.x extension cycle)
* **Governance:** M5 MUST explicitly whitelist any implemented primitive

---

# Canon Freeze Statement

This canon defines the **complete expressive vocabulary** for structural market observation under System v1.0.

No primitive may be removed.

New primitives require a **new canon version**.

---

**End of M4 Structural Primitive Canon v1.0**
