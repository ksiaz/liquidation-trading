#!/usr/bin/env python3
"""
HLP25 Validation Runner.

Main entry point for validating HLP25 hypotheses against HLP24 data.

Usage:
    python scripts/run_hlp25_validation.py [--days 30] [--db path/to/db]

Output:
    Validation report showing which hypotheses hold and which fail.
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from runtime.logging.execution_db import ResearchDatabase
from analysis.cascade_labeler import CascadeLabeler
from analysis.validators import (
    WaveStructureValidator,
    AbsorptionValidator,
    OIConcentrationValidator,
    CrossAssetValidator,
    ValidationResult
)


def now_ns() -> int:
    """Current time in nanoseconds."""
    return int(time.time() * 1_000_000_000)


def print_header():
    """Print report header."""
    print()
    print("=" * 60)
    print("HLP25 VALIDATION REPORT")
    print("=" * 60)
    print()


def print_result(result: ValidationResult):
    """Print a single validation result."""
    status_symbol = {
        'VALIDATED': '[PASS]',
        'FAILED': '[FAIL]',
        'INSUFFICIENT_DATA': '[----]'
    }.get(result.status, '[????]')

    # Format success rate
    rate_str = f"{result.success_rate * 100:.1f}%" if result.total_events > 0 else "N/A"

    print(f"{status_symbol} {result.hypothesis_name}")
    print(f"         Status: {result.status}")
    print(f"         Events: {result.total_events} total, {result.supporting_events} supporting")
    print(f"         Rate:   {rate_str}")

    if result.calibrated_threshold is not None:
        print(f"         Threshold: {result.calibrated_threshold}")

    if result.details:
        print(f"         Details: {result.details}")

    print()


def print_summary(results: list):
    """Print summary of all results."""
    validated = sum(1 for r in results if r.status == 'VALIDATED')
    failed = sum(1 for r in results if r.status == 'FAILED')
    insufficient = sum(1 for r in results if r.status == 'INSUFFICIENT_DATA')

    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Validated:         {validated}")
    print(f"  Failed:            {failed}")
    print(f"  Insufficient Data: {insufficient}")
    print(f"  Total Tested:      {len(results)}")
    print("=" * 60)
    print()


def run_validation(db_path: str, days: int = 30, verbose: bool = False) -> list:
    """Run validation pipeline.

    Args:
        db_path: Path to database
        days: Number of days to analyze
        verbose: Print detailed output

    Returns:
        List of ValidationResult objects
    """
    if verbose:
        print(f"Loading database from: {db_path}")

    db = ResearchDatabase(db_path)

    # Calculate time range
    end_ts = now_ns()
    start_ts = end_ts - (days * 24 * 3600 * 1_000_000_000)

    if verbose:
        print(f"Analyzing {days} days of data")
        print(f"  Start: {start_ts}")
        print(f"  End:   {end_ts}")
        print()

    # Step 1: Label cascades from raw data
    if verbose:
        print("Step 1: Labeling cascade events...")

    labeler = CascadeLabeler(db)
    cascades = labeler.label_all(start_ts=start_ts, end_ts=end_ts)

    if verbose:
        stats = labeler.get_statistics(cascades)
        print(f"  Found {len(cascades)} cascade events")
        print(f"  By coin: {stats['by_coin']}")
        print(f"  By outcome: {stats['by_outcome']}")
        print()

    # Step 2: Run validators
    if verbose:
        print("Step 2: Running hypothesis validators...")
        print()

    validators = [
        WaveStructureValidator(),
        AbsorptionValidator(),
        OIConcentrationValidator(),
        CrossAssetValidator(),
    ]

    results = []
    for validator in validators:
        if verbose:
            print(f"  Testing: {validator.name}")

        result = validator.validate(cascades)
        results.append(result)

        # Log to database
        db.log_validation_result(
            hypothesis_name=result.hypothesis_name,
            run_ts=end_ts,
            total_events=result.total_events,
            supporting_events=result.supporting_events,
            success_rate=result.success_rate,
            calibrated_threshold=result.calibrated_threshold,
            status=result.status,
            notes=str(result.details) if result.details else None
        )

    db.close()
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Validate HLP25 hypotheses against HLP24 data'
    )
    parser.add_argument(
        '--db', '-d',
        type=str,
        default='logs/execution.db',
        help='Path to database file (default: logs/execution.db)'
    )
    parser.add_argument(
        '--days', '-n',
        type=int,
        default=30,
        help='Number of days to analyze (default: 30)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed output'
    )

    args = parser.parse_args()

    # Check database exists
    if not Path(args.db).exists():
        print(f"Error: Database not found: {args.db}")
        print()
        print("Make sure you have collected data using the HLP24 collector.")
        print("The database should be at: logs/execution.db")
        sys.exit(1)

    print_header()

    try:
        results = run_validation(
            db_path=args.db,
            days=args.days,
            verbose=args.verbose
        )

        if not results:
            print("No validation results generated.")
            print("Check if the database contains HLP24 raw data.")
            sys.exit(1)

        # Print results
        for result in results:
            print_result(result)

        print_summary(results)

        # Exit with appropriate code
        failed_count = sum(1 for r in results if r.status == 'FAILED')
        if failed_count > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
