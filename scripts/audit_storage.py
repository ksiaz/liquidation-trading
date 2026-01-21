"""
Comprehensive Data Storage Audit
Verifies what data is actually being captured vs what's available
"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('logs/execution.db')
cursor = conn.cursor()

print("=" * 80)
print("COMPREHENSIVE DATA STORAGE AUDIT")
print("=" * 80)

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]

print("\n✓ DATABASE TABLES:")
for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    status = "✅ ACTIVE" if count > 0 else "⚠️  EMPTY"
    print(f"   {table:<25} {count:>10,} rows  {status}")

# Check data quality for populated tables
print("\n" + "=" * 80)
print("DATA QUALITY CHECKS")
print("=" * 80)

# 1. Execution Cycles - Check completeness
cursor.execute("""
    SELECT 
        COUNT(*) as total,
        AVG(m2_active_nodes) as avg_active,
        AVG(primitives_computing_total) as avg_primitives,
        MIN(timestamp) as start_ts,
        MAX(timestamp) as end_ts
    FROM execution_cycles
""")
row = cursor.fetchone()
print(f"\n📊 EXECUTION CYCLES:")
print(f"   Total: {row[0]:,}")
print(f"   Avg Active Nodes: {row[1]:.2f}")
print(f"   Avg Primitives Computing: {row[2]:.1f}")
if row[3]:
    duration = row[4] - row[3]
    print(f"   Duration: {duration/60:.1f} minutes")
    print(f"   Rate: {row[0]/duration:.2f} cycles/sec")

# 2. M2 Node Events - Check event flow
cursor.execute("""
    SELECT 
        event_type,
        COUNT(*) as count,
        COUNT(DISTINCT node_id) as unique_nodes,
        COUNT(DISTINCT symbol) as unique_symbols
    FROM m2_node_events
    GROUP BY event_type
""")
print(f"\n🧠 M2 NODE EVENTS:")
for row in cursor.fetchall():
    print(f"   {row[0]:<12}: {row[1]:>3} events, {row[2]} unique nodes, {row[3]} symbols")

# 3. Primitive Values - Check coverage
cursor.execute("""
    SELECT 
        COUNT(DISTINCT symbol) as symbols,
        SUM(CASE WHEN zone_penetration_depth IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as zone_pct,
        SUM(CASE WHEN price_velocity IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as velocity_pct,
        SUM(CASE WHEN acceptance_ratio IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as acceptance_pct,
        SUM(CASE WHEN absence_duration IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as absence_pct
    FROM primitive_values
""")
row = cursor.fetchone()
print(f"\n📈 PRIMITIVE VALUES:")
print(f"   Symbols Tracked: {row[0]}")
print(f"   Zone Penetration: {row[1]:.1f}% populated")
print(f"   Price Velocity: {row[2]:.1f}% populated")
print(f"   Acceptance Ratio: {row[3]:.1f}% populated")
print(f"   Absence Duration: {row[4]:.1f}% populated")

# 4. M2 Nodes Snapshots - Check snapshot frequency
cursor.execute("""
    SELECT 
        COUNT(DISTINCT cycle_id) as cycles_with_nodes,
        COUNT(*) as total_snapshots,
        COUNT(DISTINCT node_id) as unique_nodes
    FROM m2_nodes
""")
row = cursor.fetchone()
print(f"\n🔄 M2 NODE SNAPSHOTS:")
print(f"   Cycles with Nodes: {row[0]:,}")
print(f"   Total Snapshots: {row[1]:,}")
print(f"   Unique Nodes Captured: {row[2]}")

# Missing data tables
print("\n" + "=" * 80)
print("MISSING DATA (Tables Ready but Not Populated)")
print("=" * 80)

empty_tables = []
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
for table_name in [row[0] for row in cursor.fetchall()]:
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    if cursor.fetchone()[0] == 0:
        empty_tables.append(table_name)
        
if empty_tables:
    for table in empty_tables:
        print(f"   ⚠️  {table}")
        # Show what this table is for
        if table == 'liquidation_events':
            print(f"       → Raw liquidation data from Binance (not yet connected)")
        elif table == 'ohlc_candles':
            print(f"       → 1-minute OHLC price data (not yet connected)")
        elif table == 'policy_evaluations':
            print(f"       → Policy decision tracking (ready for integration)")
        elif table == 'mandates':
            print(f"       → Mandate generation logs (ready for integration)")
        elif table == 'arbitration_rounds':
            print(f"       → Arbitration conflict resolution (ready for integration)")
else:
    print("   ✅ All tables populated!")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
cursor.execute("SELECT COUNT(*) FROM execution_cycles")
cycles = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM m2_node_events")
events = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM primitive_values")
primitives = cursor.fetchone()[0]

if cycles > 0 and events > 0 and primitives > 0:
    print("✅ Core data capture is WORKING:")
    print(f"   - {cycles:,} execution cycles")
    print(f"   - {events} node events")
    print(f"   - {primitives:,} primitive values")
    print("\n⚠️  Additional logging available but not yet integrated:")
    print("   - Raw liquidation events")
    print("   - OHLC candles")
    print("   - Policy/mandate/arbitration details")
else:
    print("❌ Data capture has issues - check system")

conn.close()
