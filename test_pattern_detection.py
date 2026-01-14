"""Test M4 pattern detection from live data.

Verifies that:
1. Order blocks are detected from M2 nodes
2. Supply/demand zones are detected from node clusters
3. Pattern primitives are exposed via observation snapshot
4. Pattern characteristics are structurally sound
"""
import asyncio
import sys
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS
from observation import ObservationSystem

async def test_pattern_detection():
    """Run for 60 seconds to test pattern detection."""
    print("Starting pattern detection test...")
    print(f"Watching symbols: {TOP_10_SYMBOLS}\n")

    obs_system = ObservationSystem(TOP_10_SYMBOLS)
    collector = CollectorService(obs_system, warmup_duration_sec=10)

    # Start collector
    task = asyncio.create_task(collector.start())

    try:
        # Run for 60 seconds
        await asyncio.sleep(60)

        # Get snapshot
        snapshot = obs_system.query({'type': 'snapshot'})

        # Check M2 metrics
        m2_metrics = obs_system._m2_store.get_metrics()

        print("\n=== M2 Node Status ===")
        print(f"Total nodes created: {m2_metrics['total_nodes_created']}")
        print(f"Active nodes: {m2_metrics['active_nodes']}")
        print(f"Total interactions: {m2_metrics['total_interactions']}")

        # Check for patterns in each symbol
        order_blocks_found = 0
        supply_demand_zones_found = 0

        print("\n=== Pattern Detection Results ===")
        for symbol in TOP_10_SYMBOLS:
            if symbol in snapshot.primitives:
                bundle = snapshot.primitives[symbol]

                # Check order block detection
                if bundle.order_block is not None:
                    ob = bundle.order_block
                    order_blocks_found += 1
                    print(f"\n{symbol} - ORDER BLOCK DETECTED:")
                    print(f"  Price: ${ob.price_center:.2f} (±${ob.price_band:.2f})")
                    print(f"  Side: {ob.side}")
                    print(f"  Interactions: {ob.interaction_count} ({ob.interactions_per_hour:.1f}/hour)")
                    print(f"  Burstiness: {ob.burstiness_coefficient:.3f}")
                    print(f"  Node strength: {ob.node_strength:.3f}")
                    print(f"  Total volume: ${ob.total_volume:,.0f}")
                    print(f"  Time since interaction: {ob.time_since_interaction_sec:.1f}s")
                    print(f"  Liquidations in band: {ob.liquidations_within_band}")

                # Check supply/demand zone detection
                if bundle.supply_demand_zone is not None:
                    zone = bundle.supply_demand_zone
                    supply_demand_zones_found += 1
                    print(f"\n{symbol} - {zone.zone_type.upper()} ZONE DETECTED:")
                    print(f"  Range: ${zone.zone_low:.2f} - ${zone.zone_high:.2f}")
                    print(f"  Center: ${zone.zone_center:.2f}")
                    print(f"  Width: ${zone.zone_width:.2f}")
                    print(f"  Nodes in cluster: {zone.node_count}")
                    print(f"  Total interactions: {zone.total_interactions}")
                    print(f"  Total volume: ${zone.total_volume:,.0f}")
                    print(f"  Avg node strength: {zone.avg_node_strength:.3f}")
                    if zone.displacement_detected:
                        print(f"  Displacement: {zone.displacement_direction} by ${zone.displacement_magnitude:.2f}")
                    if zone.retest_detected:
                        print(f"  Retests: {zone.retest_count}")

        print(f"\n=== Summary ===")
        print(f"Order blocks detected: {order_blocks_found}")
        print(f"Supply/demand zones detected: {supply_demand_zones_found}")

        if order_blocks_found == 0 and supply_demand_zones_found == 0:
            print("\nNo patterns detected. This could mean:")
            print("- Not enough data collected (try longer run)")
            print("- Detection thresholds too strict")
            print("- Market conditions don't meet pattern criteria")
            print("\nShowing sample M2 nodes for debugging:")
            for symbol in TOP_10_SYMBOLS[:3]:
                nodes = obs_system._m2_store.get_active_nodes_for_symbol(symbol)
                if nodes:
                    print(f"\n{symbol}: {len(nodes)} active nodes")
                    for node in nodes[:2]:
                        print(f"  Node {node.id}:")
                        print(f"    Price: ${node.price_center:.2f}, Strength: {node.strength:.3f}")
                        print(f"    Interactions: {node.interaction_count}, Volume: ${node.volume_total:,.0f}")

    except KeyboardInterrupt:
        print("\nTest interrupted")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_pattern_detection())
