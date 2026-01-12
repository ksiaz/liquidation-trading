#!/usr/bin/env python3
"""
Verify all invariants have enforcement points in codebase

Usage:
    python3 verify_invariant_coverage.py --schema SYSTEM_MAP_SCHEMA.yaml --codebase . --fail-on-missing-enforcement
"""

import sys
import os
import yaml
import argparse

def file_and_function_exist(codebase, enforcement_point):
    """Check if enforcement point exists in codebase"""
    # Format: "file.py:function" or "file.py:class.method"
    try:
        parts = enforcement_point.split(':')
        if len(parts) != 2:
            return False

        file_path, location = parts
        full_path = os.path.join(codebase, file_path)

        if not os.path.exists(full_path):
            return False

        # Read file and check for function/method existence
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Simple check: look for "def function_name" or "def method_name"
        if '.' in location:
            # class.method
            class_name, method_name = location.split('.')
            # Check for both class and method
            if f'class {class_name}' in content and f'def {method_name}' in content:
                return True
        else:
            # function
            if f'def {location}' in content or f'{location} =' in content:
                return True

        return False
    except Exception as e:
        print(f"WARNING: Could not verify {enforcement_point}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Verify invariant coverage')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--codebase', required=True, help='Path to codebase root')
    parser.add_argument('--fail-on-missing-enforcement', action='store_true')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Check each invariant category
    invariants = schema.get('invariants', {})
    missing_enforcement = []

    for category in ['epistemic', 'position', 'arbitration']:
        if category in invariants:
            for invariant in invariants[category]:
                inv_id = invariant.get('id')
                enforcement = invariant.get('enforcement_point')

                if enforcement and not file_and_function_exist(args.codebase, enforcement):
                    missing_enforcement.append({
                        'id': inv_id,
                        'enforcement_point': enforcement,
                        'category': category
                    })

    if missing_enforcement:
        print("=" * 60)
        print("INVARIANTS WITHOUT ENFORCEMENT")
        print("=" * 60)
        for inv in missing_enforcement:
            print(f"✗ [{inv['category']}] {inv['id']}")
            print(f"  Expected: {inv['enforcement_point']}")
            print()
        print(f"Total missing: {len(missing_enforcement)}")

        if args.fail_on_missing_enforcement:
            sys.exit(1)
    else:
        total = sum(len(invariants.get(cat, [])) for cat in ['epistemic', 'position', 'arbitration'])
        print(f"✓ All invariants have enforcement points ({total} invariants)")

if __name__ == "__main__":
    main()
