#!/usr/bin/env python3
"""
Validate schema has all required keys

Usage:
    python3 validate_schema_completeness.py --schema SYSTEM_MAP_SCHEMA.yaml --required-keys system_name system_version subsystems
"""

import sys
import yaml
import argparse

def main():
    parser = argparse.ArgumentParser(description='Validate schema completeness')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--required-keys', nargs='+', required=True, help='Required top-level keys')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Check for required keys
    missing = [k for k in args.required_keys if k not in schema]

    if missing:
        print("=" * 60)
        print("SCHEMA INCOMPLETE")
        print("=" * 60)
        for k in missing:
            print(f"✗ Missing key: {k}")
        print(f"\nTotal missing: {len(missing)}")
        sys.exit(1)
    else:
        print(f"✓ Schema complete ({len(args.required_keys)} required keys present)")

if __name__ == "__main__":
    main()
