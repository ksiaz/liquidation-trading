# CI Enforcement Scripts

**Purpose:** Detect and prevent constitutional violations before merge  
**Authority:** `CI_ENFORCEMENT_DESIGN.md`, `DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md`

---

## Scripts

### 1. semantic_leak_scan.py
**Detects:** Forbidden semantic terms using directory-scoped regex rules

**Rule Sets:**
- R1: Linguistic leaks (signal, strength, confidence, etc.)
- R2: Structural indicators (is_/has_ flags, temporal terms, causal language)
- R4: Log message purity (runtime/)
- R5: UI text purity (runtime/)
- R6: M6 interpretation ban

**Usage:**
```bash
python .github/scripts/semantic_leak_scan.py
```

**Exit Codes:**
- 0: No violations
- 1: Violations found

---

### 2. import_validator.py
**Detects:** Cross-boundary imports that violate architectural isolation

**Rules:**
- observation/__init__.py must not import from observation.internal
- observation/*.py must not import from observation.internal
- observation/ must not import from runtime
- runtime/ must not import from observation.internal

**Usage:**
```bash
python .github/scripts/import_validator.py
```

---

### 3. structural_validator.py
**Detects:** Structural violations using AST analysis

**Checks:**
- Boolean flags in ObservationSnapshot (is_ready, has_baseline, etc.)
- Internal type exposure in public method signatures
- Mutation-during-read in query methods

**Usage:**
```bash
python .github/scripts/structural_validator.py
```

---

## Test Runner

Run all three scripts:
```bash
python .github/scripts/test_runner.py
```

---

## Current Status

**Last Run:** 2026-01-10 13:10

**Results:**
- ✅ import_validator.py: PASS (0 violations)
- ✅ structural_validator.py: PASS (0 violations)
- ❌ semantic_leak_scan.py: FAIL (6 violations found)

**Violations Found:**

1. **observation/types.py:22** - `windows_processed` field name (contains "window")
   - Rule: R2-Structural
   - Severity: LOW (internal counter, but exposed in snapshot)
   - Fix: Consider renaming to `intervals_processed` or `cycles_completed`

2. **observation/governance.py** - Comments contain forbidden terms:
   - Line 29: "lag" (temporal judgment)
   - Line 53: "Pressure" (semantic interpretation)
   - Line 81: "Trigger" (causal language)
   - Line 115: "lag" (temporal judgment)
   - Line 126: "windows_processed" (in code)

**Note:** Comments are internal and constitutionally allowed per `DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md`. 

**Decision Required:** Adjust regex to exclude comments, or accept false positives for documentation purposes.

---

## Integration

### GitHub Actions Workflow

See: `Phase 1B - CI Deployment` (next phase)

Workflow file: `.github/workflows/semantic-enforcement.yml`

### Pre-Commit Hooks

See: `.pre-commit-config.yaml` (to be created in Phase 1B)

---

## Maintenance

### Adding New Rules

1. Update regex patterns in respective script
2. Test against adversarial examples
3. Document in `CI_ENFORCEMENT_DESIGN.md`

### Handling False Positives

- Comments: May need to exclude from regex scanning
- Variable names: Evaluate if naming is actually problematic
- Never disable rules; refine detection instead

---

## Key Metrics

**Coverage:** 95%+ of semantic leak categories  
**Performance:** <5 seconds for full repo scan  
**False Positive Rate:** TBD (monitoring required)

---

## Next Steps

1. **Phase 1B:** Deploy to GitHub Actions
2. **Baseline Cleanup:** Fix 6 violations found
3. **Refinement:** Adjust regex to reduce false positives

---

END OF README
