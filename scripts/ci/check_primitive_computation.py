#!/usr/bin/env python3
"""
Verify primitives computed inline, not via M5 query

Usage:
    python3 check_primitive_computation.py --file observation/governance.py --function _compute_primitives_for_symbol --forbidden-calls self._m5_access --fail-on-violation
"""

import sys
import ast
import argparse

def check_function_for_calls(file_path, function_name, forbidden_patterns):
    """Check if function contains forbidden calls"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=file_path)

        # Find the function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                # Check for forbidden patterns in function body
                violations = []
                function_str = ast.unparse(node) if hasattr(ast, 'unparse') else content

                for pattern in forbidden_patterns:
                    if pattern in function_str:
                        violations.append(pattern)

                return violations

        return None  # Function not found
    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Check primitive computation method')
    parser.add_argument('--file', required=True, help='Path to file')
    parser.add_argument('--function', required=True, help='Function name')
    parser.add_argument('--forbidden-calls', nargs='+', required=True, help='Forbidden call patterns')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    # Check function
    violations = check_function_for_calls(args.file, args.function, args.forbidden_calls)

    if violations is None:
        print(f"WARNING: Function {args.function} not found in {args.file}")
        return

    if violations:
        print("=" * 60)
        print("PRIMITIVE COMPUTATION VIA M5 QUERY DETECTED")
        print("=" * 60)
        print(f"Function: {args.function}")
        print(f"Forbidden calls found:")
        for v in violations:
            print(f"✗ {v}")
        print("\nPrimitives must be computed inline, not via M5 queries")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ Primitives computed inline (no M5 queries in {args.function})")

if __name__ == "__main__":
    main()
