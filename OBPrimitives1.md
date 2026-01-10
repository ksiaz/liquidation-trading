# Candidate Primitive Admissibility Ledger — Pre-M6

**Status:** Draft v0.1 (Admissibility-First)

**Scope:** This ledger enumerates *candidate descriptive primitives* required to fully express all observed market phenomena documented in the Research Notes. Each primitive is defined **without semantics, prediction, ranking, or intent**.

**Rule of Inclusion:** A primitive is admissible **only if** it:

* describes something that *occurred or did not occur*,
* is measurable or enumerable,
* is deterministic and stateless,
* does not imply importance, direction, quality, or action.

Each primitive includes an explicit **Non-Implications** section to prevent semantic leakage.

---

## P1 — Reference Object

**What it Describes**
A reference object is any price-anchored or time-varying object against which price interaction can be described.

**Formal Description**
A reference object is defined by:

* reference_id
* reference_type ∈ {static_price, bounded_region, rolling_reference}
* definition_parameters (price, price_range, window_length, formula)
* creation_timestamp
* supersession_state ∈ {active, superseded}

**Why It Is Needed**
All research reduces to price interacting with *something*. This primitive unifies extrema, zones, EMAs, ranges, and regions under a single neutral abstraction.

**Layer Placement**
M2 (identity & lifecycle), M4 (read models)

**Non-Implications**
This primitive does **not** imply:

* support or resistance
* indicator significance
* trader attention
* future relevance

---

## P2 — Interaction Event

**What it Describes**
A single instance of price interacting with a reference object.

**Formal Description**
An interaction event records:

* reference_id
* interaction_type ∈ {touch, overlap, traverse}
* interaction_start_timestamp
* interaction_end_timestamp
* min_price, max_price during interaction

**Why It Is Needed**
Every concept (orderblock, liquidity, rejection, respect) decomposes into *how* price interacted with a reference.

**Layer Placement**
M3 (temporal ordering), M4 (composition views)

**Non-Implications**
This primitive does **not** imply:

* acceptance or rejection
* success or failure
* strength or weakness

---

## P3 — Absence Interval

**What it Describes**
A contiguous interval where price did *not* interact with a reference or price span.

**Formal Description**
An absence interval records:

* absence_target (reference_id or price_span)
* absence_start_timestamp
* absence_end_timestamp
* duration

**Why It Is Needed**
Gaps, imbalances, voids, and momentum all rely on *absence*, not presence.

**Layer Placement**
M3, M4

**Non-Implications**
This primitive does **not** imply:

* inefficiency
* inevitability of return
* expectation of fill

---

## P4 — Sequence Position

**What it Describes**
The ordered position of an event within a local or bounded sequence.

**Formal Description**
Sequence position records:

* sequence_id
* event_id
* ordinal_index
* sequence_scope (time_window, reference_id)

**Why It Is Needed**
Inducement, confirmation, and failures are sequence-dependent, not state-dependent.

**Layer Placement**
M3

**Non-Implications**
This primitive does **not** imply:

* causality
* correctness
* necessity

---

## P5 — Duration Metric

**What it Describes**
How long a state or interaction persisted.

**Formal Description**
Duration metrics apply to:

* interaction events
* absence intervals
* reference lifecycle states

Recorded as:

* start_timestamp
* end_timestamp
* duration

**Why It Is Needed**
Duration replaces all folk notions of “strength” or “conviction”.

**Layer Placement**
M4

**Non-Implications**
This primitive does **not** imply:

* importance
* dominance
* reliability

---

## P6 — Geometry Descriptor

**What it Describes**
Relative spatial relationships between price and references.

**Formal Description**
Geometry descriptors include:

* distance_to_reference
* position_relative_to_leg ∈ [0,1]
* depth_of_traversal
* width_of_region

**Why It Is Needed**
Extreme zones, premium/discount, and location bias all reduce to geometry.

**Layer Placement**
M4

**Non-Implications**
This primitive does **not** imply:

* better or worse location
* trade desirability

---

## P7 — Interval Finality State

**What it Describes**
Whether an interaction was provisional intra-interval or finalized at interval close.

**Formal Description**
Finality state records:

* interval_id
* reference_id
* intra_interval_excursion ∈ {true,false}
* interval_close_side ∈ {above, within, below}

**Why It Is Needed**
Wick vs close, confirmation, and false breaks are all finality distinctions.

**Layer Placement**
M3, M4

**Non-Implications**
This primitive does **not** imply:

* confirmation
* rejection
* validity

---

## P8 — Cross-Scale Visibility

**What it Describes**
Whether the same event exists at multiple aggregation scales.

**Formal Description**
Cross-scale visibility records:

* event_id
* scale
* exists ∈ {true,false}

**Why It Is Needed**
Timeframe conflict is observational, not interpretive.

**Layer Placement**
M4

**Non-Implications**
This primitive does **not** imply:

* scale superiority
* confirmation hierarchy

---

## P9 — Visit Count & Degradation

**What it Describes**
How interaction characteristics change across repeated visits.

**Formal Description**
Visit tracking records:

* reference_id
* visit_index
* dwell_time
* traversal_ratio

**Why It Is Needed**
Zone “weakening” is actually visit-indexed geometry change.

**Layer Placement**
M2, M4

**Non-Implications**
This primitive does **not** imply:

* loss of effectiveness
* future break

---

## P10 — Extremum Lineage

**What it Describes**
How extrema are superseded over time.

**Formal Description**
Extremum lineage records:

* extremum_id
* superseded_by
* supersession_timestamp

**Why It Is Needed**
Reversals are extremum lineage changes, not signals.

**Layer Placement**
M2

**Non-Implications**
This primitive does **not** imply:

* trend change
* direction

---

## P11 — Evidence Supersession

**What it Describes**
Later observations that override provisional ones.

**Formal Description**
Evidence supersession records:

* superseded_event_id
* superseding_event_id
* timestamp

**Why It Is Needed**
Prevents hindsight rewriting and preserves epistemic safety.

**Layer Placement**
M5

**Non-Implications**
This primitive does **not** imply:

* correctness
* error

---

## P12 — Outcome Divergence Marker

**What it Describes**
Explicit marking that identical descriptive states led to different outcomes.

**Formal Description**
Outcome divergence records:

* state_fingerprint
* outcome_id

**Why It Is Needed**
Guarantees the system never collapses to probability or expectation.

**Layer Placement**
M5

**Non-Implications**
This primitive does **not** imply:

* randomness explanation
* statistical meaning

---

**End of Draft**

Next step (explicit instruction required):

* refine, reject, or split individual primitives
* verify full coverage against Research Notes
* lock admissible set before M6 design
