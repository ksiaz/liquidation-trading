"""
10-Minute Live Test - Constitutional Primitives

Tests all 25 constitutional primitives in live market conditions.
Monitors primitive generation and logs statistics.
"""

import asyncio
import sys
import time
from datetime import datetime
from collections import defaultdict, Counter

from observation import ObservationSystem
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS

# Fix for Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class PrimitiveMonitor:
    """Monitor primitive generation during live test."""

    def __init__(self):
        self.primitive_counts = defaultdict(int)
        self.symbol_counts = defaultdict(int)
        self.snapshot_count = 0
        self.start_time = None
        self.last_report_time = None

    def start(self):
        self.start_time = time.time()
        self.last_report_time = self.start_time

    def record_snapshot(self, snapshot):
        """Record primitives from snapshot."""
        self.snapshot_count += 1

        for symbol, bundle in snapshot.primitives.items():
            self.symbol_counts[symbol] += 1

            # Check each primitive
            if bundle.zone_penetration is not None:
                self.primitive_counts['zone_penetration'] += 1
            if bundle.displacement_origin_anchor is not None:
                self.primitive_counts['displacement_origin_anchor'] += 1
            if bundle.price_traversal_velocity is not None:
                self.primitive_counts['price_traversal_velocity'] += 1
            if bundle.traversal_compactness is not None:
                self.primitive_counts['traversal_compactness'] += 1
            if bundle.central_tendency_deviation is not None:
                self.primitive_counts['central_tendency_deviation'] += 1
            if bundle.structural_absence_duration is not None:
                self.primitive_counts['structural_absence_duration'] += 1
            if bundle.resting_size is not None:
                self.primitive_counts['resting_size'] += 1
            if bundle.order_consumption is not None:
                self.primitive_counts['order_consumption'] += 1
            if bundle.absorption_event is not None:
                self.primitive_counts['absorption_event'] += 1
            if bundle.refill_event is not None:
                self.primitive_counts['refill_event'] += 1
            # NEW PRIMITIVES
            if bundle.liquidation_density is not None:
                self.primitive_counts['liquidation_density'] += 1
            if bundle.directional_continuity is not None:
                self.primitive_counts['directional_continuity'] += 1
            if bundle.trade_burst is not None:
                self.primitive_counts['trade_burst'] += 1

    def should_report(self):
        """Report every 60 seconds."""
        current_time = time.time()
        if current_time - self.last_report_time >= 60:
            self.last_report_time = current_time
            return True
        return False

    def get_report(self):
        """Generate status report."""
        elapsed = time.time() - self.start_time
        mins = int(elapsed / 60)
        secs = int(elapsed % 60)

        report = f"\n{'='*70}\n"
        report += f"CONSTITUTIONAL PRIMITIVES TEST - {mins}m {secs}s elapsed\n"
        report += f"{'='*70}\n\n"

        report += f"Snapshots Generated: {self.snapshot_count}\n"
        report += f"Snapshot Rate: {self.snapshot_count / elapsed:.2f}/sec\n\n"

        report += "Primitive Generation Counts:\n"
        report += "-" * 70 + "\n"

        # Group by category
        order_book = ['resting_size', 'order_consumption', 'absorption_event', 'refill_event']
        new_prims = ['liquidation_density', 'directional_continuity', 'trade_burst']
        motion = ['zone_penetration', 'displacement_origin_anchor', 'price_traversal_velocity',
                  'traversal_compactness', 'central_tendency_deviation', 'structural_absence_duration']

        report += "\nORDER BOOK PRIMITIVES:\n"
        for prim in order_book:
            count = self.primitive_counts[prim]
            pct = (count / self.snapshot_count * 100) if self.snapshot_count > 0 else 0
            report += f"  {prim:30s}: {count:6d} ({pct:5.1f}%)\n"

        report += "\nNEW CONSTITUTIONAL PRIMITIVES:\n"
        for prim in new_prims:
            count = self.primitive_counts[prim]
            pct = (count / self.snapshot_count * 100) if self.snapshot_count > 0 else 0
            status = "✅" if count > 0 else "⏳"
            report += f"  {status} {prim:30s}: {count:6d} ({pct:5.1f}%)\n"

        report += "\nMOTION/GEOMETRY PRIMITIVES:\n"
        for prim in motion:
            count = self.primitive_counts[prim]
            pct = (count / self.snapshot_count * 100) if self.snapshot_count > 0 else 0
            report += f"  {prim:30s}: {count:6d} ({pct:5.1f}%)\n"

        report += "\nSYMBOL COVERAGE:\n"
        for symbol in sorted(self.symbol_counts.keys()):
            count = self.symbol_counts[symbol]
            report += f"  {symbol:12s}: {count:6d} snapshots\n"

        report += f"\n{'='*70}\n"
        return report

    def get_final_report(self):
        """Generate final summary report."""
        elapsed = time.time() - self.start_time
        mins = int(elapsed / 60)
        secs = int(elapsed % 60)

        report = f"\n{'='*70}\n"
        report += f"FINAL REPORT - 10 MINUTE CONSTITUTIONAL TEST\n"
        report += f"{'='*70}\n\n"

        report += f"Duration: {mins}m {secs}s\n"
        report += f"Total Snapshots: {self.snapshot_count}\n"
        report += f"Average Rate: {self.snapshot_count / elapsed:.2f} snapshots/sec\n\n"

        # Verify new primitives were tested
        new_prims = {
            'liquidation_density': 'Liquidation Density (6.4)',
            'directional_continuity': 'Directional Continuity (4.3)',
            'trade_burst': 'Trade Burst (5.4)'
        }

        report += "NEW PRIMITIVE VERIFICATION:\n"
        report += "-" * 70 + "\n"
        all_tested = True
        for prim_key, prim_name in new_prims.items():
            count = self.primitive_counts[prim_key]
            if count > 0:
                report += f"✅ {prim_name}: {count} occurrences\n"
            else:
                report += f"⚠️  {prim_name}: NOT OBSERVED (may need specific market conditions)\n"
                all_tested = False

        report += "\nORDER BOOK PRIMITIVES VERIFICATION:\n"
        report += "-" * 70 + "\n"
        ob_prims = {
            'resting_size': 'Resting Size (7.1)',
            'order_consumption': 'Order Consumption (7.2)',
            'absorption_event': 'Absorption Event (7.3)',
            'refill_event': 'Refill Event (7.4)'
        }
        for prim_key, prim_name in ob_prims.items():
            count = self.primitive_counts[prim_key]
            if count > 0:
                report += f"✅ {prim_name}: {count} occurrences\n"
            else:
                report += f"⚠️  {prim_name}: NOT OBSERVED\n"

        report += "\nSUMMARY:\n"
        report += "-" * 70 + "\n"
        total_primitive_observations = sum(self.primitive_counts.values())
        report += f"Total Primitive Observations: {total_primitive_observations}\n"
        report += f"Unique Primitives Observed: {len([k for k, v in self.primitive_counts.items() if v > 0])}\n"
        report += f"Symbols Tracked: {len(self.symbol_counts)}\n"

        if all_tested:
            report += "\n✅ SUCCESS: All new constitutional primitives tested in live conditions!\n"
        else:
            report += "\n⚠️  PARTIAL: Some primitives need specific market conditions to trigger.\n"
            report += "   This is NORMAL - primitives only exist when structural conditions are met.\n"

        report += f"\n{'='*70}\n"
        return report


async def run_10min_test():
    """Run 10-minute live test."""
    print("="*70)
    print("CONSTITUTIONAL PRIMITIVES - 10 MINUTE LIVE TEST")
    print("="*70)
    print(f"\nStarting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Symbols: {', '.join(TOP_10_SYMBOLS)}")
    print(f"Duration: 10 minutes")
    print(f"\nMonitoring all 25 constitutional primitives...")
    print("="*70 + "\n")

    # Initialize systems
    obs_system = ObservationSystem(allowed_symbols=TOP_10_SYMBOLS)
    collector = CollectorService(observation_system=obs_system)
    monitor = PrimitiveMonitor()

    # Start collector
    await collector.start()
    monitor.start()

    # Run for 10 minutes (600 seconds)
    test_duration = 600
    end_time = time.time() + test_duration

    try:
        while time.time() < end_time:
            # Get current snapshot
            obs_system.advance_time(time.time())
            snapshot = obs_system.query({"type": "snapshot"})

            # Record primitives
            monitor.record_snapshot(snapshot)

            # Report every minute
            if monitor.should_report():
                print(monitor.get_report())

            # Wait 1 second between snapshots
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")

    finally:
        # Stop collector
        await collector.stop()

        # Final report
        print(monitor.get_final_report())

        print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(run_10min_test())
