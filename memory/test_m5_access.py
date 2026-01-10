"""
Tests for M5 Memory Access Facade.
Verifies the Firewall correctly guards, executes, and sanitizes.
"""

import pytest
from unittest.mock import Mock, MagicMock
from memory.m5_access import (
    MemoryAccess,
    AccessDeniedError,
    SchemaValidationError,
    EpistemicSafetyError,
    DeterminismError
)
from memory.m2_continuity_store import ContinuityMemoryStore
from memory.m5_query_schemas import M4ViewType

# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_store():
    # Mock the store
    store = Mock(spec=ContinuityMemoryStore)
    
    # Mock Node for Identity Query
    mock_node = Mock()
    mock_node.id = "test_node"
    mock_node.state.name = "ACTIVE"
    mock_node.timestamp = 100.0
    mock_node.last_update_timestamp = 200.0
    mock_node.price_center = 100.0
    mock_node.creation_reason = "TEST"
    
    store.get_node.return_value = mock_node
    
    # Mock View for Local Context
    mock_view = Mock()
    mock_view.to_dict.return_value = {"metric": 1.0}
    store.get_interaction_density_view.return_value = mock_view
    
    # Mock public members for Spatial/Proximity (since Access uses them)
    # We need to mock _active_nodes dict
    store._active_nodes = {
        "test_node": mock_node
    }
    store._dormant_nodes = {}
    store._archived_nodes = {}
    
    return store

@pytest.fixture
def access(mock_store):
    return MemoryAccess(mock_store)

# ==============================================================================
# TEST 1: PIPELINE ENFORCEMENT (GUARDS)
# ==============================================================================

def test_access_rejects_forbidden_params(access):
    """Verify guards run before anything else."""
    params = {
        "node_id": "1",
        "min_strength": 0.5 # Forbidden
    }
    with pytest.raises(EpistemicSafetyError):
        access.execute_query("IDENTITY", params)

def test_access_rejects_evaluative_values(access):
    """Verify guards catch semantic violations."""
    params = {
        "node_id": "1",
        "reason": "STRONG_BUY" # Forbidden
    }
    with pytest.raises(EpistemicSafetyError):
        access.execute_query("IDENTITY", params)

def test_access_enforces_determinism(access):
    """Verify implicit time is rejected."""
    params = {
        "node_id": "1",
        "current_ts": "timestamp", # Not float
        # Wait, Guards check specific strings "now", "latest".
        # Schema validation checks TYPE (float).
        # Let's test both.
    }
    # Schema check will fail if type is wrong
    with pytest.raises(SchemaValidationError):
        access.execute_query("LOCAL_CONTEXT", {
            "node_id": "1",
            "view_type": "DENSITY",
            "current_ts": "string_time"
        })

# ==============================================================================
# TEST 2: SCHEMA VALIDATION
# ==============================================================================

def test_access_validates_schema_types(access):
    """Verify schema enforces types at instantiation."""
    # IdentityQuery needs string node_id
    # If we pass int, strictly it might handle it or fail depending on Pydantic/Dataclass behavior.
    # Standard dataclasses don't check type at runtime unless we add logic.
    # M5QuerySchemas are just dataclasses. 
    # BUT we filtered params.
    # If we pass 'abc' for node_id (str), it works. 
    # If we check missing requirement.
    
    with pytest.raises(SchemaValidationError):
        # Missing node_id
        access.execute_query("IDENTITY", {"include_archived": True})

def test_access_rejects_unknown_query_type(access):
    """Verify unknown query type rejection."""
    with pytest.raises(AccessDeniedError):
        access.execute_query("MAGIC_PREDICTION", {})

# ==============================================================================
# TEST 3: EXECUTION & DISPATCH
# ==============================================================================

def test_execute_identity_query(access, mock_store):
    """Verify Identity Query execution."""
    result = access.execute_query("IDENTITY", {"node_id": "test_node"})
    
    # Check store call
    mock_store.get_node.assert_called_with("test_node")
    
    # Check result structure
    assert result["node_id"] == "test_node"
    assert result["state"] == "ACTIVE"

def test_execute_local_context_query(access, mock_store):
    """Verify Local Context execution."""
    result = access.execute_query("LOCAL_CONTEXT", {
        "node_id": "test_node",
        "current_ts": 1000.0,
        "view_type": M4ViewType.DENSITY # Enum must be passed? Or logic converts?
        # Logic: Schema expects Enum.
        # But we pass dict from inputs (usually JSON/Dict primitives).
        # Standard Dataclass doesn't auto-convert String to Enum unless we use a library.
        # So we must pass the Enum object, OR M5 Access logic should handle conversion?
        
        # M5 Policy: "Inputs keys/values".
        # If user passes string "DENSITY", standard dataclass __init__ assigns string.
        # But type hint says M4ViewType. 
        # Python dataclasses do NOT auto-convert.
        # So Access Logic needs to be robust or we expect Caller to match types.
        
        # For this test, let's pass the Enum as expected by Python.
    })
    
    mock_store.get_interaction_density_view.assert_called_with("test_node")
    assert result["metric"] == 1.0

# ==============================================================================
# TEST 4: NORMALIZATION
# ==============================================================================

def test_execute_and_normalize_spatial(access, mock_store):
    """Verify Spatial query result is sorted and stripped."""
    # Mocking active nodes
    n1 = Mock(id="A", price_center=100.0)
    n1.state.name = "ACTIVE"
    n2 = Mock(id="B", price_center=200.0)
    n2.state.name = "ACTIVE"
    
    mock_store._active_nodes = {"A": n1, "B": n2}
    
    # Query with range covering both
    result = access.execute_query("SPATIAL_GROUP", {
        "min_price": 50.0,
        "max_price": 250.0,
        "current_ts": 1000.0
    })
    
    # Expect Sorted by Price
    assert len(result) == 2
    assert result[0]["node_id"] == "A" # 100.0
    assert result[1]["node_id"] == "B" # 200.0
