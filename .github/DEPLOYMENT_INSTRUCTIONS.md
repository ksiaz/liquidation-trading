# CI Deployment Instructions

## Files Ready for Deployment

### Core CI Files
- `.github/scripts/semantic_leak_scan.py`
- `.github/scripts/import_validator.py`
- `.github/scripts/structural_validator.py`
- `.github/scripts/test_runner.py`
- `.github/scripts/README.md`

### Deployment Configuration
- `.github/workflows/semantic-enforcement.yml`
- `.github/CI_CONFIGURATION_GUIDE.md`
- `.pre-commit-config.yaml`
- `CONTRIBUTING.md`
- `ARCHITECTURE_INDEX.md`

### Documentation
- `docs/ADVERSARIAL_CODE_EXAMPLES.md`
- `docs/CI_ENFORCEMENT_DESIGN.md`
- `docs/DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md`
- `docs/INVARIANT_IMPOSSIBILITY_PROOFS.md`
- `docs/MANDATE_ARBITRATION_PROOFS.md`
- `docs/POSITION_STATE_MACHINE_PROOFS.md`
- `docs/RISK_EXPOSURE_MATHEMATICS.md`
- `semantic leak exhaustive  audit.md`

### Code Fixes
- `observation/types.py` (renamed: windows_processed → intervals_processed)
- `observation/governance.py` (renamed field usage)

---

## Deployment Steps

### Step 1: Stage Files (Manual)

```bash
# Core CI infrastructure
git add .github/

# Configuration
git add .pre-commit-config.yaml CONTRIBUTING.md ARCHITECTURE_INDEX.md

# Documentation (new constitutional docs)
git add docs/ADVERSARIAL_CODE_EXAMPLES.md
git add docs/CI_ENFORCEMENT_DESIGN.md
git add docs/DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md
git add docs/INVARIANT_IMPOSSIBILITY_PROOFS.md
git add docs/MANDATE_ARBITRATION_PROOFS.md
git add docs/POSITION_STATE_MACHINE_PROOFS.md
git add docs/RISK_EXPOSURE_MATHEMATICS.md
git add "semantic leak exhaustive  audit.md"

# Code fixes
git add observation/types.py observation/governance.py

# Other new docs
git add PRDbyTheArchitect.md
git add "PROJECT SPECIFICATION — CONSTITUTIONAL EXECUTION SYSTEM.md"
```

### Step 2: Commit

```bash
git commit -m "feat: CI enforcement infrastructure (Phase 1 complete)

Core Changes:
- Add semantic leak scanner with R1-R7 rules
- Add import validator (cross-boundary detection)
- Add structural validator (type exposure, boolean flags)
- GitHub Actions workflow for PR checks
- Pre-commit hooks for local enforcement

Documentation:
- Complete formal verification (42+ theorems)
- Risk & exposure mathematics
- Semantic leak taxonomy (9 categories)
- Architecture index

Code Fixes:
- Rename windows_processed → intervals_processed
- Comments excluded from semantic scanning

All CI checks passing locally.
See: .github/CI_CONFIGURATION_GUIDE.md for setup"
```

### Step 3: Push to GitHub

```bash
git push origin master  # or your branch name
```

---

## Post-Push: Enable Branch Protection

### Required GitHub Settings

1. **Go to Repository Settings**
   - Navigate to: Settings → Branches

2. **Add Branch Protection Rule**
   - Branch name pattern: `main` (or `master`)
   - Enable: ☑ **Require status checks to pass before merging**
   - Add required checks:
     - `Constitutional Compliance Checks`
     - `semantic-enforcement` (job name)

3. **Enforce Strictness**
   - Enable: ☑ **Require branches to be up to date before merging**
   - Enable: ☑ **Do not allow bypassing the above settings**
   - **Disable admin bypass** for constitutional checks

4. **Save Changes**

**Effect:** PRs with violations will be blocked from merging.

---

## Post-Deployment Testing

### Create Test PR

1. **Create test branch:**
```bash
git checkout -b test-ci-enforcement
```

2. **Add known violation:**
```python
# In observation/types.py
signal_strength: float  # Should trigger R1-Linguistic
```

3. **Commit and push:**
```bash
git add observation/types.py
git commit -m "test: intentional violation for CI testing"
git push origin test-ci-enforcement
```

4. **Open PR on GitHub**
   - Verify workflow runs
   - Verify violation is caught
   - Verify PR is blocked

5. **Clean up:**
```bash
git checkout master
git branch -D test-ci-enforcement
```

---

## Local Developer Setup (One-Time)

### Install Pre-Commit Hooks

```bash
pip install pre-commit
pre-commit install
```

### Test Hooks

```bash
pre-commit run --all-files
```

**Expected output:**
```
[OK] No semantic leaks detected
[OK] No forbidden imports detected
[OK] No structural violations detected
```

---

## Monitoring

### View CI Runs
- GitHub → Actions tab → "Semantic Leak Enforcement"
- Check logs for detailed violation reports

### Metrics to Track
- False positive rate
- Violations caught per PR
- Time to run checks (<5s expected)

---

## Troubleshooting

**CI workflow not running?**
- Check workflow file syntax (YAML)
- Verify triggers (on: pull_request, push)
- Check Actions permissions (Settings → Actions)

**Pre-commit hooks not working?**
- Reinstall: `pre-commit install`
- Check Python path in shebang
- Run manually: `python .github/scripts/test_runner.py`

**False positives?**
- Document in `.github/scripts/README.md`
- Refine regex patterns
- Never disable checks entirely

---

## Success Criteria

✅ Workflow visible in GitHub Actions  
✅ Required status checks enforced  
✅ Test PR with violation blocked  
✅ Pre-commit hooks installed locally  
✅ All checks passing on main branch  

---

END OF DEPLOYMENT INSTRUCTIONS
