# PR #5: Scanner Update - Directory-Scoped Rule-Class Detection

## Summary

Implements AD-001 resolution: Scanner now classifies semantic patterns by rule class (EVAL, STRUCTURAL_METRIC, etc.) and enforces directory-aware rules. Eliminates false positives in observation layer while maintaining strict enforcement elsewhere.

**Key Achievement:** Observation layer now passes with **0 violations** (previously 25 false positives).

---

## Changes

### 1. Scanner Complete Rewrite
**File:** `.github/scripts/semantic_leak_scan.py`

- Added `RuleClass` enum (7 classes: EVAL, INTENT, QUALITY, STRUCTURAL_METRIC, AGGREGATION, TEMPORAL_PARAMETER, DESCRIPTIVE_STATE)
- Split old `R2_STRUCTURAL` pattern into EVAL vs STRUCTURAL_METRIC
- Directory-scoped enforcement matrix
- Windows path separator fix (backslash → forward slash)
- Enhanced violation reporting with rule class + reasoning

**Before:** Pattern-only matching (no context)  
**After:** Rule-class + directory-aware enforcement

---

### 2. Directory Rules Matrix

| Directory | Allowed Rule Classes | Forbidden |
|-----------|----------------------|-----------|
| `observation/` | STRUCTURAL_METRIC, AGGREGATION, TEMPORAL_PARAMETER, DESCRIPTIVE_STATE | EVAL, INTENT, QUALITY |
| `memory/` | STRUCTURAL_METRIC, AGGREGATION, DESCRIPTIVE_STATE | EVAL, INTENT, QUALITY, TEMPORAL_PARAMETER |
| `runtime/` | STRUCTURAL_METRIC, AGGREGATION | EVAL, INTENT, QUALITY |
| `ui/` | NONE | ALL |

---

### 3. Remove Temporary Exception
**File:** `.github/workflows/semantic-enforcement.yml`

Removed PR #4-specific conditional logic (lines 28-40):

```diff
- if [ "${{ github.event.pull_request.number }}" == "4" ]; then
-   python .github/scripts/semantic_leak_scan.py --exclude-paths observation/
- else
-   python .github/scripts/semantic_leak_scan.py
- fi
+ python .github/scripts/semantic_leak_scan.py
```

---

### 4. Mark AD-001 as Resolved
**File:** `docs/ARCHITECTURAL_DECISIONS.md`

Added resolution note with PR reference.

---

## Testing

### Local Testing

```bash
python .github/scripts/semantic_leak_scan.py
# Output: [OK] No semantic leaks detected
```

**observation/governance.py:** 0 violations (was 25)

### Pattern Classification Validation

All 25 previous violations correctly classified as **ALLOWED**:

| Pattern | Rule Class | Verdict |
|---------|------------|---------|
| `max_penetration = 0.0` | STRUCTURAL_METRIC | ✅ ALLOWED |
| `if len(recent_prices) >= 2:` | AGGREGATION | ✅ ALLOWED |
| `stale_threshold = 60.0` | TEMPORAL_PARAMETER | ✅ ALLOWED |
| `sum(...)` | AGGREGATION | ✅ ALLOWED |

### Cross-Directory Validation

- observation/: STRUCTURAL_METRIC **allowed**
- ui/: STRUCTURAL_METRIC **forbidden** (ui allows nothing)
- runtime/: EVAL **forbidden** (universal)

---

## Migration & Rollout

**No breaking changes.** Scanner CLI remains compatible:
- `--exclude-paths` flag deprecated (still accepted, prints warning)
- All existing workflows continue to function

---

## Success Criteria

- ✅ Scanner classifies patterns by rule class
- ✅ Directory rules enforced correctly  
- ✅ Observation layer passes without exclusions (0 violations)
- ✅ False positive rate: **0%** (target: <5%)
- ✅ Real leaks still caught (EVAL, INTENT, QUALITY)
- ✅ Temporary exception removed from CI
- ✅ Windows path compatibility (backslash normalization)

---

## Authority

- **Architect Ruling:** AD-001 (2026-01-10)
- **Canonical Spec:** `docs/DIRECTORY_SCOPED_SEMANTIC_RULES.md`
- **Closes:** `NEXT_REQUIRED_SCANNER_UPDATE.md`

---

## Files Modified

**Scanner:**
- `.github/scripts/semantic_leak_scan.py` - Complete rewrite (320 lines)

**CI Workflow:**
- `.github/workflows/semantic-enforcement.yml` - Remove temporary exception

**Documentation:**
- `docs/ARCHITECTURAL_DECISIONS.md` - Mark AD-001 as resolved

**Stats:**
- ~320 lines scanner (new implementation)
- 13 lines removed from workflow (clean)
- 0 breaking changes

---

## PR Checklist

- ✅ Scanner passes locally on observation layer (0 violations)
- ✅ Rule classification correct (tested all 7 classes)
- ✅ Directory-aware enforcement verified
- ✅ Temporary exception completely removed
- ✅ AD-001 marked as resolved
- ✅ No breaking changes to CLI interface

**Ready to merge.**
