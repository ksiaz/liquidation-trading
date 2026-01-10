#!/usr/bin/env python3
"""
Semantic Leak Scanner - Directory-Scoped Rule-Class Detection
Purpose: Detect forbidden semantic terms with context-aware enforcement
Authority: DIRECTORY_SCOPED_SEMANTIC_RULES.md, AD-001

Version: 2.0 (Rule-Class Aware)
"""

import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass
from enum import Enum

# ==============================================================================
# RULE CLASSIFICATION
# ==============================================================================

class RuleClass(Enum):
    """Semantic rule classifications per DIRECTORY_SCOPED_SEMANTIC_RULES.md"""
    EVAL = "evaluative"
    INTENT = "action-implying"
    QUALITY = "confidence/correctness"
    STRUCTURAL_METRIC = "numeric-descriptor"
    AGGREGATION = "statistical-operation"
    TEMPORAL_PARAMETER = "duration-threshold"
    DESCRIPTIVE_STATE = "binary-fact"

# ==============================================================================
# PATTERN DEFINITIONS (Classified by Rule Class)
# ==============================================================================

# EVAL - Forbidden everywhere
R1_EVAL = re.compile(
    r'\b(strong|weak|good|bad|healthy|optimal|ideal|better|worse|'
    r'valid|invalid|correct|incorrect|reliable|accurate|'
    r'significant|normal|abnormal|momentum|reversal|bullish|bearish)\b',
    re.IGNORECASE
)

# STRUCTURAL_METRIC - Context-dependent (allowed in observation/memory)
R2_STRUCTURAL_METRIC = re.compile(
    r'\b(max|min|sum|count|avg|mean|total|delta)_\w+|'
    r'\w+_(penetration|velocity|duration|span|deviation|compactness|anchor|absence)',
    re.IGNORECASE
)

# AGGREGATION - Context-dependent (allowed in observation/memory)
R3_AGGREGATION = re.compile(
    r'\blen\(|\.count\(|max\(|min\(|sum\(|mean\(|'
    r'\b(if|while)\s+len\(',
    re.IGNORECASE
)

# TEMPORAL_PARAMETER - Context-dependent (allowed in observation/memory)
R4_TEMPORAL_PARAM = re.compile(
    r'\b(threshold|window|duration|timeout|delay|cooldown|debounce)\s*[=:]',
    re.IGNORECASE
)

# INTENT - Forbidden in observation/memory
R5_INTENT = re.compile(
    r'\b(should|must|ready|actionable|executable|tradeable)\b',
    re.IGNORECASE
)

# QUALITY - Forbidden in observation/memory
R6_QUALITY = re.compile(
    r'\b(confidence|quality|health)\s*[=:]',
    re.IGNORECASE
)

# ==============================================================================
# DIRECTORY-SCOPED RULES
# ==============================================================================

DIRECTORY_RULES: Dict[str, Dict[str, Set[RuleClass]]] = {
    'observation/': {
        'allowed': {
            RuleClass.STRUCTURAL_METRIC,
            RuleClass.AGGREGATION,
            RuleClass.TEMPORAL_PARAMETER,
            RuleClass.DESCRIPTIVE_STATE
        },
        'forbidden': {
            RuleClass.EVAL,
            RuleClass.INTENT,
            RuleClass.QUALITY
        }
    },
    'memory/': {
        'allowed': {
            RuleClass.STRUCTURAL_METRIC,
            RuleClass.AGGREGATION,
            RuleClass.DESCRIPTIVE_STATE
        },
        'forbidden': {
            RuleClass.EVAL,
            RuleClass.INTENT,
            RuleClass.QUALITY,
            RuleClass.TEMPORAL_PARAMETER
        }
    },
    'runtime/': {
        'allowed': {
            RuleClass.STRUCTURAL_METRIC,
            RuleClass.AGGREGATION
        },
        'forbidden': {
            RuleClass.EVAL,
            RuleClass.INTENT,
            RuleClass.QUALITY
        }
    },
    'ui/': {
        'allowed': set(),
        'forbidden': '__ALL__'
    }
}

# Default: Strict (fail-closed)
DEFAULT_RULES = {
    'allowed': set(),
    'forbidden': '__ALL__'
}

# ==============================================================================
# FILE-TO-RULES MAPPING (with Rule Classes)
# ==============================================================================

RULES: Dict[str, List[Tuple[str, re.Pattern, RuleClass]]] = {
    'observation/types.py': [
        ('R1-EVAL', R1_EVAL, RuleClass.EVAL),
        ('R2-STRUCTURAL_METRIC', R2_STRUCTURAL_METRIC, RuleClass.STRUCTURAL_METRIC),
        ('R3-AGGREGATION', R3_AGGREGATION, RuleClass.AGGREGATION),
        ('R4-TEMPORAL_PARAM', R4_TEMPORAL_PARAM, RuleClass.TEMPORAL_PARAMETER),
        ('R5-INTENT', R5_INTENT, RuleClass.INTENT),
        ('R6-QUALITY', R6_QUALITY, RuleClass.QUALITY),
    ],
    'observation/governance.py': [
        ('R1-EVAL', R1_EVAL, RuleClass.EVAL),
        ('R2-STRUCTURAL_METRIC', R2_STRUCTURAL_METRIC, RuleClass.STRUCTURAL_METRIC),
        ('R3-AGGREGATION', R3_AGGREGATION, RuleClass.AGGREGATION),
        ('R4-TEMPORAL_PARAM', R4_TEMPORAL_PARAM, RuleClass.TEMPORAL_PARAMETER),
        ('R5-INTENT', R5_INTENT, RuleClass.INTENT),
        ('R6-QUALITY', R6_QUALITY, RuleClass.QUALITY),
    ],
}

# ==============================================================================
# VIOLATION DATACLASS
# ==============================================================================

@dataclass
class Violation:
    filepath: str
    line_num: int
    rule_name: str
    rule_class: RuleClass
    line_content: str
    verdict: str
    reason: str

# ==============================================================================
# SCANNER LOGIC
# ==============================================================================

def get_directory_rules(filepath: str) -> dict:
    """Get rule set for directory (fail-closed)."""
    for dir_prefix in DIRECTORY_RULES:
        if filepath.startswith(dir_prefix):
            return DIRECTORY_RULES[dir_prefix]
    return DEFAULT_RULES

def get_violation_reason(filepath: str, rule_class: RuleClass) -> str:
    """Generate human-readable reason for violation."""
    if filepath.startswith('observation/'):
        if rule_class == RuleClass.EVAL:
            return "Observation layer must not make evaluative judgments"
        elif rule_class == RuleClass.INTENT:
            return "Observation describes facts, execution decides actions"
        elif rule_class == RuleClass.QUALITY:
            return "Observations are measurements, not assessments"
    elif filepath.startswith('memory/'):
        if rule_class == RuleClass.EVAL:
            return "Memory layer must not evaluate or interpret"
        elif rule_class == RuleClass.TEMPORAL_PARAMETER:
            return "Memory stores state, observation defines temporal parameters"
    elif filepath.startswith('runtime/'):
        if rule_class == RuleClass.EVAL:
            return "Runtime must not use evaluative language"
        elif rule_class == RuleClass.INTENT:
            return "Intent only allowed in audited mandate emission"
    elif filepath.startswith('ui/'):
        return "UI must display facts only, no semantic terms allowed"
    
    return f"{rule_class.value} is forbidden in this directory"

def scan_file(
    filepath: Path,
    rules: List[Tuple[str, re.Pattern, RuleClass]],
    repo_root: Path
) -> List[Violation]:
    """
    Scan file with rule-class awareness.
    
    Returns:
        List of violations (only forbidden patterns)
    """
    violations = []
    rel_path = str(filepath.relative_to(repo_root)).replace('\\', '/')  # Normalize to forward slashes
    dir_rules = get_directory_rules(rel_path)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comment-only lines
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                
                for rule_name, pattern, rule_class in rules:
                    if pattern.search(line):
                        # Check if allowed in this directory
                        if rule_class in dir_rules['allowed']:
                            # Allowed - don't report
                            continue
                        elif dir_rules['forbidden'] == '__ALL__' or rule_class in dir_rules['forbidden']:
                            # Forbidden - report it
                            violations.append(Violation(
                                filepath=rel_path,
                                line_num=line_num,
                                rule_name=rule_name,
                                rule_class=rule_class,
                                line_content=line.strip(),
                                verdict="FORBIDDEN",
                                reason=get_violation_reason(rel_path, rule_class)
                            ))
                        else:
                            # Not explicitly allowed = forbidden (fail-closed)
                            violations.append(Violation(
                                filepath=rel_path,
                                line_num=line_num,
                                rule_name=rule_name,
                                rule_class=rule_class,
                                line_content=line.strip(),
                                verdict="FORBIDDEN",
                                reason=f"{rule_class.value} not explicitly allowed in this directory"
                            ))
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return violations

def main():
    """Main entry point."""
    # Parse arguments (keep for backward compatibility, but no longer used)
    parser = argparse.ArgumentParser(description='Semantic Leak Scanner (Rule-Class Aware)')
    parser.add_argument(
        '--exclude-paths',
        type=str,
        help='[DEPRECATED] Use directory-scoped rules instead'
    )
    args = parser.parse_args()
    
    if args.exclude_paths:
        print("⚠️  --exclude-paths is deprecated. Scanner now uses directory-scoped rules.")
        print("    See: docs/DIRECTORY_SCOPED_SEMANTIC_RULES.md")
    
    all_violations = {}
    
    # Get repository root
    repo_root = Path(__file__).parent.parent.parent
    
    # Scan each configured file
    for rel_path, rules in RULES.items():
        filepath = repo_root / rel_path
        
        if not filepath.exists():
            continue
        
        violations = scan_file(filepath, rules, repo_root)
        
        if violations:
            all_violations[rel_path] = violations
    
    # Report results
    if all_violations:
        print("=" * 80)
        print("SEMANTIC LEAK VIOLATIONS DETECTED")
        print("=" * 80)
        
        for filepath, violations in all_violations.items():
            print(f"\n{filepath}:")
            for v in violations:
                print(f"  Line {v.line_num}: [{v.rule_name}] [{v.rule_class.value}]")
                print(f"    {v.line_content}")
                print(f"  Verdict: {v.verdict}")
                print(f"  Reason: {v.reason}")
        
        print("\n" + "=" * 80)
        print(f"Total violations: {sum(len(v) for v in all_violations.values())}")
        print("=" * 80)
        print("\nSee: docs/DIRECTORY_SCOPED_SEMANTIC_RULES.md")
        print("See: docs/ARCHITECTURAL_DECISIONS.md (AD-001)")
        
        sys.exit(1)
    
    print("[OK] No semantic leaks detected")
    sys.exit(0)


if __name__ == '__main__':
    main()
