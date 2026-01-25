#!/usr/bin/env python3
"""
Binance Data Collector Runner.

Runs the Binance collector service to continuously fetch funding rates
and spot prices for cross-exchange analysis.

Usage:
    python scripts/run_binance_collector.py [--db path] [--funding-interval 60]
    python scripts/run_binance_collector.py --once  # Single poll
    python scripts/run_binance_collector.py --status  # Check last data

This collector runs alongside the main HLP24 Hyperliquid collector.
Data is used for HLP25 Part 1 (funding lead) and Part 8 (basis) validation.
"""

import argparse
import sys
import signal
import time
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from runtime.logging.execution_db import ResearchDatabase
from runtime.binance import (
    BinanceCollector,
    CollectorConfig,
    CollectorState,
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def print_header():
    """Print startup header."""
    print()
    print("=" * 60)
    print("BINANCE DATA COLLECTOR")
    print("=" * 60)
    print()


def print_status(status: dict):
    """Print collector status."""
    print(f"State: {status['state']}")
    print(f"Symbols: {', '.join(status['symbols'])}")
    print(f"Funding interval: {status['funding_interval']}s")
    print(f"Spot interval: {status['spot_interval']}s")
    print()
    print("Statistics:")
    stats = status['stats']
    print(f"  Funding polls: {stats['funding_polls']}")
    print(f"  Spot polls: {stats['spot_polls']}")
    print(f"  Funding records: {stats['funding_records']}")
    print(f"  Spot records: {stats['spot_records']}")
    print(f"  Errors: {stats['errors']}")
    if stats['last_funding_poll_ts']:
        last_funding = datetime.fromtimestamp(stats['last_funding_poll_ts'] / 1e9)
        print(f"  Last funding poll: {last_funding}")
    if stats['last_spot_poll_ts']:
        last_spot = datetime.fromtimestamp(stats['last_spot_poll_ts'] / 1e9)
        print(f"  Last spot poll: {last_spot}")
    print()


def check_database_status(db: ResearchDatabase):
    """Check status of Binance data in database."""
    print("Checking database status...")
    print()

    # Check funding snapshots
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT COUNT(*), MIN(snapshot_ts), MAX(snapshot_ts)
        FROM binance_funding_snapshots
    """)
    row = cursor.fetchone()
    funding_count = row[0]
    funding_min_ts = row[1]
    funding_max_ts = row[2]

    print("Funding Snapshots:")
    print(f"  Total records: {funding_count}")
    if funding_min_ts:
        min_dt = datetime.fromtimestamp(funding_min_ts / 1e9)
        max_dt = datetime.fromtimestamp(funding_max_ts / 1e9)
        print(f"  Date range: {min_dt} to {max_dt}")

    # Check by coin
    cursor.execute("""
        SELECT coin, COUNT(*) as cnt
        FROM binance_funding_snapshots
        GROUP BY coin
        ORDER BY cnt DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        print("  By coin:")
        for row in rows:
            print(f"    {row[0]}: {row[1]} records")
    print()

    # Check spot snapshots
    cursor.execute("""
        SELECT COUNT(*), MIN(snapshot_ts), MAX(snapshot_ts)
        FROM spot_price_snapshots
    """)
    row = cursor.fetchone()
    spot_count = row[0]
    spot_min_ts = row[1]
    spot_max_ts = row[2]

    print("Spot Price Snapshots:")
    print(f"  Total records: {spot_count}")
    if spot_min_ts:
        min_dt = datetime.fromtimestamp(spot_min_ts / 1e9)
        max_dt = datetime.fromtimestamp(spot_max_ts / 1e9)
        print(f"  Date range: {min_dt} to {max_dt}")

    # Check by coin
    cursor.execute("""
        SELECT coin, COUNT(*) as cnt
        FROM spot_price_snapshots
        GROUP BY coin
        ORDER BY cnt DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        print("  By coin:")
        for row in rows:
            print(f"    {row[0]}: {row[1]} records")
    print()


def run_once(db: ResearchDatabase, symbols: list, logger):
    """Run a single poll cycle."""
    print("Running single poll cycle...")
    print()

    config = CollectorConfig(symbols=symbols)
    collector = BinanceCollector(db, config, logger)

    result = collector.poll_once()

    print(f"Funding records stored: {result['funding_records']}")
    print(f"Spot records stored: {result['spot_records']}")
    print(f"Symbols polled: {', '.join(result['symbols'])}")
    print()
    print("Poll complete.")


def run_continuous(
    db: ResearchDatabase,
    symbols: list,
    funding_interval: float,
    spot_interval: float,
    logger
):
    """Run continuous collection."""
    config = CollectorConfig(
        symbols=symbols,
        funding_poll_interval=funding_interval,
        spot_poll_interval=spot_interval
    )

    collector = BinanceCollector(db, config, logger)

    # Handle shutdown gracefully
    def signal_handler(signum, frame):
        print()
        print("Shutdown signal received...")
        collector.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"Starting continuous collection...")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Funding interval: {funding_interval}s")
    print(f"  Spot interval: {spot_interval}s")
    print()
    print("Press Ctrl+C to stop")
    print()

    collector.start()

    # Monitor loop
    try:
        while collector.state in (CollectorState.RUNNING, CollectorState.PAUSED, CollectorState.ERROR):
            time.sleep(30)
            status = collector.get_status()
            stats = status['stats']
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Funding: {stats['funding_records']} records, "
                f"Spot: {stats['spot_records']} records, "
                f"Errors: {stats['errors']}"
            )
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Binance Data Collector - Funding rates and spot prices'
    )
    parser.add_argument(
        '--db', '-d',
        type=str,
        default='logs/execution.db',
        help='Path to database file (default: logs/execution.db)'
    )
    parser.add_argument(
        '--funding-interval', '-f',
        type=float,
        default=60.0,
        help='Funding rate poll interval in seconds (default: 60)'
    )
    parser.add_argument(
        '--spot-interval', '-s',
        type=float,
        default=10.0,
        help='Spot price poll interval in seconds (default: 10)'
    )
    parser.add_argument(
        '--symbols',
        type=str,
        default='BTC,ETH,SOL,DOGE,XRP,AVAX,LINK,ARB,OP,SUI',
        help='Comma-separated list of symbols to track'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run a single poll cycle and exit'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Check database status and exit'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    print_header()

    # Parse symbols
    symbols = [s.strip().upper() for s in args.symbols.split(',')]

    # Ensure database directory exists
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = ResearchDatabase(args.db)

    try:
        if args.status:
            check_database_status(db)
        elif args.once:
            run_once(db, symbols, logger)
        else:
            run_continuous(
                db,
                symbols,
                args.funding_interval,
                args.spot_interval,
                logger
            )
    finally:
        db.close()


if __name__ == '__main__':
    main()
