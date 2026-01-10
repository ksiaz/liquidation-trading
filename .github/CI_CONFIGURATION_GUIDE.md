# CI/CD Configuration Guide

## GitHub Actions Setup

### Workflow File
**Location:** `.github/workflows/semantic-enforcement.yml`

**Triggers:**
- Pull requests to `main` or `develop`
- Pushes to `main`

**Jobs:**
1. Semantic leak scanning
2. Import validation
3. Structural validation

**Status:** Workflow file created, not yet deployed to GitHub

---

## Required Status Checks (GitHub Settings)

To make CI enforcement **blocking** (PRs cannot merge without passing):

### Steps:
1. Go to repository **Settings** → **Branches**
2. Add/Edit branch protection rule for `main`
3. Enable: **Require status checks to pass before merging**
4. Add required checks:
   - `Constitutional Compliance Checks`
   - `semantic-enforcement`

5. Enable: **Require branches to be up to date before merging**
6. **Do NOT** enable admin bypass for these checks

**Effect:** PRs with constitutional violations will be blocked from merging.

---

## Pre-Commit Hooks Setup

### Installation (Local Development)

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Test hooks
pre-commit run --all-files
```

### Usage
Once installed, hooks run automatically on `git commit`.

**To bypass** (emergency only, strongly discouraged):
```bash
git commit --no-verify
```

---

## Testing the CI Setup

### Test Locally
```bash
# Run all checks
python .github/scripts/test_runner.py

# Run individual checks
python .github/scripts/semantic_leak_scan.py
python .github/scripts/import_validator.py
python .github/scripts/structural_validator.py
```

### Test on GitHub
1. Create a test branch with a known violation
2. Open PR
3. Verify CI runs and catches violation
4. Verify PR is blocked from merging

**Example test violation:**
```python
# In observation/types.py
signal_strength: float  # Should trigger R1-Linguistic
```

---

## Monitoring & Maintenance

### View CI Runs
- GitHub Actions tab → "Semantic Leak Enforcement"
- Check logs for detailed violation reports

### Update Rules
1. Modify regex patterns in scripts
2. Test locally
3. Commit changes
4. CI updates automatically

### False Positives
1. Document in `.github/scripts/README.md`
2. Refine regex (never disable)
3. Consider exclusions only if constitutionally justified

---

## Success Criteria

- ✅ Workflow file created
- ✅ Pre-commit config created
- ⏳ Workflow deployed to GitHub
- ⏳ Branch protection enabled
- ⏳ Pre-commit hooks installed locally
- ⏳ Test PR validated

---

## Next Steps

1. **Push to GitHub:** Commit `.github/` directory
2. **Enable branch protection:** Configure required checks
3. **Install pre-commit:** Local setup for developers
4. **Test end-to-end:** Create test PR with violation

---

END OF CI CONFIGURATION GUIDE
