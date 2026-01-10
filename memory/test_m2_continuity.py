"""
M2 Validation Tests

Validates Phase M2 implementation against requirements.
"""

import sys
sys.path.append('d:/liquidation-trading')

from memory import (
    ContinuityMemoryStore,
    MemoryState,
    MemoryStateThresholds,
    MemoryTopology,
    MemoryPressureAnalyzer
)


def test_three_state_model():
    """Test ACTIVE → DORMANT → ARCHIVED transitions."""
    print("="*70)
    print("TEST 1: Three-State Model")
    print("="*70)
    
    store = ContinuityMemoryStore()
    
    # Create active node with low strength
    node = store.add_or_update_node(
        node_id="test_state",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        timestamp=1000.0,
        creation_reason="executed_liquidity",
        initial_strength=0.1  # Below threshold (0.15)
    )
    
    print(f"\nInitial: {len(store._active_nodes)} active, {len(store._dormant_nodes)} dormant")
    print(f"Node strength: {node.strength}")
    
    # Trigger ACTIVE → DORMANT (low strength)
    result = store.update_memory_states(1100.0)
    
    print(f"After state update: {len(store._active_nodes)} active, {len(store._dormant_nodes)} dormant")
    print(f"Transitioned: {result['transitioned_to_dormant']} to dormant")
    
    assert len(store._active_nodes) == 0, f"Expected 0 active, got {len(store._active_nodes)}"
    assert len(store._dormant_nodes) == 1, f"Expected 1 dormant, got {len(store._dormant_nodes)}"
    assert "test_state" in store._dormant_evidence
    
    print("✓ ACTIVE → DORMANT transition works")
    
    # Trigger DORMANT → ARCHIVED (very low strength)
    node_dormant = list(store._dormant_nodes.values())[0]
    node_dormant.strength = 0.005  # Below archive threshold
    
    result = store.update_memory_states(2000.0)
    
    print(f"After archival: {len(store._dormant_nodes)} dormant, {len(store._archived_nodes)} archived")
    print(f"Transitioned: {result['transitioned_to_archived']} to archived")
    
    assert len(store._dormant_nodes) == 0
    assert len(store._archived_nodes) == 1
    
    print("✓ DORMANT → ARCHIVED transition works")
    print("✅ TEST 1 PASSED\n")


def test_historical_evidence_retention():
    """Test that dormant nodes preserve historical evidence."""
    print("="*70)
    print("TEST 2: Historical Evidence Retention")
    print("="*70)
    
    store = ContinuityMemoryStore()
    
    # Create node with rich evidence
    node = store.add_or_update_node(
        node_id="test_history",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        timestamp=1000.0,
        creation_reason="executed_liquidity",
        initial_strength=0.2
    )
    
    # Add evidence
    store.update_with_trade("test_history", 1010.0, 5000.0, False)
    store.update_with_trade("test_history", 1020.0, 3000.0, True)
    store.update_with_liquidation("test_history", 1030.0, "BUY")
    
    original_interactions = node.interaction_count
    original_volume = node.volume_total
    
    print(f"Before dormancy: {original_interactions} interactions, ${original_volume:.0f} volume")
    
    # Transition to dormant
    store.update_memory_states(5000.0)
    
    # Check historical evidence preserved
    assert "test_history" in store._dormant_evidence
    evidence = store._dormant_evidence["test_history"]
    
    print(f"Historical evidence: {evidence.total_interactions} interactions, ${evidence.total_volume:.0f} volume")
    
    assert evidence.total_interactions >= original_interactions
    assert evidence.total_volume == original_volume
    assert evidence.buyer_volume > 0
    assert evidence.long_liquidations > 0
    
    print("✓ Historical evidence retained")
    print("✅ TEST 2 PASSED\n")


def test_dormant_revival():
    """Test dormant node revival with historical context."""
    print("="*70)
    print("TEST 3: Dormant Revival with History")
    print("="*70)
    
    store = ContinuityMemoryStore()
    
    # Create and populate node
    node = store.add_or_update_node(
        node_id="test_revival",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        timestamp=1000.0,
        creation_reason="executed_liquidity",
        initial_strength=0.2
    )
    
    store.update_with_trade("test_revival", 1010.0, 10000.0, False)
    
    # Transition to dormant
    store.update_memory_states(5000.0)
    
    print(f"Node dormant: {len(store._dormant_nodes)} dormant nodes")
    
    # Revival with new evidence
    revived = store.add_or_update_node(
        node_id="test_revival",
        price_center=2.05,
        price_band=0.002,
        side="bid",
        timestamp=6000.0,
        creation_reason="executed_liquidity",
        volume=5000.0
    )
    
    print(f"After revival: strength={revived.strength:.3f}")
    
    assert len(store._dormant_nodes) == 0
    assert len(store._active_nodes) == 1
    assert revived.strength > 0.0  # Has historical context
    
    print("✓ Dormant node revived with historical strength")
    print("✅ TEST 3 PASSED\n")


def test_dormant_persistence():
    """Test dormant nodes persist longer than active."""
    print("="*70)
    print("TEST 4: Dormant Persistence (>10× Active)")
    print("="*70)
    
    active_decay = MemoryStateThresholds.ACTIVE_DECAY_RATE
    dormant_decay = MemoryStateThresholds.DORMANT_DECAY_RATE
    
    ratio = active_decay / dormant_decay
    
    print(f"Active decay rate: {active_decay}")
    print(f"Dormant decay rate: {dormant_decay}")
    print(f"Ratio: {ratio}×")
    
    assert ratio >= 10.0
    
    print("✓ Dormant decay is ≥10× slower")
    print("✅ TEST 4 PASSED\n")


def test_topology_clustering():
    """Test topology clustering (no labels)."""
    print("="*70)
    print("TEST 5: Topology Clustering (Factual Only)")
    print("="*70)
    
    store = ContinuityMemoryStore()
    
    # Create cluster of nodes
    for i in range(5):
        store.add_or_update_node(
            node_id=f"cluster_a_{i}",
            price_center=202 + (i * 0.001),
            price_band=0.002,
            side="bid",
            timestamp=1000.0 + i,
            creation_reason="executed_liquidity"
        )
    
    # Create another cluster
    for i in range(3):
        store.add_or_update_node(
            node_id=f"cluster_b_{i}",
            price_center=2.10 + (i * 0.001),
            price_band=0.002,
            side="ask",
            timestamp=1000.0 + i,
            creation_reason="liquidation_interaction"
        )
    
    clusters = store.get_topological_clusters(price_threshold=0.01, min_cluster_size=2)
    
    print(f"Found {len(clusters)} clusters")
    for cluster in clusters:
        print(f"  {cluster.cluster_id}: {cluster.node_count} nodes, center=${cluster.price_center:.4f}")
    
    assert len(clusters) >= 2
    
    # Verify no interpretive labels
    for cluster in clusters:
        assert "support" not in cluster.cluster_id.lower()
        assert "resistance" not in cluster.cluster_id.lower()
    
    print("✓ Clustering works without interpretive labels")
    print("✅ TEST 5 PASSED\n")


def test_memory_pressure():
    """Test memory pressure metrics (not trade pressure)."""
    print("="*70)
    print("TEST 6: Memory Pressure Metrics")
    print("="*70)
    
    store = ContinuityMemoryStore()
    
    # Create nodes with varying activity
    for i in range(10):
        node = store.add_or_update_node(
            node_id=f"pressure_{i}",
            price_center=2.05 + (i * 0.01),
            price_band=0.002,
            side="bid",
            timestamp=1000.0,
            creation_reason="executed_liquidity"
        )
        store.update_with_trade(f"pressure_{i}", 1010.0, 1000.0 * (i+1), False)
    
    pressure = store.get_pressure_map((2.05, 2.15))
    
    print(f"Pressure map for $2.05-$2.15:")
    print(f"  Nodes per unit: {pressure.nodes_per_unit:.2f}")
    print(f"  Volume per unit: ${pressure.volume_per_unit:.0f}")
    print(f"  Interactions per unit: {pressure.interactions_per_unit:.2f}")
    
    assert pressure.nodes_per_unit > 0
    assert pressure.volume_per_unit > 0
    
    print("✓ Pressure metrics computed (factual density)")
    print("✅ TEST 6 PASSED\n")


def test_prohibition_compliance():
    """Verify no signal/prediction fields exist."""
    print("="*70)
    print("TEST 7: Prohibition Compliance")
    print("="*70)
    
    store = ContinuityMemoryStore()
    
    # Check for forbidden fields in store
    forbidden_attrs = [
        'generate_signal', 'predict_direction', 'classify_regime',
        'is_bullish', 'is_bearish', 'is_support', 'is_resistance',
        'trade_recommendation', 'entry_signal', 'exit_signal'
    ]
    
    violations = []
    for attr in forbidden_attrs:
        if hasattr(store, attr):
            violations.append(attr)
    
    if violations:
        print(f"❌ FAIL: Found forbidden attributes: {violations}")
        assert False
    else:
        print("✓ No signal generation methods")
    
    # Check query methods return facts only
    clusters = store.get_topological_clusters()
    pressure = store.get_pressure_map((2.0, 2.1))
    
    # Verify no interpretive labels in output
    assert isinstance(pressure.nodes_per_unit, (int, float))
    assert not hasattr(pressure, 'bullish_bias')
    assert not hasattr(pressure, 'support_level')
    
    print("✓ All outputs are factual (counts, densities, metrics)")
    print("✅ TEST 7 PASSED\n")


def run_all_tests():
    """Run all M2 validation tests."""
    print("\n" + "="*70)
    print("M2 PHASE VALIDATION - MEMORY CONTINUITY & TOPOLOGY")
    print("="*70 + "\n")
    
    test_three_state_model()
    test_historical_evidence_retention()
    test_dormant_revival()
    test_dormant_persistence()
    test_topology_clustering()
    test_memory_pressure()
    test_prohibition_compliance()
    
    print("="*70)
    print("✅ ALL M2 VALIDATION TESTS PASSED")
    print("="*70)
    print("\nPhase M2 Requirements Met:")
    print("  ✓ Three-state model (ACTIVE/DORMANT/ARCHIVED)")
    print("  ✓ Historical evidence retention")
    print("  ✓ Dormant revival with context")
    print("  ✓ Dormant persistence >10× active")
    print("  ✓ Topology without labels")
    print("  ✓ Pressure metrics (factual)")
    print("  ✓ Zero signal/prediction fields")
    print("\n" + "="*70)


if __name__ == "__main__":
    run_all_tests()
