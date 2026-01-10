"""
Tests for M4 Zone Geometry
Per M4 Phase 1 Coding Agent Prompts - Module 3
"""

import pytest
from memory.m4_zone_geometry import (
    compute_zone_penetration_depth,
    identify_displacement_origin_anchor,
    ZonePenetrationDepth,
    DisplacementOriginAnchor
)


def test_zone_penetration_none():
    """No zone overlap returns None."""
    result = compute_zone_penetration_depth(
        zone_id="Z1",
        zone_low=100.0,
        zone_high=110.0,
        traversal_prices=[90.0, 95.0]
    )
    assert result is None


def test_zone_penetration_partial():
    """Partial penetration detected."""
    result = compute_zone_penetration_depth(
        zone_id="Z1",
        zone_low=100.0,
        zone_high=110.0,
        traversal_prices=[105.0]
    )
    assert result is not None
    assert result.zone_id == "Z1"
    assert result.penetration_depth == 5.0


def test_zone_penetration_full():
    """Full penetration."""
    result = compute_zone_penetration_depth(
        zone_id="Z1",
        zone_low=100.0,
        zone_high=110.0,
        traversal_prices=[100.0, 105.0, 110.0]
    )
    assert result is not None


def test_zone_invalid_bounds():
    """zone_low >= zone_high raises error."""
    with pytest.raises(ValueError):
        compute_zone_penetration_depth(
            zone_id="Z1",
            zone_low=110.0,
            zone_high=100.0,
            traversal_prices=[105.0]
        )


def test_anchor_dwell_time():
    """Anchor dwell time calculated."""
    result = identify_displacement_origin_anchor(
        traversal_id="T1",
        pre_traversal_prices=[100.0, 101.0, 100.5],
        pre_traversal_timestamps=[1000.0, 1001.0, 1002.0]
    )
    assert result.anchor_dwell_time == 2.0
    assert result.anchor_low == 100.0
    assert result.anchor_high == 101.0


def test_anchor_empty_sequence():
    """Empty sequence raises error."""
    with pytest.raises(ValueError):
        identify_displacement_origin_anchor(
            traversal_id="T1",
            pre_traversal_prices=[],
            pre_traversal_timestamps=[]
        )
