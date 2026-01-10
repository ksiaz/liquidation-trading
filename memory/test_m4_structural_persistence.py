"""
Tests for M4 Structural Persistence (B2.1)

Per Tier B-2 Canon v1.0 - Phase 1
"""

import pytest
import math
from memory.m4_structural_persistence import (
    compute_structural_persistence_duration,
    StructuralPersistenceDuration
)


def test_full_persistence():
    """Full coverage → ratio = 1.0."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1000.0, 1100.0),)
    )
    
    assert result.total_persistence_duration == 100.0
    assert result.observation_window == 100.0
    assert result.persistence_ratio == 1.0


def test_partial_persistence():
    """Partial coverage → partial ratio."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1080.0),)
    )
    
    # Present: 60, Window: 100
    assert result.total_persistence_duration == 60.0
    assert result.observation_window == 100.0
    assert result.persistence_ratio == 0.6


def test_zero_persistence():
    """Empty intervals → zero persistence."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=()
    )
    
    assert result.total_persistence_duration == 0.0
    assert result.observation_window == 100.0
    assert result.persistence_ratio == 0.0


def test_multiple_intervals():
    """Multiple non-overlapping intervals sum correctly."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1010.0, 1020.0), (1030.0, 1040.0), (1050.0, 1060.0))
    )
    
    # Total: 10+10+10=30
    assert result.total_persistence_duration == 30.0
    assert result.observation_window == 100.0
    assert result.persistence_ratio == 0.3


def test_overlapping_intervals():
    """Overlapping intervals merge correctly."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1060.0), (1040.0, 1080.0))
    )
    
    # Merged: 1020-1080 = 60
    assert result.total_persistence_duration == 60.0
    assert result.observation_window == 100.0
    assert result.persistence_ratio == 0.6


def test_adjacent_intervals():
    """Adjacent intervals (touching) merge correctly."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1050.0), (1050.0, 1080.0))
    )
    
    # Merged: 1020-1080 = 60
    assert result.total_persistence_duration == 60.0
    assert result.persistence_ratio == 0.6


def test_determinism():
    """Determinism: identical inputs → identical outputs."""
    result1 = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1060.0),)
    )
    
    result2 = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1060.0),)
    )
    
    assert result1 == result2


def test_invalid_window():
    """Invalid: end <= start raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_persistence_duration(
            observation_start_ts=1100.0,
            observation_end_ts=1000.0,
            presence_intervals=()
        )


def test_invalid_interval_end_before_start():
    """Invalid interval: end <= start."""
    with pytest.raises(ValueError):
        compute_structural_persistence_duration(
            observation_start_ts=1000.0,
            observation_end_ts=1100.0,
            presence_intervals=((1050.0, 1040.0),)
        )


def test_interval_outside_window():
    """Interval outside observation window raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_persistence_duration(
            observation_start_ts=1000.0,
            observation_end_ts=1100.0,
            presence_intervals=((900.0, 950.0),)
        )


def test_nan_observation_start():
    """NaN in observation_start_ts raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_persistence_duration(
            observation_start_ts=float('nan'),
            observation_end_ts=1100.0,
            presence_intervals=()
        )


def test_infinity_observation_end():
    """Infinity in observation_end_ts raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_persistence_duration(
            observation_start_ts=1000.0,
            observation_end_ts=float('inf'),
            presence_intervals=()
        )


def test_nan_interval():
    """NaN in interval raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_persistence_duration(
            observation_start_ts=1000.0,
            observation_end_ts=1100.0,
            presence_intervals=((1020.0, float('nan')),)
        )


def test_immutability():
    """Output dataclass is frozen (immutable)."""
    result = compute_structural_persistence_duration(
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=()
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        result.total_persistence_duration = 999.0
