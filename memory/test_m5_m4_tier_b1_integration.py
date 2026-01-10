"""
M5-M4 Tier B-1 Integration Tests

End-to-end verification of M5 → M4 routing for Tier B-1 structural absence primitives.
Uses real M4 primitive functions, not mocks.

Per Tier B Canon v1.0 - Phase B-1
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
# B1.1: Structural Absence Duration Tests
# ==============================================================================

def test_b11_structural_absence_duration_happy_path(m5_access):
    """B1.1 Happy Path: Absence duration computed correctly."""
    result = m5_access.execute_query("STRUCTURAL_ABSENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ((1020.0, 1080.0),)
    })
    
    # M4 primitive returns frozen dataclass
    assert result.observation_window == 100.0
    assert result.absence_duration == 40.0  # 100 - 60
    assert result.absence_ratio == 0.4


def test_b11_determinism(m5_access):
    """B1.1 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ((1020.0, 1080.0),)
    }
    
    result1 = m5_access.execute_query("STRUCTURAL_ABSENCE_DURATION", params)
    result2 = m5_access.execute_query("STRUCTURAL_ABSENCE_DURATION", params)
    
    assert result1 == result2


# ==============================================================================
# B1.2: Traversal Void Span Tests
# ==============================================================================

def test_b12_traversal_void_span_happy_path(m5_access):
    """B1.2 Happy Path: Void spans identified correctly."""
    result = m5_access.execute_query("TRAVERSAL_VOID_SPAN", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "traversal_timestamps": (1020.0, 1040.0, 1080.0)
    })
    
    # Voids: [1000-1020], [1020-1040], [1040-1080], [1080-1100]
    assert len(result.void_intervals) == 4
    assert result.max_void_duration == 40.0  # 1040-1080


def test_b12_determinism(m5_access):
    """B1.2 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "traversal_timestamps": (1020.0, 1080.0)
    }
    
    result1 = m5_access.execute_query("TRAVERSAL_VOID_SPAN", params)
    result2 = m5_access.execute_query("TRAVERSAL_VOID_SPAN", params)
    
    assert result1 == result2


# ==============================================================================
# B1.3: Event Non-Occurrence Counter Tests
# ==============================================================================

def test_b13_event_non_occurrence_counter_happy_path(m5_access):
    """B1.3 Happy Path: Non-occurrence count computed correctly."""
    result = m5_access.execute_query("EVENT_NON_OCCURRENCE_COUNTER", {
        "node_id": "TEST_NODE",
        "expected_event_ids": ("E1", "E2", "E3"),
        "observed_event_ids": ("E1", "E3")
    })
    
    assert result.expected_count == 3
    assert result.observed_count == 2
    assert result.non_occurrence_count == 1


def test_b13_determinism(m5_access):
    """B1.3 Determinism: Identical inputs yield identical outputs."""
    params = {
        "node_id": "TEST_NODE",
        "expected_event_ids": ("E1", "E2"),
        "observed_event_ids": ("E1",)
    }
    
    result1 = m5_access.execute_query("EVENT_NON_OCCURRENCE_COUNTER", params)
    result2 = m5_access.execute_query("EVENT_NON_OCCURRENCE_COUNTER", params)
    
    assert result1 == result2


# ==============================================================================
# Immutability Tests
# ==============================================================================

def test_tier_b1_output_immutability(m5_access):
    """Tier B-1 outputs must be immutable (frozen dataclasses)."""
    result = m5_access.execute_query("STRUCTURAL_ABSENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ()
    })
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        result.absence_duration = 999.0


# ==============================================================================
# Type Safety Tests
# ==============================================================================

def test_tier_b1_output_types(m5_access):
    """Tier B-1 outputs must match M4 dataclass types exactly."""
    result = m5_access.execute_query("TRAVERSAL_VOID_SPAN", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "traversal_timestamps": (1050.0,)
    })
    
    # Verify output structure
    assert hasattr(result, 'max_void_duration')
    assert hasattr(result, 'void_intervals')
    
    # Verify types
    assert isinstance(result.max_void_duration, float)
    assert isinstance(result.void_intervals, tuple)


# ==============================================================================
# Edge Case Tests
# ==============================================================================

def test_b11_empty_presence_intervals(m5_access):
    """B1.1: Empty presence intervals → full absence."""
    result = m5_access.execute_query("STRUCTURAL_ABSENCE_DURATION", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "presence_intervals": ()
    })
    
    assert result.absence_ratio == 1.0


def test_b12_empty_traversal_timestamps(m5_access):
    """B1.2: Empty traversal list → full void."""
    result = m5_access.execute_query("TRAVERSAL_VOID_SPAN", {
        "node_id": "TEST_NODE",
        "observation_start_ts": 1000.0,
        "observation_end_ts": 1100.0,
        "traversal_timestamps": ()
    })
    
    assert result.max_void_duration == 100.0
    assert len(result.void_intervals) == 1


def test_b13_none_observed(m5_access):
    """B1.3: None observed → all non-occurred."""
    result = m5_access.execute_query("EVENT_NON_OCCURRENCE_COUNTER", {
        "node_id": "TEST_NODE",
        "expected_event_ids": ("E1", "E2", "E3"),
        "observed_event_ids": ()
    })
    
    assert result.non_occurrence_count == 3
