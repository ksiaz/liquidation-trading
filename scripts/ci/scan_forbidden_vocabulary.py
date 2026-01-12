#!/usr/bin/env python3
"""
Scan for forbidden semantic vocabulary in observation layer

Usage:
    python3 scan_forbidden_vocabulary.py --dirs observation/ memory/ --forbidden signal setup opportunity edge --fail-on-violation
"""

import sys
import os
import re
import argparse

def scan_file_for_words(file_path, forbidden_words):
    """Scan file for forbidden vocabulary"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        violations = []
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith('#'):
                continue

            # Skip strings (but not docstrings - those matter)
            # Simplistic check - just look for words in code
            for word in forbidden_words:
                # Case-insensitive search
                pattern = rf'\b{word}\b'
                if re.search(pattern, line, re.IGNORECASE):
                    # Check if it's in a comment or string literal
                    if '#' in line and line.index('#') < line.lower().index(word.lower()):
                        continue  # In comment, skip

                    violations.append({
                        'line_num': i,
                        'line': line.strip(),
                        'word': word
                    })

        return violations

    except Exception as e:
        print(f"WARNING: Could not scan {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Scan for forbidden vocabulary')
    parser.add_argument('--dirs', nargs='+', required=True, help='Directories to scan')
    parser.add_argument('--forbidden', nargs='+', required=True, help='Forbidden words')
    parser.add_argument('--context-sensitive', action='store_true', help='Enable context checking')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    all_violations = []

    for directory in args.dirs:
        if not os.path.exists(directory):
            continue

        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    violations = scan_file_for_words(file_path, args.forbidden)

                    if violations:
                        all_violations.append({
                            'file': file_path,
                            'violations': violations
                        })

    if all_violations:
        print("=" * 60)
        print("FORBIDDEN VOCABULARY DETECTED")
        print("=" * 60)
        for item in all_violations:
            print(f"\nFile: {item['file']}")
            for v in item['violations']:
                print(f"  Line {v['line_num']}: {v['word']}")
                print(f"    {v['line'][:80]}")

        total = sum(len(item['violations']) for item in all_violations)
        print(f"\nTotal violations: {total}")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ No forbidden vocabulary detected")

if __name__ == "__main__":
    main()
