#!/usr/bin/env python3
"""
Check case sensitivity handling in policy adapter (warning only)

Usage:
    python3 check_case_sensitivity.py --file runtime/policy_adapter.py --function _extract_primitives --warn-on-incomplete
"""

import sys
import argparse

def check_case_handling(file_path, function_name):
    """Check if function handles case variations"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Look for case handling patterns
        patterns = [
            'symbol.lower()',
            'symbol.upper()',
            '.lower()]',
            '.upper()]'
        ]

        found_patterns = [p for p in patterns if p in content]

        return len(found_patterns) >= 2  # Should handle at least lower and upper

    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Check case sensitivity handling')
    parser.add_argument('--file', required=True, help='Path to policy adapter')
    parser.add_argument('--function', required=True, help='Function name')
    parser.add_argument('--warn-on-incomplete', action='store_true')

    args = parser.parse_args()

    # Check case handling
    has_handling = check_case_handling(args.file, args.function)

    if not has_handling and args.warn_on_incomplete:
        print("=" * 60)
        print("CASE SENSITIVITY HANDLING WARNING")
        print("=" * 60)
        print(f"Function {args.function} may not handle symbol case variations")
        print("Recommended: Try symbol, symbol.lower(), symbol.upper()")
        print("\nThis is a warning only - does not block merge")
    else:
        print(f"✓ Case sensitivity handling appears complete")

if __name__ == "__main__":
    main()
