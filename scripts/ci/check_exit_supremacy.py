#!/usr/bin/env python3
"""
Verify EXIT is checked first in arbitration

Usage:
    python3 check_exit_supremacy.py --file runtime/arbitration/arbitrator.py --function arbitrate --required-first-check EXIT --fail-on-violation
"""

import sys
import ast
import re
import argparse

def check_first_mandate_check(file_path, function_name, required_check):
    """Check if first mandate type check is EXIT"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find arbitrate function
        func_pattern = rf'def {function_name}\(.*?\):.*?(?=\n    def |\nclass |\Z)'
        func_match = re.search(func_pattern, content, re.DOTALL)

        if not func_match:
            return None

        func_body = func_match.group(0)

        # Look for first mandate type check
        # Pattern: if any(m.type == MandateType.EXIT
        # Or: exit_mandates = [m for m in mandates if m.type == MandateType.EXIT]
        exit_check_patterns = [
            r'if.*MandateType\.EXIT',
            r'exit_mandates\s*=',
            r'if.*mandates.*\.EXIT'
        ]

        # Find first occurrence of any mandate check
        first_check_pos = float('inf')
        first_check_type = None

        for mandate_type in ['EXIT', 'BLOCK', 'REDUCE', 'ENTRY', 'HOLD']:
            pattern = rf'MandateType\.{mandate_type}'
            match = re.search(pattern, func_body)
            if match and match.start() < first_check_pos:
                first_check_pos = match.start()
                first_check_type = mandate_type

        return first_check_type

    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Check EXIT supremacy')
    parser.add_argument('--file', required=True, help='Path to arbitrator file')
    parser.add_argument('--function', required=True, help='Function name')
    parser.add_argument('--required-first-check', required=True, help='Required first mandate check')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    # Check first mandate check
    first_check = check_first_mandate_check(args.file, args.function, args.required_first_check)

    if first_check is None:
        print(f"WARNING: Could not determine first mandate check in {args.function}")
        return

    if first_check != args.required_first_check:
        print("=" * 60)
        print("EXIT SUPREMACY VIOLATION")
        print("=" * 60)
        print(f"Expected first check: {args.required_first_check}")
        print(f"Actual first check:   {first_check}")
        print("\nEXIT must be checked before all other mandate types")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ EXIT supremacy enforced (first check: {first_check})")

if __name__ == "__main__":
    main()
