"""
Tests for M4 Price Distribution
Per M4 Phase 1 Coding Agent Prompts - Module 4
"""

import pytest
from memory.m4_price_distribution import (
    compute_price_acceptance_ratio,
    compute_central_tendency_deviation,
    PriceAcceptanceRatio,
    CentralTendencyDeviation
)


def test_acceptance_ratio_full_body():
    """Full-body candle (no wicks)."""
    result = compute_price_acceptance_ratio(
        candle_open=100.0,
        candle_high=110.0,
        candle_low=100.0,
        candle_close=110.0
    )
    assert result.accepted_range == 10.0
    assert result.rejected_range == 0.0
    assert result.acceptance_ratio == 1.0


def test_acceptance_ratio_long_wick():
    """Long-wick candle."""
    result = compute_price_acceptance_ratio(
        candle_open=100.0,
        candle_high=115.0,
        candle_low=95.0,
        candle_close=102.0
    )
    # Body: 102 - 100 = 2
    # Total: 115 - 95 = 20
    # Wicks: 18
    assert result.accepted_range == 2.0
    assert result.rejected_range == 18.0
    assert result.acceptance_ratio == 0.1


def test_acceptance_ratio_doji():
    """Doji (open = close)."""
    result = compute_price_acceptance_ratio(
        candle_open=100.0,
        candle_high=100.0,
        candle_low=100.0,
        candle_close=100.0
    )
    assert result.accepted_range == 0.0
    assert result.acceptance_ratio == 1.0


def test_acceptance_ratio_invalid_high():
    """Invalid: high < max(open, close)."""
    with pytest.raises(ValueError):
        compute_price_acceptance_ratio(
            candle_open=100.0,
            candle_high=99.0,
            candle_low=90.0,
            candle_close=105.0
        )


def test_central_tendency_deviation_positive():
    """Positive deviation."""
    result = compute_central_tendency_deviation(
        price=105.0,
        central_tendency=100.0
    )
    assert result.deviation_value == 5.0


def test_central_tendency_deviation_negative():
    """Negative deviation."""
    result = compute_central_tendency_deviation(
        price=95.0,
        central_tendency=100.0
    )
    assert result.deviation_value == -5.0


def test_central_tendency_deviation_zero():
    """Zero deviation."""
    result = compute_central_tendency_deviation(
        price=100.0,
        central_tendency=100.0
    )
    assert result.deviation_value == 0.0
