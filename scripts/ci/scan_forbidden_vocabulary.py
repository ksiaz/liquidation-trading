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

# ==============================================================================
# EXCEPTIONS (with constitutional justification)
# ==============================================================================

# Files exempt from vocabulary checks entirely
EXEMPT_FILES = {
    # Test files
    'test_': "Test files are exempt",
    '/tests/': "Test directory is exempt",
}

# Word-specific exemptions by file path pattern
# Format: {word: [list of path patterns where word is allowed]}
WORD_EXEMPTIONS = {
    'regime': [
        'regime_classifier',  # Component name
        'masterframe/regime',  # Regime module
        'runtime/regime',  # Runtime regime module
        'ep2_effcs_strategy',  # Strategy uses regime
        'ep2_slbrs_strategy',  # Strategy uses regime
        'policy_adapter',  # Passes regime to strategies
        'collector/service',  # Collector tracks regime
        'analytics/',  # Analytics tracks regime for journaling
        'native_app/',  # UI displays regime
        'indicators/',  # ATR/VWAP for regime classification
        'liquidations/',  # Z-score for regime classification
        'orderflow/',  # Imbalance for regime classification
        'logging/execution_db',  # Database schema
        'meta/',  # System regime detector
        'risk/',  # Capital management uses regime
    ],
    'momentum': [
        'm4_cascade_momentum',  # M4 primitive name
        'cascade_momentum',  # Component reference
        'hyperliquid/',  # Hyperliquid tracking
        'ep2_strategy_cascade_sniper',  # Strategy uses cascade momentum
    ],
    'bias': [
        'm4_open_interest_bias',  # M4 primitive name
        'open_interest_bias',  # Component reference
        'directional_bias',  # Component reference
        'governance.py',  # Computes bias primitive
        'native_app/',  # UI panels (whale bias display)
        'meta/',  # Design bias protection documentation
        'regime/classifier',  # Imbalance bias threshold
    ],
    'pressure': [
        'm2_pressure',  # M2 module name
        'memory_pressure',  # Component reference
        'm2_continuity_store',  # Memory pressure method
        'stop_hunt_detector',  # Absorption pressure (technical)
        'ep4_ghost_tracker',  # Market pressure context
        'entry_quality',  # Exhaustion pressure context
    ],
    'signal': [
        'm4_cascade_state',  # Documentation about what it cannot be
        'ep2_strategy_absence',  # Documents what is not a signal
        'hyperliquid/',  # WebSocket signal (technical term)
        'ws_position_tracker',  # Technical signal term
        'liquidation_fade',  # Technical signal term
        'client.py',  # API documentation
        'ep4_ghost_tracker',  # Liquidation signal strength (technical)
        'stop_hunt_detector',  # Detection signal (technical)
        'native_app/',  # Qt Signal class, UI signal handling
        'terminal_app/',  # Python signal module
        'entry_quality',  # Documentation about signal strength
    ],
    'opportunity': [
        'ep2_effcs_strategy',  # Method name (constitutional: no semantic interpretation)
        'ep2_slbrs_strategy',  # Method name (constitutional: no semantic interpretation)
        'ep2_strategy_cascade_sniper',  # Method name
        'arbitration/types',  # Comment in enum
        'ep4_ghost_tracker',  # Entry opportunity method
        'stop_hunt_detector',  # Entry opportunity method
        'entry_quality',  # Entry opportunity scoring method
    ],
    'edge': [
        'ep2_slbrs_strategy',  # "block edge" - geometric term, not semantic
        'meta/',  # System edge detector (legitimate component)
        'native_app/',  # Chart edge positioning (geometric)
    ],
    'setup': [
        'env_setup',  # File name
        'position_tracker',  # Method name (setup wallets)
        'entry_quality',  # "reversal setup" - technical term
    ],
    'alpha': [
        'indicators/',  # EMA alpha smoothing constant (mathematical)
    ],
    'momentum': [
        'm4_cascade_momentum',  # M4 primitive name
        'cascade_momentum',  # Component reference
        'hyperliquid/',  # Hyperliquid tracking
        'ep2_strategy_cascade_sniper',  # Strategy uses cascade momentum
        'regime/',  # Regime classifier documents momentum behavior
        'm4_absorption_confirmation',  # Documentation of cascade sniper mode
    ],
    'regime': [
        'm4_absorption_confirmation',  # Technical term for market context (volatility/liquidity state)
        'regime_classifier',  # Component name
        'masterframe/regime',  # Regime module
        'runtime/regime',  # Runtime regime module
        'ep2_effcs_strategy',  # Strategy uses regime
        'ep2_slbrs_strategy',  # Strategy uses regime
        'policy_adapter',  # Passes regime to strategies
        'collector/service',  # Collector tracks regime
        'analytics/',  # Analytics tracks regime for journaling
        'native_app/',  # UI displays regime
        'indicators/',  # ATR/VWAP for regime classification
        'liquidations/',  # Z-score for regime classification
        'orderflow/',  # Imbalance for regime classification
        'logging/execution_db',  # Database schema
        'meta/',  # System regime detector
        'risk/',  # Capital management uses regime
        'entry_quality',  # TrendRegimeContext parameter type
        'ep2_strategy_cascade_sniper',  # TrendRegimeContext parameter type
    ],
    'trend': [
        # TrendDirection/TrendRegimeContext - observable price structure, not prediction
        'm4_absorption_confirmation',  # Trend primitive computation (price structure)
        'observation/types',  # Re-exports TrendRegimeContext
        'entry_quality',  # Kill-switch uses trend context
        'ep2_strategy_cascade_sniper',  # Strategy uses trend for reversal blocking
        'policy_adapter',  # Wires trend context to strategies
    ],
}

def is_exempt_file(file_path):
    """Check if file is completely exempt from vocabulary checks."""
    normalized = file_path.replace('\\', '/')

    for pattern in EXEMPT_FILES:
        if pattern in normalized:
            return True

    return False

def is_word_exempt_in_file(word, file_path):
    """Check if specific word is exempt in specific file."""
    normalized = file_path.replace('\\', '/')
    word_lower = word.lower()

    if word_lower in WORD_EXEMPTIONS:
        for pattern in WORD_EXEMPTIONS[word_lower]:
            if pattern in normalized:
                return True

    return False

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
    # Check if entire file is exempt
    if is_exempt_file(file_path):
        return []

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
                # Check if word is exempt in this file
                if is_word_exempt_in_file(word, file_path):
                    continue

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
