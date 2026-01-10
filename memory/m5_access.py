"""
M5 Memory Access - The Firewall Facade.
The ONLY allowed entry point for the Strategy Layer to access Memory.
Enforces the Governance Pipeline: Schema -> Guards -> Execution -> Normalization.
"""

from typing import Dict, Any, List, Optional, Union, Type
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

    def _dispatch_execution(self, query: M5Query) -> Any:
        """
        Maps M5Query objects to M4 Wrapper calls on the store.
        """
        if isinstance(query, IdentityQuery):
            node = self._store.get_node(query.node_id)
            if not node:
               return {} 
            return {
                "node_id": node.id,
                "state": node.get_lifecycle_state(query.current_ts if hasattr(query, 'current_ts') else 0.0).upper(), 
                "creation_ts": node.first_seen_ts,
                "last_update_ts": node.last_interaction_ts, # Corrected from last_update_timestamp? Check node attrs methods.
                # Node has last_interaction_ts.
                "price_center": node.price_center,
                "creation_reason": node.creation_reason
            }
            
        elif isinstance(query, LocalContextQuery):
            if query.view_type == M4ViewType.COMPOSITION:
                return asdict(self._store.get_evidence_composition_view(query.node_id, query.current_ts))
            elif query.view_type == M4ViewType.DENSITY:
                return asdict(self._store.get_interaction_density_view(query.node_id, query.current_ts))
            elif query.view_type == M4ViewType.STABILITY:
                return asdict(self._store.get_stability_transience_view(query.node_id, query.current_ts))
            else:
                # Other views not mapped in LocalContextQuery context or unimplemented
                # Maybe CrossNode is separate?
                raise AccessDeniedError(f"View {query.view_type.name} not supported in LocalContext")

        elif isinstance(query, TemporalSequenceQuery):
            node = self._store.get_node(query.node_id)
            if not node:
                return []
                
            # We need to filter by time and limit by max_tokens.
            # This logic mimics M3 internal logic but applied at read time.
            # Or we assume M3 buffer has a query method.
            # For safety: We read the buffer and filter here (since it's Read-Only logic).
            
            all_tokens = list(node.sequence_buffer.tokens) # Convert deque to list
            # Filter: t < query_end_ts
            valid = [
                t_tuple for t_tuple in all_tokens 
                if t_tuple[1] < query.query_end_ts
            ]
            
            if query.lookback_seconds:
                start_ts = query.query_end_ts - query.lookback_seconds
                valid = [t for t in valid if t[1] >= start_ts]
                
            # Sort keys: t[1] is timestamp
            valid.sort(key=lambda t: t[1])
            
            if query.max_tokens:
                 valid = valid[-query.max_tokens:]
                 
            return [
                {
                    "token_type": t[0], # Enum
                    "timestamp": t[1],
                    "volume": 0.0, # SequenceBuffer is purely Token+Time. Volume is lost/not stored here?
                    # M3 Sequence Buffer only stores (Token, Time).
                    # M5 Token output schema includes 'volume', 'duration'.
                    # If data is missing, return 0.0 or defaults.
                    "duration": 0.0
                }
                for t in valid
            ]
            
        elif isinstance(query, SpatialGroupQuery):
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
                        # Use get_lifecycle_state method
                        "state": node.get_lifecycle_state(query.current_ts),
                        "distance_from_min": node.price_center - query.min_price
                    })
            return results

        elif isinstance(query, StateDistributionQuery):
            if query.symbol:
                 # Filtered count (O(N))
                 counts = {
                     "ACTIVE": sum(1 for n in self._store._active_nodes.values() if n.symbol == query.symbol),
                     "DORMANT": sum(1 for n in self._store._dormant_nodes.values() if n.symbol == query.symbol),
                     "ARCHIVED": sum(1 for n in self._store._archived_nodes.values() if n.symbol == query.symbol),
                     "total_count": 0
                 }
            else:
                 # Global count (O(1))
                 counts = {
                    "ACTIVE": len(self._store._active_nodes),
                    "DORMANT": len(self._store._dormant_nodes),
                    "ARCHIVED": len(self._store._archived_nodes),
                    "total_count": 0
                 }
            counts["total_count"] = counts["ACTIVE"] + counts["DORMANT"] + counts["ARCHIVED"]
            return counts

        elif isinstance(query, ProximityQuery):
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
            
        # M4 Tier A Structural Primitives (Per M5 Whitelist Spec v1.0)
        elif isinstance(query, StructuralBoundaryViolationQuery):
            # A1: Structural Boundary Violation
            # Note: This requires traversal data which M2 doesn't directly provide.
            # For initial integration, we return None as no violations can be detected
            # without traversal price/timestamp sequences.
            # Full implementation requires M2 to track price history or receive sequences.
            return None  # Placeholder - requires traversal data from caller
            
        elif isinstance(query, StructuralConversionFailureQuery):
            # A2: Structural Conversion Failure
            # Requires post-violation price data.
            # Placeholder - requires violation + post-violation data from caller
            return None
            
        elif isinstance(query, PriceTraversalVelocityQuery):
            # A3: Price Traversal Velocity
            result = compute_price_traversal_velocity(
                traversal_id=query.node_id,  # Use node_id as traversal_id
                price_start=query.start_price,
                price_end=query.end_price,
                ts_start=query.start_ts,
                ts_end=query.end_ts
            )
            # Return raw M4 primitive output (frozen dataclass)
            return result
            
        elif isinstance(query, TraversalCompactnessQuery):
            # A4: Traversal Compactness
            result = compute_traversal_compactness(
                traversal_id=query.node_id,
                ordered_prices=query.price_sequence
            )
            return result
            
        elif isinstance(query, PriceAcceptanceRatioQuery):
            # A5: Price Acceptance Ratio
            result = compute_price_acceptance_ratio(
                candle_open=query.open_price,
                candle_high=query.high_price,
                candle_low=query.low_price,
                candle_close=query.close_price
            )
            return result
            
        elif isinstance(query, ZonePenetrationDepthQuery):
            # A6: Zone Penetration Depth
            # Construct traversal prices from observed range
            traversal_prices = [query.observed_low, query.observed_high]
            result = compute_zone_penetration_depth(
                zone_id=query.node_id,
                zone_low=query.zone_low,
                zone_high=query.zone_high,
                traversal_prices=traversal_prices
            )
            return result
            
        elif isinstance(query, DisplacementOriginAnchorQuery):
            # A7: Displacement Origin Anchor
            result = identify_displacement_origin_anchor(
                traversal_id=query.node_id,
                pre_traversal_prices=query.price_sequence,
                pre_traversal_timestamps=query.timestamp_sequence
            )
            return result
            
        elif isinstance(query, CentralTendencyDeviationQuery):
            # A8: Central Tendency Deviation
            result = compute_central_tendency_deviation(
                price=query.reference_price,
                central_tendency=query.central_price
            )
            return result
        
        # M4 Tier B-1 Structural Absence Primitives (Per Tier B Canon v1.0)
        elif isinstance(query, StructuralAbsenceDurationQuery):
            # B1.1: Structural Absence Duration
            result = compute_structural_absence_duration(
                observation_start_ts=query.observation_start_ts,
                observation_end_ts=query.observation_end_ts,
                presence_intervals=query.presence_intervals
            )
            return result
            
        elif isinstance(query, TraversalVoidSpanQuery):
            # B1.2: Traversal Void Span
            result = compute_traversal_void_span(
                observation_start_ts=query.observation_start_ts,
                observation_end_ts=query.observation_end_ts,
                traversal_timestamps=query.traversal_timestamps
            )
            return result
            
        elif isinstance(query, EventNonOccurrenceCounterQuery):
            # B1.3: Event Non-Occurrence Counter
            result = compute_event_non_occurrence_counter(
                expected_event_ids=query.expected_event_ids,
                observed_event_ids=query.observed_event_ids
            )
            return result
        
        # M4 Tier B-2 Phase 1 Structural Persistence Primitives (Per Tier B-2 Canon v1.0)
        elif isinstance(query, StructuralPersistenceDurationQuery):
            # B2.1: Structural Persistence Duration
            result = compute_structural_persistence_duration(
                observation_start_ts=query.observation_start_ts,
                observation_end_ts=query.observation_end_ts,
                presence_intervals=query.presence_intervals
            )
            return result
            
        elif isinstance(query, StructuralExposureCountQuery):
            # B2.2: Structural Exposure Count
            result = compute_structural_exposure_count(
                exposure_timestamps=query.exposure_timestamps,
                observation_start_ts=query.observation_start_ts,
                observation_end_ts=query.observation_end_ts
            )
            return result
        
        else:
            raise AccessDeniedError(f"Query execution not implemented for {type(query)}")
