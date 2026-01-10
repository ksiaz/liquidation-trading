"""
Tests for M5 Tier A Query Schemas

Validates construction, frozen dataclasses, required fields, and schema registry.
Per M5 Whitelist Spec v1.0
"""

import pytest
from memory.m5_query_schemas import (
    StructuralBoundaryViolationQuery,
    StructuralConversionFailureQuery,
    PriceTraversalVelocityQuery,
    TraversalCompactnessQuery,
    PriceAcceptanceRatioQuery,
    ZonePenetrationDepthQuery,
    DisplacementOriginAnchorQuery,
    CentralTendencyDeviationQuery,
    QUERY_TYPES
)


# ==============================================================================
# Construction Validity Tests
# ==============================================================================

def test_structural_boundary_violation_construction():
    """A1: Valid construction."""
    query = StructuralBoundaryViolationQuery(
        node_id="N1",
        boundary_low=100.0,
        boundary_high=110.0,
        window_start_ts=1000.0,
        window_end_ts=1010.0
    )
    assert query.node_id == "N1"
    assert query.boundary_low == 100.0


def test_structural_conversion_failure_construction():
    """A2: Valid construction."""
    query = StructuralConversionFailureQuery(
        node_id="N1",
        observation_start_ts=1000.0,
        observation_end_ts=1010.0,
        conversion_window=5.0
    )
    assert query.node_id == "N1"
    assert query.conversion_window == 5.0


def test_price_traversal_velocity_construction():
    """A3: Valid construction."""
    query = PriceTraversalVelocityQuery(
        node_id="N1",
        start_price=100.0,
        end_price=110.0,
        start_ts=1000.0,
        end_ts=1010.0
    )
    assert query.start_price == 100.0
    assert query.end_price == 110.0


def test_traversal_compactness_construction():
    """A4: Valid construction."""
    query = TraversalCompactnessQuery(
        node_id="N1",
        price_sequence=(100.0, 105.0, 110.0),
        timestamp_sequence=(1000.0, 1005.0, 1010.0)
    )
    assert len(query.price_sequence) == 3


def test_price_acceptance_ratio_construction():
    """A5: Valid construction."""
    query = PriceAcceptanceRatioQuery(
        node_id="N1",
        open_price=100.0,
        high_price=110.0,
        low_price=95.0,
        close_price=105.0
    )
    assert query.open_price == 100.0


def test_zone_penetration_depth_construction():
    """A6: Valid construction."""
    query = ZonePenetrationDepthQuery(
        node_id="N1",
        zone_low=100.0,
        zone_high=110.0,
        observed_low=102.0,
        observed_high=108.0
    )
    assert query.zone_low == 100.0


def test_displacement_origin_anchor_construction():
    """A7: Valid construction."""
    query = DisplacementOriginAnchorQuery(
        node_id="N1",
        price_sequence=(100.0, 101.0),
        timestamp_sequence=(1000.0, 1001.0)
    )
    assert len(query.price_sequence) == 2


def test_central_tendency_deviation_construction():
    """A8: Valid construction."""
    query = CentralTendencyDeviationQuery(
        node_id="N1",
        reference_price=105.0,
        central_price=100.0
    )
    assert query.reference_price == 105.0


# ==============================================================================
# Frozen Dataclass Immutability Tests
# ==============================================================================

def test_schemas_are_frozen():
    """All Tier A schemas must be frozen (immutable)."""
    query = StructuralBoundaryViolationQuery(
        node_id="N1",
        boundary_low=100.0,
        boundary_high=110.0,
        window_start_ts=1000.0,
        window_end_ts=1010.0
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        query.node_id = "MODIFIED"


# ==============================================================================
# Required Field Enforcement Tests
# ==============================================================================

def test_missing_required_field():
    """Missing required fields must raise TypeError."""
    with pytest.raises(TypeError):
        StructuralBoundaryViolationQuery(
            node_id="N1",
            boundary_low=100.0
            # Missing boundary_high, window_start_ts, window_end_ts
        )


# ==============================================================================
# Schema Registry Tests
# ==============================================================================

def test_tier_a_schemas_registered():
    """All 8 Tier A schemas must be in QUERY_TYPES registry."""
    assert "STRUCTURAL_BOUNDARY_VIOLATION" in QUERY_TYPES
    assert "STRUCTURAL_CONVERSION_FAILURE" in QUERY_TYPES
    assert "PRICE_TRAVERSAL_VELOCITY" in QUERY_TYPES
    assert "TRAVERSAL_COMPACTNESS" in QUERY_TYPES
    assert "PRICE_ACCEPTANCE_RATIO" in QUERY_TYPES
    assert "ZONE_PENETRATION_DEPTH" in QUERY_TYPES
    assert "DISPLACEMENT_ORIGIN_ANCHOR" in QUERY_TYPES
    assert "CENTRAL_TENDENCY_DEVIATION" in QUERY_TYPES


def test_registry_mapping_correct():
    """Registry must map query type strings to correct dataclass."""
    assert QUERY_TYPES["STRUCTURAL_BOUNDARY_VIOLATION"] == StructuralBoundaryViolationQuery
    assert QUERY_TYPES["PRICE_TRAVERSAL_VELOCITY"] == PriceTraversalVelocityQuery
    assert QUERY_TYPES["ZONE_PENETRATION_DEPTH"] == ZonePenetrationDepthQuery
