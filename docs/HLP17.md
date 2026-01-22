CAPITAL MANAGEMENT & RISK CONTROLS
Position Sizing, Risk Limits, and Drawdown Protection

Capital management is not optional.
It is the difference between:
  - Short-term profit and long-term survival
  - Growth and blowup
  - Discipline and gambling

This document defines exact rules for:
  - How much capital per trade
  - Maximum risk exposure
  - Drawdown triggers
  - Position sizing adjustments

These are hard constraints, not guidelines.

---

PART 1: POSITION SIZING FUNDAMENTALS

Core Principle:

Never risk more than you can afford to lose.
Size positions based on:
  - Stop distance
  - Win probability
  - Capital base
  - Market volatility

---

Position Sizing Method 1: Fixed Fractional (Base Case)

Formula:

position_size = (capital × risk_per_trade) / stop_distance_dollars

Where:
  capital: Current account value
  risk_per_trade: 1% (default, max 2%)
  stop_distance_dollars: Entry - stop price (in dollars)

Example:

Capital: $10,000
Risk per trade: 1% = $100
Entry: $50,000 (BTC)
Stop: $49,500
Stop distance: $500

Position size = $10,000 × 0.01 / $500 = $100 / $500 = 0.2 BTC

Verify: If stop hits, loss = 0.2 BTC × $500 = $100 ✓

Rules:
  - Never exceed 2% risk per trade
  - Use 1% as default
  - Use 0.5% after consecutive losses (see drawdown controls)

---

Position Sizing Method 2: Volatility-Adjusted

Formula:

base_size = (capital × risk_per_trade) / stop_distance_dollars
volatility_scalar = baseline_volatility / current_volatility
adjusted_size = base_size × volatility_scalar

Where:
  baseline_volatility: 30-day ATR
  current_volatility: Last 24h ATR

Rationale:

When volatility is high:
  - Stops hit more often
  - Reduce size to same dollar risk

When volatility is low:
  - More predictable
  - Increase size (up to limit)

Constraints:
  - Max adjustment: 2x (don't go crazy in low vol)
  - Min adjustment: 0.5x (always maintain minimum)

---

Position Sizing Method 3: Event-Specific Sizing

Different event types have different risk profiles.

**HYPOTHESIS (requires validation):**
Event type correlates with win rate. Adjust sizing accordingly.

Size Multipliers by Event Type:

Liquidation Cascade:
  - Base multiplier: 1.0x
  - Use standard sizing until validated

Failed Hunt:
  - Base multiplier: 1.0x
  - Use standard sizing until validated

Funding Snapback:
  - Base multiplier: 1.0x
  - Use standard sizing until validated

Inventory Distribution:
  - Base multiplier: 0.75x
  - Longer hold time, more uncertainty

Final Formula:

position_size = base_size × event_multiplier × volatility_scalar

Never exceed absolute maximum (see risk limits).

NOTE: Do not adjust sizing based on "confidence" scores until:
1. Historical data validates that higher-threshold events have higher win rates
2. Sample size > 100 trades per event type
3. Out-of-sample testing confirms relationship

---

PART 2: RISK LIMITS (HARD CAPS)

Risk Limit 1: Maximum Position Size Per Symbol

Max position = 5% of total capital (dollar value)

Example:
  Capital: $10,000
  Max position in BTC: $500 worth
  
If position would exceed this:
  - Reject trade
  - Log rejection reason
  
Rationale:
  - Prevents concentration risk
  - Limits impact of adverse move

---

Risk Limit 2: Maximum Aggregate Exposure

Max aggregate exposure = 10% of total capital

Sum of all open positions (dollar value) cannot exceed 10%.

Example:
  Capital: $10,000
  Open positions:
    - BTC: $400
    - ETH: $300
    - Total: $700 (7% of capital) ✓ OK
  
  New position request: SOL $500
  New total: $1,200 (12%) ✗ REJECT

Rationale:
  - Prevents over-leveraging
  - Maintains dry powder
  - Preserves capital for best opportunities

---

Risk Limit 3: Maximum Correlated Exposure

Assets with correlation > 0.7 count as same exposure.

Example:
  BTC and ETH correlation: 0.85
  BTC position: $400
  ETH position: $300
  Effective correlated exposure: $700
  
  Max correlated exposure: 7% of capital
  
Check before new position:
  - Calculate correlation with existing positions
  - Sum correlated exposures
  - Reject if exceeds limit

Rationale:
  - Correlated assets move together
  - Diversification must be real
  - Prevents illusion of diversification

---

Risk Limit 4: Leverage Limit

No leverage allowed (1x only).

All positions must be fully collateralized.

Rationale:
  - Liquidation trading is already risky
  - Leverage amplifies losses
  - Need buffer for unexpected moves

Exception:
  - If Hyperliquid requires minimum leverage:
    * Use absolute minimum (e.g., 1.1x)
    * Never exceed 2x
    
---

PART 3: DRAWDOWN CONTROLS

Drawdown = Decline from peak equity

Types of Drawdown:

Daily drawdown: Today's low vs today's high
Weekly drawdown: This week's low vs this week's high
Overall drawdown: Current vs all-time high

---

Drawdown Control 1: Daily Loss Limit

Rule:

If daily loss > 3% of capital:
  - Stop all trading immediately
  - Close all open positions
  - Enter DAILY_COOLDOWN mode
  - Resume tomorrow (after reset)

Example:
  Capital: $10,000
  Daily loss limit: $300
  
  Losses so far: $250
  New position would risk $100
  If it loses fully: $350 total
  
  Reject: Would exceed daily limit

Logging:
  - Track daily PnL continuously
  - Alert at -2% (warning)
  - Hard stop at -3%

---

Drawdown Control 2: Weekly Loss Limit

Rule:

If weekly loss > 7% of capital:
  - Stop all trading for rest of week
  - Close all open positions
  - Enter WEEKLY_COOLDOWN mode
  - Resume next Monday

Example:
  Capital: $10,000
  Weekly loss limit: $700
  
  Monday-Thursday losses: $650
  Reject all Friday trades (approaching limit)

Rationale:
  - Prevents blow-through in bad week
  - Forces time away from market
  - Allows reset psychologically

---

Drawdown Control 3: Consecutive Loss Limit

Rule:

After 5 consecutive losses:
  - Reduce position size to 50%
  - Enter REDUCED_RISK mode
  - Require 2 consecutive wins to exit

After 10 consecutive losses:
  - Stop trading immediately
  - Manual review required
  - Identify systematic issue

Rationale:
  - Consecutive losses indicate:
    * Strategy broken
    * Market regime changed
    * System malfunction
  - Cutting size limits damage
  - Forced pause prevents revenge trading

---

Drawdown Control 4: Maximum Overall Drawdown

Rule:

If account drops > 25% from all-time high:
  - Enter MAXIMUM_DRAWDOWN mode
  - Position sizes reduced to 25%
  - Only trades meeting all threshold criteria allowed
  - Slow recovery protocol

Recovery Protocol:

Position sizing remains reduced until:
  - Account recovers to > 15% drawdown
  - Then gradually increase sizing:
    * Every 5% recovery → +25% sizing
    * At 5% drawdown → full sizing resumed

Rationale:
  - Large drawdowns are psychological
  - Recovery requires smaller positions
  - Don't dig deeper hole

---

PART 4: POSITION HEAT MANAGEMENT

How many positions simultaneously?

Default: Maximum 1 open position at a time

Rationale:
  - Simplifies management
  - Prevents correlation blowup
  - Clear focus

Advanced (After Proven Performance):

Maximum 3 concurrent positions IF:
  - Correlation < 0.5 between all pairs
  - Each position < 3% of capital
  - Aggregate exposure < 10%
  - All positions have stops
  
Monitoring:

Portfolio heat = Σ(position_size × stop_distance_pct)

If portfolio heat > 10%:
  - Scale down existing positions, or
  - Reject new positions

---

PART 5: DYNAMIC POSITION SIZING ADJUSTMENT

Increase Sizing After Wins:

After 3 consecutive wins:
  - Increase risk per trade: 1% → 1.25%
  - Max increase: 1.5%

After 5 consecutive wins:
  - Increase risk per trade: 1.25% → 1.5%

Rationale:
  - Strategies are working
  - Market conditions favorable
  - Compound winnings

Constraints:
  - Never exceed 2% per trade
  - Daily/weekly limits still apply
  - Revert to 1% after any loss

---

Decrease Sizing After Losses:

After 2 consecutive losses:
  - Decrease risk per trade: 1% → 0.75%

After 4 consecutive losses:
  - Decrease risk per trade: 0.75% → 0.5%

After 6 consecutive losses:
  - Stop trading (see drawdown controls)

Rationale:
  - Limit bleeding
  - Preserve capital
  - Force reassessment

Recovery:
  - Require 2 wins to move up sizing tier
  - Gradual return to baseline

---

PART 6: REGIME-BASED SIZING

Regime affects sizing:

SIDEWAYS Regime:
  - Baseline sizing (1%)
  - Standard thresholds apply

EXPANSION Regime:
  - Reduced sizing (0.75%)
  - More volatility, wider stops
  - Preserve capital

DISABLED Regime:
  - No trading
  - Regime unclear, stay out

Implementation:

base_risk_pct = 0.01  # 1%
regime_scalar = {
  "SIDEWAYS": 1.0,
  "EXPANSION": 0.75,
  "DISABLED": 0.0
}

risk_per_trade = base_risk_pct × regime_scalar[current_regime]

---

PART 7: KELLY CRITERION (OPTIONAL ADVANCED)

Kelly Formula:

f = (p × b - q) / b

Where:
  f: Fraction of capital to bet
  p: Win probability
  q: Loss probability (1 - p)
  b: Win/loss ratio (average win / average loss)

Example:
  Win rate: 60% (p = 0.6)
  Avg win: $200
  Avg loss: $100
  b = 200/100 = 2
  
  f = (0.6 × 2 - 0.4) / 2
    = (1.2 - 0.4) / 2
    = 0.8 / 2
    = 0.4 (40% of capital)

But this is INSANE for crypto.

Practical Application:

Use Fractional Kelly:
  - Half Kelly: f / 2 = 20%
  - Quarter Kelly: f / 4 = 10%
  - Tenth Kelly: f / 10 = 4%

Recommendation:
  - Use Tenth Kelly as absolute maximum
  - Only after 100+ trades to validate stats
  - Still respect hard caps (5% per position max)

Rationale:
  - Kelly assumes perfect knowledge of p and b
  - Real-world estimates are noisy
  - Fractional Kelly prevents over-betting

---

PART 8: EMERGENCY CAPITAL PRESERVATION

Emergency Triggers:

Trigger 1: Flash crash detected
  - All positions to 25% size immediately
  - Tighten all stops by 50%

Trigger 2: Exchange issues
  - Close all positions if possible
  - If cannot close: Hedge on secondary exchange

Trigger 3: System malfunction
  - Close all positions at market
  - Hard shutdown

Manual Override:

Operator can:
  - Force position closure
  - Override size limits (with justification)
  - Halt trading
  - Modify risk parameters

All overrides must be logged with reason.

---

PART 9: CAPITAL ALLOCATION ACROSS STRATEGIES

If running multiple strategies:

Option 1: Equal Allocation

Each strategy gets equal share of capital:
  - 3 strategies → 33% each
  - 2 strategies → 50% each

Option 2: Performance-Based

Allocate based on Sharpe ratio:
  - Strategy A Sharpe: 2.0
  - Strategy B Sharpe: 1.0
  - Strategy C Sharpe: 1.0
  
  Total: 4.0
  
  Allocation:
    - Strategy A: 50% (2.0 / 4.0)
    - Strategy B: 25%
    - Strategy C: 25%

Rebalance: Monthly

Option 3: Risk Parity

Allocate inversely to volatility:
  - Lower volatility strategy → more capital
  - Higher volatility strategy → less capital

Target: Equal risk contribution per strategy

Recommended: Start with Option 1, migrate to Option 2 after data

---

PART 10: MONITORING & REPORTING

Track Daily:

Daily PnL
Daily win rate
Daily Sharpe
Largest win
Largest loss
Current drawdown
Risk utilization (actual vs allowed)

Track Weekly:

Weekly PnL
Weekly win rate
Average win vs average loss
Consecutive wins/losses
Drawdown from weekly peak

Track Monthly:

Monthly PnL
Total trades
Overall win rate
Sharpe ratio
Max drawdown
Recovery time from drawdowns
Capital growth rate

Alerts:

Alert if:
  - Approaching daily loss limit (-2%)
  - Weekly losses > 5%
  - Consecutive losses > 3
  - Drawdown > 15%
  - Risk utilization > 80%

---

PART 11: RISK METRICS FORMULAS

Sharpe Ratio:

sharpe = (mean_return - risk_free_rate) / std_dev_return

Assume risk_free_rate = 0 for crypto.

sharpe = mean_return / std_dev_return

**HYPOTHESIS:** Target Sharpe > 1.5 is achievable. Validate with live data.

Max Drawdown:

max_dd = (trough_value - peak_value) / peak_value

Track both:
  - Current drawdown (from recent peak)
  - Historical max drawdown (worst ever)

Win Rate:

win_rate = wins / total_trades

**HYPOTHESIS:** Target win rate > 55% is achievable. Validate with live data.

Profit Factor:

profit_factor = total_wins / total_losses

Target: > 1.5

Expected Value Per Trade:

ev = (win_rate × avg_win) - (loss_rate × avg_loss)

Must be positive.

---

PART 12: POSITION SIZING DECISION TREE

Before entering any trade:

1. Calculate position size:
   ✓ Use fixed fractional method
   ✓ Apply volatility adjustment
   ✓ Apply event multiplier (1.0x default until validated)

2. Check against limits:
   ✓ Position size < 5% of capital?
   ✓ Aggregate exposure < 10%?
   ✓ Correlated exposure < 7%?
   ✓ Portfolio heat < 10%?

3. Check drawdown:
   ✓ Daily loss < 3%?
   ✓ Weekly loss < 7%?
   ✓ Consecutive losses < 5?
   ✓ Overall drawdown < 25%?

4. Apply regime adjustment:
   ✓ Regime allows trading?
   ✓ Regime scalar applied?

5. Apply dynamic adjustment:
   ✓ Recent win/loss streak considered?
   ✓ Size adjusted accordingly?

If ALL checks pass:
  → Execute trade

If ANY check fails:
  → Reject trade
  → Log rejection reason

---

PART 13: TESTING CAPITAL MANAGEMENT

Simulation Tests:

Test 1: Daily Loss Limit
  - Simulate 5 consecutive losses
  - Verify trading stops at -3%
  - Verify cooldown activates

Test 2: Position Size Calculation
  - Given: capital, stop distance, risk%
  - Verify correct size calculated
  - Verify limits enforced

Test 3: Drawdown Recovery
  - Simulate 25% drawdown
  - Verify sizing reduces
  - Verify gradual recovery

Test 4: Concurrent Position Limits
  - Add positions until limit hit
  - Verify rejection of excess
  - Verify correlation check works

---

PART 14: CAPITAL MANAGEMENT CONFIGURATION

Configurable Parameters:

risk_per_trade_default: 0.01 (1%)
risk_per_trade_max: 0.02 (2%)
max_position_size_pct: 0.05 (5%)
max_aggregate_exposure: 0.10 (10%)
max_correlation_exposure: 0.07 (7%)
daily_loss_limit: 0.03 (3%)
weekly_loss_limit: 0.07 (7%)
max_drawdown: 0.25 (25%)
consecutive_loss_limit: 5
max_concurrent_positions: 1
regime_scalars: {"SIDEWAYS": 1.0, "EXPANSION": 0.75}

Storage:
  - Config file (YAML)
  - Version controlled
  - Hot-reload capable

Changes:
  - Require justification
  - Logged with timestamp
  - Auditable

---

IMPLEMENTATION CHECKLIST

[ ] Implement position sizing calculator
[ ] Implement risk limit checks
[ ] Implement drawdown tracking
[ ] Implement dynamic sizing adjustment
[ ] Implement capital allocation logic
[ ] Build risk metrics dashboard
[ ] Add risk alerts
[ ] Write capital management tests
[ ] Create configuration system
[ ] Document all parameters

---

BOTTOM LINE

Capital management is NOT:
  - Guessing how much to trade
  - "Whatever feels right"
  - Maximizing position size

Capital management IS:
  - Mathematical sizing
  - Hard risk limits
  - Drawdown protection
  - Survival first, profits second

The goal is not to make maximum money per trade.
The goal is to survive long enough to compound.

Risk management done right:
  - Protects against blowup
  - Allows compounding
  - Enforces discipline
  - Enables scaling

Without capital management:
  - One bad trade can wipe you out
  - Revenge trading destroys accounts
  - No systematic growth

Position sizing is the difference between:
  - Professional trading
  - Gambling

Size correctly or don't trade at all.
