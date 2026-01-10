"""
M5-M4 Tier B-2 Phase 1 Integration Tests

End-to-end verification of M5 → M4 routing for Tier B-2 Phase 1 structural persistence primitives.
Uses real M4 primitive functions, not mocks.

Per Tier B-2 Canon v1.0 - Phase 1
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
# B2.1: Structural Persistence Duration Tests
# ==============================================================================

def test_b21_structural_persistence_duration_happy_path(m5_access):
    """B2.1 Happy Path: Persistence duration computed correctly."""
    result = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ((1020.0, 1080.0),)
    })
    
    # M4 primitive returns frozen dataclass
    assert result.total_persistence_duration == 60.0
    assert result.observation_window == 100.0
    assert result.persistence_ratio == 0.6


def test_b21_determinism(m5_access):
    """B2.1 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ((1020.0, 1080.0),)
    }
    
    result1 = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", params)
    result2 = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", params)
    
    assert result1 == result2


def test_b21_overlapping_intervals(m5_access):
    """B2.1: Overlapping intervals merge correctly."""
    result = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ((1020.0, 1060.0), (1040.0, 1080.0))
    })
    
    # Merged: 1020-1080 = 60
    assert result.total_persistence_duration == 60.0
    assert result.persistence_ratio == 0.6


# ==============================================================================
# B2.2: Structural Exposure Count Tests
# ==============================================================================

def test_b22_structural_exposure_count_happy_path(m5_access):
    """B2.2 Happy Path: Exposure count computed correctly."""
    result = m5_access.execute_query("STRUCTURAL_EXPOSURE_COUNT", {
        "node_id": "TEST_NODE",
        "exposure_timestamps": (1020.0, 1040.0, 1060.0, 1080.0),
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0
    })
    
    assert result.exposure_count == 4
    assert result.observation_window == 100.0


def test_b22_determinism(m5_access):
    """B2.2 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "exposure_timestamps": (1020.0, 1040.0),
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0
    }
    
    result1 = m5_access.execute_query("STRUCTURAL_EXPOSURE_COUNT", params)
    result2 = m5_access.execute_query("STRUCTURAL_EXPOSURE_COUNT", params)
    
    assert result1 == result2


def test_b22_empty_exposures(m5_access):
    """B2.2: Empty exposures → zero count."""
    result = m5_access.execute_query("STRUCTURAL_EXPOSURE_COUNT", {
        "node_id": "TEST_NODE",
        "exposure_timestamps": (),
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0
    })
    
    assert result.exposure_count == 0


# ==============================================================================
# Immutability Tests
# ==============================================================================

def test_tier_b2_output_immutability(m5_access):
    """Tier B-2 Phase 1 outputs must be immutable (frozen dataclasses)."""
    result = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ()
    })
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        result.total_persistence_duration = 999.0


# ==============================================================================
# Type Safety Tests
# ==============================================================================

def test_tier_b2_output_types(m5_access):
    """Tier B-2 Phase 1 outputs must match M4 dataclass types exactly."""
    result = m5_access.execute_query("STRUCTURAL_EXPOSURE_COUNT", {
        "node_id": "TEST_NODE",
        "exposure_timestamps": (1050.0,),
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0
    })
    
    # Verify output structure
    assert hasattr(result, 'exposure_count')
    assert hasattr(result, 'observation_window')
    
    # Verify types
    assert isinstance(result.exposure_count, int)
    assert isinstance(result.observation_window, float)


# ==============================================================================
# Edge Case Tests
# ==============================================================================

def test_b21_full_persistence(m5_access):
    """B2.1: Full coverage → ratio = 1.0."""
    result = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ((1000.0, 1100.0),)
    })
    
    assert result.persistence_ratio == 1.0


def test_b21_zero_persistence(m5_access):
    """B2.1: Empty intervals → zero persistence."""
    result = m5_access.execute_query("STRUCTURAL_PERSISTENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ()
    })
    
    assert result.persistence_ratio == 0.0


def test_b22_single_exposure(m5_access):
    """B2.2: Single exposure counted correctly."""
    result = m5_access.execute_query("STRUCTURAL_EXPOSURE_COUNT", {
        "node_id": "TEST_NODE",
        "exposure_timestamps": (1050.0,),
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0
    })
    
    assert result.exposure_count == 1
