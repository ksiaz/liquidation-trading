#!/usr/bin/env python3
"""
Check for unregistered mandate types

Usage:
    python3 check_mandate_types.py --schema SYSTEM_MAP_SCHEMA.yaml --file runtime/arbitration/types.py --enum MandateType --fail-on-unregistered
"""

import sys
import ast
import yaml
import argparse

def extract_enum_values(file_path, enum_name):
    """Extract enum values from Python file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == enum_name:
                values = []
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                values.append(target.id)
                return values

        return []
    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Check mandate types')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--file', required=True, help='Path to types file')
    parser.add_argument('--enum', required=True, help='Enum name')
    parser.add_argument('--fail-on-unregistered', action='store_true')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Get schema mandate types
    try:
        schema_types = list(schema['state_machines']['mandate_arbitration']['priority_levels'].keys())
    except KeyError:
        print(f"ERROR: Mandate types not found in schema")
        sys.exit(1)

    # Extract code enum values
    code_types = extract_enum_values(args.file, args.enum)

    if not code_types:
        print(f"WARNING: No {args.enum} found in {args.file}")
        return

    # Check for new types
    new_types = [t for t in code_types if t not in schema_types]

    if new_types:
        print("=" * 60)
        print("UNREGISTERED MANDATE TYPES DETECTED")
        print("=" * 60)
        for t in new_types:
            print(f"✗ {t}")
        print(f"\nTotal unregistered: {len(new_types)}")
        print("\nAction required: Add to SYSTEM_MAP_SCHEMA.yaml priority_levels")

        if args.fail_on_unregistered:
            sys.exit(1)
    else:
        print(f"✓ All mandate types registered ({len(code_types)} types)")

if __name__ == "__main__":
    main()
