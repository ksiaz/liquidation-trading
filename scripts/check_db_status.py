import sqlite3

conn = sqlite3.connect('logs/execution.db')
cursor = conn.cursor()

print("=" * 60)
print("DATABASE STATUS CHECK")
print("=" * 60)

# Check cycles
cursor.execute("SELECT COUNT(*) FROM execution_cycles")
cycles = cursor.fetchone()[0]
print(f"\nExecution Cycles: {cycles}")

# Check M2 nodes
cursor.execute("SELECT COUNT(*) FROM m2_nodes")
nodes = cursor.fetchone()[0]
print(f"M2 Nodes Logged: {nodes}")

# Check primitive values
cursor.execute("SELECT COUNT(*) FROM primitive_values")
primitives = cursor.fetchone()[0]
print(f"Primitive Value Records: {primitives}")

# Show last few cycles with M2 info
cursor.execute("""
    SELECT timestamp, m2_active_nodes, primitives_computing_total
    FROM execution_cycles
    ORDER BY id DESC
    LIMIT 5
""")
print(f"\nLast 5 Cycles:")
print(f"{'Timestamp':<20} {'Active Nodes':<15} {'Primitives'}")
print("-" * 50)
for row in cursor.fetchall():
    from datetime import datetime
    ts_str = datetime.fromtimestamp(row[0]).strftime('%H:%M:%S')
    print(f"{ts_str:<20} {row[1]:<15} {row[2]}")

# Check if get_active_nodes is being called
cursor.execute("""
    SELECT COUNT(*) 
    FROM execution_cycles
    WHERE m2_active_nodes > 0
""")
cycles_with_nodes = cursor.fetchone()[0]
print(f"\nCycles with active M2 nodes: {cycles_with_nodes}")

conn.close()
