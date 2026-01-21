#!/usr/bin/env python3
"""
Check if new modules are registered in schema

Usage:
    python3 check_new_modules.py --schema SYSTEM_MAP_SCHEMA.yaml --git-diff HEAD~1..HEAD --fail-on-unregistered
"""

import sys
import subprocess
import yaml
import argparse

def get_new_python_files(git_diff_range):
    """Get list of new .py files from git diff"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-status', git_diff_range],
            capture_output=True,
            text=True,
            check=True
        )

        new_files = []
        for line in result.stdout.strip().split('\n'):
            if line.startswith('A\t') and line.endswith('.py'):
                file_path = line.split('\t', 1)[1]
                new_files.append(file_path)

        return new_files
    except subprocess.CalledProcessError:
        # If git diff fails (e.g., in CI without proper history), return empty
        return []
    except Exception as e:
        print(f"WARNING: Could not get git diff: {e}")
        return []

def get_registered_modules(schema):
    """Get list of all modules registered in schema"""
    registered = []
    for subsystem_name, subsystem in schema.get('subsystems', {}).items():
        modules = subsystem.get('modules', [])
        registered.extend(modules)
    return registered

def main():
    parser = argparse.ArgumentParser(description='Check new module registration')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--git-diff', required=True, help='Git diff range (e.g., HEAD~1..HEAD)')
    parser.add_argument('--fail-on-unregistered', action='store_true', help='Exit 1 if unregistered')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Get new files
    new_files = get_new_python_files(args.git_diff)

    if not new_files:
        print("✓ No new Python files detected")
        return

    # Get registered modules
    registered = get_registered_modules(schema)

    # Check each new file
    unregistered = []
    for file_path in new_files:
        if file_path not in registered:
            # Ignore test files and scripts
            if '/tests/' not in file_path and '/scripts/' not in file_path and not file_path.startswith('test_'):
                unregistered.append(file_path)

    if unregistered:
        print("=" * 60)
        print("UNREGISTERED MODULES DETECTED")
        print("=" * 60)
        for f in unregistered:
            print(f"✗ {f}")
        print(f"\nTotal unregistered: {len(unregistered)}")
        print("\nAction required: Add these modules to SYSTEM_MAP_SCHEMA.yaml")

        if args.fail_on_unregistered:
            sys.exit(1)
    else:
        print(f"✓ All new modules registered ({len(new_files)} files)")

if __name__ == "__main__":
    main()
