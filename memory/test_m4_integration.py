"""
M4 Integration Tests

Verifies M4 read models integrate correctly with ContinuityMemoryStore.
Tests ONLY wiring, determinism, and immutability - no semantic assertions.
"""

import pytest
from memory.m2_continuity_store import ContinuityMemoryStore
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m4_evidence_composition import get_evidence_composition
from memory.m4_interaction_density import get_interaction_density
from memory.m4_stability_transience import get_stability_metrics
from memory.m4_temporal_structure import get_temporal_structure


def create_test_node(node_id="test_node", price=100.0):
    """Create a test node."""
    return EnrichedLiquidityMemoryNode(
        id=node_id,
        price_center=price,
        price_band=0.1,
        side="both",
        first_seen_ts=1000.0,
        last_interaction_ts=2000.0,
        strength=0.8,
        confidence=0.7,
        active=True,
        decay_rate=0.0001,
        creation_reason="test"
    )


# ==================== STORE WIRING TESTS ====================

def test_store_evidence_composition_matches_direct_view():
    """Store wrapper matches direct view output."""
    store = ContinuityMemoryStore()
    node = create_test_node()
    
    # Add node via store
    store.add_or_update_node(
        node_id=node.id,
        price_center=node.price_center,
        price_band=0.1,
        side="both",
        timestamp=1000.0,
        creation_reason="test"
    )
    node_id = node.id
    
    # Get via store
    via_store = store.get_evidence_composition_view(node_id)
    
    # Get direct
    stored_node = store.get_node(node_id)
    direct = get_evidence_composition(stored_node)
    
    # Must be identical
    assert via_store == direct


def test_store_interaction_density_matches_direct_view():
    """Store wrapper matches direct view output."""
    store = ContinuityMemoryStore()
    node = create_test_node()
    
    store.add_or_update_node(
        node_id=node.id,
        price_center=node.price_center,
        price_band=0.1,
        side="both",
        timestamp=1000.0,
        creation_reason="test"
    )
    node_id = node.id
    current_ts = 5000.0
    
    via_store = store.get_interaction_density_view(node_id, current_ts)
    
    stored_node = store.get_node(node_id)
    direct = get_interaction_density(stored_node, current_ts)
    
    assert via_store == direct


def test_store_stability_metrics_matches_direct_view():
    """Store wrapper matches direct view output."""
    store = ContinuityMemoryStore()
    node = create_test_node()
    
    store.add_or_update_node(
        node_id=node.id,
        price_center=node.price_center,
        price_band=0.1,
        side="both",
        timestamp=1000.0,
        creation_reason="test"
    )
    node_id = node.id
    current_ts = 5000.0
    
    via_store = store.get_stability_metrics_view(node_id, current_ts)
    
    stored_node = store.get_node(node_id)
    direct = get_stability_metrics(stored_node, current_ts)
    
    assert via_store == direct


def test_store_temporal_structure_matches_direct_view():
    """Store wrapper matches direct view output."""
    store = ContinuityMemoryStore()
    node = create_test_node()
    
    store.add_or_update_node(
        node_id=node.id,
        price_center=node.price_center,
        price_band=0.1,
        side="both",
        timestamp=1000.0,
        creation_reason="test"
    )
    node_id = node.id
    current_ts = 5000.0
    
    via_store = store.get_temporal_structure_view(node_id, current_ts)
    
    stored_node = store.get_node(node_id)
    direct = get_temporal_structure(stored_node, current_ts)
    
    assert via_store == direct


# ==================== DETERMINISM TESTS ====================

def test_store_wrapper_determinism():
    """Store wrappers are deterministic."""
    store = ContinuityMemoryStore()
    
    store.add_or_update_node(
        node_id="100.0_both",
        price_center=100.0,
        price_band=0.1,
        side="both",
        timestamp=1000.0,
        creation_reason="test"
    )
    node_id = "100.0_both"
    current_ts = 5000.0
    
    # Call multiple times
    result1 = store.get_evidence_composition_view(node_id)
    result2 = store.get_evidence_composition_view(node_id)    
    assert result1 == result2
    
    result3 = store.get_interaction_density_view(node_id, current_ts)
    result4 = store.get_interaction_density_view(node_id, current_ts)
    assert result3 == result4


# ==================== IMMUTABILITY TESTS ====================

def test_store_wrappers_do_not_modify_nodes():
    """M4 queries via store don't modify M2/M3."""
    store = ContinuityMemoryStore()
    
    store.add_or_update_node(
        node_id="100.0_both",
        price_center=100.0,
        price_band=0.1,
        side="both",
        timestamp=1000.0,
        creation_reason="test"
    )
    node_id = "100.0_both"
    current_ts = 5000.0
    
    # Capture state
    node = store.get_node(node_id)
    strength_before = node.strength
    active_before = node.active
    
    # Query all M4 views
    store.get_evidence_composition_view(node_id)
    store.get_interaction_density_view(node_id, current_ts)
    store.get_stability_metrics_view(node_id, current_ts)
    store.get_temporal_structure_view(node_id, current_ts)
    
    # Assert unchanged
    assert node.strength == strength_before
    assert node.active == active_before


# ==================== NULL HANDLING ====================

def test_store_returns_none_for_missing_nodes():
    """Store returns None for non-existent nodes."""
    store = ContinuityMemoryStore()
    
    assert store.get_evidence_composition_view("nonexistent") is None
    assert store.get_interaction_density_view("nonexistent", 5000.0) is None
    assert store.get_stability_metrics_view("nonexistent", 5000.0) is None
    assert store.get_temporal_structure_view("nonexistent", 5000.0) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
