"""
Tests for M4 Traversal Voids (B1.2)

Per Tier B Canon v1.0 - Phase B-1
"""

import pytest
from memory.m4_traversal_voids import (
    compute_traversal_void_span,
    TraversalVoidSpan
)


def test_empty_traversal_list_full_void():
    """No traversal timestamps → one void = full window."""
    result = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=()
    )
    
    assert result.max_void_duration == 100.0
    assert len(result.void_intervals) == 1
    assert result.void_intervals[0] == (1000.0, 1100.0)


def test_single_traversal():
    """Single traversal creates two voids."""
    result = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=(1050.0,)
    )
    
    assert len(result.void_intervals) == 2
    assert result.void_intervals[0] == (1000.0, 1050.0)
    assert result.void_intervals[1] == (1050.0, 1100.0)
    assert result.max_void_duration == 50.0


def test_multiple_traversals():
    """Multiple traversals create multiple voids."""
    result = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=(1020.0, 1040.0, 1080.0)
    )
    
    # Voids: [1000-1020], [1020-1040], [1040-1080], [1080-1100]
    assert len(result.void_intervals) == 4
    assert result.void_intervals[0] == (1000.0, 1020.0)
    assert result.void_intervals[1] == (1020.0, 1040.0)
    assert result.void_intervals[2] == (1040.0, 1080.0)
    assert result.void_intervals[3] == (1080.0, 1100.0)
    assert result.max_void_duration == 40.0  # 1040-1080


def test_traversal_at_window_boundaries():
    """Traversals at window start/end → no voids."""
    result = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=(1000.0, 1100.0)
    )
    
    # Only void is between the two traversals
    assert len(result.void_intervals) == 1
    assert result.void_intervals[0] == (1000.0, 1100.0)
    assert result.max_void_duration == 100.0


def test_determinism():
    """Determinism: identical inputs → identical outputs."""
    result1 = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1050.0,
        traversal_timestamps=(1020.0, 1030.0)
    )
    
    result2 = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1050.0,
        traversal_timestamps=(1020.0, 1030.0)
    )
    
    assert result1 == result2


def test_unsorted_timestamps_handled():
    """Unsorted timestamps are sorted internally."""
    result = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=(1080.0, 1020.0, 1040.0)
    )
    
    # Should produce same result as sorted input
    assert len(result.void_intervals) == 4
    assert result.max_void_duration == 40.0


def test_invalid_observation_window():
    """Invalid: end <= start raises ValueError."""
    with pytest.raises(ValueError):
        compute_traversal_void_span(
            observation_start_ts=1100.0,
            observation_end_ts=1000.0,
            traversal_timestamps=()
        )


def test_timestamp_outside_window():
    """Traversal timestamp outside window raises ValueError."""
    with pytest.raises(ValueError):
        compute_traversal_void_span(
            observation_start_ts=1000.0,
            observation_end_ts=1100.0,
            traversal_timestamps=(900.0,)
        )


def test_immutability():
    """Output dataclass is frozen (immutable)."""
    result = compute_traversal_void_span(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=()
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        result.max_void_duration = 999.0
