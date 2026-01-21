STRATEGY STATE MACHINE SPECIFICATION
Formal Definition of All Strategy States and Transitions

This document defines the exact state machines for Geometry, Kinematics, and Cascade strategies.

Every state, transition, and invalidation condition is specified precisely.
These are the contracts that implementations must satisfy.

Violating these state machines breaks determinism.

---

GENERAL STATE MACHINE PRINCIPLES

These apply to ALL strategies.

Rule 1: No State Skipping

States must transition in order.
Direct jumps are forbidden.

Example (correct):
DISABLED → SCANNING → ARMED → ENTERED → EXITED → COOLDOWN → DISABLED

Example (forbidden):
DISABLED → ARMED (skipped SCANNING)
ENTERED → DISABLED (skipped EXITED and COOLDOWN)

Rule 2: Single Active Setup

At most ONE setup may exist per strategy at any time.

If in ARMED state and new setup appears:
  Ignore it
  Current setup takes precedence

Rule 3: Reset on Invalidation

Any invalidation condition immediately triggers:

If in ENTERED:
  Exit position at market
  Transition to EXITED
  Then COOLDOWN

If in ARMED:
  Cancel pending order
  Transition to DISABLED
  Then COOLDOWN

Rule 4: Cooldown Is Absolute

During cooldown:

No setup detection
No state evaluation
No background scanning

The strategy is frozen.

Rule 5: Logging Is Mandatory

Every state transition must log:

Timestamp
Previous state
New state
Trigger reason
Relevant metrics (OI, funding, depth, etc.)

---

GEOMETRY STRATEGY STATE MACHINE

Purpose: Trade failed liquidation hunts in sideways regime

States: 6
Transitions: 8
Invalidation Conditions: 4

STATE DEFINITIONS

State: DISABLED

Entry conditions:
  - Regime != SIDEWAYS
  - Strategy disabled by controller
  - Cooldown expired and conditions not met

Behavior:
  - No scanning
  - No evaluation
  - Return immediately

Exit conditions:
  - Regime == SIDEWAYS
  - Controller enables strategy

State: SCANNING

Entry conditions:
  - Regime == SIDEWAYS
  - Strategy enabled
  - No active setup
  - Not in cooldown

Behavior:
  - Monitor OI
  - Monitor funding skew
  - Watch for aggressive push toward liq band
  - Check depth thinning

Exit conditions:
  - Setup detected (→ ARMED)
  - Regime changes (→ DISABLED)
  - Invalidation (→ COOLDOWN)

State: ARMED

Entry conditions:
  - Valid setup detected
  - All preconditions satisfied:
    * OI elevated (> baseline + threshold)
    * Funding skewed (> threshold)
    * Aggressive push detected
    * Depth thinned on target side
    * Price approaching liq band
    * Hunter wallet active (if tracking enabled)

Behavior:
  - Monitor for liquidation cascade trigger
  - Watch OI collapse
  - Prepare entry order
  - Calculate stop and target

Exit conditions:
  - Cascade triggers (→ ENTERED)
  - Setup invalidates (→ COOLDOWN)
  - Timeout (→ COOLDOWN)

State: ENTERED

Entry conditions:
  - OI collapses sharply (> threshold)
  - Funding stops accelerating
  - Aggressive orders flip side
  - Entry order filled

Behavior:
  - Monitor position
  - Track invalidation conditions
  - Update stop if needed
  - Watch for target

Exit conditions:
  - Target hit (→ EXITED)
  - Stop hit (→ EXITED)
  - Invalidation (→ EXITED)
  - Time stop (→ EXITED)

State: EXITED

Entry conditions:
  - Position closed (any reason)

Behavior:
  - Log trade metrics
  - Calculate PnL
  - Record invalidation reason (if applicable)

Exit conditions:
  - Logging complete (→ COOLDOWN)

State: COOLDOWN

Entry conditions:
  - Trade completed
  - Setup invalidated
  - Error occurred

Behavior:
  - Freeze for N bars
  - No scanning
  - No evaluation

Exit conditions:
  - Cooldown period elapsed (→ DISABLED)

TRANSITION TABLE

From         To           Trigger
-----------  -----------  ----------------------------------
DISABLED     SCANNING     Regime == SIDEWAYS AND enabled
SCANNING     ARMED        Valid setup detected
SCANNING     DISABLED     Regime != SIDEWAYS
SCANNING     COOLDOWN     Invalidation condition
ARMED        ENTERED      Cascade triggered
ARMED        COOLDOWN     Setup invalidated OR timeout
ENTERED      EXITED       Target/stop/invalidation
EXITED       COOLDOWN     Logging complete
COOLDOWN     DISABLED     Cooldown elapsed

INVALIDATION CONDITIONS

Invalidation 1: OI Rebuild Failure

If in ARMED:
  If OI recovers (moves back above trigger threshold):
    Invalidate setup
    Transition to COOLDOWN

Reason:
Leverage rebuilt, hunt failed

Invalidation 2: Hunter Wallet Exit

If in ARMED:
  If manipulator wallet exits position:
    Invalidate setup
    Transition to COOLDOWN

Reason:
Hunt abandoned

Invalidation 3: Regime Change

If in ARMED OR ENTERED:
  If regime != SIDEWAYS:
    Exit position if in ENTERED
    Transition to COOLDOWN

Reason:
Strategy assumptions violated

Invalidation 4: Time Stop

If in ENTERED:
  If time in position > max_hold_time:
    Exit position
    Transition to EXITED

Reason:
Mean reversion failed

SETUP DETECTION LOGIC

A valid setup requires ALL of:

Structural preconditions:
  OI > baseline + 2 std dev
  Funding skew > 0.01% per hour
  Price within 5% of suspected liq band

Localization:
  Repeated failed attempts at same level
  Depth asymmetry (bid/ask ratio > 2:1 or < 0.5:1)

Microstructure:
  Aggressive orders consuming depth
  Passive liquidity canceling ahead of price
  Market orders not moving price efficiently

Optional (if wallet tracking enabled):
  Known manipulator wallet active
  Wallet direction aligns with push

ENTRY LOGIC

Entry triggers when:

OI drops > 5% in < 10 seconds
Aggressive orders flip side
Funding stops accelerating

Entry order:
Market order
Opposite direction of push

Stop placement:
Recent swing high/low
Or fixed % (2%)

Target placement:
Mean reversion target
Or R:R ratio (2:1 minimum)

EXIT LOGIC

Normal exits:

Target hit: Take profit
Stop hit: Cut loss
Time stop: Exit at market after N minutes

Invalidation exits:

OI rebuilds: Close immediately
Regime changes: Close immediately
Funding reversal: Close immediately

---

KINEMATICS STRATEGY STATE MACHINE

Purpose: Trade post-liquidation inventory distribution in sideways regime

States: 6 (same structure as Geometry)
Transitions: 8
Invalidation Conditions: 3

STATE DEFINITIONS

(Structure identical to Geometry, differences noted below)

State: SCANNING

Behavior differences:
  - Watch for completed liquidation cascades
  - Monitor volume compression
  - Track book refill behavior
  - Detect inventory overhang

State: ARMED

Entry conditions (different from Geometry):
  - Recent liquidation cascade completed (OI collapsed)
  - Price stabilized (range compression)
  - Volume elevated but range tight
  - Book refilling on both sides
  - Hunter wallet switching to passive orders (if tracking enabled)

Behavior:
  - Monitor range expansion trigger
  - Prepare entry order
  - Calculate stop and target

State: ENTERED

Entry conditions:
  - Range expansion breakout detected
  - Volume confirms direction
  - Entry order filled

INVALIDATION CONDITIONS

Invalidation 1: Range Collapse

If in ARMED:
  If range compresses further (< threshold):
    Invalidate setup
    Transition to COOLDOWN

Reason:
Inventory distribution stalled

Invalidation 2: OI Spike

If in ARMED OR ENTERED:
  If OI suddenly increases (> threshold):
    Exit if in ENTERED
    Transition to COOLDOWN

Reason:
New leverage entering, invalidates distribution assumption

Invalidation 3: Regime Change

(Same as Geometry)

SETUP DETECTION LOGIC

A valid setup requires ALL of:

Post-cascade state:
  OI dropped > 5% in recent window (< 1 hour)
  Price stabilized (< 1% range for > 10 minutes)
  Volume elevated (> baseline)

Compression signs:
  Range tightening
  Book depth balanced
  Funding stabilizing

Optional (if wallet tracking enabled):
  Hunter wallet still active
  Execution switching passive (limit orders)

ENTRY LOGIC

Entry triggers when:

Range expands beyond compression bounds
Volume surge confirms breakout
Direction aligns with higher-timeframe bias

Entry order:
Market order
Direction of expansion

Stop placement:
Opposite edge of compression range

Target placement:
Expansion target (N × range)
Or R:R ratio (2:1 minimum)

---

CASCADE SNIPER STATE MACHINE

Purpose: Front-run liquidation cascade inevitability in expansion regime

States: 7 (additional state: PRE_ARMED)
Transitions: 10
Invalidation Conditions: 5

This is the most complex strategy.

STATE DEFINITIONS

State: DISABLED

(Same as Geometry)

State: SCANNING

Entry conditions:
  - Regime == EXPANSION
  - Strategy enabled
  - No active setup

Behavior:
  - Monitor depth vs estimated liquidation size
  - Watch liquidity withdrawal
  - Track passive participants stepping away
  - Calculate liquidation inevitability threshold

State: PRE_ARMED

Entry conditions:
  - Liquidation bands detected (clustered leverage near price)
  - Liquidity thinning detected
  - Depth approaching critical threshold

Behavior:
  - Calculate exact inevitability point
  - Prepare entry order
  - Monitor for final trigger

This state exists to separate detection from commitment.

State: ARMED

Entry conditions:
  - Remaining depth < expected liquidation volume
  - Liquidity inevitability threshold crossed
  - Optional: Hunter wallet activated

Behavior:
  - Ready to enter on cascade trigger
  - Monitor for price acceleration into liq band

State: ENTERED

Entry conditions:
  - Cascade triggered
  - Entry order filled

Behavior:
  - Monitor for liquidation exhaustion
  - Track OI collapse
  - Prepare exit

State: EXITED

(Same as Geometry)

State: COOLDOWN

(Same as Geometry)

TRANSITION TABLE

From         To           Trigger
-----------  -----------  ----------------------------------
DISABLED     SCANNING     Regime == EXPANSION AND enabled
SCANNING     PRE_ARMED    Liquidation bands detected
SCANNING     DISABLED     Regime != EXPANSION
SCANNING     COOLDOWN     Invalidation
PRE_ARMED    ARMED        Inevitability threshold crossed
PRE_ARMED    COOLDOWN     Setup invalidated
ARMED        ENTERED      Cascade triggered
ARMED        COOLDOWN     Setup invalidated OR timeout
ENTERED      EXITED       Exhaustion detected OR invalidation
EXITED       COOLDOWN     Logging complete
COOLDOWN     DISABLED     Cooldown elapsed

INVALIDATION CONDITIONS

Invalidation 1: Liquidity Refill

If in PRE_ARMED or ARMED:
  If depth suddenly refills (> threshold):
    Invalidate setup
    Transition to COOLDOWN

Reason:
Inevitability broken, hunt unlikely

Invalidation 2: OI Collapse Without Entry

If in ARMED:
  If OI collapses but entry not triggered:
    Invalidate setup
    Transition to COOLDOWN

Reason:
Missed entry, do not chase

Invalidation 3: Cascade Completion

If in ENTERED:
  If OI drops sharply (liquidations exhausted):
    Exit position
    Transition to EXITED

Reason:
Reversal imminent

Invalidation 4: Volume Exhaustion

If in ENTERED:
  If volume spike with no further extension:
    Exit position
    Transition to EXITED

Reason:
Cascade ending

Invalidation 5: Regime Change

(Same as Geometry, Kinematics)

SETUP DETECTION LOGIC

A valid setup requires ALL of:

Structural preconditions:
  OI elevated and rising
  Funding skewed and accelerating
  Price approaching liq band

Liquidation band localization:
  Round-number magnetism detected
  Repeated tests of same level
  Heavy resting liquidity just past key price

Inevitability calculation:
  Estimated liq size > remaining depth
  Liquidity withdrawal detected
  Depth / liq ratio < threshold (e.g. 0.5)

Optional (if wallet tracking enabled):
  Known hunter wallet initiating push
  First trade detected (clock start)

ENTRY LOGIC

Entry triggers when:

Cascade begins (aggressive push into band)
Price acceleration detected
OI starting to collapse

Entry order:
Market order
Same direction as cascade

Stop placement:
Tight (1-2%)
Below/above liq band edge

Target placement:
Liquidation exhaustion point
Or fixed R:R (1.5:1 minimum)

EXIT LOGIC

Normal exits:

Exhaustion conditions:
  - OI drops sharply
  - Volume spike without extension
  - Aggressive orders stop

Invalidation exits:

Cascade stalls: Exit immediately
Depth refills: Exit immediately
Time stop: Exit after N seconds

This is a fast strategy. Hold times << 1 minute typical.

---

SHARED STATE MACHINE ENFORCEMENT RULES

Rule 1: No Bypass

Strategies cannot skip states.
Controllers cannot force state jumps.

Rule 2: Reset Always Via Cooldown

All resets must pass through COOLDOWN.

Exception:
  DISABLED → SCANNING (initialization)

Rule 3: One Active Setup Per Strategy

If strategy has active setup (ARMED or ENTERED):
  New setups ignored until current setup resolves

Rule 4: Regime Override

If regime changes:
  All strategies of wrong regime immediately reset
  No exceptions

Rule 5: Emergency Kill Switch

If hard kill condition triggers:
  All strategies → DISABLED
  No auto-recovery
  Require manual reset

---

STATE PERSISTENCE

Between restarts, strategies must save:

Current state
Active setup (if any)
Cooldown expiration time
Recent trade history (for baseline calculations)

On restart:

Restore state
Validate setup still valid
If not, reset to DISABLED

Do not resume without validation.

---

TESTING REQUIREMENTS

For each strategy, unit tests must cover:

Valid Transitions:
  - Test each valid state transition
  - Verify state updates correctly
  - Verify logging occurs

Invalid Transitions:
  - Attempt invalid transitions
  - Verify rejected
  - Verify error logged

Invalidation Conditions:
  - Trigger each invalidation
  - Verify immediate response
  - Verify correct state transition

Setup Detection:
  - Valid setup detected correctly
  - Invalid setup rejected
  - Partial conditions do not trigger

Cooldown:
  - Strategy frozen during cooldown
  - No scanning occurs
  - Correct duration

Replay Determinism:
  - Same inputs → same outputs
  - Same state transitions
  - Same trade decisions

---

STATE MACHINE VISUALIZATION

Geometry/Kinematics:

    ┌──────────┐
    │ DISABLED │←──────────────┐
    └─────┬────┘               │
          │                    │
          ↓                    │
    ┌──────────┐               │
    │ SCANNING │←───┐          │
    └─────┬────┘    │          │
          │         │          │
          ↓         │  ┌───────┴─────┐
    ┌──────────┐    │  │  COOLDOWN   │
    │  ARMED   │    │  └───────△─────┘
    └─────┬────┘    │          │
          │         │          │
          ↓         │          │
    ┌──────────┐    │          │
    │ ENTERED  │    │          │
    └─────┬────┘    │          │
          │         │          │
          ↓         │          │
    ┌──────────┐    │          │
    │  EXITED  │────┘──────────┘
    └──────────┘

Cascade (has PRE_ARMED):

    ┌──────────┐
    │ DISABLED │←──────────────┐
    └─────┬────┘               │
          │                    │
          ↓                    │
    ┌──────────┐               │
    │ SCANNING │←───┐          │
    └─────┬────┘    │          │
          │         │          │
          ↓         │  ┌───────┴─────┐
    ┌───────────┐   │  │  COOLDOWN   │
    │ PRE_ARMED │   │  └───────△─────┘
    └─────┬─────┘   │          │
          │         │          │
          ↓         │          │
    ┌──────────┐    │          │
    │  ARMED   │    │          │
    └─────┬────┘    │          │
          │         │          │
          ↓         │          │
    ┌──────────┐    │          │
    │ ENTERED  │    │          │
    └─────┬────┘    │          │
          │         │          │
          ↓         │          │
    ┌──────────┐    │          │
    │  EXITED  │────┘──────────┘
    └──────────┘

---

IMPLEMENTATION CHECKLIST

For each strategy:

[ ] State enum defined
[ ] Transition logic implemented
[ ] Invalidation conditions implemented
[ ] Setup detection logic implemented
[ ] Entry logic implemented
[ ] Exit logic implemented
[ ] State persistence implemented
[ ] Logging implemented
[ ] Unit tests written
[ ] Integration tests written
[ ] Replay tests passing

Until all items checked:
  Strategy is not production-ready

---

BOTTOM LINE

State machines are the contract between design and implementation.

Every state transition must be:
  - Explicit
  - Tested
  - Logged
  - Deterministic

No shortcuts.
No implicit transitions.
No state skipping.

The complexity is necessary to maintain correctness under stress.

If the state machine is not followed exactly:
  The system is unpredictable
  The rulebook is violated
  Trading becomes random
