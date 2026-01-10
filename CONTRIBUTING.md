# Contributing to Epistemically-Constrained Execution System

## Before You Start

This project enforces **constitutional constraints** via automated CI checks. All code must comply with:

1. **Epistemic Constitution** - Observation layer exposes facts only
2. **Semantic Leak Prevention** - No interpretation crosses boundaries
3. **Architectural Isolation** - No cross-boundary imports

**Violations block merges.** There are no exceptions.

---

## Setup (Required)

### Install Pre-Commit Hooks

```bash
pip install pre-commit
pre-commit install
```

**This runs constitutional checks before every commit.**

---

## What Gets Checked

### 1. Semantic Leak Scanner
**Catches:** Forbidden terms like `signal`, `strength`, `confidence`, `healthy`, `ready`

**Example violation:**
```python
# ❌ FORBIDDEN
signal_strength: float

# ✅ ALLOWED
threshold_exceedance_count: int
```

### 2. Import Validator
**Catches:** Cross-boundary imports

**Example violation:**
```python
# ❌ FORBIDDEN (in observation/types.py)
from observation.internal.m3_temporal import BaselineCalculator

# ✅ ALLOWED (in observation/internal/m3_temporal.py)
from observation.types import ObservationSnapshot
```

### 3. Structural Validator
**Catches:** Boolean flags like `is_ready`, `has_baseline`

**Example violation:**
```python
# ❌ FORBIDDEN (in ObservationSnapshot)
is_ready: bool

# ✅ ALLOWED
status: ObservationStatus  # UNINITIALIZED or FAILED only
```

---

## If CI Fails

### Read the Error Message
CI output shows:
- File and line number
- Rule violated
- Suggested fix

### Fix the Violation
**Never bypass CI.** Fix the code to comply.

### Need Help?
See:
- `docs/SEMANTIC_LEAK_EXHAUSTIVE_AUDIT.md` - All 9 leak categories
- `docs/ADVERSARIAL_CODE_EXAMPLES.md` - 12 violation patterns
- `docs/DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md` - What's allowed where

---

## Pull Request Checklist

Before submitting:
- [ ] Pre-commit hooks installed and passing
- [ ] All CI checks green
- [ ] No constitutional violations
- [ ] Code matches formal specifications

**PRs with violations cannot merge** (branch protection enforced).

---

## Philosophy

This project prioritizes **provable correctness** over convenience.

**If you're fighting the CI, you're probably violating the architecture.**

Read: `PRDbyTheArchitect.md` and `EPISTEMIC_CONSTITUTION.md` to understand why.

---

## Questions?

1. Check `ARCHITECTURE_INDEX.md` for document navigation
2. Review constitutional documents (see Quick Start in index)
3. Ask in PR comments with `@architect` tag

---

END OF CONTRIBUTING GUIDE
