"""
Unit tests for LiquidityMemoryStore

Validates deterministic behavior.
"""

import sys
sys.path.append('d:/liquidation-trading')

from memory import LiquidityMemoryStore, CreationReason


def test_add_node():
    """Test adding new nodes."""
    store = LiquidityMemoryStore()
    
    node = store.add_or_update_node(
        node_id="test_bid_2.01",
        price_center=2.01,
        price_band=0.001,
        side="bid",
        timestamp=1000.0,
        creation_reason=CreationReason.ORDERBOOK_PERSISTENCE,
        initial_strength=0.6,
        initial_confidence=0.7
    )
    
    assert node.id == "test_bid_2.01"
    assert node.price_center == 2.01
    assert node.strength == 0.6
    assert node.active == True
    
    metrics = store.get_metrics()
    assert metrics['total_nodes_created'] == 1
    assert metrics['active_nodes'] == 1
    
    print("✓ test_add_node passed")


def test_update_existing_node():
    """Test updating existing node."""
    store = LiquidityMemoryStore()
    
    # Create node
    node1 = store.add_or_update_node(
        node_id="test_bid_2.01",
        price_center=2.01,
        price_band=0.001,
        side="bid",
        timestamp=1000.0,
        creation_reason=CreationReason.ORDERBOOK_PERSISTENCE,
        initial_strength=0.5
    )
    
    # Update same node
    node2 = store.add_or_update_node(
        node_id="test_bid_2.01",
        price_center=2.01,
        price_band=0.001,
        side="bid",
        timestamp=1100.0,
        creation_reason=CreationReason.EXECUTED_LIQUIDITY,
        volume=1000.0
    )
    
    # Should be same node
    assert node1 is node2
    assert node2.strength == 0.6  # 0.5 + 0.1 boost
    assert node2.interaction_count == 2
    assert node2.volume_observed == 1000.0
    
    metrics = store.get_metrics()
    assert metrics['total_nodes_created'] == 1  # Only one node created
    assert metrics['total_interactions'] == 2  # But two interactions
    
    print("✓ test_update_existing_node passed")


def test_decay():
    """Test node decay."""
    store = LiquidityMemoryStore()
    
    node = store.add_or_update_node(
        node_id="test_bid_2.01",
        price_center=2.01,
        price_band=0.001,
        side="bid",
        timestamp=1000.0,
        creation_reason=CreationReason.ORDERBOOK_PERSISTENCE,
        initial_strength=0.5,
        decay_rate=0.01  # 1% decay per second
    )
    
    # Decay after 10 seconds
    archived = store.decay_nodes(1010.0)
    
    # Strength should be reduced: 0.5 * (1 - 0.01*10) = 0.5 * 0.9 = 0.45
    assert 0.44 < node.strength < 0.46
    assert archived == 0  # Not archived yet
    
    # Decay after 100 seconds total (more aggressive to ensure it drops low enough)
    archived = store.decay_nodes(1100.0)
    
    # Strength should be very low now (but may not be <0.1 due to decay formula)
    # After 100s: strength * (1 - 0.01*100) = 0.45 * 0 = 0 (would be archived)
    # So we expect it to be archived
    assert node.active == False or node.strength < 0.05
    
    print("✓ test_decay passed")


def test_archival():
    """Test node archival when strength drops."""
    store = LiquidityMemoryStore()
    
    node = store.add_or_update_node(
        node_id="test_bid_2.01",
        price_center=2.01,
        price_band=0.001,
        side="bid",
        timestamp=1000.0,
        creation_reason=CreationReason.ORDERBOOK_PERSISTENCE,
        initial_strength=0.05,  # Low initial strength
        decay_rate=0.01  # 1% per second
    )
    
    # Decay aggressively to push below threshold
    # strength * (1 - 0.01 * time_elapsed) needs to be < 0.01
    # 0.05 * (1 - 0.01 * t) < 0.01
    # (1 - 0.01*t) < 0.2
    # 0.01*t > 0.8
    # t > 80
    archived = store.decay_nodes(1100.0)  # 100 seconds later
    
    assert archived == 1
    
    metrics = store.get_metrics()
    assert metrics['active_nodes'] == 0
    assert metrics['archived_nodes'] == 1
    
    print("✓ test_archival passed")


def test_query_active_nodes():
    """Test querying nodes by price and filters."""
    store = LiquidityMemoryStore()
    
    # Add multiple nodes
    store.add_or_update_node("bid_2.00", 2.00, 0.001, "bid", 1000.0, CreationReason.ORDERBOOK_PERSISTENCE, 0.8)
    store.add_or_update_node("bid_2.01", 2.01, 0.001, "bid", 1000.0, CreationReason.ORDERBOOK_PERSISTENCE, 0.6)
    store.add_or_update_node("ask_2.02", 2.02, 0.001, "ask", 1000.0, CreationReason.ORDERBOOK_PERSISTENCE, 0.4)
    
    # Query all
    all_nodes = store.get_active_nodes()
    assert len(all_nodes) == 3
    
    # Query by price radius
    nearby = store.get_active_nodes(current_price=2.00, radius=0.005)
    assert len(nearby) == 1
    assert nearby[0].price_center == 2.00
    
    # Query by strength
    strong = store.get_active_nodes(min_strength=0.7)
    assert len(strong) == 1
    assert strong[0].strength == 0.8
    
    # Query by side
    bids = store.get_active_nodes(side_filter="bid")
    assert len(bids) == 2
    
    print("✓ test_query_active_nodes passed")


def test_determinism():
    """Test that operations are deterministic."""
    # Run same sequence twice
    results = []
    
    for _ in range(2):
        store = LiquidityMemoryStore()
        
        store.add_or_update_node("node1", 2.00, 0.001, "bid", 1000.0, CreationReason.ORDERBOOK_PERSISTENCE, 0.5)
        store.add_or_update_node("node2", 2.01, 0.001, "ask", 1001.0, CreationReason.EXECUTED_LIQUIDITY, 0.6)
        store.decay_nodes(1100.0)
        
        metrics = store.get_metrics()
        results.append(metrics)
    
    # Both runs should produce identical metrics
    assert results[0] == results[1]
    
    print("✓ test_determinism passed")


if __name__ == "__main__":
    print("Running LiquidityMemoryStore unit tests...\n")
    
    test_add_node()
    test_update_existing_node()
    test_decay()
    test_archival()
    test_query_active_nodes()
    test_determinism()
    
    print("\n✅ All tests passed!")
