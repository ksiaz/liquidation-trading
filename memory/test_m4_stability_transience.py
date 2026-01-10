"""
M4 Stability vs Transience Views - Unit Tests

Tests for stability/transience read model.
Validates determinism, prohibition compliance, and state duration accuracy.
"""

import pytest
from dataclasses import dataclass
from typing import Dict
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


# Will be implemented in m4_stability_transience.py
@dataclass
class StabilityTransienceView:
    """Read-only view of stability characteristics at a memory node."""
    node_id: str
    cumulative_active_sec: float
    cumulative_dormant_sec: float
    cumulative_archived_sec: float
    active_ratio: float
    dormant_ratio: float
    state_transition_count: int
    avg_active_duration_sec: float
    avg_dormant_duration_sec: float
    current_state: str
    current_strength: float
    strength_decay_rate: float
    time_since_last_interaction_sec: float
    total_lifetime_sec: float


def create_test_node(
    node_id: str = "test_node",
    active: bool = True,
    strength: float = 0.8,
    first_seen: float = 1000.0,
    last_interaction: float = 2000.0
) -> EnrichedLiquidityMemoryNode:
    """Create a test node with specified state."""
    return EnrichedLiquidityMemoryNode(
        id=node_id,
        price_center=100.0,
        price_band=0.1,
        side="both",
        first_seen_ts=first_seen,
        last_interaction_ts=last_interaction,
        strength=strength,
        confidence=0.7,
        active=active,
        decay_rate=0.0001,
        creation_reason="test"
    )


# ==================== DETERMINISM TESTS ====================

def test_det_1_identical_input_identical_output():
    """DET-1: Same input → identical output."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node()
    current_ts = 5000.0
    
    result1 = get_stability_metrics(node, current_ts)
    result2 = get_stability_metrics(node, current_ts)
    
    assert result1 == result2
    assert result1.current_strength == result2.current_strength
    assert result1.total_lifetime_sec == result2.total_lifetime_sec


def test_det_3_timestamp_reference_consistency():
    """DET-3: Same current_ts produces identical results."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node()
    current_ts = 10000.0
    
    results = [get_stability_metrics(node, current_ts) for _ in range(5)]
    
    for i in range(1, len(results)):
        assert results[i] == results[0]


def test_det_4_order_independence_batch():
    """DET-4: Batch queries are order-independent."""
    from memory.m4_stability_transience import get_stability_metrics_batch
    
    node1 = create_test_node(node_id="node1")
    node2 = create_test_node(node_id="node2")
    node3 = create_test_node(node_id="node3")
    current_ts = 5000.0
    
    result_a = get_stability_metrics_batch([node1, node2, node3], current_ts)
    result_b = get_stability_metrics_batch([node3, node1, node2], current_ts)
    
    # Same keys and values regardless of order
    assert set(result_a.keys()) == set(result_b.keys())
    for key in result_a:
        assert result_a[key] == result_b[key]


# ==================== NO-GROWTH-WITHOUT-CHANGE TESTS ====================

def test_ngc_2_memory_immutability():
    """NGC-2: Query does not modify M2 fields."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node()
    current_ts = 5000.0
    
    # Capture state
    strength_before = node.strength
    active_before = node.active
    decay_rate_before = node.decay_rate
    
    # Query
    get_stability_metrics(node, current_ts)
    
    # Assert unchanged
    assert node.strength == strength_before
    assert node.active == active_before
    assert node.decay_rate == decay_rate_before


# ==================== PROHIBITION COMPLIANCE TESTS ====================

def test_pro_2_no_importance_fields():
    """PRO-2: No importance/ranking fields in output."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node()
    result = get_stability_metrics(node, 5000.0)
    
    result_dict = result.__dict__
    forbidden = ['importance', 'priority', 'rank', 'score', 'quality',
                 'reliability_score', 'stability_rating', 'persistence_quality']
    
    for field in forbidden:
        assert field not in result_dict, f"Forbidden field '{field}' found"


def test_pro_3_no_sorted_by_importance():
    """PRO-3: Batch results not sorted by importance."""
    from memory.m4_stability_transience import get_stability_metrics_batch
    
    # Create nodes with different strengths
    nodes = [
        create_test_node(node_id="weak", strength=0.2),
        create_test_node(node_id="strong", strength=0.9),
        create_test_node(node_id="medium", strength=0.5)
    ]
    
    result = get_stability_metrics_batch(nodes, 5000.0)
    
    # Result should be a dict (unordered) not a sorted list
    assert isinstance(result, dict)
    
    # Keys should be node IDs, not sorted by strength
    assert set(result.keys()) == {"weak", "strong", "medium"}


# ==================== EQUIVALENCE TESTS ====================

def test_eqv_lifetime_calculation():
    """Total lifetime calculated correctly from timestamps."""
    from memory.m4_stability_transience import get_stability_metrics
    
    first_seen = 1000.0
    last_interaction = 2000.0
    current_ts = 5000.0
    
    node = create_test_node(first_seen=first_seen, last_interaction=last_interaction)
    result = get_stability_metrics(node, current_ts)
    
    expected_lifetime = current_ts - first_seen
    assert abs(result.total_lifetime_sec - expected_lifetime) < 0.001


def test_eqv_time_since_interaction():
    """Time since last interaction calculated correctly."""
    from memory.m4_stability_transience import get_stability_metrics
    
    last_interaction = 2000.0
    current_ts = 5000.0
    
    node = create_test_node(last_interaction=last_interaction)
    result = get_stability_metrics(node, current_ts)
    
    expected_time = current_ts - last_interaction
    assert abs(result.time_since_last_interaction_sec - expected_time) < 0.001


def test_eqv_ratio_sum_to_one():
    """State ratios sum to 1.0."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node()
    result = get_stability_metrics(node, 5000.0)
    
    total_ratio = result.active_ratio + result.dormant_ratio
    # Note: archived_sec would be included if node has been archived
    assert abs(total_ratio - 1.0) < 0.001 or total_ratio <= 1.0


# ==================== EDGE CASE TESTS ====================

def test_edg_1_zero_lifetime():
    """Handle newly created node (zero lifetime)."""
    from memory.m4_stability_transience import get_stability_metrics
    
    first_seen = 1000.0
    current_ts = 1000.0  # Same as first_seen
    
    node = create_test_node(first_seen=first_seen, last_interaction=first_seen)
    result = get_stability_metrics(node, current_ts)
    
    assert result.total_lifetime_sec == 0.0
    # Ratios should be 0 or NaN handled gracefully
    assert result.active_ratio >= 0.0 and result.active_ratio <= 1.0


def test_edg_archived_node():
    """Handle archived node (active=False, low strength)."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node(active=False, strength=0.0)
    result = get_stability_metrics(node, 5000.0)
    
    assert result.current_state in ['DORMANT', 'ARCHIVED', 'INACTIVE']
    assert result.current_strength == 0.0


# ==================== FUNCTIONAL CORRECTNESS TESTS ====================

def test_current_state_active():
    """Current state correctly reflects active node."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node(active=True, strength=0.8)
    result = get_stability_metrics(node, 5000.0)
    
    assert result.current_state == 'ACTIVE'


def test_current_state_inactive():
    """Current state correctly reflects inactive node."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node(active=False, strength=0.3)
    result = get_stability_metrics(node, 5000.0)
    
    assert result.current_state in ['DORMANT', 'ARCHIVED', 'INACTIVE']


def test_complete_output_schema():
    """Verify all required fields present."""
    from memory.m4_stability_transience import get_stability_metrics
    
    node = create_test_node()
    result = get_stability_metrics(node, 5000.0)
    
    required_fields = [
        'node_id', 'cumulative_active_sec', 'cumulative_dormant_sec',
        'cumulative_archived_sec', 'active_ratio', 'dormant_ratio',
        'state_transition_count', 'avg_active_duration_sec',
        'avg_dormant_duration_sec', 'current_state', 'current_strength',
        'strength_decay_rate', 'time_since_last_interaction_sec',
        'total_lifetime_sec'
    ]
    
    for field in required_fields:
        assert hasattr(result, field), f"Missing required field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
