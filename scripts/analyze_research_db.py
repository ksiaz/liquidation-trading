"""
Comprehensive Execution Log Analyzer

Query research database for insights:
- Policy competition
- Primitive value distributions
- Node lifecycle patterns
- Market context correlation
"""

import sqlite3
import argparse
from datetime import datetime
from typing import Optional
import json


def show_summary(db_path: str):
    """Show overall system summary."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("SYSTEM SUMMARY")
    print("="*60)
    
    # Get total cycles
    cursor.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM execution_cycles")
    total_cycles, min_ts, max_ts = cursor.fetchone()
    
    if min_ts and max_ts:
        duration = max_ts - min_ts
        hours = duration / 3600
        
        print(f"\nTotal Execution Cycles: {total_cycles:,}")
        print(f"Start: {datetime.fromtimestamp(min_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End:   {datetime.fromtimestamp(max_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {hours:.2f} hours ({duration/60:.1f} minutes)")
        print(f"Cycles/second: {total_cycles / duration:.2f}")
        
        # Get avg M2 nodes and primitives
        cursor.execute("""
            SELECT 
                AVG(m2_active_nodes), 
                AVG(primitives_computing_total),
                AVG(primitives_possible_total)
            FROM execution_cycles
        """)
        avg_nodes, avg_computing, avg_total = cursor.fetchone()
        
        print(f"\nM2 Memory:")
        print(f"  Avg Active Nodes: {avg_nodes:.1f}")
        
        print(f"\nPrimitives:")
        print(f"  Avg Computing: {avg_computing:.1f} / {avg_total:.0f}")
        print(f"  Coverage: {(avg_computing/avg_total*100):.1f}%")
        
        # Get node creation stats
        cursor.execute("SELECT COUNT(DISTINCT node_id) FROM m2_nodes")
        unique_nodes = cursor.fetchone()[0]
        print(f"\nUnique M2 Nodes Observed: {unique_nodes}")
    
    conn.close()


def analyze_node_lifecycle(db_path: str, node_id: Optional[str] = None):
    """Analyze M2 node lifecycle patterns."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("M2 NODE LIFECYCLE ANALYSIS")
    print("="*60)
    
    if node_id:
        # Specific node evolution
        cursor.execute("""
            SELECT 
                ec.timestamp,
                n.strength,
                n.confidence,
                n.age_seconds,
                n.liquidation_count
            FROM m2_nodes n
            JOIN execution_cycles ec ON n.cycle_id = ec.id
            WHERE n.node_id = ?
            ORDER BY ec.timestamp
        """, (node_id,))
        
        print(f"\nNode: {node_id}")
        print(f"{'Time':<20} {'Strength':<10} {'Confidence':<12} {'Age(s)':<10} {'Liq Count'}")
        print("-" * 65)
        
        for row in cursor.fetchall():
            ts, strength, confidence, age, liq_count = row
            time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
            print(f"{time_str:<20} {strength:<10.3f} {confidence:<12.3f} {age:<10.1f} {liq_count}")
    
    else:
        # Aggregate node stats
        cursor.execute("""
            SELECT 
                AVG(strength) as avg_strength,
                MIN(strength) as min_strength,
                MAX(strength) as max_strength,
                AVG(age_seconds) as avg_age,
                MAX(age_seconds) as max_age,
                AVG(liquidation_count) as avg_liq_count
            FROM m2_nodes
        """)
        
        row = cursor.fetchone()
        print(f"\nNode Strength:")
        print(f"  Average: {row[0]:.3f}")
        print(f"  Min: {row[1]:.3f}")
        print(f"  Max: {row[2]:.3f}")
        
        print(f"\nNode Age:")
        print(f"  Average: {row[3]:.1f} seconds")
        print(f"  Max: {row[4]:.1f} seconds ({row[4]/60:.1f} minutes)")
        
        print(f"\nLiquidation Evidence:")
        print(f"  Avg per node: {row[5]:.1f}")
    
    conn.close()


def analyze_primitives(db_path: str, symbol: Optional[str] = None):
    """Analyze primitive value distributions."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("PRIMITIVE VALUE ANALYSIS")
    print("="*60)
    
    where_clause = f"WHERE symbol = '{symbol}'" if symbol else ""
    symbol_label = f" ({symbol})" if symbol else " (All Symbols)"
    
    # Zone Penetration
    cursor.execute(f"""
        SELECT 
            COUNT(*) as count,
            AVG(zone_penetration_depth) as avg_depth,
            MIN(zone_penetration_depth) as min_depth,
            MAX(zone_penetration_depth) as max_depth
        FROM primitive_values
        {where_clause}
        AND zone_penetration_depth IS NOT NULL
    """)
    
    row = cursor.fetchone()
    if row[0] > 0:
        print(f"\nZone Penetration{symbol_label}:")
        print(f"  Occurrences: {row[0]}")
        print(f"  Avg Depth: {row[1]:.3f}")
        print(f"  Range: {row[2]:.3f} to {row[3]:.3f}")
    
    # Price Velocity
    cursor.execute(f"""
        SELECT 
            COUNT(*) as count,
            AVG(price_velocity) as avg_vel,
            MIN(price_velocity) as min_vel,
            MAX(price_velocity) as max_vel
        FROM primitive_values
        {where_clause}
        AND price_velocity IS NOT NULL
    """)
    
    row = cursor.fetchone()
    if row[0] > 0:
        print(f"\nPrice Velocity{symbol_label}:")
        print(f"  Occurrences: {row[0]}")
        print(f"  Avg: {row[1]:.6f} per second")
        print(f"  Range: {row[2]:.6f} to {row[3]:.6f}")
    
    # Acceptance Ratio (Kinematics Policy)
    cursor.execute(f"""
        SELECT 
            COUNT(*) as count,
            AVG(acceptance_ratio) as avg_ratio,
            MIN(acceptance_ratio) as min_ratio,
            MAX(acceptance_ratio) as max_ratio
        FROM primitive_values
        {where_clause}
        AND acceptance_ratio IS NOT NULL
    """)
    
    row = cursor.fetchone()
    if row[0] > 0:
        print(f"\nPrice Acceptance Ratio{symbol_label}: (Kinematics Policy)")
        print(f"  Occurrences: {row[0]}")
        print(f"  Avg: {row[1]:.3f}")
        print(f"  Range: {row[2]:.3f} to {row[3]:.3f}")
    
    # Persistence Duration (Absence Policy)
    cursor.execute(f"""
        SELECT 
            COUNT(*) as count,
            AVG(persistence_duration) as avg_dur,
            MIN(persistence_duration) as min_dur,
            MAX(persistence_duration) as max_dur
        FROM primitive_values
        {where_clause}
        AND persistence_duration IS NOT NULL
    """)
    
    row = cursor.fetchone()
    if row[0] > 0:
        print(f"\nStructural Persistence{symbol_label}: (Absence Policy)")
        print(f"  Occurrences: {row[0]}")
        print(f"  Avg Duration: {row[1]:.1f} seconds")
        print(f"  Range: {row[2]:.1f} to {row[3]:.1f} seconds")
    
    conn.close()


def analyze_liquidations(db_path: str, hours: Optional[int] = None):
    """Analyze liquidation events."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("LIQUIDATION EVENTS")
    print("="*60)
    
    where_clause = ""
    if hours:
        cutoff = datetime.now().timestamp() - (hours * 3600)
        where_clause = f"WHERE timestamp >= {cutoff}"
    
    # Count by symbol
    cursor.execute(f"""
        SELECT symbol, COUNT(*) as count, SUM(volume) as total_vol
        FROM liquidation_events
        {where_clause}
        GROUP BY symbol
        ORDER BY count DESC
    """)
    
    print(f"\nLiquidations by Symbol:")
    print(f"{'Symbol':<12} {'Count':<10} {'Total Volume'}")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"{row[0]:<12} {row[1]:<10} {row[2]:.2f}")
    
    # Count by side
    cursor.execute(f"""
        SELECT side, COUNT(*) as count
        FROM liquidation_events
        {where_clause}
        GROUP BY side
    """)
    
    print(f"\nBy Side:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Analyze research execution database')
    parser.add_argument('--db', default='logs/execution.db', help='Database path')
    parser.add_argument('--summary', action='store_true', help='Show system summary')
    parser.add_argument('--nodes', action='store_true', help='Analyze node lifecycle')
    parser.add_argument('--node-id', type=str, help='Specific node ID to analyze')
    parser.add_argument('--primitives', action='store_true', help='Analyze primitive values')
    parser.add_argument('--symbol', type=str, help='Filter by symbol')
    parser.add_argument('--liquidations', action='store_true', help='Show liquidation events')
    parser.add_argument('--hours', type=int, help='Limit to last N hours')
    
    args = parser.parse_args()
    
    if args.summary:
        show_summary(args.db)
    
    if args.nodes or args.node_id:
        analyze_node_lifecycle(args.db, args.node_id)
    
    if args.primitives:
        analyze_primitives(args.db, args.symbol)
    
    if args.liquidations:
        analyze_liquidations(args.db, args.hours)
    
    if not any([args.summary, args.nodes, args.node_id, args.primitives, args.liquidations]):
        # Default: show summary
        show_summary(args.db)


if __name__ == "__main__":
    main()
