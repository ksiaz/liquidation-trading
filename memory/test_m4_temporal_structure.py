"""
M4 Temporal Structure Views - Unit Tests

Tests for temporal structure read model.
Validates determinism, prohibition compliance, M3 integration, and motif consistency.
"""

import pytest
from dataclasses import dataclass
from typing import Tuple, Dict
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m3_evidence_token import EvidenceToken
from memory.m3_sequence_buffer import SequenceBuffer


# Will be implemented in m4_temporal_structure.py
@dataclass
class TemporalStructureView:
    """Read-only view of temporal sequence structure at a memory node."""
    node_id: str
    avg_sequence_length: float
    token_type_count: int
    token_diversity_ratio: float
    median_token_gap_sec: float
    most_common_bigram: Tuple[EvidenceToken, EvidenceToken]
    most_common_bigram_count: int
    token_type_distribution: Dict[EvidenceToken, float]
    total_sequences_observed: int
    current_buffer_size: int


def create_test_node_with_m3(
    node_id: str = "test_node",
    tokens: list = None
) -> EnrichedLiquidityMemoryNode:
    """Create a test node with M3 sequence buffer."""
    if tokens is None:
        # Default: simple sequence
        tokens = [
            (EvidenceToken.OB_APPEAR, 1000.0),
            (EvidenceToken.TRADE_EXEC, 1100.0),
            (EvidenceToken.OB_PERSIST, 1200.0),
            (EvidenceToken.TRADE_EXEC, 1300.0),
        ]
    
    node = EnrichedLiquidityMemoryNode(
        id=node_id,
        price_center=100.0,
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
    
    # Create M3 sequence buffer
    node.sequence_buffer = SequenceBuffer(max_length=100, time_window_sec=3600.0)
    for token, ts in tokens:
        node.sequence_buffer.append(token, ts)
    
    node.total_sequences_observed = len(tokens)
    
    return node


# ==================== DETERMINISM TESTS ====================

def test_det_1_identical_input_identical_output():
    """DET-1: Same input → identical output."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3()
    current_ts = 5000.0
    
    result1 = get_temporal_structure(node, current_ts)
    result2 = get_temporal_structure(node, current_ts)
    
    assert result1 == result2
    assert result1.token_diversity_ratio == result2.token_diversity_ratio


def test_det_4_order_independence_batch():
    """DET-4: Batch queries are order-independent."""
    from memory.m4_temporal_structure import get_temporal_structure_batch
    
    node1 = create_test_node_with_m3(node_id="node1")
    node2 = create_test_node_with_m3(node_id="node2")
    node3 = create_test_node_with_m3(node_id="node3")
    current_ts = 5000.0
    
    result_a = get_temporal_structure_batch([node1, node2, node3], current_ts)
    result_b = get_temporal_structure_batch([node3, node1, node2], current_ts)
    
    assert set(result_a.keys()) == set(result_b.keys())
    for key in result_a:
        assert result_a[key] == result_b[key]


# ==================== NO-GROWTH-WITHOUT-CHANGE TESTS ====================

def test_ngc_2_memory_immutability():
    """NGC-2: Query does not modify M3 fields."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3()
    current_ts = 5000.0
    
    # Capture M3 state
    buffer_size_before = len(node.sequence_buffer.tokens)
    total_observed_before = node.total_sequences_observed
    
    # Query
    get_temporal_structure(node, current_ts)
    
    # Assert unchanged
    assert len(node.sequence_buffer.tokens) == buffer_size_before
    assert node.total_sequences_observed == total_observed_before


# ==================== PROHIBITION COMPLIANCE TESTS ====================

def test_pro_2_no_importance_fields():
    """PRO-2: No importance/ranking fields in output."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3()
    result = get_temporal_structure(node, 5000.0)
    
    result_dict = result.__dict__
    forbidden = ['importance', 'priority', 'rank', 'score', 'quality',
                 'pattern_strength', 'sequence_quality']
    
    for field in forbidden:
        assert field not in result_dict, f"Forbidden field '{field}' found"


def test_pro_4_no_directional_labels():
    """PRO-4: No directional interpretation in fields."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3()
    result = get_temporal_structure(node, 5000.0)
    
    # Field names should be neutral
    result_str = str(result.__dict__.keys()).lower()
    forbidden_terms = ['bullish', 'bearish', 'support', 'resistance', 'signal']
    
    for term in forbidden_terms:
        assert term not in result_str


# ==================== EQUIVALENCE TESTS ====================

def test_eqv_4_motif_count_consistency():
    """EQV-4: Motif counts match M3 raw data."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    tokens = [
        (EvidenceToken.OB_APPEAR, 1000.0),
        (EvidenceToken.TRADE_EXEC, 1100.0),
        (EvidenceToken.OB_APPEAR, 1200.0),
        (EvidenceToken.TRADE_EXEC, 1300.0),
    ]
    
    node = create_test_node_with_m3(tokens=tokens)
    result = get_temporal_structure(node, 2000.0)
    
    # (OB_APPEAR, TRADE_EXEC) should appear twice as a bigram
    expected_bigram = (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    assert result.most_common_bigram == expected_bigram
    assert result.most_common_bigram_count == 2


def test_eqv_token_diversity_calculation():
    """Token diversity ratio calculated correctly."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    # 3 unique token types, 6 total tokens
    tokens = [
        (EvidenceToken.OB_APPEAR, 1000.0),
        (EvidenceToken.TRADE_EXEC, 1100.0),
        (EvidenceToken.LIQ_OCCUR, 1200.0),
        (EvidenceToken.OB_APPEAR, 1300.0),
        (EvidenceToken.TRADE_EXEC, 1400.0),
        (EvidenceToken.OB_APPEAR, 1500.0),
    ]
    
    node = create_test_node_with_m3(tokens=tokens)
    result = get_temporal_structure(node, 2000.0)
    
    # Diversity = unique types / total tokens = 3 / 6 = 0.5
    assert result.token_type_count == 3
    assert abs(result.token_diversity_ratio - 0.5) < 0.001


def test_eqv_distribution_sums_to_one():
    """Token type distribution sums to 1.0."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3()
    result = get_temporal_structure(node, 5000.0)
    
    total = sum(result.token_type_distribution.values())
    assert abs(total - 1.0) < 0.001


# ==================== EDGE CASE TESTS ====================

def test_edg_empty_buffer():
    """Handle node with no M3 data."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3(tokens=[])
    result = get_temporal_structure(node, 2000.0)
    
    # Should handle gracefully
    assert result.current_buffer_size == 0
    assert result.token_type_count == 0
    assert result.token_diversity_ratio == 0.0


def test_edg_single_token():
    """Handle buffer with single token."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    tokens = [(EvidenceToken.OB_APPEAR, 1000.0)]
    node = create_test_node_with_m3(tokens=tokens)
    result = get_temporal_structure(node, 2000.0)
    
    assert result.current_buffer_size == 1
    assert result.token_type_count == 1
    assert result.token_diversity_ratio == 1.0  # 1 unique / 1 total


def test_edg_no_m3_data():
    """Handle node without M3 sequence buffer."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = EnrichedLiquidityMemoryNode(
        id="no_m3",
        price_center=100.0,
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
    # No sequence_buffer set
    
    result = get_temporal_structure(node, 5000.0)
    
    # Should return empty/zero metrics
    assert result.current_buffer_size == 0
    assert result.total_sequences_observed == 0


# ==================== FUNCTIONAL CORRECTNESS TESTS ====================

def test_complete_output_schema():
    """Verify all required fields present."""
    from memory.m4_temporal_structure import get_temporal_structure
    
    node = create_test_node_with_m3()
    result = get_temporal_structure(node, 5000.0)
    
    required_fields = [
        'node_id', 'avg_sequence_length', 'token_type_count',
        'token_diversity_ratio', 'median_token_gap_sec',
        'most_common_bigram', 'most_common_bigram_count',
        'token_type_distribution', 'total_sequences_observed',
        'current_buffer_size'
    ]
    
    for field in required_fields:
        assert hasattr(result, field), f"Missing required field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
