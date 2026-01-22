MONITORING & ALERTING
Operational Visibility for Production Trading

You cannot manage what you cannot measure.
You cannot fix what you cannot see.

This document defines:
  - What metrics to track
  - When to alert
  - How to visualize system health
  - Debugging workflows

Goal: Know the system's state at all times.

---

PART 1: METRIC CATEGORIES

Four categories of metrics:

1. Health Metrics
   - Is the system operating correctly?
   - Are components responsive?
   - Is data fresh?

2. Performance Metrics
   - Is trading profitable?
   - What's the win rate?
   - What's the risk-adjusted return?

3. Operational Metrics
   - Resource usage (CPU, memory, disk)
   - Latency (decision to execution)
   - Throughput (events processed)

4. Business Metrics
   - Total PnL
   - Capital deployed
   - Opportunity cost

Track all four. Different audiences care about different categories.

---

PART 2: HEALTH METRICS

Metric: Data Staleness

Definition: Age of most recent data update

data_age_ms = current_time - last_node_message_timestamp

Thresholds:
  - Normal: < 500ms
  - Warning: 500ms - 1000ms
  - Critical: > 1000ms

Alert: If critical for > 5 seconds

---

Metric: Component Heartbeats

Track each component separately:

components = [
  "node_client",
  "state_builder", 
  "regime_controller",
  "strategy_geometry",
  "strategy_kinematics",
  "strategy_cascade",
  "execution_service",
  "wallet_tracker",
]

For each:
  last_heartbeat_time: timestamp
  heartbeat_interval: 1 second
  
Alert: If heartbeat_age > 3 seconds

---

Metric: Connection Status

Track:
  - WebSocket connection state (CONNECTED, DISCONNECTED, RECONNECTING)
  - Last successful message time
  - Reconnection attempt count

Alert:
  - If DISCONNECTED for > 10 seconds
  - If reconnection attempts > 5

---

Metric: Event Registry Health

Track:
  - Active events count
  - Stale events count (lifecycle state = EXPIRED)
  - Event processing rate

Alert:
  - If active_events > 100 (potential memory leak)
  - If stale_events > 50 (cleanup not running)

---

Metric: Position Consistency

Check every second:

internal_positions = position_manager.get_all()
exchange_positions = exchange_api.get_positions()

if internal != exchange:
  alert("Position mismatch detected")

Track:
  - Mismatch count (should be 0)
  - Last reconciliation time

Alert: If any mismatch detected

---

Metric: Stop Order Status

For each open position:
  - Verify stop order exists
  - Verify stop price correct
  - Verify stop is active

Alert:
  - If position exists but no stop
  - If stop canceled unexpectedly

---

PART 3: PERFORMANCE METRICS

Metric: Win Rate

win_rate = wins / total_trades

Track:
  - Overall win rate
  - Per-strategy win rate
  - Rolling 20-trade win rate

Thresholds:
  - Target: > 55%
  - Warning: < 50%
  - Critical: < 40%

Alert: If rolling win rate < 40% over last 20 trades

---

Metric: PnL Tracking

Track multiple views:

Daily PnL:
  - Today's realized PnL
  - Today's unrealized PnL
  - Total

Weekly PnL:
  - This week's total
  - Week-over-week change

Monthly PnL:
  - This month's total
  - Month-over-month change

Alert:
  - If daily loss > 2% of capital
  - If weekly loss > 5% of capital

---

Metric: Sharpe Ratio

sharpe = (mean_return - risk_free_rate) / std_dev_return

Assume risk_free_rate = 0

Calculate:
  - Rolling 30-day Sharpe
  - Rolling 90-day Sharpe

Target: Sharpe > 1.5

Alert: If Sharpe < 0.5 over 30 days

---

Metric: Maximum Drawdown

Track:
  - Current drawdown (from recent peak)
  - Max historical drawdown
  - Time in drawdown
  - Recovery time from drawdowns

Alert:
  - If current drawdown > 15%
  - If in drawdown > 7 days

---

Metric: Average Win vs Average Loss

avg_win = sum(winning_trades) / win_count
avg_loss = sum(losing_trades) / loss_count
win_loss_ratio = avg_win / avg_loss

Target: > 1.5

Alert: If ratio < 1.0 (losing more per loss than winning per win)

---

Metric: Profit Factor

profit_factor = total_wins / total_losses

Target: > 1.5

Alert: If profit_factor < 1.1

---

Metric: Strategy Performance

Track per strategy:

strategy_metrics = {
  "geometry": {
    "trades": 45,
    "wins": 27,
    "win_rate": 0.60,
    "total_pnl": 1250,
    "sharpe": 1.8,
  },
  "kinematics": {
    "trades": 12,
    "wins": 8,
    "win_rate": 0.67,
    "total_pnl": 450,
    "sharpe": 2.1,
  },
  ...
}

Alert:
  - If any strategy win_rate < 0.4
  - If any strategy sharpe < 0

---

PART 4: OPERATIONAL METRICS

Metric: CPU Usage

Track:
  - Overall system CPU %
  - Per-process CPU %

Thresholds:
  - Normal: < 70%
  - Warning: 70-90%
  - Critical: > 90%

Alert: If critical for > 30 seconds

---

Metric: Memory Usage

Track:
  - Total memory used
  - Per-process memory
  - Memory growth rate

Thresholds:
  - Normal: < 75%
  - Warning: 75-85%
  - Critical: > 85%

Alert:
  - If critical
  - If memory growing > 10% per hour (potential leak)

---

Metric: Disk Usage

Track:
  - Disk space used %
  - Disk I/O rate
  - Write queue depth

Alert:
  - If disk > 90% full
  - If disk I/O > sustained limit

---

Metric: Network Latency

Track:
  - Ping to Hyperliquid node
  - API request latency
  - WebSocket message latency

Thresholds:
  - Normal: < 50ms
  - Warning: 50-100ms
  - Critical: > 100ms

Alert: If sustained high latency

---

Metric: Order Execution Latency

Track end-to-end timing:

decision_to_submission: μs
submission_to_ack: μs
ack_to_fill: μs
total: μs

Track percentiles:
  - p50 (median)
  - p95
  - p99
  - max

Targets:
  - p50 < 2ms
  - p99 < 20ms

Alert: If p99 > 50ms

---

Metric: Event Processing Rate

Track:
  - Events detected per minute
  - Events processed per minute
  - Event queue depth

Alert:
  - If queue depth growing (backlog)
  - If processing rate drops significantly

---

PART 5: BUSINESS METRICS

Metric: Total Capital

Track:
  - Starting capital
  - Current capital
  - Peak capital
  - Growth rate

Display:
  - As absolute value
  - As % change from start
  - As equity curve

---

Metric: Capital Deployed

Track:
  - % of capital in positions
  - Average position size
  - Position count

Alert: If deployed > risk limit (10%)

---

Metric: Opportunity Cost

From counterfactual tracking (HLP15):

Track:
  - Total missed PnL
  - Opportunity cost per day
  - Highest opportunity cost event

This guides optimization priorities.

---

Metric: Strategy Utilization

Track:
  - How often each strategy trades
  - Idle time per strategy
  - Regime distribution

Helps identify if strategies are under-utilized.

---

PART 6: ALERT SEVERITY LEVELS

INFO:
  - Informational only
  - No action required
  - Example: "Strategy entered trade"

WARNING:
  - Potential issue
  - Monitor closely
  - Example: "Win rate dropped to 52%"

ERROR:
  - Issue requiring attention
  - May need intervention soon
  - Example: "Data staleness 2 seconds"

CRITICAL:
  - Immediate action required
  - Trading may be compromised
  - Example: "Position mismatch detected"

EMERGENCY:
  - System safety at risk
  - Automated halt triggered
  - Example: "Circuit breaker activated"

---

PART 7: ALERT CHANNELS

Where to send alerts:

Console/Logs:
  - All severity levels
  - Always logged

Dashboard:
  - WARNING and above
  - Visual indicators

Email:
  - ERROR and above
  - Async notification

SMS/Push:
  - CRITICAL and above
  - Immediate notification

Automated Response:
  - EMERGENCY only
  - System takes protective action

---

PART 8: ALERT RULES

Rule: Data Staleness

if data_age_ms > 1000:
  for i in range(5):
    wait(1s)
    if data_age_ms <= 1000:
      return  # Recovered
  
  alert(CRITICAL, "Data stale for 5+ seconds")
  halt_trading()

---

Rule: Rapid Losses

if current_session_losses >= 3:
  alert(WARNING, "3 consecutive losses")

if current_session_losses >= 5:
  alert(ERROR, "5 consecutive losses - reducing size")
  reduce_position_sizing()

if current_session_losses >= 10:
  alert(CRITICAL, "10 consecutive losses - halting")
  halt_trading()

---

Rule: Daily Loss Limit

if daily_pnl < -capital * 0.02:
  alert(WARNING, "Daily loss at -2%")

if daily_pnl < -capital * 0.03:
  alert(CRITICAL, "Daily loss limit hit -3%")
  close_all_positions()
  halt_trading()

---

Rule: Position Mismatch

if internal_position != exchange_position:
  alert(EMERGENCY, "Position mismatch detected")
  halt_new_trades()
  reconcile_positions()

---

Rule: Stop Order Missing

for position in open_positions:
  if not has_active_stop(position):
    alert(EMERGENCY, f"No stop for position {position.symbol}")
    close_position_at_market(position)

---

Rule: Component Failure

if component_heartbeat_age > 10s:
  alert(CRITICAL, f"Component {component} not responding")
  attempt_restart(component)

if component_restart_fails:
  alert(EMERGENCY, f"Component {component} restart failed")
  halt_trading()

---

PART 9: DASHBOARDS

Dashboard 1: Real-Time Trading Status

Display:
  - Current time
  - System status (ACTIVE, DEGRADED, HALTED)
  - Connection status
  - Data age
  - Current regime
  - Active events count
  - Open positions count
  - Today's PnL

Update frequency: 1 second

---

Dashboard 2: Position Overview

For each open position:
  - Symbol
  - Direction (LONG/SHORT)
  - Entry price
  - Current price
  - Size
  - Unrealized PnL
  - Stop price
  - Target price
  - Time in position

Update frequency: 1 second

---

Dashboard 3: Performance Summary

Display:
  - Total trades (today, week, month)
  - Win rate (today, week, month)
  - Total PnL (today, week, month)
  - Sharpe ratio (30-day)
  - Max drawdown (current, historical)
  - Largest win
  - Largest loss
  - Average hold time

Update frequency: 5 seconds

---

Dashboard 4: Strategy Breakdown

For each strategy:
  - Current state
  - Trades today
  - Win rate
  - PnL contribution
  - Last trade time
  - Active setups count

Update frequency: 5 seconds

---

Dashboard 5: System Health

Display:
  - CPU usage %
  - Memory usage %
  - Disk usage %
  - Network latency
  - Event processing rate
  - Order execution latency (p50, p99)
  - Component heartbeats (green/red indicators)

Update frequency: 1 second

---

Dashboard 6: Error Log

Display recent errors:
  - Timestamp
  - Severity
  - Component
  - Error message
  - Count (if repeated)

Keep last 100 errors visible

---

PART 10: LATENCY PROFILING

Detailed breakdown of execution latency:

Stage 1: Strategy Decision
  - Measure: Time from event emission to strategy decision
  - Target: < 100μs

Stage 2: Risk Validation
  - Measure: Time for capital checks, risk limits
  - Target: < 50μs

Stage 3: Position Reservation
  - Measure: Atomic CAS operation
  - Target: < 10μs

Stage 4: Order Construction
  - Measure: Building order object
  - Target: < 20μs

Stage 5: Order Submission
  - Measure: Network call to exchange
  - Target: < 500μs

Stage 6: Exchange Processing
  - Measure: Time from submission to acknowledgment
  - Target: < 1ms (exchange-side)

Stage 7: Fill Notification
  - Measure: Time from fill to system awareness
  - Target: < 100μs

Total Target: < 2ms

Track percentiles for each stage:
  - p50
  - p95
  - p99

Alert: If any stage p99 > 10x target

---

PART 11: METRIC STORAGE

Time-Series Database:

Use: InfluxDB, TimescaleDB, or similar

Schema:

measurement: trading_metrics
tags:
  - metric_name
  - strategy (if applicable)
  - symbol (if applicable)
fields:
  - value (float)
timestamp: nanoseconds

Example:

INSERT trading_metrics,metric=win_rate,strategy=geometry value=0.62 1737478800000000000

Retention:
  - High-resolution (1s): 7 days
  - Medium-resolution (1m): 90 days
  - Low-resolution (1h): Forever

---

PART 12: DEBUGGING WORKFLOWS

Workflow: Investigate Lost Trade

Steps:
1. Check performance dashboard - find trade in history
2. View trade details:
   - Entry time, price
   - Exit time, price
   - PnL
   - Exit reason
3. Check event log:
   - What event triggered?
   - Event lifecycle states
4. Check arbitration log:
   - Was this trade selected over others?
   - What was the score?
5. Review state at entry:
   - Regime
   - OI levels
   - Wallet positions
6. Identify failure point

---

Workflow: Investigate Missed Entry

Steps:
1. Check event log - find the event
2. Check event lifecycle:
   - Was it detected?
   - Did it reach ACTIONABLE state?
   - When did it expire?
3. Check strategy state:
   - Was strategy in SCANNING?
   - Was regime correct?
   - Were conditions met?
4. Check arbitration log:
   - Was event presented for selection?
   - Was it rejected? Why?
5. Review capital availability:
   - Was capital available?
   - Were risk limits hit?

---

Workflow: Investigate High Latency

Steps:
1. Check latency dashboard
2. Identify which stage is slow
3. Check system health:
   - CPU high?
   - Memory high?
   - Disk I/O bottleneck?
4. Check network:
   - High ping to exchange?
   - Packet loss?
5. Review recent code changes
6. Profile hot path

---

PART 13: MONITORING TOOLS

Recommended Stack:

Metrics Collection: Prometheus
Time-Series Storage: InfluxDB
Visualization: Grafana
Alerting: PagerDuty or custom
Logging: Elasticsearch + Kibana (ELK)

Alternative (Lightweight):

Metrics: Custom SQLite database
Visualization: Custom web dashboard
Alerting: Email + Slack
Logging: Structured JSON logs to files

---

PART 14: IMPLEMENTATION CHECKLIST

[ ] Define all metric schemas
[ ] Implement metric collection
[ ] Set up time-series database
[ ] Build real-time dashboards
[ ] Configure alert rules
[ ] Set up alert channels
[ ] Implement latency profiling
[ ] Add debugging tools
[ ] Write monitoring tests
[ ] Document alert response procedures

---

PART 15: TESTING MONITORING

Inject Test Scenarios:

Test 1: Simulate data staleness
  - Stop node feed for 5 seconds
  - Verify staleness alert triggers
  - Verify trading halts

Test 2: Simulate position mismatch
  - Manually modify internal position
  - Verify mismatch detected
  - Verify alert triggers

Test 3: Simulate component failure
  - Kill strategy process
  - Verify heartbeat timeout detected
  - Verify restart attempted

Test 4: Simulate rapid losses
  - Force 5 losing trades
  - Verify consecutive loss alert
  - Verify size reduction

---

BOTTOM LINE

Monitoring is not optional.

Without monitoring:
  - You're blind
  - Failures go unnoticed
  - No feedback loop for improvement
  - Cannot debug issues

With monitoring:
  - Know system state in real-time
  - Detect failures immediately
  - Understand performance trends
  - Debug issues systematically

Invest in monitoring upfront.
It pays for itself the first time it prevents a catastrophic loss.

Monitor everything.
Alert on anomalies.
Fix broken things before they break worse.
