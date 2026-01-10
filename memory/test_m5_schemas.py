"""
Tests for M5 Query Schemas.
Verifies that the contracts are strict, immutable, and correctly typed.
"""

import pytest
from dataclasses import FrozenInstanceError
from memory.m5_query_schemas import (
    M5Query,
    IdentityQuery,
    LocalContextQuery,
    TemporalSequenceQuery,
    SpatialGroupQuery,
    StateDistributionQuery,
    ProximityQuery,
    M4ViewType,
    LifecycleState
)

# ==============================================================================
# TEST 1: IMMUTABILITY
# ==============================================================================

def test_schemas_are_immutable():
    """Verify that M5 queries cannot be modified after creation."""
    query = IdentityQuery(node_id="test_node")
    
    with pytest.raises(FrozenInstanceError):
        query.node_id = "modified_node"
        
    with pytest.raises(FrozenInstanceError):
        query.include_archived = True

# ==============================================================================
# TEST 2: IDENTITY QUERY
# ==============================================================================

def test_identity_query_structure():
    """Verify IdentityQuery parameters."""
    q = IdentityQuery(node_id="test_1", include_archived=True)
    assert q.node_id == "test_1"
    assert q.include_archived is True
    
    # Default
    q_default = IdentityQuery(node_id="test_2")
    assert q_default.include_archived is False

# ==============================================================================
# TEST 3: LOCAL CONTEXT QUERY
# ==============================================================================

def test_local_context_query_structure():
    """Verify LocalContextQuery parameters."""
    q = LocalContextQuery(
        node_id="test_3",
        current_ts=1000.0,
        view_type=M4ViewType.DENSITY
    )
    assert q.node_id == "test_3"
    assert q.current_ts == 1000.0
    assert q.view_type == M4ViewType.DENSITY

# ==============================================================================
# TEST 4: TEMPORAL SEQUENCE QUERY
# ==============================================================================

def test_temporal_sequence_query_structure():
    """Verify TemporalSequenceQuery parameters."""
    q = TemporalSequenceQuery(
        node_id="test_4",
        query_end_ts=2000.0,
        lookback_seconds=60.0,
        max_tokens=100
    )
    assert q.node_id == "test_4"
    assert q.query_end_ts == 2000.0
    assert q.lookback_seconds == 60.0
    assert q.max_tokens == 100
    
    # Defaults
    q_def = TemporalSequenceQuery(node_id="test_5", query_end_ts=3000.0)
    assert q_def.lookback_seconds is None
    assert q_def.max_tokens is None

# ==============================================================================
# TEST 5: SPATIAL GROUP QUERY
# ==============================================================================

def test_spatial_group_query_structure():
    """Verify SpatialGroupQuery parameters."""
    q = SpatialGroupQuery(
        min_price=100.0,
        max_price=200.0,
        current_ts=1000.0,
        include_dormant=True
    )
    assert q.min_price == 100.0
    assert q.max_price == 200.0
    assert q.current_ts == 1000.0
    assert q.include_dormant is True

# ==============================================================================
# TEST 6: STATE DISTRIBUTION QUERY
# ==============================================================================

def test_state_distribution_query_structure():
    """Verify StateDistributionQuery parameters."""
    q = StateDistributionQuery(
        query_ts=5000.0,
        states=[LifecycleState.ACTIVE, LifecycleState.DORMANT]
    )
    assert q.query_ts == 5000.0
    assert len(q.states) == 2
    assert LifecycleState.ACTIVE in q.states

# ==============================================================================
# TEST 7: PROXIMITY QUERY
# ==============================================================================

def test_proximity_query_structure():
    """Verify ProximityQuery parameters."""
    q = ProximityQuery(
        center_price=150.0,
        search_radius=5.0,
        current_ts=1000.0,
        include_dormant=False
    )
    assert q.center_price == 150.0
    assert q.search_radius == 5.0

# ==============================================================================
# TEST 8: POLYMORPHISM
# ==============================================================================

def test_queries_are_m5_measure_instances():
    """Verify all queries inherit from M5Query base."""
    q1 = IdentityQuery(node_id="1")
    q2 = ProximityQuery(center_price=1.0, search_radius=1.0, current_ts=1.0)
    
    assert isinstance(q1, M5Query)
    assert isinstance(q2, M5Query)
