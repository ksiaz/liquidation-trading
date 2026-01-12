#!/usr/bin/env python3
"""
Verify arbitration priority order matches schema

Usage:
    python3 verify_arbitration_priority.py --schema SYSTEM_MAP_SCHEMA.yaml --module runtime/arbitration/arbitrator.py --fail-on-mismatch
"""

import sys
import re
import yaml
import argparse

def extract_priority_order(file_path):
    """Extract mandate priority order from arbitrator code"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Look for priority hierarchy in arbitrate() function
        # Pattern: for mandate_type in [MandateType.EXIT, MandateType.REDUCE, ...]
        pattern = r'for mandate_type in \[(.*?)\]:'
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            priority_list = matches[0]
            # Extract mandate types
            types = re.findall(r'MandateType\.(\w+)', priority_list)
            return types

        return []
    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Verify arbitration priority order')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--module', required=True, help='Path to arbitrator module')
    parser.add_argument('--fail-on-mismatch', action='store_true', help='Exit 1 on mismatch')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Get schema priority
    try:
        schema_priority = schema['state_machines']['mandate_arbitration']['priority_levels']
        # Sort by priority value (descending)
        schema_order = sorted(schema_priority.items(), key=lambda x: x[1], reverse=True)
        schema_types = [k for k, v in schema_order]
    except KeyError:
        print(f"ERROR: Arbitration priority not found in schema")
        sys.exit(1)

    # Extract code priority order
    code_order = extract_priority_order(args.module)

    if not code_order:
        print(f"WARNING: No priority order found in {args.module}")
        if args.fail_on_mismatch:
            sys.exit(1)
        return

    # Compare (only actionable types in code)
    # Code checks: EXIT, REDUCE, ENTRY, HOLD (not BLOCK since it's non-actionable)
    actionable_schema = [t for t in schema_types if t != 'BLOCK']

    if code_order != actionable_schema[:len(code_order)]:
        print("=" * 60)
        print("ARBITRATION PRIORITY ORDER MISMATCH")
        print("=" * 60)
        print(f"Schema order: {actionable_schema}")
        print(f"Code order:   {code_order}")

        if args.fail_on_mismatch:
            sys.exit(1)
    else:
        print(f"✓ Arbitration priority order matches schema: {code_order}")

if __name__ == "__main__":
    main()
