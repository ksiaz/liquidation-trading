"""
M4 Cross-Node Context Views - Unit Tests

Tests for cross-node aggregation read model.
Validates determinism, prohibition compliance, and aggregation accuracy.
"""

import pytest
from dataclasses import dataclass
from typing import List, Tuple
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m3_evidence_token import EvidenceToken


# Will be implemented in m4_cross_node_context.py
@dataclass
class CrossNodeContextView:
    """Read-only view of cross-node context in a price range."""
    price_range_start: float
    price_range_end: float
    node_count: int
    node_density_per_dollar: float
    avg_node_spacing: float
    min_node_spacing: float
    max_node_spacing: float
    clustered_node_count: int
    isolated_node_count: int
    cluster_count: int
    avg_cluster_size: float
    total_active_nodes: int
    total_dormant_nodes: int
    shared_motif_count: int
    nodes_with_shared_motifs: int


def create_test_nodes(prices: List[float], active_states: List[bool] = None) -> List[EnrichedLiquidityMemoryNode]:
    """Create test nodes at specified prices."""
    if active_states is None:
        active_states = [True] * len(prices)
    
    nodes = []
    for i, (price, is_active) in enumerate(zip(prices, active_states)):
        node = EnrichedLiquidityMemoryNode(
            id=f"node_{i}",
            price_center=price,
            price_band=0.1,
            side="both",
            first_seen_ts=1000.0,
            last_interaction_ts=2000.0,
            strength=0.8 if is_active else 0.0,
            confidence=0.7,
            active=is_active,
            decay_rate=0.0001,
            creation_reason="test"
        )
        nodes.append(node)
    
    return nodes


# ==================== DETERMINISM TESTS ====================

def test_det_1_identical_input_identical_output():
    """DET-1: Same input → identical output."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    prices = [100.0, 100.1, 100.2, 100.5, 101.0]
    nodes = create_test_nodes(prices)
    current_ts = 5000.0
    
    result1 = get_cross_node_context(100.0, 101.0, nodes, current_ts)
    result2 = get_cross_node_context(100.0, 101.0, nodes, current_ts)
    
    assert result1 == result2
    assert result1.node_count == result2.node_count


# ==================== NO-GROWTH-WITHOUT-CHANGE TESTS ====================

def test_ngc_2_memory_immutability():
    """NGC-2: Query does not modify nodes."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    prices = [100.0, 100.5, 101.0]
    nodes = create_test_nodes(prices)
    current_ts = 5000.0
    
    # Capture state
    prices_before = [n.price_center for n in nodes]
    strengths_before = [n.strength for n in nodes]
    
    # Query
    get_cross_node_context(100.0, 101.0, nodes, current_ts)
    
    # Assert unchanged
    assert [n.price_center for n in nodes] == prices_before
    assert [n.strength for n in nodes] == strengths_before


# ==================== PROHIBITION COMPLIANCE TESTS ====================

def test_pro_2_no_importance_fields():
    """PRO-2: No importance/ranking fields in output."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    nodes = create_test_nodes([100.0, 100.5])
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    result_dict = result.__dict__
    forbidden = ['importance', 'priority', 'rank', 'score', 'quality',
                 'zone_strength', 'level_importance']
    
    for field in forbidden:
        assert field not in result_dict, f"Forbidden field '{field}' found"


def test_pro_4_no_directional_labels():
    """PRO-4: No support/resistance labels."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    nodes = create_test_nodes([100.0, 100.5])
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    result_str = str(result.__dict__).lower()
    forbidden_terms = ['support', 'resistance', 'bullish', 'bearish']
    
    for term in forbidden_terms:
        assert term not in result_str


# ==================== EQUIVALENCE TESTS ====================

def test_eqv_1_count_aggregation_accuracy():
    """EQV-1: Node count matches actual nodes in range."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    prices = [99.0, 100.0, 100.5, 101.0, 102.0]  # 3 in [100, 101]
    nodes = create_test_nodes(prices)
    
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    # Should count 100.0, 100.5, 101.0 = 3 nodes
    assert result.node_count == 3


def test_eqv_density_calculation():
    """Density calculated correctly."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    prices = [100.0, 100.2, 100.4, 100.6, 100.8]
    nodes = create_test_nodes(prices)
    
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    # 5 nodes / 1 dollar range = 5 nodes per dollar
    assert abs(result.node_density_per_dollar - 5.0) < 0.001


def test_eqv_spacing_statistics():
    """Spacing statistics calculated correctly."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    prices = [100.0, 100.1, 100.3]  # Gaps: 0.1, 0.2
    nodes = create_test_nodes(prices)
    
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    assert abs(result.min_node_spacing - 0.1) < 0.001
    assert abs(result.max_node_spacing - 0.2) < 0.001
    assert abs(result.avg_node_spacing - 0.15) < 0.001


# ==================== EDGE CASE TESTS ====================

def test_edg_1_empty_range():
    """Handle empty price range gracefully."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    nodes = create_test_nodes([99.0, 102.0])  # None in [100, 101]
    
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    assert result.node_count == 0
    assert result.node_density_per_dollar == 0.0


def test_edg_single_node():
    """Handle single node in range."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    nodes = create_test_nodes([100.5])
    
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    assert result.node_count == 1
    # No spacing for single node
    assert result.avg_node_spacing == 0.0


def test_edg_state_distribution():
    """State distribution calculated correctly."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    prices = [100.0, 100.2, 100.4, 100.6]
    active_states = [True, False, True, False]
    nodes = create_test_nodes(prices, active_states)
    
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    assert result.total_active_nodes == 2
    assert result.total_dormant_nodes == 2


# ==================== FUNCTIONAL CORRECTNESS TESTS ====================

def test_complete_output_schema():
    """Verify all required fields present."""
    from memory.m4_cross_node_context import get_cross_node_context
    
    nodes =create_test_nodes([100.0, 100.5])
    result = get_cross_node_context(100.0, 101.0, nodes, 5000.0)
    
    required_fields = [
        'price_range_start', 'price_range_end', 'node_count',
        'node_density_per_dollar', 'avg_node_spacing',
        'min_node_spacing', 'max_node_spacing',
        'clustered_node_count', 'isolated_node_count',
        'cluster_count', 'avg_cluster_size',
        'total_active_nodes', 'total_dormant_nodes',
        'shared_motif_count', 'nodes_with_shared_motifs'
    ]
    
    for field in required_fields:
        assert hasattr(result, field), f"Missing required field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
