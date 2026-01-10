Goal

Make this job mandatory:

Semantic Constitution Enforcement (Scoped)


So that:

❌ PRs cannot be merged if it fails

❌ Direct pushes cannot bypass it

✅ All semantic leaks are caught before merge

Step 1 — Confirm the Job Name (Canonical)

Your workflow defines:

name: Semantic Constitution Enforcement (Scoped)


This exact string is what GitHub uses for branch protection.

⚠️ It must match character-for-character.

Step 2 — Enable Branch Protection

Go to your repository on GitHub

Navigate to:

Settings → Branches → Branch protection rules


Click “Add rule”

Step 3 — Configure the Rule
Branch name pattern

Use one of:

main


or

master


(or both, separate rules if needed)

Enable Required Status Checks

Check:

☑ Require status checks to pass before merging

Then:

☑ Require branches to be up to date before merging
(important — prevents stale bypass)

Add Required Status Check

In the search box, select exactly:

Semantic Constitution Enforcement (Scoped)


If it does not appear yet:

Push a commit that triggers the workflow once

Refresh the page

It will then be selectable

Step 4 — Lock Down Bypass Vectors

Enable all of the following:

☑ Require pull request reviews before merging
☑ Dismiss stale pull request approvals when new commits are pushed
☑ Require conversation resolution before merging

Optional but recommended:

☑ Restrict who can push to matching branches
→ set to no one or admins only

Step 5 — Decide on Admin Override (Strong Recommendation)

To make the constitution non-overrideable, enable:

☑ Do NOT check “Allow administrators to bypass”

This ensures:

Even repo admins cannot merge violating code

Constitutional violations require explicit rule change, not discretion

Resulting Enforcement Model

After this:

Action	Outcome
Semantic leak introduced	❌ CI fails
CI fails	❌ Merge blocked
Admin tries to merge	❌ Blocked
Force push	❌ Blocked
Branch behind main	❌ Blocked

The constitution becomes mechanically enforced, not socially enforced.

Sanity Check (Recommended)

Test with a dummy PR:

Add this line anywhere outside allowed dirs:

confidence = 0.9


Expected result:

CI fails

PR cannot be merged

No override possible

What this achieves (architecturally)

The constitution is now law, not guidance

Enforcement is objective

Violations are detectable

Drift becomes impossible without visible governance change