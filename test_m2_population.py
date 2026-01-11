"""
M2 Node Population Verification Test

Verifies that M2 memory nodes are created from live market data:
- Liquidations create new nodes
- Trades update existing nodes
- Node lifecycle management works
- Symbol partitioning functions correctly
"""

import asyncio
import sys
import time
import logging
from datetime import datetime

# Fix Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from observation import ObservationSystem
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class M2PopulationMonitor:
    """Monitor M2 node population from live data."""

    def __init__(self):
        self.obs_system = None
        self.collector = None
        self.start_time = None

    async def run_test(self, duration_seconds=180):
        """Run 3-minute M2 population test."""
        logger.info("="*70)
        logger.info("M2 NODE POPULATION VERIFICATION TEST - 3 MINUTES")
        logger.info("="*70)
        logger.info(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Symbols: {', '.join(TOP_10_SYMBOLS)}")
        logger.info(f"Duration: {duration_seconds} seconds")
        logger.info("="*70)
        logger.info("")

        # Initialize systems
        logger.info("Initializing ObservationSystem...")
        self.obs_system = ObservationSystem(allowed_symbols=TOP_10_SYMBOLS)
        logger.info("✓ ObservationSystem initialized")

        logger.info("Initializing CollectorService...")
        self.collector = CollectorService(observation_system=self.obs_system)
        logger.info("✓ CollectorService initialized")

        # Start collector
        logger.info("Starting Binance WebSocket collector...")
        asyncio.create_task(self.collector.start())

        self.start_time = time.time()
        end_time = self.start_time + duration_seconds

        logger.info("✓ Collector started - monitoring M2 node creation...")
        logger.info("")

        # Report intervals
        last_report = self.start_time
        report_interval = 30  # 30 seconds

        try:
            while time.time() < end_time:
                current_time = time.time()

                # Advance time
                self.obs_system.advance_time(current_time)

                # Report every 30 seconds
                if current_time - last_report >= report_interval:
                    self.print_progress_report()
                    last_report = current_time

                # Sleep 1 second
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.warning("Test interrupted by user")
        except Exception as e:
            logger.error(f"Test error: {e}", exc_info=True)
        finally:
            # Stop collector
            self.collector._running = False
            logger.info("")
            logger.info("Stopping collector...")

            # Final report
            self.print_final_report()

    def print_progress_report(self):
        """Print progress report."""
        elapsed = int(time.time() - self.start_time)

        logger.info("")
        logger.info(f"--- PROGRESS REPORT ({elapsed}s elapsed) ---")

        # Get M2 store stats
        m2 = self.obs_system._m2_store

        logger.info(f"Active Nodes: {len(m2._active_nodes)}")
        logger.info(f"Dormant Nodes: {len(m2._dormant_nodes)}")
        logger.info(f"Archived Nodes: {len(m2._archived_nodes)}")
        logger.info(f"Total Nodes Created: {m2._total_nodes_created}")
        logger.info(f"Total Interactions: {m2._total_interactions}")

        # Get M1 ingestion stats
        m1 = self.obs_system._m1
        logger.info(f"Liquidations Ingested: {m1.counters['liquidations']}")
        logger.info(f"Trades Ingested: {m1.counters['trades']}")

        # Show sample nodes by symbol
        if m2._active_nodes:
            logger.info("")
            logger.info("Active Nodes by Symbol:")
            symbol_counts = {}
            for node in m2._active_nodes.values():
                symbol_counts[node.symbol] = symbol_counts.get(node.symbol, 0) + 1

            for symbol in sorted(symbol_counts.keys()):
                logger.info(f"  {symbol}: {symbol_counts[symbol]} nodes")

            # Show strongest node
            strongest = max(m2._active_nodes.values(), key=lambda n: n.strength)
            logger.info("")
            logger.info(f"Strongest Node:")
            logger.info(f"  {strongest.symbol} @ ${strongest.price_center:.2f}")
            logger.info(f"  Strength: {strongest.strength:.3f}")
            logger.info(f"  Interactions: {strongest.interaction_count}")
            logger.info(f"  Liquidations: {strongest.liquidation_proximity_count}")
            logger.info(f"  Trades: {strongest.trade_execution_count}")
        else:
            logger.warning("  No active nodes yet")

        logger.info("")

    def print_final_report(self):
        """Print final verification report."""
        elapsed = time.time() - self.start_time

        logger.info("="*70)
        logger.info("FINAL M2 POPULATION VERIFICATION REPORT")
        logger.info("="*70)
        logger.info(f"Test Duration: {elapsed:.1f} seconds")
        logger.info(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # Get M2 store stats
        m2 = self.obs_system._m2_store
        m1 = self.obs_system._m1

        # Node statistics
        logger.info("NODE POPULATION STATISTICS:")
        logger.info(f"  Total Nodes Created: {m2._total_nodes_created}")
        logger.info(f"  Active Nodes: {len(m2._active_nodes)}")
        logger.info(f"  Dormant Nodes: {len(m2._dormant_nodes)}")
        logger.info(f"  Archived Nodes: {len(m2._archived_nodes)}")
        logger.info(f"  Total Interactions: {m2._total_interactions}")
        logger.info("")

        # Ingestion statistics
        logger.info("INGESTION STATISTICS:")
        logger.info(f"  Liquidations: {m1.counters['liquidations']}")
        logger.info(f"  Trades: {m1.counters['trades']}")
        logger.info(f"  Depth Updates: {m1.counters['depth_updates']}")
        logger.info("")

        # Node creation rate
        if m1.counters['liquidations'] > 0:
            creation_rate = (m2._total_nodes_created / m1.counters['liquidations']) * 100
            logger.info(f"Node Creation Rate: {creation_rate:.1f}% of liquidations")
        logger.info("")

        # Symbol distribution
        if m2._active_nodes:
            logger.info("SYMBOL DISTRIBUTION (Active Nodes):")
            symbol_counts = {}
            for node in m2._active_nodes.values():
                symbol_counts[node.symbol] = symbol_counts.get(node.symbol, 0) + 1

            for symbol in sorted(symbol_counts.keys()):
                count = symbol_counts[symbol]
                logger.info(f"  {symbol}: {count} nodes")
            logger.info("")

            # Node details
            logger.info("TOP 5 STRONGEST NODES:")
            sorted_nodes = sorted(m2._active_nodes.values(),
                                 key=lambda n: n.strength, reverse=True)[:5]
            for i, node in enumerate(sorted_nodes, 1):
                logger.info(f"  {i}. {node.symbol} @ ${node.price_center:.2f}")
                logger.info(f"     Strength: {node.strength:.3f} | " +
                          f"Interactions: {node.interaction_count} | " +
                          f"Liquidations: {node.liquidation_proximity_count}")
            logger.info("")

        # Success criteria
        logger.info("SUCCESS CRITERIA:")
        criteria = {
            "Nodes created from liquidations": m2._total_nodes_created > 0,
            "Multiple symbols have nodes": len(set(n.symbol for n in m2._active_nodes.values())) > 1 if m2._active_nodes else False,
            "Trades updating nodes": m2._total_interactions > m2._total_nodes_created,
            "Lifecycle management active": m2._last_state_update_ts is not None,
            "At least 1 liquidation ingested": m1.counters['liquidations'] > 0
        }

        for criterion, passed in criteria.items():
            status = "✓" if passed else "✗"
            logger.info(f"  {status} {criterion}")

        logger.info("")

        # Overall verdict
        all_passed = all(criteria.values())
        if all_passed:
            logger.info("="*70)
            logger.info("✓✓✓ M2 POPULATION VERIFICATION SUCCESSFUL ✓✓✓")
            logger.info("="*70)
            logger.info("M2 memory nodes are being created and maintained from live data!")
        else:
            logger.warning("="*70)
            logger.warning("⚠ M2 POPULATION VERIFICATION INCOMPLETE - See criteria above")
            logger.warning("="*70)
            if m1.counters['liquidations'] == 0:
                logger.warning("NOTE: No liquidations occurred during test period.")
                logger.warning("      This is NORMAL in low-volatility conditions.")
                logger.warning("      Extend test duration or wait for volatile period.")


async def main():
    """Run 3-minute M2 population test."""
    monitor = M2PopulationMonitor()
    await monitor.run_test(duration_seconds=180)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        sys.exit(0)
