CODING AGENT UNIT TEST PROMPTS
FOR MARKET REGIME MASTERFRAME
================================================

GLOBAL TESTING INSTRUCTION
--------------------------
All tests must be deterministic.
No randomness.
No mocking of future data.
All tests must FAIL CLOSED.

If a test cannot be written exactly as specified, STOP and report why.

================================================
UNIT TEST SET 1 — DATA INGESTION & ALIGNMENT
================================================

TEST 1.1 — Timestamp Alignment
- Provide orderbook, trades, liquidations with aligned timestamps
- EXPECT: data accepted, evaluation allowed

TEST 1.2 — Misaligned Timestamps
- Shift one stream by > tolerance
- EXPECT: evaluation skipped, no state changes

TEST 1.3 — Missing Stream
- Remove liquidation feed
- EXPECT: all derived metrics NULL
- EXPECT: no trades allowed

TEST 1.4 — Warm-Up Period
- Provide fewer samples than rolling window
- EXPECT: metrics NULL
- EXPECT: system remains DISABLED

================================================
UNIT TEST SET 2 — DERIVED METRICS
================================================

TEST 2.1 — VWAP Calculation
- Known price/volume series
- EXPECT: VWAP exact match

TEST 2.2 — ATR Windows
- Feed fixed-range candles
- EXPECT: ATR values correct per window

TEST 2.3 — Rolling Volume
- Feed controlled trade stream
- EXPECT: taker_buy_10s, taker_sell_30s correct

TEST 2.4 — Liquidation Z-Score
- Constant liquidation rate
- EXPECT: z-score ≈ 0
- Inject spike
- EXPECT: z-score > threshold

================================================
UNIT TEST SET 3 — ORDERBOOK ZONING
================================================

TEST 3.1 — Zone Assignment
- Feed synthetic orderbook
- EXPECT: liquidity assigned to correct zones

TEST 3.2 — Zone Persistence
- Maintain liquidity for ≥30s
- EXPECT: persistence counter increments correctly

TEST 3.3 — Cancel vs Execute
- Simulate trades hitting zone
- EXPECT: executed_volume increments
- Remove liquidity without trades
- EXPECT: canceled_volume increments

TEST 3.4 — No Per-Level Leakage
- Ensure no logic references raw levels
- EXPECT: failure if detected

================================================
UNIT TEST SET 4 — REGIME CLASSIFIER
================================================

TEST 4.1 — Sideways Activation
- Feed data satisfying ALL sideways conditions
- EXPECT: state == SIDEWAYS_ACTIVE

TEST 4.2 — Sideways Partial Conditions
- Break ONE condition
- EXPECT: state == DISABLED

TEST 4.3 — Expansion Activation
- Feed data satisfying ALL expansion conditions
- EXPECT: state == EXPANSION_ACTIVE

TEST 4.4 — Mutual Exclusivity
- Attempt to satisfy both regimes
- EXPECT: DISABLED (ambiguous)

================================================
UNIT TEST SET 5 — LIQUIDITY BLOCK DETECTION
================================================

TEST 5.1 — Valid Absorption Block
- High zone liquidity
- Persistence ≥30s
- Executions present
- Low price impact
- EXPECT: block_type == ABSORPTION

TEST 5.2 — Consumption Block
- Executions + price acceptance
- EXPECT: block_type == CONSUMPTION
- EXPECT: not tradable

TEST 5.3 — Spoof Block
- Liquidity disappears without trades
- EXPECT: block_type == SPOOF

TEST 5.4 — Block Invalidation
- Price accepts through block
- EXPECT: block invalidated immediately

================================================
UNIT TEST SET 6 — SLBRS STATE MACHINE
================================================

TEST 6.1 — Correct State Sequence
- SIDEWAYS → SETUP_DETECTED → FIRST_TEST → RETEST_ARMED → IN_POSITION
- EXPECT: no skipped states

TEST 6.2 — Invalid Transition
- Attempt FIRST_TEST without SETUP_DETECTED
- EXPECT: rejection, reset

TEST 6.3 — Single Setup Enforcement
- Trigger second block while one active
- EXPECT: second ignored

TEST 6.4 — Regime Change Abort
- Change regime mid-setup
- EXPECT: reset to DISABLED

================================================
UNIT TEST SET 7 — SLBRS ENTRY CONDITIONS
================================================

TEST 7.1 — Valid Retest Entry
- Reduced aggression
- Lower price impact
- Absorption ratio ≥0.65
- EXPECT: entry triggered

TEST 7.2 — Failed Retest
- Aggression not reduced
- EXPECT: no entry

TEST 7.3 — R:R Rejection
- Valid setup but R:R < 1.5
- EXPECT: entry blocked

================================================
UNIT TEST SET 8 — EFFCS ENTRY LOGIC
================================================

TEST 8.1 — Valid Impulse Entry
- Price displacement ≥0.5 ATR
- Liquidation spike
- Shallow pullback
- EXPECT: entry in impulse direction

TEST 8.2 — Deep Pullback
- Retracement >30%
- EXPECT: no entry

TEST 8.3 — Liquidity Refill
- Orderbook replenishes
- EXPECT: entry blocked

TEST 8.4 — Countertrend Protection
- Attempt fade
- EXPECT: rejection

================================================
UNIT TEST SET 9 — RISK MANAGEMENT
================================================

TEST 9.1 — Stop Placement
- EXPECT: stop beyond block + ATR buffer

TEST 9.2 — Target Validation
- No opposing block or VWAP
- EXPECT: trade rejected

TEST 9.3 — Immediate Invalidation Exit
- Trigger invalidation mid-trade
- EXPECT: immediate market exit

================================================
UNIT TEST SET 10 — COOLDOWN & FAIL-SAFES
================================================

TEST 10.1 — Cooldown Enforcement
- Exit trade
- Attempt setup during cooldown
- EXPECT: no evaluation

TEST 10.2 — Consecutive Loss Kill
- Two stopouts
- EXPECT: system disabled

TEST 10.3 — Drawdown Kill
- Exceed MAX_DD
- EXPECT: system disabled

TEST 10.4 — Winrate Kill
- Winrate last 20 <35%
- EXPECT: system disabled

================================================
UNIT TEST SET 11 — MASTER CONTROLLER
================================================

TEST 11.1 — Mutual Exclusion
- SIDEWAYS_ACTIVE
- EXPECT: EFFCS disabled

TEST 11.2 — Strategy Routing
- EXPANSION_ACTIVE
- EXPECT: only EFFCS evaluated

TEST 11.3 — Transition Reset
- SIDEWAYS → DISABLED
- EXPECT: all states reset

================================================
UNIT TEST SET 12 — LOGGING & AUDIT
================================================

TEST 12.1 — Mandatory Fields
- Execute trade
- EXPECT: all required log fields present

TEST 12.2 — Decision Logging
- Regime change
- EXPECT: logged with timestamp

TEST 12.3 — Missing Log Failure
- Suppress logging
- EXPECT: test failure

================================================
FINAL TESTING RULE
================================================

ALL tests must pass before integration.
If ANY test fails:
- DO NOT PROCEED
- FIX THE MODULE
- RE-RUN TESTS

END OF UNIT TEST PROMPTS
================================================