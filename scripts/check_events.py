import sqlite3
from datetime import datetime

conn = sqlite3.connect('logs/execution.db')
cursor = conn.cursor()

print("=" * 80)
print("DATABASE STATUS CHECK")
print("=" * 80)

# Check all tables
cursor.execute("SELECT COUNT(*) FROM execution_cycles")
cycles = cursor.fetchone()[0]
print(f"\n✓ Execution Cycles: {cycles}")

cursor.execute("SELECT COUNT(*) FROM m2_node_events")
node_events = cursor.fetchone()[0]
print(f"✓ M2 Node Events: {node_events}")

cursor.execute("SELECT COUNT(*) FROM primitive_values")
primitives = cursor.fetchone()[0]
print(f"✓ Primitive Values: {primitives}")

cursor.execute("SELECT COUNT(*) FROM m2_nodes")
node_snapshots = cursor.fetchone()[0]
print(f"✓ M2 Node Snapshots: {node_snapshots}")

cursor.execute("SELECT COUNT(*) FROM liquidation_events")
liqs = cursor.fetchone()[0]
print(f"✓ Liquidation Events: {liqs}")

if node_events > 0:
    print("\n" + "=" * 80)
    print("RECENT M2 NODE EVENTS")
    print("=" * 80)
    
    cursor.execute("""
        SELECT timestamp, event_type, symbol, price, volume, strength_after
        FROM m2_node_events
        ORDER BY id DESC
        LIMIT 15
    """)
    
    print(f"\n{'Time':<12} {'Type':<12} {'Symbol':<10} {'Price':<12} {'Volume':<12} {'Strength'}")
    print("-" * 80)
    for row in cursor.fetchall():
        ts = datetime.fromtimestamp(row[0]).strftime('%H:%M:%S')
        print(f"{ts:<12} {row[1]:<12} {row[2]:<10} {row[3]:<12.2f} {row[4]:<12.2f} {row[5]:.3f}")

# Event type breakdown
print("\n" + "=" * 80)
print("EVENT TYPE BREAKDOWN")
print("=" * 80)
cursor.execute("SELECT event_type, COUNT(*) FROM m2_node_events GROUP BY event_type")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
