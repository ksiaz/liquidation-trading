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

# Tier B-6: Cascade observation primitives (from Hyperliquid)
from memory.m4_cascade_proximity import LiquidationCascadeProximity
from memory.m4_cascade_state import CascadeStateObservation
from memory.m4_leverage_concentration import LeverageConcentrationRatio
from memory.m4_open_interest_bias import OpenInterestDirectionalBias

class SystemHaltedException(Exception):
    """Critical Failure: System Invariant Broken."""
    pass

class ObservationStatus(Enum):
    UNINITIALIZED = auto()
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

    # Tier B-5 - Node Pattern Detection (from M2 memory nodes)
    order_block: Optional[Any]  # OrderBlockPrimitive
    supply_demand_zone: Optional[Any]  # SupplyDemandZonePrimitive

    # Tier B-6 - Cascade Observation (from Hyperliquid positions + liquidations)
    liquidation_cascade_proximity: Optional[LiquidationCascadeProximity]
    cascade_state: Optional[CascadeStateObservation]
    leverage_concentration_ratio: Optional[LeverageConcentrationRatio]
    open_interest_directional_bias: Optional[OpenInterestDirectionalBias]

    @classmethod
    def empty(cls, symbol: str) -> "M4PrimitiveBundle":
        """Create an empty bundle with all primitives set to None.

        Use for testing or when no primitives are available.
        None means "absence of structural fact", not failure.
        """
        return cls(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=None,
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )


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
