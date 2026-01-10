"""
M5 Query Schemas - Immutable contracts for M5 Queries.
Defines the exact shape of every allowed question.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Tuple
from enum import Enum

# ==============================================================================
# BASE SCHEMA
# ==============================================================================

@dataclass(frozen=True)
class M5Query:
    """Base class for all M5 queries."""
    pass

# ==============================================================================
# ENUMS
# ==============================================================================

class M4ViewType(Enum):
    COMPOSITION = "COMPOSITION"
    DENSITY = "DENSITY"
    STABILITY = "STABILITY"
    TEMPORAL = "TEMPORAL"
    CROSS_NODE = "CROSS_NODE"

class LifecycleState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    ARCHIVED = "ARCHIVED"

# ==============================================================================
# 1. IDENTITY QUERIES
# Question: "Does node X exist, and what is its fixed state?"
# ==============================================================================

@dataclass(frozen=True)
class IdentityQuery(M5Query):
    node_id: str
    include_archived: bool = False

# ==============================================================================
# 2. LOCAL CONTEXT QUERIES
# Question: "What are the raw statistics of node X?"
# ==============================================================================

@dataclass(frozen=True)
class LocalContextQuery(M5Query):
    node_id: str
    current_ts: float
    view_type: M4ViewType

# ==============================================================================
# 3. TEMPORAL SEQUENCE QUERIES
# Question: "What specific event sequence strictly preceded T?"
# ==============================================================================

@dataclass(frozen=True)
class TemporalSequenceQuery(M5Query):
    node_id: str
    query_end_ts: float
    lookback_seconds: Optional[float] = None
    max_tokens: Optional[int] = None

# ==============================================================================
# 4. SPATIAL GROUP QUERIES
# Question: "Which nodes physically exist in Price Range [A, B]?"
# ==============================================================================

@dataclass(frozen=True)
class SpatialGroupQuery(M5Query):
    min_price: float
    max_price: float
    current_ts: float
    include_dormant: bool = False
    symbol: Optional[str] = None

# ==============================================================================
# 5. STATE DISTRIBUTION QUERIES
# Question: "How many nodes are in State S at Time T?"
# ==============================================================================

@dataclass(frozen=True)
class StateDistributionQuery(M5Query):
    query_ts: float
    states: Optional[List[LifecycleState]] = None
    symbol: Optional[str] = None

# ==============================================================================
# 6. PROXIMITY QUERIES
# Question: "What are the N nearest nodes to Price P?"
# ==============================================================================

@dataclass(frozen=True)
class ProximityQuery(M5Query):
    center_price: float
    search_radius: float
    current_ts: float
    include_dormant: bool = False
    symbol: Optional[str] = None

# ==============================================================================
# M4 TIER A STRUCTURAL PRIMITIVES (Per M5 Whitelist Spec v1.0)
# ==============================================================================

@dataclass(frozen=True)
class StructuralBoundaryViolationQuery(M5Query):
    """A1: Structural boundary violation detection."""
    node_id: str
    boundary_low: float
    boundary_high: float
    window_start_ts: float
    window_end_ts: float

@dataclass(frozen=True)
class StructuralConversionFailureQuery(M5Query):
    """A2: Structural conversion failure detection."""
    node_id: str
    observation_start_ts: float
    observation_end_ts: float
    conversion_window: float

@dataclass(frozen=True)
class PriceTraversalVelocityQuery(M5Query):
    """A3: Price traversal velocity computation."""
    node_id: str
    start_price: float
    end_price: float
    start_ts: float
    end_ts: float

@dataclass(frozen=True)
class TraversalCompactnessQuery(M5Query):
    """A4: Traversal compactness ratio."""
    node_id: str
    price_sequence: Tuple[float, ...]
    timestamp_sequence: Tuple[float, ...]

@dataclass(frozen=True)
class PriceAcceptanceRatioQuery(M5Query):
    """A5: Price acceptance ratio from OHLC."""
    node_id: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float

@dataclass(frozen=True)
class ZonePenetrationDepthQuery(M5Query):
    """A6: Zone penetration depth measurement."""
    node_id: str
    zone_low: float
    zone_high: float
    observed_low: float
    observed_high: float

@dataclass(frozen=True)
class DisplacementOriginAnchorQuery(M5Query):
    """A7: Displacement origin anchor identification."""
    node_id: str
    price_sequence: Tuple[float, ...]
    timestamp_sequence: Tuple[float, ...]

@dataclass(frozen=True)
class CentralTendencyDeviationQuery(M5Query):
    """A8: Central tendency deviation computation."""
    node_id: str
    reference_price: float
    central_price: float

# ==============================================================================
# M4 TIER B-1 STRUCTURAL ABSENCE PRIMITIVES (Per Tier B Canon v1.0)
# ==============================================================================

@dataclass(frozen=True)
class StructuralAbsenceDurationQuery(M5Query):
    """B1.1: Structural absence duration measurement."""
    node_id: str
    observation_start_ts: float
    observation_end_ts: float
    presence_intervals: Tuple[Tuple[float, float], ...]

@dataclass(frozen=True)
class TraversalVoidSpanQuery(M5Query):
    """B1.2: Traversal void span identification."""
    node_id: str
    observation_start_ts: float
    observation_end_ts: float
    traversal_timestamps: Tuple[float, ...]

@dataclass(frozen=True)
class EventNonOccurrenceCounterQuery(M5Query):
    """B1.3: Event non-occurrence counter."""
    node_id: str
    expected_event_ids: Tuple[str, ...]
    observed_event_ids: Tuple[str, ...]

# ==============================================================================
# M4 TIER B-2 PHASE 1 STRUCTURAL PERSISTENCE PRIMITIVES (Per Tier B-2 Canon v1.0)
# ==============================================================================

@dataclass(frozen=True)
class StructuralPersistenceDurationQuery(M5Query):
    """B2.1: Structural persistence duration measurement."""
    node_id: str
    observation_start_ts: float
    observation_end_ts: float
    presence_intervals: Tuple[Tuple[float, float], ...]

@dataclass(frozen=True)
class StructuralExposureCountQuery(M5Query):
    """B2.2: Structural exposure count."""
    node_id: str
    exposure_timestamps: Tuple[float, ...]
    observation_start_ts: float
    observation_end_ts: float

# ==============================================================================
# REGISTRY
# ==============================================================================

QUERY_TYPES = {
    "IDENTITY": IdentityQuery,
    "LOCAL_CONTEXT": LocalContextQuery,
    "TEMPORAL_SEQUENCE": TemporalSequenceQuery,
    "SPATIAL_GROUP": SpatialGroupQuery,
    "STATE_DISTRIBUTION": StateDistributionQuery,
    "PROXIMITY": ProximityQuery,
    # M4 Tier A Structural Primitives
    "STRUCTURAL_BOUNDARY_VIOLATION": StructuralBoundaryViolationQuery,
    "STRUCTURAL_CONVERSION_FAILURE": StructuralConversionFailureQuery,
    "PRICE_TRAVERSAL_VELOCITY": PriceTraversalVelocityQuery,
    "TRAVERSAL_COMPACTNESS": TraversalCompactnessQuery,
    "PRICE_ACCEPTANCE_RATIO": PriceAcceptanceRatioQuery,
    "ZONE_PENETRATION_DEPTH": ZonePenetrationDepthQuery,
    "DISPLACEMENT_ORIGIN_ANCHOR": DisplacementOriginAnchorQuery,
    "CENTRAL_TENDENCY_DEVIATION": CentralTendencyDeviationQuery,
    # M4 Tier B-1 Structural Absence Primitives
    "STRUCTURAL_ABSENCE_DURATION": StructuralAbsenceDurationQuery,
    "TRAVERSAL_VOID_SPAN": TraversalVoidSpanQuery,
    "EVENT_NON_OCCURRENCE_COUNTER": EventNonOccurrenceCounterQuery,
    # M4 Tier B-2 Phase 1 Structural Persistence Primitives
    "STRUCTURAL_PERSISTENCE_DURATION": StructuralPersistenceDurationQuery,
    "STRUCTURAL_EXPOSURE_COUNT": StructuralExposureCountQuery,
}
