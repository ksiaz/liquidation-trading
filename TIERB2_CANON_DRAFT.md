Tier B-2 Canon v1.0 — Structural Persistence & Exposure Primitives

Status: FROZEN (Canon v1.0)
Freeze Date: 2026-01-05
Implementation Status: Not Authorized (Canon Only)
Layer: M4 (Contextual Read Models)
Canon Scope: Structural persistence, exposure, recurrence
Non-Scope: Semantics, prediction, importance, optimization
Design Goal: Measure how long, how often, and how continuously structures exist — without implying meaning.

---

## Freeze Confirmation

**Scope:** Structural Persistence & Exposure (M4)  
**Status:** Canon v1.0 frozen; implementation not authorized  

**Change Control:**
- ✅ Allowed: Documentation clarifications, typo fixes, naming corrections (non-semantic)
- ❌ Prohibited: Semantic changes, added primitives, signature changes, threshold introduction

**System Impact:**
- M4: Canon expanded (no code changes)
- M5: No changes required at this stage
- M6: Predicate compatibility guaranteed (EXISTS/EQUALS/IN_CATEGORY only)
- EP-2/EP-3: No changes required

---


1. Tier B-2 Design Intent

Tier B-2 answers questions of the form:

"For how long did a structure exist?"

"How repeatedly did a structure reappear?"

"How continuously was a structure exposed?"

It does not answer:

Whether persistence is good or bad

Whether exposure implies significance

Whether recurrence implies intent or reliability

All primitives are descriptive, not evaluative.

2. Tier B-2 Admissibility Rules (Hard)

All Tier B-2 primitives MUST:

Be pure functions

Be fully deterministic

Use keyword-only arguments

Return frozen dataclasses

Operate on explicit inputs only

Contain no thresholds

Contain no trend, strength, or quality semantics

Make no forward inference

Measure only time, count, or continuity

3. Canonical Primitive Set (Tier B-2)
B2.1 — Structural Persistence Duration

Purpose
Measure total time a structure existed within an observation window.

Function Signature

def compute_structural_persistence_duration(
    *,
    observation_start_ts: float,
    observation_end_ts: float,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralPersistenceDuration


Output

@dataclass(frozen=True)
class StructuralPersistenceDuration:
    persistence_duration: float
    observation_window: float
    persistence_ratio: float


Measures

Total presence time

Fraction of window occupied

Does NOT imply

Strength

Validity

Importance

Reliability

B2.2 — Structural Exposure Count

Purpose
Count how many distinct exposure intervals occurred.

Function Signature

def compute_structural_exposure_count(
    *,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralExposureCount


Output

@dataclass(frozen=True)
class StructuralExposureCount:
    exposure_count: int


Measures

Number of times structure appeared

Does NOT imply

Frequency quality

Relevance

Opportunity

B2.3 — Structural Exposure Continuity

Purpose
Describe how fragmented or continuous exposure was.

Function Signature

def compute_structural_exposure_continuity(
    *,
    observation_start_ts: float,
    observation_end_ts: float,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralExposureContinuity


Output

@dataclass(frozen=True)
class StructuralExposureContinuity:
    longest_continuous_span: float
    exposure_spans: tuple[tuple[float, float], ...]


Measures

Longest uninterrupted exposure

Explicit exposure spans

Does NOT imply

Stability

Commitment

Dominance

B2.4 — Structural Recurrence Count

Purpose
Count how many times a structure re-emerged after absence.

Function Signature

def compute_structural_recurrence_count(
    *,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralRecurrenceCount


Output

@dataclass(frozen=True)
class StructuralRecurrenceCount:
    recurrence_count: int


Measures

Number of re-entries after gaps

Does NOT imply

Pattern strength

Reliability

Expectation

B2.5 — Structural Gap Distribution

Purpose
Describe the gaps between exposures.

Function Signature

def compute_structural_gap_distribution(
    *,
    observation_start_ts: float,
    observation_end_ts: float,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralGapDistribution


Output

@dataclass(frozen=True)
class StructuralGapDistribution:
    gap_intervals: tuple[tuple[float, float], ...]
    max_gap_duration: float


Measures

Where structure was absent between presences

Does NOT imply

Weakness

Suppression

Avoidance

4. Explicit Non-Implications (Tier-Wide)

Tier B-2 primitives must never be interpreted as:

"Strong / weak structure"

"Reliable / unreliable"

"Good / bad persistence"

"Institutional interest"

"Signal confirmation"

"Trend continuation"

All meaning is external.

5. Relationship to Other Tiers
Tier	Focus	Relationship
Tier A	Geometry & kinematics	B-2 builds temporal descriptors on top
Tier B-1	Absence	B-2 complements with presence
Tier B-2	Persistence & exposure	Neutral temporal characterization
Tier B-3 (future)	Correlation (if ever)	Must not aggregate meaning
6. M5 / M6 Compatibility (Guaranteed)

Tier B-2 outputs are compatible with:

M5: Schema-whitelisted queries

M6: Predicates via

EXISTS

EQUALS

IN_CATEGORY (on externally labeled categories)

No M5 guard extensions are required in principle.

7. Implementation Phasing Recommendation

If authorized later:

Phase B-2.1
B2.1, B2.2 (simple aggregation of intervals)

Phase B-2.2
B2.3, B2.4 (continuity & recurrence)

Phase B-2.3
B2.5 (gap distribution)

Each phase independently certifiable.

8. Canon Freeze Checklist

Before freezing Tier B-2:

Function signatures reviewed

Non-implications approved

No thresholds detected

No semantic leakage

No overlap with Tier A/B-1

No strategy assumptions

9. Canon Status Declaration (Draft)

Tier B-2 Canon v1.0 defines a complete, non-semantic vocabulary for describing structural persistence, exposure, and recurrence.
No interpretation, ranking, or prediction is admissible within this tier.
