FAILURE MODES & RECOVERY
Critical Error Handling for Production Trading Systems

In liquidation trading, failures are not hypothetical.
They are inevitable and must be handled explicitly.

This document defines:
  - Every failure mode
  - Detection mechanisms
  - Recovery procedures
  - Circuit breakers

The goal is not to prevent failures.
The goal is to fail safely and recover deterministically.

---

PART 1: NETWORK FAILURES

Failure Mode 1.1: WebSocket Connection Drop

Symptoms:
  - No messages received for > heartbeat_timeout
  - WebSocket close signal
  - Network unreachable error

Detection:
  - Heartbeat monitor (every 5 seconds)
  - Message gap detector (sequence numbers)
  - Connection state tracking

Response:

Immediate (< 100ms):
  1. Mark connection as DISCONNECTED
  2. Stop trading immediately
  3. Flag hot state as STALE
  4. Log disconnection event

Short-term (< 5s):
  1. Attempt reconnection with exponential backoff:
     - Retry 1: Immediate
     - Retry 2: 1s delay
     - Retry 3: 2s delay
     - Retry 4: 4s delay
     - Retry 5: 8s delay
  2. If reconnection successful:
     - Request full orderbook snapshot
     - Validate sequence numbers
     - Resume state building
  3. If reconnection fails after 5 attempts:
     - Enter DEGRADED mode
     - Alert operator
     - Continue retrying indefinitely

State Recovery After Reconnection:

Must rebuild state completely:
  1. Request full L2 orderbook snapshot
  2. Sync current OI, funding, mark price
  3. Validate against last known state:
     - If price moved > 5%: Alert (possible data gap)
     - If OI changed > 20%: Alert (missed liquidation)
  4. Clear all active events (may be stale)
  5. Reset all strategy states to SCANNING
  6. Resume trading only after N seconds of clean data

Recovery Time Target: < 10 seconds

---

Failure Mode 1.2: API Rate Limiting

Symptoms:
  - HTTP 429 responses
  - Exponentially increasing latency
  - Request rejections

Detection:
  - Monitor response codes
  - Track request rate
  - Latency threshold alerts

Response:

1. Back off immediately:
   - Reduce request rate by 50%
   - Add jitter to prevent thundering herd
2. If rate limit persists:
   - Enter DEGRADED mode
   - Use cached data where possible
   - Extended polling intervals
3. Recovery:
   - Gradually increase request rate
   - Monitor for 429s
   - Return to normal after 5 minutes clean

Prevention:
  - Pre-configure rate limits in client
  - Use request budgets
  - Prioritize critical requests (orderbook > historical)

---

Failure Mode 1.3: DNS Failure

Symptoms:
  - Name resolution errors
  - Timeout on connection attempts

Detection:
  - Connection attempt failures
  - DNS resolution monitoring

Response:

1. Use fallback DNS servers:
   - Primary: CloudFlare (1.1.1.1)
   - Secondary: Google (8.8.8.8)
2. Use cached IP addresses if available
3. If all DNS fails:
   - Alert operator
   - Manual intervention required

Prevention:
  - Cache resolved IPs
  - Use numeric IPs as fallback
  - Monitor DNS resolution latency

---

Failure Mode 1.4: Firewall / Port Blocking

Symptoms:
  - Connection refused
  - Timeout on specific ports

Detection:
  - Connection state monitoring
  - Port accessibility tests

Response:

1. Verify local firewall rules
2. Test connectivity to known-good endpoints
3. If blocked:
   - Alert operator
   - Manual firewall reconfiguration required
4. Use alternative connection paths if available

---

PART 2: DATA QUALITY ISSUES

Failure Mode 2.1: Stale Ticks

Symptoms:
  - Last update timestamp > staleness_threshold
  - Sequence number gap
  - Price hasn't changed in > N seconds

Detection:

data_age_ms = current_time - last_update_time

If data_age_ms > 1000ms:
  Mark hot state as STALE

Response:

1. Stop all trading immediately
2. Do not enter new positions
3. Maintain existing positions (stops still active)
4. Alert: "Stale data detected"
5. If staleness persists > 10 seconds:
   - Exit all positions at market
   - Enter EMERGENCY_HALT mode

Recovery:
  - Resume trading only after 3 consecutive fresh updates
  - Verify data consistency

---

Failure Mode 2.2: Sequence Number Gaps

Symptoms:
  - Sequence numbers not monotonically increasing
  - Missing messages detected

Detection:

if current_seq != expected_seq:
  gap = current_seq - expected_seq
  log_error(f"Sequence gap detected: {gap} messages missing")

Response:

If gap < 10 messages:
  - Request historical data to fill gap
  - Replay missed messages
  - Resume trading

If gap >= 10 messages:
  - Cannot reliably recover state
  - Request full orderbook snapshot
  - Reset all active events
  - Resume trading after state rebuilt

Prevention:
  - Buffer messages during processing
  - Detect gaps immediately
  - Log all sequence numbers

---

Failure Mode 2.3: Timestamp Anomalies

Symptoms:
  - Future timestamps (ts > current_time + tolerance)
  - Backwards timestamps (ts < previous_ts)
  - Clock drift detected

Detection:

# Future timestamp check
if message_ts > current_time + 5000:  # 5 second tolerance
  log_error("Future timestamp detected")
  
# Backwards timestamp check
if message_ts < last_message_ts:
  log_error("Backwards timestamp detected")

Response:

For future timestamps:
  - Accept if within tolerance (5s)
  - Reject if beyond tolerance
  - Alert on repeated occurrences

For backwards timestamps:
  - Use message processing time instead
  - Flag data as suspect
  - Alert operator

Clock Drift Detection:
  - Monitor NTP offset
  - If drift > 1 second:
    * Alert operator
    * Synchronize clock
    * May need to restart

Prevention:
  - Use NTP for time synchronization
  - Monitor clock health
  - Use monotonic clocks where possible

---

Failure Mode 2.4: Corrupt Messages

Symptoms:
  - JSON parse errors
  - Invalid field values
  - Missing required fields

Detection:

try:
  message = json.parse(raw_data)
  validate_schema(message)
except:
  log_error("Corrupt message detected")

Response:

1. Reject corrupt message
2. Log for debugging
3. Increment corruption counter
4. If corruption_rate > 5%:
   - Enter DEGRADED mode
   - Alert operator
   - Possible node issue

Recovery:
  - No recovery needed (single message)
  - Monitor corruption rate
  - Investigate if persistent

---

PART 3: COMPONENT FAILURES

Failure Mode 3.1: State Builder Crash

Symptoms:
  - Process terminated unexpectedly
  - No heartbeat from state builder
  - Exception in state building logic

Detection:
  - Process monitoring (systemd, supervisor)
  - Heartbeat timeout (every 1 second)
  - Exception logging

Response:

Immediate:
  1. Stop all trading
  2. Mark hot state as INVALID
  3. Alert operator

Auto-recovery (via process supervisor):
  1. Restart state builder process
  2. Reload from last snapshot
  3. Replay missed messages from cold storage
  4. Rebuild hot state
  5. Validate state consistency
  6. Resume trading after validation

Manual Steps (if auto-recovery fails):
  1. Investigate crash reason (logs)
  2. Fix bug if applicable
  3. Manual restart
  4. Verify state correctness

Recovery Time Target: < 30 seconds

---

Failure Mode 3.2: Strategy Crash

Symptoms:
  - Strategy process terminated
  - Unhandled exception in strategy logic
  - Strategy heartbeat timeout

Detection:
  - Per-strategy heartbeat monitoring
  - Exception logging
  - Strategy health checks

Response:

1. Isolate crash to single strategy:
   - Other strategies continue
   - Only crashed strategy stops
2. Log crash details:
   - Stack trace
   - Input state that caused crash
   - Active events at crash time
3. Auto-restart strategy:
   - Reset to DISABLED state
   - Clear active setups
   - Resume scanning
4. If crash repeats > 3 times in 10 minutes:
   - Disable strategy permanently
   - Alert operator
   - Requires manual intervention

Position Handling:
  - If strategy had open position:
    * Position manager takes over
    * Manages stops automatically
    * Strategy cannot re-enter

Prevention:
  - Extensive exception handling
  - Input validation
  - Strategy isolation (one crash doesn't kill all)

---

Failure Mode 3.3: Database Corruption

Symptoms:
  - Cannot read/write to database
  - Checksum failures
  - Filesystem errors

Detection:
  - Database health checks
  - Write verification
  - Periodic integrity audits

Response:

Immediate:
  1. Stop cold storage writes
  2. Continue trading (in-memory only)
  3. Buffer recent data in memory
  4. Alert operator

Recovery:
  1. Attempt to repair database
  2. If repair fails:
     - Restore from last backup
     - Replay from backup point
  3. If restore fails:
     - Initialize new database
     - Loss of historical data
     - Trading can continue

Prevention:
  - Regular backups (hourly)
  - Write verification
  - RAID storage
  - File system integrity checks

---

Failure Mode 3.4: Disk Full

Symptoms:
  - Write failures
  - ENOSPC errors
  - Disk usage > 95%

Detection:
  - Disk usage monitoring (every minute)
  - Write failure detection
  - Pre-emptive warnings at 90%

Response:

At 90% usage:
  - Warning alert
  - Begin cleanup of old logs
  - Compress archived data

At 95% usage:
  - Critical alert
  - Aggressive cleanup
  - Stop writing to cold storage
  - Continue trading (in-memory only)

At 98% usage:
  - Emergency cleanup
  - Delete oldest archived data
  - Maintain only critical logs

Recovery:
  - Add more storage
  - Archive to external storage
  - Implement log rotation policies

Prevention:
  - Automated log rotation
  - Compression
  - Archive old data to cloud storage
  - Disk usage alerts

---

PART 4: CIRCUIT BREAKERS

Circuit Breaker 1: Rapid Loss Detection

Trigger Conditions:
  - Lose > 5% of capital in single trade
  - Lose > 10% of capital in single session
  - 5 consecutive losses

Response:
  1. Halt all trading immediately
  2. Close all open positions
  3. Enter CIRCUIT_BREAKER mode
  4. Alert operator
  5. Require manual reset

Recovery:
  - Manual review of losses
  - Identify systematic issue
  - Fix before resuming
  - Require operator approval to resume

---

Circuit Breaker 2: Abnormal Price Movement

Trigger Conditions:
  - Price moves > 20% in < 1 minute
  - Orderbook depth drops > 95%
  - Funding rate spikes > 10x normal

Response:
  1. Pause trading for 60 seconds
  2. Do not close existing positions
  3. Validate data quality
  4. Alert operator

Recovery:
  - If movement confirmed as real:
    * Resume trading
    * Adjust parameters if needed
  - If determined as data error:
    * Request fresh data
    * Rebuild state
    * Resume after validation

---

Circuit Breaker 3: Strategy Malfunction

Trigger Conditions:
  - Win rate drops > 30% below baseline
  - Average loss > 2x average win
  - Sharpe ratio < 0 over 20 trades

Response:
  1. Disable underperforming strategy
  2. Continue other strategies
  3. Alert operator
  4. Log strategy metrics

Recovery:
  - Analyze strategy performance
  - Identify issue (market regime change? bug?)
  - Fix or recalibrate
  - Test on paper trading before re-enable

---

Circuit Breaker 4: System Resource Exhaustion

Trigger Conditions:
  - CPU usage > 95% for > 30 seconds
  - Memory usage > 90%
  - Latency p99 > 10x baseline

Response:
  1. Pause heavy background tasks:
     - Backtesting
     - Parameter optimization
     - Historical analysis
  2. Prioritize trading processes
  3. Alert operator

Recovery:
  - Identify resource hog
  - Terminate or throttle
  - Resume background tasks when resources available

Prevention:
  - Resource limits per process
  - Priority queues
  - Load shedding policies

---

PART 5: GRACEFUL DEGRADATION

Degradation Level 1: REDUCED_FUNCTIONALITY

Triggers:
  - Minor data quality issues
  - Elevated latency (> 2x baseline)
  - Non-critical component failure

Behavior:
  - Continue trading most liquid symbols only
  - Increase minimum match_score thresholds
  - Reduce position sizes by 50%
  - Disable advanced features (wallet tracking)

---

Degradation Level 2: EMERGENCY_MODE

Triggers:
  - Major data quality issues
  - Critical component failure
  - Persistent connection issues

Behavior:
  - Close all open positions
  - Do not enter new positions
  - Maintain monitoring only
  - Attempt recovery

---

Degradation Level 3: HARD_SHUTDOWN

Triggers:
  - Unrecoverable errors
  - Data integrity compromised
  - Safety concerns

Behavior:
  - Immediate shutdown
  - Close all positions at market
  - Flush critical data to disk
  - Require manual restart

---

PART 6: TIME SYNCHRONIZATION

Clock Drift Detection:

Monitor NTP offset every 10 seconds:

ntp_offset = query_ntp_server()

if abs(ntp_offset) > 1000ms:
  log_error("Clock drift detected")
  alert_operator()
  
if abs(ntp_offset) > 5000ms:
  log_critical("Severe clock drift")
  halt_trading()

Response to Clock Drift:

1. Synchronize clock via NTP
2. If sync fails:
   - Use fallback NTP servers
3. If all sync fails:
   - Alert operator
   - Manual time correction required
4. After correction:
   - Rebuild all timestamps
   - Clear event lifecycle history
   - Resume trading

Prevention:
  - Continuous NTP synchronization
  - Multiple NTP sources
  - Hardware clock verification

---

PART 7: CONNECTION MANAGEMENT

WebSocket Reconnection Strategy:

Exponential Backoff:

attempt = 0
while not connected:
  delay = min(2^attempt, 60)  # Cap at 60 seconds
  wait(delay + random(0, delay/2))  # Add jitter
  attempt += 1
  try_reconnect()

Max Reconnection Attempts: Infinite (until manual intervention)

Connection Health Monitoring:

Every 5 seconds:
  - Send ping
  - Expect pong within 1 second
  - If no pong: Mark connection as suspect
  - If 3 missed pongs: Trigger reconnection

Message Handling During Reconnection:

1. Buffer outgoing messages (max 1000)
2. On reconnection:
   - Flush buffer
   - Verify delivery
3. If buffer overflows:
   - Drop oldest messages
   - Alert operator

---

PART 8: DATA QUALITY VALIDATION

Price Range Checks:

if abs(price_change_pct) > 20:
  log_warning("Extreme price movement")
  validate_with_secondary_source()
  
if price < min_historical_price * 0.5:
  log_error("Price below historical minimum")
  reject_tick()

OI Sanity Checks:

if oi_change_pct > 50:
  log_warning("Extreme OI change")
  validate_with_secondary_source()
  
if oi < 0:
  log_error("Negative OI")
  reject_tick()

Volume Validation:

if volume > max_historical_volume * 10:
  log_warning("Extreme volume")
  validate()

Outlier Detection:

Use rolling z-score:

z_score = (current - mean) / std_dev

if abs(z_score) > 5:
  log_warning("Statistical outlier detected")
  flag_for_review()

---

PART 9: MONITORING & HEALTH CHECKS

System Health Check (Every Second):

✓ Node connection alive?
✓ State builder responsive?
✓ Hot state age < 1s?
✓ Strategies responsive?
✓ Disk space > 10%?
✓ Memory usage < 90%?
✓ CPU usage < 95%?

If any check fails:
  - Log failure
  - Increment failure counter
  - If failure_count > threshold: Take action

Component Heartbeats:

Each component emits heartbeat every second:

heartbeat_map = {
  "node_client": last_heartbeat_time,
  "state_builder": last_heartbeat_time,
  "strategy_geometry": last_heartbeat_time,
  ...
}

Monitor:
  if current_time - heartbeat_time > 3s:
    log_error(f"{component} heartbeat timeout")
    attempt_recovery(component)

---

PART 10: ERROR LOGGING

Log Levels:

DEBUG: Detailed diagnostic
INFO: Normal operations
WARNING: Potential issue
ERROR: Failure requiring attention
CRITICAL: System integrity compromised

What to Log:

Every network failure
Every data quality issue
Every component crash
Every circuit breaker trigger
Every recovery attempt
Every state transition

Log Format:

{
  "timestamp": nanoseconds,
  "level": "ERROR",
  "component": "state_builder",
  "error_type": "sequence_gap",
  "details": {
    "expected_seq": 12345,
    "received_seq": 12350,
    "gap": 5
  },
  "action_taken": "requested_historical_data"
}

---

PART 11: RECOVERY VALIDATION

After any recovery, validate:

✓ State consistency (compare to last known good)
✓ No sequence gaps
✓ Timestamps reasonable
✓ Active events valid
✓ Strategies in correct states

Validation Checklist:

[ ] Hot state age < 1s
[ ] Orderbook depth > minimum
[ ] Mark price within historical range
[ ] OI within historical range
[ ] No active alerts
[ ] All components responsive

Only resume trading after all checks pass.

---

PART 12: TESTING FAILURE MODES

Required Tests:

[ ] Simulate WebSocket disconnect
[ ] Inject sequence gaps
[ ] Corrupt messages
[ ] Kill state builder process
[ ] Fill disk to 95%
[ ] Inject future timestamps
[ ] Simulate extreme price movement
[ ] Trigger each circuit breaker
[ ] Test reconnection logic
[ ] Validate recovery procedures

Each test must verify:
  1. Failure detected correctly
  2. Response executed as specified
  3. Recovery successful
  4. No data loss (where applicable)
  5. Trading resumes safely

---

IMPLEMENTATION CHECKLIST

[ ] Implement heartbeat monitoring
[ ] Implement reconnection logic
[ ] Implement circuit breakers
[ ] Implement degradation modes
[ ] Implement data quality checks
[ ] Implement recovery procedures
[ ] Add comprehensive error logging
[ ] Build health check dashboard
[ ] Write failure mode tests
[ ] Document recovery procedures
[ ] Create operator runbooks

---

BOTTOM LINE

Failures will happen.
The system must handle them explicitly.

Every failure mode must have:
  - Clear detection mechanism
  - Defined response procedure
  - Recovery steps
  - Validation checks

The difference between a good system and a bad one:
  - Bad system: Crashes and loses money
  - Good system: Detects failure, stops safely, recovers automatically

Build for failure, not success.
