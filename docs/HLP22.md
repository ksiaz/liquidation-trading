BACKTESTING INFRASTRUCTURE
Replay, Validation, and Parameter Optimization

Backtesting is not about finding profitable parameters.
Backtesting is about validating determinism and strategy correctness.

This document defines:
  - How to replay historical data
  - How to validate deterministic execution
  - How to detect regressions
  - How to optimize parameters safely

Critical principle: Backtest results must match forward testing exactly.

---

PART 1: BACKTEST OBJECTIVES

Objective 1: Validate Determinism

Same inputs → Same outputs (always)

Test:
  - Run strategy on historical data
  - Run again on same data
  - Results must be IDENTICAL

If not identical:
  - System is non-deterministic
  - Do NOT deploy to production
  - Find and fix source of randomness

---

Objective 2: Validate Strategy Logic

Does the strategy behave as specified?

Test:
  - Manual scenarios with known outcomes
  - Edge cases (invalidation conditions)
  - Regime transitions

Compare:
  - Actual behavior vs specification (HLP10)

---

Objective 3: Performance Estimation

What's the expected performance?

Metrics:
  - Win rate
  - Average PnL per trade
  - Sharpe ratio
  - Max drawdown
  - Trade frequency

Use this to:
  - Set realistic expectations
  - Detect anomalies in live trading
  - Validate strategy improvements

---

Objective 4: Parameter Optimization

Find optimal parameters (with extreme caution)

Parameters to test:
  - Entry thresholds
  - Stop distances
  - Target multiples
  - Match score minimums

Critical: Avoid overfitting (see Part 6)

---

Objective 5: Regression Detection

Detect if changes break strategies

Process:
  1. Establish baseline performance
  2. Make code changes
  3. Re-run backtest
  4. Compare to baseline

Alert if:
  - Win rate drops > 5%
  - Sharpe drops > 20%
  - Trade count changes significantly

---

PART 2: DATA REQUIREMENTS

Source Data

From cold storage (HLP11):
  - Orderbook snapshots (every 100ms)
  - Trade ticks
  - Funding rate updates
  - OI updates
  - Mark price updates

From node logs:
  - WebSocket messages (raw)
  - Sequence numbers
  - Timestamps (nanosecond precision)

From wallet tracking:
  - Wallet position changes
  - Classification data

Data Completeness:

Required:
  - No gaps in sequence numbers
  - No missing timestamps
  - Complete orderbook snapshots

Validate before backtest:
  - Check for gaps
  - Verify timestamp order
  - Ensure data quality

If data incomplete:
  - Flag backtest as "incomplete"
  - Document missing ranges
  - Use only complete segments

---

Data Time Range

Minimum for validation:
  - 7 days of data
  - Multiple regime cycles
  - 20+ liquidation events

Ideal for optimization:
  - 90 days of data
  - Multiple market conditions
  - 100+ trades

Out-of-Sample Validation:

Split data:
  - In-sample: First 60% (for optimization)
  - Out-of-sample: Last 40% (for validation)

Never use out-of-sample data for parameter tuning.

---

PART 3: REPLAY MECHANISM

Replay Architecture

Components:

1. Data Reader
   - Reads from cold storage
   - Maintains sequence order
   - Emits messages in timestamp order

2. Simulated Node Client
   - Replaces live node connection
   - Feeds data to state builder
   - Same interface as live client

3. State Builder (unchanged)
   - Processes messages
   - Updates hot state
   - No modifications needed

4. Strategies (unchanged)
   - React to state changes
   - Generate trade signals
   - No modifications needed

5. Simulated Execution
   - Replaces live execution service
   - Simulates fills instantly
   - Records all trade details

---

Replay Flow

Step 1: Initialize System

Load configuration:
  - Same as production
  - Same strategy parameters
  - Same regime thresholds

Initialize components:
  - State builder (fresh state)
  - Strategies (DISABLED initially)
  - Simulated execution service

Step 2: Stream Data

for message in historical_data:
  
  # Respect timing (optional)
  if realtime_mode:
    wait_until(message.timestamp)
  
  # Feed to state builder
  state_builder.process_message(message)
  
  # State builder updates hot state
  # Strategies react to state changes
  # Trades are simulated

Step 3: Collect Results

Track all trades:
  - Entry time, price, size
  - Exit time, price, reason
  - PnL
  - Strategy that generated it

Calculate metrics:
  - Win rate, Sharpe, drawdown
  - Per-strategy breakdown

---

Time Handling

Two modes:

Mode 1: Fast Forward (Default)
  - Process messages as fast as possible
  - Ignore real timing
  - Complete backtest in minutes

Mode 2: Real-Time
  - Preserve message timing
  - Useful for debugging timing issues
  - Replay takes same time as original

Recommendation: Use fast-forward for most tests

---

PART 4: SIMULATED EXECUTION

Fill Simulation

Assumption: Market orders fill immediately

For MARKET order:
  fill_price = current_market_price
  slippage = random(0, max_slippage)  # NO! Don't do this
  
Better approach:
  fill_price = simulate_from_orderbook()

Orderbook-Based Fill Simulation:

for market BUY order:
  1. Walk up the ask side of orderbook
  2. Accumulate liquidity until order filled
  3. Calculate weighted average fill price

Example:

Order: Buy 0.5 BTC (market)

Orderbook:
  Ask: 0.2 BTC @ $50,000
  Ask: 0.3 BTC @ $50,005
  Ask: 0.5 BTC @ $50,010

Fill:
  0.2 BTC @ $50,000 = $10,000
  0.3 BTC @ $50,005 = $15,001.50
  Total: 0.5 BTC for $25,001.50
  Average: $50,003

This gives realistic slippage estimation.

---

Stop and Target Fills:

Assumption: Fills occur when price reaches level

For STOP order at $49,500:
  - Monitor market price
  - When price <= $49,500:
    * Trigger stop
    * Simulate market order fill
    * Use orderbook at trigger moment

For TARGET limit order at $50,200:
  - Monitor market price
  - When price >= $50,200:
    * Fill at limit price (optimistic)
    * Or use orderbook (conservative)

Conservative approach recommended.

---

Partial Fills

Decision: Simulate or assume full fills?

Option 1: Assume Full Fills
  - Simpler implementation
  - Optimistic (may overstate performance)

Option 2: Simulate Partial Fills
  - Check orderbook depth
  - If insufficient liquidity: Partial fill
  - More realistic

Recommendation: Option 1 initially, add Option 2 if needed

---

PART 5: DETERMINISM VALIDATION

Replay Test

Test:

def test_determinism():
  # Run 1
  results_1 = run_backtest(data, config)
  
  # Run 2 (same data, same config)
  results_2 = run_backtest(data, config)
  
  # Compare
  assert results_1.trades == results_2.trades
  assert results_1.pnl == results_2.pnl
  assert results_1.final_state == results_2.final_state

If this fails:
  - System is non-deterministic
  - Find sources of randomness:
    * Random number generators
    * System time (use event timestamps)
    * Hash iteration order (use sorted)
    * Floating point rounding (use fixed-point)

Fix ALL sources of non-determinism.

---

Checkpointing

Create checkpoints during replay:

checkpoints = []

for i, message in enumerate(historical_data):
  process_message(message)
  
  if i % 1000 == 0:
    checkpoint = capture_full_state()
    checkpoints.append(checkpoint)

Validation:

Replay from checkpoint:
  - Load checkpoint state
  - Continue from checkpoint
  - Verify same results

This tests:
  - State serialization
  - State restoration
  - No hidden dependencies

---

PART 6: PARAMETER OPTIMIZATION

Warning: Danger of Overfitting

Overfitting occurs when:
  - Parameters tuned to historical data
  - Perform well in backtest
  - Fail in live trading

How to avoid:

1. Minimize parameters
   - Fewer parameters = less overfitting risk
   - Each parameter must have clear rationale

2. Use out-of-sample validation
   - Never touch out-of-sample data during optimization
   - Final validation on unseen data

3. Avoid data snooping
   - Don't look at historical patterns then create strategies
   - Strategy logic should derive from market mechanics

4. Walk-forward testing
   - Optimize on period 1
   - Test on period 2
   - Optimize on period 2
   - Test on period 3
   - Etc.

---

Grid Search

For each parameter combination:

parameter_grid = {
  "oi_threshold": [1.1, 1.15, 1.2, 1.25],
  "funding_threshold": [0.01, 0.015, 0.02, 0.025],
  "confidence_min": [0.6, 0.7, 0.8],
}

results = []

for oi in parameter_grid["oi_threshold"]:
  for funding in parameter_grid["funding_threshold"]:
    for match_score in parameter_grid["match_score_min"]:

      config = {
        "oi_threshold": oi,
        "funding_threshold": funding,
        "match_score_min": match_score,
      }
      
      result = run_backtest(in_sample_data, config)
      results.append((config, result))

# Find best on in-sample
best_config = max(results, key=lambda x: x[1].sharpe)

# Validate on out-of-sample
oos_result = run_backtest(out_of_sample_data, best_config)

If out-of-sample performance << in-sample:
  - Overfitted
  - Try fewer parameters or wider ranges

---

Optimization Metrics

Don't optimize for PnL alone.

Better metrics:

Sharpe Ratio:
  - Risk-adjusted return
  - Penalizes volatility

Profit Factor:
  - Total wins / total losses
  - Must be > 1

Max Drawdown:
  - Worst peak-to-trough decline
  - Lower is better

Trade Count:
  - Too few: Insufficient data
  - Too many: May be noise

Combined Score:

score = sharpe * sqrt(trade_count / 100)

This balances quality and quantity.

---

PART 7: PERFORMANCE METRICS

Metrics to Track:

Total Trades:
  - Count of completed trades

Win Rate:
  - Wins / total trades

Total PnL:
  - Sum of all PnL

Average Win:
  - Mean of winning trades

Average Loss:
  - Mean of losing trades

Win/Loss Ratio:
  - Average win / average loss

Profit Factor:
  - Total wins / total losses

Sharpe Ratio:
  - (Mean return) / (Std dev return)

Max Drawdown:
  - Worst peak-to-trough decline

Average Hold Time:
  - Mean time in position

Trade Frequency:
  - Trades per day

---

Equity Curve

Track capital over time:

equity_curve = []
capital = initial_capital

for trade in trades:
  capital += trade.pnl
  equity_curve.append({
    "timestamp": trade.exit_time,
    "capital": capital,
  })

Visualize:
  - Plot capital vs time
  - Identify drawdown periods
  - Detect regime dependencies

---

Per-Strategy Breakdown

Track metrics separately per strategy:

strategy_metrics = {
  "geometry": {...},
  "kinematics": {...},
  "cascade": {...},
}

Identify:
  - Which strategies contribute most PnL
  - Which have highest Sharpe
  - Which trade most frequently

---

PART 8: REPORTING

Backtest Report

Include:

1. Configuration
   - Time range
   - Initial capital
   - Strategy parameters
   - Regime thresholds

2. Summary Metrics
   - Total trades
   - Win rate
   - Total PnL
   - Sharpe ratio
   - Max drawdown

3. Equity Curve
   - Plot capital over time

4. Trade Distribution
   - Histogram of PnL per trade
   - Win vs loss distribution

5. Drawdown Analysis
   - Drawdown periods
   - Recovery times

6. Per-Strategy Breakdown

7. Top Trades
   - Largest wins
   - Largest losses

8. Warnings
   - Data gaps
   - Incomplete data
   - Low sample size

---

Comparison Reports

Compare two backtest runs:

Scenario A: Baseline parameters
Scenario B: Modified parameters

Report:
  - Side-by-side metrics
  - Delta (B - A)
  - Statistical significance

Helps evaluate if changes improve performance.

---

PART 9: REGRESSION TESTING

Establish Baseline

After strategy validation:

baseline_results = run_backtest(reference_data, production_config)

Store:
  - Baseline metrics
  - Baseline trades (full details)
  - Date established

---

Regression Detection

After code changes:

new_results = run_backtest(reference_data, production_config)

Compare:
  - new_results vs baseline_results

Tolerances:
  - Win rate: ± 2%
  - Sharpe: ± 10%
  - Trade count: ± 5%
  - PnL: ± 10%

If outside tolerance:
  - Investigation required
  - Code change may have broken something

Exceptions:
  - Intentional strategy improvements
  - Bug fixes (may change results legitimately)

---

Continuous Regression Testing

Run backtest on every commit:

git push → trigger backtest → compare to baseline

If regression detected:
  - Block merge
  - Require investigation

This prevents accidental strategy degradation.

---

PART 10: FAILURE MODES

Failure Mode 1: Data Mismatch

Backtest uses different data than live system

Prevention:
  - Use exact same data pipeline
  - Same normalization
  - Same validation

Validation:
  - Spot-check backtest data vs live logs
  - Ensure timestamps align

---

Failure Mode 2: Lookahead Bias

Using future data in past decisions

Examples:
  - Using EOD close in intraday signal
  - Peeking at future orderbook
  - Synchronization issues

Prevention:
  - Strict timestamp ordering
  - No data access before timestamp
  - Code review for lookahead

---

Failure Mode 3: Survivorship Bias

Only testing on symbols that still exist

Impact:
  - Overstates performance
  - Missing delisted symbols

Prevention:
  - Include all historically traded symbols
  - Track symbol lifecycle

---

Failure Mode 4: Optimistic Fills

Assuming fills that wouldn't happen

Examples:
  - Limit orders always fill
  - No slippage
  - Instant execution

Prevention:
  - Conservative fill simulation
  - Orderbook-based slippage
  - Model execution delays

---

PART 11: IMPLEMENTATION ARCHITECTURE

Components:

1. Data Loader
   - Reads cold storage
   - Maintains sequence order
   - Emits messages

2. Replay Engine
   - Drives simulation
   - Manages timing (fast-forward vs real-time)
   - Coordinates components

3. Simulated Exchange
   - Simulates order matching
   - Returns fills
   - Maintains orderbook state

4. Metrics Collector
   - Tracks all trades
   - Calculates performance metrics
   - Generates reports

5. State Validator
   - Captures checkpoints
   - Validates determinism
   - Detects regressions

---

Interfaces:

Same as production:
  - State builder
  - Strategies
  - Event registry

This ensures:
  - No code changes needed
  - Same behavior as live
  - Easy to switch between backtest and live

---

PART 12: TESTING THE BACKTESTER

Meta-Testing:

The backtester itself needs testing.

Test 1: Known Outcome

Create synthetic data:
  - Simple price pattern
  - Known entry/exit points
  - Calculable PnL

Run backtest:
  - Verify correct trades detected
  - Verify correct PnL calculated

---

Test 2: Determinism

Run same backtest twice:
  - Results must be identical
  - Verify hash of all trades matches

---

Test 3: Fill Simulation

Create orderbook scenario:
  - Known liquidity distribution
  - Known order size

Verify:
  - Slippage calculated correctly
  - Fill price matches expectation

---

PART 13: PERFORMANCE CONSIDERATIONS

Backtest Speed:

Target: Process 24 hours of data in < 5 minutes

Optimization:
  - Parallel processing (multiple symbols)
  - Efficient data structures
  - Minimize I/O

Monitoring:
  - Track processing rate (events/sec)
  - Identify bottlenecks

---

Storage Requirements:

90 days of data:
  - Orderbook snapshots: ~100GB
  - Trade ticks: ~10GB
  - Other data: ~5GB
  Total: ~115GB

Compression:
  - Use Parquet or similar
  - Can reduce by 80-90%

---

PART 14: IMPLEMENTATION CHECKLIST

[ ] Implement data loader
[ ] Implement replay engine
[ ] Implement simulated exchange
[ ] Implement fill simulation (orderbook-based)
[ ] Implement metrics collection
[ ] Build equity curve visualization
[ ] Implement regression testing
[ ] Write backtest report generator
[ ] Test determinism
[ ] Test on known outcomes
[ ] Optimize for performance
[ ] Document usage

---

PART 15: USAGE WORKFLOW

Workflow: Validate New Strategy

1. Implement strategy logic
2. Write unit tests (state machine)
3. Run backtest on 30 days data
4. Review metrics:
   - Is win rate > 55%?
   - Is Sharpe > 1.5?
   - Is max drawdown < 20%?
5. If acceptable:
   - Run out-of-sample validation
   - If still good: Deploy to paper trading
6. If not acceptable:
   - Revise strategy
   - Repeat

---

Workflow: Optimize Parameters

1. Define parameter grid
2. Run grid search on in-sample data (60%)
3. Find best parameters by Sharpe
4. Validate on out-of-sample data (40%)
5. If out-of-sample performance acceptable:
   - Use these parameters
6. If degraded:
   - Overfitted, use wider ranges
   - Or use baseline parameters

---

Workflow: Detect Regression

1. Make code changes
2. Run backtest on reference data
3. Compare to baseline:
   - Win rate delta
   - Sharpe delta
   - Trade count delta
4. If within tolerance:
   - Deploy changes
5. If outside tolerance:
   - Investigate why
   - Fix or revert changes

---

BOTTOM LINE

Backtesting is for validation, not discovery.

Use backtesting to:
  - Verify determinism
  - Validate strategy logic
  - Detect regressions
  - Estimate performance

Do NOT use backtesting to:
  - Mine for patterns
  - Overfit parameters
  - Justify wishful thinking

Rules:

1. Backtest must be deterministic
   - Same inputs = same outputs (always)

2. Backtest must use production code
   - No separate backtest implementation
   - Same strategies, same logic

3. Backtest must be conservative
   - Realistic slippage
   - Conservative fills
   - Include all costs

4. Backtest must validate out-of-sample
   - Never trust in-sample results alone
   - Always test on unseen data

5. Backtest results are NOT guarantees
   - Past performance ≠ future results
   - Use as validation, not prediction

Build backtesting infrastructure early.
Use it continuously.
Trust it only when it's deterministic and validated.
