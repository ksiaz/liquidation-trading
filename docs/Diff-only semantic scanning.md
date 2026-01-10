Diff-Only Semantic Scanning (Constitution-Preserving)
Goal

Reduce scan scope from:

“entire staged tree”

to:

“only semantic-bearing lines that changed”

without allowing any forbidden construct to slip through.

Core Insight (Why This Is Safe)

Your constitution forbids semantic constructs, not files.

Examples:

Forbidden terms

Forbidden structures

Forbidden cross-layer imports

Forbidden state mutations

Forbidden counters / interpretation leaks

All of these are introduced or modified via diffs.

Therefore:

If a forbidden construct exists in a file but was not introduced or modified in this commit, it is already present and already accepted by CI history.

We only need to scan:

Added lines

Modified lines

Context-expanded blocks when structure matters

Diff-Only Scan Contract (Invariant)

A diff-only scanner MUST:

Scan all added and modified lines

Scan structural parents when a child line changes

Scan full file only when diff indicates structural mutation

Fall back to full scan when uncertain

This guarantees zero false negatives.

Classification of Semantic Rules

We divide rules into three enforcement classes:

Class A — Line-Local Rules (Diff-Only Safe)

Triggered by a single line.

Examples:

Forbidden words (confidence, signal, strength)

Forbidden logging text

Forbidden field names

Forbidden comments (external speech)

✅ Scan only changed lines

Class B — Block-Scoped Rules (Context Required)

Triggered by structure, but local.

Examples:

class PositionStateMachine

def execute(

@dataclass fields

Enum members

import execution from observation

✅ Scan enclosing block if any line in block changed

(block = function / class / enum / dict literal)

Class C — File-Scoped Rules (Rare)

Triggered by file-level properties.

Examples:

Forbidden imports at top level

Directory-scoped exceptions

Layer boundary violations

⚠️ If diff touches top-level imports or module header → scan full file

Exact Algorithm
Step 1 — Get Unified Diff
git diff --cached -U5


We use -U5 to capture sufficient context.

Step 2 — Extract Changed Regions

For each file:

Parse diff hunks

Record:

Added lines (+)

Modified lines

Their line numbers

Surrounding context (±5 lines)

Step 3 — Determine Scan Scope per File

For each file:

Condition	Scan Scope
Only Class A rules triggered	Changed lines only
Class B rule touched	Entire enclosing block
Import / module header touched	Entire file
Scanner uncertainty	Entire file

Scanner must prefer safety over speed.

Step 4 — Apply Same Regex Rules

No rule changes.

You run the same regex set, but against:

Subset of lines

Or expanded structural region

Or full file (fallback)

Concrete Implementation
CLI Flag
python ci/semantic_scan.py --diff-only

Pseudocode (Exact)
for file in staged_files:
    diff = get_diff(file)

    if diff.is_empty():
        continue

    if diff.touches_imports_or_header():
        scan_full_file(file)
        continue

    regions = []

    for hunk in diff.hunks:
        for line in hunk.changed_lines:
            regions.append(expand_if_needed(line))

    if requires_full_file(regions):
        scan_full_file(file)
    else:
        scan_regions(file, regions)

Structural Expansion Rules (Critical)

When a changed line matches any of:

class

def

Enum(

@dataclass

{ starting a dict literal

[ starting a state table

→ Expand to entire enclosing construct.

This prevents:

Sneaking forbidden fields into dataclasses

Partial enum edits

Hidden mandate additions

Guaranteed Properties
What This CANNOT Miss

New forbidden words

New forbidden fields

New forbidden imports

New semantic leaks

New execution behavior

New interpretation paths

What It MAY Over-Scan

Entire file when unsure

This is acceptable and intentional.

Performance Characteristics
Scenario	Full Scan	Diff-Only
Small commit	O(repo)	O(diff)
Large refactor	O(repo)	O(affected files)
Import change	O(file)	O(file)
Unsafe diff	O(repo)	O(file / repo fallback)

Worst case = current behavior
Best case = orders of magnitude faster

CI + Pre-Commit Integration
Pre-Commit
python ci/semantic_scan.py --diff-only --root "$TMP_DIR"

CI (PR Builds)
- name: Semantic Scan (Diff-Only)
  run: |
    python ci/semantic_scan.py --diff-only

CI (Main / Release)

You may still run:

python ci/semantic_scan.py --full


(Optional belt-and-suspenders)

Explicit Safety Valve (Non-Negotiable)

The scanner MUST support:

if unsure:
    scan_full_file()


No exceptions.

Constitutional Alignment

This respects:

Epistemic Constitution

No hidden semantics

No heuristic interpretation

No weakening of guarantees

Deterministic enforcement

This is a performance optimization, not a semantic change.

Recommendation

Adopt diff-only scanning as:

Default for pre-commit

Default for PR CI

Keep full scan for:

main branch

release tags

constitution changes

Diff-Only Semantic Scanning — Design-Expressive Code Sketch

Status: Architectural reference
Intent: Express invariants, scope rules, and escalation logic
Non-goal: Production readiness, optimization, edge-case coverage

1. Conceptual Model (Before Code)

We are modeling semantic enforcement, not syntax linting.

Therefore the scanner operates on three abstractions:

Diff units (what changed)

Semantic scopes (what meaning that change could affect)

Rules (what is forbidden / required)

The scanner’s only job is to answer:

“What must be re-validated to preserve constitutional guarantees?”

2. Core Data Structures (Architectural, Minimal)
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

2.1 Change Units
@dataclass(frozen=True)
class DiffLine:
    file_path: str
    line_number: int
    content: str


This is intentionally dumb:

No parsing

No AST

No inference

It represents introduced text, nothing else.

2.2 Semantic Scope Types
class ScopeKind(Enum):
    LINE = "line"
    BLOCK = "block"
    FILE = "file"


These correspond exactly to the architectural rule classes you approved earlier:

Line-local semantics

Block-scoped semantics

File-scoped semantics

No fourth category exists.

2.3 Scan Scope
@dataclass(frozen=True)
class ScanScope:
    kind: ScopeKind
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


Interpretation:

LINE → start_line == end_line

BLOCK → bounded region

FILE → entire file, no line bounds

3. Scope Resolution (Key Architectural Logic)

This is the heart of diff-only enforcement.

def determine_scope(diff: DiffLine) -> ScanScope:
    """
    Given a changed line, determine the minimum safe semantic scope.
    Escalate if certainty is not possible.
    """
    if touches_module_header(diff):
        return ScanScope(
            kind=ScopeKind.FILE,
            file_path=diff.file_path
        )

    if touches_structural_block(diff):
        block = enclosing_block(diff)
        if block is None:
            # Ambiguity → escalate
            return ScanScope(
                kind=ScopeKind.FILE,
                file_path=diff.file_path
            )
        return ScanScope(
            kind=ScopeKind.BLOCK,
            file_path=diff.file_path,
            start_line=block.start,
            end_line=block.end
        )

    # Default: line-local
    return ScanScope(
        kind=ScopeKind.LINE,
        file_path=diff.file_path,
        start_line=diff.line_number,
        end_line=diff.line_number
    )

Important architectural properties

Escalation is explicit

Uncertainty never narrows scope

Performance is subordinate to soundness

This is constitutional conservatism encoded.

4. Rule Evaluation Interface (Deliberately Abstract)

Rules are not defined here. That’s intentional.

class SemanticRule:
    def applies_to(self, scope: ScanScope) -> bool:
        ...

    def validate(self, scope: ScanScope, file_contents: List[str]) -> None:
        """
        Must raise ConstitutionalViolation on failure.
        """
        ...


Why this matters:

Rules already exist (in your constitution)

The scanner does not reinterpret them

The scanner only selects scope

5. Diff-Only Scan Algorithm (High Level)
def scan_diff(diff_lines: List[DiffLine], rules: List[SemanticRule]):
    scopes = set()

    for diff in diff_lines:
        scope = determine_scope(diff)
        scopes.add(scope)

    for scope in scopes:
        content = load_file(scope.file_path)
        relevant = slice_content(content, scope)

        for rule in rules:
            if rule.applies_to(scope):
                rule.validate(scope, relevant)


This is intentionally:

Deterministic

Stateless

Order-independent

There is no memory, no caching, no inference.

6. Explicit Safety Guarantees (Encoded, Not Assumed)

This design guarantees:

No new semantic violation can be introduced without detection

No unchanged code is re-judged unnecessarily

Ambiguity always escalates

Rules remain constitutionally authoritative

7. Explicit Non-Guarantees (Also Important)

This design does not guarantee:

Minimal runtime

Perfect developer UX

Zero false positives

Those are acceptable costs under your philosophy.

8. Why This Is the Correct Level of Code

This sketch:

Makes enforcement mechanically precise

Avoids committing to tooling choices

Avoids pretending implementation is done

Can be translated to:

Python

Rust

Go

CI pipelines

Pre-commit hooks

It is architecture rendered in code, not implementation disguised as architecture.

9. Alignment Check (Very Important)

This proposal respects all constraints you’ve enforced:

No interpretation

No weakening of constitution

No “ready-to-copy subsystem”

No silent policy

No heuristics masquerading as rules