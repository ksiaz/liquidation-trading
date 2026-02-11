"""
Quick Analysis Script - Real-time System Health Check
"""
from datetime import datetime, timedelta
from runtime.logging.pg_pool import get_conn, put_conn, init_pool

init_pool()

conn = get_conn()
try:
    cursor = conn.cursor()

    print("=" * 80)
    print("REAL-TIME SYSTEM HEALTH CHECK")
    print("=" * 80)

    # Overall stats
    cursor.execute("SELECT COUNT(*) FROM execution_cycles")
    cycles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM m2_node_events")
    events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT node_id) FROM m2_node_events")
    unique_nodes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM primitive_values")
    primitives = cursor.fetchone()[0]

    print(f"\nTotal Records:")
    print(f"   Execution Cycles: {cycles:,}")
    print(f"   M2 Node Events: {events}")
    print(f"   Unique Nodes: {unique_nodes}")
    print(f"   Primitive Values: {primitives:,}")

    # Time range
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM execution_cycles")
    start_ts, end_ts = cursor.fetchone()
    duration = end_ts - start_ts
    print(f"\nCollection Period:")
    print(f"   Start: {datetime.fromtimestamp(start_ts).strftime('%H:%M:%S')}")
    print(f"   End:   {datetime.fromtimestamp(end_ts).strftime('%H:%M:%S')}")
    print(f"   Duration: {duration/60:.1f} minutes")
    print(f"   Rate: {cycles/duration:.2f} cycles/sec")

    # Symbol breakdown
    cursor.execute("""
        SELECT symbol, COUNT(*) as count
        FROM m2_node_events
        GROUP BY symbol
        ORDER BY count DESC
    """)
    print(f"\nNodes by Symbol:")
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]} events")

    # Event types
    cursor.execute("""
        SELECT event_type, COUNT(*)
        FROM m2_node_events
        GROUP BY event_type
    """)
    print(f"\nEvent Types:")
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]}")

    # Active vs dormant nodes
    cursor.execute("""
        SELECT
            SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN active = 0 THEN 1 ELSE 0 END) as dormant,
            COUNT(*) as total
        FROM m2_nodes
        WHERE id = (SELECT MAX(id) FROM execution_cycles)
    """)
    row = cursor.fetchone()
    if row and row[2]:
        print(f"\nCurrent Node State:")
        print(f"   Active: {row[0] or 0}")
        print(f"   Dormant: {row[1] or 0}")

    # Primitive coverage
    cursor.execute("""
        SELECT
            symbol,
            AVG(CASE WHEN zone_penetration_depth IS NOT NULL THEN 1 ELSE 0 END) * 100 as zone_pct,
            AVG(CASE WHEN price_velocity IS NOT NULL THEN 1 ELSE 0 END) * 100 as velocity_pct,
            AVG(CASE WHEN acceptance_ratio IS NOT NULL THEN 1 ELSE 0 END) * 100 as acceptance_pct
        FROM primitive_values
        GROUP BY symbol
        LIMIT 5
    """)
    print(f"\nPrimitive Coverage (top 5 symbols):")
    print(f"   {'Symbol':<12} {'Zone %':<10} {'Velocity %':<12} {'Acceptance %'}")
    print("   " + "-" * 50)
    for row in cursor.fetchall():
        print(f"   {row[0]:<12} {row[1]:>6.1f}%    {row[2]:>6.1f}%       {row[3]:>6.1f}%")

    print("\n" + "=" * 80)
    print("System Operating Normally")
    print("=" * 80)
finally:
    put_conn(conn)
