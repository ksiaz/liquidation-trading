#!/usr/bin/env python3
"""
Verify timestamp units are float seconds (not milliseconds)

Usage:
    python3 check_timestamp_units.py --file observation/internal/m1_ingestion.py --require-division-by-1000 --fail-on-violation
"""

import sys
import re
import argparse

def check_timestamp_conversion(file_path):
    """Check if timestamps are converted from milliseconds to seconds"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Look for timestamp extraction from raw payloads
        # Good: timestamp = int(raw_payload['T']) / 1000.0
        # Bad:  timestamp = int(raw_payload['T'])

        good_patterns = [
            r"timestamp\s*=.*\['[TE]'\]\s*/\s*1000",
            r"timestamp\s*=.*\[\"[TE]\"\]\s*/\s*1000"
        ]

        bad_patterns = [
            r"timestamp\s*=.*\['[TE]'\]\s*(?!/\s*1000)",
            r"timestamp\s*=.*\[\"[TE]\"\]\s*(?!/\s*1000)"
        ]

        has_good = any(re.search(p, content) for p in good_patterns)
        has_bad = any(re.search(p, content) for p in bad_patterns)

        # Find actual timestamp assignments
        timestamp_lines = re.findall(r'timestamp\s*=.*raw_payload.*', content)

        return {
            'has_division': has_good,
            'has_violation': has_bad,
            'lines': timestamp_lines
        }

    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return {'has_division': False, 'has_violation': True, 'lines': []}

def main():
    parser = argparse.ArgumentParser(description='Check timestamp units')
    parser.add_argument('--file', required=True, help='Path to M1 ingestion file')
    parser.add_argument('--require-division-by-1000', action='store_true')
    parser.add_argument('--fail-on-violation', action='store_true')

    args = parser.parse_args()

    # Check timestamp conversion
    result = check_timestamp_conversion(args.file)

    if args.require_division_by_1000 and not result['has_division']:
        print("=" * 60)
        print("TIMESTAMP UNIT VIOLATION")
        print("=" * 60)
        print("Timestamps must be converted from milliseconds to seconds")
        print("Required: timestamp = raw_payload['T'] / 1000.0")
        print(f"\nTimestamp assignments found:")
        for line in result['lines']:
            print(f"  {line}")

        if args.fail_on_violation:
            sys.exit(1)
    else:
        print(f"✓ Timestamp units correct (float seconds)")

if __name__ == "__main__":
    main()
