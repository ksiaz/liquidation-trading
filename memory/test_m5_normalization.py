"""
Tests for M5 Output Normalization.
Verifies that the Cleaner correctly strips forbidden fields and enforces structure.
"""

import pytest
from memory.m5_normalization import (
    normalize_output,
    EpistemicSafetyError,
    _scan_and_strip_forbidden
)
from memory.m5_query_schemas import (
    IdentityQuery,
    SpatialGroupQuery,
    ProximityQuery
)

# ==============================================================================
# TEST 1: STRIP FORBIDDEN FIELDS
# ==============================================================================

def test_strip_forbidden_fields_raises_error():
    """Verify that presence of forbidden fields logic is triggered."""
    # The current implementation RAISES error if forbidden key is found.
    # Policy says "Block... if any key matches".
    
    dirty_data = {
        "node_id": "123",
        "score": 0.95,  # Forbidden
        "data": "valid"
    }
    
    with pytest.raises(EpistemicSafetyError):
        _scan_and_strip_forbidden(dirty_data)

def test_strip_forbidden_fields_nested_raises_error():
    """Verify recursive checking."""
    dirty_nested = {
        "valid": True,
        "details": {
            "rank": 1, # Forbidden
            "info": "bad"
        }
    }
    with pytest.raises(EpistemicSafetyError):
        _scan_and_strip_forbidden(dirty_nested)

def test_strip_forbidden_fields_list_raises_error():
    """Verify checking inside lists."""
    dirty_list = [
        {"id": 1},
        {"id": 2, "quality": "high"} # Forbidden
    ]
    # _scan_and_strip_forbidden handles dicts directly. 
    # But normalize_* functions iterate lists.
    # Let's test the helper directly on a dict if possible, or verify normalization flow.
    # The helper is recursive on lists too.
    
    # We can't pass a list to _scan_and_strip_forbidden directly based on type hint Dict,
    # but the implementation handles it?
    # Implementation: `if isinstance(val, list): clean[key] = ...`
    # It recurses on VALUES. It expects input to be Dict.
    
    # If we pass a list to `normalize_output` (e.g. for TemporalSequence), it calls:
    # `[_scan_and_strip_forbidden(item) for item in result]`
    
    # So we simulate that.
    with pytest.raises(EpistemicSafetyError):
        _scan_and_strip_forbidden(dirty_list[1])

# ==============================================================================
# TEST 2: IDENTITY NORMALIZATION
# ==============================================================================

def test_normalize_identity_passes_clean_data():
    """Verify safe data passes through."""
    q = IdentityQuery(node_id="test")
    raw = {
        "node_id": "test",
        "state": "ACTIVE",
        "creation_ts": 100.0,
        "last_update_ts": 200.0,
        "price_center": 100.0,
        "creation_reason": "TEST"
    }
    cleaned = normalize_output(q, raw)
    assert cleaned == raw

# ==============================================================================
# TEST 3: SORTING ENFORCEMENT
# ==============================================================================

def test_normalize_spatial_group_sorts_by_price():
    """Verify SpatialGroup results are sorted by Price ASC."""
    q = SpatialGroupQuery(min_price=1, max_price=10, current_ts=100)
    raw = [
        {"node_id": "B", "price": 200.0},
        {"node_id": "A", "price": 100.0},
        {"node_id": "C", "price": 150.0}
    ]
    
    cleaned = normalize_output(q, raw)
    
    assert cleaned[0]["node_id"] == "A"
    assert cleaned[1]["node_id"] == "C"
    assert cleaned[2]["node_id"] == "B"

def test_normalize_proximity_sorts_by_distance():
    """Verify Proximity results are sorted by Distance ASC."""
    q = ProximityQuery(center_price=100, search_radius=10, current_ts=100)
    raw = [
        {"node_id": "Far", "distance": 10.0},
        {"node_id": "Near", "distance": 1.0},
        {"node_id": "Mid", "distance": 5.0}
    ]
    
    cleaned = normalize_output(q, raw)
    
    assert cleaned[0]["node_id"] == "Near"
    assert cleaned[1]["node_id"] == "Mid"
    assert cleaned[2]["node_id"] == "Far"

# ==============================================================================
# TEST 4: FALLBACK SAFETY
# ==============================================================================

def test_normalize_fallback_strips_forbidden():
    """Verify fallback strips forbidden keys if query type unknown (shouldn't happen but safe)."""
    # Just pass None as query to trigger fallback
    raw = {"data": "ok", "alpha": 0.5}
    
    with pytest.raises(EpistemicSafetyError):
        normalize_output(None, raw)
