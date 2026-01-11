"""Quick 30-second test to debug liquidation ingestion"""
import asyncio
import sys
import time

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from observation import ObservationSystem
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS

async def main():
    print("=" * 70)
    print("LIQUIDATION DEBUG TEST - 30 SECONDS")
    print("=" * 70)

    obs_system = ObservationSystem(allowed_symbols=TOP_10_SYMBOLS)
    collector = CollectorService(observation_system=obs_system)

    print("Starting collector...")
    asyncio.create_task(collector.start())

    start_time = time.time()

    while time.time() - start_time < 30:
        obs_system.advance_time(time.time())
        await asyncio.sleep(1)

    # Stop
    collector._running = False

    # Results
    m1 = obs_system._m1
    m2 = obs_system._m2_store

    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    print(f"Trades ingested: {m1.counters['trades']}")
    print(f"Liquidations ingested: {m1.counters['liquidations']}")
    print(f"Errors: {m1.counters['errors']}")
    print(f"M2 nodes created: {m2._total_nodes_created}")
    print(f"M2 active nodes: {len(m2._active_nodes)}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
