#!/usr/bin/env python3
"""
Verify state machine transition table matches schema

Usage:
    python3 verify_state_machine.py --schema SYSTEM_MAP_SCHEMA.yaml --module runtime/position/state_machine.py --machine position_lifecycle --fail-on-mismatch
"""

import sys
import ast
import yaml
import argparse

def extract_transition_table(file_path):
    """Extract ALLOWED_TRANSITIONS from state machine file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=file_path)

        # Find ALLOWED_TRANSITIONS dict
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'ALLOWED_TRANSITIONS':
                        # Extract dict structure
                        transitions = []
                        if isinstance(node.value, ast.Dict):
                            for key, value in zip(node.value.keys, node.value.values):
                                if isinstance(key, ast.Tuple) and len(key.elts) == 2:
                                    from_state = ast.unparse(key.elts[0]) if hasattr(ast, 'unparse') else 'UNKNOWN'
                                    action = ast.unparse(key.elts[1]) if hasattr(ast, 'unparse') else 'UNKNOWN'
                                    to_state = ast.unparse(value) if hasattr(ast, 'unparse') else 'UNKNOWN'

                                    # Clean up quotes and enum names
                                    from_state = from_state.replace('PositionState.', '').strip('"\'')
                                    action = action.replace('Action.', '').strip('"\'')
                                    to_state = to_state.replace('PositionState.', '').strip('"\'')

                                    transitions.append({
                                        'from': from_state,
                                        'action': action,
                                        'to': to_state
                                    })
                        return transitions

        return []
    except Exception as e:
        print(f"ERROR: Could not parse {file_path}: {e}")
        return []

def compare_transitions(schema_transitions, code_transitions):
    """Compare schema and code transition tables"""
    mismatches = []

    # Normalize schema transitions
    schema_set = set()
    for t in schema_transitions:
        schema_set.add((t['from'], t['action'], t['to']))

    # Normalize code transitions
    code_set = set()
    for t in code_transitions:
        code_set.add((t['from'], t['action'], t['to']))

    # Find differences
    missing_in_code = schema_set - code_set
    extra_in_code = code_set - schema_set

    for t in missing_in_code:
        mismatches.append(f"Missing in code: {t[0]} --[{t[1]}]--> {t[2]}")

    for t in extra_in_code:
        mismatches.append(f"Extra in code: {t[0]} --[{t[1]}]--> {t[2]}")

    return mismatches

def main():
    parser = argparse.ArgumentParser(description='Verify state machine transitions')
    parser.add_argument('--schema', required=True, help='Path to schema file')
    parser.add_argument('--module', required=True, help='Path to state machine module')
    parser.add_argument('--machine', required=True, help='Machine name in schema')
    parser.add_argument('--fail-on-mismatch', action='store_true', help='Exit 1 on mismatches')

    args = parser.parse_args()

    # Load schema
    try:
        with open(args.schema, 'r') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Could not load schema: {e}")
        sys.exit(1)

    # Get schema transitions
    try:
        schema_transitions = schema['state_machines'][args.machine]['transitions']['allowed']
    except KeyError:
        print(f"ERROR: Machine '{args.machine}' not found in schema")
        sys.exit(1)

    # Extract code transitions
    code_transitions = extract_transition_table(args.module)

    if not code_transitions:
        print(f"WARNING: No transitions found in {args.module}")
        if args.fail_on_mismatch:
            sys.exit(1)

    # Compare
    mismatches = compare_transitions(schema_transitions, code_transitions)

    if mismatches:
        print("=" * 60)
        print("STATE MACHINE TRANSITION MISMATCH")
        print("=" * 60)
        for m in mismatches:
            print(f"✗ {m}")
        print(f"\nTotal mismatches: {len(mismatches)}")

        if args.fail_on_mismatch:
            sys.exit(1)
    else:
        print(f"✓ State machine transitions match schema ({len(schema_transitions)} transitions)")

if __name__ == "__main__":
    main()
