"""
Execution Log Analyzer

Query and analyze execution database for insights on:
- Policy competition
- Primitive coverage
- Performance metrics
"""

import sqlite3
import argparse
from datetime import datetime, timedelta
from typing import Optional


def analyze_policy_competition(db_path: str, hours: Optional[int] = None):
    """Analyze which policies generate mandates."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Calculate time filter
    where_clause = ""
    if hours:
        cutoff = datetime.now().timestamp() - (hours * 3600)
        where_clause = f"WHERE timestamp >= {cutoff}"
    
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
    """)
    
    print("Mandate Types:")
    total = 0
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
        total += row[1]
    print(f"  TOTAL: {total}\n")
    
    conn.close()


def analyze_primitive_coverage(db_path: str, symbol: Optional[str] = None):
    """Analyze primitive coverage statistics."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    where_clause = f"WHERE symbol = '{symbol}'" if symbol else ""
    
    print(f"\n=== Primitive Coverage ===")
    if symbol:
        print(f"Symbol: {symbol}\n")
    
    # Get critical primitives avg
    cursor.execute(f"""
        SELECT 
            ROUND(AVG(zone_penetration) * 100, 1) as zone_pct,
            ROUND(AVG(price_traversal_velocity) * 100, 1) as velocity_pct,
            ROUND(AVG(price_acceptance_ratio) * 100, 1) as acceptance_pct,
            ROUND(AVG(structural_persistence_duration) * 100, 1) as persistence_pct,
            COUNT(*) as cycles
        FROM primitive_coverage
        {where_clause}
    """)
    
    row = cursor.fetchone()
    if row:
        print(f"Zone Penetration: {row[0]}% of cycles")
        print(f"Price Velocity: {row[1]}% of cycles")
        print(f"Price Acceptance Ratio: {row[2]}% of cycles (Kinematics)")
        print(f"Structural Persistence: {row[3]}% of cycles (Absence)")
        print(f"\nTotal Cycles Analyzed: {row[4]}")
    
    conn.close()


def show_summary(db_path: str):
    """Show overall system summary."""
    conn = sqlite3.connect(db_path)
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
    
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Analyze execution database')
    parser.add_argument('--db', default='logs/execution.db', help='Database path')
    parser.add_argument('--competition', action='store_true', help='Show policy competition')
    parser.add_argument('--primitives', type=str, help='Show primitive coverage for symbol')
    parser.add_argument('--summary', action='store_true', help='Show system summary')
    parser.add_argument('--hours', type=int, help='Limit to last N hours')
    
    args = parser.parse_args()
    
    if args.summary:
        show_summary(args.db)
    
    if args.competition:
        analyze_policy_competition(args.db, args.hours)
    
    if args.primitives:
        analyze_primitive_coverage(args.db, args.primitives)
    
    if not (args.summary or args.competition or args.primitives):
        # Default: show summary
        show_summary(args.db)


if __name__ == "__main__":
    main()
