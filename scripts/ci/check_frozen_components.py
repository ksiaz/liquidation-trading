#!/usr/bin/env python3
"""
Check if frozen components are modified without authorization

Usage:
    python3 check_frozen_components.py --schema SYSTEM_MAP_SCHEMA.yaml --git-diff HEAD~1..HEAD --require-override "OVERRIDE: CODE_FREEZE" --fail-on-unauthorized
"""

import sys
import subprocess
import yaml
import argparse

def get_modified_files(git_diff_range):
    """Get list of modified files from git diff"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', git_diff_range],
            capture_output=True,
            text=True,
            check=True
        )

        return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
    except subprocess.CalledProcessError:
        return []
    except Exception as e:
        print(f"WARNING: Could not get git diff: {e}")
        return []

def get_frozen_modules(schema):
    """Get list of frozen modules from schema"""
    frozen = []
    for subsystem_name, subsystem in schema.get('subsystems', {}).items():
        if subsystem.get('frozen') == True:
            modules = subsystem.get('modules', [])
            frozen.extend(modules)
    return frozen

def get_commit_message():
    """Get last commit message"""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--pretty=%B'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except:
        return ""

def main():
    parser = argparse.ArgumentParser(description='Check frozen component modifications')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--git-diff', required=True, help='Git diff range')
    parser.add_argument('--require-override', required=True, help='Required override string')
    parser.add_argument('--fail-on-unauthorized', action='store_true', help='Exit 1 on violations')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Get modified files
    modified = get_modified_files(args.git_diff)

    if not modified:
        print("✓ No modified files detected")
        return

    # Get frozen modules
    frozen = get_frozen_modules(schema)

    # Check for frozen modifications
    frozen_modified = [f for f in modified if f in frozen]

    if not frozen_modified:
        print(f"✓ No frozen components modified ({len(modified)} total modifications)")
        return

    # Check for override in commit message
    commit_msg = get_commit_message()
    has_override = args.require_override in commit_msg

    print("=" * 60)
    print("FROZEN COMPONENT MODIFICATION DETECTED")
    print("=" * 60)
    for f in frozen_modified:
        print(f"✗ {f}")
    print(f"\nTotal frozen components modified: {len(frozen_modified)}")

    if has_override:
        print(f"\n✓ Override detected in commit message: {args.require_override}")
        print("  Modification authorized")
    else:
        print(f"\n✗ Missing required override: {args.require_override}")
        print("  To modify frozen components, include override in commit message")
        print("  And provide logged evidence reference")

        if args.fail_on_unauthorized:
            sys.exit(1)

if __name__ == "__main__":
    main()
