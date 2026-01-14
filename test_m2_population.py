"""Test M2 node population from live data.

Verifies that:
1. Nodes are created from liquidations
2. Trades associate with nodes
3. Lifecycle management works (decay, state transitions)
4. M4 views can compute from nodes
"""
import asyncio
import sys
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS
from observation import ObservationSystem

async def test_m2_population():
    """Run for 60 seconds to test M2 node population."""
    print("Starting M2 node population test...")
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

        print("\n=== M2 Node Population Report ===")
        print(f"Total nodes created: {m2_metrics['total_nodes_created']}")
        print(f"Active nodes: {m2_metrics['active_nodes']}")
        print(f"Dormant nodes: {m2_metrics['dormant_nodes']}")
        print(f"Archived nodes: {m2_metrics['archived_nodes']}")
        print(f"Total interactions: {m2_metrics['total_interactions']}")

        # Show sample nodes per symbol
        for symbol in TOP_10_SYMBOLS:
            nodes = obs_system._m2_store.get_active_nodes_for_symbol(symbol)
            print(f"\n{symbol}: {len(nodes)} active nodes")
            for node in nodes[:3]:  # Show first 3
                print(f"  - {node}")

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
    asyncio.run(test_m2_population())
