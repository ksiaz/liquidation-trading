CODING AGENT INTEGRATION TEST PROMPTS
FOR MARKET REGIME MASTERFRAME
================================================

GLOBAL INTEGRATION TESTING INSTRUCTION
-------------------------------------
These tests validate end-to-end system behavior.

Rules:
- No mocks of strategy logic
- Only controlled synthetic data feeds
- All modules must run together
- Tests must fail CLOSED
- No partial passes allowed

If any test outcome is ambiguous:
STOP.
Report the ambiguity.
Do NOT weaken the test.

================================================
INTEGRATION TEST SET 1 — FULL DATA PIPELINE
================================================

TEST 1.1 — End-to-End Data Flow
- Feed aligned orderbook, trades, liquidations, klines
- Run full pipeline
- EXPECT:
  - Derived metrics populated
  - Regime classifier evaluated
  - No trades without valid regime

TEST 1.2 — Data Dropout Handling
- Drop one stream mid-run (e.g. liquidations)
- EXPECT:
  - Metrics return NULL
  - System enters DISABLED
  - No open or new trades

================================================
INTEGRATION TEST SET 2 — REGIME TRANSITIONS
================================================

TEST 2.1 — DISABLED → SIDEWAYS → DISABLED
- Start with insufficient data
- Gradually satisfy sideways conditions
- Then break one condition
- EXPECT:
  - Clean transition into SIDEWAYS_ACTIVE
  - Clean reset to DISABLED
  - No residual setup state

TEST 2.2 — SIDEWAYS → EXPANSION (Hard Transition)
- Start in SIDEWAYS
- Trigger expansion conditions abruptly
- EXPECT:
  - SLBRS aborted immediately
  - No SLBRS trades after transition
  - EXPANSION_ACTIVE only after all expansion conditions true

TEST 2.3 — Ambiguous Regime
- Craft data that partially satisfies both regimes
- EXPECT:
  - State == DISABLED
  - No strategy evaluated

================================================
INTEGRATION TEST SET 3 — SLBRS END-TO-END FLOW
================================================

TEST 3.1 — Complete SLBRS Trade Lifecycle
- SIDEWAYS regime active
- Valid absorption block forms
- First test rejection
- Retest entry
- Target hit

EXPECT:
- Correct state progression
- Exactly one entry
- Correct stop & target
- Proper exit reason logged

TEST 3.2 — SLBRS Invalidation Mid-Setup
- SIDEWAYS regime active
- Setup detected
- Before retest, orderflow becomes one-sided
- EXPECT:
  - Setup invalidated
  - State reset
  - No trade entered

TEST 3.3 — SLBRS Block Acceptance Failure
- Price accepts through block during first test
- EXPECT:
  - Block invalidated
  - No retest allowed
  - State reset

================================================
INTEGRATION TEST SET 4 — EFFCS END-TO-END FLOW
================================================

TEST 4.1 — Complete EFFCS Trade Lifecycle
- EXPANSION regime active
- Impulse + liquidation spike
- Shallow pullback
- Continuation entry
- Trend continuation exit

EXPECT:
- Single entry
- No countertrend logic
- Exit only on defined conditions

TEST 4.2 — Failed Expansion Attempt
- VWAP escape occurs
- But no liquidation spike or OI contraction
- EXPECT:
  - No entry
  - Strategy remains idle

TEST 4.3 — Expansion Abort
- Entry triggered
- Liquidity replenishes near price
- EXPECT:
  - Immediate exit
  - Transition to COOLDOWN

================================================
INTEGRATION TEST SET 5 — MUTUAL EXCLUSION
================================================

TEST 5.1 — Strategy Isolation
- SIDEWAYS_ACTIVE
- Force EFFCS entry conditions artificially
- EXPECT:
  - EFFCS does NOT evaluate
  - Only SLBRS logic active

TEST 5.2 — Expansion Isolation
- EXPANSION_ACTIVE
- SLBRS block appears
- EXPECT:
  - SLBRS ignored
  - No block setup initiated

================================================
INTEGRATION TEST SET 6 — COOLDOWN BEHAVIOR
================================================

TEST 6.1 — Cooldown After SLBRS Exit
- Exit SLBRS trade
- Feed valid new sideways setup
- EXPECT:
  - No evaluation during cooldown
  - Evaluation resumes after cooldown expires

TEST 6.2 — Cooldown After EFFCS Exit
- Exit EFFCS trade
- Trigger new impulse
- EXPECT:
  - No entry until cooldown complete

================================================
INTEGRATION TEST SET 7 — FAIL-SAFE ESCALATION
================================================

TEST 7.1 — Consecutive Loss Shutdown
- Force two losing trades
- EXPECT:
  - System disabled
  - No further evaluations

TEST 7.2 — Drawdown Shutdown
- Simulate PnL exceeding MAX_DD
- EXPECT:
  - Hard kill triggered
  - Manual reset required

TEST 7.3 — Structural Failure
- Force 20 trades with <35% winrate
- EXPECT:
  - System disabled
  - All states cleared

================================================
INTEGRATION TEST SET 8 — LOGGING & TRACEABILITY
================================================

TEST 8.1 — Full Trade Trace
- Execute one SLBRS trade and one EFFCS trade
- EXPECT:
  - Regime changes logged
  - State transitions logged
  - Entry/exit reasons logged
  - No missing fields

TEST 8.2 — Decision Without Trade
- Regime changes but no entry
- EXPECT:
  - Decision logged
  - Explicit "NO_TRADE" reason

================================================
INTEGRATION TEST SET 9 — FAIL CLOSED BEHAVIOR
================================================

TEST 9.1 — Metric Failure Mid-Run
- Corrupt ATR calculation
- EXPECT:
  - Strategy halted
  - No trades
  - Error logged

TEST 9.2 — Controller Override
- Force strategy to emit entry signal while DISABLED
- EXPECT:
  - Controller blocks entry
  - Violation logged

================================================
FINAL INTEGRATION TEST RULE
================================================

The system PASSES integration testing only if:
- ALL tests pass
- NO ambiguous behavior observed
- NO trades occur outside defined regimes
- NO state leakage across strategies

If ANY test fails:
DO NOT DEPLOY.
FIX.
RETEST.

END OF INTEGRATION TEST PROMPTS
================================================