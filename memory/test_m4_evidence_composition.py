"""
M4 Evidence Composition Views - Unit Tests

Tests for evidence composition read model.
Validates determinism, prohibition compliance, and equivalence to raw M2 data.
"""

import pytest
from dataclasses import dataclass
from typing import Dict
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


# Will be implemented in m4_evidence_composition.py
@dataclass
class EvidenceCompositionView:
    """Read-only view of evidence composition at a memory node."""
    node_id: str
    orderbook_count: int
    trade_count: int
    liquidation_count: int
    orderbook_ratio: float
    trade_ratio: float
    liquidation_ratio: float
    buyer_volume_usd: float
    seller_volume_usd: float
    total_volume_usd: float
    passive_fill_ratio: float
    aggressive_fill_ratio: float
    dominant_evidence_type: str


def create_test_node(
    node_id: str = "test_node",
    orderbook_count: int = 10,
    trade_count: int = 20,
    liquidation_count: int = 5,
    buyer_volume: float = 10000.0,
    seller_volume: float = 15000.0,
    passive_volume: float = 12000.0,
    aggressive_volume: float = 13000.0
) -> EnrichedLiquidityMemoryNode:
    """Create a test node with specified evidence."""
    node = EnrichedLiquidityMemoryNode(
        id=node_id,
        price_center=100.0,
        price_band=0.1,
        side="both",
        first_seen_ts=1000.0,
        last_interaction_ts=1100.0,
        strength=0.8,
        confidence=0.7,
        active=True,
        decay_rate=0.0001,
        creation_reason="test"
    )
    
    # Set evidence counts
    node.orderbook_appearance_count = orderbook_count
    node.trade_execution_count = trade_count
    node.liquidation_proximity_count = liquidation_count
    node.interaction_count = orderbook_count + trade_count + liquidation_count
    
    # Set volume
    node.buyer_initiated_volume = buyer_volume
    node.seller_initiated_volume = seller_volume
    node.volume_total = buyer_volume + seller_volume
    node.passive_fill_volume = passive_volume
    node.aggressive_fill_volume = aggressive_volume
    
    return node


# ==================== DETERMINISM TESTS ====================

def test_det_1_identical_input_identical_output():
    """DET-1: Same input → identical output."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node()
    
    # Call twice with same node
    result1 = get_evidence_composition(node)
    result2 = get_evidence_composition(node)
    
    # Must be exactly equal
    assert result1 == result2
    assert result1.node_id == result2.node_id
    assert result1.orderbook_count == result2.orderbook_count
    assert result1.orderbook_ratio == result2.orderbook_ratio


def test_det_2_recomputation_consistency():
    """DET-2: Repeated calls produce identical results."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node(orderbook_count=15, trade_count=30, liquidation_count=5)
    
    results = [get_evidence_composition(node) for _ in range(10)]
    
    # All results must be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


# ==================== NO-GROWTH-WITHOUT-CHANGE TESTS ====================

def test_ngc_2_memory_immutability():
    """NGC-2: Query does not modify M2 fields."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node()
    
    # Capture state before
    orderbook_before = node.orderbook_appearance_count
    trade_before = node.trade_execution_count
    volume_before = node.volume_total
    
    # Query
    get_evidence_composition(node)
    
    # Assert unchanged
    assert node.orderbook_appearance_count == orderbook_before
    assert node.trade_execution_count == trade_before
    assert node.volume_total == volume_before


# ==================== PROHIBITION COMPLIANCE TESTS ====================

def test_pro_2_no_importance_fields():
    """PRO-2: No importance/ranking fields in output."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node()
    result = get_evidence_composition(node)
    
    # Check no forbidden fields
    result_dict = result.__dict__
    forbidden = ['importance', 'priority', 'rank', 'score', 'quality', 
                 'strength_score', 'reliability', 'confidence']
    
    for field in forbidden:
        assert field not in result_dict, f"Forbidden field '{field}' found"


def test_pro_4_no_directional_labels():
    """PRO-4: No directional labels in output."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node()
    result = get_evidence_composition(node)
    
    # Check dominant_evidence_type uses neutral terms
    assert result.dominant_evidence_type in ['orderbook', 'trade', 'liquidation']
    
    # Check for forbidden INTERPRETIVE terms (NOT execution-side data)
    # NOTE: buyer_volume_usd/seller_volume_usd are factual execution-side data (ALLOWED)
    forbidden_terms = ['support', 'resistance', 'bullish', 'bearish', 'buy_zone', 'sell_zone',
                      'buy_pressure', 'sell_pressure', 'buy_signal', 'sell_signal']
    
    # Check field names and dominant_evidence_type only (not entire string repr)
    fields_to_check = [result.dominant_evidence_type, result.node_id]
    combined_str = ' '.join(str(f) for f in fields_to_check).lower()
    
    for term in forbidden_terms:
        assert term not in combined_str, f"Forbidden term '{term}' found"


# ==================== EQUIVALENCE TESTS ====================

def test_eqv_2_ratio_calculation_correctness():
    """EQV-2: Ratios correctly represent raw proportions."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node(orderbook_count=10, trade_count=20, liquidation_count=5)
    # Total = 35
    
    result = get_evidence_composition(node)
    
    # Verify ratios
    assert abs(result.orderbook_ratio - (10 / 35)) < 0.0001
    assert abs(result.trade_ratio - (20 / 35)) < 0.0001
    assert abs(result.liquidation_ratio - (5 / 35)) < 0.0001
    
    # Ratios should sum to 1.0
    total_ratio = result.orderbook_ratio + result.trade_ratio + result.liquidation_ratio
    assert abs(total_ratio - 1.0) < 0.0001


def test_eqv_volume_accuracy():
    """Volume fields must match raw M2 values exactly."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    buyer_vol = 12345.67
    seller_vol = 23456.78
    
    node = create_test_node(buyer_volume=buyer_vol, seller_volume=seller_vol)
    result = get_evidence_composition(node)
    
    assert result.buyer_volume_usd == buyer_vol
    assert result.seller_volume_usd == seller_vol
    assert result.total_volume_usd == buyer_vol + seller_vol


def test_eqv_fill_ratio_correctness():
    """Fill ratios correctly represent raw proportions."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    passive = 10000.0
    aggressive = 15000.0
    
    node = create_test_node(passive_volume=passive, aggressive_volume=aggressive)
    result = get_evidence_composition(node)
    
    total = passive + aggressive
    assert abs(result.passive_fill_ratio - (passive / total)) < 0.0001
    assert abs(result.aggressive_fill_ratio - (aggressive / total)) < 0.0001
    
    # Ratios sum to 1.0
    assert abs(result.passive_fill_ratio + result.aggressive_fill_ratio - 1.0) < 0.0001


# ==================== EDGE CASE TESTS ====================

def test_edg_1_zero_interactions():
    """EDG-1: Handle node with zero interactions gracefully."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node(orderbook_count=0, trade_count=0, liquidation_count=0)
    result = get_evidence_composition(node)
    
    # Should return zeros, not errors
    assert result.orderbook_count == 0
    assert result.trade_count == 0
    assert result.liquidation_count == 0
    
    # Ratios should be 0.0 (or NaN handled gracefully)
    assert result.orderbook_ratio == 0.0
    assert result.trade_ratio == 0.0
    assert result.liquidation_ratio == 0.0


def test_edg_2_single_evidence_type():
    """EDG-2: Handle single evidence type domination."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    # Only trades
    node = create_test_node(orderbook_count=0, trade_count=100, liquidation_count=0)
    result = get_evidence_composition(node)
    
    assert result.trade_ratio == 1.0
    assert result.orderbook_ratio == 0.0
    assert result.liquidation_ratio == 0.0
    assert result.dominant_evidence_type == 'trade'


def test_edg_zero_volume():
    """Handle zero volume gracefully."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node(
        buyer_volume=0.0,
        seller_volume=0.0,
        passive_volume=0.0,
        aggressive_volume=0.0
    )
    result = get_evidence_composition(node)
    
    assert result.total_volume_usd == 0.0
    assert result.passive_fill_ratio == 0.0
    assert result.aggressive_fill_ratio == 0.0


# ==================== FUNCTIONAL CORRECTNESS TESTS ====================

def test_dominant_evidence_determination():
    """Dominant evidence type correctly identified."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    # Orderbook dominant
    node1 = create_test_node(orderbook_count=100, trade_count=20, liquidation_count=5)
    result1 = get_evidence_composition(node1)
    assert result1.dominant_evidence_type == 'orderbook'
    
    # Liquidation dominant
    node2 = create_test_node(orderbook_count=5, trade_count=10, liquidation_count=50)
    result2 = get_evidence_composition(node2)
    assert result2.dominant_evidence_type == 'liquidation'


def test_complete_output_schema():
    """Verify all required fields present."""
    from memory.m4_evidence_composition import get_evidence_composition
    
    node = create_test_node()
    result = get_evidence_composition(node)
    
    # All fields must be present
    required_fields = [
        'node_id', 'orderbook_count', 'trade_count', 'liquidation_count',
        'orderbook_ratio', 'trade_ratio', 'liquidation_ratio',
        'buyer_volume_usd', 'seller_volume_usd', 'total_volume_usd',
        'passive_fill_ratio', 'aggressive_fill_ratio', 'dominant_evidence_type'
    ]
    
    for field in required_fields:
        assert hasattr(result, field), f"Missing required field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
