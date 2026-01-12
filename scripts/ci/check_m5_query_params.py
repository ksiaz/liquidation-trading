#!/usr/bin/env python3
"""
Check for forbidden query parameters in M5 schemas

Usage:
    python3 check_m5_query_params.py --file memory/m5_query_schemas.py --forbidden sort_by rank_by --fail-on-violation
"""

import sys
import ast
import argparse

def extract_dataclass_fields_all(file_path):
    """Extract all dataclass fields from file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)

        all_fields = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        all_fields.append({
                            'class': node.name,
                            'field': item.target.id
                        })

        return all_fields
    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Check M5 query params')
    parser.add_argument('--file', required=True, help='Path to M5 query schemas file')
    parser.add_argument('--forbidden', nargs='+', required=True, help='Forbidden parameter names')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    # Extract all fields
    all_fields = extract_dataclass_fields_all(args.file)

    if not all_fields:
        print(f"WARNING: No query schema fields found in {args.file}")
        return

    # Check for forbidden fields
    violations = []
    for item in all_fields:
        if item['field'] in args.forbidden:
            violations.append(item)

    if violations:
        print("=" * 60)
        print("FORBIDDEN QUERY PARAMETERS DETECTED")
        print("=" * 60)
        for v in violations:
            print(f"✗ {v['class']}.{v['field']}")
        print(f"\nTotal violations: {len(violations)}")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ No forbidden query parameters ({len(all_fields)} fields checked)")

if __name__ == "__main__":
    main()
