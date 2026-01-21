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

def is_negation_context(line, word):
    """Check if word appears in negation context"""
    line_lower = line.lower()
    word_lower = word.lower()

    # Check for negation patterns (more comprehensive)
    negation_patterns = [
        rf'\bno\s+{word_lower}',  # "no signal"
        rf'\bnot\s+{word_lower}',  # "not signal"
        rf'\bno_{word_lower}',  # "no_signal"
        rf'\bwithout\s+{word_lower}',  # "without signal"
        rf'\bnever\s+{word_lower}',  # "never signal"
        rf'"{word_lower}"',  # In quotes as forbidden word list
        rf"'{word_lower}'",  # In single quotes
        rf'\bno\s+\w+\s+{word_lower}',  # "no interpretation of signal"
        rf'\bnot\s+\w+\s+{word_lower}',  # "not directional signal"
        rf'\bno\s+\w+,\s*\w+,\s*or\s+{word_lower}',  # "no ranking, interpretation, or signal"
        rf'\bwithout\s+\w+,\s*\w+,\s*or\s+{word_lower}',  # "without interpretation, ranking, or signal"
    ]

    for pattern in negation_patterns:
        if re.search(pattern, line_lower):
            return True

    # Check if word is part of a hyphenated identifier (e.g., "M6-BULLISH-SIGNAL")
    if re.search(rf'-{word_lower}', line_lower) or re.search(rf'{word_lower}-', line_lower):
        # Check if in string literal (identifier/constant name)
        if re.search(rf'["\'][^"\']*{word_lower}[^"\']*["\']', line_lower):
            return True

    # Check if in a list of forbidden words (array/list literal)
    if re.search(rf'[\[,]\s*["\']?{word_lower}["\']?\s*[,\]]', line_lower):
        return True

    # Check for FORBIDDEN: prefix in comments
    if 'FORBIDDEN' in line and word_lower in line_lower:
        return True

    # Check for "Cannot imply:" pattern (constitutional documentation)
    if 'cannot imply' in line_lower and word_lower in line_lower:
        return True

    # Check for "Constitutional:" pattern followed by negation
    if 'constitutional:' in line_lower:
        # Extract text after "constitutional:"
        const_idx = line_lower.find('constitutional:')
        after_const = line_lower[const_idx:]
        if word_lower in after_const:
            # Check if there's negation in the constitutional statement
            if any(neg in after_const for neg in ['no ', 'not ', 'without ']):
                return True

    # Check for "Zero X" pattern
    if re.search(rf'\bzero\s+{word_lower}', line_lower):
        return True

    # Check for "Expected: No X" pattern (test expectations)
    if re.search(rf'expected:.*\bno\s+.*{word_lower}', line_lower):
        return True

    # Check for "FAIL: Any X" pattern (test failure descriptions)
    if re.search(rf'\bfail:.*\bany\s+{word_lower}', line_lower):
        return True

    return False

def scan_file_for_words(file_path, forbidden_words, context_sensitive=False):
    """Scan file for forbidden vocabulary"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        violations = []
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # Skip comment-only lines
            if line.strip().startswith('#'):
                continue

            # Skip strings (but not docstrings - those matter)
            # Simplistic check - just look for words in code
            for word in forbidden_words:
                # Case-insensitive search
                pattern = rf'\b{word}\b'
                if re.search(pattern, line, re.IGNORECASE):
                    # Check if it's in a comment
                    if '#' in line:
                        try:
                            comment_start = line.index('#')
                            word_pos = line.lower().index(word.lower())
                            if comment_start < word_pos:
                                # Word is in comment, check context if enabled
                                if context_sensitive and is_negation_context(line, word):
                                    continue
                        except ValueError:
                            pass

                    # Context-sensitive filtering for non-comment occurrences
                    if context_sensitive and is_negation_context(line, word):
                        continue

                    # Skip pytest fixture names like "setup"
                    if word.lower() == 'setup' and 'def ' in line and '(self' not in line:
                        if re.search(r'def\s+\w*setup\w*\(', line, re.IGNORECASE):
                            continue

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
                    violations = scan_file_for_words(file_path, args.forbidden, args.context_sensitive)

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
