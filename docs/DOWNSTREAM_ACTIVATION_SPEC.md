# Phase Next: Downstream Activation After M2/M4 Closure

**Document Type:** Architectural Specification
**Date:** 2026-02-01
**Prerequisite:** M2_M4_SEMANTIC_CLOSURE.md (RATIFIED)

---

## 1. DOWNSTREAM CONTRACT SPECIFICATION

### 1.1 How External Policies Consume M4PrimitiveBundle

**Interface:**
```
ObservationSnapshot.primitives: Dict[str, M4PrimitiveBundle]
```

**Contract:**
- Policies receive `M4PrimitiveBundle` as immutable input
- Policies access primitives by field name (e.g., `bundle.zone_penetration`)
- `None` means "structural fact absent" — not failure, not zero
- Policies must handle `None` gracefully (skip, not crash)
- Policies cannot modify, cache, or feedback into primitives

**Consumption Pattern (Descriptive):**
```
1. PolicyAdapter.generate_mandates() receives ObservationSnapshot
2. PolicyAdapter extracts M4PrimitiveBundle for target symbol
3. PolicyAdapter invokes frozen external policy functions
4. External policy reads primitive fields (read-only)
5. External policy returns StrategyProposal or None
```

**Current External Policies (FROZEN):**
| Policy | File | Consumes |
|--------|------|----------|
| Geometry | ep2_strategy_geometry.py | zone_penetration, displacement |
| Kinematics | ep2_strategy_kinematics.py | velocity, compactness |
| Absence | ep2_strategy_absence.py | structural_absence |
| Orderbook Test | ep2_strategy_orderbook_test.py | resting_size, absorption |
| SLBRS | ep2_slbrs_strategy.py | Regime gated |
| EFFCS | ep2_effcs_strategy.py | Regime gated |
| Cascade Sniper | ep2_strategy_cascade_sniper.py | ProximityData, LiquidationBurst |

### 1.2 How Policies Emit Mandates

**Emission Path:**
```
External Policy → StrategyProposal → PolicyAdapter → Mandate
```

**StrategyProposal Structure:**
- `action`: Proposed action type
- `symbol`: Target symbol
- `direction`: LONG or SHORT (for entry)
- `quantity`: Position size (Decimal)
- `entry_price`: Price hint (Decimal)
- `strategy_id`: Emitting strategy identifier

**Mandate Structure (runtime/arbitration/types.py):**
```python
@dataclass(frozen=True)
class Mandate:
    symbol: str
    type: MandateType          # ENTRY | EXIT | REDUCE | HOLD | BLOCK
    authority: float           # Non-negative
    timestamp: float
    direction: Optional[str]   # "LONG" | "SHORT"
    strategy_id: Optional[str]
    quantity: Optional[Decimal]
    entry_price: Optional[Decimal]
```

**MandateType Hierarchy (Theorem 2.2):**
```
EXIT (5) > BLOCK (4) > REDUCE (3) > ENTRY (2) > HOLD (1)
```

### 1.3 How Mandate Authority Is Assigned

**Rule:** Authority is a **static wiring parameter**, not a computed score.

**Current Assignment (AdapterConfig):**
```python
default_authority: float = 5.0
```

**Properties:**
- Authority does NOT reflect "quality" or "confidence"
- Authority does NOT vary based on primitive values
- Authority is used ONLY for deterministic tiebreaking
- Higher authority wins when same MandateType conflicts

**Anti-Pattern (Prohibited):**
```python
# WRONG: Computing authority from primitives
authority = primitive.strength * 10.0  # FORBIDDEN
```

### 1.4 How Arbitration Consumes Mandates

**Arbitrator Contract (runtime/arbitration/arbitrator.py):**

**Input:** `Set[Mandate]` for single symbol
**Output:** Exactly one `Action`

**Algorithm (Deterministic - Theorem 3.1):**
```
1. If any EXIT mandate → return Action(EXIT)
2. If any BLOCK mandate → filter out ENTRY mandates
3. Group remaining by type, select highest authority per type
4. Return highest priority actionable type
5. If only BLOCK remains → return NO_ACTION
6. If empty → return NO_ACTION
```

**Properties:**
- Symbol-local (Theorem 5.1): No cross-symbol interference
- Deterministic (Theorem 3.1): Same mandates → same action
- Complete (Theorem 8.1): Always produces result
- EXIT supremacy (Theorem 2.2): EXIT cannot be overridden

### 1.5 How Execution Consumes Arbitration Output

**Action Structure:**
```python
@dataclass(frozen=True)
class Action:
    type: ActionType           # ENTRY | EXIT | REDUCE | HOLD | NO_ACTION
    symbol: str
    strategy_id: Optional[str]
    direction: Optional[str]
    quantity: Optional[Decimal]
    entry_price: Optional[Decimal]
```

**Execution Contract:**
- Action is consumed by ExecutionController
- ENTRY/REDUCE require non-None quantity (validated)
- NO_ACTION and HOLD produce no exchange interaction
- Execution outcome is logged but NOT fed back to observation

---

## 2. NEXT LEGITIMATE ENGINEERING SURFACE

### Selected: **(A) External Policy Validation & Correctness Tests**

### Justification

1. **Immediate Dependency on Closed Layers:**
   External policies are the first downstream consumers of M4. With M2/M4 now closed, policy correctness is the next verification surface.

2. **Determinism Verification Required:**
   Policies must be deterministic (same M4 input → same proposal). This is testable now that M4 output is stable.

3. **No Upstream Changes Required:**
   Policy tests consume frozen M4PrimitiveBundle structures. No observation layer modifications needed.

4. **Enables Downstream Confidence:**
   Verified policies enable confident arbitration and execution testing in subsequent phases.

5. **Existing Test Infrastructure:**
   Test files exist (`runtime/tests/test_policy_adapter.py`) but require coverage expansion.

### Excluded Alternatives (With Reasoning)

| Option | Why Not Next |
|--------|--------------|
| (B) Arbitration edge-case audit | Depends on policy correctness first |
| (C) Execution ↔ Risk stress testing | Requires verified arbitration output |
| (D) Offline analytics harness | Lower priority than runtime correctness |
| (E) CI / semantic enforcement | Valuable but policy tests more urgent |
| (F) Documentation artifacts | Already produced; action needed now |

---

## 3. INVARIANTS THAT MUST NOW HOLD

The following invariants are testable because M2/M4 are closed:

### Invariant 1: Snapshot Immutability

**Statement:**
> ObservationSnapshot and M4PrimitiveBundle are frozen after construction. No downstream consumer may modify them.

**Verification Method:**
- Unit test: Attempt to modify snapshot field → expect failure
- Type check: `@dataclass(frozen=True)` enforced
- Runtime guard: No setter methods exist

### Invariant 2: Policy Determinism

**Statement:**
> Given identical M4PrimitiveBundle input, an external policy must produce identical output.

**Verification Method:**
- Unit test: Call policy twice with same input → assert equal output
- Fuzz test: Randomized M4 bundles, verify f(x) == f(x)
- No time-dependent or random logic in policies

### Invariant 3: Mandate Authority Monotonicity

**Statement:**
> Mandate authority is assigned at emission time and never modified.

**Verification Method:**
- Unit test: Mandate.authority is read-only (frozen dataclass)
- Code audit: No authority computation from primitive values
- Arbitration test: Authority used only for same-type tiebreaking

### Invariant 4: No Cross-Symbol Leakage

**Statement:**
> M4 primitives, policies, mandates, and arbitration are strictly symbol-scoped. No cross-symbol inference occurs.

**Verification Method:**
- Unit test: Arbitrate mandates for symbol A, verify symbol B unaffected
- Code audit: No iteration over multiple symbols in single policy call
- M4 test: Each M4PrimitiveBundle contains single symbol field

### Invariant 5: No Execution Feedback

**Statement:**
> Execution outcomes (fills, P&L, errors) do not flow back into observation layers.

**Verification Method:**
- Dependency audit: observation/ has no imports from runtime/executor/
- Code audit: No execution result passed to ObservationSystem
- Integration test: Execute trade, verify M4 primitives unchanged

### Invariant 6: Policy-Primitive Separation

**Statement:**
> Policies consume M4 primitives but cannot request new primitives or modify existing ones.

**Verification Method:**
- Interface audit: Policies receive M4PrimitiveBundle, not ObservationSystem
- No primitive computation in external_policy/
- Type enforcement: M4PrimitiveBundle is frozen

---

## 4. WHAT THIS PHASE EXPLICITLY DOES NOT DO

### ❌ Modify M2 or M4
- No new nodes, fields, primitives, or thresholds
- No semantic reinterpretation
- No "improvements" or "clarifications"

### ❌ Introduce Optimization
- No parameter tuning based on outcomes
- No "better" authority assignment
- No scoring, ranking, or win-rate calculation

### ❌ Create Feedback Loops
- No execution results flowing to observation
- No performance metrics affecting primitive computation
- No learning or adaptation

### ❌ Change Frozen External Policies
- Policies in external_policy/ are FROZEN
- No logic modifications
- Test-only interaction

### ❌ Implement New Strategies
- No new policy creation
- No new entry/exit logic
- No trading strategy work

### ❌ Performance Analysis
- No backtesting inside runtime
- No edge quantification
- No expectancy calculation

### ❌ Production Deployment
- This phase is verification only
- No live trading changes
- No risk parameter modifications

---

## 5. NEXT-ACTION CHECKLIST

### Phase A: External Policy Validation & Correctness Tests

| # | Task | Type | Acceptance Criteria |
|---|------|------|---------------------|
| A1 | Enumerate all external policies with their M4 dependencies | Audit | Table mapping policy → consumed primitives |
| A2 | Create synthetic M4PrimitiveBundle fixtures | Test setup | Fixtures for each primitive tier (None, minimal, full) |
| A3 | Write determinism tests for each policy | Unit test | Same input → same output, 100% pass |
| A4 | Write None-handling tests for each policy | Unit test | Policies return None or valid proposal, never crash |
| A5 | Verify policy does not modify input bundle | Unit test | Assert input unchanged after policy call |
| A6 | Verify policy has no side effects | Unit test | No global state, no file I/O, no network |
| A7 | Document policy input/output contract | Spec | One-page contract per policy |

### Exit Criteria for Phase A

- [ ] All 6 frozen policies have determinism tests
- [ ] All policies handle None primitives gracefully
- [ ] No policy modifies its input
- [ ] No policy has side effects
- [ ] Policy contracts documented

### Next Phase (After A Complete)

Proceed to **(B) Mandate Arbitration Edge-Case Audit** only after Phase A exit criteria are met.

---

## 6. FORMAL DECLARATION

**Downstream work proceeds under these constraints:**

1. M2 and M4 are READ-ONLY
2. External policies are FROZEN (test-only interaction)
3. No optimization, scoring, or feedback permitted
4. All work is verification and validation
5. Implementation changes require explicit architectural approval

**This phase is about proving correctness, not improving performance.**

---

*End of Downstream Activation Specification*
