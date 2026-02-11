"""
M5 Memory Access - The Firewall Facade.
The ONLY allowed entry point for the Strategy Layer to access Memory.
Enforces the Governance Pipeline: Schema -> Guards -> Execution -> Normalization.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Union, Type

logger = logging.getLogger(__name__)
from memory.m5_query_schemas import (
    M5Query,
    IdentityQuery,
    LocalContextQuery,
    TemporalSequenceQuery,
    SpatialGroupQuery,
    StateDistributionQuery,
    ProximityQuery,
    # M4 Tier A Structural Primitives
    StructuralBoundaryViolationQuery,
    StructuralConversionFailureQuery,
    PriceTraversalVelocityQuery,
    TraversalCompactnessQuery,
    PriceAcceptanceRatioQuery,
    ZonePenetrationDepthQuery,
    DisplacementOriginAnchorQuery,
    CentralTendencyDeviationQuery,
    # M4 Tier B-1 Structural Absence Primitives
    StructuralAbsenceDurationQuery,
    TraversalVoidSpanQuery,
    EventNonOccurrenceCounterQuery,
    # M4 Tier B-2 Phase 1 Structural Persistence Primitives
    StructuralPersistenceDurationQuery,
    StructuralExposureCountQuery,
    QUERY_TYPES,
    M4ViewType,
    LifecycleState
)
from dataclasses import asdict
from memory.m5_selection_guards import run_guards, inject_neutral_defaults, EpistemicSafetyError, DeterminismError
from memory.m5_normalization import normalize_output
from memory.m2_continuity_store import ContinuityMemoryStore
from memory.m5_constants import ERR_SCHEMA

# M4 Tier A Structural Primitive Imports
from memory.m4_structural_boundaries import (
    detect_structural_boundary_violation,
    detect_structural_conversion_failure
)
from memory.m4_traversal_kinematics import (
    compute_price_traversal_velocity,
    compute_traversal_compactness
)
from memory.m4_zone_geometry import (
    compute_zone_penetration_depth,
    identify_displacement_origin_anchor
)
from memory.m4_price_distribution import (
    compute_price_acceptance_ratio,
    compute_central_tendency_deviation
)

# M4 Tier B-1 Structural Absence Primitive Imports
from memory.m4_structural_absence import compute_structural_absence_duration
from memory.m4_traversal_voids import compute_traversal_void_span
from memory.m4_event_absence import compute_event_non_occurrence_counter

# M4 Tier B-2 Phase 1 Structural Persistence Primitive Imports
from memory.m4_structural_persistence import compute_structural_persistence_duration
from memory.m4_structural_exposure import compute_structural_exposure_count

class AccessDeniedError(Exception):
    """Raised when an unknown or disallowed query type is requested."""
    pass

class SchemaValidationError(Exception):
    """Raised when input params do not match the required schema."""
    pass

class MemoryAccess:
    """
    Stateless Facade for Memory Access.
    
    Architecture:
    1. Input: Raw Dict + Query Type Name
    2. Guard: Check for forbidden params/values (on raw dict)
    3. Schema: Validates & Instantiates M5Query object (Enforces Types)
    4. Execution: Dispatches to ContinuityMemoryStore (Read-Only)
    5. Normalization: Cleans output
    
    This class has NO state. It holds a reference to the store only to execute.
    """
    __slots__ = ('_store',)
    
    def __init__(self, store: ContinuityMemoryStore):
        self._store = store

    def _convert_enums(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert string inputs to Enums where expected.
        This enables strict Schema Validation.
        """
        converted = params.copy()
        
        # M4ViewType
        if "view_type" in converted:
            val = converted["view_type"]
            if isinstance(val, str):
                try:
                    converted["view_type"] = M4ViewType[val]
                except KeyError:
                    raise SchemaValidationError(f"Invalid view_type: {val}. Options: {[e.name for e in M4ViewType]}")
        
        # LifecycleState (List or Single)
        if "states" in converted:
             val = converted["states"]
             if isinstance(val, list):
                 new_list = []
                 for item in val:
                     if isinstance(item, str):
                         try:
                             new_list.append(LifecycleState[item])
                         except KeyError:
                             raise SchemaValidationError(f"Invalid state: {item}. Options: {[e.name for e in LifecycleState]}")
                     else:
                         new_list.append(item)
                 converted["states"] = new_list
        
        return converted

    def _validate_and_build_query(self, query_type: str, params: Dict[str, Any]) -> M5Query:
        """
        Pipeline Steps 1-3: Guard, Defaults, Schema.
        """
        # Step 1: Run Guards on Raw Input
        run_guards(params)
        
        # Step 2: Inject Neutral Defaults
        defaulted_params = inject_neutral_defaults(params)
        
        # Step 3: Resolve Schema Class
        if query_type not in QUERY_TYPES:
            raise AccessDeniedError(f"Query Type '{query_type}' is not permitted.")
        
        schema_cls = QUERY_TYPES[query_type]
        
        # Step 4: Filter params to Schema Fields
        valid_fields = schema_cls.__dataclass_fields__.keys()
        filtered_params = {k: v for k, v in defaulted_params.items() if k in valid_fields}
        
        # Step 5: Convert Enums
        typed_params = self._convert_enums(filtered_params)
        
        # Step 6: Strict Type Enforcement (Primitives)
        # Standard Dataclasses don't enforce types at runtime. We must.
        self._enforce_types(schema_cls, typed_params)
        
        # Step 7: Instantiate Schema (Validates Required Fields)
        try:
            return schema_cls(**typed_params)
        except TypeError as e:
            raise SchemaValidationError(ERR_SCHEMA.format(details=str(e)))
        except ValueError as e:
            raise SchemaValidationError(ERR_SCHEMA.format(details=str(e)))

    def _enforce_types(self, schema_cls: Type[M5Query], params: Dict[str, Any]) -> None:
        """
        Strictly validate that values match the Dataclass type hints for primitives.
        """
        annotations = schema_cls.__annotations__
        for key, value in params.items():
            if key not in annotations:
                continue # Should be filtered already logic-wise
            
            expected_type = annotations[key]
            
            # Handle Optional (Union[T, None]) - simplified check
            # In Python < 3.10, Optional[float] is Union[float, NoneType]
            # We can use limited heuristics or 'typing.get_origin'.
            
            # For M5, key types are: str, float, int, bool, List, Enums.
            
            # Skip checking Enums here (handled in _convert_enums or safely passed)
            # Skip checking None (allowed for Optionals usually)
            if value is None:
                continue
                
            # If expected is float, allow int or float
            if expected_type == float or expected_type == Optional[float]:
                if not isinstance(value, (float, int)):
                    raise SchemaValidationError(f"Param '{key}' expected float, got {type(value).__name__}")
            elif expected_type == int or expected_type == Optional[int]:
                if not isinstance(value, int):
                    raise SchemaValidationError(f"Param '{key}' expected int, got {type(value).__name__}")
            elif expected_type == bool or expected_type == Optional[bool]:
                if not isinstance(value, bool):
                    raise SchemaValidationError(f"Param '{key}' expected bool, got {type(value).__name__}")
            elif expected_type == str or expected_type == Optional[str]:
                if not isinstance(value, str):
                    raise SchemaValidationError(f"Param '{key}' expected str, got {type(value).__name__}")


    def execute_query(self, query_type: str, params: Dict[str, Any]) -> Any:
        """
        Public Entry Point.
        """
        # 1. Validation Pipeline
        query_obj = self._validate_and_build_query(query_type, params)
        
        # 2. Execution Dispatch
        raw_result = self._dispatch_execution(query_obj)
        
        # 3. Output Normalization
        clean_result = normalize_output(query_obj, raw_result)
        
        return clean_result

    def _handle_identity_query(self, query: IdentityQuery) -> dict:
        """Handle IdentityQuery - returns node identity info."""
        node = self._store.get_node(query.node_id)
        if not node:
            return {}
        return {
            "node_id": node.id,
            "state": node.get_lifecycle_state(
                query.current_ts if hasattr(query, 'current_ts') else 0.0
            ).upper(),
            "creation_ts": node.first_seen_ts,
            "last_update_ts": node.last_interaction_ts,
            "price_center": node.price_center,
            "creation_reason": node.creation_reason
        }

    def _handle_local_context_query(self, query: LocalContextQuery) -> dict:
        """Handle LocalContextQuery - returns view-specific node context."""
        if query.view_type == M4ViewType.COMPOSITION:
            return asdict(self._store.get_evidence_composition_view(query.node_id, query.current_ts))
        elif query.view_type == M4ViewType.DENSITY:
            return asdict(self._store.get_interaction_density_view(query.node_id, query.current_ts))
        elif query.view_type == M4ViewType.STABILITY:
            return asdict(self._store.get_stability_transience_view(query.node_id, query.current_ts))
        else:
            raise AccessDeniedError(f"View {query.view_type.name} not supported in LocalContext")

    def _handle_temporal_sequence_query(self, query: TemporalSequenceQuery) -> list:
        """Handle TemporalSequenceQuery - returns filtered token sequence."""
        node = self._store.get_node(query.node_id)
        if not node:
            return []

        all_tokens = list(node.sequence_buffer.tokens)
        valid = [t for t in all_tokens if t[1] < query.query_end_ts]

        if query.lookback_seconds:
            start_ts = query.query_end_ts - query.lookback_seconds
            valid = [t for t in valid if t[1] >= start_ts]

        valid.sort(key=lambda t: t[1])

        if query.max_tokens:
            valid = valid[-query.max_tokens:]

        return [
            {
                "token_type": t[0],
                "timestamp": t[1],
                "volume": 0.0,
                "duration": 0.0
            }
            for t in valid
        ]

    def _handle_spatial_group_query(self, query: SpatialGroupQuery) -> list:
        """Handle SpatialGroupQuery - returns nodes within price range."""
        results = []
        candidates = list(self._store._active_nodes.values())
        if query.include_dormant:
            candidates.extend(self._store._dormant_nodes.values())

        for node in candidates:
            if query.symbol and node.symbol != query.symbol:
                continue
            if query.min_price <= node.price_center <= query.max_price:
                results.append({
                    "node_id": node.id,
                    "price": node.price_center,
                    "state": node.get_lifecycle_state(query.current_ts),
                    "distance_from_min": node.price_center - query.min_price
                })
        return results

    def _handle_state_distribution_query(self, query: StateDistributionQuery) -> dict:
        """Handle StateDistributionQuery - returns node counts by state."""
        if query.symbol:
            counts = {
                "ACTIVE": sum(1 for n in self._store._active_nodes.values() if n.symbol == query.symbol),
                "DORMANT": sum(1 for n in self._store._dormant_nodes.values() if n.symbol == query.symbol),
                "ARCHIVED": sum(1 for n in self._store._archived_nodes.values() if n.symbol == query.symbol),
                "total_count": 0
            }
        else:
            counts = {
                "ACTIVE": len(self._store._active_nodes),
                "DORMANT": len(self._store._dormant_nodes),
                "ARCHIVED": len(self._store._archived_nodes),
                "total_count": 0
            }
        counts["total_count"] = counts["ACTIVE"] + counts["DORMANT"] + counts["ARCHIVED"]
        return counts

    def _handle_proximity_query(self, query: ProximityQuery) -> list:
        """Handle ProximityQuery - returns nodes within radius of center price."""
        center = query.center_price
        radius = query.search_radius

        candidates = list(self._store._active_nodes.values())
        if query.include_dormant:
            candidates.extend(self._store._dormant_nodes.values())

        results = []
        for node in candidates:
            if query.symbol and node.symbol != query.symbol:
                continue
            dist = abs(node.price_center - center)
            if dist <= radius:
                results.append({
                    "node_id": node.id,
                    "price": node.price_center,
                    "distance": dist,
                    "direction": node.price_center - center
                })
        return results

    # -------------------------------------------------------------------------
    # M4 Tier A Computation Handlers
    # -------------------------------------------------------------------------

    def _handle_structural_boundary_violation_query(self, query: StructuralBoundaryViolationQuery):
        """A1: Placeholder - requires traversal data from caller."""
        return None

    def _handle_structural_conversion_failure_query(self, query: StructuralConversionFailureQuery):
        """A2: Placeholder - requires violation + post-violation data from caller."""
        return None

    def _handle_price_traversal_velocity_query(self, query: PriceTraversalVelocityQuery):
        """A3: Price Traversal Velocity."""
        return compute_price_traversal_velocity(
            traversal_id=query.node_id,
            price_start=query.start_price,
            price_end=query.end_price,
            ts_start=query.start_ts,
            ts_end=query.end_ts
        )

    def _handle_traversal_compactness_query(self, query: TraversalCompactnessQuery):
        """A4: Traversal Compactness."""
        return compute_traversal_compactness(
            traversal_id=query.node_id,
            ordered_prices=query.price_sequence
        )

    def _handle_price_acceptance_ratio_query(self, query: PriceAcceptanceRatioQuery):
        """A5: Price Acceptance Ratio."""
        return compute_price_acceptance_ratio(
            candle_open=query.open_price,
            candle_high=query.high_price,
            candle_low=query.low_price,
            candle_close=query.close_price
        )

    def _handle_zone_penetration_depth_query(self, query: ZonePenetrationDepthQuery):
        """A6: Zone Penetration Depth."""
        traversal_prices = [query.observed_low, query.observed_high]
        return compute_zone_penetration_depth(
            zone_id=query.node_id,
            zone_low=query.zone_low,
            zone_high=query.zone_high,
            traversal_prices=traversal_prices
        )

    def _handle_displacement_origin_anchor_query(self, query: DisplacementOriginAnchorQuery):
        """A7: Displacement Origin Anchor."""
        return identify_displacement_origin_anchor(
            traversal_id=query.node_id,
            pre_traversal_prices=query.price_sequence,
            pre_traversal_timestamps=query.timestamp_sequence
        )

    def _handle_central_tendency_deviation_query(self, query: CentralTendencyDeviationQuery):
        """A8: Central Tendency Deviation."""
        return compute_central_tendency_deviation(
            price=query.reference_price,
            central_tendency=query.central_price
        )

    # -------------------------------------------------------------------------
    # M4 Tier B-1 Structural Absence Handlers
    # -------------------------------------------------------------------------

    def _handle_structural_absence_duration_query(self, query: StructuralAbsenceDurationQuery):
        """B1.1: Structural Absence Duration."""
        return compute_structural_absence_duration(
            observation_start_ts=query.observation_start_ts,
            observation_end_ts=query.observation_end_ts,
            presence_intervals=query.presence_intervals
        )

    def _handle_traversal_void_span_query(self, query: TraversalVoidSpanQuery):
        """B1.2: Traversal Void Span."""
        return compute_traversal_void_span(
            observation_start_ts=query.observation_start_ts,
            observation_end_ts=query.observation_end_ts,
            traversal_timestamps=query.traversal_timestamps
        )

    def _handle_event_non_occurrence_counter_query(self, query: EventNonOccurrenceCounterQuery):
        """B1.3: Event Non-Occurrence Counter."""
        return compute_event_non_occurrence_counter(
            expected_event_ids=query.expected_event_ids,
            observed_event_ids=query.observed_event_ids
        )

    # -------------------------------------------------------------------------
    # M4 Tier B-2 Structural Persistence Handlers
    # -------------------------------------------------------------------------

    def _handle_structural_persistence_duration_query(self, query: StructuralPersistenceDurationQuery):
        """B2.1: Structural Persistence Duration."""
        return compute_structural_persistence_duration(
            observation_start_ts=query.observation_start_ts,
            observation_end_ts=query.observation_end_ts,
            presence_intervals=query.presence_intervals
        )

    def _handle_structural_exposure_count_query(self, query: StructuralExposureCountQuery):
        """B2.2: Structural Exposure Count."""
        return compute_structural_exposure_count(
            exposure_timestamps=query.exposure_timestamps,
            observation_start_ts=query.observation_start_ts,
            observation_end_ts=query.observation_end_ts
        )

    def _dispatch_execution(self, query: M5Query) -> Any:
        """
        Maps M5Query objects to M4 Wrapper calls on the store.
        Includes timing and logging for operational visibility.
        """
        query_type = type(query).__name__
        start_time = time.perf_counter()

        try:
            result = self._route_query(query)
            elapsed = time.perf_counter() - start_time
            logger.info(f"M5 query {query_type} completed in {elapsed:.4f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"M5 query {query_type} failed after {elapsed:.4f}s: {e}", exc_info=True)
            raise

    def _route_query(self, query: M5Query) -> Any:
        """Route query to appropriate handler."""
        if isinstance(query, IdentityQuery):
            return self._handle_identity_query(query)

        elif isinstance(query, LocalContextQuery):
            return self._handle_local_context_query(query)

        elif isinstance(query, TemporalSequenceQuery):
            return self._handle_temporal_sequence_query(query)

        elif isinstance(query, SpatialGroupQuery):
            return self._handle_spatial_group_query(query)

        elif isinstance(query, StateDistributionQuery):
            return self._handle_state_distribution_query(query)

        elif isinstance(query, ProximityQuery):
            return self._handle_proximity_query(query)

        # M4 Tier A Structural Primitives
        elif isinstance(query, StructuralBoundaryViolationQuery):
            return self._handle_structural_boundary_violation_query(query)

        elif isinstance(query, StructuralConversionFailureQuery):
            return self._handle_structural_conversion_failure_query(query)

        elif isinstance(query, PriceTraversalVelocityQuery):
            return self._handle_price_traversal_velocity_query(query)

        elif isinstance(query, TraversalCompactnessQuery):
            return self._handle_traversal_compactness_query(query)

        elif isinstance(query, PriceAcceptanceRatioQuery):
            return self._handle_price_acceptance_ratio_query(query)

        elif isinstance(query, ZonePenetrationDepthQuery):
            return self._handle_zone_penetration_depth_query(query)

        elif isinstance(query, DisplacementOriginAnchorQuery):
            return self._handle_displacement_origin_anchor_query(query)

        elif isinstance(query, CentralTendencyDeviationQuery):
            return self._handle_central_tendency_deviation_query(query)

        # M4 Tier B-1 Structural Absence Primitives
        elif isinstance(query, StructuralAbsenceDurationQuery):
            return self._handle_structural_absence_duration_query(query)

        elif isinstance(query, TraversalVoidSpanQuery):
            return self._handle_traversal_void_span_query(query)

        elif isinstance(query, EventNonOccurrenceCounterQuery):
            return self._handle_event_non_occurrence_counter_query(query)

        # M4 Tier B-2 Structural Persistence Primitives
        elif isinstance(query, StructuralPersistenceDurationQuery):
            return self._handle_structural_persistence_duration_query(query)

        elif isinstance(query, StructuralExposureCountQuery):
            return self._handle_structural_exposure_count_query(query)

        else:
            raise AccessDeniedError(f"Query execution not implemented for {type(query)}")
