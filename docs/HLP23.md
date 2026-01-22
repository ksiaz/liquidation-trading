THRESHOLD DISCOVERY & TUNING
From Arbitrary Numbers to Validated Decision Boundaries

---

CRITICAL NOTICE: ALL THRESHOLDS ARE HYPOTHESES

Every threshold in this document is a HYPOTHESIS requiring validation.

No threshold has been validated against historical data.
No threshold has been tested in live trading.
All performance expectations (win rates, trade counts) are GUESSES.

Treat ALL values in this document as STARTING POINTS, not PROVEN VALUES.

---

VOCABULARY NOTE:

This document uses "confidence" to mean "event match score" or "threshold proximity."
In code, use "match_score" or "priority_score" instead of "confidence" to comply
with constitutional vocabulary rules.

---

CONSERVATIVE STARTING THRESHOLDS (HYPOTHESES):

These values are derived from general market structure reasoning, NOT empirical data.

OI_SPIKE_THRESHOLD = 1.15      # 15% above 15-minute baseline
FUNDING_SKEW_THRESHOLD = 0.0015  # 0.15% (15 bps)
DEPTH_ASYMMETRY_THRESHOLD = 1.5  # Bid depth / Ask depth
MATCH_SCORE_MINIMUM = 0.70       # 70% of conditions met

Rationale for each:
- OI 1.15: Normal OI varies ±10%. 15% is 1.5x normal movement.
- Funding 0.15%: Normal funding is ±0.01%. 0.15% is 15x normal.
- Depth 1.5: Normal asymmetry is 0.8-1.2. 1.5 is outside normal range.
- Match score 0.70: Require 70% of entry conditions to be met.

THESE ARE GUESSES. Validate before trusting.

---

WHAT THIS DOCUMENT COVERS:

Every strategy has thresholds:
  - OI spike > 1.15x baseline (HYPOTHESIS)
  - Funding skew > 0.15% (HYPOTHESIS)
  - Match score > 0.70 (HYPOTHESIS)
  - Depth asymmetry > 1.5x (HYPOTHESIS)

But where do these numbers come from?
How do you know 1.15 is better than 1.10 or 1.20?

This document defines:
  - How to start without historical data (COLD START)
  - What thresholds actually do in your system
  - How to discover initial values (data-driven)
  - How to validate they work (testing)
  - How to tune them over time (adaptation)
  - How to document them (auditability)

Without this: Thresholds are guesses.
With this: Thresholds are validated decision boundaries.

NOTE: Even after following this document, thresholds remain validated HYPOTHESES
until proven profitable over significant sample size (100+ trades).

---

PART 0: THE COLD START PROBLEM

The Circular Dependency:

Problem: You need 90 days of data to optimize thresholds.
But: You need thresholds to run the system for 90 days.
Catch-22: Where do initial thresholds come from?

This is the bootstrapping problem. You must solve it first.

---

---

SOLUTION 1: Collect Your Own Historical Data First

The Reality Check:

You DON'T know if Hyperliquid provides:
  - Historical orderbook snapshots (archive API?)
  - Historical trade ticks
  - Historical OI/funding data
  - What granularity (1s? 1m? Daily only?)

You must verify what's actually available.

What TO DO First (Week -4 to Week 0):

Step 1: Run node for data collection BEFORE building strategies

Week -4 to Week 0:
  1. Set up node
  2. Build basic data pipeline (HLP7):
     - WebSocket connection
     - Message logging
     - Cold storage (save everything)
  3. Let it run for 4 weeks
  4. Don't trade yet, just collect

After 4 weeks:
  - You have 30 days of YOUR OWN data
  - Known granularity (what YOU captured)
  - Known completeness (what YOU logged)
  - Ready to start threshold optimization

This is the ONLY way to be certain you have the data you need.

Timeline: 4 weeks data collection before threshold optimization

---

Alternative: Check if Historical Data Exists

Before committing to 4-week wait, investigate:

1. Hyperliquid Documentation
   - Read API docs thoroughly
   - Look for historical endpoints
   - Check what's actually available

2. Community Resources
   - Ask in Hyperliquid Discord/forums
   - Check if data vendors exist
   - See what others have done

3. Node Query Capabilities
   - Can your node query past blocks?
   - How far back does it go?
   - What's the query limit?

If you find accessible historical data:
  - Great! Use it (verify granularity matches needs)
  - Proceed with optimization immediately

If NOT available:
  - Must collect your own (4+ weeks)
  - OR start with conservative defaults
  
Don't assume. Verify.

---

SOLUTION 2: Conservative Default Thresholds

If historical data unavailable, use conservative defaults based on market structure.

How to derive conservative defaults:

Step 1: Study market behavior manually

Watch market for 1 week:
  - Observe typical OI changes (5-10% is normal)
  - Note funding rate fluctuations (±0.01% is common)
  - Track depth asymmetry (1.2-1.3x is noise)

Step 2: Set thresholds above noise level

Conservative = 2-3 standard deviations above normal

Example observations:
  - Normal OI change: Mean 7%, Std 3%
  - Noise threshold: 7% + (2 × 3%) = 13%
  - Conservative threshold: 15% (round up)

Apply this to all thresholds:
  - OI spike: 1.15 (15% increase, conservative)
  - Funding skew: 0.020 (2%, conservative)
  - Depth asymmetry: 1.8x (conservative)
  - Match score: 0.80 (high bar, conservative)

Step 3: Deploy conservatively

With conservative thresholds:
  - Fewer setups detected (low recall)
  - Higher precision (fewer false positives)
  - Lower trade frequency
  - Higher win rate (but less profit)

This is acceptable for bootstrapping phase.

Step 4: Collect data, then optimize

After 30 days with conservative thresholds:
  - You have labeled data (which setups worked)
  - Run optimization (relax thresholds gradually)
  - Re-deploy with optimized values

After 60 days:
  - Re-optimize again
  - Closer to optimal

After 90 days:
  - Full optimization possible
  - System mature

Timeline: 0 days to start (immediate), 90 days to optimal

---

SOLUTION 3: Phased Threshold Relaxation

Start tight, relax gradually as you learn.

Phase 1 (Days 1-30): Ultra-Conservative
  - OI threshold: 1.25 (25% increase)
  - Funding threshold: 0.025 (2.5%)
  - Match score: 0.85 (85%)

  **HYPOTHESIS:** May produce 5-10 trades/month. Win rate unknown.

Phase 2 (Days 31-60): Conservative
  - OI threshold: 1.20 (20% increase)
  - Funding threshold: 0.020 (2%)
  - Match score: 0.75 (75%)

  **HYPOTHESIS:** May produce 15-25 trades/month. Win rate unknown.

Phase 3 (Days 61-90): Moderate
  - OI threshold: 1.15 (15% increase)
  - Funding threshold: 0.015 (1.5%)
  - Match score: 0.70 (70%)

  **HYPOTHESIS:** May produce 25-40 trades/month. Win rate unknown.

Phase 4 (Days 90+): Optimized
  - Run full optimization on all collected data
  - Deploy optimal thresholds

  **HYPOTHESIS:** Optimized thresholds should improve Sharpe ratio vs defaults.

Advantages:
  - Start immediately (day 1)
  - Low risk initially (tight thresholds)
  - Gradual learning
  - Smooth transition to optimized

---

SOLUTION 4: Use Domain Knowledge as Prior

Leverage market structure understanding to seed thresholds.

Example: OI Spike Threshold

Market structure knowledge:
  - Liquidations are forced, not optional
  - Hyperliquid guarantees execution
  - Cascades are mechanical (price → liquidations → more liquidations)

Reasoning:
  - Small OI changes (5-10%) are normal market flow
  - Medium changes (10-20%) may indicate positioning shift
  - Large changes (>20%) often precede forced liquidation

Initial threshold: 1.20 (20% increase)
  - Above normal flow
  - Below extreme events
  - Conservative middle ground

Rationale documented: "Based on liquidation mechanics, 20% OI increase suggests positioning stress"

This is better than random guess, even without data.

Apply to all thresholds:
  - Funding: Extreme when >2% per 8h → threshold 0.02
  - Depth: Market makers provide 1.2-1.3x depth → threshold 1.5x (above normal)
  - Match score: High bar for real money → 0.75 minimum

---

RECOMMENDED BOOTSTRAP STRATEGY (REALISTIC)

Path A: If Historical Data Accessible (Verify First!)

Week -2 to Week 0:
  1. Verify Hyperliquid has historical API
  2. Download/query available data
  3. Verify it has what you need:
     - Orderbook depth (for slippage, depth asymmetry)
     - Trade ticks (for order flow)
     - OI history (for spike detection)
     - Funding rates (for skew detection)
  4. If ALL needed data available:
     - Label 50-100 events
     - Run optimization
     - Get initial thresholds

Week 1 (Deploy):
  5. Paper trade with optimized thresholds (7 days)
  6. Validate performance
  7. Go live with small capital

This ONLY works if historical data actually exists and has correct granularity.

---

Path B: No Historical Data (Most Likely)

Week -4 to Week 0 (Data Collection Phase):
  1. Build basic data pipeline (node + logging)
  2. Let it run for 4 weeks minimum
  3. Collect YOUR OWN data
  4. Verify completeness (no gaps)

Week 1-2 (Conservative Start):
  5. Use domain-knowledge defaults (Solution 4)
  6. Deploy conservatively
  7. Paper trade (7 days)
  8. Go live with VERY small capital

Week 3-8 (Continue Collecting):
  9. Trade conservatively for 30 more days
  10. Now have ~60 days total data
  11. Run first optimization
  12. Relax thresholds slightly

Week 9-16 (Approach Optimal):
  13. Trade for another 30 days
  14. Now have 90 days data
  15. Run full optimization
  16. Deploy optimal thresholds
  17. Scale capital gradually

Timeline: 16 weeks to fully optimized system

This is REALISTIC. No assumptions about data availability.

---

Path C: Hybrid (Recommended)

Week -4 to Week 0:
  1. Start collecting your own data immediately
  2. WHILE collecting, investigate historical data
  
If historical found (during collection):
  - Great! Use it to seed initial thresholds
  - Still keep collecting your own data
  
If NOT found:
  - You're already collecting
  - Proceed with conservative defaults
  - Optimize when you have enough data

This hedges against both scenarios.

---

THRESHOLD STARTING VALUES (RECOMMENDED)

If you must start immediately without data, use these:

Geometry Strategy:
  - OI spike threshold: 1.18 (18%)
  - Funding skew threshold: 0.018 (1.8%)
  - Depth asymmetry threshold: 1.6x
  - Match score minimum: 0.75

Kinematics Strategy:
  - Range threshold: 0.015 (1.5% Bollinger squeeze)
  - Volume threshold: 0.8x (20% below average)
  - OI stability threshold: ±0.05 (5%)
  - Match score minimum: 0.70

Cascade Strategy:
  - OI collapse threshold: 0.85 (15% drop)
  - Price momentum threshold: 0.02 (2% move in 1min)
  - Inevitability threshold: 0.90 (90% probability)
  - Match score minimum: 0.80

Risk Management:
  - Daily loss limit: 0.03 (3%)
  - Position size limit: 0.05 (5% of capital)
  - Max aggregate exposure: 0.10 (10%)

These are conservative estimates based on market structure.
Not optimal, but safe starting points.

Use these for 30 days, then re-optimize with collected data.

---

---

PART 1: UNDERSTANDING THRESHOLDS

What is a Threshold?

A threshold is a decision boundary that converts continuous data into discrete actions.

Example:

Continuous data: OI change = +18%
Threshold: OI spike if > +15%
Decision: Is 18% > 15%? Yes → Setup detected

Thresholds appear everywhere:

Strategy Setup Detection:
  - OI spike threshold: 1.20x (20% increase)
  - Funding skew threshold: 0.015 (1.5% 8h)
  - Depth asymmetry threshold: 1.5x

Regime Classification:
  - OI stability threshold: ±5% = sideways
  - Funding neutrality threshold: ±0.005 = neutral

Risk Management:
  - Daily loss limit: -3%
  - Position size limit: 5% of capital
  - Win streak boost threshold: 3 consecutive wins

Event Match Score:
  - Minimum match score: 0.70 (70%)
  - High match score: > 0.85 (85%)

Every threshold is a hypothesis: "This boundary separates signal from noise."

---

PART 2: THE THRESHOLD PROBLEM

Why Arbitrary Thresholds Fail:

Example: OI spike threshold

If you guess 1.20 (20% increase):
  - Too low: Many false positives (noise triggers strategy)
  - Too high: Miss real setups (signal goes undetected)
  - Just right: Goldilocks zone (maximize true positives, minimize false)

How do you know where "just right" is?

You don't. Unless you test.

The Optimization Surface:

For any threshold, there's a tradeoff:

Lower threshold:
  ↑ More setups detected (higher recall)
  ↓ More false positives (lower precision)
  ↓ Lower win rate

Higher threshold:
  ↓ Fewer setups detected (lower recall)
  ↑ Fewer false positives (higher precision)
  ↑ Higher win rate (but fewer trades)

Optimal threshold balances:
  - Trade frequency (need enough trades)
  - Win rate (need profitable trades)
  - Sharpe ratio (risk-adjusted return)

---

PART 3: THRESHOLD DISCOVERY METHODS

Method 1: Historical Data Analysis

Process:

1. Collect labeled data (past events)
   - Label: "Was this a real liquidation cascade?" (yes/no)
   - Feature: OI change magnitude

2. Calculate distribution
   - Real cascades: Mean OI change = 25%, Std = 8%
   - False signals: Mean OI change = 12%, Std = 5%

3. Find separating threshold
   - Plot distributions
   - Find point where they diverge
   - Often: Mean of real events - 1 std dev

Example:

Real cascades: 25% ± 8% → Lower bound: 17%
False signals: 12% ± 5% → Upper bound: 17%

Separation point: ~17%

Initial threshold: OI spike = 1.17 (17% increase)

Pros:
  - Data-driven
  - Based on actual market behavior
  - Explainable

Cons:
  - Requires labeled historical data
  - May not generalize to future

---

Method 2: Grid Search Optimization

Process:

1. Define threshold range
   - Min: 1.10 (10% increase)
   - Max: 1.40 (40% increase)
   - Step: 0.05 (5% increments)

2. For each threshold value:
   - Run backtest on historical data
   - Measure: Win rate, trade count, Sharpe ratio

3. Select optimal threshold
   - Maximize objective function (e.g., Sharpe ratio)
   - Subject to constraints (e.g., min 20 trades/month)

Example Results:

Threshold | Trades/month | Win Rate | Sharpe | Score
1.10      | 45           | 52%      | 1.1    | 49.5
1.15      | 32           | 58%      | 1.4    | 44.8
1.20      | 24           | 63%      | 1.6    | 38.4
1.25      | 18           | 68%      | 1.7    | 30.6
1.30      | 12           | 72%      | 1.5    | 18.0

Score = Win_Rate × sqrt(Trades) × Sharpe

Optimal: 1.15 (best score)

Pros:
  - Systematic
  - Finds local optimum
  - Considers multiple metrics

Cons:
  - Risk of overfitting
  - Computationally expensive
  - May not generalize

---

Method 3: Receiver Operating Characteristic (ROC) Analysis

Process:

1. For each possible threshold:
   - Calculate: True Positive Rate (TPR) = Real setups detected
   - Calculate: False Positive Rate (FPR) = False setups detected

2. Plot ROC curve (TPR vs FPR)

3. Find threshold that maximizes:
   - Youden's Index: J = TPR - FPR
   - Or: Closest to top-left corner (high TPR, low FPR)

Example:

Threshold | TPR  | FPR  | J
1.10      | 0.95 | 0.45 | 0.50
1.15      | 0.88 | 0.28 | 0.60 ← Optimal
1.20      | 0.75 | 0.15 | 0.60
1.25      | 0.60 | 0.08 | 0.52

Optimal: 1.15 or 1.20 (tie)

Pros:
  - Clear visual representation
  - Balances sensitivity and specificity
  - Industry standard

Cons:
  - Requires binary labels (yes/no)
  - Doesn't consider profitability
  - Equal weighting of errors

---

Method 4: Expected Value Maximization

Process:

1. For each threshold, calculate expected value:
   EV = (P(win) × avg_win) - (P(loss) × avg_loss) - (costs)

2. Select threshold with highest EV

Example:

Threshold | Win% | Avg Win | Avg Loss | Trades | EV/trade
1.10      | 52%  | $100    | $80      | 45     | $10.40
1.15      | 58%  | $120    | $75      | 32     | $26.10 ← Optimal
1.20      | 63%  | $140    | $70      | 24     | $31.90 ← Better!
1.25      | 68%  | $150    | $65      | 18     | $28.20

But also consider total PnL:
1.20: $31.90 × 24 = $765.60/month ← Best total

Optimal: 1.20 (highest total EV)

Pros:
  - Directly optimizes profit
  - Accounts for win/loss asymmetry
  - Realistic

Cons:
  - Requires accurate win/loss estimates
  - Backtest-dependent
  - Overfitting risk

---

PART 4: VALIDATION FRAMEWORK

Once you have a threshold candidate, validate it:

Step 1: Out-of-Sample Testing

Don't use the same data you optimized on.

Split data:
  - In-sample: First 60% (for optimization)
  - Out-of-sample: Last 40% (for validation)

Process:
  1. Find optimal threshold on in-sample data (e.g., 1.15)
  2. Test on out-of-sample data
  3. Compare performance

Results:
  In-sample: Sharpe 1.6, Win rate 58%
  Out-of-sample: Sharpe 1.4, Win rate 55%

If out-of-sample degrades < 20%: Threshold is robust
If degrades > 20%: Overfitted, choose more conservative threshold

---

Step 2: Walk-Forward Testing

Simulate real-world deployment:

1. Optimize on data [t0, t1] → Threshold A
2. Trade with Threshold A on [t1, t2]
3. Optimize on data [t1, t2] → Threshold B
4. Trade with Threshold B on [t2, t3]
5. Repeat...

Example:

Jan-Feb optimization: Threshold = 1.15
Mar performance: Sharpe 1.3

Mar-Apr optimization: Threshold = 1.20
May performance: Sharpe 1.5

May-Jun optimization: Threshold = 1.18
Jul performance: Sharpe 1.4

Average: Sharpe 1.4 (realistic expectation)

This simulates adaptive threshold tuning.

---

Step 3: Sensitivity Analysis

How sensitive is performance to threshold changes?

Test:
  Threshold ± 10%
  Measure: Change in Sharpe ratio

Example:

Threshold | Sharpe | Delta
1.08      | 1.2    | −0.3
1.15      | 1.5    | 0.0 (baseline)
1.23      | 1.4    | −0.1

If Sharpe changes < 10% within ±10% range: Robust threshold
If Sharpe very sensitive: Fragile, likely overfitted

Robust thresholds are preferable.

---

Step 4: Regime Stability Testing

Does threshold work across different market regimes?

Test threshold performance in:
  - Bull markets (2021-style)
  - Bear markets (2022-style)
  - Sideways markets (ranging)
  - High volatility periods
  - Low volatility periods

Example:

Threshold 1.15 tested across regimes:

Regime       | Sharpe | Win Rate | Trades
Bull         | 1.8    | 62%      | 45
Bear         | 1.2    | 54%      | 38
Sideways     | 0.9    | 48%      | 22
High Vol     | 0.6    | 45%      | 30
Low Vol      | 1.5    | 65%      | 18

If consistent across regimes: Good
If fails in specific regime: Consider regime-dependent thresholds

---

PART 5: MULTI-THRESHOLD OPTIMIZATION

Strategies have multiple thresholds.

Example (Geometry strategy):
  - OI spike: > 1.20
  - Funding skew: > 0.015
  - Depth asymmetry: > 1.5
  - Match score minimum: > 0.70

Optimizing all simultaneously:

Problem: 4 thresholds → 4-dimensional search space

If each threshold has 10 possible values:
  10^4 = 10,000 combinations to test

Approaches:

Approach 1: One-at-a-time Optimization

1. Fix all thresholds except one
2. Optimize that threshold
3. Move to next threshold
4. Repeat until convergence

Example:

Iteration 1:
  - Optimize OI (others fixed) → 1.15
Iteration 2:
  - Optimize funding (OI=1.15, others fixed) → 0.018
Iteration 3:
  - Optimize depth (OI=1.15, funding=0.018, others fixed) → 1.6
Iteration 4:
  - Optimize match_score (all others fixed) → 0.65
Iteration 5:
  - Re-optimize OI (others at new values) → 1.18
  ...converges

Pros: Feasible computationally
Cons: May miss global optimum (local optimum only)

---

Approach 2: Grid Search (Coarse-to-Fine)

1. Coarse grid (large steps):
   - OI: [1.10, 1.20, 1.30]
   - Funding: [0.01, 0.02]
   - Depth: [1.3, 1.5, 1.7]
   - Match_score: [0.6, 0.7, 0.8]
   Total: 3 × 2 × 3 × 3 = 54 combinations

2. Find best coarse combination

3. Fine grid around best:
   - OI: [1.15, 1.18, 1.20, 1.22, 1.25]
   - Funding: [0.015, 0.018, 0.020, 0.022]
   - Etc.

Pros: More thorough
Cons: Computationally expensive

---

Approach 3: Bayesian Optimization

Use probabilistic model to guide search:

1. Test small sample of threshold combinations
2. Build model of performance surface
3. Select next threshold to test (maximize expected improvement)
4. Repeat until convergence

Pros: Efficient (fewer evaluations needed)
Cons: Complex implementation

---

PART 6: THRESHOLD DOCUMENTATION

Every threshold must be documented:

Template:

```
Threshold: OI Spike Detection
Value: 1.18 (18% increase from 15m baseline)
Date Set: 2026-01-15
Method: Grid search on 90 days historical data
Performance: Sharpe 1.5, Win rate 58%, 28 trades/month
Validation: Out-of-sample Sharpe 1.4 (7% degradation)
Sensitivity: ±5% threshold change → <10% Sharpe change
Regime Stability: Works in all tested regimes
Next Review: 2026-02-15 (monthly)
Rationale: Balances trade frequency with win rate. Lower thresholds increased false positives significantly.
```

Why document:

1. Auditability: Know why threshold was chosen
2. Replicability: Can recreate decision
3. Review: Scheduled threshold re-evaluation
4. Learning: Understand what worked/didn't

Store in version-controlled config file.

---

PART 7: ADAPTIVE THRESHOLDS

Markets evolve. Thresholds that worked may degrade.

Continuous Monitoring:

Track monthly:
  - Win rate with current threshold
  - Sharpe ratio
  - Trade frequency

Alert if:
  - Win rate drops > 10% from baseline
  - Sharpe drops > 0.3
  - Trade frequency changes > 50%

Example:

Jan: OI threshold 1.18, Sharpe 1.5
Feb: OI threshold 1.18, Sharpe 1.3 (degraded)
Mar: OI threshold 1.18, Sharpe 1.1 (alert!)

Response: Re-optimize threshold on recent 90 days

---

Scheduled Re-optimization:

Every month (or quarter):
  1. Run optimization on last 90 days
  2. Find new optimal threshold
  3. Compare to current threshold
  4. If new threshold significantly better (>15% improvement):
     - Paper trade with new threshold for 1 week
     - If validated: Deploy
  5. If current threshold still optimal: Keep

Example:

Monthly review:
  Current: OI = 1.18, Sharpe 1.3
  Optimized: OI = 1.22, Sharpe 1.5 (+15%)
  Action: Test OI = 1.22 in paper mode
  After 1 week paper: Sharpe 1.6
  Decision: Deploy OI = 1.22

---

Regime-Dependent Thresholds:

Alternative: Different thresholds for different regimes

Example:

Sideways regime:
  - OI threshold: 1.15 (lower, less OI movement expected)
  
Expansion regime:
  - OI threshold: 1.25 (higher, filter for only strong signals)

Implementation:

```python
def get_oi_threshold(regime):
  if regime == SIDEWAYS:
    return 1.15
  elif regime == EXPANSION:
    return 1.25
  else:
    return 1.20  # default
```

Pros: Adapts to market conditions
Cons: More complex, more parameters to tune

---

PART 8: COMMON PITFALLS

Pitfall 1: Overfitting to Recent Data

Symptom: Threshold performs great in backtest, fails live

Cause: Optimized on short time period, overfitted to noise

Fix:
  - Use longer optimization period (90+ days)
  - Out-of-sample validation
  - Walk-forward testing

---

Pitfall 2: Too Many Thresholds

Symptom: 10+ thresholds, impossible to optimize

Cause: Strategy too complex

Fix:
  - Simplify strategy
  - Remove least important thresholds
  - Use composite scores instead of multiple thresholds

---

Pitfall 3: Threshold Hysteresis Ignored

Problem: Threshold at boundary causes oscillation

Example:
  OI = 19.8% (< 20% threshold) → No signal
  OI = 20.1% (> 20% threshold) → Signal
  OI = 19.9% (< 20% threshold) → Signal off
  Flip-flopping!

Fix: Add hysteresis (different thresholds for on/off)

```python
THRESHOLD_ON = 1.20  # Signal turns on
THRESHOLD_OFF = 1.15  # Signal turns off

if not signal_active:
  if oi_change > THRESHOLD_ON:
    signal_active = True
else:
  if oi_change < THRESHOLD_OFF:
    signal_active = False
```

---

Pitfall 4: Ignoring Costs

Problem: Optimal threshold without costs ≠ optimal with costs

Example:
  Threshold 1.10: 60 trades/month, $2000 profit, $300 fees = $1700 net
  Threshold 1.20: 25 trades/month, $1800 profit, $125 fees = $1675 net

Without costs: 1.10 looks better ($2000 > $1800)
With costs: Roughly equal ($1700 vs $1675)

Fix: Include execution costs in optimization objective

---

PART 9: IMPLEMENTATION CHECKLIST

[ ] Identify all thresholds in strategy
[ ] For each threshold:
    [ ] Document current value
    [ ] Choose discovery method (grid search recommended)
    [ ] Run optimization on historical data
    [ ] Validate out-of-sample
    [ ] Perform sensitivity analysis
    [ ] Document results
[ ] Store thresholds in versioned config
[ ] Set up monthly review schedule
[ ] Implement monitoring (performance tracking)
[ ] Define alert conditions (degradation triggers)

---

BOTTOM LINE

Thresholds are not guesses.
Thresholds are decision boundaries discovered through data.

Every threshold must:
  1. Be derived from historical analysis
  2. Be validated out-of-sample
  3. Be documented (method, rationale, performance)
  4. Be monitored (for degradation)
  5. Be re-optimized (monthly/quarterly)

Without systematic threshold discovery:
  - You're trading on arbitrary numbers
  - Performance is luck, not skill
  - System will degrade over time

With systematic threshold discovery:
  - Thresholds are evidence-based
  - Performance is measurable and attributable
  - System adapts to market changes

Don't guess. Discover. Validate. Monitor. Adapt.
