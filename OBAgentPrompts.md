CODING AGENT PROMPTS
FOR MARKET REGIME MASTERFRAME
==============================================

IMPORTANT GLOBAL INSTRUCTION (APPLIES TO ALL PROMPTS)
-----------------------------------------------------
You MUST follow the CODING_AGENT_RULEBOOK exactly.
Do NOT interpret, simplify, or optimize logic.
If any rule is unclear, STOP and ask for clarification.
Fail closed: if unsure, do not implement.

All logic must be deterministic and state-driven.
No discretionary logic. No additional indicators.

==============================================
PROMPT 1 — DATA INGESTION & NORMALIZATION MODULE
==============================================

TASK:
Implement the data ingestion and normalization layer.

REQUIREMENTS:
- Ingest the following streams:
  - L2 orderbook (top 20 levels, 1-second snapshots)
  - Aggressive trades (buyer/seller initiated)
  - Liquidation events
  - OHLCV klines (1m, 5m)

- Align all data by timestamp.
- If timestamps do not align within tolerance, SKIP evaluation.
- No forward-looking data is allowed.

IMPLEMENT:
- Time-aligned rolling buffers for each stream
- Explicit warm-up handling (return NULL until full)

FORBIDDEN:
- Using raw orderbook snapshots directly in strategy logic
- Interpolating missing data
- Guessing timestamps

OUTPUT:
- Clean, synchronized data objects
- Explicit NULLs when data is insufficient

==============================================
PROMPT 2 — DERIVED METRICS MODULE
==============================================

TASK:
Compute all derived metrics exactly as specified.

METRICS TO IMPLEMENT:
- Session-anchored VWAP
- ATR(1m), ATR(5m), ATR(30m)
- Rolling taker buy volume (10s, 30s)
- Rolling taker sell volume (10s, 30s)
- Liquidation Z-score (60m rolling baseline)
- Open interest delta (if available)

RULES:
- Use fixed rolling window sizes
- Do NOT smooth unless specified
- Return NULL if window not fully initialized
- No trades allowed while any required metric is NULL

FORBIDDEN:
- Adaptive window sizing
- Lookahead bias
- Statistical fitting

OUTPUT:
- Deterministic metric values with timestamps

==============================================
PROMPT 3 — ORDERBOOK ZONING & COMPRESSION MODULE
==============================================

TASK:
Convert raw L2 orderbook into normalized liquidity zones.

IMPLEMENT:
- Mid-price calculation
- Relative price zoning:
  Zone A: 0–5 bps
  Zone B: 5–15 bps
  Zone C: 15–30 bps

- Aggregate liquidity per zone per side
- Track:
  - Zone liquidity
  - Persistence time
  - Executed volume
  - Canceled volume

RULES:
- Zones must be relative to mid-price
- No per-level logic allowed
- Zone C is context only (non-tradable)

OUTPUT:
- Zone-level liquidity state objects

==============================================
PROMPT 4 — REGIME CLASSIFIER MODULE
==============================================

TASK:
Implement the global regime classifier.

REGIMES:
- SIDEWAYS
- EXPANSION
- DISABLED

IMPLEMENT EXACT CONDITIONS:

SIDEWAYS:
- abs(price − VWAP) ≤ 1.25 × ATR(5m)
- ATR(5m) / ATR(30m) < 0.80
- abs(taker_buy_30s − taker_sell_30s) / total_volume_30s < 0.18
- liquidation_zscore < 2.0

EXPANSION:
- abs(price − VWAP) ≥ 1.5 × ATR(5m)
- ATR(5m) / ATR(30m) ≥ 1.0
- abs(taker_buy_30s − taker_sell_30s) / total_volume_30s ≥ 0.35
- liquidation_zscore ≥ 2.5 OR open_interest contracts

RULES:
- ALL conditions must be true
- If neither regime qualifies → DISABLED
- Regime classification does NOT generate trades

OUTPUT:
- Regime state with timestamp
- Regime transition logs

==============================================
PROMPT 5 — LIQUIDITY BLOCK DETECTION MODULE (SLBRS)
==============================================

TASK:
Detect and classify liquidity blocks.

BLOCK QUALIFICATION (ALL REQUIRED):
- zone_liquidity ≥ 2.5 × rolling_zone_avg
- persistence ≥ 30 seconds
- executed_volume > 0
- cancel_to_trade_ratio < 3.5

CLASSIFICATION:
- ABSORPTION: high execution, low price impact
- CONSUMPTION: high execution, price accepts through
- SPOOF: otherwise

RULES:
- Only ABSORPTION blocks are tradable
- Blocks must be invalidated on acceptance
- Track block age and persistence

OUTPUT:
- Liquidity block objects with classification

==============================================
PROMPT 6 — SLBRS STATE MACHINE MODULE
==============================================

TASK:
Implement the SLBRS internal state machine.

STATES:
- SETUP_DETECTED
- FIRST_TEST
- RETEST_ARMED
- IN_POSITION

LOGIC:
- Follow the exact sequence defined in the master spec
- No state skipping allowed
- One setup at a time
- Reset on invalidation

ENTRY ALLOWED:
- ONLY in RETEST_ARMED state

RULES:
- Must respect SIDEWAYS regime gate
- Must abort immediately on regime change

OUTPUT:
- State transitions
- Entry/exit signals

==============================================
PROMPT 7 — EFFCS LOGIC MODULE
==============================================

TASK:
Implement the Expansion & Forced Flow Continuation Strategy.

REQUIREMENTS:
- Only active when regime == EXPANSION
- Never fade price
- Detect impulse + shallow pullback
- Use orderbook only for fragility confirmation

ENTRY CONDITIONS:
- price displacement ≥ 0.5 × ATR(5m)
- liquidation spike OR OI contraction
- pullback ≤ 30%
- pullback volume decreases

RULES:
- No countertrend entries
- No trades if liquidity replenishes
- Single entry per impulse

OUTPUT:
- Entry/exit signals with reason codes

==============================================
PROMPT 8 — MASTER CONTROLLER MODULE
==============================================

TASK:
Implement the master controller.

RESPONSIBILITIES:
- Enforce mutual exclusion between SLBRS and EFFCS
- Route data to active strategy only
- Disable all strategies when regime == DISABLED
- Enforce cooldowns

RULES:
- Strategies cannot self-activate
- Controller overrides all strategy logic
- Cooldown blocks all evaluations

OUTPUT:
- Active strategy state
- Controller decision logs

==============================================
PROMPT 9 — RISK MANAGEMENT MODULE
==============================================

TASK:
Implement stop, target, and exit logic exactly as specified.

RULES:
- Stops must be structural (block edge / ATR)
- Targets must be validated before entry
- Enforce minimum R:R
- No scaling, pyramiding, or averaging

EXIT:
- Immediate exit on invalidation
- Market exit only

OUTPUT:
- Executed orders
- Exit reason codes

==============================================
PROMPT 10 — FAIL-SAFES & COOLDOWN MODULE
==============================================

TASK:
Implement all fail-safe logic.

FAIL-SAFES:
- 2 consecutive losses → disable
- Daily drawdown ≥ MAX_DD → disable
- Winrate last 20 < 35% → disable

COOLDOWN:
- 5 minutes after any exit
- No evaluations during cooldown

RULES:
- Hard kill requires manual reset
- Fail closed

OUTPUT:
- Kill-switch events
- Cooldown timers

==============================================
PROMPT 11 — LOGGING & AUDIT MODULE
==============================================

TASK:
Implement mandatory logging.

LOG:
- Regime changes
- State transitions
- Setup invalidations
- Entries/exits
- Kill-switch triggers

FORMAT:
- Structured logs
- Timestamped
- Machine-readable

RULES:
- Missing logs invalidate implementation
- Log decisions, not just trades

==============================================
FINAL INSTRUCTION
==============================================

Correctness > completeness > performance.

If any module cannot be implemented exactly as specified:
STOP.
REQUEST CLARIFICATION.
DO NOT GUESS.

END OF AGENT PROMPTS
==============================================