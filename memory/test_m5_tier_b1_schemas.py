"""
Tests for M5 Tier B-1 Query Schemas

Validates construction, frozen dataclasses, required fields, and schema registry.
Per Tier B Canon v1.0 - Phase B-1
"""

import pytest
from memory.m5_query_schemas import (
    StructuralAbsenceDurationQuery,
    TraversalVoidSpanQuery,
    EventNonOccurrenceCounterQuery,
    QUERY_TYPES
)


# ==============================================================================
# Construction Validity Tests
# ==============================================================================

def test_structural_absence_duration_construction():
    """B1.1: Valid construction."""
    query = StructuralAbsenceDurationQuery(
        node_id="N1",
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        presence_intervals=((1020.0, 1080.0),)
    )
    assert query.node_id == "N1"
    assert query.observation_start_ts == 1000.0
    assert query.presence_intervals == ((1020.0, 1080.0),)


def test_traversal_void_span_construction():
    """B1.2: Valid construction."""
    query = TraversalVoidSpanQuery(
        node_id="N1",
        observation_start_ts=1000.0,
        observation_end_ts=1100.0,
        traversal_timestamps=(1020.0, 1040.0, 1080.0)
    )
    assert query.node_id == "N1"
    assert query.traversal_timestamps == (1020.0, 1040.0, 1080.0)


def test_event_non_occurrence_counter_construction():
    """B1.3: Valid construction."""
    query = EventNonOccurrenceCounterQuery(
        node_id="N1",
        expected_event_ids=("E1", "E2", "E3"),
        observed_event_ids=("E1", "E3")
    )
    assert query.node_id == "N1"
    assert query.expected_event_ids == ("E1", "E2", "E3")
    assert query.observed_event_ids == ("E1", "E3")


# ==============================================================================
# Frozen Dataclass Immutability Tests
# ==============================================================================

def test_schemas_are_frozen():
    """All Tier B-1 schemas must be frozen (immutable)."""
    query = StructuralAbsenceDurationQuery(
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

def test_missing_required_field_b11():
    """B1.1: Missing required fields must raise TypeError."""
    with pytest.raises(TypeError):
        StructuralAbsenceDurationQuery(
            node_id="N1",
            observation_start_ts=1000.0
            # Missing observation_end_ts, presence_intervals
        )


def test_missing_required_field_b12():
    """B1.2: Missing required fields must raise TypeError."""
    with pytest.raises(TypeError):
        TraversalVoidSpanQuery(
            node_id="N1",
            observation_start_ts=1000.0
            # Missing observation_end_ts, traversal_timestamps
        )


def test_missing_required_field_b13():
    """B1.3: Missing required fields must raise TypeError."""
    with pytest.raises(TypeError):
        EventNonOccurrenceCounterQuery(
            node_id="N1",
            expected_event_ids=("E1",)
            # Missing observed_event_ids
        )


# ==============================================================================
# Schema Registry Tests
# ==============================================================================

def test_tier_b1_schemas_registered():
    """All 3 Tier B-1 schemas must be in QUERY_TYPES registry."""
    assert "STRUCTURAL_ABSENCE_DURATION" in QUERY_TYPES
    assert "TRAVERSAL_VOID_SPAN" in QUERY_TYPES
    assert "EVENT_NON_OCCURRENCE_COUNTER" in QUERY_TYPES


def test_registry_mapping_correct():
    """Registry must map query type strings to correct dataclass."""
    assert QUERY_TYPES["STRUCTURAL_ABSENCE_DURATION"] == StructuralAbsenceDurationQuery
    assert QUERY_TYPES["TRAVERSAL_VOID_SPAN"] == TraversalVoidSpanQuery
    assert QUERY_TYPES["EVENT_NON_OCCURRENCE_COUNTER"] == EventNonOccurrenceCounterQuery
