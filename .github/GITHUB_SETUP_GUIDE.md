# GitHub Setup Guide (For Non-GitHub Users)

## Problem 1: Git Push Failed (HTTP 500)

**Error:** `error: RPC failed; HTTP 500`  
**Cause:** Repository size (2GB) exceeded GitHub's HTTP buffer  
**Status:** Commit is local, not pushed to GitHub yet

### Solutions:

**Option A: Increase Git Buffer (Quick Fix)**
```bash
git config http.postBuffer 524288000  # 500MB buffer
git push origin master
```

**Option B: Push in Chunks (if Option A fails)**
```bash
# Push just the CI files first
git push origin master:refs/heads/ci-enforcement

# Then merge via GitHub PR (smaller operation)
```

**Option C: Use SSH Instead of HTTPS**
```bash
# If you have SSH keys configured
git remote set-url origin git@github.com:YOUR_USERNAME/liquidation-trading.git
git push origin master
```

---

## Problem 2: Branch Protection (Cannot Use Git Commands)

**Important:** Branch protection settings are **not configurable via git**. You must use:
- GitHub Web UI (easiest for beginners), OR
- GitHub CLI (`gh` command), OR  
- GitHub API (advanced)

---

## Solution 1: GitHub CLI (Recommended if gh is installed)

### Check if GitHub CLI is installed:
```bash
gh --version
```

If installed, authenticate and configure:
```bash
# Login to GitHub
gh auth login

# Enable branch protection
gh api repos/:owner/:repo/branches/master/protection \
  -X PUT \
  -f required_status_checks[strict]=true \
  -f required_status_checks[contexts][]=semantic-enforcement \
  -f enforce_admins=true \
  -f required_pull_request_reviews=null
```

### Install GitHub CLI (if not installed):
**Windows (PowerShell):**
```powershell
winget install --id GitHub.cli
```

Or download from: https://cli.github.com/

---

## Solution 2: GitHub Web UI (Step-by-Step for Beginners)

Since you mentioned not knowing GitHub, here's the **complete walkthrough**:

### Step 1: Go to Your Repository on GitHub

1. Open your web browser
2. Go to: `https://github.com/YOUR_USERNAME/liquidation-trading`
   - (Replace YOUR_USERNAME with your actual GitHub username)
3. You should see your repository page

### Step 2: Navigate to Settings

1. Click the **"Settings"** tab at the top (to the right of "Insights")
   - It looks like a gear icon ⚙️
2. If you don't see Settings, you might not be logged in or don't have admin rights

### Step 3: Go to Branches Section

1. In the left sidebar, find and click **"Branches"**
   - It's under the "Code and automation" section
2. You'll see "Branch protection rules" page

### Step 4: Add Protection Rule

1. Click the green **"Add rule"** or **"Add branch protection rule"** button
2. In "Branch name pattern", type: `master`
   - (or `main` if your default branch is main)

### Step 5: Configure Protection Settings

**Check these boxes:**

✅ **Require status checks to pass before merging**
   - This enables CI enforcement
   
✅ **Require branches to be up to date before merging**
   - Ensures latest code is tested
   
Under "Status checks that are required":
   - Type: `semantic-enforcement`
   - Click the suggestion when it appears
   - Also add: `Constitutional Compliance Checks` if it appears

✅ **Do not allow bypassing the above settings**
   - Prevents admin override (important for constitutional enforcement)

**Leave unchecked:**
- ❌ Require a pull request before merging (optional, your choice)
- ❌ Require approvals (optional)

### Step 6: Save Changes

1. Scroll to bottom
2. Click **"Create"** or **"Save changes"**
3. You'll see a green success message

---

## Alternative: Skip GitHub for Now (Local-Only)

If you just want CI to work locally without GitHub:

```bash
# Install pre-commit hooks (local enforcement)
pip install pre-commit
pre-commit install

# Test it works
pre-commit run --all-files
```

**Effect:** CI runs on every `git commit` (before code is committed), no GitHub needed.

---

## What to Do Now

**Recommended Priority:**

1. **Fix the push issue first:**
```bash
git config http.postBuffer 524288000
git push origin master
```

2. **Then set up branch protection** (choose one):
   - **Easy:** Use GitHub Web UI (follow steps above)
   - **Advanced:** Use GitHub CLI (`gh` commands)
   - **Local-only:** Install pre-commit hooks

3. **Verify it works:**
   - Create a test branch with a violation
   - Try to merge it (should be blocked)

---

## Need Help?

**If you're stuck on any step:**
1. Can you access https://github.com in your browser?
2. Are you logged in to GitHub?
3. Do you have admin access to the repository?

**If push keeps failing:**
- Repository might be too large for GitHub free tier
- Contact GitHub support or consider Git LFS for large files

---

END OF GITHUB SETUP GUIDE
