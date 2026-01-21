"""
Test Primitive Computation with Manually Seeded M2 Nodes

This script creates test nodes in M2 and verifies that primitives
are computed correctly when M2 is populated.
"""

import time
from observation import ObservationSystem

# Test configuration
TEST_SYMBOL = "BTCUSDT"
TEST_PRICE = 50000.0

def seed_test_nodes(obs_system: ObservationSystem):
    """Manually seed M2 with test nodes."""
    print("\n" + "=" * 70)
    print("SEEDING M2 WITH TEST NODES")
    print("=" * 70)

    m2 = obs_system._m2_store
    current_time = time.time()

    # Create 3 test nodes at different price levels
    nodes_created = []

    # Node 1: Strong bid zone at $49,900
    node1 = m2.add_or_update_node(
        node_id=f"{TEST_SYMBOL}_bid_49900",
        symbol=TEST_SYMBOL,
        price_center=49900.0,
        price_band=100.0,
        side="bid",
        timestamp=current_time - 300,  # 5 minutes ago
        creation_reason="manual_test_seed",
        initial_strength=0.8,
        initial_confidence=0.7,
        volume=100000.0
    )
    # Simulate interactions
    node1.record_liquidation(current_time - 200, "BUY")
    node1.record_trade_execution(current_time - 100, 50000.0, True)
    node1.record_trade_execution(current_time - 50, 30000.0, False)
    nodes_created.append(node1)
    print(f"✓ Created Node 1: {node1.symbol} bid @ ${node1.price_center}")

    # Node 2: Medium ask zone at $50,100
    node2 = m2.add_or_update_node(
        node_id=f"{TEST_SYMBOL}_ask_50100",
        symbol=TEST_SYMBOL,
        price_center=50100.0,
        price_band=100.0,
        side="ask",
        timestamp=current_time - 200,  # 3 minutes ago
        creation_reason="manual_test_seed",
        initial_strength=0.6,
        initial_confidence=0.5,
        volume=75000.0
    )
    node2.record_liquidation(current_time - 150, "SELL")
    node2.record_trade_execution(current_time - 75, 40000.0, True)
    nodes_created.append(node2)
    print(f"✓ Created Node 2: {node2.symbol} ask @ ${node2.price_center}")

    # Node 3: Weak bid zone at $49,700 (will test structural absence)
    node3 = m2.add_or_update_node(
        node_id=f"{TEST_SYMBOL}_bid_49700",
        symbol=TEST_SYMBOL,
        price_center=49700.0,
        price_band=100.0,
        side="bid",
        timestamp=current_time - 600,  # 10 minutes ago
        creation_reason="manual_test_seed",
        initial_strength=0.3,
        initial_confidence=0.4,
        volume=25000.0
    )
    # No recent interactions - will test structural absence
    nodes_created.append(node3)
    print(f"✓ Created Node 3: {node3.symbol} bid @ ${node3.price_center} (stale)")

    # Seed M3 with recent prices (simulate traversal through zone)
    print(f"\n✓ Seeding M3 with price history...")
    m3 = obs_system._m3

    # Simulate price movement from 49,850 -> 50,050 (crossing node1's zone)
    prices_in_traversal = [
        49850, 49870, 49890, 49910, 49930, 49950,  # Approaching zone
        49970, 49990, 50010, 50030, 50050           # Penetrating and exiting
    ]

    for i, price in enumerate(prices_in_traversal):
        ts = current_time - (len(prices_in_traversal) - i) * 0.5
        # Feed trade to M3
        m3.process_trade(
            timestamp=ts,
            symbol=TEST_SYMBOL,
            price=float(price),
            quantity=1.0,
            side="BUY"
        )

    print(f"  - Added {len(prices_in_traversal)} price points")
    print(f"  - Price range: ${prices_in_traversal[0]} → ${prices_in_traversal[-1]}")

    # Keep M3 window open (don't advance time beyond last trade)
    # This ensures prices remain in current_window
    print(f"  - M3 window contains {len(m3._current_windows.get(TEST_SYMBOL, []))} trades")

    print(f"\n✓ M2 now has {len(nodes_created)} active nodes for {TEST_SYMBOL}")
    print("=" * 70)

    return nodes_created


def test_primitive_computation(obs_system: ObservationSystem):
    """Test primitive computation with populated M2."""
    print("\n" + "=" * 70)
    print("TESTING PRIMITIVE COMPUTATION")
    print("=" * 70)

    # Advance time
    current_time = time.time()
    obs_system.advance_time(current_time)

    # Get snapshot (triggers primitive computation)
    snapshot = obs_system.query({"type": "snapshot"})

    # Examine primitives for test symbol
    bundle = snapshot.primitives.get(TEST_SYMBOL)

    if not bundle:
        print(f"✗ No primitive bundle found for {TEST_SYMBOL}")
        return

    print(f"\nPRIMITIVE BUNDLE FOR {TEST_SYMBOL}:")
    print("-" * 70)

    primitives_found = 0

    # Zone Geometry
    if bundle.zone_penetration is not None:
        print(f"✓ zone_penetration: {bundle.zone_penetration:.6f}")
        primitives_found += 1
    else:
        print(f"  zone_penetration: None")

    if bundle.displacement_origin_anchor is not None:
        print(f"✓ displacement_origin_anchor: {bundle.displacement_origin_anchor:.6f}")
        primitives_found += 1
    else:
        print(f"  displacement_origin_anchor: None")

    # Traversal Kinematics
    if bundle.price_traversal_velocity is not None:
        print(f"✓ price_traversal_velocity: {bundle.price_traversal_velocity:.6f}")
        primitives_found += 1
    else:
        print(f"  price_traversal_velocity: None")

    if bundle.traversal_compactness is not None:
        print(f"✓ traversal_compactness: {bundle.traversal_compactness:.6f}")
        primitives_found += 1
    else:
        print(f"  traversal_compactness: None")

    # Distribution
    if bundle.central_tendency_deviation is not None:
        print(f"✓ central_tendency_deviation: {bundle.central_tendency_deviation:.6f}")
        primitives_found += 1
    else:
        print(f"  central_tendency_deviation: None")

    # Structural Absence
    if bundle.structural_absence_duration is not None:
        print(f"✓ structural_absence_duration: {bundle.structural_absence_duration:.6f}s")
        primitives_found += 1
    else:
        print(f"  structural_absence_duration: None")

    # Liquidation Metrics
    if bundle.liquidation_density is not None:
        print(f"✓ liquidation_density: {bundle.liquidation_density:.6f}")
        primitives_found += 1
    else:
        print(f"  liquidation_density: None")

    # Directional Continuity
    if bundle.directional_continuity is not None:
        print(f"✓ directional_continuity: {bundle.directional_continuity:.6f}")
        primitives_found += 1
    else:
        print(f"  directional_continuity: None")

    # Trade Burst
    if bundle.trade_burst is not None:
        print(f"✓ trade_burst: {bundle.trade_burst:.6f}")
        primitives_found += 1
    else:
        print(f"  trade_burst: None")

    # Order Book Primitives
    if bundle.resting_size is not None:
        print(f"✓ resting_size: bid={bundle.resting_size.resting_size_bid:.2f}, " +
              f"ask={bundle.resting_size.resting_size_ask:.2f}")
        primitives_found += 1
    else:
        print(f"  resting_size: None")

    print("-" * 70)
    print(f"\nSUMMARY: {primitives_found}/25 primitives computed")

    # Success criteria
    print("\n" + "=" * 70)
    print("SUCCESS CRITERIA:")
    print("=" * 70)

    criteria = {
        "Zone penetration computed": bundle.zone_penetration is not None,
        "Structural absence detected": bundle.structural_absence_duration is not None,
        "Central tendency computed": bundle.central_tendency_deviation is not None,
        "At least 3 primitives computed": primitives_found >= 3,
    }

    for criterion, passed in criteria.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {criterion}")

    all_passed = all(criteria.values())
    if all_passed:
        print("\n" + "=" * 70)
        print("✓✓✓ PRIMITIVE COMPUTATION WITH M2 NODES SUCCESSFUL ✓✓✓")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("⚠ PARTIAL SUCCESS - Some primitives not computed")
        print("=" * 70)


def main():
    print("=" * 70)
    print("M2 NODE-BASED PRIMITIVE COMPUTATION TEST")
    print("=" * 70)

    # Initialize system
    obs_system = ObservationSystem(allowed_symbols=[TEST_SYMBOL])

    # Seed M2 with test nodes
    nodes = seed_test_nodes(obs_system)

    # Test primitive computation
    test_primitive_computation(obs_system)

    # Show M2 state
    m2 = obs_system._m2_store
    print(f"\n" + "=" * 70)
    print("M2 STATE:")
    print("=" * 70)
    print(f"Total nodes created: {m2._total_nodes_created}")
    print(f"Active nodes: {len(m2._active_nodes)}")
    print(f"Total interactions: {m2._total_interactions}")
    print("=" * 70)


if __name__ == "__main__":
    main()
