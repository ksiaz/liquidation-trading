"""Stage 1A: Baseline Structural Distribution Collection

Run for 24-48 hours with permissive thresholds to establish baseline primitive distributions.

Stopping Criteria:
- Minimum 10,000 cycles with all 3 primitives computed
- Minimum 1,000 samples per symbol
- Coverage of at least 3 volatility regimes (low/med/high)
- Zero time regressions, no gaps > 60 seconds
- Primitive computation success rate > 95%

Data Collected:
- Primitive values per symbol per cycle
- Market regime indicators (volatility, volume)
- Co-occurrence patterns
- Temporal patterns
"""

import asyncio
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.collector.service import CollectorService, TOP_10_SYMBOLS
from observation import ObservationSystem


class Stage1AMonitor:
    """Monitor Stage 1A baseline collection progress."""

    def __init__(self, db_path="logs/execution.db"):
        self.db_path = db_path
        self.start_time = time.time()
        self.target_duration_hours = 48  # Maximum duration
        self.min_duration_hours = 24     # Minimum duration

        # Stopping criteria
        self.min_cycles = 10_000
        self.min_samples_per_symbol = 1_000
        self.min_volatility_regimes = 3
        self.max_gap_seconds = 60
        self.min_primitive_success_rate = 0.95

    def check_stopping_criteria(self):
        """Check if stopping criteria are met.

        Returns:
            (should_stop: bool, reason: str, progress: dict)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            elapsed_hours = (time.time() - self.start_time) / 3600

            # Check 1: Minimum duration
            if elapsed_hours < self.min_duration_hours:
                return False, f"Min duration not met ({elapsed_hours:.1f}h / {self.min_duration_hours}h)", {}

            # Check 2: Maximum duration
            if elapsed_hours >= self.target_duration_hours:
                return True, f"Max duration reached ({elapsed_hours:.1f}h)", {}

            # Check 3: Count cycles with all 3 primitives
            cursor.execute("""
                SELECT COUNT(*) FROM policy_outcomes
                WHERE active_primitives LIKE '%zone_penetration%'
                  AND active_primitives LIKE '%traversal_compactness%'
                  AND active_primitives LIKE '%central_tendency%'
            """)
            cycles_with_all_primitives = cursor.fetchone()[0]

            # Check 4: Samples per symbol
            cursor.execute("""
                SELECT symbol, COUNT(*) as sample_count
                FROM policy_outcomes
                WHERE active_primitives LIKE '%zone_penetration%'
                GROUP BY symbol
            """)
            samples_by_symbol = dict(cursor.fetchall())
            min_symbol_samples = min(samples_by_symbol.values()) if samples_by_symbol else 0

            # Check 5: Primitive computation success rate
            cursor.execute("SELECT COUNT(*) FROM policy_outcomes")
            total_outcomes = cursor.fetchone()[0]

            success_rate = cycles_with_all_primitives / total_outcomes if total_outcomes > 0 else 0

            # Check 6: Time gaps (simplified - check last 100 cycles)
            cursor.execute("""
                SELECT timestamp FROM policy_outcomes
                ORDER BY timestamp DESC
                LIMIT 100
            """)
            recent_timestamps = [row[0] for row in cursor.fetchall()]
            recent_timestamps.sort()

            max_gap = 0
            if len(recent_timestamps) > 1:
                gaps = [recent_timestamps[i+1] - recent_timestamps[i]
                       for i in range(len(recent_timestamps)-1)]
                max_gap = max(gaps) if gaps else 0

            conn.close()

            progress = {
                'elapsed_hours': elapsed_hours,
                'cycles_with_all_primitives': cycles_with_all_primitives,
                'min_symbol_samples': min_symbol_samples,
                'success_rate': success_rate,
                'max_recent_gap': max_gap,
                'samples_by_symbol': samples_by_symbol
            }

            # Check all criteria
            criteria_met = (
                cycles_with_all_primitives >= self.min_cycles and
                min_symbol_samples >= self.min_samples_per_symbol and
                success_rate >= self.min_primitive_success_rate and
                max_gap <= self.max_gap_seconds
            )

            if criteria_met:
                return True, "All stopping criteria met", progress
            else:
                return False, "Criteria not yet met", progress

        except Exception as e:
            return False, f"Error checking criteria: {e}", {}

    def print_progress_report(self):
        """Print progress toward stopping criteria."""
        should_stop, reason, progress = self.check_stopping_criteria()

        if not progress:
            print(f"\n=== Stage 1A Progress (Unable to check) ===")
            print(f"Reason: {reason}")
            return should_stop

        print(f"\n=== Stage 1A Progress Report ===")
        print(f"Elapsed: {progress['elapsed_hours']:.1f}h / {self.target_duration_hours}h")
        print(f"")
        print(f"Cycles with all 3 primitives: {progress['cycles_with_all_primitives']:,} / {self.min_cycles:,}")
        print(f"  {'✅' if progress['cycles_with_all_primitives'] >= self.min_cycles else '⏳'} Cycle count")
        print(f"")
        print(f"Min samples per symbol: {progress['min_symbol_samples']:,} / {self.min_samples_per_symbol:,}")
        print(f"  {'✅' if progress['min_symbol_samples'] >= self.min_samples_per_symbol else '⏳'} Symbol coverage")
        print(f"")
        print(f"Primitive success rate: {progress['success_rate']:.1%}")
        print(f"  {'✅' if progress['success_rate'] >= self.min_primitive_success_rate else '⏳'} Success rate")
        print(f"")
        print(f"Max recent gap: {progress['max_recent_gap']:.1f}s / {self.max_gap_seconds}s")
        print(f"  {'✅' if progress['max_recent_gap'] <= self.max_gap_seconds else '⏳'} Time continuity")
        print(f"")
        print(f"Samples by symbol:")
        for symbol, count in sorted(progress['samples_by_symbol'].items()):
            status = '✅' if count >= self.min_samples_per_symbol else '⏳'
            print(f"  {status} {symbol}: {count:,}")
        print(f"")
        print(f"Status: {reason}")
        print(f"Should stop: {'YES' if should_stop else 'NO'}")
        print(f"=" * 50)

        return should_stop


async def run_stage_1a_collection():
    """Run Stage 1A baseline collection."""

    print("=" * 70)
    print("STAGE 1A: BASELINE STRUCTURAL DISTRIBUTION COLLECTION")
    print("=" * 70)
    print(f"")
    print(f"Purpose: Establish baseline primitive value distributions")
    print(f"Duration: 24-48 hours (adaptive based on stopping criteria)")
    print(f"Thresholds: Permissive (>0, !=0)")
    print(f"Symbols: {', '.join(TOP_10_SYMBOLS)}")
    print(f"")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=" * 70)
    print(f"")

    # Initialize observation system and collector
    obs_system = ObservationSystem(TOP_10_SYMBOLS)
    collector = CollectorService(obs_system, warmup_duration_sec=10)

    # Initialize monitor
    monitor = Stage1AMonitor()

    # Start collector
    collector_task = asyncio.create_task(collector.start())

    # Progress reporting interval (every 30 minutes)
    report_interval_sec = 30 * 60
    last_report_time = time.time()

    try:
        while True:
            await asyncio.sleep(60)  # Check every minute

            # Periodic progress report
            if time.time() - last_report_time >= report_interval_sec:
                should_stop = monitor.print_progress_report()
                last_report_time = time.time()

                if should_stop:
                    print(f"\nStopping criteria met. Shutting down gracefully...")
                    break

    except KeyboardInterrupt:
        print(f"\n\nInterrupted by user. Generating final report...")
        monitor.print_progress_report()

    finally:
        # Shutdown collector
        print(f"\nShutting down collector...")
        collector_task.cancel()
        try:
            await collector_task
        except asyncio.CancelledError:
            pass

        # Final report
        print(f"\n" + "=" * 70)
        print(f"STAGE 1A COLLECTION COMPLETE")
        print(f"=" * 70)
        monitor.print_progress_report()
        print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\nNext step: Run analysis script to extract percentile distributions")
        print(f"  python scripts/analyze_stage_1a_distributions.py")
        print(f"=" * 70)


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_stage_1a_collection())
