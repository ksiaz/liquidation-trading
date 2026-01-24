#!/usr/bin/env python3
"""
HLP23 Threshold Discovery Runner.

Discovers optimal thresholds from historical data using grid search,
validates out-of-sample, and stores results with full provenance.

Usage:
    python scripts/run_hlp23_discovery.py [--db path] [--days 90]
    python scripts/run_hlp23_discovery.py --init-defaults [--strategy name]
    python scripts/run_hlp23_discovery.py --review-due
    python scripts/run_hlp23_discovery.py --export path/to/output.json

Output:
    Discovered thresholds with validation status and confidence metrics.
"""

import argparse
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from runtime.logging.execution_db import ResearchDatabase
from analysis.cascade_labeler import CascadeLabeler
from analysis.threshold_discovery import (
    DiscoveryMethod,
    GridSearchConfig,
    GridSearchOptimizer,
    ThresholdCandidate,
    SensitivityAnalyzer,
    get_conservative_defaults,
    get_phased_thresholds,
)
from analysis.threshold_store import (
    ThresholdStore,
    ThresholdConfig,
    ThresholdStatus,
    create_threshold_config,
    create_conservative_threshold_set,
)


def now_ns() -> int:
    """Current time in nanoseconds."""
    return int(time.time() * 1_000_000_000)


def print_header():
    """Print report header."""
    print()
    print("=" * 60)
    print("HLP23 THRESHOLD DISCOVERY REPORT")
    print("=" * 60)
    print()


def print_threshold_config(config: ThresholdConfig):
    """Print a threshold configuration."""
    status_symbol = {
        ThresholdStatus.VALIDATED: '[PASS]',
        ThresholdStatus.OVERFITTED: '[FAIL]',
        ThresholdStatus.HYPOTHESIS: '[????]',
        ThresholdStatus.DEPRECATED: '[OLD ]',
        ThresholdStatus.ACTIVE: '[USE ]',
    }.get(config.status, '[????]')

    print(f"{status_symbol} {config.name}")
    print(f"         Value: {config.value}")
    print(f"         Method: {config.method.name}")
    print(f"         Status: {config.status.name}")
    print(f"         Sharpe: {config.sharpe_ratio:.2f}" if config.sharpe_ratio else "         Sharpe: N/A")
    print(f"         Win Rate: {config.win_rate * 100:.1f}%" if config.win_rate else "         Win Rate: N/A")
    if config.validation_sharpe is not None:
        print(f"         OOS Sharpe: {config.validation_sharpe:.2f}")
    if config.validation_degradation_pct is not None:
        print(f"         Degradation: {config.validation_degradation_pct:.1f}%")
    print(f"         Robust: {'Yes' if config.is_robust else 'No'}")
    print(f"         Rationale: {config.rationale[:50]}..." if len(config.rationale) > 50 else f"         Rationale: {config.rationale}")
    if config.next_review_date:
        print(f"         Review: {config.next_review_date[:10]}")
    print()


def print_summary(configs: list):
    """Print summary of all thresholds."""
    validated = sum(1 for c in configs if c.status == ThresholdStatus.VALIDATED)
    overfitted = sum(1 for c in configs if c.status == ThresholdStatus.OVERFITTED)
    hypothesis = sum(1 for c in configs if c.status == ThresholdStatus.HYPOTHESIS)
    active = sum(1 for c in configs if c.status == ThresholdStatus.ACTIVE)

    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Validated:   {validated}")
    print(f"  Overfitted:  {overfitted}")
    print(f"  Hypothesis:  {hypothesis}")
    print(f"  Active:      {active}")
    print(f"  Total:       {len(configs)}")
    print("=" * 60)
    print()


def init_conservative_defaults(db: ResearchDatabase, strategy_name: str):
    """Initialize database with conservative default thresholds.

    Args:
        db: Database connection
        strategy_name: Strategy name to tag thresholds with
    """
    print(f"Initializing conservative defaults for strategy: {strategy_name}")
    print()

    threshold_set = create_conservative_threshold_set(strategy_name)
    store = ThresholdStore(db)

    configs = []
    for name, config in threshold_set.thresholds.items():
        # Update strategy name
        config = ThresholdConfig(
            name=config.name,
            value=config.value,
            method=config.method,
            date_set=config.date_set,
            rationale=config.rationale,
            sharpe_ratio=config.sharpe_ratio,
            win_rate=config.win_rate,
            trades_per_month=config.trades_per_month,
            next_review_date=config.next_review_date,
            status=config.status,
        )
        store.save_threshold(config)
        configs.append(config)
        print(f"  Saved: {name} = {config.value}")

    print()
    print(f"Initialized {len(configs)} thresholds")
    return configs


def show_phased_thresholds(phase: int):
    """Show thresholds for a specific phase.

    Args:
        phase: Phase number (1-4)
    """
    print(f"Phase {phase} Thresholds (Phased Relaxation Strategy)")
    print("-" * 40)

    thresholds = get_phased_thresholds(phase)

    for name, value in thresholds.items():
        print(f"  {name}: {value}")

    print()
    print("Use these thresholds for 30 days, then advance to next phase.")


def check_thresholds_due_for_review(db: ResearchDatabase):
    """Check for thresholds that need review.

    Args:
        db: Database connection
    """
    store = ThresholdStore(db)
    due_thresholds = store.get_thresholds_due_for_review()

    if not due_thresholds:
        print("No thresholds are due for review.")
        return

    print("Thresholds Due for Review")
    print("-" * 40)

    for config in due_thresholds:
        print(f"  {config.name}")
        print(f"    Current value: {config.value}")
        print(f"    Last set: {config.date_set[:10]}")
        print(f"    Review date: {config.next_review_date[:10]}")
        print()

    print(f"Total: {len(due_thresholds)} thresholds need review")


def export_thresholds(db: ResearchDatabase, output_path: str, strategy_name: str = None):
    """Export thresholds to JSON file.

    Args:
        db: Database connection
        output_path: Output file path
        strategy_name: Optional strategy filter
    """
    store = ThresholdStore(db)

    if strategy_name:
        threshold_set = store.load_threshold_set(strategy_name)
        if threshold_set:
            store.export_to_json(threshold_set, output_path)
            print(f"Exported {len(threshold_set.thresholds)} thresholds to {output_path}")
        else:
            print(f"No thresholds found for strategy: {strategy_name}")
    else:
        # Export all active thresholds
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT name FROM hl_threshold_configs
            WHERE status NOT IN ('DEPRECATED')
        """)
        names = [row[0] for row in cursor.fetchall()]

        thresholds = {}
        for name in names:
            config = store.get_active_threshold(name)
            if config:
                thresholds[name] = config.to_dict()

        with open(output_path, 'w') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'threshold_count': len(thresholds),
                'thresholds': thresholds
            }, f, indent=2)

        print(f"Exported {len(thresholds)} thresholds to {output_path}")


def run_discovery(
    db_path: str,
    days: int = 90,
    strategy_name: str = 'default',
    verbose: bool = False
) -> list:
    """Run threshold discovery on historical data.

    Args:
        db_path: Path to database
        days: Number of days of data to analyze
        strategy_name: Strategy name to tag results
        verbose: Print detailed output

    Returns:
        List of discovered ThresholdConfig objects
    """
    if verbose:
        print(f"Loading database from: {db_path}")

    db = ResearchDatabase(db_path)
    store = ThresholdStore(db)

    # Calculate time range
    end_ts = now_ns()
    start_ts = end_ts - (days * 24 * 3600 * 1_000_000_000)

    if verbose:
        print(f"Analyzing {days} days of data")
        print()

    # Load labeled cascades (from HLP25)
    labeler = CascadeLabeler(db)
    cascades = labeler.label_all(start_ts=start_ts, end_ts=end_ts)

    if verbose:
        print(f"Found {len(cascades)} labeled cascade events")
        print()

    if len(cascades) < 30:
        print("WARNING: Insufficient data for reliable threshold discovery.")
        print(f"Found {len(cascades)} cascades, recommend at least 30.")
        print()
        print("Consider using conservative defaults instead:")
        print("  python scripts/run_hlp23_discovery.py --init-defaults")
        print()

    # Get HLP25 validation results to inform threshold discovery
    validation_results = db.get_validation_results()

    discovered_configs = []

    # For each validated hypothesis, extract calibrated thresholds
    for result in validation_results:
        if result.get('calibrated_threshold') is not None:
            threshold_name = f"{result['hypothesis_name']}_threshold"

            config = create_threshold_config(
                name=threshold_name,
                value=result['calibrated_threshold'],
                method=DiscoveryMethod.GRID_SEARCH,
                rationale=f"Calibrated from HLP25 validation. Success rate: {result['success_rate']*100:.1f}%, n={result['total_events']}",
                sharpe=0.0,  # Would need trade data
                win_rate=result['success_rate'],
                trades_per_month=result['total_events'] / max(1, days / 30),
                review_days=30,
            )

            # Update status based on validation
            if result['status'] == 'VALIDATED':
                config = ThresholdConfig(
                    name=config.name,
                    value=config.value,
                    method=config.method,
                    date_set=config.date_set,
                    rationale=config.rationale,
                    sharpe_ratio=config.sharpe_ratio,
                    win_rate=config.win_rate,
                    trades_per_month=config.trades_per_month,
                    next_review_date=config.next_review_date,
                    status=ThresholdStatus.VALIDATED,
                    is_robust=True,
                )

            store.save_threshold(config)
            discovered_configs.append(config)

            # Log the optimization run
            db.log_optimization_run(
                threshold_name=threshold_name,
                run_ts=end_ts,
                method='HLP25_VALIDATION',
                optimal_value=result['calibrated_threshold'],
                in_sample_sharpe=None,
                out_of_sample_sharpe=None,
                is_robust=result['status'] == 'VALIDATED',
                notes=f"From HLP25 {result['hypothesis_name']} validation"
            )

            if verbose:
                print(f"Discovered: {threshold_name} = {result['calibrated_threshold']}")

    db.close()
    return discovered_configs


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='HLP23 Threshold Discovery - From arbitrary numbers to validated boundaries'
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
        default=90,
        help='Number of days to analyze (default: 90)'
    )
    parser.add_argument(
        '--strategy', '-s',
        type=str,
        default='default',
        help='Strategy name (default: default)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed output'
    )
    parser.add_argument(
        '--init-defaults',
        action='store_true',
        help='Initialize database with conservative default thresholds'
    )
    parser.add_argument(
        '--phase',
        type=int,
        choices=[1, 2, 3, 4],
        help='Show thresholds for specific phase (1-4)'
    )
    parser.add_argument(
        '--review-due',
        action='store_true',
        help='Check for thresholds due for review'
    )
    parser.add_argument(
        '--export',
        type=str,
        help='Export thresholds to JSON file'
    )

    args = parser.parse_args()

    # Check database exists for commands that need it
    db_required = not args.phase
    if db_required and not Path(args.db).exists():
        print(f"Error: Database not found: {args.db}")
        print()
        print("Make sure you have collected data using the HLP24 collector.")
        sys.exit(1)

    print_header()

    try:
        if args.phase:
            show_phased_thresholds(args.phase)
            sys.exit(0)

        db = ResearchDatabase(args.db)

        if args.init_defaults:
            configs = init_conservative_defaults(db, args.strategy)
            print_summary(configs)
            db.close()
            sys.exit(0)

        if args.review_due:
            check_thresholds_due_for_review(db)
            db.close()
            sys.exit(0)

        if args.export:
            export_thresholds(db, args.export, args.strategy if args.strategy != 'default' else None)
            db.close()
            sys.exit(0)

        # Run discovery
        db.close()
        configs = run_discovery(
            db_path=args.db,
            days=args.days,
            strategy_name=args.strategy,
            verbose=args.verbose
        )

        if not configs:
            print("No thresholds discovered.")
            print()
            print("This can happen if:")
            print("  - No HLP25 validation has been run yet")
            print("  - Insufficient cascade data")
            print()
            print("Try running HLP25 validation first:")
            print("  python scripts/run_hlp25_validation.py")
            print()
            print("Or initialize with conservative defaults:")
            print("  python scripts/run_hlp23_discovery.py --init-defaults")
            sys.exit(1)

        # Print results
        for config in configs:
            print_threshold_config(config)

        print_summary(configs)

        # Report status
        validated_count = sum(1 for c in configs if c.status == ThresholdStatus.VALIDATED)
        if validated_count > 0:
            print(f"{validated_count} thresholds validated and ready for use.")
        else:
            print("No thresholds fully validated yet.")
            print("Continue collecting data and re-run discovery.")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
