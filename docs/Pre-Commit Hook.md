Pre-Commit Hook — Semantic Constitution Enforcement
Objective

Guarantee that any commit violating constitutional semantic rules is rejected locally, before it can:

Reach CI

Pollute history

Create review noise

Be “accidentally” pushed

This hook must be bit-for-bit aligned with CI.

Canonical Rule

Pre-commit must call the same scanner, same regexes, same directory scopes as CI.

No duplicate logic.
No partial enforcement.
No “best effort”.

File Layout (Authoritative)

Assume you already have:

/ci/
  semantic_scan.py
  semantic_rules.yaml


CI uses:

python ci/semantic_scan.py


The pre-commit hook will invoke exactly this.

Step 1 — Create .git/hooks/pre-commit
touch .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

Step 2 — Pre-Commit Hook (Exact)

Paste verbatim:

#!/usr/bin/env bash
set -euo pipefail

echo "🔒 Semantic Constitution Pre-Commit Enforcement"

# Only scan staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|ts|js|yaml|yml)$' || true)

if [[ -z "$STAGED_FILES" ]]; then
  echo "✓ No relevant files staged"
  exit 0
fi

# Create temp staging area
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Export staged versions (not working tree)
for file in $STAGED_FILES; do
  mkdir -p "$TMP_DIR/$(dirname "$file")"
  git show ":$file" > "$TMP_DIR/$file"
done

# Run the SAME scanner as CI
echo "→ Running semantic scan on staged content"
python ci/semantic_scan.py --root "$TMP_DIR"

echo "✓ Semantic constitution satisfied"

Step 3 — Modify Scanner to Support --root

Your CI scanner must accept a root override.

Minimal required change (if not present)

In semantic_scan.py:

import argparse
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--root", default=".", help="Scan root")
args = parser.parse_args()

ROOT = pathlib.Path(args.root)


Then ensure all file walks use ROOT, not ..

This guarantees CI and pre-commit are identical.

Step 4 — Make It Impossible to Bypass Accidentally
Enforce hook installation

Add this file:

scripts/install_hooks.sh

#!/usr/bin/env bash
set -e

HOOK=".git/hooks/pre-commit"

if [[ ! -f "$HOOK" ]]; then
  echo "Installing semantic constitution pre-commit hook"
  cp scripts/pre-commit "$HOOK"
  chmod +x "$HOOK"
fi


Then add to README:

⚠️ This repository enforces semantic constitutional rules.
Run `scripts/install_hooks.sh` after cloning.

Step 5 — Alignment Guarantees (Critical)

This system guarantees:

Vector	Status
CI enforcement	✅
Local enforcement	✅
Staged-only correctness	✅
Directory-scoped exceptions	✅
Regex parity	✅
No duplicated logic	✅
Failure Behavior (By Design)

If a violation exists:

❌ SEMANTIC VIOLATION
File: execution/order_router.py
Line: 88
Rule: forbidden term "confidence"
Section: Annex A.3


Result:

Commit is rejected

Nothing is staged

No override

No ambiguity

What This Prevents Permanently

“I’ll fix it in CI”

“Forgot to run tests”

“Just a small wording thing”

“It’s internal”

“It’s temporary”

All eliminated.

Optional Hardening (If You Want Absolute Discipline)

You can add:

git config core.hooksPath .githooks

Signed commit requirement

Hook checksum verification in CI

Hook version hash check

But not required for correctness.

Bottom Line

With this hook:

The constitution is enforced at the moment of authorship, not review.

CI becomes confirmation — not defense.