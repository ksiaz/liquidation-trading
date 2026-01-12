"""
2-Minute Deployment Verification Test

Tests all system components in live conditions with detailed logging.
Verifies: ObservationSystem, CollectorService, Primitive Generation, Data Ingestion
"""

import asyncio
import sys
import time
import logging
from datetime import datetime
from collections import defaultdict

# Fix Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from observation import ObservationSystem
from observation.types import ObservationStatus
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class DeploymentVerifier:
    """Verify system deployment with detailed logging."""

    def __init__(self):
        self.obs_system = None
        self.collector = None
        self.start_time = None
        self.last_report = None

        # Metrics
        self.status_transitions = []
        self.snapshot_count = 0
        self.primitive_counts = defaultdict(int)
        self.symbol_activity = defaultdict(int)
        self.ingestion_counts = {
            'trades': 0,
            'liquidations': 0,
            'depth_updates': 0
        }

    async def run_test(self, duration_seconds=120):
        """Run 2-minute verification test."""
        logger.info("="*70)
        logger.info("DEPLOYMENT VERIFICATION TEST - 2 MINUTES")
        logger.info("="*70)
        logger.info(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Symbols: {', '.join(TOP_10_SYMBOLS)}")
        logger.info(f"Duration: {duration_seconds} seconds")
        logger.info("="*70)

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
        self.last_report = self.start_time
        end_time = self.start_time + duration_seconds

        logger.info("✓ Collector started - monitoring system...")
        logger.info("")

        try:
            iteration = 0
            while time.time() < end_time:
                iteration += 1
                current_time = time.time()

                # Advance time and get snapshot
                self.obs_system.advance_time(current_time)
                snapshot = self.obs_system.query({"type": "snapshot"})

                # Track status transitions
                if not self.status_transitions or self.status_transitions[-1] != snapshot.status:
                    self.status_transitions.append(snapshot.status)
                    logger.info(f"STATUS CHANGE: {snapshot.status.name}")

                # Record snapshot
                self.snapshot_count += 1

                # Track primitives
                for symbol, bundle in snapshot.primitives.items():
                    self.symbol_activity[symbol] += 1

                    if bundle.zone_penetration:
                        self.primitive_counts['zone_penetration'] += 1
                    if bundle.displacement_origin_anchor:
                        self.primitive_counts['displacement_origin_anchor'] += 1
                    if bundle.price_traversal_velocity:
                        self.primitive_counts['price_traversal_velocity'] += 1
                    if bundle.traversal_compactness:
                        self.primitive_counts['traversal_compactness'] += 1
                    if bundle.central_tendency_deviation:
                        self.primitive_counts['central_tendency_deviation'] += 1
                    if bundle.structural_absence_duration:
                        self.primitive_counts['structural_absence_duration'] += 1
                    if bundle.resting_size:
                        self.primitive_counts['resting_size'] += 1
                    if bundle.order_consumption:
                        self.primitive_counts['order_consumption'] += 1
                    if bundle.absorption_event:
                        self.primitive_counts['absorption_event'] += 1
                    if bundle.refill_event:
                        self.primitive_counts['refill_event'] += 1
                    if bundle.liquidation_density:
                        self.primitive_counts['liquidation_density'] += 1
                    if bundle.directional_continuity:
                        self.primitive_counts['directional_continuity'] += 1
                    if bundle.trade_burst:
                        self.primitive_counts['trade_burst'] += 1

                # Get ingestion stats from M1
                m1 = self.obs_system._m1
                self.ingestion_counts['trades'] = m1.counters['trades']
                self.ingestion_counts['liquidations'] = m1.counters['liquidations']
                self.ingestion_counts['depth_updates'] = m1.counters['depth_updates']

                # Report every 15 seconds
                if current_time - self.last_report >= 15:
                    self.print_progress_report(current_time)
                    self.last_report = current_time

                # Sleep 1 second between snapshots
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

    def print_progress_report(self, current_time):
        """Print progress report every 15 seconds."""
        elapsed = int(current_time - self.start_time)

        logger.info("")
        logger.info(f"--- PROGRESS REPORT ({elapsed}s elapsed) ---")
        logger.info(f"Snapshots: {self.snapshot_count}")
        logger.info(f"Trades Ingested: {self.ingestion_counts['trades']}")
        logger.info(f"Liquidations Ingested: {self.ingestion_counts['liquidations']}")
        logger.info(f"Depth Updates: {self.ingestion_counts['depth_updates']}")

        total_primitives = sum(self.primitive_counts.values())
        logger.info(f"Total Primitives Generated: {total_primitives}")

        if total_primitives > 0:
            top_primitives = sorted(self.primitive_counts.items(),
                                   key=lambda x: x[1], reverse=True)[:5]
            logger.info("Top Primitives:")
            for prim, count in top_primitives:
                logger.info(f"  - {prim}: {count}")
        logger.info("")

    def print_final_report(self):
        """Print final verification report."""
        elapsed = time.time() - self.start_time

        logger.info("="*70)
        logger.info("FINAL DEPLOYMENT VERIFICATION REPORT")
        logger.info("="*70)
        logger.info(f"Test Duration: {elapsed:.1f} seconds")
        logger.info(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # Status transitions
        logger.info("STATUS TRANSITIONS:")
        for i, status in enumerate(self.status_transitions, 1):
            logger.info(f"  {i}. {status.name}")
        logger.info("")

        # Verify ACTIVE status achieved
        if ObservationStatus.ACTIVE in self.status_transitions:
            logger.info("✓ System successfully transitioned to ACTIVE status")
        else:
            logger.error("✗ System did NOT reach ACTIVE status")

        logger.info("")

        # Ingestion metrics
        logger.info("DATA INGESTION METRICS:")
        logger.info(f"  Trades Ingested: {self.ingestion_counts['trades']}")
        logger.info(f"  Liquidations Ingested: {self.ingestion_counts['liquidations']}")
        logger.info(f"  Depth Updates: {self.ingestion_counts['depth_updates']}")

        total_ingested = sum(self.ingestion_counts.values())
        rate = total_ingested / elapsed if elapsed > 0 else 0
        logger.info(f"  Total Events: {total_ingested}")
        logger.info(f"  Ingestion Rate: {rate:.1f} events/sec")
        logger.info("")

        # Snapshot metrics
        logger.info("SNAPSHOT METRICS:")
        logger.info(f"  Total Snapshots: {self.snapshot_count}")
        snapshot_rate = self.snapshot_count / elapsed if elapsed > 0 else 0
        logger.info(f"  Snapshot Rate: {snapshot_rate:.2f}/sec")
        logger.info("")

        # Primitive generation
        logger.info("PRIMITIVE GENERATION:")
        total_primitives = sum(self.primitive_counts.values())
        logger.info(f"  Total Primitives: {total_primitives}")
        logger.info(f"  Unique Primitive Types: {len([k for k, v in self.primitive_counts.items() if v > 0])}")
        logger.info("")

        if self.primitive_counts:
            logger.info("  Breakdown by Type:")
            for prim in sorted(self.primitive_counts.keys()):
                count = self.primitive_counts[prim]
                if count > 0:
                    logger.info(f"    {prim:35s}: {count:6d}")
        else:
            logger.info("  ⚠ No primitives generated (may need longer observation period)")

        logger.info("")

        # Symbol activity
        logger.info("SYMBOL ACTIVITY:")
        active_symbols = [s for s, count in self.symbol_activity.items() if count > 0]
        logger.info(f"  Active Symbols: {len(active_symbols)}/{len(TOP_10_SYMBOLS)}")
        if active_symbols:
            for symbol in sorted(active_symbols):
                count = self.symbol_activity[symbol]
                logger.info(f"    {symbol}: {count} snapshots")
        logger.info("")

        # Success criteria
        logger.info("SUCCESS CRITERIA:")
        criteria = {
            "System reached ACTIVE status": ObservationStatus.ACTIVE in self.status_transitions,
            "Data ingestion working (>0 events)": total_ingested > 0,
            "Snapshots generated (>100)": self.snapshot_count > 100,
            "No system halts": ObservationStatus.FAILED not in self.status_transitions,
            "Multiple symbols active": len(active_symbols) > 1
        }

        for criterion, passed in criteria.items():
            status = "✓" if passed else "✗"
            logger.info(f"  {status} {criterion}")

        logger.info("")

        # Overall verdict
        all_passed = all(criteria.values())
        if all_passed:
            logger.info("="*70)
            logger.info("✓✓✓ DEPLOYMENT VERIFICATION SUCCESSFUL ✓✓✓")
            logger.info("="*70)
        else:
            logger.warning("="*70)
            logger.warning("⚠ DEPLOYMENT VERIFICATION INCOMPLETE - See criteria above")
            logger.warning("="*70)


async def main():
    """Run 2-minute deployment test."""
    verifier = DeploymentVerifier()
    await verifier.run_test(duration_seconds=120)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        sys.exit(0)
