# ANNEX: M4 Primitive Flow Architecture

**Status:** Constitutional Amendment
**Authority:** Architectural Ruling 2026-01-10
**Governed By:** EPISTEMIC_CONSTITUTION.md, SYSTEM_CANON.md, CODE_FREEZE.md
**Effect:** Permanent
**Supersedes:** Phase 2 stub implementation assumptions

---

## PURPOSE

This annex resolves an architectural ambiguity discovered during Phase 3 implementation regarding how M4 structural primitives flow from observation (M1-M5) to execution (M6).

**The Problem:**
- External policies (EP2) require actual M4 primitive dataclass instances as inputs
- ObservationSnapshot did not include M4 primitives
- PolicyAdapter (M6) cannot query M5 dynamically per constitutional prohibition
- No compliant data path existed for primitives to reach external policies

**The Resolution:**
- M5 computes M4 primitives exactly once per snapshot
- ObservationSnapshot carries pre-computed primitives
- M6 reads primitives from snapshot (no dynamic queries)

---

## ARCHITECTURAL DECISION

### Decision Statement

**PolicyAdapter is part of M6.**

**M6 must never query M5, directly or indirectly.**

**M4 primitives must be computed by M5 exactly once per snapshot.**

**ObservationSnapshot is the sole carrier of M4 primitives.**

**M4 primitives are immutable, descriptive, and non-interpretive.**

**CODE_FREEZE is amended narrowly to allow adding primitives to ObservationSnapshot only.**

**No alternative primitive channels are permitted.**

---

## WHY THIS IS CONSTITUTIONALLY SOUND

### 1. M4 Primitives Are Not Interpretation

M4 primitives are:
- Descriptive (record structural facts)
- Deterministic (same inputs → same outputs)
- Non-evaluative (no "good/bad", "strong/weak", "ready/valid")
- Inputs to policy logic, not outputs to humans

They are **allowed internal epistemic products** per architect ruling:
> "Internal semantics are allowed; exported semantics are forbidden"

### 2. Snapshot Sealing Enforces Epistemic Finality

Computing primitives at snapshot creation time ensures:
- **Atomicity:** All primitives computed from same observation state
- **Immutability:** No re-computation or dynamic probing by M6
- **Auditability:** Single computation point, traceable
- **Determinism:** Identical snapshot → identical primitives

### 3. No M6 → M5 Query Channel

After snapshot is sealed:
- M6 reads primitives from snapshot
- M6 never queries M5
- M6 never computes primitives
- M6 never interprets primitive presence/absence

This maintains constitutional separation.

---

## PROHIBITION CLARIFICATION

### What "M6 Must Not Requery M5 Dynamically" Means

**Forbidden:**
- ❌ M6 calling M5 query methods
- ❌ M6 calling MemoryAccess.execute_query()
- ❌ M6 importing M5 access layer
- ❌ M6 computing M4 primitives from observation state
- ❌ M6 probing observation for additional data after snapshot

**Allowed:**
- ✅ M6 reading pre-computed primitives from ObservationSnapshot
- ✅ M6 passing primitives to external policies
- ✅ M6 handling None primitives gracefully

### Intent of Prohibition

The prohibition exists to enforce **epistemic finality**:
- Prevent execution from shaping observation queries
- Prevent hidden coupling between M6 and M5
- Prevent "just one more query" erosion
- Maintain single source of truth

**Pre-computing primitives at snapshot time satisfies this intent.**

---

## IMPLEMENTATION SPECIFICATION

### 1. New Types (observation/types.py)

```python
from dataclasses import dataclass
from typing import Optional, Dict
from memory.m4_zone_geometry import ZonePenetrationDepth, DisplacementOriginAnchor
from memory.m4_traversal_kinematics import PriceTraversalVelocity, TraversalCompactness
from memory.m4_structural_absence import StructuralAbsenceDuration

@dataclass(frozen=True)
class M4PrimitiveBundle:
    """Pre-computed M4 primitives for a single symbol.

    Computed once by M5 at snapshot creation.
    Immutable after construction.

    Fields may be None if primitive computation:
    - Required unavailable data
    - Detected no structural condition
    - Failed validation checks

    None means "absence of structural fact", not "failure".
    """
    symbol: str

    # Tier A - Zone Geometry
    zone_penetration: Optional[ZonePenetrationDepth]
    displacement_origin_anchor: Optional[DisplacementOriginAnchor]

    # Tier A - Traversal Kinematics
    price_traversal_velocity: Optional[PriceTraversalVelocity]
    traversal_compactness: Optional[TraversalCompactness]

    # Tier A - Central Tendency (when implemented)
    central_tendency_deviation: Optional[Any]  # CentralTendencyDeviation

    # Tier B-1 - Structural Absence
    structural_absence_duration: Optional[StructuralAbsenceDuration]
    traversal_void_span: Optional[Any]  # TraversalVoidSpan (when implemented)
    event_non_occurrence_counter: Optional[Any]  # EventNonOccurrenceCounter (when implemented)
```

### 2. Updated ObservationSnapshot

```python
@dataclass(frozen=True)
class ObservationSnapshot:
    """Immutable snapshot of the Observation System state.

    Contains pre-computed M4 primitives per symbol.
    """
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[Dict[str, Any]]]

    # NEW: Pre-computed M4 primitives
    primitives: Dict[str, M4PrimitiveBundle]  # symbol -> bundle
```

### 3. Snapshot Creation (observation/governance.py)

```python
def _get_snapshot(self) -> ObservationSnapshot:
    """Construct public snapshot from internal states.

    Computes M4 primitives exactly once via M5.
    """
    # Compute primitives for all active symbols
    primitives = {}
    for symbol in self._allowed_symbols:
        primitives[symbol] = self._compute_primitives_for_symbol(symbol)

    return ObservationSnapshot(
        status=self._status,
        timestamp=self._system_time,
        symbols_active=sorted(self._allowed_symbols),
        counters=SystemCounters(
            intervals_processed=None,
            dropped_events=None
        ),
        promoted_events=None,
        primitives=primitives  # NEW
    )

def _compute_primitives_for_symbol(self, symbol: str) -> M4PrimitiveBundle:
    """Compute M4 primitives for a single symbol.

    This is the ONLY place M4 primitives are computed.
    Called exactly once per symbol per snapshot.
    """
    # Query M5 for primitives
    # Implementation delegated to M5 access layer
    # Returns M4PrimitiveBundle with fields set to None if unavailable
    pass  # Implementation in next phase
```

### 4. PolicyAdapter Update (runtime/policy_adapter.py)

```python
def _extract_primitives(
    self,
    observation_snapshot: ObservationSnapshot,
    symbol: str
) -> Dict[str, Any]:
    """Extract M4 primitives from observation snapshot.

    Reads pre-computed primitives - does NOT query M5.

    Args:
        observation_snapshot: Snapshot with pre-computed primitives
        symbol: Symbol to extract primitives for

    Returns:
        Dictionary of primitive name -> primitive object
    """
    # Get pre-computed bundle for symbol
    bundle = observation_snapshot.primitives.get(symbol)

    if bundle is None:
        # Symbol not in snapshot (should not happen if symbol in symbols_active)
        return {
            "zone_penetration": None,
            "traversal_compactness": None,
            "central_tendency_deviation": None,
            "price_traversal_velocity": None,
            "displacement_origin_anchor": None,
            "structural_absence_duration": None,
            "traversal_void_span": None,
            "event_non_occurrence_counter": None,
        }

    # Extract primitives from bundle (read-only access)
    return {
        "zone_penetration": bundle.zone_penetration,
        "traversal_compactness": bundle.traversal_compactness,
        "central_tendency_deviation": bundle.central_tendency_deviation,
        "price_traversal_velocity": bundle.price_traversal_velocity,
        "displacement_origin_anchor": bundle.displacement_origin_anchor,
        "structural_absence_duration": bundle.structural_absence_duration,
        "traversal_void_span": bundle.traversal_void_span,
        "event_non_occurrence_counter": bundle.event_non_occurrence_counter,
    }
```

---

## CI ENFORCEMENT

### New Rule: M6 Must Not Import M5

Add to `.github/scripts/import_validator.py`:

```python
# M6 → M5 import prohibition
M6_M5_VIOLATIONS = [
    ("runtime/", "memory.m5_access"),
    ("runtime/", "memory.m5_query_schemas"),
    ("runtime/", "memory.m5_"),
]

# Error message
ERR_M6_M5 = "M6 (runtime/) must not import M5 (memory/m5_*). Primitives flow via ObservationSnapshot only."
```

---

## WHICH PRIMITIVES ARE INCLUDED

**Inclusion Criteria:**
- Only primitives required by frozen EP2 external policies
- No speculative additions
- No composite scores
- No derived rankings

**Required Primitives (from EP2 contracts):**

**EP2 Geometry Strategy:**
- zone_penetration (A6: ZonePenetrationDepth)
- traversal_compactness (A4: TraversalCompactness)
- central_tendency_deviation (A8: CentralTendencyDeviation)

**EP2 Kinematics Strategy:**
- price_traversal_velocity (A3: PriceTraversalVelocity)
- traversal_compactness (A4: TraversalCompactness)
- displacement_origin_anchor (A7: DisplacementOriginAnchor)

**EP2 Absence Strategy:**
- structural_absence_duration (B1.1: StructuralAbsenceDuration)
- traversal_void_span (B1.2: TraversalVoidSpan)
- event_non_occurrence_counter (B1.3: EventNonOccurrenceCounter)

**No other primitives are included in v1.0.**

---

## CODE FREEZE AMENDMENT

### Narrow Exemption

CODE_FREEZE.md is amended to allow **only**:

1. Adding `M4PrimitiveBundle` dataclass to `observation/types.py`
2. Adding `primitives: Dict[str, M4PrimitiveBundle]` field to `ObservationSnapshot`
3. Implementing `_compute_primitives_for_symbol()` in `observation/governance.py`
4. No other modifications to frozen observation layer

### Justification

This is **not a functional change** to observation logic.

This is **exposing existing internal computation** through the snapshot interface.

M4 primitives already exist internally.

This amendment makes them **externally readable** in a sealed, immutable form.

### Review Requirement

All changes to observation layer must:
- ✅ Be documented in this annex
- ✅ Pass semantic leak scanner
- ✅ Pass import validator (no new M6 → M5 imports)
- ✅ Be reviewed against EPISTEMIC_CONSTITUTION.md

---

## ALTERNATIVE APPROACHES REJECTED

### Option A: Modify ObservationSnapshot Without Specifying Computation

**Rejected because:** Incomplete specification creates ambiguity about who computes primitives and when.

### Option C: Allow PolicyAdapter to Query M5 "Once Per Cycle"

**Rejected because:** Violates constitutional prohibition. Intent is to prevent **any** M6 → M5 query channel, regardless of frequency.

### Option D: Parallel Primitive Store

**Rejected because:** Creates shadow observation system, violates single source of truth, introduces synchronization problems and temporal drift.

---

## WHY THIS AMBIGUITY AROSE

This was not a design mistake.

This was **architectural maturation**.

**Chronology:**
1. M1-M5 observation layer was correctly separated from execution
2. M4 primitives were correctly defined as structural, non-interpretive
3. External policies were correctly frozen with M4 primitive contracts
4. PolicyAdapter was correctly designed as pure wiring layer
5. **But:** Data path for primitives M5 → M6 was underspecified

**Resolution Point:**
- M4 primitives sit conceptually between observation and policy
- Constitution treats M4 as "internal computation"
- But external policies must consume M4
- **Question:** Where do M4 primitives become externally visible without interpretation?
- **Answer:** At snapshot sealing time (exactly once, immutable)

This is a **clean, principled resolution** that maintains all constitutional guarantees.

---

## GOVERNANCE TRACEABILITY

```
EPISTEMIC_CONSTITUTION.md (Observation exposure rules)
    ↓
SYSTEM_CANON.md (Layer separation, M6 prohibition)
    ↓
CODE_FREEZE.md (Frozen component rules)
    ↓
OBM6MandateTemplate.md (M6 must not requery M5)
    ↓
Architectural Ruling 2026-01-10 (M4 flow via snapshot)
    ↓
ANNEX_M4_PRIMITIVE_FLOW.md (This document)
    ↓
observation/types.py (M4PrimitiveBundle + snapshot field)
    ↓
runtime/policy_adapter.py (Read primitives from snapshot)
```

All decisions trace to constitutional authority.

---

## VERIFICATION REQUIREMENTS

### Before Deployment

1. ✅ All tests pass with new snapshot structure
2. ✅ Semantic leak scanner: 0 violations
3. ✅ Import validator: No M6 → M5 imports
4. ✅ External policies receive actual M4 primitive instances
5. ✅ PolicyAdapter never imports M5 modules
6. ✅ End-to-end mandate generation verified

### Runtime Invariants

1. M4 primitives computed exactly once per snapshot
2. Primitives immutable after snapshot construction
3. M6 never queries M5 directly
4. No parallel primitive computation channels

---

## SUMMARY

**Problem:** M4 primitives had no constitutional data path from M5 to M6.

**Solution:** Pre-compute primitives at snapshot sealing time.

**Constitutional Status:** ✅ Compliant with all epistemic guarantees.

**Implementation:** Narrow amendment to ObservationSnapshot schema only.

**Effect:** Permanent. M4 primitives flow via snapshot, never via dynamic query.

---

**Status:** ✅ Architectural Ambiguity Resolved
**Ready For:** Phase 3 Implementation
**Authority:** Architect Ruling 2026-01-10

---

END OF ANNEX
