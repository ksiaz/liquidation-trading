"""
Observation System Types (Immutable)

Defines the data structures for the Memory-Centric Observation System.
These types are exposed via M5 for query results.

Amendment 2026-01-10: Added M4PrimitiveBundle per ANNEX_M4_PRIMITIVE_FLOW.md
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum, auto

# M4 Primitive imports (read-only, for bundle composition)
from memory.m4_zone_geometry import ZonePenetrationDepth, DisplacementOriginAnchor
from memory.m4_traversal_kinematics import PriceTraversalVelocity, TraversalCompactness
from memory.m4_structural_absence import StructuralAbsenceDuration

class SystemHaltedException(Exception):
    """Critical Failure: System Invariant Broken."""
    pass

class ObservationStatus(Enum):
    UNINITIALIZED = auto()
    ACTIVE = auto()
    FAILED = auto()

@dataclass(frozen=True)
class SystemCounters:
    intervals_processed: Optional[int]
    dropped_events: Optional[Dict[str, int]]


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

    Authority: ANNEX_M4_PRIMITIVE_FLOW.md
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

    # Tier B-2 - Structural Persistence
    structural_persistence_duration: Optional[Any]  # StructuralPersistenceDuration

    # Tier B-2.1 - Order Book Primitives (validation target)
    resting_size: Optional[Any]  # RestingSizeAtPrice
    order_consumption: Optional[Any]  # OrderConsumption
    absorption_event: Optional[Any]  # AbsorptionEvent
    refill_event: Optional[Any]  # RefillEvent

    # Tier B-2.2 - Price Acceptance
    price_acceptance_ratio: Optional[Any]  # PriceAcceptanceRatio

    # Tier B-3 - Liquidation Clustering
    liquidation_density: Optional[Any]  # LiquidationDensity

    # Tier B-4 - Trade Flow
    directional_continuity: Optional[Any]  # DirectionalContinuity
    trade_burst: Optional[Any]  # TradeBurst


@dataclass(frozen=True)
class ObservationSnapshot:
    """Immutable snapshot of the Observation System state.

    Contains pre-computed M4 primitives per symbol.

    Amendment 2026-01-10: Added primitives field per ANNEX_M4_PRIMITIVE_FLOW.md
    """
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[Dict[str, Any]]]
    primitives: Dict[str, M4PrimitiveBundle]  # symbol -> bundle
