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
from memory.m4_structural_persistence import StructuralPersistenceDuration
from memory.m4_price_distribution import PriceAcceptanceRatio, CentralTendencyDeviation
from memory.m4_orderbook import RestingSizeAtPrice, OrderConsumption, AbsorptionEvent, RefillEvent
from memory.m4_liquidation_density import LiquidationDensity
from memory.m4_directional_continuity import DirectionalContinuity
from memory.m4_trade_burst import TradeBurst

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
    price_acceptance_ratio: Optional[PriceAcceptanceRatio]

    # Tier A - Central Tendency
    central_tendency_deviation: Optional[CentralTendencyDeviation]

    # Tier B-1 - Structural Absence
    structural_absence_duration: Optional[StructuralAbsenceDuration]
    traversal_void_span: Optional[Any]  # TraversalVoidSpan (when implemented)
    event_non_occurrence_counter: Optional[Any]  # EventNonOccurrenceCounter (when implemented)

    # Tier B-2 - Structural Persistence
    structural_persistence_duration: Optional[StructuralPersistenceDuration]

    # Order Book Primitives (Phase OB)
    resting_size: Optional[RestingSizeAtPrice]
    order_consumption: Optional[OrderConsumption]
    absorption_event: Optional[AbsorptionEvent]
    refill_event: Optional[RefillEvent]

    # Additional Primitives (Phase MP/DC/TB/LD)
    liquidation_density: Optional[LiquidationDensity]
    directional_continuity: Optional[DirectionalContinuity]
    trade_burst: Optional[TradeBurst]


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
