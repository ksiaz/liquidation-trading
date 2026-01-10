# CI SEMANTIC LEAK ENFORCEMENT DESIGN

**Status:** Authoritative Design Specification  
**Purpose:** Comprehensive CI architecture for detecting and preventing semantic leaks  
**Authority:** Semantic Leak Audit, Directory Framework, Adversarial Examples

---

## 1. SYSTEM ARCHITECTURE

### 1.1 Enforcement Goals

**Primary Objective:** Prevent semantic leaks from crossing constitutional boundaries

**Secondary Objectives:**
- Enable fast feedback (diff-only scanning where possible)
- Provide actionable error messages
- Support pre-commit mirroring
- Maintain zero false negatives (catchable violations must be caught)

**Non-Goals:**
- Perfect precision (false positives acceptable if rare)
- Natural language understanding
- AI-based detection

---

## 2. DETECTION STRATEGY

### 2.1 Three-Layer Enforcement

**Layer 1: Regex-Based Pattern Matching**
- Fast, deterministic
- Directory-scoped rules
- Catches linguistic and structural leaks
- Primary enforcement mechanism

**Layer 2: Import Path Analysis**
- AST-based module import validation
- Detects cross-boundary imports
- Identifies type exposure violations

**Layer 3: Structural Analysis**
- Type signature checking
- Boolean flag detection in public types
- Mutation-during-read detection

---

## 3. REGEX TAXONOMY (DIRECTORY-SCOPED)

### 3.1 observation/ (Root) - ZERO TOLERANCE

**Target Files:** `types.py`, `governance.py`, `__init__.py`

**Rule Set R1: Linguistic Leaks**
```regex
# Forbidden interpretive terms in field names, class names, method names
(signal|strength|confidence|quality|health|ready|valid|good|bad|stale|fresh|
live|active|flowing|pressure|baseline|opportunity|bias|setup|weak|strong|
support|resistance|validated|confirmed|normal|abnormal|significant|
momentum|reversal|bullish|bearish)
```

**Application:** Match against:
- Class attribute names
- Dataclass field names  
- Method names (public only)
- Type names

**Rule Set R2: Structural Indicators**
```regex
# Boolean flags implying interpretation
^(is|has|can|should|must|may)_\w+

# Temporal judgments
(recent|lag|delay|outdated|fresh|stale|window|rolling|cooldown|debounce)

# Causal language
(triggered|caused|due_to|because|led_to|response_to|result_of)

# Threshold language (in field names)
(threshold|limit|max|min|safe|danger|warning|critical)_
```

**Exclusions:**
- `is` in `isinstance()` - Language keyword
- `has` in method implementations (internal)

---

### 3.2 observation/internal/ - CONTAINED

**Target Files:** `m1_ingestion.py`, `m3_temporal.py`, `m4_*.py`

**Rule Set R3: Export Detection**
```regex
# Forbidden: Exporting internal classes via __init__.py
# Check observation/__init__.py for imports from observation.internal

from\s+\.internal\.\w+\s+import
```

**Application:** Match in `observation/__init__.py` only

**Permitted in internal/:**
- All semantic naming (baseline, pressure, warmth, etc.)
- All statistical computation
- All heuristics and thresholds

---

### 3.3 runtime/ - ZERO TOLERANCE (External I/O)

**Target Files:** `collector/service.py`, `native_app/main.py`

**Rule Set R4: Log Message Purity**
```regex
# Activity assertions in logs
logger\.(info|warning|error|debug)\([^)]*
(start|starting|connect|connecting|process|processing|analyz|detect|
live|flowing|active|healthy|ready|working|successful|failed|error|
problem|issue|warning|good|bad)
```

**Rule Set R5: UI Text Purity**
```regex
# Interpretive UI text
setText\([^)]*
(pressure|signal|strength|confidence|health|ready|warm|valid|good|bad|
detecting|analyzing|processing|active|live|flowing|setup|opportunity)

setWindowTitle\([^)]*
(detector|analyzer|predictor|signal|pressure|peak|opportunity)
```

**Application:** Match against string contents in UI/log calls

---

### 3.4 runtime/m6_executor.py - ZERO TOLERANCE

**Target File:** `m6_executor.py`

**Rule Set R6: M6 Interpretation Ban**
```regex
# Any interpretation logic forbidden
if\s+\w+\.(counters|promoted_events|symbols_active)

# Any logging forbidden
(logger|print|log)\(

# Any state persistence forbidden
^class\s+\w+:
self\.\w+\s*=

# Any loops forbidden
while\s+|for\s+\w+\s+in

# Any retry/fallback patterns
try:.*except.*continue|pass|return\s+default
```

**Application:** Comprehensive ban on interpretation, state, logging, loops

---

### 3.5 execution/ - ZERO TOLERANCE

**Target Files:** Position state machine, arbitration, mandate handling

**Rule Set R7: Semantic Leak in Execution**
```regex
# Interpretation of observation data forbidden
observation.*\.counters\.(signal|strength|confidence|quality)

# Retry/recovery patterns forbidden
retry|fallback|downgrade|recovery|graceful_degradation

# Confidence/quality judgments forbidden
if.*confidence|if.*quality|if.*valid
```

---

## 4. IMPORT PATH ANALYSIS

### 4.1 Forbidden Import Patterns

**Check 1: Internal Exposure**
```python
# FORBIDDEN in observation/__init__.py
from .internal.m3_temporal import BaselineCalculator
from .internal.m1_ingestion import M1IngestionEngine
```

**Detection:** Parse `observation/__init__.py`, check all imports

**Check 2: Cross-Boundary Imports**
```python
# FORBIDDEN in observation/
from runtime.m6_executor import execute

# FORBIDDEN in runtime/
from observation.internal.m3_temporal import anything
```

**Detection:** Parse imports in each directory, verify boundaries

**Check 3: Circular Dependencies**
```python
# FORBIDDEN
observation → runtime (via import)
```

**Detection:** Build import graph, detect cycles

---

## 5. STRUCTURAL ANALYSIS

### 5.1 Type Signature Validation

**Check: Public Methods Must Use Public Types**

```python
# FORBIDDEN in observation/governance.py
def get_baseline(self) -> BaselineStatus:  # Internal type exposed
    ...

# OK
def query(self, query_spec: Dict) -> ObservationSnapshot:  # Public type
    ...
```

**Detection:**
1. Parse public method signatures in `governance.py`
2. Extract return types
3. Check if return type is from `observation.internal.*`
4. Fail if internal type used

---

### 5.2 Boolean Flag Detection

**Check: No Interpretive Booleans in Public Types**

```python
# FORBIDDEN in ObservationSnapshot
is_ready: bool
has_baseline: bool
can_trade: bool
```

**Detection:**
1. Parse `ObservationSnapshot` dataclass
2. Extract all field types
3. Flag any `bool` field matching `^(is|has|can|should)_`

---

### 5.3 Mutation-During-Read Detection

**Check: Query Methods Must Be Pure**

```python
# FORBIDDEN in query() or _get_snapshot()
self._last_query_time = time.time()
self._query_count += 1
```

**Detection:**
1. Parse `query()` and `_get_snapshot()` methods
2. Scan for assignments to `self._*`
3. Flag any mutations

---

## 6. CI PIPELINE DESIGN

### 6.1 GitHub Actions Workflow

**Trigger:** On pull request, push to main

**Jobs:**

```yaml
name: Semantic Leak Enforcement

on: [pull_request, push]

jobs:
  semantic-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Full history for diff
      
      - name: Semantic Leak Scan
        run: python .github/scripts/semantic_leak_scan.py
        
      - name: Import Path Validation
        run: python .github/scripts/import_validator.py
        
      - name: Structural Analysis
        run: python .github/scripts/structural_validator.py
```

---

### 6.2 Diff-Only Scanning (Performance)

**Strategy:** Scan only changed files/lines in PRs

**Implementation:**
```bash
# Get changed files
git diff --name-only origin/main...HEAD

# For each changed file matching pattern
# Run directory-specific regex rules
```

**Fallback:** Full scan on main branch merges

---

### 6.3 Required Status Checks

**GitHub Branch Protection Rules:**

Must pass before merge:
- ✅ `ci/semantic-leak-scan`
- ✅ `ci/import-validation`
- ✅ `ci/structural-analysis`

**Bypass:** None (no admin override for constitutional violations)

---

## 7. IMPLEMENTATION SCRIPTS

### 7.1 Semantic Leak Scanner

**File:** `.github/scripts/semantic_leak_scan.py`

**Functionality:**
- Load directory-specific regex rules
- Scan target files
- Report violations with line numbers
- Exit code 1 if violations found

**Pseudo-code:**
```python
import re
import sys
from pathlib import Path

RULES = {
    'observation/types.py': [R1, R2],
    'observation/governance.py': [R1, R2],
    'runtime/collector/service.py': [R4],
    'runtime/native_app/main.py': [R4, R5],
    'runtime/m6_executor.py': [R6],
}

def scan_file(filepath, rules):
    violations = []
    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            for rule_name, pattern in rules:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append((line_num, rule_name, line.strip()))
    return violations

def main():
    all_violations = {}
    for filepath, rules in RULES.items():
        if Path(filepath).exists():
            violations = scan_file(filepath, rules)
            if violations:
                all_violations[filepath] = violations
    
    if all_violations:
        print("SEMANTIC LEAK VIOLATIONS DETECTED:")
        for filepath, violations in all_violations.items():
            print(f"\n{filepath}:")
            for line_num, rule, line in violations:
                print(f"  Line {line_num}: {rule}")
                print(f"    {line}")
        sys.exit(1)
    
    print("✓ No semantic leaks detected")
    sys.exit(0)
```

---

### 7.2 Import Validator

**File:** `.github/scripts/import_validator.py`

**Functionality:**
- Parse Python AST
- Extract import statements
- Validate against boundary rules
- Report forbidden imports

**Pseudo-code:**
```python
import ast
import sys
from pathlib import Path

FORBIDDEN_IMPORTS = {
    'observation/__init__.py': [
        'observation.internal.*'
    ],
    'observation/*.py': [
        'runtime.m6_executor'
    ],
    'runtime/*.py': [
        'observation.internal.*'
    ]
}

def get_imports(filepath):
    with open(filepath) as f:
        tree = ast.parse(f.read())
    
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(n.name for n in node.names)
    
    return imports

def matches_pattern(import_str, pattern):
    if pattern.endswith('.*'):
        prefix = pattern[:-2]
        return import_str.startswith(prefix)
    return import_str == pattern

def main():
    violations = []
    
    for pattern, forbidden_list in FORBIDDEN_IMPORTS.items():
        files = Path('.').glob(pattern)
        for filepath in files:
            imports = get_imports(filepath)
            for imp in imports:
                for forbidden in forbidden_list:
                    if matches_pattern(imp, forbidden):
                        violations.append((filepath, imp, forbidden))
    
    if violations:
        print("FORBIDDEN IMPORT VIOLATIONS:")
        for filepath, imp, rule in violations:
            print(f"  {filepath}: imports {imp} (forbidden: {rule})")
        sys.exit(1)
    
    print("✓ No import violations detected")
    sys.exit(0)
```

---

### 7.3 Structural Validator

**File:** `.github/scripts/structural_validator.py`

**Functionality:**
- Parse dataclass definitions
- Validate field names/types
- Check method signatures
- Detect mutations in read methods

**Pseudo-code:**
```python
import ast
import sys

def check_observation_snapshot():
    with open('observation/types.py') as f:
        tree = ast.parse(f.read())
    
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'ObservationSnapshot':
            for field in node.body:
                if isinstance(field, ast.AnnAssign):
                    field_name = field.target.id
                    # Check boolean flags
                    if field_name.startswith(('is_', 'has_', 'can_')):
                        violations.append(f"Boolean flag: {field_name}")
    
    return violations

def main():
    violations = check_observation_snapshot()
    # ... other structural checks ...
    
    if violations:
        print("STRUCTURAL VIOLATIONS:")
        for v in violations:
            print(f"  {v}")
        sys.exit(1)
    
    print("✓ No structural violations detected")
    sys.exit(0)
```

---

## 8. PRE-COMMIT INTEGRATION

### 8.1 Pre-Commit Hook Configuration

**File:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: semantic-leak-scan
        name: Semantic Leak Scanner
        entry: python .github/scripts/semantic_leak_scan.py
        language: python
        pass_filenames: false
        stages: [commit]
        
      - id: import-validator
        name: Import Path Validator
        entry: python .github/scripts/import_validator.py
        language: python
        pass_filenames: false
        stages: [commit]
```

**Installation:**
```bash
pip install pre-commit
pre-commit install
```

**Behavior:** Same checks as CI, runs locally before commit

---

## 9. ERROR MESSAGES & DEVELOPER GUIDANCE

### 9.1 Error Message Format

**Standard Format:**
```
SEMANTIC LEAK VIOLATION
File: observation/types.py
Line: 23
Rule: Linguistic Leak (R1)
Pattern: "signal_strength"
Violation: Field name contains forbidden interpretive term "signal"

Guidance:
- Remove interpretive naming from public types
- Use neutral terms: exceedance_count, threshold_breach_count
- See: docs/SEMANTIC_LEAK_EXHAUSTIVE_AUDIT.md

Constitutional Authority:
- EPISTEMIC_CONSTITUTION.md Article III
- DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md Section 3.1
```

**Key Elements:**
- Exact location (file, line)
- Rule violated
- Explanation
- Suggested fix
- Constitutional reference

---

### 9.2 Common Fixes Reference

**Quick Fix Guide in CI Output:**

```
Common Violations & Fixes:

1. Interpretive field names
   ❌ signal_strength: float
   ✅ threshold_exceedance_count: int

2. Boolean readiness flags
   ❌ is_ready: bool
   ✅ status: ObservationStatus

3. Log messages with interpretation
   ❌ logger.info("Processing events")  
   ✅ (remove log entirely)

4. UI text with semantic claims
   ❌ setText("System is healthy")
   ✅ setText(f"Status: {snapshot.status.name}")

See docs/ADVERSARIAL_CODE_EXAMPLES.md for more patterns
```

---

## 10. PERFORMANCE OPTIMIZATION

### 10.1 Diff-Only Strategy

**PR Scanning:**
```python
# Get changed files in PR
changed_files = subprocess.run(
    ['git', 'diff', '--name-only', 'origin/main...HEAD'],
    capture_output=True
).stdout.decode().splitlines()

# Scan only changed files
for filepath in changed_files:
    if filepath in RULES:
        scan_file(filepath, RULES[filepath])
```

**Full Scan Triggers:**
- Merge to main
- Changes to enforcement scripts
- Changes to constitutional documents
- Manual request

---

### 10.2 Caching Strategy

**Cache Regex Compilation:**
```python
import re
from functools import lru_cache

@lru_cache(maxsize=128)
def compile_pattern(pattern):
    return re.compile(pattern, re.IGNORECASE)
```

**Expected Performance:**
- PR scan (5-10 changed files): <5 seconds
- Full scan (entire repo): <30 seconds

---

## 11. MONITORING & METRICS

### 11.1 Tracked Metrics

**Per PR:**
- Number of files scanned
- Number of violations found
- Rules triggered (histogram)
- Scan duration

**Historical:**
- Violation trends
- Most common violation types
- False positive rate (when violations overridden)

---

### 11.2 Reporting Dashboard

**Weekly Report:**
- Total violations blocked
- Most violated rules
- Directories with most violations
- Compliance score (% clean PRs)

---

## 12. MAINTENANCE & UPDATES

### 12.1 Adding New Rules

**Process:**
1. Identify new leak pattern (via code review)
2. Add to adversarial examples
3. Define regex pattern
4. Add to appropriate rule set
5. Test against existing codebase
6. Deploy to CI

**Documentation:** Update this doc + ADVERSARIAL_CODE_EXAMPLES.md

---

### 12.2 Rule Refinement

**False Positive Handling:**
1. Document false positive
2. Refine regex to exclude
3. Add exclusion to rule set
4. Test regression

**Never:** Disable rule entirely without constitutional amendment

---

## 13. CONSTITUTIONAL COMPLIANCE PROOF

### 13.1 Coverage Map

| Leak Category | Detection Layer | Rule Set | Coverage |
|---------------|----------------|----------|----------|
| Linguistic | Regex (R1) | observation/, runtime/ | 100% |
| Structural | Regex (R2) + Structural | All boundaries | 100% |
| Aggregation | Structural Analysis | observation/governance.py | 90% |
| Temporal | Regex (R2, R4) | runtime/ logs | 100% |
| Causal | Regex (R2) | observation/types.py | 100% |
| Absence-as-Signal | Structural Analysis | m6_executor.py | Manual review |
| Threshold | Regex (R2, R7) | All boundaries | 95% |
| Statistical | Structural Analysis | Public method signatures | 90% |
| Cross-Layer | Import Analysis | All boundaries | 100% |

**Total Coverage:** >95% automated, remainder requires manual review

---

### 13.2 Adversarial Example Validation

**Test:** All 12 adversarial examples must be caught by CI

**Validation Script:**
```python
# Test that each adversarial example triggers appropriate rule
for example in ADVERSARIAL_EXAMPLES:
    result = run_semantic_scan(example.code)
    assert result.violations
        , f"Example{example.id} not caught!"
```

---

## 14. ROLLOUT PLAN

### 14.1 Phase 1: Design & Validation (Current)

- ✅ Define taxonomy
- ✅ Create adversarial examples
- ✅ Design CI architecture
- ⏭️ Implement scripts
- ⏭️ Test against current codebase

---

### 14.2 Phase 2: Implementation

1. Implement semantic_leak_scan.py
2. Implement import_validator.py
3. Implement structural_validator.py
4. Test on existing violations
5. Refine patterns

---

### 14.3 Phase 3: Deployment

1. Add GitHub Actions workflow
2. Enable as required check (non-blocking)
3. Monitor for false positives
4. Refine rules
5. Make blocking

---

### 14.4 Phase 4: Hardening

1. Add pre-commit hooks
2. Document enforcement
3. Train reviewers
4. Periodic audits

---

## 15. SUCCESS CRITERIA

**System is successful when:**

✅ All 12 adversarial examples trigger CI failure  
✅ Zero false negatives on known leak patterns  
✅ <5% false positive rate  
✅ <30 second full repo scan  
✅ <5 second diff-only scan  
✅ Pre-commit parity with CI  
✅ Clear error messages with constitutional references  
✅ >95% developer compliance (violations rare)  

---

END OF CI DESIGN SPECIFICATION
