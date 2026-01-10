"""
Tests for M4 Event Absence (B1.3)

Per Tier B Canon v1.0 - Phase B-1
"""

import pytest
from memory.m4_event_absence import (
    compute_event_non_occurrence_counter,
    EventNonOccurrenceCounter
)


def test_all_expected_observed():
    """All expected events observed → zero non-occurrence."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2", "E3"),
        observed_event_ids=("E1", "E2", "E3")
    )
    
    assert result.expected_count == 3
    assert result.observed_count == 3
    assert result.non_occurrence_count == 0


def test_none_observed():
    """None observed → all non-occurred."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2", "E3"),
        observed_event_ids=()
    )
    
    assert result.expected_count == 3
    assert result.observed_count == 0
    assert result.non_occurrence_count == 3


def test_partial_observed():
    """Partial observed → some non-occurred."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2", "E3"),
        observed_event_ids=("E1", "E3")
    )
    
    assert result.expected_count == 3
    assert result.observed_count == 2
    assert result.non_occurrence_count == 1


def test_duplicate_observed_ids():
    """Duplicate observed IDs count once per expected ID."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2"),
        observed_event_ids=("E1", "E1", "E1", "E2")
    )
    
    # E1 observed (duplicates don't matter), E2 observed
    assert result.expected_count == 2
    assert result.observed_count == 2
    assert result.non_occurrence_count == 0


def test_extra_observed_ids():
    """Extra observed IDs (not expected) don't affect count."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2"),
        observed_event_ids=("E1", "E2", "E3", "E4")
    )
    
    assert result.expected_count == 2
    assert result.observed_count == 2
    assert result.non_occurrence_count == 0


def test_determinism():
    """Determinism: identical inputs → identical outputs."""
    result1 = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2"),
        observed_event_ids=("E1",)
    )
    
    result2 = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2"),
        observed_event_ids=("E1",)
    )
    
    assert result1 == result2


def test_empty_expected():
    """Empty expected list → zero counts."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=(),
        observed_event_ids=("E1", "E2")
    )
    
    assert result.expected_count == 0
    assert result.observed_count == 0
    assert result.non_occurrence_count == 0


def test_invalid_empty_expected_id():
    """Empty string in expected IDs raises ValueError."""
    with pytest.raises(ValueError):
        compute_event_non_occurrence_counter(
            expected_event_ids=("E1", "", "E2"),
            observed_event_ids=("E1",)
        )


def test_invalid_empty_observed_id():
    """Empty string in observed IDs raises ValueError."""
    with pytest.raises(ValueError):
        compute_event_non_occurrence_counter(
            expected_event_ids=("E1", "E2"),
            observed_event_ids=("E1", "")
        )


def test_immutability():
    """Output dataclass is frozen (immutable)."""
    result = compute_event_non_occurrence_counter(
        expected_event_ids=("E1", "E2"),
        observed_event_ids=("E1",)
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        result.expected_count = 999
