TESTING & VALIDATION STRATEGY
Building Confidence Through Comprehensive Testing

Untested code is broken code.
You just don't know how yet.

This document defines:
  - Testing layers (unit, integration, end-to-end)
  - Validation criteria before production
  - Chaos engineering for resilience
  - Paper trading requirements

Goal: Deploy with confidence, not hope.

---

PART 1: TESTING PYRAMID

Layer 1: Unit Tests (Foundation)
  - Test individual components
  - Fast, isolated, deterministic
  - 70% of test coverage

Layer 2: Integration Tests
  - Test component interactions
  - Slower, requires setup
  - 20% of test coverage

Layer 3: End-to-End Tests
  - Test complete workflows
  - Slowest, most brittle
  - 10% of test coverage

Invert this pyramid = slow, unstable tests.

---

PART 2: UNIT TESTS

What to Unit Test:

1. State Machine Transitions

For each strategy state machine (HLP10):

test_geometry_scanning_to_armed():
  strategy = GeometryStrategy()
  strategy.state = SCANNING
  
  # Trigger arming condition
  state = create_mock_state(
    oi_spike=1.25,
    funding_skewed=True,
    regime=EXPANSION
  )
  
  strategy.evaluate(state)
  
  assert strategy.state == ARMED
  assert strategy.armed_at > 0

test_geometry_armed_invalidation():
  strategy = GeometryStrategy()
  strategy.state = ARMED
  strategy.armed_at = now() - 120_000  # 2 minutes ago
  
  strategy.evaluate(state)
  
  assert strategy.state == SCANNING  # Timeout
  assert strategy.armed_at == 0

Test every transition, every invalidation.

---

2. Position Sizing Calculations

From HLP17:

test_position_sizing_basic():
  capital = 10000
  risk_pct = 0.01
  stop_distance = 500
  
  size = calculate_position_size(capital, risk_pct, stop_distance)
  
  assert size == 0.2  # BTC

test_position_sizing_respects_max():
  capital = 10000
  risk_pct = 0.05  # 5% (too high)
  stop_distance = 100
  
  size = calculate_position_size(capital, risk_pct, stop_distance)
  
  # Should cap at 2% max
  expected = (10000 * 0.02) / 100
  assert size == expected

test_volatility_adjustment():
  base_size = 1.0
  baseline_volatility = 100
  current_volatility = 200
  
  adjusted = apply_volatility_adjustment(
    base_size, baseline_volatility, current_volatility
  )
  
  assert adjusted == 0.5  # Half size in high vol

---

3. Risk Limit Checks

test_max_position_size_enforced():
  capital = 10000
  max_pct = 0.05  # 5%
  
  position_value = 600  # 6% of capital
  
  result = check_position_size_limit(position_value, capital, max_pct)
  
  assert result == REJECT

test_aggregate_exposure_limit():
  capital = 10000
  existing_positions = [400, 300, 200]  # Total: 900
  new_position = 200
  max_aggregate = 0.10  # 10%
  
  result = check_aggregate_limit(
    existing_positions, new_position, capital, max_aggregate
  )
  
  # 900 + 200 = 1100 (11%) > 1000 max
  assert result == REJECT

---

4. Event Lifecycle State Transitions

From HLP14:

test_event_lifecycle_detected_to_triggered():
  event = LiquidationCascadeEvent()
  event.lifecycle_state = DETECTED
  
  # Trigger condition met
  event.update(oi_drop_rate=0.15)
  
  assert event.lifecycle_state == TRIGGERED
  assert event.triggered_at > 0

test_event_expiration():
  event = Event()
  event.lifecycle_state = COMPLETED
  event.completed_at = now() - 300_000  # 5 minutes ago
  event.ttl_ms = 300_000
  
  event.check_expiration()
  
  assert event.lifecycle_state == EXPIRED

---

5. Orderbook Analysis

test_calculate_slippage():
  orderbook = create_mock_orderbook(
    asks=[
      (50000, 0.2),
      (50005, 0.3),
      (50010, 0.5),
    ]
  )
  
  order_size = 0.5
  
  slippage = calculate_market_order_slippage(orderbook, order_size, "BUY")
  
  # (0.2*50000 + 0.3*50005) / 0.5 = 50003
  # Mid price: 50000
  # Slippage: 3 / 50000 = 0.006%
  assert abs(slippage - 0.00006) < 0.00001

---

6. Capital Management

test_daily_loss_limit_enforced():
  capital = 10000
  daily_pnl = -250  # -2.5%
  limit_pct = 0.03  # 3%
  
  can_trade = check_daily_loss_limit(daily_pnl, capital, limit_pct)
  
  assert can_trade == True  # Still under limit
  
  daily_pnl = -350  # -3.5%
  can_trade = check_daily_loss_limit(daily_pnl, capital, limit_pct)
  
  assert can_trade == False  # Exceeded

test_consecutive_loss_size_reduction():
  consecutive_losses = 5
  base_size = 1.0
  
  adjusted = apply_consecutive_loss_adjustment(consecutive_losses, base_size)
  
  assert adjusted == 0.5  # 50% reduction after 5 losses

---

Unit Test Requirements:

Coverage: > 80% of core logic
Speed: < 1 second total for all unit tests
Isolation: No external dependencies (mock everything)
Determinism: Same results every run

Run: On every code change (pre-commit hook)

---

PART 3: INTEGRATION TESTS

What to Integration Test:

1. End-to-End Trade Flow

test_complete_trade_flow():
  # Setup
  system = initialize_trading_system()
  mock_exchange = MockExchange()
  
  # Inject event
  inject_liquidation_cascade_event(
    oi_drop=0.20,
    price_move=0.05,
  )
  
  # System should:
  # 1. Detect event
  # 2. Classify as cascade
  # 3. Strategy evaluates
  # 4. Position sized
  # 5. Order submitted
  # 6. Stop placed
  
  wait_for_order_submission(timeout=5s)
  
  orders = mock_exchange.get_orders()
  assert len(orders) == 2  # Entry + stop
  assert orders[0].side == "BUY"
  assert orders[1].type == "STOP_MARKET"

---

2. Multi-Strategy Coordination

test_strategy_exclusion():
  system = initialize_system()
  
  # Both strategies detect setups on same symbol
  inject_cascade_event("BTC")
  inject_snapback_event("BTC")
  
  # System should arbitrate (HLP15)
  wait_for_arbitration()
  
  positions = system.get_active_positions()
  
  # Only one position opened (mutual exclusion)
  assert len(positions) == 1

---

3. Position Reconciliation

test_position_reconciliation_detects_mismatch():
  system = initialize_system()
  exchange = system.exchange
  
  # System thinks it has position
  system.position_manager.set_position("BTC", 1.0)
  
  # Exchange says no position
  exchange.set_actual_position("BTC", 0.0)
  
  # Trigger reconciliation
  system.reconcile_positions()
  
  # Should detect and alert
  alerts = system.get_alerts()
  assert any("mismatch" in a.message for a in alerts)

---

4. Failure Recovery

test_connection_drop_and_recovery():
  system = initialize_system()
  
  # Simulate connection drop
  system.node_client.disconnect()
  
  wait(2s)
  
  # Verify trading halted
  assert system.trading_enabled == False
  
  # Reconnect
  system.node_client.connect()
  
  # Verify state rebuilt
  wait_for_state_rebuild()
  assert system.hot_state.age_ms < 1000
  
  # Verify trading resumed
  assert system.trading_enabled == True

---

5. Circuit Breaker Triggers

test_circuit_breaker_rapid_loss():
  system = initialize_system(capital=10000)
  
  # Simulate 5 consecutive losses
  for i in range(5):
    execute_losing_trade(loss=50)
  
  # Circuit breaker should trigger
  assert system.circuit_breaker_active == True
  assert system.trading_enabled == False

---

Integration Test Requirements:

Coverage: All critical paths
Speed: < 30 seconds total
Setup: Automated (fixtures, mocks)
Cleanup: Tear down properly

Run: Before deployment

---

PART 4: END-TO-END TESTS

What to E2E Test:

1. Paper Trading Validation

test_paper_trading_session():
  # Run system in paper mode
  system = initialize_system(mode="paper")
  
  # Connect to real market data
  system.connect_to_testnet()
  
  # Run for 24 hours or N trades
  run_until(trades=20 or time=24h)
  
  # Verify:
  results = system.get_results()
  assert results.trades > 0
  assert results.no_errors == True
  assert results.position_reconciliation_ok == True

---

2. Replay Test (Full Historical Day)

test_replay_full_day():
  # Load full day of historical data
  data = load_historical_data("2026-01-15")
  
  # Replay
  results = run_backtest(data, production_config)
  
  # Verify determinism (run twice)
  results_2 = run_backtest(data, production_config)
  
  assert results == results_2
  
  # Verify metrics reasonable
  assert results.trade_count > 0
  assert results.win_rate > 0.4

---

E2E Test Requirements:

Coverage: Complete user workflows
Speed: < 10 minutes per test
Environment: Testnet or replay
Validation: Real-world scenarios

Run: Before production deployment

---

PART 5: CHAOS ENGINEERING

Purpose: Verify system resilience under failure

Chaos Scenarios:

1. Random Component Crashes

test_strategy_random_crashes():
  system = initialize_system()
  
  # Killer thread
  async def random_killer():
    while True:
      await sleep(random(10, 60))
      strategy = random_choice(strategies)
      kill_process(strategy)
  
  # Run for 1 hour
  run_with_chaos(duration=1h, chaos_fn=random_killer)
  
  # Verify:
  # - Strategies auto-restart
  # - No trades lost
  # - No position inconsistencies

---

2. Network Interruptions

test_flaky_network():
  system = initialize_system()
  
  # Chaos function
  async def network_chaos():
    while True:
      await sleep(random(30, 120))
      # Drop connection for 1-5 seconds
      disconnect_for(duration=random(1, 5))
  
  run_with_chaos(duration=2h, chaos_fn=network_chaos)
  
  # Verify:
  # - Auto-reconnection works
  # - State rebuilds correctly
  # - No duplicate orders

---

3. Data Quality Issues

test_corrupt_messages():
  system = initialize_system()
  
  # Inject corrupt messages (10%)
  inject_corruption_rate(0.10)
  
  run_for(duration=30m)
  
  # Verify:
  # - Corrupt messages rejected
  # - System continues functioning
  # - No crashes

---

4. Resource Exhaustion

test_memory_pressure():
  system = initialize_system()
  
  # Create memory pressure
  memory_hog = allocate_memory(target_usage=85%)
  
  run_for(duration=30m)
  
  # Verify:
  # - System degrades gracefully
  # - Background tasks throttled
  # - Core trading continues

---

Chaos Test Requirements:

Duration: 1-4 hours minimum
Scenarios: 5+ different failure types
Monitoring: Full instrumentation
Validation: No data loss, no crashes

Run: Weekly or before major releases

---

PART 6: PAPER TRADING CRITERIA

Before Live Trading:

Run paper trading for minimum:
  - Duration: 7 days
  - OR Trades: 50 completed trades
  - Whichever comes first

Success Criteria:

1. No System Errors
   - Zero crashes
   - Zero position mismatches
   - Zero missed stops

2. Performance Acceptable
   - Win rate > 50%
   - Sharpe > 1.0
   - Max drawdown < 20%

3. Execution Quality
   - Fill rate > 95%
   - Avg slippage < 0.1%
   - Order latency p99 < 50ms

4. Risk Controls Working
   - No risk limit violations
   - Daily loss limits enforced
   - Circuit breakers functional

If ANY criterion fails:
  - Do NOT go live
  - Fix issue
  - Restart paper trading

---

Validation Checklist:

[ ] System runs continuously for 7 days
[ ] All trades logged correctly
[ ] Position reconciliation: 100% match rate
[ ] No memory leaks (memory stable over 7 days)
[ ] No data staleness incidents
[ ] All circuit breakers tested (via simulation)
[ ] Emergency shutdown works
[ ] Recovery from failures works
[ ] Win rate meets target
[ ] Sharpe ratio acceptable
[ ] Max drawdown under limit

---

PART 7: REGRESSION TEST SUITE

Maintain test suite that grows over time.

Components:

1. Core Functionality Tests
   - Strategy logic
   - Position sizing
   - Risk checks

2. Bug Reproduction Tests
   - For every bug found in production
   - Create test that reproduces bug
   - Verify fix prevents recurrence

3. Edge Case Tests
   - Extreme market conditions
   - Unusual data patterns
   - Boundary conditions

---

Test Organization:

tests/
  unit/
    test_state_machines.py
    test_position_sizing.py
    test_risk_limits.py
    test_event_lifecycle.py
  integration/
    test_trade_flow.py
    test_arbitration.py
    test_recovery.py
  e2e/
    test_paper_trading.py
    test_replay.py
  chaos/
    test_resilience.py
  regression/
    test_bug_fixes.py
    test_edge_cases.py

---

PART 8: CONTINUOUS TESTING

Pre-Commit Tests:

Hook: Run before every commit

git commit → run unit tests → allow commit if pass

Fast feedback loop.

---

Pre-Merge Tests:

On pull request:
  1. Run full unit test suite
  2. Run integration tests
  3. Run regression backtest
  4. Check code coverage

Require all passing before merge.

---

Nightly Tests:

Run every night:
  - Full test suite
  - Chaos tests
  - Historical replay (last 30 days)
  - Performance benchmarks

Report results next morning.

---

PART 9: TEST DATA MANAGEMENT

Test Data Sources:

1. Synthetic Data
   - Programmatically generated
   - Controlled, deterministic
   - Fast to create

2. Historical Snapshots
   - Real market data
   - Specific scenarios
   - Realistic edge cases

3. Mock Services
   - Simulated exchange
   - Simulated node

---

Test Data Requirements:

Version Control:
  - Store test data in repo (small files)
  - Or reference by hash (large files)

Reproducibility:
  - Same test data → same results

Documentation:
  - Describe what each dataset represents
  - Why it's important for testing

---

PART 10: TESTING CHECKLIST

Before Deployment:

[ ] All unit tests pass
[ ] All integration tests pass
[ ] All E2E tests pass
[ ] Chaos tests run successfully
[ ] Paper trading validation complete
[ ] Regression tests pass
[ ] Code coverage > 80%
[ ] No known critical bugs
[ ] Performance benchmarks acceptable
[ ] Manual smoke test on testnet

---

BOTTOM LINE

Testing is not optional.

Without testing:
  - No confidence in code
  - Bugs discovered in production
  - Data loss, capital loss
  - Long debugging cycles

With testing:
  - Deploy with confidence
  - Catch bugs before production
  - Faster development (fewer regressions)
  - Better sleep

Test early, test often, test thoroughly.

The cost of testing is trivial compared to the cost of a production bug.
