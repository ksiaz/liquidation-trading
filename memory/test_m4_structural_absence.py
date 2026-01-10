"""
Tests for M4 Structural Absence (B1.1)

Per Tier B Canon v1.0 - Phase B-1
"""

import pytest
from memory.m4_structural_absence import (
    compute_structural_absence_duration,
    StructuralAbsenceDuration
)


def test_empty_intervals_full_absence():
    """Empty presence intervals → full absence."""
    result = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=()
    )
    
    assert result.absence_duration == 100.0
    assert result.observation_window == 100.0
    assert result.absence_ratio == 1.0


def test_full_coverage_zero_absence():
    """Fully covered window → zero absence."""
    result = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1000.0, 1100.0),)
    )
    
    assert result.absence_duration == 0.0
    assert result.observation_window == 100.0
    assert result.absence_ratio == 0.0


def test_partial_coverage():
    """Partial coverage → partial absence."""
    result = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1080.0),)
    )
    
    # Present: 60, Absent: 40
    assert result.absence_duration == 40.0
    assert result.observation_window == 100.0
    assert result.absence_ratio == 0.4


def test_overlapping_intervals():
    """Overlapping intervals handled correctly."""
    result = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1060.0), (1040.0, 1080.0))
    )
    
    # Merged: 1020-1080 = 60, Absent: 40
    assert result.absence_duration == 40.0
    assert result.observation_window == 100.0
    assert result.absence_ratio == 0.4


def test_multiple_non_overlapping_intervals():
    """Multiple non-overlapping intervals."""
    result = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1010.0, 1020.0), (1030.0, 1040.0), (1050.0, 1060.0))
    )
    
    # Present: 10+10+10=30, Absent: 70
    assert result.absence_duration == 70.0
    assert result.observation_window == 100.0
    assert result.absence_ratio == 0.7


def test_determinism():
    """Determinism: identical inputs → identical outputs."""
    result1 = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1050.0,
        presence_intervals=((1010.0, 1030.0),)
    )
    
    result2 = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1050.0,
        presence_intervals=((1010.0, 1030.0),)
    )
    
    assert result1 == result2


def test_invalid_observation_window():
    """Invalid: end <= start raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_absence_duration(
            observation_start_ts=1100.0,
            observation_end_ts=1000.0,
            presence_intervals=()
        )


def test_invalid_interval_end_before_start():
    """Invalid interval: end <= start."""
    with pytest.raises(ValueError):
        compute_structural_absence_duration(
            observation_start_ts=1000.0,
            observation_end_ts=1100.0,
            presence_intervals=((1050.0, 1040.0),)
        )


def test_interval_outside_window():
    """Interval outside observation window raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_absence_duration(
            observation_start_ts=1000.0,
            observation_end_ts=1100.0,
            presence_intervals=((900.0, 950.0),)
        )


def test_immutability():
    """Output dataclass is frozen (immutable)."""
    result = compute_structural_absence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=()
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        result.absence_duration = 999.0
