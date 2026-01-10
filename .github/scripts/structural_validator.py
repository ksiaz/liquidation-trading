#!/usr/bin/env python3
"""
Structural Validator
Purpose: Detect structural violations (type exposure, boolean flags, mutations)
Authority: DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md Section 4.3
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple

# ==============================================================================
# STRUCTURAL CHECKS
# ==============================================================================

def check_observation_snapshot_boolean_flags(filepath: Path) -> List[Tuple[int, str]]:
    """
    Check ObservationSnapshot for interpretive boolean flags.
    
    Forbidden: is_ready, has_baseline, can_trade, etc.
    """
    violations = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(filepath))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'ObservationSnapshot':
                for item in node.body:
                    if isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name):
                            field_name = item.target.id
                            
                            # Check for interpretive boolean patterns
                            if field_name.startswith(('is_', 'has_', 'can_', 'should_', 'must_')):
                                violations.append((
                                    item.lineno,
                                    f"Boolean flag with interpretation: {field_name}"
                                ))
    
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error checking {filepath}: {e}", file=sys.stderr)
    
    return violations


def check_internal_type_exposure(filepath: Path) -> List[Tuple[int, str]]:
    """
    Check for internal types exposed in public method signatures.
    
    Example forbidden:
        def query(...) -> PromotedEventInternal  # Internal type exposed!
    """
    violations = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=str(filepath))
        
        # Check for imports from observation.internal in observation/governance.py
        has_internal_imports = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and 'observation.internal' in node.module:
                    has_internal_imports = True
                    violations.append((
                        node.lineno,
                        f"Imports from observation.internal: {node.module}"
                    ))
        
        # If internal imports exist, check method signatures
        if has_internal_imports:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check if it's a public method (doesn't start with _)
                    if not node.name.startswith('_'):
                        # Check return annotation
                        if node.returns:
                            return_annotation = ast.unparse(node.returns)
                            # Simple heuristic: check for types with "Internal" in name
                            if 'Internal' in return_annotation or 'Baseline' in return_annotation:
                                violations.append((
                                    node.lineno,
                                    f"Public method '{node.name}' returns internal type: {return_annotation}"
                                ))
    
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error checking {filepath}: {e}", file=sys.stderr)
    
    return violations


def check_mutation_during_read(filepath: Path) -> List[Tuple[int, str]]:
    """
    Check for state mutations in query/getter methods.
    
    Forbidden:
        def query(...):
            self._query_count += 1  # Mutation during read!
    """
    violations = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(filepath))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check if method name suggests it's a read operation
                if node.name in ['query', 'get_snapshot', '_get_snapshot']:
                    # Look for assignments to self._*
                    for stmt in ast.walk(node):
                        if isinstance(stmt, (ast.Assign, ast.AugAssign)):
                            # Check if assigning to self._something
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Attribute):
                                        if isinstance(target.value, ast.Name) and target.value.id == 'self':
                                            if target.attr.startswith('_'):
                                                violations.append((
                                                    stmt.lineno,
                                                    f"Mutation during read in '{node.name}': self.{target.attr}"
                                                ))
                            
                            elif isinstance(stmt, ast.AugAssign):
                                if isinstance(stmt.target, ast.Attribute):
                                    if isinstance(stmt.target.value, ast.Name) and stmt.target.value.id == 'self':
                                        if stmt.target.attr.startswith('_'):
                                            violations.append((
                                                stmt.lineno,
                                                f"Mutation during read in '{node.name}': self.{stmt.target.attr}"
                                            ))
    
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error checking {filepath}: {e}", file=sys.stderr)
    
    return violations


# ==============================================================================
# VALIDATOR
# ==============================================================================

def validate_structure(repo_root: Path) -> List[Tuple[str, int, str]]:
    """
    Run all structural validations.
    
    Returns:
        List of (filepath, line_number, violation_message)
    """
    all_violations = []
    
    # Check 1: ObservationSnapshot boolean flags
    types_file = repo_root / 'observation' / 'types.py'
    if types_file.exists():
        violations = check_observation_snapshot_boolean_flags(types_file)
        for line_num, msg in violations:
            all_violations.append(('observation/types.py', line_num, msg))
    
    # Check 2: Internal type exposure in governance.py
    gov_file = repo_root / 'observation' / 'governance.py'
    if gov_file.exists():
        violations = check_internal_type_exposure(gov_file)
        for line_num, msg in violations:
            all_violations.append(('observation/governance.py', line_num, msg))
    
    # Check 3: Mutation during read in governance.py
    if gov_file.exists():
        violations = check_mutation_during_read(gov_file)
        for line_num, msg in violations:
            all_violations.append(('observation/governance.py', line_num, msg))
    
    return all_violations


def main():
    """Main entry point."""
    # Get repository root
    repo_root = Path(__file__).parent.parent.parent
    
    # Run validations
    violations = validate_structure(repo_root)
    
    if violations:
        print("=" * 80)
        print("STRUCTURAL VIOLATIONS")
        print("=" * 80)
        
        for filepath, line_num, msg in violations:
            print(f"\n{filepath}:{line_num}")
            print(f"  {msg}")
        
        print("\n" + "=" * 80)
        print(f"Total violations: {len(violations)}")
        print("=" * 80)
        print("\nSee: docs/ADVERSARIAL_CODE_EXAMPLES.md")
        print("See: docs/DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md Section 4.3")
        
        sys.exit(1)  # Fail CI
    
    print("[OK] No structural violations detected")
    sys.exit(0)  # Pass


if __name__ == '__main__':
    main()
