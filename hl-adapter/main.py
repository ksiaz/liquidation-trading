#!/usr/bin/env python3
"""
HL Node Adapter - Entry Point.

Standalone process that reads HL node data and emits canonical events.

Usage:
    python main.py [--data-path PATH] [--symbols SYM1,SYM2,...] [--checkpoint PATH]

Output:
    JSON events to stdout (one per line)
    Status messages to stderr
"""

import argparse
import signal
import sys
from pathlib import Path

from adapter import NodeAdapter


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='HL Node Adapter - reads node data and emits events'
    )

    parser.add_argument(
        '--data-path',
        type=Path,
        default=None,
        help='Path to HL data directory (default: ~/hl/data)'
    )

    parser.add_argument(
        '--symbols',
        type=str,
        default=None,
        help='Comma-separated list of symbols to focus on (default: all)'
    )

    parser.add_argument(
        '--checkpoint',
        type=Path,
        default=None,
        help='Path to checkpoint file (default: ~/.hl-adapter/checkpoint.json)'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Parse focus symbols
    focus_symbols = None
    if args.symbols:
        focus_symbols = set(s.strip().upper() for s in args.symbols.split(','))
        print(f"[MAIN] Focus symbols: {focus_symbols}", file=sys.stderr)

    # Create adapter
    adapter = NodeAdapter(
        data_path=args.data_path,
        focus_symbols=focus_symbols,
        checkpoint_path=args.checkpoint,
    )

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n[MAIN] Received signal {signum}, shutting down...", file=sys.stderr)
        adapter.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run adapter
    print("[MAIN] Starting HL Node Adapter...", file=sys.stderr)
    adapter.run()


if __name__ == '__main__':
    main()
