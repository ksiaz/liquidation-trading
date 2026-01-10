#!/usr/bin/env python3
"""
Import Validator
Purpose: Detect cross-boundary imports that violate architectural isolation
Authority: DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md Section 4.1
"""

import ast
import sys
from pathlib import Path
from typing import List, Set, Tuple

# ==============================================================================
# FORBIDDEN IMPORT PATTERNS
# ==============================================================================

FORBIDDEN_IMPORTS = {
    # observation/__init__.py must not import from internal
    'observation/__init__.py': [
        'observation.internal',
    ],

    # observation/*.py (non-internal) must not import from internal
    'observation/*.py': [
        'observation.internal',
    ],

    # observation/ must never import from runtime
    'observation/**/*.py': [
        'runtime.m6_executor',
        'runtime.collector',
        'runtime.native_app',
    ],

    # runtime/ must not import from observation.internal
    'runtime/**/*.py': [
        'observation.internal',
    ],

    # M6 (runtime/) must not import M5 (memory/m5_*)
    # Per ANNEX_M4_PRIMITIVE_FLOW.md: Primitives flow via ObservationSnapshot only
    'runtime/**/*.py': [
        'memory.m5_access',
        'memory.m5_query_schemas',
        'memory.m5_guards',
        'memory.m5_defaults',
        'memory.m5_output_normalizer',
    ],
}

# ==============================================================================
# IMPORT EXTRACTION
# ==============================================================================

def get_imports(filepath: Path) -> Set[str]:
    """
    Extract all import statements from a Python file.
    
    Returns:
        Set of imported module names
    """
    imports = set()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(filepath))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
    
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error parsing {filepath}: {e}", file=sys.stderr)
    
    return imports


def matches_pattern(import_str: str, pattern: str) -> bool:
    """
    Check if an import matches a forbidden pattern.
    
    Patterns:
        'observation.internal' matches 'observation.internal.m3_temporal'
        Supports glob-like wildcards via startswith
    """
    if pattern.endswith('.*'):
        prefix = pattern[:-2]
        return import_str.startswith(prefix)
    
    return import_str == pattern or import_str.startswith(pattern + '.')


# ==============================================================================
# VALIDATOR
# ==============================================================================

def validate_imports(repo_root: Path) -> List[Tuple[str, str, str]]:
    """
    Validate imports across the repository.
    
    Returns:
        List of (filepath, import, rule) violations
    """
    violations = []
    
    # Check observation/__init__.py
    init_file = repo_root / 'observation' / '__init__.py'
    if init_file.exists():
        imports = get_imports(init_file)
        forbidden = FORBIDDEN_IMPORTS.get('observation/__init__.py', [])
        
        for imp in imports:
            for forbidden_pattern in forbidden:
                if matches_pattern(imp, forbidden_pattern):
                    violations.append((
                        'observation/__init__.py',
                        imp,
                        f'Forbidden: {forbidden_pattern}'
                    ))
    
    # Check observation/*.py (exclude __init__.py and internal/)
    obs_dir = repo_root / 'observation'
    if obs_dir.exists():
        for pyfile in obs_dir.glob('*.py'):
            if pyfile.name == '__init__.py':
                continue
            
            imports = get_imports(pyfile)
            forbidden = FORBIDDEN_IMPORTS.get('observation/*.py', [])
            
            for imp in imports:
                for forbidden_pattern in forbidden:
                    if matches_pattern(imp, forbidden_pattern):
                        violations.append((
                            f'observation/{pyfile.name}',
                            imp,
                            f'Forbidden: {forbidden_pattern}'
                        ))
    
    # Check observation/**/*.py (all files, check for runtime imports)
    if obs_dir.exists():
        for pyfile in obs_dir.rglob('*.py'):
            imports = get_imports(pyfile)
            forbidden = FORBIDDEN_IMPORTS.get('observation/**/*.py', [])
            
            for imp in imports:
                for forbidden_pattern in forbidden:
                    if matches_pattern(imp, forbidden_pattern):
                        rel_path = pyfile.relative_to(repo_root)
                        violations.append((
                            str(rel_path),
                            imp,
                            f'Forbidden: {forbidden_pattern}'
                        ))
    
    # Check runtime/**/*.py
    runtime_dir = repo_root / 'runtime'
    if runtime_dir.exists():
        for pyfile in runtime_dir.rglob('*.py'):
            imports = get_imports(pyfile)
            forbidden = FORBIDDEN_IMPORTS.get('runtime/**/*.py', [])
            
            for imp in imports:
                for forbidden_pattern in forbidden:
                    if matches_pattern(imp, forbidden_pattern):
                        rel_path = pyfile.relative_to(repo_root)
                        violations.append((
                            str(rel_path),
                            imp,
                            f'Forbidden: {forbidden_pattern}'
                        ))
    
    return violations


def main():
    """Main entry point."""
    # Get repository root
    repo_root = Path(__file__).parent.parent.parent
    
    # Validate imports
    violations = validate_imports(repo_root)
    
    if violations:
        print("=" * 80)
        print("FORBIDDEN IMPORT VIOLATIONS")
        print("=" * 80)
        
        for filepath, import_str, rule in violations:
            print(f"\n{filepath}:")
            print(f"  imports: {import_str}")
            print(f"  {rule}")
        
        print("\n" + "=" * 80)
        print(f"Total violations: {len(violations)}")
        print("=" * 80)
        print("\nSee: docs/DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md Section 4.1")
        
        sys.exit(1)  # Fail CI
    
    print("[OK] No forbidden imports detected")
    sys.exit(0)  # Pass


if __name__ == '__main__':
    main()
