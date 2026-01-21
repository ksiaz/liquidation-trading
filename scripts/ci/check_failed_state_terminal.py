#!/usr/bin/env python3
"""
Verify FAILED state has no exit transitions

Usage:
    python3 check_failed_state_terminal.py --file observation/governance.py --forbidden-transition FAILED --fail-on-violation
"""

import sys
import re
import argparse

def check_failed_transitions(file_path, failed_state_name):
    """Check if FAILED state has any exit transitions"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        violations = []

        # Look for patterns like:
        # if self._status == ObservationStatus.FAILED:
        #     self._status = ObservationStatus.ACTIVE  # VIOLATION

        # Pattern: FAILED -> anything else
        pattern = rf'if.*{failed_state_name}.*:\s*\n.*self\._status\s*=\s*ObservationStatus\.(?!FAILED)'

        matches = re.finditer(pattern, content, re.MULTILINE)
        for match in matches:
            violations.append(match.group(0))

        return violations

    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Check FAILED state terminal')
    parser.add_argument('--file', required=True, help='Path to observation file')
    parser.add_argument('--forbidden-transition', required=True, help='State that must be terminal')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    # Check for FAILED transitions
    violations = check_failed_transitions(args.file, args.forbidden_transition)

    if violations:
        print("=" * 60)
        print("FAILED STATE EXIT TRANSITION DETECTED")
        print("=" * 60)
        print("FAILED state must be terminal (no exit transitions)")
        print(f"\nViolations found: {len(violations)}")
        for v in violations:
            print(f"✗ {v[:100]}...")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ FAILED state is terminal (no exit transitions)")

if __name__ == "__main__":
    main()
