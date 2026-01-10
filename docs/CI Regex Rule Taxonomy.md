# CI Regex Rule Taxonomy
(Mapped to Adversarial Semantic Violations)

## Status
CONSTITUTIONAL ENFORCEMENT ARTIFACT  
Normative, preventive, non-semantic (syntax-level only)

This document defines **regex-based CI rules** designed to automatically catch
~80% of high-risk semantic violations **before human review**.

Regexes are **deliberately coarse**.  
False positives are acceptable.  
False negatives are constitutional failures.

---

## 1. Design Principles

1. Regex rules are **preventive**, not definitive
2. They enforce **structural discipline**, not correctness
3. They are:
   - Fast
   - Diff-compatible
   - Language-agnostic where possible
4. They complement (not replace) human review

---

## 2. Rule Categories

Each rule maps to:
- A **semantic leak class**
- One or more **adversarial examples**
- A **constitutional article**

---

## 3. Observation Layer Rules

### R-OBS-01: Derived Semantic Fields in Snapshots

**Purpose:** Prevent hidden interpretation in exposed schemas

**Regex:**
```regex
class\s+ObservationSnapshot[\s\S]*?(score|confidence|signal|pressure|bias|strength|volatility|momentum)

Catches:

    pressure_score

    confidence_hint

    volatility_estimate

Maps to:

    Adversarial 3.1

    Article III (Epistemic Ceiling)

R-OBS-02: Freshness / Liveness Inference

(now|time\(\)|timestamp).*(>|<|-).*(last|prev|previous)

Catches:

    now - last_event_ts

    time() - prev_update

Maps to:

    Adversarial 3.3

    Silence Rule

R-OBS-03: Status Expansion

ObservationStatus\.(OK|STALE|SYNC|READY|ACTIVE)

Maps to:

    Status regression

    Article VI

4. Mandate Emission Rules
R-MAND-01: Confidence / Strength Scalars

(confidence|strength|score|weight)\s*[<>]=?

Catches:

    if confidence > 0.7

    score >= threshold

Maps to:

    Adversarial 4.2

    Mandate purity invariant

R-MAND-02: Mandate Reasoning Language

emit_mandate\([\s\S]*?(reason|because|due_to|justification)

Maps to:

    Adversarial 4.1

    Non-interpretive mandate rule

R-MAND-03: Multiple Emits Per Cycle

emit\([^)]*\)[\s\S]*?emit\([^)]*\)

Maps to:

    Adversarial 4.3

    Single-action invariant

5. Arbitration Rules
R-ARB-01: Heuristic Sorting / Ranking

(sorted|max|min)\(.*mandate.*key=

Catches:

    max(mandates, key=...)

Maps to:

    Adversarial 5.1

    Authority ordering invariant

R-ARB-02: Cross-Cycle Memory

(last_|prev_|previous_).*(mandate|action|decision)

Maps to:

    Adversarial 5.2

    Stateless arbitration rule

6. Execution Layer Rules
R-EXEC-01: PnL-Based Logic

(pnl|profit|loss|drawdown|unrealized)

Maps to:

    Adversarial 6.1

    Execution non-interpretation rule

R-EXEC-02: Directional Flip Shortcuts

(reverse|flip|close_and_reverse|swap_position)

Maps to:

    Adversarial 6.2

    Lifecycle invariants

R-EXEC-03: Implicit Safety Actions

(auto|safety|protect|emergency).*(exit|reduce)

Maps to:

    Unauthorized execution logic

7. Logging & Telemetry Rules
R-LOG-01: Activity Assertions

logger\.(info|warning|error)\(.*(started|advanced|processing|connected|running)

Maps to:

    Adversarial 7.1

    External speech restriction

R-LOG-02: Quality Assertions

(error|failed|healthy|ok|stable|degraded)

(Outside explicitly allowed error paths)

Maps to:

    Epistemic violations

R-METRIC-01: Numeric Activity Telemetry

(metric|telemetry|stats)\.(emit|record|push)

Maps to:

    Adversarial 7.2

    Activity leakage

8. Configuration Backdoor Rules
R-CONFIG-01: Execution Flags

(enable|allow|toggle).*(m6|execute|executor)

Maps to:

    Adversarial 8.1

    Explicit wiring requirement

9. Test Code Rules (Soft Fail)
R-TEST-01: Golden Path Only Tests

assert\s+action\s*==\s*(ENTRY|EXIT|REDUCE)

Severity: WARNING
Reviewer must verify rejection paths exist
10. Directory-Scoped Suppressions

Regex rules may be selectively disabled only if:

    Directory is explicitly whitelisted

    Exception is documented

    Scope is minimal

Example:

allow:
  - observation/internal/**
deny:
  - observation/types.py

(Defined formally in Directory-Scoped Exception Framework)
11. Rule Severity Levels
Level	Meaning
BLOCK	CI failure
WARN	Requires human review
INFO	Audit signal only

Default: BLOCK
12. Completeness & Limits

These rules:

    Catch ~80% of violations

    Do not detect:

        Pure semantic misuse

        Architectural miswiring

        Intentional adversarial obfuscation

They exist to prevent accidental drift, not replace judgment.
13. Constitutional Lock

Any change to:

    Rule removal

    Severity downgrade

    Directory expansion

Requires constitutional amendment, not CI config change.

END OF DOCUMENT