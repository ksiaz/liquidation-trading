#!/usr/bin/env python3
"""
Check dependency graph for cycles

Usage:
    python3 check_dependency_graph.py --schema SYSTEM_MAP_SCHEMA.yaml --fail-on-cycle
"""

import sys
import yaml
import argparse
from collections import defaultdict, deque

def has_cycle(graph):
    """Check if directed graph has cycles using DFS"""
    visited = set()
    rec_stack = set()

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node):
                return True

    return False

def main():
    parser = argparse.ArgumentParser(description='Check dependency graph')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--fail-on-cycle', action='store_true')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Build dependency graph
    graph = defaultdict(list)
    dependencies = schema.get('dependencies', [])

    for dep in dependencies:
        from_sys = dep.get('from')
        to_sys = dep.get('to')
        if from_sys and to_sys:
            graph[from_sys].append(to_sys)

    # Check for cycles
    if has_cycle(graph):
        print("=" * 60)
        print("CIRCULAR DEPENDENCY DETECTED")
        print("=" * 60)
        print("Dependency graph contains cycles")
        print("This violates constitutional architecture")

        if args.fail_on_cycle:
            sys.exit(1)
    else:
        print(f"✓ Dependency graph is acyclic ({len(dependencies)} dependencies)")

if __name__ == "__main__":
    main()
