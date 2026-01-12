#!/usr/bin/env python3
"""
Load and validate SYSTEM_MAP_SCHEMA.yaml

Usage:
    python3 scripts/ci/load_schema.py SYSTEM_MAP_SCHEMA.yaml
"""

import sys
import yaml

def main():
    if len(sys.argv) < 2:
        print("ERROR: Schema file path required")
        print("Usage: python3 load_schema.py SYSTEM_MAP_SCHEMA.yaml")
        sys.exit(1)

    schema_path = sys.argv[1]

    try:
        with open(schema_path, 'r') as f:
            schema = yaml.safe_load(f)

        # Basic validation
        required_keys = ['system_name', 'system_version', 'subsystems', 'dependencies']
        for key in required_keys:
            if key not in schema:
                print(f"ERROR: Missing required key: {key}")
                sys.exit(1)

        print(f"✓ Schema loaded successfully")
        print(f"  System: {schema['system_name']}")
        print(f"  Version: {schema['system_version']}")
        print(f"  Subsystems: {len(schema['subsystems'])}")
        print(f"  Dependencies: {len(schema['dependencies'])}")

    except FileNotFoundError:
        print(f"ERROR: Schema file not found: {schema_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML syntax: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
