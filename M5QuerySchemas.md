Below are the exact, implementation-ready M5 query schema definitions for M4 Tier A primitives.
They are written to drop directly into memory/m5_query_schemas.py (or equivalent), and to be consumed by existing M5 validation, guards, and normalization without semantic leakage.

M5 Query Schemas — M4 Tier A

Version: v1.0
Status: READY FOR IMPLEMENTATION
Authority: M4 Structural Primitive Canon v1.0, M5 Whitelist Spec v1.0

Global Rules (Apply to All Tier A Schemas)

All schemas are @dataclass(frozen=True)

No default sorting, ranking, filtering, or thresholds

No evaluative parameter names

Explicit timestamps required where temporal context applies

Unknown fields rejected by M5 core validation

Common Imports
from dataclasses import dataclass
from typing import Optional, Tuple

A1 — Structural Boundary Violation

Exposure Name: STRUCTURAL_BOUNDARY_VIOLATION
Query Type: LocalContextQuery

@dataclass(frozen=True)
class StructuralBoundaryViolationQuery:
    query_type: str = "STRUCTURAL_BOUNDARY_VIOLATION"

    node_id: str
    boundary_low: float
    boundary_high: float

    window_start_ts: float
    window_end_ts: float


Notes

Returns None or a single record

No comparison flags, no “break” semantics

Boundaries are geometric inputs only

A2 — Structural Conversion Failure

Exposure Name: STRUCTURAL_CONVERSION_FAILURE
Query Type: TemporalSequenceQuery

@dataclass(frozen=True)
class StructuralConversionFailureQuery:
    query_type: str = "STRUCTURAL_CONVERSION_FAILURE"

    node_id: str

    observation_start_ts: float
    observation_end_ts: float
    conversion_window: float


Notes

Detects reversion without state conversion

Does not label failure quality or intent

A3 — Price Traversal Velocity

Exposure Name: PRICE_TRAVERSAL_VELOCITY
Query Type: TemporalSequenceQuery

@dataclass(frozen=True)
class PriceTraversalVelocityQuery:
    query_type: str = "PRICE_TRAVERSAL_VELOCITY"

    node_id: str

    start_price: float
    end_price: float

    start_ts: float
    end_ts: float


Notes

Velocity is strictly (end_price - start_price) / (end_ts - start_ts)

No acceleration, no interpretation

A4 — Traversal Compactness

Exposure Name: TRAVERSAL_COMPACTNESS
Query Type: TemporalSequenceQuery

@dataclass(frozen=True)
class TraversalCompactnessQuery:
    query_type: str = "TRAVERSAL_COMPACTNESS"

    node_id: str

    price_sequence: Tuple[float, ...]
    timestamp_sequence: Tuple[float, ...]


Notes

Sequences must be equal length

M5 validates ordering and timestamp monotonicity

No “efficiency” semantics

A5 — Price Acceptance Ratio

Exposure Name: PRICE_ACCEPTANCE_RATIO
Query Type: LocalContextQuery

@dataclass(frozen=True)
class PriceAcceptanceRatioQuery:
    query_type: str = "PRICE_ACCEPTANCE_RATIO"

    node_id: str

    open_price: float
    high_price: float
    low_price: float
    close_price: float


Notes

OHLC must satisfy low ≤ open, close ≤ high

No conviction, no validation semantics

A6 — Zone Penetration Depth

Exposure Name: ZONE_PENETRATION_DEPTH
Query Type: LocalContextQuery

@dataclass(frozen=True)
class ZonePenetrationDepthQuery:
    query_type: str = "ZONE_PENETRATION_DEPTH"

    node_id: str

    zone_low: float
    zone_high: float

    observed_low: float
    observed_high: float


Notes

Returns None if no overlap

No “defense” or “failure” semantics

A7 — Displacement Origin Anchor

Exposure Name: DISPLACEMENT_ORIGIN_ANCHOR
Query Type: TemporalSequenceQuery

@dataclass(frozen=True)
class DisplacementOriginAnchorQuery:
    query_type: str = "DISPLACEMENT_ORIGIN_ANCHOR"

    node_id: str

    price_sequence: Tuple[float, ...]
    timestamp_sequence: Tuple[float, ...]


Notes

Anchor defined purely by dwell computation

No accumulation or preparation semantics

A8 — Central Tendency Deviation

Exposure Name: CENTRAL_TENDENCY_DEVIATION
Query Type: LocalContextQuery

@dataclass(frozen=True)
class CentralTendencyDeviationQuery:
    query_type: str = "CENTRAL_TENDENCY_DEVIATION"

    node_id: str

    reference_price: float
    central_price: float


Notes

Deviation is reference_price - central_price

No overextension or reversion meaning

Schema Registration (Required)

These must be added to the M5 schema registry:

QUERY_SCHEMAS = {
    "STRUCTURAL_BOUNDARY_VIOLATION": StructuralBoundaryViolationQuery,
    "STRUCTURAL_CONVERSION_FAILURE": StructuralConversionFailureQuery,
    "PRICE_TRAVERSAL_VELOCITY": PriceTraversalVelocityQuery,
    "TRAVERSAL_COMPACTNESS": TraversalCompactnessQuery,
    "PRICE_ACCEPTANCE_RATIO": PriceAcceptanceRatioQuery,
    "ZONE_PENETRATION_DEPTH": ZonePenetrationDepthQuery,
    "DISPLACEMENT_ORIGIN_ANCHOR": DisplacementOriginAnchorQuery,
    "CENTRAL_TENDENCY_DEVIATION": CentralTendencyDeviationQuery,
}

Explicit Non-Features (Certification-Critical)

These schemas do not include:

min_*, max_*, threshold, tolerance

rank, score, best, worst

direction, strength, trend

Optional boolean flags

Any attempt to add these is a Type-2 certification violation.

Ready State

These schemas are:

Canon-compliant

Guard-compatible

Deterministic

Strategy-agnostic

Safe to expose via M5 immediately