"""
M5-M4 Tier A Integration Tests

End-to-end verification of M5 → M4 routing for Tier A structural primitives.
Uses real M4 primitive functions, not mocks.

Per M5 Tier A Access Layer Integration Authorization
"""

import pytest
from memory.m5_access import MemoryAccess
from memory.m2_continuity_store import ContinuityMemoryStore


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def memory_store():
    """Create a simple memory store for integration tests."""
    return ContinuityMemoryStore()


@pytest.fixture
def m5_access(memory_store):
    """Create M5 access facade."""
    return MemoryAccess(memory_store)


# ==============================================================================
# A3: Price Traversal Velocity Tests
# ==============================================================================

def test_a3_price_traversal_velocity_happy_path(m5_access):
    """A3 Happy Path: Velocity computed correctly."""
    result = m5_access.execute_query("PRICE_TRAVERSAL_VELOCITY", {
        "node_id": "TEST_NODE",
        "start_price": 100.0,
        "end_price": 110.0,
        "start_ts": 1000.0,
        "end_ts": 1010.0
    })
    
    # M4 primitive returns frozen dataclass
    assert result.price_delta == 10.0
    assert result.time_delta == 10.0
    assert result.velocity == 1.0


def test_a3_price_traversal_velocity_determinism(m5_access):
    """A3 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "start_price": 100.0,
        "end_price": 105.0,
        "start_ts": 1000.0,
        "end_ts": 1005.0
    }
    
    result1 = m5_access.execute_query("PRICE_TRAVERSAL_VELOCITY", params)
    result2 = m5_access.execute_query("PRICE_TRAVERSAL_VELOCITY", params)
    
    assert result1 == result2


# ==============================================================================
# A4: Traversal Compactness Tests
# ==============================================================================

def test_a4_traversal_compactness_happy_path(m5_access):
    """A4 Happy Path: Compactness ratio computed correctly."""
    result = m5_access.execute_query("TRAVERSAL_COMPACTNESS", {
        "node_id": "TEST_NODE",
        "price_sequence": (100.0, 105.0, 110.0),
        "timestamp_sequence": (1000.0, 1005.0, 1010.0)
    })
    
    assert result.net_displacement == 10.0
    assert result.total_path_length == 10.0
    assert result.compactness_ratio == 1.0  # Perfect line


def test_a4_traversal_compactness_determinism(m5_access):
    """A4 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "price_sequence": (100.0, 110.0, 105.0, 115.0),
        "timestamp_sequence": (1000.0, 1001.0, 1002.0, 1003.0)
    }
    
    result1 = m5_access.execute_query("TRAVERSAL_COMPACTNESS", params)
    result2 = m5_access.execute_query("TRAVERSAL_COMPACTNESS", params)
    
    assert result1 == result2


# ==============================================================================
# A5: Price Acceptance Ratio Tests
# ==============================================================================

def test_a5_price_acceptance_ratio_happy_path(m5_access):
    """A5 Happy Path: Acceptance ratio computed correctly."""
    result = m5_access.execute_query("PRICE_ACCEPTANCE_RATIO", {
        "node_id": "TEST_NODE",
        "open_price": 100.0,
        "high_price": 110.0,
        "low_price": 100.0,
        "close_price": 110.0
    })
    
    # Full body candle
    assert result.accepted_range == 10.0
    assert result.rejected_range == 0.0
    assert result.acceptance_ratio == 1.0


def test_a5_price_acceptance_ratio_determinism(m5_access):
    """A5 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "open_price": 100.0,
        "high_price": 115.0,
        "low_price": 95.0,
        "close_price": 102.0
    }
    
    result1 = m5_access.execute_query("PRICE_ACCEPTANCE_RATIO", params)
    result2 = m5_access.execute_query("PRICE_ACCEPTANCE_RATIO", params)
    
    assert result1 == result2


# ==============================================================================
# A6: Zone Penetration Depth Tests
# ==============================================================================

def test_a6_zone_penetration_depth_happy_path(m5_access):
    """A6 Happy Path: Penetration depth computed correctly."""
    result = m5_access.execute_query("ZONE_PENETRATION_DEPTH", {
        "node_id": "TEST_NODE",
        "zone_low": 100.0,
        "zone_high": 110.0,
        "observed_low": 102.0,
        "observed_high": 108.0
    })
    
    # Penetration detected
    assert result is not None
    assert result.penetration_depth > 0


def test_a6_zone_penetration_depth_no_penetration(m5_access):
    """A6: No penetration returns None."""
    result = m5_access.execute_query("ZONE_PENETRATION_DEPTH", {
        "node_id": "TEST_NODE",
        "zone_low": 100.0,
        "zone_high": 110.0,
        "observed_low": 90.0,
        "observed_high": 95.0
    })
    
    assert result is None


def test_a6_zone_penetration_depth_determinism(m5_access):
    """A6 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "zone_low": 100.0,
        "zone_high": 110.0,
        "observed_low": 105.0,
        "observed_high": 108.0
    }
    
    result1 = m5_access.execute_query("ZONE_PENETRATION_DEPTH", params)
    result2 = m5_access.execute_query("ZONE_PENETRATION_DEPTH", params)
    
    assert result1 == result2


# ==============================================================================
# A7: Displacement Origin Anchor Tests
# ==============================================================================

def test_a7_displacement_origin_anchor_happy_path(m5_access):
    """A7 Happy Path: Anchor identified correctly."""
    result = m5_access.execute_query("DISPLACEMENT_ORIGIN_ANCHOR", {
        "node_id": "TEST_NODE",
        "price_sequence": (100.0, 101.0, 100.5),
        "timestamp_sequence": (1000.0, 1001.0, 1002.0)
    })
    
    assert result.anchor_low == 100.0
    assert result.anchor_high == 101.0
    assert result.anchor_dwell_time == 2.0


def test_a7_displacement_origin_anchor_determinism(m5_access):
    """A7 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "price_sequence": (100.0, 102.0, 101.0, 103.0),
        "timestamp_sequence": (1000.0, 1001.0, 1002.0, 1003.0)
    }
    
    result1 = m5_access.execute_query("DISPLACEMENT_ORIGIN_ANCHOR", params)
    result2 = m5_access.execute_query("DISPLACEMENT_ORIGIN_ANCHOR", params)
    
    assert result1 == result2


# ==============================================================================
# A8: Central Tendency Deviation Tests
# ==============================================================================

def test_a8_central_tendency_deviation_happy_path(m5_access):
    """A8 Happy Path: Deviation computed correctly."""
    result = m5_access.execute_query("CENTRAL_TENDENCY_DEVIATION", {
        "node_id": "TEST_NODE",
        "reference_price": 105.0,
        "central_price": 100.0
    })
    
    assert result.deviation_value == 5.0


def test_a8_central_tendency_deviation_determinism(m5_access):
    """A8 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "reference_price": 95.0,
        "central_price": 100.0
    }
    
    result1 = m5_access.execute_query("CENTRAL_TENDENCY_DEVIATION", params)
    result2 = m5_access.execute_query("CENTRAL_TENDENCY_DEVIATION", params)
    
    assert result1 == result2


# ==============================================================================
# Immutability Tests
# ==============================================================================

def test_tier_a_output_immutability(m5_access):
    """Tier A outputs must be immutable (frozen dataclasses)."""
    result = m5_access.execute_query("PRICE_TRAVERSAL_VELOCITY", {
        "node_id": "TEST_NODE",
        "start_price": 100.0,
        "end_price": 110.0,
        "start_ts": 1000.0,
        "end_ts": 1010.0
    })
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        result.velocity = 999.0


# ==============================================================================
# Type Safety Tests
# ==============================================================================

def test_tier_a_output_types(m5_access):
    """Tier A outputs must match M4 dataclass types exactly."""
    result = m5_access.execute_query("PRICE_ACCEPTANCE_RATIO", {
        "node_id": "TEST_NODE",
        "open_price": 100.0,
        "high_price": 110.0,
        "low_price": 95.0,
        "close_price": 105.0
    })
    
    # Verify output structure
    assert hasattr(result, 'accepted_range')
    assert hasattr(result, 'rejected_range')
    assert hasattr(result, 'acceptance_ratio')
    
    # Verify types
    assert isinstance(result.accepted_range, float)
    assert isinstance(result.rejected_range, float)
    assert isinstance(result.acceptance_ratio, float)
