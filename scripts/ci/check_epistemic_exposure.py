#!/usr/bin/env python3
"""
Check for evaluative fields in ObservationSnapshot

Usage:
    python3 check_epistemic_exposure.py --file observation/types.py --forbidden-fields strength confidence quality --fail-on-violation
"""

import sys
import ast
import argparse

def extract_dataclass_fields(file_path, class_name='ObservationSnapshot'):
    """Extract fields from a dataclass"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                fields = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.append(item.target.id)
                return fields

        return []
    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Check epistemic exposure')
    parser.add_argument('--file', required=True, help='Path to types file')
    parser.add_argument('--forbidden-fields', nargs='+', required=True, help='Forbidden field names')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    # Extract fields
    fields = extract_dataclass_fields(args.file)

    if not fields:
        print(f"WARNING: No ObservationSnapshot fields found in {args.file}")
        return

    # Check for forbidden fields
    violations = [f for f in fields if f in args.forbidden_fields]

    if violations:
        print("=" * 60)
        print("EVALUATIVE FIELDS IN OBSERVATION SNAPSHOT")
        print("=" * 60)
        for v in violations:
            print(f"✗ {v}")
        print(f"\nTotal violations: {len(violations)}")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ No evaluative fields in ObservationSnapshot ({len(fields)} fields checked)")

if __name__ == "__main__":
    main()
