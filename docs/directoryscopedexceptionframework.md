# Directory-Scoped Exception Framework
(Formal, Minimal, Auditable)

## Status
CONSTITUTIONAL ENFORCEMENT ARTIFACT  
Normative. Binding. Non-heuristic.

This document defines the **only permitted mechanism** by which
constitutional enforcement rules (CI regex, semantic audits, static checks)
may be **selectively relaxed** based on directory scope.

Purpose:  
Allow necessary low-level computation **without permitting semantic leakage**  
into externally meaningful layers.

---

## 1. Core Principle

**Exceptions apply to *directories*, never to rules globally.**

There is:
- ❌ No file-level opt-out
- ❌ No inline suppression
- ❌ No per-developer override
- ❌ No temporary disable

All exceptions are:
- Explicit
- Scoped
- Documented
- Auditable

---

## 2. Invariant: External Boundary Supremacy

No directory-scoped exception may weaken rules governing:

- External speech
- Snapshot schemas
- Mandate emission
- Arbitration outcomes
- Execution actions
- UI / logs / metrics

**If a directory can influence external meaning, it cannot receive exceptions.**

---

## 3. Directory Classification

Every directory in the repository must belong to **exactly one** class.

### 3.1 Class A — External Boundary (No Exceptions)

**Definition:**  
Directories whose code directly or indirectly produces externally observable meaning.

**Examples:**
- `observation/types.py`
- `observation/governance.py`
- `runtime/m6_executor.py`
- `execution/`
- `ui/`
- `api/`

**Rules:**
- 100% rule enforcement
- No suppressions permitted
- CI violations are fatal

---

### 3.2 Class B — Internal Computation (Limited Exceptions)

**Definition:**  
Directories that perform raw computation but do **not** expose meaning.

**Examples:**
- `observation/internal/`
- `observation/ingestion/`
- `data_pipeline/`
- `exchange_adapters/`

**Permitted Exceptions (strictly limited):**
- Counters
- Statistical terminology
- Baselines / averages
- Rolling windows
- Temporary buffers

**Still Forbidden:**
- Exported schemas
- Human-readable logs
- Semantic field names
- Snapshot mutation

---

### 3.3 Class C — Test & Verification Code

**Definition:**  
Code used only for validation, simulation, or proof.

**Examples:**
- `tests/`
- `simulation/`
- `formal_models/`

**Permitted:**
- Direct invocation of M6
- Mock snapshots
- Artificial signals
- Explicit assertions

**Restrictions:**
- Must never be imported by production code
- CI enforces isolation

---

### 3.4 Class D — Documentation

**Definition:**  
Non-executable artifacts.

**Examples:**
- `docs/`
- `*.md`

**Rules:**
- Unrestricted language
- No enforcement

---

## 4. Exception Granting Rules

### 4.1 Explicit Enumeration

All exceptions must be declared in **one file only**:

docs/DIRECTORY_EXCEPTIONS.md


No inline comments.
No per-rule toggles.

---

### 4.2 Minimal Surface Rule

An exception must satisfy:

- Narrowest directory scope
- Narrowest rule set
- Narrowest duration (if temporary)

Example (acceptable):
```yaml
observation/internal/:
  allow:
    - R-OBS-01   # counters
    - R-OBS-02   # baselines

Example (forbidden):

observation/**:
  allow: all

4.3 One-Way Rule

Exceptions may only loosen enforcement inward, never outward.

Forbidden:

    Allowing internal code to influence external schema

    Allowing observation/internal to write to snapshot fields

    Allowing execution to reference internal counters

5. Prohibited Exception Patterns

The following are constitutionally forbidden:

    File-level exceptions

    Regex-level opt-outs

    Inline # noqa, # ignore, # disable

    Environment-variable-based suppression

    CI job branching based on directory

    Developer-specific overrides

Any detection = hard failure.
6. Auditability Requirements

Every exception entry must include:

    Directory path

    Rule IDs suppressed

    Justification (one sentence)

    Date added

    Architect approval reference

Example:

observation/internal/:
  allow:
    - R-OBS-COUNTERS
  justification: "Required for raw ingestion aggregation; never exposed"
  approved_by: ARCH-001
  date: 2026-01-06

7. Drift Prevention Invariants
7.1 No Silent Expansion

    Adding files to a directory does not expand exception scope implicitly

    Moving a file into an excepted directory triggers audit

7.2 No Transitive Trust

Exceptions do not propagate via imports.

Importing from an excepted directory does not grant exception.
8. CI Enforcement Model

CI must verify:

    Every directory has a class

    Every exception is declared centrally

    No rule is disabled without mapping

    No external-boundary directory has exceptions

    No diff introduces new exception paths silently

Failure in any check blocks merge.
9. Constitutional Lock

Changes to this framework require:

    Explicit amendment

    Full semantic audit

    Versioned constitution update

No implementation discretion is permitted.
10. Summary

This framework ensures:

    Raw computation is possible

    Semantic leakage is impossible

    Enforcement is mechanical

    Exceptions are visible, minimal, and reviewable

There is no such thing as a “temporary” exception.

END OF DOCUMENT