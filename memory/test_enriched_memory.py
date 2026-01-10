"""
Test enriched memory node functionality.
"""

import sys
sys.path.append('d:/liquidation-trading')

from memory import EnrichedLiquidityMemoryNode


def test_enriched_node_creation():
    """Test creating enriched node."""
    node = EnrichedLiquidityMemoryNode(
        id="test1",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.5,
        confidence=0.6,
        creation_reason="executed_liquidity",
        decay_rate=0.0001,
        active=True
    )
    
    assert node.interaction_count == 0
    assert node.volume_total == 0.0
    assert node.buyer_initiated_volume == 0.0
    
    print("✓ test_enriched_node_creation passed")


def test_trade_evidence_accumulation():
    """Test recording trade evidence."""
    node = EnrichedLiquidityMemoryNode(
        id="test2",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.5,
        confidence=0.6,
        creation_reason="executed_liquidity",
        decay_rate=0.0001,
        active=True
    )
    
    # Record buyer-initiated trade
    node.record_trade_execution(1010.0, 5000.0, is_buyer_maker=False)
    
    assert node.trade_execution_count == 1
    assert node.interaction_count == 1
    assert node.volume_total == 5000.0
    assert node.buyer_initiated_volume == 5000.0
    assert node.seller_initiated_volume == 0.0
    assert node.volume_largest_event == 5000.0
    
    # Record seller-initiated trade
    node.record_trade_execution(1020.0, 3000.0, is_buyer_maker=True)
    
    assert node.trade_execution_count == 2
    assert node.interaction_count == 2
    assert node.volume_total == 8000.0
    assert node.buyer_initiated_volume == 5000.0
    assert node.seller_initiated_volume == 3000.0
    
    print("✓ test_trade_evidence_accumulation passed")


def test_liquidation_evidence():
    """Test recording liquidation evidence."""
    node = EnrichedLiquidityMemoryNode(
        id="test3",
        price_center=2.05,
        price_band=0.002,
        side="both",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.5,
        confidence=0.5,
        creation_reason="liquidation_interaction",
        decay_rate=0.0001,
        active=True
    )
    
    # Record long liquidation
    node.record_liquidation(1010.0, "BUY")
    assert node.long_liquidations == 1
    assert node.short_liquidations == 0
    assert node.liquidations_within_band == 1
    
   # Record short liquidation
    node.record_liquidation(1015.0, "SELL")
    assert node.long_liquidations == 1
    assert node.short_liquidations == 1
    assert node.liquidations_within_band == 2
    
    # Test cascade detection (close together)
    node.record_liquidation(1016.0, "SELL")
    node.record_liquidation(1017.0, "SELL")
    
    assert node.max_liquidation_cascade_size >= 3
    
    print("✓ test_liquidation_evidence passed")


def test_temporal_statistics():
    """Test temporal statistics calculation."""
    node = EnrichedLiquidityMemoryNode(
        id="test4",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.5,
        confidence=0.6,
        creation_reason="orderbook_persistence",
        decay_rate=0.0001,
        active=True
    )
    
    # Record interactions at different times
    node.record_price_touch(1010.0)  # 10s gap
    node.record_price_touch(1025.0)  # 15s gap
    node.record_price_touch(1040.0)  # 15s gap
    node.record_price_touch(1055.0)  # 15s gap
    
    assert node.interaction_count == 4
    assert node.interaction_gap_median > 0
    assert len(node.interaction_timestamps) == 4
    
    print("✓ test_temporal_statistics passed")


def test_strength_checkpointing():
    """Test strength history tracking."""
    node = EnrichedLiquidityMemoryNode(
        id="test5",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.5,
        confidence=0.6,
        creation_reason="executed_liquidity",
        decay_rate=0.0001,
        active=True
    )
    
    node.checkpoint_strength()
    assert len(node.strength_history) == 1
    assert node.strength_history[0] == 0.5
    
    node.strength = 0.6
    node.checkpoint_strength()
    assert len(node.strength_history) == 2
    
    print("✓ test_strength_checkpointing passed")


def test_enriched_to_dict():
    """Test export to dict."""
    node = EnrichedLiquidityMemoryNode(
        id="test6",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1010.0,
        strength=0.7,
        confidence=0.8,
        creation_reason="executed_liquidity",
        decay_rate=0.0001,
        active=True
    )
    
    node.record_trade_execution(1020.0, 10000.0, is_buyer_maker=False)
    
    data = node.to_dict()
    
    assert 'price_center' in data
    assert 'volume_total' in data
    assert 'buyer_initiated_volume' in data
    assert data['trade_execution_count'] == 1
    assert data['volume_total'] == 10000.0
    
    print("✓ test_enriched_to_dict passed")


if __name__ == "__main__":
    print("Running enriched memory node tests...\n")
    
    test_enriched_node_creation()
    test_trade_evidence_accumulation()
    test_liquidation_evidence()
    test_temporal_statistics()
    test_strength_checkpointing()
    test_enriched_to_dict()
    
    print("\n✅ All enriched memory tests passed!")
