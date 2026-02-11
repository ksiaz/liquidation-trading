"""
Execution Log Analyzer

Query and analyze execution database for insights on:
- Policy competition
- Primitive coverage
- Performance metrics
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.logging.pg_pool import get_conn, put_conn, init_pool


def analyze_policy_competition(hours: Optional[int] = None):
    """Analyze which policies generate mandates."""
    conn = get_conn()
    try:
        cursor = conn.cursor()

        # Calculate time filter
        where_clause = ""
        params = []
        if hours:
            cutoff = datetime.now().timestamp() - (hours * 3600)
            where_clause = "WHERE timestamp >= %s"
            params = [cutoff]

        print(f"\n=== Policy Competition ===")
        if hours:
            print(f"(Last {hours} hours)\n")

        # Count by mandate type
        cursor.execute(f"""
            SELECT mandate_type, COUNT(*) as count
            FROM mandates
            {where_clause}
            GROUP BY mandate_type
            ORDER BY count DESC
        """, params)

        print("Mandate Types:")
        total = 0
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")
            total += row[1]
        print(f"  TOTAL: {total}\n")
    finally:
        put_conn(conn)


def analyze_primitive_coverage(symbol: Optional[str] = None):
    """Analyze primitive coverage statistics."""
    conn = get_conn()
    try:
        cursor = conn.cursor()

        where_clause = ""
        params = []
        if symbol:
            where_clause = "WHERE symbol = %s"
            params = [symbol]

        print(f"\n=== Primitive Coverage ===")
        if symbol:
            print(f"Symbol: {symbol}\n")

        # Get critical primitives avg
        cursor.execute(f"""
            SELECT
                ROUND(AVG(zone_penetration::int) * 100, 1) as zone_pct,
                ROUND(AVG(price_traversal_velocity::int) * 100, 1) as velocity_pct,
                ROUND(AVG(price_acceptance_ratio::int) * 100, 1) as acceptance_pct,
                ROUND(AVG(structural_persistence_duration::int) * 100, 1) as persistence_pct,
                COUNT(*) as cycles
            FROM primitive_coverage
            {where_clause}
        """, params)

        row = cursor.fetchone()
        if row:
            print(f"Zone Penetration: {row[0]}% of cycles")
            print(f"Price Velocity: {row[1]}% of cycles")
            print(f"Price Acceptance Ratio: {row[2]}% of cycles (Kinematics)")
            print(f"Structural Persistence: {row[3]}% of cycles (Absence)")
            print(f"\nTotal Cycles Analyzed: {row[4]}")
    finally:
        put_conn(conn)


def show_summary():
    """Show overall system summary."""
    conn = get_conn()
    try:
        cursor = conn.cursor()

        # Get total cycles
        cursor.execute("SELECT COUNT(*) FROM execution_cycles")
        total_cycles = cursor.fetchone()[0]

        # Get time range
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM execution_cycles")
        min_ts, max_ts = cursor.fetchone()

        if min_ts and max_ts:
            duration = max_ts - min_ts
            hours = duration / 3600

            print(f"\n=== System Summary ===")
            print(f"Total Execution Cycles: {total_cycles}")
            print(f"Time Range: {datetime.fromtimestamp(min_ts).strftime('%Y-%m-%d %H:%M:%S')} to {datetime.fromtimestamp(max_ts).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Duration: {hours:.1f} hours")
            print(f"Cycles per second: {total_cycles / duration:.2f}")

            # Get avg M2 nodes
            cursor.execute("SELECT AVG(m2_active_nodes), AVG(primitives_computing) FROM execution_cycles")
            avg_nodes, avg_primitives = cursor.fetchone()
            print(f"\nAvg Active M2 Nodes: {avg_nodes:.1f}")
            print(f"Avg Primitives Computing: {avg_primitives:.1f}")
    finally:
        put_conn(conn)


def main():
    parser = argparse.ArgumentParser(description='Analyze execution database')
    parser.add_argument('--db', default=None,
                        help='Ignored (data comes from PostgreSQL now)')
    parser.add_argument('--competition', action='store_true', help='Show policy competition')
    parser.add_argument('--primitives', type=str, help='Show primitive coverage for symbol')
    parser.add_argument('--summary', action='store_true', help='Show system summary')
    parser.add_argument('--hours', type=int, help='Limit to last N hours')

    args = parser.parse_args()

    init_pool()

    if args.summary:
        show_summary()

    if args.competition:
        analyze_policy_competition(args.hours)

    if args.primitives:
        analyze_primitive_coverage(args.primitives)

    if not (args.summary or args.competition or args.primitives):
        # Default: show summary
        show_summary()


if __name__ == "__main__":
    main()
