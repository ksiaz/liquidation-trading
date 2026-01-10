"""
Tests for M5 Tier B-2 Phase 1 Query Schemas

Validates construction, frozen dataclasses, required fields, and schema registry.
Per Tier B-2 Canon v1.0 - Phase 1
"""

import pytest
from memory.m5_query_schemas import (
    StructuralPersistenceDurationQuery,
    StructuralExposureCountQuery,
    QUERY_TYPES
)


# ==============================================================================
# Construction Validity Tests
# ==============================================================================

def test_structural_persistence_duration_construction():
    """B2.1: Valid construction."""
    query = StructuralPersistenceDurationQuery(
        node_id="N1",
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1080.0), (1090.0, 1100.0))
    )
    assert query.node_id == "N1"
    assert query.observation_start_ts == 1000.0
    assert query.observation_end_ts == 1100.0
    assert query.presence_intervals == ((1020.0, 1080.0), (1090.0, 1100.0))


def test_structural_exposure_count_construction():
    """B2.2: Valid construction."""
    query = StructuralExposureCountQuery(
        node_id="N1",
        exposure_timestamps=(1020.0, 1040.0, 1060.0),
        observation_start_ts=1000.0,
        observation_end_ts=1100.0
    )
    assert query.node_id == "N1"
    assert query.exposure_timestamps == (1020.0, 1040.0, 1060.0)
    assert query.observation_start_ts == 1000.0
    assert query.observation_end_ts == 1100.0


# ==============================================================================
# Frozen Dataclass Immutability Tests
# ==============================================================================

def test_schemas_are_frozen():
    """All Tier B-2 Phase 1 schemas must be frozen (immutable)."""
    query = StructuralPersistenceDurationQuery(
        node_id="N1",
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=()
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        query.node_id = "MODIFIED"


# ==============================================================================
# Required Field Enforcement Tests
# ==============================================================================

def test_missing_required_field_b21():
    """B2.1: Missing required fields must raise TypeError."""
    with pytest.raises(TypeError):
        StructuralPersistenceDurationQuery(
            node_id="N1",
            observation_start_ts=1000.0
            # Missing observation_end_ts, presence_intervals
        )


def test_missing_required_field_b22():
    """B2.2: Missing required fields must raise TypeError."""
    with pytest.raises(TypeError):
        StructuralExposureCountQuery(
            node_id="N1",
            exposure_timestamps=(1020.0,)
            # Missing observation_start_ts, observation_end_ts
        )


# ==============================================================================
# Schema Registry Tests
# ==============================================================================

def test_tier_b2_phase1_schemas_registered():
    """All 2 Tier B-2 Phase 1 schemas must be in QUERY_TYPES registry."""
    assert "STRUCTURAL_PERSISTENCE_DURATION" in QUERY_TYPES
    assert "STRUCTURAL_EXPOSURE_COUNT" in QUERY_TYPES


def test_registry_mapping_correct():
    """Registry must map query type strings to correct dataclass."""
    assert QUERY_TYPES["STRUCTURAL_PERSISTENCE_DURATION"] == StructuralPersistenceDurationQuery
    assert QUERY_TYPES["STRUCTURAL_EXPOSURE_COUNT"] == StructuralExposureCountQuery
