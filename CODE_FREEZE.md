# System v1.0 - Code Freeze Declaration

**Date:** 2026-01-05  
**Status:** HARD FREEZE  
**Authority:** Phase V1-LIVE Plan

---

## Frozen Components (No Modifications Allowed)

The following components are **frozen** and may not be modified without explicit authorization:

### Memory & Observation Stack
- `memory/m1_ingestion.py` - Structural ingestion
- `memory/m2_memory_store.py` - Memory storage
- `memory/m3_view_synthesis.py` - View synthesis
- All M4 primitive modules:
  - `memory/m4_tier_a_*.py` (8 primitives)
  - `memory/m4_structural_absence.py` (Tier B-1)
  - `memory/m4_traversal_voids.py` (Tier B-1)
  - `memory/m4_event_absence.py` (Tier B-1)
  - `memory/m4_structural_persistence.py` (Tier B-2.1)
  - `memory/m4_exposure_counting.py` (Tier B-2.1)

### Governance Layer
- `memory/m5_query_schemas.py` - Query schemas
- `memory/m5_access.py` - Access control routing
- `memory/m6_mandate.py` - Mandate evaluation

### External Policy Stack
- `external_policy/ep2_strategy_geometry.py` - Strategy #1
- `external_policy/ep2_strategy_kinematics.py` - Strategy #2
- `external_policy/ep2_strategy_absence.py` - Strategy #3
- `external_policy/ep3_arbitration.py` - Arbitration
- `execution/ep4_action_schemas.py` - Action grammar
- `execution/ep4_risk_gates.py` - Risk gates
- `execution/ep4_execution.py` - Execution orchestrator
- `execution/ep4_ghost_adapter.py` - Ghost execution

---

## Allowed Modifications (Instrumentation Only)

The following are permitted:

### Logging & Monitoring
- Add logging statements for metrics collection
- Create new monitoring scripts
- Create dashboard visualizations
- Add instrumentation hooks

### Replay & Analysis
- Create replay tooling
- Add snapshot storage utilities
- Create analysis scripts
- Add metrics aggregation

### Testing
- Add new tests covering existing behavior
- Create integration test scenarios
- Add stress tests

---

## Rationale

The code freeze ensures that:

1. **No rationalized changes** poison the empirical experiment
2. **Structural sufficiency** is tested as-is
3. **Real blind spots** are identified through pressure, not hunches
4. **Future extensions** are justified by logged evidence

---

## To Modify Frozen Code

You MUST provide:

1. **Logged evidence** from Phase V1-LIVE runs
2. **Specific timestamp** of failure/blind spot
3. **Primitive outputs** showing structural ambiguity
4. **Proposed change** with justification
5. **Authorization** from Phase V1-LIVE decision framework

**Without logged evidence, NO changes allowed.**

---

## Freeze Duration

**Start:** 2026-01-05  
**End:** TBD (after Phase V1-LIVE completion and decision)

Minimum 7 days of continuous live ghost execution required before any modifications considered.

---

**Enforcement:** This freeze is self-imposed discipline. Violating it undermines the entire epistemic architecture.
