"""
Quick test to verify primitive fixes generate mandates.
"""
import asyncio
import sys
import time

# Fix Windows event loop for aiohttp/aiodns
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from observation import ObservationSystem
from runtime.collector.service import CollectorService


async def test_mandates():
    print("=" * 70)
    print("TESTING MANDATE GENERATION AFTER PRIMITIVE FIX")
    print("=" * 70)

    # Initialize system
    obs = ObservationSystem(['BTCUSDT', 'ETHUSDT'])
    service = CollectorService(obs)

    # Start collector in background
    collector_task = asyncio.create_task(service.start())

    # Wait for data to accumulate
    print("\nWaiting 30 seconds for data collection...")
    await asyncio.sleep(30)

    # Check for mandates
    print("\nChecking mandate generation...")

    # Stop collector
    service._running = False
    await asyncio.sleep(1)

    # Check if any mandates were generated via database
    try:
        import sqlite3
        conn = sqlite3.connect('logs/execution.db')
        c = conn.cursor()

        # Get mandate count
        c.execute('SELECT COUNT(*) FROM mandates')
        mandate_count = c.fetchone()[0]

        # Get recent policy evaluations
        c.execute('''
            SELECT policy_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN generated_proposal = 1 THEN 1 ELSE 0 END) as proposals
            FROM policy_evaluations
            WHERE id > (SELECT MAX(id) - 100 FROM policy_evaluations)
            GROUP BY policy_name
        ''')

        print(f"\n✓ Total mandates generated: {mandate_count}")
        print("\nRecent policy evaluations:")
        for row in c.fetchall():
            print(f"  {row[0]}: {row[2]}/{row[1]} proposals")

        conn.close()

        if mandate_count > 0:
            print("\n✓✓✓ SUCCESS - Mandates are being generated! ✓✓✓")
        else:
            print("\n⚠ No mandates yet - may need more time or volatility")

    except Exception as e:
        print(f"\nError checking database: {e}")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_mandates())
