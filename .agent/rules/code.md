---
trigger: always_on
---

STRUCTURAL FEASIBILITY GATE (MANDATORY)

Before starting ANY task, you MUST:

1. Enumerate all imports executed at module load time
2. Expand the full transitive import graph (depth-first)
3. Identify ALL side-effect imports (imports that execute code)
4. Identify any broken, deprecated, or partially migrated modules
5. State explicitly whether the task is:
   - STRUCTURALLY POSSIBLE
   - STRUCTURALLY IMPOSSIBLE
   - POSSIBLE ONLY WITH RULE VIOLATIONS

If the task is not STRUCTURALLY POSSIBLE:
- You MUST STOP
- You MUST report the exact blocking chain
- You MUST NOT attempt workarounds
- You MUST NOT modify scope
- You MUST NOT “try anyway”

Output must end with one of:
- "STRUCTURE OK — PROCEED"
- "STRUCTURE BROKEN — ESCALATE"
CODING AGENT RULEBOOK
FOR MARKET REGIME MASTERFRAME IMPLEMENTATION
================================================

PURPOSE
-------
This rulebook defines NON-NEGOTIABLE constraints and development rules
for implementing the Market Regime Masterframe system.

The agent MUST follow these rules exactly.
Violations invalidate the implementation.

------------------------------------------------
SECTION 1 — GENERAL PRINCIPLES
------------------------------------------------

RULE 1.1 — NO INTERPRETATION
The agent must not reinterpret, simplify, or "improve" trading logic.
All logic must be implemented exactly as specified.

If a rule is unclear, STOP and request clarification.
Never guess.

RULE 1.2 — DETERMINISM ONLY
All decisions must be deterministic.
No randomness, heuristics, or probabilistic shortcuts are allowed
unless explicitly specified.

RULE 1.3 — NO DATA LEAKAGE
No future data may be accessed at any point.
All rolling calculations must use only past and current data.

RULE 1.4 — EXPLICIT STATES ONLY
All strategy logic must be implemented via explicit state machines.
Boolean flags are not acceptable substitutes for states.

------------------------------------------------
SECTION 2 — ARCHITECTURE REQUIREMENTS
------------------------------------------------

RULE 2.1 — SINGLE MASTER CONTROLLER
There must be exactly ONE master controller responsible for:
- Regime classification
- Strategy enable/disable
- Mutual exclusion enforcement

Strategies must never self-activate.

RULE 2.2 — MUTUAL EXCLUSION ENFORCEMENT
At no time may SLBRS and EFFCS be active simultaneously.
This must be enforced at the controller level, not inside strategies.

RULE 2.3 — HARD REGIME GATES
Strategies may not evaluate setups unless their regime is active.
No “pre-warming”, no background scanning.

------------------------------------------------
SECTION 3 — DATA HANDLING RULES
------------------------------------------------

RULE 3.1 — ORDERBOOK COMPRESSION
Raw orderbook snapshots must NOT be used directly in decision logic.
They must be aggregated into defined zones before any use.

RULE 3.2 — TIME ALIGNMENT
All data streams must be explicitly time-aligned.
If timestamps do not align, the system must skip evaluation.

RULE 3.3 — ROLLING WINDOWS
All rolling metrics must:
- Have fixed window sizes
- Explicitly handle warm-up periods
- Return NULL until fully initialized

The system must NOT trade while any required metric is NULL.

------------------------------------------------
SECTION 4 — REGIME CLASSIFICATION
------------------------------------------------

RULE 4.1 — REGIME IS A GATE, NOT A SIGNAL
Regime classification only enables or disables strategies.
It must never generate trades.

RULE 4.2 — ALL CONDITIONS REQUIRED
If a regime requires N conditions, ALL must be true.
No partial activation.

RULE 4.3 — TRANSITION HANDLING
If regime conditions are not clearly met:
- Set state to DISABLED
- Cancel all pending setups
- Do not carry over partial states

------------------------------------------------
SECTION 5 — STATE MACHINE RULES
------------------------------------------------

RULE 5.1 — NO STATE SKIPPING
State transitions must follow the defined order exactly.
Direct jumps are forbidden.

RULE 5.2 — RESET ON INVALIDATION
Any invalidation condition must immediately:
- Exit position if in trade
- Reset strategy state
- Enter cooldown if specified

RULE 5.3 — SINGLE ACTIVE SETUP
At most ONE setup may exist per strategy at any time.
New setups must be ignored until current setup resolves or resets.

------------------------------------------------
SECTION 6 — ENTRY & EXIT RULES
------------------------------------------------

RULE 6.1 — SINGLE ENTRY POINT
Each strategy has exactly ONE allowed entry condition.
No secondary, fallback, or emergency entries.

RULE 6.2 — NO RETROACTIVE ENTRIES
The agent must not enter trades based on past conditions.
All entries must trigger in real time.

RULE 6.3 — IMMEDIATE INVALIDATION
If an invalidation condition triggers:
- Exit immediately at market
- Do not wait for bar close
- Do not average or hedge

------------------------------------------------
SECTION 7 — RISK MANAGEMENT
------------------------------------------------

RULE 7.1 — STOPS ARE STRUCTURAL
Stops must be placed exactly as specified.
Fixed-percentage or discretionary stops are forbidden.

RULE 7.2 — TARGETS MUST BE VALIDATED
Before entering a trade:
- Target must exist
- Reward/Risk constraint must be satisfied
If not, the trade must be rejected.

RULE 7.3 — NO POSITION SCALING
No adding, reducing, or pyramiding positions.
Each trade is single-entry, single-exit.

------------------------------------------------
SECTION 8 — COOLDOWN & FAIL-SAFES
------------------------------------------------

RULE 8.1 — COOLDOWN IS ABSOLUTE
During cooldown:
- No setup detection
- No state evaluation
- No background scanning

RULE 8.2 — HARD KILL OVERRIDES ALL
If a hard kill condition is met:
- Disable entire system
- Do not re-enable automatically
- Require manual reset

------------------------------------------------
SECTION 9 — LOGGING (MANDATORY)
------------------------------------------------

RULE 9.1 — LOG EVERYTHING REQUIRED
All specified metrics must be logged per trade.
Missing logs invalidate the implementation.

RULE 9.2 — LOG DECISIONS, NOT JUST TRADES
The system must log:
- Regime changes
- Setup invalidations
- State transitions
- Kill-switch triggers

------------------------------------------------
SECTION 10 — TESTING REQUIREMENTS
------------------------------------------------

RULE 10.1 — STATE UNIT TESTS
Each state transition must have unit tests covering:
- Valid transition
- Invalid transition
- Forced reset

RULE 10.2 — REGIME BOUNDARY TESTS
The agent must test behavior at regime boundaries:
- Sideways → Expansion
- Expansion → Disabled
- Disabled → Sideways

RULE 10.3 — NO PERFORMANCE OPTIMIZATION FIRST
Correctness is mandatory before performance tuning.
Do not optimize early.

------------------------------------------------
SECTION 11 — FORBIDDEN ACTIONS
------------------------------------------------

The agent must NOT:
- Add indicators not specified
- Modify thresholds without instruction
- Merge strategies
- Use ML or statistical fitting
- Introduce discretionary logic
- Trade during unclear regimes

------------------------------------------------
SECTION 12 — FAILURE HANDLING
------------------------------------------------

RULE 12.1 — FAIL CLOSED
If any required data is missing, delayed, or invalid:
- Do not trade
- Do not guess
- Do not interpolate

RULE 12.2 — VISIBILITY OVER CONTINUITY
It is better to stop trading than to trade incorrectly.

------------------------------------------------
FINAL INSTRUCTION
------------------------------------------------

The goal is NOT to trade often.
The goal is NOT to be clever.
The goal is to execute EXACTLY what is specified,
only when conditions are structurally valid.

If unsure — STOP.


END OF RULEBOOK
================================================