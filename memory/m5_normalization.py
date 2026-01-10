"""
M5 Output Normalization - The Cleaner.
Enforces uniform output structure and strips forbidden fields.
"""

from typing import Dict, Any, List
from memory.m5_query_schemas import (
    M5Query,
    IdentityQuery,
    LocalContextQuery,
    TemporalSequenceQuery,
    SpatialGroupQuery,
    StateDistributionQuery,
    ProximityQuery
)
from memory.m5_constants import GLOBAL_FORBIDDEN_OUTPUTS

class EpistemicSafetyError(Exception):
    """Raised when an output violates M5 safety protocols."""
    pass

def _scan_and_strip_forbidden(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively remove forbidden keys from a dictionary.
    Raises EpistemicSafetyError if a forbidden key is critical (this logic can be adjusted).
    Currently, we just strip them to be safe, but if we want to be strict, we could raise.
    M5 Policy: "Block... if any key matches".
    Blocking implies raising an error, so the Strategy knows it asked for something illegal 
    or the system produced something illegal.
    """
    clean = {}
    for key, val in data.items():
        if key in GLOBAL_FORBIDDEN_OUTPUTS:
            # We treat this as an internal system violation essentially, 
            # because M4 views *should* be clean. If they aren't, M5 blocks delivery.
            raise EpistemicSafetyError(f"Forbidden output field detected: {key}")
        
        # Recursive check for nested dicts
        if isinstance(val, dict):
            clean[key] = _scan_and_strip_forbidden(val)
        elif isinstance(val, list):
            clean[key] = [_scan_and_strip_forbidden(i) if isinstance(i, dict) else i for i in val]
        else:
            clean[key] = val
    return clean

def normalize_identity_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Identity Query output.
    Required fields: node_id, state, creation_ts, last_update_ts, price_center, creation_reason.
    """
    # 1. Scan for forbidden
    clean = _scan_and_strip_forbidden(result)
    
    # 2. Ensure Schema Compliance (Optional strict check, or just pass through structured data)
    # We assume M4/Store returns roughly correct data. We just enforce safety here.
    return clean

def normalize_local_context_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Local Context output.
    """
    return _scan_and_strip_forbidden(result)

def normalize_temporal_sequence_result(result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize Temporal Sequence output.
    Must be ordered by timestamp ASC (usually).
    """
    clean_list = [_scan_and_strip_forbidden(item) for item in result]
    # Enforce deterministic sort: Timestamp ASC
    # If timestamps match, sort by event type or something stable?
    clean_list.sort(key=lambda x: x.get("timestamp", 0.0))
    return clean_list

def normalize_spatial_group_result(result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize Spatial Group output.
    Must be ordered by Price ASC.
    """
    clean_list = [_scan_and_strip_forbidden(item) for item in result]
    clean_list.sort(key=lambda x: x.get("price", 0.0))
    return clean_list

def normalize_state_distribution_result(result: Dict[str, int]) -> Dict[str, int]:
    """
    Normalize State Distribution output.
    """
    return _scan_and_strip_forbidden(result)

def normalize_proximity_result(result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize Proximity output.
    Must be ordered by Distance ASC.
    """
    clean_list = [_scan_and_strip_forbidden(item) for item in result]
    clean_list.sort(key=lambda x: x.get("distance", float('inf')))
    return clean_list

def normalize_output(query: M5Query, raw_result: Any) -> Any:
    """
    Dispatch to specific normalizer based on query type.
    """
    if isinstance(query, IdentityQuery):
        return normalize_identity_result(raw_result)
    elif isinstance(query, LocalContextQuery):
        return normalize_local_context_result(raw_result)
    elif isinstance(query, TemporalSequenceQuery):
        return normalize_temporal_sequence_result(raw_result)
    elif isinstance(query, SpatialGroupQuery):
        return normalize_spatial_group_result(raw_result)
    elif isinstance(query, StateDistributionQuery):
        return normalize_state_distribution_result(raw_result)
    elif isinstance(query, ProximityQuery):
        return normalize_proximity_result(raw_result)
    else:
        # Fallback for unknown types (should not happen if typed correctly)
        if isinstance(raw_result, dict):
            return _scan_and_strip_forbidden(raw_result)
        elif isinstance(raw_result, list):
             return [_scan_and_strip_forbidden(i) if isinstance(i, dict) else i for i in raw_result]
        return raw_result
