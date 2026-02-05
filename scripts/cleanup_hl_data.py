#!/usr/bin/env python3
"""
Hyperliquid Node Data Cleanup Script

Cleans old HL node data to reclaim disk space. The HL node can accumulate
100GB/day with default settings.

Data categories:
1. DIAGNOSTIC_DIRS - Safe to delete entirely (logs, latency stats, etc.)
2. PRUNE_BY_AGE - Keep recent hours, delete older (node_fills, node_trades, etc.)
3. ABCI_STATES - Old visor state backups

Usage:
    # Dry run (show what would be deleted)
    python scripts/cleanup_hl_data.py --dry-run

    # Clean with default settings (keep 24h, default data dir)
    python scripts/cleanup_hl_data.py

    # Custom settings
    python scripts/cleanup_hl_data.py --data-dir ~/hl/data --keep-hours 6 --verbose

    # Clean only diagnostics (safe, always deletable)
    python scripts/cleanup_hl_data.py --diagnostics-only

Note on --replica-cmds-style:
    If you're accumulating massive replica_cmds data (100GB/day), you should
    restart the HL node with the --replica-cmds-style recent-actions flag.
    This keeps only the 2 latest height files instead of full history.
    See: https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data
"""

import argparse
import os
import shutil
import time
from datetime import datetime
from pathlib import Path


# Directories safe to delete entirely (diagnostic/logging data)
# Note: node_order_statuses and node_raw_book_diffs are NOT used by our trading system
# (we only use node_fills and replica_cmds)
DIAGNOSTIC_DIRS = [
    'node_logs',
    'latency_buckets',
    'latency_summaries',
    'tcp_traffic',
    'visor_child_stderr',
    'crit_msg_stats',
    'tokio_spawn_forever_metrics',
    'periodic_abci_state_statuses',
    'rate_limited_ips',
    'tcp_lz4_stats',
    'log',
    'node_order_statuses',    # NOT used - can grow to 100s of GB
    'node_raw_book_diffs',    # NOT used - orderbook diffs
]

# Directories to prune by age (keep recent hours)
PRUNE_BY_AGE_DIRS = [
    'node_fills/hourly',
    'node_trades/hourly',
    'evm_block_and_receipts/hourly',
    'node_fast_block_times',
    'node_slow_block_times',
    'hip3_oracle_updates',
    'misc_events',
    'system_and_core_writer_actions',
    'node_twap_statuses',
]

# ABCI state directories (old state backups)
ABCI_STATE_DIRS = [
    'visor_abci_states',
    'periodic_abci_states',  # Legacy name
]

# Replica commands - session directories that can grow 100GB+/day
# Format: replica_cmds/YYYY-MM-DDTHH:MM:SSZ/
REPLICA_CMDS_DIR = 'replica_cmds'


def get_dir_size(path: Path) -> int:
    """Get total size of directory in bytes."""
    total = 0
    try:
        for entry in path.rglob('*'):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"


def delete_directory(path: Path, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """Delete a directory and return (files_deleted, bytes_freed)."""
    if not path.exists():
        return 0, 0

    size = get_dir_size(path)
    file_count = sum(1 for _ in path.rglob('*') if _.is_file())

    if dry_run:
        if verbose:
            print(f"  [DRY RUN] Would delete {path} ({format_size(size)}, {file_count} files)")
        return file_count, size

    try:
        shutil.rmtree(path)
        if verbose:
            print(f"  Deleted {path} ({format_size(size)}, {file_count} files)")
        return file_count, size
    except Exception as e:
        print(f"  Error deleting {path}: {e}")
        return 0, 0


def delete_file(path: Path, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """Delete a file and return (1, bytes_freed) or (0, 0) on failure."""
    if not path.exists():
        return 0, 0

    try:
        size = path.stat().st_size
    except (OSError, PermissionError):
        return 0, 0

    if dry_run:
        if verbose:
            print(f"  [DRY RUN] Would delete {path} ({format_size(size)})")
        return 1, size

    try:
        path.unlink()
        if verbose:
            print(f"  Deleted {path} ({format_size(size)})")
        return 1, size
    except Exception as e:
        print(f"  Error deleting {path}: {e}")
        return 0, 0


def prune_hourly_dirs(base_path: Path, keep_hours: int, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """
    Prune hourly subdirectories older than keep_hours.

    Structure: base_path/YYYY-MM-DD/HH/
    """
    if not base_path.exists():
        return 0, 0

    cutoff = time.time() - (keep_hours * 3600)
    total_files = 0
    total_bytes = 0

    # Iterate through date directories (YYYY-MM-DD)
    for date_dir in sorted(base_path.iterdir()):
        if not date_dir.is_dir():
            continue

        # Check if entire date directory is old enough to delete
        try:
            # Parse date from directory name
            date_str = date_dir.name
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_ts = date_obj.timestamp()

            # If date is more than keep_hours + 24h ago, delete entire date dir
            if date_ts < cutoff - 86400:
                files, bytes_freed = delete_directory(date_dir, dry_run, verbose)
                total_files += files
                total_bytes += bytes_freed
                continue
        except ValueError:
            # Not a date directory, skip
            continue

        # Otherwise, prune individual hour directories
        for hour_dir in sorted(date_dir.iterdir()):
            if not hour_dir.is_dir():
                continue

            try:
                # Get modification time of directory
                mtime = hour_dir.stat().st_mtime
                if mtime < cutoff:
                    files, bytes_freed = delete_directory(hour_dir, dry_run, verbose)
                    total_files += files
                    total_bytes += bytes_freed
            except (OSError, ValueError):
                continue

        # Remove date directory if empty
        if date_dir.exists() and not any(date_dir.iterdir()):
            if not dry_run:
                try:
                    date_dir.rmdir()
                except OSError:
                    pass

    return total_files, total_bytes


def prune_flat_dir_by_mtime(base_path: Path, keep_hours: int, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """
    Prune files in a flat directory older than keep_hours based on mtime.
    """
    if not base_path.exists():
        return 0, 0

    cutoff = time.time() - (keep_hours * 3600)
    total_files = 0
    total_bytes = 0

    for entry in base_path.iterdir():
        try:
            mtime = entry.stat().st_mtime
            if mtime < cutoff:
                if entry.is_dir():
                    files, bytes_freed = delete_directory(entry, dry_run, verbose)
                else:
                    files, bytes_freed = delete_file(entry, dry_run, verbose)
                total_files += files
                total_bytes += bytes_freed
        except (OSError, PermissionError):
            continue

    return total_files, total_bytes


def cleanup_replica_cmds(data_dir: Path, keep_hours: int, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """
    Clean old replica_cmds session directories.

    These are session snapshots that can grow 100GB+/day.
    Format: replica_cmds/YYYY-MM-DDTHH:MM:SSZ/
    """
    replica_path = data_dir / REPLICA_CMDS_DIR
    if not replica_path.exists():
        return 0, 0

    cutoff = time.time() - (keep_hours * 3600)
    total_files = 0
    total_bytes = 0

    for session_dir in sorted(replica_path.iterdir()):
        if not session_dir.is_dir():
            continue

        try:
            # Parse timestamp from directory name (e.g., 2026-02-03T02:56:41Z)
            session_name = session_dir.name
            # Parse ISO format timestamp
            dt = datetime.fromisoformat(session_name.replace('Z', '+00:00'))
            session_ts = dt.timestamp()

            if session_ts < cutoff:
                files, bytes_freed = delete_directory(session_dir, dry_run, verbose)
                total_files += files
                total_bytes += bytes_freed
        except (ValueError, OSError) as e:
            if verbose:
                print(f"  Skipping {session_dir.name}: {e}")
            continue

    return total_files, total_bytes


def cleanup_abci_states(data_dir: Path, keep_count: int, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """
    Clean up old ABCI state snapshots, keeping only the most recent ones.

    These are state snapshots taken periodically by the visor.
    """
    total_files = 0
    total_bytes = 0

    for abci_dir_name in ABCI_STATE_DIRS:
        abci_path = data_dir / abci_dir_name
        if not abci_path.exists():
            continue

        # Collect all state files/dirs with their mtimes
        entries = []
        for entry in abci_path.iterdir():
            try:
                mtime = entry.stat().st_mtime
                entries.append((mtime, entry))
            except (OSError, PermissionError):
                continue

        # Sort by mtime descending (newest first)
        entries.sort(reverse=True)

        # Delete all but the most recent keep_count
        for mtime, entry in entries[keep_count:]:
            if entry.is_dir():
                files, bytes_freed = delete_directory(entry, dry_run, verbose)
            else:
                files, bytes_freed = delete_file(entry, dry_run, verbose)
            total_files += files
            total_bytes += bytes_freed

    return total_files, total_bytes


def cleanup_hl_data(
    data_dir: str = "~/hl/data",
    keep_hours: int = 24,
    keep_abci_states: int = 5,
    dry_run: bool = False,
    verbose: bool = False,
    diagnostics_only: bool = False,
) -> dict:
    """
    Clean old HL node data.

    Args:
        data_dir: Path to HL node data directory
        keep_hours: Hours of data to keep for time-based pruning
        keep_abci_states: Number of ABCI states to keep
        dry_run: If True, only show what would be deleted
        verbose: Print detailed progress
        diagnostics_only: Only clean diagnostic directories

    Returns:
        dict with cleanup statistics
    """
    data_path = Path(data_dir).expanduser().resolve()

    if not data_path.exists():
        print(f"Data directory not found: {data_path}")
        return {'error': 'Data directory not found'}

    print(f"{'[DRY RUN] ' if dry_run else ''}Cleaning HL node data in: {data_path}")
    print(f"Keep hours: {keep_hours}, Keep ABCI states: {keep_abci_states}")
    print()

    results = {
        'data_dir': str(data_path),
        'keep_hours': keep_hours,
        'dry_run': dry_run,
        'diagnostics': {'files': 0, 'bytes': 0},
        'hourly_data': {'files': 0, 'bytes': 0},
        'abci_states': {'files': 0, 'bytes': 0},
        'replica_cmds': {'files': 0, 'bytes': 0},
    }

    # Phase 1: Delete diagnostic directories entirely
    print("Phase 1: Cleaning diagnostic directories...")
    for diag_dir in DIAGNOSTIC_DIRS:
        diag_path = data_path / diag_dir
        if diag_path.exists():
            files, bytes_freed = delete_directory(diag_path, dry_run, verbose)
            results['diagnostics']['files'] += files
            results['diagnostics']['bytes'] += bytes_freed

    print(f"  Diagnostics: {results['diagnostics']['files']} files, "
          f"{format_size(results['diagnostics']['bytes'])}")

    if diagnostics_only:
        print("\n--diagnostics-only specified, skipping time-based cleanup")
        return results

    # Phase 2: Prune hourly data directories by age
    print("\nPhase 2: Pruning hourly data by age...")
    for hourly_dir in PRUNE_BY_AGE_DIRS:
        hourly_path = data_path / hourly_dir

        # Handle nested hourly structure (e.g., node_fills/hourly/YYYY-MM-DD/HH)
        if 'hourly' in hourly_dir:
            files, bytes_freed = prune_hourly_dirs(hourly_path, keep_hours, dry_run, verbose)
        else:
            files, bytes_freed = prune_flat_dir_by_mtime(hourly_path, keep_hours, dry_run, verbose)

        results['hourly_data']['files'] += files
        results['hourly_data']['bytes'] += bytes_freed

    print(f"  Hourly data: {results['hourly_data']['files']} files, "
          f"{format_size(results['hourly_data']['bytes'])}")

    # Phase 3: Clean old ABCI states
    print("\nPhase 3: Cleaning old ABCI states...")
    files, bytes_freed = cleanup_abci_states(data_path, keep_abci_states, dry_run, verbose)
    results['abci_states']['files'] = files
    results['abci_states']['bytes'] = bytes_freed
    print(f"  ABCI states: {results['abci_states']['files']} files, "
          f"{format_size(results['abci_states']['bytes'])}")

    # Phase 4: Clean old replica_cmds sessions (can be 100GB+/day)
    print("\nPhase 4: Cleaning old replica_cmds sessions...")
    files, bytes_freed = cleanup_replica_cmds(data_path, keep_hours, dry_run, verbose)
    results['replica_cmds']['files'] = files
    results['replica_cmds']['bytes'] = bytes_freed
    print(f"  Replica cmds: {results['replica_cmds']['files']} files, "
          f"{format_size(results['replica_cmds']['bytes'])}")

    # Summary
    total_files = (results['diagnostics']['files'] +
                   results['hourly_data']['files'] +
                   results['abci_states']['files'] +
                   results['replica_cmds']['files'])
    total_bytes = (results['diagnostics']['bytes'] +
                   results['hourly_data']['bytes'] +
                   results['abci_states']['bytes'] +
                   results['replica_cmds']['bytes'])

    print()
    print("=" * 60)
    print(f"{'[DRY RUN] ' if dry_run else ''}TOTAL: {total_files} files, {format_size(total_bytes)}")
    print("=" * 60)

    results['total_files'] = total_files
    results['total_bytes'] = total_bytes

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Clean Hyperliquid node data to reclaim disk space',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--data-dir',
        default='~/hl/data',
        help='Path to HL node data directory (default: ~/hl/data)'
    )

    parser.add_argument(
        '--keep-hours',
        type=int,
        default=24,
        help='Hours of data to keep for time-based pruning (default: 24)'
    )

    parser.add_argument(
        '--keep-abci-states',
        type=int,
        default=5,
        help='Number of ABCI state snapshots to keep (default: 5)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed progress'
    )

    parser.add_argument(
        '--diagnostics-only',
        action='store_true',
        help='Only clean diagnostic directories (safe, always deletable)'
    )

    args = parser.parse_args()

    results = cleanup_hl_data(
        data_dir=args.data_dir,
        keep_hours=args.keep_hours,
        keep_abci_states=args.keep_abci_states,
        dry_run=args.dry_run,
        verbose=args.verbose,
        diagnostics_only=args.diagnostics_only,
    )

    # Exit with error if nothing to clean or error occurred
    if 'error' in results:
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
