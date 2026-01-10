"""
Test enhanced decay and lifecycle features.
"""

import sys
sys.path.append('d:/liquidation-trading')

from memory import LiquidityMemoryNode, CreationReason


def test_enhanced_decay_time_based():
    """Test basic time-based decay."""
    node = LiquidityMemoryNode(
        id="test1",
        price_center=2.0,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.5,
        confidence=0.6,
        creation_reason=CreationReason.ORDERBOOK_PERSISTENCE,
        decay_rate=0.001,  # 0.1% per second
        active=True
    )
    
    # Apply enhanced decay (no price, so just time-based)
    result = node.apply_enhanced_decay(1100.0)  # 100 seconds later
    
    assert result['decay_type'] == 'time_based'
    assert 0.4 < node.strength < 0.5  # Should have decayed
    assert node.active == True
    
    print("✓ test_enhanced_decay_time_based passed")


def test_invalidation_clean_break():
    """Test invalidation from clean break."""
    node = LiquidityMemoryNode(
        id="test2",
        price_center=2.0,
        price_band=0.002,  # ±0.001
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.6,
        confidence=0.7,
        creation_reason=CreationReason.EXECUTED_LIQUIDITY,
        decay_rate=0.0001,
        active=True
    )
    
    # Price breaks cleanly above (2x band = 0.004)
    result = node.apply_enhanced_decay(1500.0, current_price=2.01)  # 500s later, far away
    
    # Should detect invalidation
    assert 'invalidation' in result['decay_type']
    assert result['decay_rate'] > 0.0001  # Accelerated
    
    print("✓ test_invalidation_clean_break passed")


def test_lifecycle_forming():
    """Test forming state."""
    node = LiquidityMemoryNode(
        id="test3",
        price_center=2.0,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,
        strength=0.2,  # Low strength
        confidence=0.5,
        creation_reason=CreationReason.ORDERBOOK_PERSISTENCE,
        decay_rate=0.0001,
        active=True,
        interaction_count=1
    )
    
    # Just created, low strength
    state = node.get_lifecycle_state(1030.0)  # 30 seconds old
    assert state == "forming"
    
    print("✓ test_lifecycle_forming passed")


def test_lifecycle_established():
    """Test established state."""
    node = LiquidityMemoryNode(
        id="test4",
        price_center=2.0,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,  # Old interaction (20 min ago)
        strength=0.7,  # High strength
        confidence=0.8,
        creation_reason=CreationReason.EXECUTED_LIQUIDITY,
        decay_rate=0.0001,
        active=True,
        interaction_count=5  # Multiple interactions
    )
    
    state = node.get_lifecycle_state(2200.0)  # 20 minutes later
    assert state == "established"
    
    print("✓ test_lifecycle_established passed")


def test_lifecycle_active():
    """Test active state."""
    node = LiquidityMemoryNode(
        id="test5",
        price_center=2.0,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1500.0,  # Recent interaction
        strength=0.5,
        confidence=0.7,
        creation_reason=CreationReason.EXECUTED_LIQUIDITY,
        decay_rate=0.0001,
        active=True,
        interaction_count=3
    )
    
    # Within 10 minutes of last interaction
    state = node.get_lifecycle_state(1600.0)
    assert state == "active"
    
    print("✓ test_lifecycle_active passed")


def test_lifecycle_dormant():
    """Test dormant state."""
    node = LiquidityMemoryNode(
        id="test6",
        price_center=2.0,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1000.0,  # Old interaction
        strength=0.15,  # Some strength remains
        confidence=0.6,
        creation_reason=CreationReason.LIQUIDATION_INTERACTION,
        decay_rate=0.0001,
        active=True,
        interaction_count=2
    )
    
    # 30 minutes since interaction, but still has strength
    state = node.get_lifecycle_state(2800.0)
    assert state == "dormant"
    
    print("✓ test_lifecycle_dormant passed")


def test_lifecycle_metadata():
    """Test lifecycle metadata."""
    node = LiquidityMemoryNode(
        id="test7",
        price_center=2.0,
        price_band=0.002,
        side="bid",
        first_seen_ts=1000.0,
        last_interaction_ts=1200.0,
        strength=0.6,
        confidence=0.7,
        creation_reason=CreationReason.PRICE_REJECTION,
        decay_rate=0.0001,
        active=True,
        interaction_count=4,
        volume_observed=5000.0
    )
    
    metadata = node.get_lifecycle_metadata(1300.0, current_price=2.001)
    
    assert 'state' in metadata
    assert 'age_seconds' in metadata
    assert 'distance_from_price_bps' in metadata
    assert metadata['age_seconds'] == 300.0  # 1300 - 1000
    assert metadata['time_since_interaction'] == 100.0  # 1300 - 1200
    
    print("✓ test_lifecycle_metadata passed")


if __name__ == "__main__":
    print("Running enhanced decay & lifecycle tests...\n")
    
    test_enhanced_decay_time_based()
    test_invalidation_clean_break()
    test_lifecycle_forming()
    test_lifecycle_established()
    test_lifecycle_active()
    test_lifecycle_dormant()
    test_lifecycle_metadata()
    
    print("\n✅ All M3 tests passed!")
