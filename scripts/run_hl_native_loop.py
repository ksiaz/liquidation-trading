#!/usr/bin/env python3
"""
HL-Native Decision Loop Runner

PURPOSE: Answer one question:
"Does Hyperliquid data alone ever produce a non-trivial, explainable trading signal?"

CONSTRAINTS:
- NO Binance data
- NO regime classification
- NO VWAP / ATR / orderflow
- NO paper trading or execution
- NO approximations

This script connects to the HL node adapter and runs the minimal HL-native
decision loop, logging any non-SKIP decisions.

Usage:
    python scripts/run_hl_native_loop.py --duration 300 --output decisions.json
"""

import argparse
import sys
import os
import time
from datetime import datetime
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.hl_native import (
    HLNativeAdapter,
    HLNativeDecisionLoop,
    DecisionRecord,
    Decision,
    run_hl_native_loop,
)


def format_decision_log(record: DecisionRecord) -> str:
    """Format a decision record for logging."""
    ts = datetime.fromtimestamp(record.timestamp).strftime('%H:%M:%S')
    oracle = f"@${record.oracle_price:,.2f}" if record.oracle_price else ""

    return (
        f"[{ts}] {record.symbol} {record.decision}\n"
        f"  Reason: {record.reason}\n"
        f"  Value: ${record.total_value_usd:,.0f} "
        f"(Long: ${record.long_value_usd:,.0f}, Short: ${record.short_value_usd:,.0f})\n"
        f"  Events: {record.event_count} in 60s window {oracle}"
    )


def main():
    parser = argparse.ArgumentParser(
        description='Run HL-Native Decision Loop',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run for 5 minutes
  python scripts/run_hl_native_loop.py --duration 300

  # Run with specific symbols
  python scripts/run_hl_native_loop.py --symbols BTC ETH --duration 600

  # Export decisions to JSON
  python scripts/run_hl_native_loop.py --duration 300 --output decisions.json

  # Connect to custom adapter address
  python scripts/run_hl_native_loop.py --address 192.168.1.100:50051
"""
    )

    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=60,
        help='Duration to run in seconds (default: 60)'
    )

    parser.add_argument(
        '--symbols', '-s',
        nargs='+',
        default=['BTC', 'ETH', 'SOL'],
        help='Symbols to track (default: BTC ETH SOL)'
    )

    parser.add_argument(
        '--address', '-a',
        default='localhost:50051',
        help='gRPC adapter address (default: localhost:50051)'
    )

    parser.add_argument(
        '--output', '-o',
        help='Output file for JSON export'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print all decisions (including SKIP)'
    )

    args = parser.parse_args()

    print("="*60)
    print("HL-NATIVE DECISION LOOP")
    print("="*60)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {args.duration}s")
    print(f"Symbols: {args.symbols}")
    print(f"Adapter: {args.address}")
    print()
    print("METRIC: Liquidation Side Imbalance")
    print("  - Tracks ratio of long vs short liquidation value")
    print("  - Signal when >75% one-sided AND value >$100k")
    print()
    print("DECISIONS:")
    print("  LONG_PRESSURE  = Heavy short liquidations → upward pressure")
    print("  SHORT_PRESSURE = Heavy long liquidations → downward pressure")
    print("  SKIP           = No signal (balanced or low volume)")
    print("="*60)
    print()

    # Track decisions for final summary
    all_decisions = []
    non_skip_decisions = []

    def on_decision(record: DecisionRecord):
        all_decisions.append(record)
        if args.verbose:
            print(f"[DECISION] {record.symbol}: {record.decision} - {record.reason}")

    def on_non_skip(record: DecisionRecord):
        non_skip_decisions.append(record)
        print("\n" + "="*50)
        print("*** NON-SKIP SIGNAL DETECTED ***")
        print("="*50)
        print(format_decision_log(record))
        print("="*50 + "\n")

    # Create adapter
    adapter = HLNativeAdapter(
        symbols=args.symbols,
        address=args.address,
        on_decision=on_decision,
        on_non_skip_decision=on_non_skip,
    )

    # Start
    print("Connecting to adapter...")
    if not adapter.start():
        print("\nFailed to connect. Make sure the HL node adapter is running:")
        print("  cd ~/.hl-node-adapter && cargo run --release")
        sys.exit(1)

    print(f"Connected! Running for {args.duration}s...\n")
    start_time = time.time()

    try:
        while time.time() - start_time < args.duration:
            time.sleep(5.0)

            # Print periodic status
            elapsed = int(time.time() - start_time)
            metrics = adapter.get_loop().get_metrics()
            print(f"[{elapsed:4d}s] Events: {metrics['events_processed']:5d} | "
                  f"Decisions: {metrics['decisions_made']:5d} | "
                  f"Signals: {metrics['non_skip_decisions']:3d}")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    # Stop
    adapter.stop()

    # Final summary
    loop = adapter.get_loop()
    metrics = loop.get_metrics()
    duration = time.time() - start_time

    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Duration: {duration:.1f}s")
    print(f"Events processed: {metrics['events_processed']}")
    print(f"Decisions made: {metrics['decisions_made']}")
    print(f"Non-SKIP signals: {metrics['non_skip_decisions']}")
    print(f"Skip rate: {metrics['skip_rate']:.1%}")
    print()

    if non_skip_decisions:
        print("NON-SKIP DECISIONS:")
        print("-"*40)
        for record in non_skip_decisions:
            print(format_decision_log(record))
            print()
    else:
        print("No non-SKIP signals detected during this run.")
        print("This is expected - signals require:")
        print("  - >$100k liquidation value in 60s window")
        print("  - >75% one-sided (mostly longs OR mostly shorts)")
        print()

    # Export if requested
    if args.output:
        loop.export_decisions_json(args.output)
        print(f"Decisions exported to: {args.output}")

    print("\n" + "="*60)
    print("END OF RUN")
    print("="*60)


if __name__ == '__main__':
    main()
