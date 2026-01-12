#!/usr/bin/env python3
"""
Verify all modules declared in schema exist in codebase

Usage:
    python3 verify_modules_exist.py --schema SYSTEM_MAP_SCHEMA.yaml --codebase .
"""

import sys
import os
import yaml
import argparse

def main():
    parser = argparse.ArgumentParser(description='Verify modules exist')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--codebase', required=True, help='Path to codebase root')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Get all declared modules
    declared_modules = []
    for subsystem_name, subsystem in schema.get('subsystems', {}).items():
        modules = subsystem.get('modules', [])
        declared_modules.extend(modules)

    # Check if each module exists
    missing = []
    for module in declared_modules:
        full_path = os.path.join(args.codebase, module)
        if not os.path.exists(full_path):
            missing.append(module)

    if missing:
        print("=" * 60)
        print("SCHEMA DECLARES NON-EXISTENT MODULES")
        print("=" * 60)
        for m in missing:
            print(f"✗ {m}")
        print(f"\nTotal missing: {len(missing)}")
        sys.exit(1)
    else:
        print(f"✓ All declared modules exist ({len(declared_modules)} modules)")

if __name__ == "__main__":
    main()
