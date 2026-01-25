# EXTERNAL POLICY CONSTITUTION

**Status:** Constitutional
**Authority:** Absolute
**Scope:** External Policy & Execution Layers (EP2-EP4, M6)
**Effect:** Permanent
**Relationship:** Complements EPISTEMIC_CONSTITUTION.md (which governs M1-M5)

---

## ARTICLE I: SOLE PURPOSE

External policies exist to execute conditional actions based on observed market structure.

---

## ARTICLE II: OBSERVATION-EXECUTION BOUNDARY

### Observation Layers (M1-M5)
Governed by EPISTEMIC_CONSTITUTION.md:
- Record facts only
- Never predict, never rank, never interpret
- Enforce invariants

### Policy Layers (EP2-EP4)
Governed by this document:
- Consume observation outputs
- Evaluate conditions
- Execute actions when conditions met
- Acknowledge uncertainty

**The boundary is unidirectional:**
- Policies consume observations
- Observations never know about policies
- Policy decisions never contaminate observation

---

## ARTICLE III: PERMITTED OPERATIONS

External policies MAY:

1. **Define Thresholds**
   - Specify conditions for action (e.g., `absorption_ratio ≥ 0.65`)
   - Document threshold sources (market mechanics, ATR multiples, etc.)
   - Declare thresholds as operational decisions, not truth claims

2. **Execute Conditionally**
   - "When structure X appears, execute action Y"
   - No claim about outcome probability
   - No claim about certainty

3. **Reference Historical Observations**
   - "Over N samples, structure X preceded outcome Y in M% of cases"
   - Statistical fact, not prediction guarantee
   - Must include sample size and timeframe

4. **Classify Regimes**
   - Distinguish market states (SIDEWAYS, EXPANSION, DISABLED)
   - Based on observable metrics (VWAP distance, ATR ratios, orderflow)
   - No claim about regime superiority or predictability

---

## ARTICLE IV: FORBIDDEN OPERATIONS

External policies MUST NEVER:

1. **Claim Certainty**
   - ❌ "This trade will succeed"
   - ❌ "This structure guarantees profit"
   - ❌ "This is a winning setup"

2. **Assign Confidence**
   - ❌ Numeric confidence scores (0-100%, probabilities)
   - ❌ Confidence labels ("high confidence", "strong signal")
   - ❌ Quality rankings ("excellent", "poor", "weak", "strong")

3. **Imply Causation**
   - ❌ "Structure X causes outcome Y"
   - ❌ "Absorption leads to reversal"
   - ❌ "Liquidations drive price"

4. **Collapse to Expectation**
   - ❌ "Config X has 60% win rate, therefore we expect it to perform well"
   - ❌ Selecting thresholds based on backtest win rate optimization
   - ❌ Ranking primitives by historical correlation with profits

5. **Use Forbidden Vocabulary**
   - ❌ Signal, Setup, Opportunity, Edge, Alpha
   - ❌ Bullish, Bearish, Strong, Weak
   - ❌ Prediction, Forecast, Confidence, Quality
   - ✅ Structure, Condition, Threshold, Regime, Action

---

## ARTICLE V: OUTCOME DIVERGENCE PRINCIPLE (P12)

**Core Principle:**
Identical observable structures can lead to different outcomes.

**Implications:**
1. No threshold selection implies outcome predictability
2. Historical correlation ≠ future causation
3. Trading decisions are conditional procedures, not predictions
4. The system can be wrong about any individual trade

**Required Acknowledgment:**
Every external policy must document:
- "This policy executes action A when structure S appears"
- "Same structure may lead to different outcomes"
- "Historical observation X does not guarantee future outcome Y"

---

## ARTICLE VI: THRESHOLD DERIVATION

### Permitted Sources
Thresholds MAY be derived from:
1. **Market Mechanics**
   - ATR multiples (e.g., `displacement ≥ 0.5 × ATR`)
   - Orderflow ratios (e.g., `imbalance ≥ 0.35`)
   - Liquidity multiples (e.g., `zone_liquidity ≥ 2.5 × avg`)

2. **Statistical Boundaries**
   - Z-scores (e.g., `liquidation_zscore ≥ 2.5`)
   - Percentiles from observation (e.g., P95 of observed values)
   - Volatility-adjusted distances

3. **Structural Criteria**
   - Non-degeneracy checks (e.g., `compactness > 0`)
   - Existence criteria (e.g., `persistence_duration > 30s`)
   - Regime classification rules

### Forbidden Sources
Thresholds MUST NOT be derived from:
1. **Outcome Optimization**
   - Backtest win rate maximization
   - Profit/loss optimization
   - "Best performing" configuration selection

2. **Predictive Modeling**
   - Machine learning trained on outcomes
   - Correlation with future price
   - Regression against profits

**Rationale:** Outcome-based threshold selection collapses to expectation (violates P12)

---

## ARTICLE VII: REGIME MUTUAL EXCLUSION

Multiple strategies may coexist ONLY if:
1. Regime classification is deterministic
2. Regimes are mutually exclusive (only one active at a time)
3. DISABLED state exists when no regime criteria met

**Example:**
- SIDEWAYS_ACTIVE: VWAP containment + volatility compression + balanced orderflow
- EXPANSION_ACTIVE: VWAP escape + volatility expansion + orderflow dominance
- DISABLED: Neither regime valid
- Both strategies cannot execute simultaneously

---

## ARTICLE VIII: TRANSPARENCY REQUIREMENTS

Every external policy MUST document:

1. **Strategy Identifier**
   - Unique ID (e.g., "EP2-SLBRS-V1")
   - Version tracking

2. **Threshold Definitions**
   - All threshold values explicitly stated
   - Source of each threshold (ATR multiple, Z-score, etc.)
   - Why threshold chosen (market mechanic, not backtest result)

3. **Assumptions**
   - What structure the policy acts on
   - What the policy assumes about structure (without claiming certainty)
   - Example: "Assumes absorption_ratio ≥ 0.65 may precede reversal (not guaranteed)"

4. **Invalidation Criteria**
   - When policy stops executing (regime change, condition violation)
   - Exit logic clearly defined

5. **Historical Context (Optional)**
   - "Over N samples, structure X preceded outcome Y in M% of cases"
   - Must include: sample size, timeframe, symbols
   - Must not claim: "therefore this will continue"

---

## ARTICLE IX: LOGGING REQUIREMENTS

Policy execution logs MUST include:

**At Entry:**
- Timestamp
- Strategy ID
- Structure observed (primitive values)
- Thresholds crossed
- Action taken (ENTRY)
- NO confidence score, NO quality assessment

**At Exit:**
- Timestamp
- Strategy ID
- Exit reason (invalidation trigger, regime change, etc.)
- Action taken (EXIT, REDUCE)
- NO performance claim, NO outcome interpretation

**Never Log:**
- "Good trade", "Bad trade"
- "Should have", "Would have"
- Confidence assessment
- Performance prediction

---

## ARTICLE X: EMPIRICAL CALIBRATION PROHIBITION

**Forbidden:**
Using historical trade outcomes to select or adjust thresholds is **epistemically illegal**.

**Why:**
1. Selects "best performing" thresholds = ranking by outcome
2. Implies thresholds with better past performance will perform better in future
3. Collapses to expectation (violates P12)
4. Optimizes for past data, not structural validity

**Permitted Alternative:**
1. Define thresholds from market mechanics (ATR, Z-scores, liquidity ratios)
2. Use percentiles from observation distribution (P95 of observed values)
3. Apply thresholds uniformly without outcome-based selection
4. Track outcomes for analysis, not for threshold adjustment

**Example of Violation:**
- Run 17,000 trades with 125 configurations
- Rank configurations by win rate
- Select top 10 configurations
- **This is collapsing to expectation (prohibited)**

**Example of Compliance:**
- SLBRS uses `absorption_ratio ≥ 0.65` from liquidity mechanics
- EFFCS uses `liquidation_zscore ≥ 2.5` from deviation significance
- Thresholds applied consistently
- Outcomes tracked but not used for threshold selection

---

## ARTICLE XI: FALLIBILITY REQUIREMENT

All external policies MUST acknowledge:

1. **Individual Trade Fallibility**
   - Any specific trade can fail
   - Structure presence ≠ outcome guarantee
   - Risk management required

2. **Threshold Uncertainty**
   - Thresholds are operational choices, not truth claims
   - Different thresholds would yield different trades
   - No threshold is "optimal"

3. **Outcome Variance**
   - Same structure → different outcomes (P12)
   - Historical statistics ≠ future performance
   - "Past N samples showed X% rate" ≠ "Next trade has X% probability"

---

## ARTICLE XII: RISK MANAGEMENT SEPARATION

Risk management is DISTINCT from strategy signals:

**Strategy Layer (EP2):**
- Proposes: ENTRY, EXIT, HOLD, REDUCE, BLOCK
- Based on: Observed structure
- No claim about: Risk, size, probability

**Risk Layer (EP4):**
- Enforces: Position size limits, exposure limits, drawdown limits
- Based on: Account state, position state, invariants
- Independent of: Strategy confidence (which doesn't exist)

**No strategy may:**
- Suggest position size
- Adjust size based on "confidence"
- Override risk invariants

---

## ARTICLE XIII: AMENDMENT RULES

This constitution may be amended to:
1. **Strengthen constraints** (additional prohibitions)
2. **Clarify existing rules** (no semantic change)
3. **Add transparency requirements**

This constitution may NOT be amended to:
1. Permit confidence scoring
2. Permit outcome-based threshold optimization
3. Permit certainty claims
4. Weaken any prohibition in Articles IV, V, VI, or X

---

## ARTICLE XIV: ENFORCEMENT

**Violations:**

Any external policy that violates this constitution is **epistemically illegal**.

Specific violations:
- Assigning confidence scores → ILLEGAL
- Optimizing thresholds via backtest win rates → ILLEGAL
- Claiming prediction or causation → ILLEGAL
- Using forbidden vocabulary in external output → ILLEGAL

**Consequences:**

Epistemic illegality voids:
- Policy trustworthiness
- Trade validity (for analysis purposes)
- System constitutional compliance

**Remedy:**

Policy must be:
1. Halted immediately
2. Rewritten to comply
3. Re-certified before execution

---

## ARTICLE XV: INTEGRATION WITH EPISTEMIC_CONSTITUTION.md

**Observation Layers (M1-M5):**
- Governed by EPISTEMIC_CONSTITUTION.md
- Never predict, never rank, never interpret
- Remain usable without external policies

**Policy Layers (EP2-EP4):**
- Governed by this document
- Consume observations, execute conditionally
- Acknowledge uncertainty, no confidence claims

**Both Constitutions Share:**
- Silence Rule: Say nothing when truth cannot be proven
- Failure Rule: Halt on invariant violation
- Vocabulary Rule: Forbidden terms remain forbidden

**Difference:**
- EPISTEMIC_CONSTITUTION: Observation may never imply prediction
- EXTERNAL_POLICY_CONSTITUTION: Policies may execute conditionally, but must acknowledge fallibility and outcome divergence

---

## FINAL STATEMENT

External policies are not predictions.

They are **conditional procedures**:
- "When structure S, execute action A"
- Not: "Structure S predicts outcome O"

They acknowledge **outcome divergence** (P12):
- Same structure may lead to different outcomes
- Historical correlation ≠ future causation
- The system can be wrong about any individual trade

They derive thresholds from **market mechanics**, not outcome optimization:
- ATR multiples, Z-scores, liquidity ratios
- Not: Backtest win rate maximization

Confidence is forbidden.
Certainty is forbidden.
Outcome-based optimization is forbidden.

**Conditional execution + acknowledged uncertainty = constitutional compliance.**

---

**END OF EXTERNAL POLICY CONSTITUTION**

This document governs how the system trades while preserving epistemic integrity.
