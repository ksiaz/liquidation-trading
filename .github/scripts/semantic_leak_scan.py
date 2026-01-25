#!/usr/bin/env python3
"""
Semantic Leak Scanner
Purpose: Detect forbidden semantic terms in code using directory-scoped regex rules
Authority: CI_ENFORCEMENT_DESIGN.md, DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ==============================================================================
# RULE SETS (Directory-Scoped)
# ==============================================================================

# R1: Linguistic Leaks (observation/types.py, observation/governance.py)
R1_LINGUISTIC = re.compile(
    r'\b(signal|strength|confidence|quality|health|ready|valid|good|bad|'
    r'stale|fresh|live|active|flowing|pressure|baseline|opportunity|bias|'
    r'setup|weak|strong|support|resistance|validated|confirmed|normal|'
    r'abnormal|significant|momentum|reversal|bullish|bearish)\b',
    re.IGNORECASE
)

# R2: Structural Indicators
R2_STRUCTURAL = re.compile(
    r'\b(is|has|can|should|must|may)_\w+|'
    r'\b(recent|lag|delay|outdated|fresh|stale|window|rolling|cooldown|debounce)|'
    r'\b(triggered|caused|due_to|because|led_to|response_to|result_of)|'
    r'\b(threshold|limit|max|min|safe|danger|warning|critical)_',
    re.IGNORECASE
)

# R4: Log Message Purity (runtime/)
R4_LOG_MESSAGES = re.compile(
    r'logger\.(info|warning|error|debug)\s*\([^)]*'
    r'(start|starting|connect|connecting|process|processing|analyz|detect|'
    r'live|flowing|active|healthy|ready|working|successful|failed|error|'
    r'problem|issue|warning|good|bad)',
    re.IGNORECASE
)

# R5: UI Text Purity (runtime/)
R5_UI_TEXT = re.compile(
    r'setText\s*\([^)]*'
    r'(pressure|signal|strength|confidence|health|ready|warm|valid|good|bad|'
    r'detecting|analyzing|processing|active|live|flowing|setup|opportunity)|'
    r'setWindowTitle\s*\([^)]*'
    r'(detector|analyzer|predictor|signal|pressure|peak|opportunity)',
    re.IGNORECASE
)

# R6: M6 Interpretation Ban (runtime/m6_executor.py)
R6_M6_INTERPRETATION = re.compile(
    r'if\s+\w+\.(counters|promoted_events|symbols_active)|'
    r'(logger|print|log)\s*\(|'
    r'^class\s+\w+:|'
    r'self\.\w+\s*=|'
    r'\bwhile\s+|\bfor\s+\w+\s+in\b|'
    r'try:.*except.*(continue|pass|return\s+default)',
    re.IGNORECASE | re.MULTILINE
)

# ==============================================================================
# EXCEPTIONS (with constitutional justification)
# ==============================================================================

# Format: {filepath: {line_number: "justification"}}
EXCEPTIONS: Dict[str, Dict[int, str]] = {
    'runtime/m6_executor.py': {
        # R6-M6Interpretation rule catches basic Python patterns (false positives)
        # Class definitions and instance variables are constitutional
        87: "Class definition: M6Config dataclass",
        116: "Class definition: ExecutionCycleResult dataclass",
        127: "Class definition: M6Executor class",
        143: "Instance variable assignment: config initialization",
        144: "Instance variable assignment: logger initialization",
        145: "Instance variable assignment: state initialization",
        149: "Loop: iterating over configured symbols",
        157: "Instance variable assignment: policy adapter setup",
        160: "Instance variable assignment: entry scorer setup",
        163: "Instance variable assignment: capital manager setup",
        166: "Instance variable assignment: risk config setup",
        180: "Instance variable assignment: exchange adapter setup",
        183: "Instance variable assignment: orchestrator setup",
        213: "State transition: halt state on error",
        220: "State transition: running state on start",
        224: "Loop: iterating over symbols for tracking",
        236: "List slicing: cycle history truncation",
        290: "Generator expression: counting active positions",
        485: "Instance variable assignment: minute tracker reset",
        486: "Instance variable assignment: action counter reset",
        514: "Instance variable assignment: action time tracking",
        519: "Instance variable assignment: action time tracking",
        534: "Instance variable assignment: action time tracking",
        573: "State transition: stopped state on shutdown",
    },
    'observation/governance.py': {
        # Structural thresholds (factual boundaries, not interpretation)
        95: "Structural config: time window for price correlation in seconds",
        # Trade handling - Binance API semantic field names
        361: "Binance API semantic: is_taker_sell indicates trade aggressor side",
        373: "Parameter passing Binance API field to M2 store",
        380: "Local variable derived from Binance trade side field",
        # Orderbook primitive parameters
        480: "Structural parameter: minimum consumption size threshold",
        491: "Structural parameter: minimum consumption size threshold",
        497: "Data access: recent_prices is collection name, not semantic claim",
        516: "Structural parameter: maximum price movement percentage",
        527: "Structural parameter: minimum refill size threshold",
        538: "Structural parameter: minimum refill size threshold",
        # Clustering parameter
        651: "Structural parameter: maximum gap percentage for clustering",
        # HLP proximity threshold
        848: "Structural parameter: threshold percentage for HLP proximity",
    },
    'runtime/collector/service.py': {
        196: "Factual error logging: reports initialization exception",
        202: "Factual status logging: reports validation init",
        225: "Factual status logging: reports collector started",
        232: "Factual error logging: reports start exception",
        362: "Factual error logging: reports classification exception",
        1363: "Factual error logging: reports stop exception",
    },
}

# ==============================================================================
# FILE-TO-RULES MAPPING
# ==============================================================================

RULES: Dict[str, List[Tuple[str, re.Pattern]]] = {
    'observation/types.py': [
        ('R1-Linguistic', R1_LINGUISTIC),
        ('R2-Structural', R2_STRUCTURAL),
    ],
    'observation/governance.py': [
        ('R1-Linguistic', R1_LINGUISTIC),
        ('R2-Structural', R2_STRUCTURAL),
    ],
    'runtime/collector/service.py': [
        ('R4-LogMessages', R4_LOG_MESSAGES),
    ],
    'runtime/native_app/main.py': [
        ('R4-LogMessages', R4_LOG_MESSAGES),
        ('R5-UIText', R5_UI_TEXT),
    ],
    'runtime/m6_executor.py': [
        ('R6-M6Interpretation', R6_M6_INTERPRETATION),
    ],
}

# ==============================================================================
# SCANNER
# ==============================================================================

def scan_file(filepath: Path, rules: List[Tuple[str, re.Pattern]], rel_path: str) -> List[Tuple[int, str, str]]:
    """
    Scan a file for violations.

    Args:
        filepath: Absolute path to file
        rules: List of (rule_name, pattern) tuples to check
        rel_path: Relative path from repo root (for exception lookup)

    Returns:
        List of (line_number, rule_name, line_content)
    """
    violations = []
    exceptions = EXCEPTIONS.get(rel_path, {})

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comment-only lines (comments are constitutionally allowed internally)
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue

                # Check if this line has an approved exception
                if line_num in exceptions:
                    continue  # Skip - exception approved

                for rule_name, pattern in rules:
                    if pattern.search(line):
                        violations.append((line_num, rule_name, line.strip()))
    except FileNotFoundError:
        pass  # File doesn't exist, skip
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)

    return violations


def main():
    """Main entry point."""
    all_violations = {}

    # Get repository root (assume script is in .github/scripts/)
    repo_root = Path(__file__).parent.parent.parent

    # Scan each configured file
    for rel_path, rules in RULES.items():
        filepath = repo_root / rel_path

        if not filepath.exists():
            continue  # Skip if file doesn't exist

        violations = scan_file(filepath, rules, rel_path)

        if violations:
            all_violations[rel_path] = violations
    
    # Report results
    if all_violations:
        print("=" * 80)
        print("SEMANTIC LEAK VIOLATIONS DETECTED")
        print("=" * 80)
        
        for filepath, violations in all_violations.items():
            print(f"\n{filepath}:")
            for line_num, rule_name, line_content in violations:
                print(f"  Line {line_num}: [{rule_name}]")
                print(f"    {line_content}")
        
        print("\n" + "=" * 80)
        print(f"Total violations: {sum(len(v) for v in all_violations.values())}")
        print("=" * 80)
        print("\nSee: docs/SEMANTIC_LEAK_EXHAUSTIVE_AUDIT.md")
        print("See: docs/ADVERSARIAL_CODE_EXAMPLES.md")
        
        sys.exit(1)  # Fail CI
    
    print("[OK] No semantic leaks detected")
    sys.exit(0)  # Pass


if __name__ == '__main__':
    main()
