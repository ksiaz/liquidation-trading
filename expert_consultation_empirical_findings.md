# Expert Consultation - Empirical Data Analysis Results

## Context

We've been developing a crypto trading system based on orderbook microstructure analysis. After implementing signal detection logic, we conducted an empirical analysis of our actual collected data before asking theoretical questions.

## What We Have

### Data Infrastructure
- **PostgreSQL database** with 88 hours of high-resolution data
- **1-second orderbook snapshots** for BTC/ETH/SOL
- **~115,000 snapshots per symbol**
- **Captured metrics**: bid/ask prices, orderbook imbalance, spread, depth

### Current Strategy Parameters
- **Profit Target**: 0.5% 
- **Stop Loss**: 10%
- **Position Size**: 2% of portfolio per trade
- **Intended Holding Time**: Minutes (implied by 0.5% target)

## Empirical Analysis Results

We analyzed the predictive power of orderbook imbalance across different forward-looking windows:

### Key Finding: Orderbook Imbalance Predicts Direction, Not Magnitude

**BTC Analysis (41,000+ high-imbalance instances):**
```
High Bid Imbalance (>30%):
- 10s forward:  Avg return +0.003%
- 30s forward:  Avg return +0.005%
- 60s forward:  Avg return +0.005%
- 120s forward: Avg return +0.006%

Win Rate (hitting 0.5% target): 0.0%
```

**ETH Analysis (41,700+ high-imbalance instances):**
```
High Bid Imbalance (>30%):
- 10s forward:  Avg return +0.004%
- 30s forward:  Avg return +0.006%
- 60s forward:  Avg return +0.006%
- 120s forward: Avg return +0.007%

Win Rate (hitting 0.5% target): 0.0-0.1%
```

**SOL Analysis (2,449 high-imbalance instances):**
```
High Bid Imbalance (>30%):
- 10s forward:  Avg return +0.005%
- 30s forward:  Avg return +0.008%
- 60s forward:  Avg return +0.009%
- 120s forward: Avg return +0.007%

Win Rate (hitting 0.5% target): 0.2%
```

### What This Means

1. **Directional Edge Exists**: High bid imbalance → slight positive bias, high ask imbalance → slight negative bias
2. **Microscopic Moves**: Average magnitude is 0.005-0.007% (1/100th of our target)
3. **Timeframe Mismatch**: 1-second data → 10-120s prediction window = too short for 0.5% moves
4. **Stop Loss Problem**: Our 10% stop is 1,666x larger than typical moves

## The Fundamental Question

We have high-quality, high-resolution orderbook data that clearly shows predictive power for **tiny directional moves** (0.005-0.009% over 10-120 seconds), but we're trying to build a strategy targeting **0.5% profit** with a **10% stop loss**.

This is a **100x magnitude gap**.

## Questions for Expert

### Question 1: Strategy Direction
Given our data characteristics (1-second snapshots, 0.006% avg predictable moves), which approach makes the most sense?

**Option A: HFT/Market-Making Approach**
- Target: 1-3 basis points (0.01-0.03%)
- Stop: 2-5 basis points (0.02-0.05%)
- Holding: 10-60 seconds
- Volume: 50-100+ trades per day
- **Matches what our data can actually predict**

**Option B: Swing Trading Approach**
- Target: 0.5-1.0%
- Stop: 1-2%
- Holding: Minutes to hours
- Volume: 5-15 trades per day
- **Requires different data/timeframe aggregation**

**Option C: Hybrid Approach**
- Use orderbook for precise entry timing (reduce slippage)
- Use higher-timeframe signals (5min/15min) for direction/exits
- Combines high-res data with realistic targets

Which path is most viable given our infrastructure and data quality?

### Question 2: Data Utilization
Our 1-second orderbook snapshots capture:
- Bid/ask imbalance (30%+ imbalances occur ~35% of the time)
- Spread dynamics
- Top 20 levels of depth
- Price momentum

If we stay with the current data resolution, what realistic metrics should we optimize for?
- Success rate per trade?
- Profit factor?
- Sharpe ratio target?
- Expected win rate?

### Question 3: Timeframe Consideration
To target 0.5% profits, should we:

**Option A**: Aggregate our 1-second data into larger bars (5min, 15min)?
- Pros: Could find 0.5% moves at this scale
- Cons: Lose microstructure edge

**Option B**: Keep 1-second granularity, accept smaller targets?
- Pros: Leverage our data's strength
- Cons: Higher frequency, more execution complexity

**Option C**: Multi-timeframe approach?
- 5min/15min for trend/targets
- 1-second for entry/exit precision

### Question 4: Signal Frequency vs Quality Trade-off
Our empirical data shows:
- **High-frequency potential**: 41,000+ extreme imbalance events over 88 hours = ~11 per hour
- **Low profit per trade**: 0.006% average move
- **Clear directional bias**: Positive edge exists

Is it better to:
- Trade frequently with tiny edges (market-making style)?
- Wait for rarer, larger setups (selective swing trading)?
- How do transaction costs (0.08% round-trip) affect this decision?

### Question 5: Risk Parameters
Given that typical moves are 0.005-0.009%:

What sensible risk parameters should we use?
- If targeting 3 bps (0.03%), what stop makes sense? (5 bps? 10 bps?)
- If targeting 50 bps (0.50%), what hold time is realistic? (30min? 2hr?)
- What position size makes sense for these micro-moves?

## Our Current Hypothesis

Based on the data, we believe **Option A (HFT approach)** or **Option C (Hybrid)** might be most appropriate because:

1. ✅ Our data clearly shows predictive power at 10-120s timeframes
2. ✅ Edge size (0.006%) is realistic for HFT but too small for swing
3. ✅ High signal frequency (11/hour) supports higher trade volume
4. ❌ BUT: 0.08% transaction costs eat 13x the avg edge (0.006%)
5. ❌ Need to verify if execution speed matters for 1-120s holds

**Is this reasoning sound, or are we missing something fundamental about how to use orderbook microstructure data?**

## What We Need

Concrete guidance on:
1. Which strategy type to pursue given our data characteristics
2. Realistic performance metrics to target
3. Appropriate timeframe for 0.5% profit targets (if we keep that goal)
4. Whether our transaction costs (0.08%) make HFT approach non-viable

We want to build what the **data supports**, not force the data into a pre-conceived strategy type.
