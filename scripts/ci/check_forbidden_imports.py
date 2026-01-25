#!/usr/bin/env python3
"""
Check for forbidden imports (upward dependencies)

Usage:
    python3 check_forbidden_imports.py --schema SYSTEM_MAP_SCHEMA.yaml --scan runtime/ --forbidden observation/internal/ --fail-on-violation
"""

import sys
import os
import ast
import argparse
from pathlib import Path

# ==============================================================================
# EXCEPTIONS (with constitutional justification)
# ==============================================================================

# Files exempt from forbidden import checks
# Format: {relative_path: "justification"}
EXEMPT_FILES = {
    # Test files need to import types to construct test data
    'runtime/executor/tests/test_exit_lifecycle.py': "Test file: needs M4 types for test data construction",
    'external_policy/test_ep2_strategy_absence.py': "Test file: needs M4 types for test data construction",
    'external_policy/test_ep2_strategy_geometry.py': "Test file: needs M4 types for test data construction",
    'external_policy/test_ep2_strategy_kinematics.py': "Test file: needs M4 types for test data construction",
    # Strategy files import M4 types (not computation) for type hints
    'external_policy/ep2_strategy_cascade_sniper.py': "Strategy: imports M4 types for primitive type hints",
    'external_policy/ep2_strategy_geometry.py': "Strategy: imports M4 types for primitive type hints",
    'external_policy/ep2_strategy_kinematics.py': "Strategy: imports M4 types for primitive type hints",
    # Hyperliquid collector imports M4 for cascade tracking
    'runtime/hyperliquid/collector.py': "Collector: imports M4 cascade momentum for live tracking",
}

def is_exempt_file(file_path):
    """Check if file is exempt from forbidden import checks."""
    # Normalize path separators
    normalized = file_path.replace('\\', '/').replace('//', '/')

    # Check against exempt files
    for exempt_path in EXEMPT_FILES:
        if normalized.endswith(exempt_path):
            return True

    # Auto-exempt test files in tests/ directory
    if '/tests/' in normalized or normalized.startswith('tests/'):
        return True

    return False

def extract_imports_from_file(file_path):
    """Extract all import statements from a Python file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return imports
    except Exception as e:
        print(f"WARNING: Could not parse {file_path}: {e}")
        return []

def is_forbidden_import(import_path, forbidden_patterns):
    """Check if import matches any forbidden pattern"""
    for pattern in forbidden_patterns:
        if import_path.startswith(pattern.replace('/', '.')):
            return True
    return False

def scan_directory(directory, forbidden_patterns):
    """Scan directory for forbidden imports"""
    violations = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)

                # Skip exempt files
                if is_exempt_file(file_path):
                    continue

                imports = extract_imports_from_file(file_path)

                for imp in imports:
                    if is_forbidden_import(imp, forbidden_patterns):
                        violations.append({
                            'file': file_path,
                            'import': imp,
                            'reason': 'forbidden_upward_dependency'
                        })

    return violations

def main():
    parser = argparse.ArgumentParser(description='Check for forbidden imports')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--scan', nargs='+', required=True, help='Directories to scan')
    parser.add_argument('--forbidden', nargs='+', required=True, help='Forbidden import patterns')
    parser.add_argument('--fail-on-violation', action='store_true', help='Exit 1 on violations')

    args = parser.parse_args()

    all_violations = []

    for scan_dir in args.scan:
        if os.path.exists(scan_dir):
            violations = scan_directory(scan_dir, args.forbidden)
            all_violations.extend(violations)

    if all_violations:
        print("=" * 60)
        print("FORBIDDEN IMPORT VIOLATIONS DETECTED")
        print("=" * 60)
        for v in all_violations:
            print(f"✗ {v['file']}")
            print(f"  Imports: {v['import']}")
            print(f"  Reason: {v['reason']}")
            print()
        print(f"Total violations: {len(all_violations)}")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print("✓ No forbidden imports detected")

if __name__ == "__main__":
    main()
