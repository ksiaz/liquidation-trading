# Architectural Decisions Log

This document records significant architectural decisions made during the project's evolution.

---

## AD-001: Directory-Scoped Semantic Rules (2026-01-10)

**Context:**  
Phase 6 (M4 Primitive Computation) introduced 25 semantic leak scanner violations in `observation/governance.py`. All violations were structural metrics (e.g., `max_penetration = 0.0`, `len(recent_prices) >= 2`) required for computing M4 primitives.

**Problem:**  
The semantic leak scanner lacks directory-awareness and rule-class detection. It treats all numeric operations as potential semantic leaks, regardless of layer or purpose.

**Decision:**  
1. **Formalized Directory-Scoped Semantic Rules** (see `docs/DIRECTORY_SCOPED_SEMANTIC_RULES.md`)
   - Defined rule classes: EVAL, INTENT, QUALITY, STRUCTURAL_METRIC, AGGREGATION, etc.
   - Specified allowed classes per directory (`observation/` may use STRUCTURAL_METRIC/AGGREGATION)
   - Documented that M4 primitives are descriptive (what IS), not prescriptive (what to DO)

2. **Classified All 25 Violations:**
   - 5 STRUCTURAL_METRIC (allowed)
   - 15 AGGREGATION (allowed)
   - 3 TEMPORAL_PARAMETER (allowed)
   - 2 DESCRIPTIVE_STATE (allowed)
   - **Ruling:** All are FALSE POSITIVES

3. **Temporary CI Exception (PR #4 Only):**
   - Modified `.github/workflows/semantic-enforcement.yml` to skip `observation/` for PR #4
   - Exception is path-scoped, documented, and visible in CI logs
   - **NOT** an admin override or permanent relaxation of branch protection

**Consequences:**  
- ✅ Constitutional integrity preserved (no semantic leaks introduced)
- ✅ Auditability maintained (exception is machine-readable and logged)
- ✅ Progress unblocked (observation system can be merged)
- ⚠️ **Next mandatory work:** Update scanner to implement directory-scoped rules

**Authority:**  
Architect ruling, 2026-01-10

**References:**  
- PR #4: https://github.com/ksiaz/liquidation-trading/pull/4
- `docs/DIRECTORY_SCOPED_SEMANTIC_RULES.md`
- `docs/DIRECTORY_SCOPED_EXCEPTION_FRAMEWORK.md`

**Follow-up Required:**  
~~Next PR must implement scanner update with rule-class detection and directory-awareness. No further observation-layer PRs permitted until scanner is fixed.~~

**RESOLVED:** PR #5 (2026-01-11) - Scanner updated with directory-scoped rule-class detection. Temporary exception removed. AD-001 closed.

---

## Future Decisions

Additional architectural decisions will be appended below with sequential numbering (AD-002, AD-003, etc.).
