#!/usr/bin/env python3
"""
Check documentation-code correspondence (warning only)

Usage:
    python3 check_doc_correspondence.py --schema SYSTEM_MAP_SCHEMA.yaml --warn-on-missing
"""

import sys
import yaml
import argparse

def main():
    parser = argparse.ArgumentParser(description='Check doc-code correspondence')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--warn-on-missing', action='store_true')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Check doc bindings
    doc_bindings = schema.get('doc_bindings', {})
    missing = []

    for doc_name, doc_data in doc_bindings.items():
        sections = doc_data.get('sections', [])
        for section in sections:
            if section.get('coverage') == 'missing':
                missing.append({
                    'document': doc_name,
                    'section': section.get('section')
                })

    if missing:
        print("=" * 60)
        print("DOC-CODE CORRESPONDENCE WARNINGS")
        print("=" * 60)
        for item in missing:
            print(f"⚠ [{item['document']}] {item['section']}")
            print(f"  Status: Documented but not implemented")
        print(f"\nTotal warnings: {len(missing)}")
        print("\nThis is informational only - does not block merge")
    else:
        print(f"✓ All documented rules have code mappings")

if __name__ == "__main__":
    main()
