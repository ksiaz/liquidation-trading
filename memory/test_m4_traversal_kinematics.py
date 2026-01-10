"""
Tests for M4 Traversal Kinematics

Per M4 Phase 1 Coding Agent Prompts - Module 1
"""

import pytest
from memory.m4_traversal_kinematics import (
    compute_price_traversal_velocity,
    compute_traversal_compactness,
    PriceTraversalVelocity,
    TraversalCompactness
)


# ==============================================================================
# A3: price_traversal_velocity Tests
# ==============================================================================

def test_velocity_determinism():
    """Determinism: same input twice produces identical output."""
    result1 = compute_price_traversal_velocity(
        traversal_id="T1",
        price_start=100.0,
        price_end=110.0,
        ts_start=1000.0,
        ts_end=1010.0
    )
    
    result2 = compute_price_traversal_velocity(
        traversal_id="T1",
        price_start=100.0,
        price_end=110.0,
        ts_start=1000.0,
        ts_end=1010.0
    )
    
    assert result1 == result2


def test_velocity_zero_movement():
    """Zero movement case: price_delta = 0."""
    result = compute_price_traversal_velocity(
        traversal_id="T2",
        price_start=100.0,
        price_end=100.0,
        ts_start=1000.0,
        ts_end=1010.0
    )
    
    assert result.price_delta == 0.0
    assert result.time_delta == 10.0
    assert result.velocity == 0.0


def test_velocity_minimal_valid_traversal():
    """Minimal valid traversal."""
    result = compute_price_traversal_velocity(
        traversal_id="T3",
        price_start=100.0,
        price_end=101.0,
        ts_start=1000.0,
        ts_end=1000.1
    )
    
    assert result.price_delta == 1.0
    assert result.time_delta == pytest.approx(0.1)
    assert result.velocity == pytest.approx(10.0)


def test_velocity_invalid_timestamp():
    """Invalid: ts_end <= ts_start."""
    with pytest.raises(ValueError):
        compute_price_traversal_velocity(
            traversal_id="T4",
            price_start=100.0,
            price_end=110.0,
            ts_start=1010.0,
            ts_end=1000.0
        )


def test_velocity_negative_movement():
    """Negative price movement."""
    result = compute_price_traversal_velocity(
        traversal_id="T5",
        price_start=110.0,
        price_end=100.0,
        ts_start=1000.0,
        ts_end=1010.0
    )
    
    assert result.price_delta == -10.0
    assert result.velocity == -1.0


# ==============================================================================
# A4: traversal_compactness Tests
# ==============================================================================

def test_compactness_determinism():
    """Determinism: same input twice produces identical output."""
    prices = [100.0, 105.0, 103.0, 110.0]
    
    result1 = compute_traversal_compactness(
        traversal_id="T1",
        ordered_prices=prices
    )
    
    result2 = compute_traversal_compactness(
        traversal_id="T1",
        ordered_prices=prices
    )
    
    assert result1 == result2


def test_compactness_perfect_line():
    """Perfect directional movement (compactness = 1.0)."""
    result = compute_traversal_compactness(
        traversal_id="T2",
        ordered_prices=[100.0, 110.0]
    )
    
    assert result.net_displacement == 10.0
    assert result.total_path_length == 10.0
    assert result.compactness_ratio == 1.0


def test_compactness_oscillating():
    """Oscillating movement (compactness < 1.0)."""
    result = compute_traversal_compactness(
        traversal_id="T3",
        ordered_prices=[100.0, 110.0, 105.0, 115.0]
    )
    
    # Net: 115 - 100 = 15
    # Path: 10 + 5 + 10 = 25
    assert result.net_displacement == 15.0
    assert result.total_path_length == 25.0
    assert result.compactness_ratio == 0.6


def test_compactness_zero_movement():
    """Zero movement case."""
    result = compute_traversal_compactness(
        traversal_id="T4",
        ordered_prices=[100.0, 100.0, 100.0]
    )
    
    assert result.net_displacement == 0.0
    assert result.total_path_length == 0.0
    assert result.compactness_ratio == 1.0  # Perfectly compact (no movement)


def test_compactness_invalid_sequence_length():
    """Invalid: < 2 prices."""
    with pytest.raises(ValueError):
        compute_traversal_compactness(
            traversal_id="T5",
            ordered_prices=[100.0]
        )


def test_compactness_minimal_valid():
    """Minimal valid: exactly 2 prices."""
    result = compute_traversal_compactness(
        traversal_id="T6",
        ordered_prices=[100.0, 105.0]
    )
    
    assert result.net_displacement == 5.0
    assert result.compactness_ratio == 1.0
