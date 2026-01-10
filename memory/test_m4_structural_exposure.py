"""
Tests for M4 Structural Exposure (B2.2)

Per Tier B-2 Canon v1.0 - Phase 1
"""

import pytest
from memory.m4_structural_exposure import (
    compute_structural_exposure_count,
    StructuralExposureCount
)


def test_empty_exposures():
    """Empty timestamps → zero count."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    assert result.exposure_count == 0
    assert result.observation_window == 100.0


def test_single_exposure():
    """Single exposure → count = 1."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(1050.0,),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    assert result.exposure_count == 1
    assert result.observation_window == 100.0


def test_multiple_exposures():
    """Multiple exposures counted correctly."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(1020.0, 1040.0, 1060.0, 1080.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    assert result.exposure_count == 4
    assert result.observation_window == 100.0


def test_unsorted_timestamps():
    """Unsorted timestamps counted correctly."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(1080.0, 1020.0, 1060.0, 1040.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    assert result.exposure_count == 4


def test_duplicate_timestamps():
    """Duplicate timestamps counted (no de-duplication)."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(1050.0, 1050.0, 1050.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    # All duplicates counted
    assert result.exposure_count == 3


def test_exposure_at_boundaries():
    """Exposures at window boundaries are valid."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(1000.0, 1100.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    assert result.exposure_count == 2


def test_determinism():
    """Determinism: identical inputs → identical outputs."""
    result1 = compute_structural_exposure_count(
        exposure_timestamps=(1020.0, 1040.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    result2 = compute_structural_exposure_count(
        exposure_timestamps=(1020.0, 1040.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    assert result1 == result2


def test_invalid_window():
    """Invalid: end <= start raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_exposure_count(
            exposure_timestamps=(),
            observation_start_ts=1100.0,
            observation_end_ts=1000.0
        )


def test_timestamp_before_window():
    """Timestamp before window raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_exposure_count(
            exposure_timestamps=(900.0,),
            observation_start_ts=1000.0,
            observation_end_ts=1100.0
        )


def test_timestamp_after_window():
    """Timestamp after window raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_exposure_count(
            exposure_timestamps=(1200.0,),
            observation_start_ts=1000.0,
            observation_end_ts=1100.0
        )


def test_nan_observation_start():
    """NaN in observation_start_ts raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_exposure_count(
            exposure_timestamps=(),
            observation_start_ts=float('nan'),
            observation_end_ts=1100.0
        )


def test_infinity_observation_end():
    """Infinity in observation_end_ts raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_exposure_count(
            exposure_timestamps=(),
            observation_start_ts=1000.0,
            observation_end_ts=float('inf')
        )


def test_nan_exposure_timestamp():
    """NaN in exposure timestamp raises ValueError."""
    with pytest.raises(ValueError):
        compute_structural_exposure_count(
            exposure_timestamps=(float('nan'),),
            observation_start_ts=1000.0,
            observation_end_ts=1100.0
        )


def test_immutability():
    """Output dataclass is frozen (immutable)."""
    result = compute_structural_exposure_count(
        exposure_timestamps=(),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        result.exposure_count = 999
