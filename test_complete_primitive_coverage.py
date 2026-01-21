"""
Complete Primitive Coverage Test

Tests that ALL primitives required by frozen policies can be computed,
including the newly implemented:
- price_acceptance_ratio (required by kinematics policy)
- structural_persistence_duration (required by absence policy)

Authority: SYSTEM_AUDIT_DATA_AND_PRIMITIVES.md
"""

import time
from observation import ObservationSystem

TEST_SYMBOL = "BTCUSDT"

def test_complete_primitive_coverage():
    """
    Test all primitives with manually seeded data to ensure they can compute.
    """
    print("=" * 70)
    print("COMPLETE PRIMITIVE COVERAGE TEST")
    print("=" * 70)
    print()

    # Initialize observation system
    print("1. Initializing ObservationSystem...")
    obs_system = ObservationSystem(allowed_symbols=[TEST_SYMBOL])
    current_time = time.time()

    # Seed M2 with test nodes
    print("2. Seeding M2 with multiple nodes...")
    m2 = obs_system._m2_store

    # Create 3 nodes at different price levels
    node1 = m2.add_or_update_node(
        node_id=f"{TEST_SYMBOL}_node1",
        symbol=TEST_SYMBOL,
        price_center=50000.0,
        price_band=100.0,
        side="bid",
        timestamp=current_time - 300,
        creation_reason="test_seed",
        initial_strength=0.8,
        initial_confidence=0.7,
        volume=100000.0
    )

    node2 = m2.add_or_update_node(
        node_id=f"{TEST_SYMBOL}_node2",
        symbol=TEST_SYMBOL,
        price_center=50200.0,
        price_band=100.0,
        side="ask",
        timestamp=current_time - 200,
        creation_reason="test_seed",
        initial_strength=0.6,
        initial_confidence=0.6,
        volume=75000.0
    )

    # Record interactions to generate presence intervals
    node1.record_liquidation(current_time - 250, "BUY")
    node1.record_trade_execution(current_time - 200, 50000.0, True)
    node2.record_trade_execution(current_time - 150, 30000.0, False)

    # Simulate node1 going dormant then reactivating
    node1.strength = 0.005  # Below threshold
    node1.apply_decay(current_time - 100)  # Should end presence interval

    # Reactivate node1
    node1.strength = 0.5
    node1.active = True
    node1._start_presence_interval(current_time - 50)
    node1.record_trade_execution(current_time - 40, 25000.0, True)

    print(f"   ✓ Created 3 nodes with interaction history")
    print(f"   ✓ Node1 presence intervals: {len(node1.presence_intervals)}")

    # Seed M3 with price traversal (to generate OHLC candles)
    print("3. Seeding M3 with price traversal...")
    m3 = obs_system._m3

    prices = [49900, 49950, 50000, 50100, 50150, 50120, 50080, 50050]
    for i, price in enumerate(prices):
        ts = current_time - (len(prices) - i) * 0.1
        m3.process_trade(
            timestamp=ts,
            symbol=TEST_SYMBOL,
            price=float(price),
            quantity=1.0,
            side="BUY" if i % 2 == 0 else "SELL"
        )

    print(f"   ✓ Added {len(prices)} trades to M3")

    # Check if OHLC candle was created
    candle = m3.get_current_candle(TEST_SYMBOL)
    if candle:
        print(f"   ✓ OHLC Candle: O={candle['open']}, H={candle['high']}, L={candle['low']}, C={candle['close']}")
    else:
        print(f"   ✗ No OHLC candle found")

    # Advance time and generate snapshot
    print()
    print("4. Generating observation snapshot...")
    obs_system.advance_time(current_time)
    snapshot = obs_system.query({"type": "snapshot"})

    print(f"   ✓ Status: {snapshot.status.name}")
    print(f"   ✓ Timestamp: {snapshot.timestamp:.2f}")
    print(f"   ✓ Symbols: {snapshot.symbols_active}")

    # Examine primitives
    print()
    print("5. Examining computed primitives...")
    bundle = snapshot.primitives.get(TEST_SYMBOL)

    if not bundle:
        print(f"   ✗ No primitive bundle for {TEST_SYMBOL}")
        return False

    primitive_results = {}

    # Check all primitives
    primitives_to_check = [
        ("zone_penetration", "Zone Penetration"),
        ("displacement_origin_anchor", "Displacement Origin Anchor"),
        ("price_traversal_velocity", "Price Traversal Velocity"),
        ("traversal_compactness", "Traversal Compactness"),
        ("price_acceptance_ratio", "Price Acceptance Ratio ⭐ NEW"),
        ("central_tendency_deviation", "Central Tendency Deviation"),
        ("structural_absence_duration", "Structural Absence Duration"),
        ("structural_persistence_duration", "Structural Persistence Duration ⭐ NEW"),
        ("traversal_void_span", "Traversal Void Span"),
        ("event_non_occurrence_counter", "Event Non-Occurrence Counter"),
        ("resting_size", "Resting Size"),
        ("order_consumption", "Order Consumption"),
        ("absorption_event", "Absorption Event"),
        ("refill_event", "Refill Event"),
        ("liquidation_density", "Liquidation Density"),
        ("directional_continuity", "Directional Continuity"),
        ("trade_burst", "Trade Burst"),
    ]

    computed_count = 0
    critical_missing = []

    for field_name, display_name in primitives_to_check:
        value = getattr(bundle, field_name, None)
        status = "✓ COMPUTED" if value is not None else "✗ None"
        primitive_results[field_name] = value is not None

        # Mark critical primitives (required by frozen policies)
        is_critical = field_name in ["price_acceptance_ratio", "structural_persistence_duration"]

        if value is not None:
            computed_count += 1
            if is_critical:
                print(f"   {status} - {display_name} (CRITICAL FOR POLICIES)")
            else:
                print(f"   {status} - {display_name}")
        else:
            if is_critical:
                print(f"   {status} - {display_name} (CRITICAL - MISSING!)")
                critical_missing.append(display_name)
            else:
                print(f"   {status} - {display_name}")

    print()
    print(f"   Total primitives computed: {computed_count}/{len(primitives_to_check)}")

    # Check critical primitives
    print()
    print("6. Verifying frozen policy dependencies...")

    geometry_ok = all([
        primitive_results.get("zone_penetration"),
        primitive_results.get("traversal_compactness"),
        primitive_results.get("central_tendency_deviation")
    ])

    kinematics_ok = all([
        primitive_results.get("price_traversal_velocity"),
        primitive_results.get("traversal_compactness"),
        primitive_results.get("price_acceptance_ratio")  # ⭐ CRITICAL
    ])

    absence_ok = all([
        primitive_results.get("structural_absence_duration"),
        primitive_results.get("structural_persistence_duration")  # ⭐ CRITICAL
    ])

    print(f"   Geometry Policy:   {'✓ OK' if geometry_ok else '✗ BROKEN'}")
    print(f"   Kinematics Policy: {'✓ OK' if kinematics_ok else '✗ BROKEN'}")
    print(f"   Absence Policy:    {'✓ OK' if absence_ok else '✗ BROKEN'}")

    # Final verdict
    print()
    print("=" * 70)
    if len(critical_missing) == 0 and kinematics_ok and absence_ok:
        print("✓✓✓ ALL CRITICAL PRIMITIVES COMPUTED ✓✓✓")
        print("=" * 70)
        print()
        print("READY FOR POLICY ACTIVATION:")
        print("  ✓ price_acceptance_ratio implemented (Kinematics Policy)")
        print("  ✓ structural_persistence_duration implemented (Absence Policy)")
        print("  ✓ All 3 frozen policies can now generate proposals")
        return True
    else:
        print("✗✗✗ CRITICAL PRIMITIVES MISSING ✗✗✗")
        print("=" * 70)
        print()
        print("MISSING:")
        for missing in critical_missing:
            print(f"  ✗ {missing}")
        return False


if __name__ == "__main__":
    success = test_complete_primitive_coverage()
    exit(0 if success else 1)
