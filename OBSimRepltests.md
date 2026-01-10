CODING AGENT SIMULATION / REPLAY TEST PROMPTS
FOR MARKET REGIME MASTERFRAME
================================================

GLOBAL SIMULATION RULES
-----------------------
Simulation tests must mimic LIVE conditions as closely as possible.

Rules:
- Data must be replayed strictly forward in time
- No bar-level shortcuts
- No batch evaluation
- System must process events exactly as it would live
- Decisions must occur at the correct timestamps

If the system behaves differently in replay vs live mode:
STOP.
The implementation is invalid.

================================================
SIMULATION TEST SET 1 — REAL-TIME REPLAY INTEGRITY
================================================

TEST 1.1 — Forward-Only Replay
- Replay historical data tick-by-tick (1s granularity)
- EXPECT:
  - No access to future candles
  - No pre-knowledge of block outcomes
  - Identical behavior to live feed

TEST 1.2 — Replay Speed Independence
- Replay data at:
  - 1× speed
  - 10× speed
  - 100× speed
- EXPECT:
  - Identical decisions
  - Identical trades
  - Identical state transitions

================================================
SIMULATION TEST SET 2 — SIDEWAYS REGIME BEHAVIOR
================================================

TEST 2.1 — Prolonged Sideways Market
- Replay long, range-bound historical period
- EXPECT:
  - SLBRS activates
  - EFFCS remains disabled
  - Trades only occur after full setup sequence
  - No overtrading

TEST 2.2 — Chop With False Breakouts
- Include repeated fake range breaks
- EXPECT:
  - Blocks invalidated correctly
  - No fading of accepted breakouts
  - No revenge trades

================================================
SIMULATION TEST SET 3 — TRANSITION BEHAVIOR
================================================

TEST 3.1 — Sideways → Expansion Transition
- Replay data where range breaks into trend
- EXPECT:
  - SLBRS aborts immediately
  - No open SLBRS trades survive transition
  - EFFCS activates only after full expansion confirmation

TEST 3.2 — Expansion → Sideways Transition
- Replay trend that stalls and compresses
- EXPECT:
  - EFFCS stops evaluating
  - SLBRS remains inactive until full sideways conditions return
  - No trades during ambiguous transition

================================================
SIMULATION TEST SET 4 — EXPANSION REGIME BEHAVIOR
================================================

TEST 4.1 — Liquidation Cascade
- Replay liquidation-driven trend
- EXPECT:
  - EFFCS entries only in direction of cascade
  - No fading
  - Positions held through minor pullbacks

TEST 4.2 — Failed Expansion
- Replay VWAP escape without liquidation support
- EXPECT:
  - No EFFCS trades
  - System remains idle

================================================
SIMULATION TEST SET 5 — ORDERBOOK BEHAVIORAL VALIDATION
================================================

TEST 5.1 — Absorption Replay
- Replay period with visible absorption at range extremes
- EXPECT:
  - Block detected
  - First test observed
  - Retest entry only
  - No single-touch entries

TEST 5.2 — Spoof Environment
- Replay high-cancel activity environment
- EXPECT:
  - Spoof blocks classified correctly
  - No SLBRS entries
  - Increased invalidations logged

================================================
SIMULATION TEST SET 6 — LATENCY & EVENT ORDERING
================================================

TEST 6.1 — Out-of-Order Events
- Replay data with slightly shuffled timestamps
- EXPECT:
  - Misaligned data skipped
  - No state corruption
  - No trades triggered

TEST 6.2 — Delayed Data
- Introduce artificial delay in one stream
- EXPECT:
  - Evaluation skipped
  - System fails closed
  - Logs indicate delay

================================================
SIMULATION TEST SET 7 — PNL & BEHAVIORAL CONSISTENCY
================================================

TEST 7.1 — Deterministic Outcomes
- Replay same dataset twice
- EXPECT:
  - Identical trades
  - Identical timestamps
  - Identical PnL

TEST 7.2 — No “Almost Trades”
- Replay period with near-miss setups
- EXPECT:
  - No partial entries
  - No speculative fills
  - Clear NO_TRADE decisions logged

================================================
SIMULATION TEST SET 8 — COOLDOWN & FATIGUE PROTECTION
================================================

TEST 8.1 — Cooldown Enforcement
- Replay dense signal environment
- EXPECT:
  - Cooldown respected
  - No immediate re-entries
  - No clustering beyond spec

TEST 8.2 — Consecutive Losses in Replay
- Force replay of losing streak
- EXPECT:
  - Kill-switch triggered
  - System disabled
  - No recovery without manual reset

================================================
SIMULATION TEST SET 9 — EDGE DEGRADATION DETECTION
================================================

TEST 9.1 — Regime Drift Over Time
- Replay multi-day dataset with changing regimes
- EXPECT:
  - Correct regime switching
  - No strategy bleed
  - No persistent bias

TEST 9.2 — Structural Failure Replay
- Replay dataset with intentionally bad conditions
- EXPECT:
  - System remains mostly inactive
  - Losses limited
  - No attempt to “force” trades

================================================
SIMULATION TEST SET 10 — LIVE-READINESS CHECK
================================================

TEST 10.1 — Replay vs Paper Trading Match
- Compare replay results with paper-trade logs
- EXPECT:
  - Near-identical trade timing
  - Same state transitions
  - Minor slippage differences only

================================================
FINAL SIMULATION RULE
================================================

A simulation test PASSES only if:
- Behavior matches live logic exactly
- No lookahead bias is detected
- No trades occur outside defined regimes
- State machine remains coherent throughout replay

If ANY discrepancy exists:
DO NOT DEPLOY.
FIX.
REPLAY AGAIN.

END OF SIMULATION / REPLAY TEST PROMPTS
================================================