"""
Tests for M4 Structural Boundaries
Per M4 Phase 1 Coding Agent Prompts - Module 2
"""

import pytest
from memory.m4_structural_boundaries import (
    detect_structural_boundary_violation,
    detect_structural_conversion_failure,
    StructuralBoundaryViolation,
    StructuralConversionFailure
)


def test_boundary_violation_determinism():
    """Determinism: same input twice."""
    result1 = detect_structural_boundary_violation(
        boundary_id="B1",
        boundary_price=100.0,
        traversal_prices=[99.0, 101.0, 102.0],
        traversal_timestamps=[1000.0, 1001.0, 1002.0]
    )
    result2 = detect_structural_boundary_violation(
        boundary_id="B1",
        boundary_price=100.0,
        traversal_prices=[99.0, 101.0, 102.0],
        traversal_timestamps=[1000.0, 1001.0, 1002.0]
    )
    assert result1 == result2


def test_boundary_violation_none():
    """No violation returns None."""
    result = detect_structural_boundary_violation(
        boundary_id="B1",
        boundary_price=100.0,
        traversal_prices=[100.0, 100.0],
        traversal_timestamps=[1000.0, 1001.0]
    )
    assert result is None


def test_boundary_violation_single():
    """Single violation detected."""
    result = detect_structural_boundary_violation(
        boundary_id="B1",
        boundary_price=100.0,
        traversal_prices=[99.0, 102.0],
        traversal_timestamps=[1000.0, 1001.0]
    )
    assert result is not None
    assert result.boundary_id == "B1"
    assert result.violation_depth > 0


def test_conversion_failure_immediate_reversion():
    """Immediate reversion detected."""
    violation = StructuralBoundaryViolation(
        boundary_id="B1",
        violation_depth=2.0,
        violation_start_ts=1000.0,
        violation_end_ts=1001.0,
        violation_duration=1.0
    )
    result = detect_structural_conversion_failure(
        boundary_id="B1",
        violation=violation,
        post_violation_prices=[99.0],
        post_violation_timestamps=[1002.0],
        conversion_window=10.0
    )
    assert result is not None


def test_invalid_timestamp_ordering():
    """Non-increasing timestamps raise error."""
    with pytest.raises(ValueError):
        detect_structural_boundary_violation(
            boundary_id="B1",
            boundary_price=100.0,
            traversal_prices=[99.0, 101.0],
            traversal_timestamps=[1001.0, 1000.0]
        )
