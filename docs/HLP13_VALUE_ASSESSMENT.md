HLP13 WORKLOADS: PRACTICAL VALUE ASSESSMENT
What Each Actually Does & Whether You Need It

You're right to question: "What's the point?"

This document provides:
  - Concrete example of each workload in action
  - How it improves a specific trading decision
  - Whether it's essential, valuable, or optional
  - How to validate if it's working

Be ruthless: If a workload doesn't demonstrably improve your edge, don't build it.

---

TIER 1: ESSENTIAL (Build These)

Workload 1: Continuous Strategy Backtesting

What it does (concretely):
  Every night at 3 AM, replays yesterday's market data through your strategies.
  Compares what strategies *would* have done vs what they *actually* did.

Example use case:
  - Your Geometry strategy had 3 losses yesterday
  - Backtest shows: With OI threshold at 1.25 instead of 1.20, only 1 loss
  - You adjust parameter, retest on last 7 days
  - Next week: Win rate improves from 55% to 62%

How it improves trading:
  - Catches parameter drift (what worked last month may not work now)
  - Finds optimal thresholds based on recent data
  - Detects if strategy is degrading

Validation:
  - Does it find better parameters?
  - When you use suggested parameters, does performance improve?
  - If yes: Keep it. If no: It's useless.

Priority: **ESSENTIAL** - This is how you adapt to markets

---

Workload 16: Real-Time Trade Execution Simulation

What it does (concretely):
  Runs strategies in parallel with live system.
  Doesn't submit orders, just simulates what *would* happen.
  Compares simulated PnL to actual PnL.

Example use case:
  - Live trading: Win rate 45% (below paper trading's 58%)
  - Shadow trading shows: Entries are 2 seconds late on average
  - Root cause: Regime controller too slow
  - You optimize, latency drops to 200ms
  - Live win rate recovers to 57%

How it improves trading:
  - Detects execution problems (slippage, timing, fills)
  - Validates strategies work as expected live
  - Catches bugs before they cause losses

Validation:
  - Does shadow vs live divergence reveal real issues?
  - When you fix issues, does live performance improve?

Priority: **ESSENTIAL** - Catches execution bugs early

---

TIER 2: HIGH VALUE (Probably Build These)

Workload 10: Order Flow Imbalance Analysis

What it does (concretely):
  Tracks aggressive buy volume vs aggressive sell volume every second.
  Calculates: imbalance = (buy_vol - sell_vol) / total_vol

Example use case:
  - Geometry strategy detects OI spike at $50,000
  - Without order flow: Enter immediately
  - With order flow: Imbalance shows -0.6 (heavy selling)
  - Decision: Wait 30 seconds for selling to exhaust
  - Entry at $49,950 instead of $50,000 (better price)
  - Stop at $49,500 (same distance, better R:R)

How it improves trading:
  - Better entry timing (wait for selling exhaustion)
  - Avoids entering into strong opposing flow
  - 5-10bps better fills = meaningful over time

Validation:
  - Do trades with favorable imbalance perform better?
  - Calculate: Win rate when imbalance > +0.3 vs < -0.3
  - If significant difference: It's valuable. If not: Remove it.

Priority: **HIGH VALUE** - Improves timing

---

Workload 2: Wallet Behavioral Classification

What it does (concretely):
  Watches 50 large wallets, classifies behavior (manipulator, directional, arb).
  Tracks when they open/close positions.

Example use case:
  - OI spike detected at 10:00 AM
  - Without wallet tracking: Enter based on OI alone (match_score 60%)
  - With wallet tracking: Wallet 0xABC (known manipulator, 85% match_score) opened 10 BTC long at 9:58 AM
  - Decision: Increase match_score to 80%, enter with larger size (1.5% risk vs 1%)
  - Manipulator exits at 10:15, you exit too
  - PnL: +$120 instead of +$80 (larger size)

How it improves trading:
  - Adds match_score when known actors involved
  - Early warning (they enter before cascade visible)
  - Better exit timing (when they exit, you exit)

Validation:
  - Win rate on trades with manipulator confirmation vs without
  - If win rate +10% with confirmation: Valuable
  - If no difference: Don't build it

Priority: **HIGH VALUE** - If manipulators exist and are detectable

---

TIER 3: MEDIUM VALUE (Maybe Build These)

Workload 11: Volatility Surface Modeling

What it does (concretely):
  Calculates realized volatility (1m, 5m, 15m) for each symbol.
  Classifies regime: LOW, MEDIUM, HIGH, EXTREME.

Example use case:
  - Geometry setup detected
  - Without volatility: Use 1% stop distance (standard)
  - With volatility: Current regime is HIGH (vol at 95th percentile)
  - Decision: Widen stop to 1.5% (avoid getting stopped out by noise)
  - Trade survives volatility spike, hits target
  - Without wider stop: Would have been stopped for -1%, actual: +2%

How it improves trading:
  - Adaptive stop placement (wider in high vol)
  - Position sizing adjustment (smaller in high vol)
  - Avoids trading in EXTREME vol (too unpredictable)

Validation:
  - Do adaptive stops reduce false stop-outs?
  - Track: Stop-out rate with adaptive vs fixed stops
  - If 10% fewer false stops: Valuable

Priority: **MEDIUM** - Nice to have, not critical

---

Workload 9: Market Microstructure Modeling

What it does (concretely):
  Models relationship between order size and price impact.
  Predicts: "0.5 BTC market buy will move price 0.08%"

Example use case:
  - Entry signal at $50,000
  - Without microstructure: Submit 0.5 BTC market order
  - Fill: $50,040 (0.08% slippage, $40 cost)
  - With microstructure: Model predicts 0.08% impact
  - Decision: Split into 2x 0.25 BTC orders, 10 seconds apart
  - Fills: $50,020 + $50,025 (0.04% + 0.05% = 0.045% average)
  - Saved: $20 per trade × 100 trades/month = $2,000/month

How it improves trading:
  - Reduces slippage through smart execution
  - Better fill prices
  - Adds up over many trades

Validation:
  - Actual slippage vs predicted
  - If predictions accurate (<20% error): Valuable
  - If wildly off: Useless

Priority: **MEDIUM** - Only if trading large size

---

TIER 4: LOW VALUE / EXPERIMENTAL (Probably Skip These)

Workload 12: Liquidity Heatmap Generation

What it does (concretely):
  Creates visual heatmap of orderbook depth at each price level.
  Detects "liquidity walls" and "voids".

Example use case:
  - Cascade detected, target at $51,000
  - Without heatmap: Hold for target
  - With heatmap: Shows massive bid wall at $50,800 (100 BTC)
  - Decision: Exit at $50,800 instead of waiting for $51,000
  - Price bounces at wall, never reaches $51,000
  - PnL: +1.6% instead of +0.5% (got stopped at breakeven)

How it improves trading:
  - Better target placement (exit before walls)
  - Avoid areas with liquidity voids (low fill probability)

Validation:
  - Do liquidity walls actually cause bounces?
  - Track: Price behavior at detected walls
  - If <60% accuracy: It's noise, remove it

Priority: **LOW** - Orderbook is already visible, this just prettifies it

---

Workload 13: Historical Pattern Mining

What it does (concretely):
  Scans 90 days of data looking for recurring sequences.
  Finds: "OI +15% → funding spike → cascade (85% of time)"

Example use case:
  - Pattern miner discovers: "When BTC OI drops 10%, ETH drops 15% within 5 min (78% of time)"
  - This pattern wasn't in original strategy
  - You add: "If BTC cascade detected, watch ETH for cascade"
  - New ETH cascade strategy: +12 trades/month, 68% win rate

How it improves trading:
  - Discovers new patterns you didn't know
  - Suggests new strategies
  - Finds cross-symbol relationships

Validation:
  - Do discovered patterns hold out-of-sample?
  - Backtest patterns on unseen data
  - If patterns degrade >20%: Overfitting, useless

Priority: **LOW** - High risk of finding spurious correlations

---

Workload 14: Monte Carlo Risk Simulation

What it does (concretely):
  Simulates 10,000 scenarios of next 30 days.
  Estimates worst-case drawdown.

Example use case:
  - Current risk: 2% per trade
  - Monte Carlo shows: 95% probability, max drawdown < 25%
  - But 5% of scenarios: drawdown > 40%
  - Decision: Reduce risk to 1.5% per trade
  - New simulation: 95% probability, max DD < 20%
  - Sleep better knowing ruin probability is low

How it improves trading:
  - Validates risk parameters aren't suicidal
  - Estimates capital requirements
  - Avoids blow-up scenarios

Validation:
  - Do simulated drawdowns match realized drawdowns?
  - After 90 days live, compare actual vs predicted
  - If within 10%: Useful. If way off: Model is wrong

Priority: **LOW** - HLP17 risk limits already conservative

---

Workload 3, 4, 5, 6, 7, 8, 15: SKIP FOR NOW

These are increasingly speculative:
  - Cross-asset correlation (Workload 4): Maybe useful, but strategies are single-symbol
  - Anomaly detection (Workload 5): What's "normal" on Hyperliquid? Unclear.
  - Regime optimization (Workload 6): Already covered by backtesting
  - Funding estimation (Workload 7): Funding is observable, estimation adds little
  - Network graphs (Workload 8): Too complex, questionable ROI
  - Parameter sensitivity (Workload 15): Covered by backtesting
  - Liquidation band detection (Workload 3): Bands are visible in OI data

---

RECOMMENDED MINIMAL SET

If starting from scratch, build only:

Month 1: Workload 1 (Backtesting)
  - Validates everything
  - Optimizes parameters
  - Essential

Month 2: Workload 16 (Execution Simulation)
  - Validates live trading
  - Catches bugs
  - Essential

Month 3: Workload 10 (Order Flow Imbalance)
  - Improves entry timing
  - High-signal data
  - Likely valuable

That's it. 3 workloads.

Then validate:
  - Does backtesting find better parameters? (Measure: performance improvement)
  - Does shadow trading catch issues? (Measure: bugs found)
  - Does order flow improve fills? (Measure: win rate with vs without)

If all 3 show measurable value: Consider adding:
  - Workload 2 (Wallet Tracking) - if manipulators detectable
  - Workload 11 (Volatility) - if high vol periods cause problems

If any of the first 3 don't show value: Remove them.

---

VALIDATION FRAMEWORK

For each workload, define success metric:

Workload 1 (Backtesting):
  - Metric: Parameter changes improve rolling 30-day Sharpe by >0.1
  - Test: Monthly
  - Pass: Yes → Keep, No → Remove

Workload 16 (Execution Sim):
  - Metric: Catches ≥1 execution bug per month
  - Test: Review logs
  - Pass: Yes → Keep, No → Remove

Workload 10 (Order Flow):
  - Metric: Win rate +5% when using flow-filtered entries
  - Test: A/B test (1 week with, 1 week without)
  - Pass: Yes → Keep, No → Remove

Be ruthless. If it doesn't measurably improve edge: Kill it.

---

ANTI-PATTERNS TO AVOID

❌ "We have compute, so let's use it"
  → Build workloads that prove their value

❌ "This seems interesting"
  → Only build what demonstrably improves trading

❌ "Maybe it'll be useful later"
  → Build when you need it, not before

❌ "Let's collect all possible data"
  → Collect what strategies actually use

❌ "More features = better system"
  → More features = more complexity = more bugs

---

BOTTOM LINE

Start with 3 workloads:
  1. Backtesting (essential)
  2. Execution simulation (essential)
  3. Order flow imbalance (likely valuable)

Validate each shows measurable improvement.

Add workloads one at a time, only after previous ones prove valuable.

Most workloads in HLP13 are speculative.
Some will be valuable.
Most won't be.

Your job: Figure out which is which through systematic testing.

Don't build for the sake of building.
Build what improves your edge.
