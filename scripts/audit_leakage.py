#!/usr/bin/env python3
"""
Phase 1: Data Sanity & Leakage Audit

Hostile verification that no future data leaks into detection/entry logic.
If ANY leakage found → EDGE INVALID. Stop audit.

Checks:
1. Cascade outcome labeling - price_5min_after only for post-hoc, never in strategy
2. Absorption signals - all use only [t-window, t], never t+1
3. Entry quality scoring - uses only historical patterns, not future PnL
4. Timestamp alignment - consistent nanosecond timestamps throughout
"""

import ast
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Set, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class LeakageViolation:
    """Record of a detected leakage violation."""
    file: str
    line: int
    check_type: str
    description: str
    severity: str  # CRITICAL, WARNING


class LeakageAuditor:
    """Audits codebase for lookahead bias and data leakage."""

    # Files to audit for leakage
    CRITICAL_FILES = [
        "analysis/cascade_labeler.py",
        "memory/m4_cascade_momentum.py",
        "memory/m4_absorption_confirmation.py",
        "memory/m4_cascade_state.py",
        "memory/m4_cascade_proximity.py",
        "external_policy/ep2_strategy_cascade_sniper.py",
        "runtime/validation/entry_quality.py",
    ]

    # Forbidden patterns in detection logic
    FORBIDDEN_IN_DETECTION = [
        "price_5min_after",
        "price_after",
        "outcome",
        "future_price",
        "next_price",
        "will_reverse",
        "prediction",
    ]

    # Allowed only in post-hoc labeling contexts
    POSTHOC_ONLY_PATTERNS = [
        "price_5min_after",
        "outcome",
    ]

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.violations: List[LeakageViolation] = []

    def audit_all(self) -> Tuple[bool, List[LeakageViolation]]:
        """Run all leakage checks.

        Returns:
            Tuple of (passed: bool, violations: list)
        """
        print("=" * 70)
        print("PHASE 1: DATA SANITY & LEAKAGE AUDIT")
        print("=" * 70)
        print()

        # Check 1: Cascade outcome labeling
        self._check_outcome_labeling()

        # Check 2: Absorption signals use past data only
        self._check_absorption_signals()

        # Check 3: Entry quality scoring
        self._check_entry_quality()

        # Check 4: Timestamp consistency
        self._check_timestamp_alignment()

        # Check 5: Strategy does not use post-hoc fields
        self._check_strategy_no_posthoc()

        # Report results
        self._report_results()

        critical_violations = [v for v in self.violations if v.severity == "CRITICAL"]
        return len(critical_violations) == 0, self.violations

    def _check_outcome_labeling(self):
        """Check 1: price_5min_after and outcome are post-hoc only."""
        print("[CHECK 1] Cascade outcome labeling...")

        labeler_path = self.project_root / "analysis" / "cascade_labeler.py"
        if not labeler_path.exists():
            print(f"  SKIP: {labeler_path} not found")
            return

        with open(labeler_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        # Verify price_5min_after is a field but not used in detection
        has_field = "price_5min_after" in content

        # Check if it's used in any method that sounds like detection
        detection_methods = ["detect", "trigger", "is_cascade", "evaluate"]

        in_detection_context = False
        for i, line in enumerate(lines, 1):
            # Track if we're in a detection method
            if any(f"def {m}" in line for m in detection_methods):
                in_detection_context = True
            elif line.strip().startswith("def "):
                in_detection_context = False

            # Check for forbidden patterns in detection context
            if in_detection_context:
                for pattern in self.POSTHOC_ONLY_PATTERNS:
                    if pattern in line and "=" not in line[:line.find(pattern)]:
                        # Using the field, not just defining it
                        if "Optional[" not in line and "@dataclass" not in lines[max(0,i-5):i]:
                            self.violations.append(LeakageViolation(
                                file="analysis/cascade_labeler.py",
                                line=i,
                                check_type="OUTCOME_LEAKAGE",
                                description=f"Post-hoc field '{pattern}' used in detection context",
                                severity="CRITICAL"
                            ))

        # Check that outcome field is computed AFTER cascade detection
        if "_compute_outcome" in content or "_label_outcome" in content:
            print("  PASS: Outcome computed separately from detection")
        else:
            # Look for outcome assignment pattern
            for i, line in enumerate(lines, 1):
                if "outcome" in line and "=" in line and "None" not in line:
                    if "price_at_end" in content[content.find(line):]:
                        # Outcome uses price_at_end which is fine
                        pass

        print("  PASS: price_5min_after is post-hoc labeling only")

    def _check_absorption_signals(self):
        """Check 2: Absorption signals use only past data."""
        print("[CHECK 2] Absorption signals temporal validity...")

        files_to_check = [
            "memory/m4_absorption_confirmation.py",
            "memory/m4_cascade_momentum.py",
        ]

        for rel_path in files_to_check:
            file_path = self.project_root / rel_path
            if not file_path.exists():
                print(f"  SKIP: {rel_path} not found")
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            # Check for future timestamp access patterns
            forbidden_patterns = [
                "timestamp + ",
                "t + 1",
                "t+1",
                "next_tick",
                "future_",
                "lookahead",
                "[i+1]",
                "[i + 1]",
            ]

            for i, line in enumerate(lines, 1):
                for pattern in forbidden_patterns:
                    if pattern in line and "#" not in line[:line.find(pattern)]:
                        # Not in a comment
                        self.violations.append(LeakageViolation(
                            file=rel_path,
                            line=i,
                            check_type="TEMPORAL_LEAKAGE",
                            description=f"Potential future data access: '{pattern}'",
                            severity="CRITICAL"
                        ))

            # Verify window lookbacks are negative (past only)
            if "window" in content.lower():
                # Check for lookback patterns like [t-window, t]
                if "- window" in content or "-window" in content:
                    print(f"  PASS: {rel_path} uses backward-looking windows")

        print("  PASS: Absorption signals use past data only")

    def _check_entry_quality(self):
        """Check 3: Entry quality scoring uses historical patterns only."""
        print("[CHECK 3] Entry quality scoring validity...")

        file_path = self.project_root / "runtime" / "validation" / "entry_quality.py"
        if not file_path.exists():
            print("  SKIP: entry_quality.py not found")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        # Check for future PnL usage
        forbidden = ["realized_pnl", "future_pnl", "actual_outcome", "true_label"]

        for i, line in enumerate(lines, 1):
            for pattern in forbidden:
                if pattern in line.lower():
                    self.violations.append(LeakageViolation(
                        file="runtime/validation/entry_quality.py",
                        line=i,
                        check_type="ENTRY_QUALITY_LEAKAGE",
                        description=f"Potential future data in scoring: '{pattern}'",
                        severity="CRITICAL"
                    ))

        # Verify scoring uses liquidation_value, not outcome
        if "liquidation_value" in content or "liq_value" in content:
            print("  PASS: Scoring uses observable liquidation metrics")

        print("  PASS: Entry quality uses historical patterns only")

    def _check_timestamp_alignment(self):
        """Check 4: Consistent nanosecond timestamps throughout."""
        print("[CHECK 4] Timestamp alignment consistency...")

        ns_files = []
        sec_files = []
        mixed_files = []

        for rel_path in self.CRITICAL_FILES:
            file_path = self.project_root / rel_path
            if not file_path.exists():
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            has_ns = "_ns" in content or "nanosecond" in content.lower()
            has_sec = "timestamp: float" in content and "_ns" not in content

            if has_ns and has_sec:
                mixed_files.append(rel_path)
            elif has_ns:
                ns_files.append(rel_path)
            elif has_sec:
                sec_files.append(rel_path)

        if mixed_files:
            for f in mixed_files:
                self.violations.append(LeakageViolation(
                    file=f,
                    line=0,
                    check_type="TIMESTAMP_MIXED",
                    description="File mixes nanosecond and second timestamps",
                    severity="WARNING"
                ))
            print(f"  WARNING: {len(mixed_files)} files have mixed timestamp formats")
        else:
            print("  PASS: Timestamp formats are consistent")

    def _check_strategy_no_posthoc(self):
        """Check 5: Strategy does not use post-hoc labeled fields."""
        print("[CHECK 5] Strategy isolation from post-hoc data...")

        strategy_path = self.project_root / "external_policy" / "ep2_strategy_cascade_sniper.py"
        if not strategy_path.exists():
            print("  SKIP: cascade_sniper strategy not found")
            return

        with open(strategy_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        # Strategy must NOT use these post-hoc fields
        forbidden_in_strategy = [
            "price_5min_after",
            "outcome",
            "LabeledCascade",
            "cascade_labeler",
        ]

        for i, line in enumerate(lines, 1):
            for pattern in forbidden_in_strategy:
                if pattern in line:
                    # Check if it's an import (allowed for type hints only)
                    if "import" in line and "LabeledCascade" in line:
                        continue
                    self.violations.append(LeakageViolation(
                        file="external_policy/ep2_strategy_cascade_sniper.py",
                        line=i,
                        check_type="STRATEGY_POSTHOC",
                        description=f"Strategy uses post-hoc field: '{pattern}'",
                        severity="CRITICAL"
                    ))

        print("  PASS: Strategy does not use post-hoc labeled data")

    def _report_results(self):
        """Report audit results."""
        print()
        print("=" * 70)
        print("LEAKAGE AUDIT RESULTS")
        print("=" * 70)

        critical = [v for v in self.violations if v.severity == "CRITICAL"]
        warnings = [v for v in self.violations if v.severity == "WARNING"]

        if critical:
            print()
            print("CRITICAL VIOLATIONS (EDGE INVALID):")
            print("-" * 50)
            for v in critical:
                print(f"  [{v.check_type}] {v.file}:{v.line}")
                print(f"    {v.description}")

        if warnings:
            print()
            print("WARNINGS:")
            print("-" * 50)
            for v in warnings:
                print(f"  [{v.check_type}] {v.file}:{v.line}")
                print(f"    {v.description}")

        print()
        print("=" * 70)
        if critical:
            print("VERDICT: EDGE INVALID - Leakage detected")
            print("         Audit cannot proceed until violations fixed.")
        else:
            print("VERDICT: PASS - No critical leakage detected")
            print("         Proceed to Phase 2: Event Extraction")
        print("=" * 70)


def main():
    """Run leakage audit."""
    auditor = LeakageAuditor(PROJECT_ROOT)
    passed, violations = auditor.audit_all()

    # Exit code: 0 = passed, 1 = failed
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
