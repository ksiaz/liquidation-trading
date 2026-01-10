# POSITION, RISK & EXECUTION CONSTITUTION
Version: v0.1 (Foundational)
Status: Active – Extend Only
Scope: Position management, risk constraints, mandate execution

---

## 0. PURPOSE & PHILOSOPHY

This document defines **hard invariants and mechanical rules** governing:

- Position existence
- Risk exposure
- Leverage bounds
- Mandate execution
- Partial vs full exits

This system is:
- Reactive, not predictive
- Constraint-driven, not confidence-driven
- Mechanically enforced, not interpretive

No section in this document explains *why* to trade.
It defines *what is allowed* and *what is forbidden*.

---

## 1. POSITION & RISK CONSTRAINTS (INVARIANTS)

These rules are **absolute** and may never be violated.

### 1.1 One Position per Symbol
- At most **one open position per symbol**
- ENTER is forbidden if a position already exists
- Opposite-direction entry requires full EXIT first

---

### 1.2 Fixed Risk per Position
- Each position has a **maximum risk budget** (e.g., 1% of account)
- Risk is defined as loss at stop, not notional size
- Risk may decrease over time, never increase beyond initial

---

### 1.3 Exposure Invariant
- Per-symbol exposure ≤ symbol exposure cap
- Cross-symbol correlated exposure ≤ global cap
- If violated, only REDUCE or EXIT permitted

---

### 1.4 Liquidation Distance Invariant
- Every position must maintain a minimum liquidation buffer
- Any action reducing buffer below minimum is forbidden
- Applies to ENTER, ADD, and leverage changes

---

### 1.5 Time-Based Invariants
- Certain windows forbid ENTER and ADD
- REDUCE and EXIT are always allowed
- HOLD is always allowed

---

## 2. POSITION LIFECYCLE STATES

Positions exist in **exactly one** state.

```text
FLAT → OPEN → PARTIAL → CLOSED

2.1 State Definitions

    FLAT

        No position exists

    OPEN

        Full position active

        Risk ≤ initial allocation

    PARTIAL

        Position reduced

        Remaining risk < initial

    CLOSED

        No exposure remains

No other states are permitted.
3. POSITION STATE TRANSITIONS
Action	From	To
ENTER	FLAT	OPEN
ADD	OPEN / PARTIAL	OPEN
REDUCE (partial)	OPEN	PARTIAL
REDUCE (full)	OPEN / PARTIAL	CLOSED
EXIT	OPEN / PARTIAL	CLOSED
HOLD	Any	Unchanged

Invalid transitions are forbidden.
4. MANDATE TYPES (INTENT ONLY)

Mandates express allowed intent, not execution certainty.
4.1 ENTER

    Intent to open a new position

    Requires FLAT state

4.2 ADD

    Intent to increase existing position

    Must not increase total risk

    Direction must match existing position

4.3 REDUCE

    Intent to partially de-risk

    May be triggered by:

        Liquidity zones

        Risk compression

        Exposure pressure

4.4 EXIT

    Intent to fully close position

    Overrides all other mandates

4.5 HOLD

    Explicit non-action

    Blocks lower-priority mandates

5. MULTIPLE MANDATES (ALLOWED)

Multiple mandates may be active simultaneously.

Examples:

    REDUCE + EXIT

    ADD + HOLD

    ENTER + HOLD (ENTER suppressed)

Mandates do not imply execution.
6. MANDATE PRIORITY (FIXED)

When multiple mandates exist:

EXIT
↓
REDUCE
↓
ADD
↓
ENTER
↓
HOLD

Higher-priority mandates suppress lower ones.
7. PARTIAL VS FULL EXIT RESOLUTION

Liquidity-related conditions may trigger either REDUCE or EXIT.
Resolution Rules

EXIT is executed only if:

    PositionState == INVALIDATED

    Liquidation buffer < hard minimum

    Risk invariants are breached

Otherwise:

    REDUCE executes

    EXIT suppressed

This allows:

    Partial exits near liquidity zones

    Full exits during structural invalidation

8. LEVERAGE & RISK COUPLING

Leverage is derived, not fixed.
Rules:

    Leverage chosen to satisfy:

        Risk budget

        Stop distance

        Liquidation buffer

    Increasing leverage must not reduce liquidation buffer

    Leverage may decrease automatically via REDUCE

9. EXECUTION INPUT BOUNDARY

Execution receives only:

    MandateType

    PositionState

    CurrentPosition (if any)

    RiskEnvelope

    ExposureState

Execution does not receive:

    Raw market data

    Signals or indicators

    Narrative context

    Historical reasoning

10. EXECUTION GUARDS & SIZE RESOLUTION

Execution occurs only if all guards pass.
10.1 Global Execution Guards

    One position per symbol

    Directional coherence

    Liquidation buffer invariant

    Exposure caps

    Time restrictions

Failure → mandate dropped silently.
10.2 ENTER Execution

    Size derived from:

        Fixed risk %

        Stop distance

        Liquidation buffer

    If no safe size exists → no execution

10.3 ADD Execution

    Only if:

        Risk after add ≤ initial risk

        Liquidation buffer stable or improved

    ADD size capped (e.g., ≤ 25% initial size)

10.4 REDUCE Execution

    Always allowed

    Size may be:

        Fixed fraction

        Risk-normalization amount

        Exposure-based amount

10.5 EXIT Execution

    Always allowed

    Closes entire position

    No sizing logic

10.6 HOLD

    No execution

    No state change

11. SINGLE EXECUTION RULE

Only one execution action may occur per cycle.

If top-priority mandate fails guards:

    Drop it

    Evaluate next

12. WHAT THIS SYSTEM NEVER DOES

    No prediction

    No signal ranking

    No confidence scoring

    No “best trade” selection

    No discretionary overrides

All behavior is constrained by invariants.
13. EXTENSION POLICY

This document may be:

    Extended

    Refined

    Made more explicit

It may never:

    Remove invariants

    Introduce interpretation

    Allow execution without constraints

All future sections must preserve prior guarantees.

## 11. CONDITION PRIMITIVES & MEMORY FACTS

This section defines **primitive conditions** extracted from research, market microstructure logic, and canonical technical analysis.

Primitives are:
- Binary or scalar facts
- Non-predictive
- Context-free
- Usable across mandates without embedding intent

They do **not** imply ENTER, EXIT, REDUCE, or HOLD by themselves.

---

## 11.1 PRICE STRUCTURE PRIMITIVES

### 11.1.1 Structure Break
- PRICE_BREAK_HIGH
- PRICE_BREAK_LOW

Definition:
- Current price exceeds a previously defined structural extreme
- No timeframe implied

---

### 11.1.2 Range Integrity
- RANGE_HOLDING
- RANGE_BROKEN

Definition:
- Price remains within / exits a defined high–low boundary

---

### 11.1.3 Equal Extremes
- EQUAL_HIGHS_PRESENT
- EQUAL_LOWS_PRESENT

Definition:
- Two or more comparable highs/lows within tolerance

---

## 11.2 LIQUIDITY & STOP-HUNT PRIMITIVES

### 11.2.1 Historical Liquidity Region
- LIQUIDITY_CLUSTER_EXISTS(region)
- LIQUIDITY_CLUSTER_RECENT(region)

Derived from:
- Prior liquidation cascades
- Prior stop runs
- Repeated spike-and-reverse behavior

---

### 11.2.2 Stop-Hunt Evidence
- STOP_HUNT_OCCURRED(region)

Definition:
- Price moves through known liquidity region and rapidly rejects

---

### 11.2.3 Liquidity Sweep Without Continuation
- LIQUIDITY_SWEPT_NO_FOLLOWTHROUGH

Used to detect:
- Failed continuation
- Potential exhaustion

---

## 11.3 LIQUIDATION-BASED PRIMITIVES

### 11.3.1 Historical Liquidation Cascade
- PAST_LIQUIDATION_CASCADE(region, side)

Definition:
- High-density forced closures occurred in the past in this region

---

### 11.3.2 Active Liquidation Events
- LIQUIDATIONS_SPIKING(side)
- LIQUIDATIONS_ACCELERATING(side)

Definition:
- Forced closures occurring faster than baseline

---

### 11.3.3 Cascade Exhaustion
- LIQUIDATION_CASCADE_EXHAUSTED

Derived when:
- Liquidations spike
- Price velocity stalls or reverses

---

## 11.4 PRICE VELOCITY & ENERGY PRIMITIVES

### 11.4.1 High Velocity Move
- PRICE_VELOCITY_HIGH

Definition:
- Rapid displacement over short time

---

### 11.4.2 Velocity Decay
- PRICE_VELOCITY_DECELERATING

Often paired with:
- Absorption
- Liquidity interaction

---

### 11.4.3 Impulse vs Compression
- IMPULSE_PHASE
- COMPRESSION_PHASE

Impulse:
- Large displacement, thin interaction

Compression:
- Tight range, heavy interaction

---

## 11.5 ORDER FLOW & ABSORPTION PRIMITIVES

### 11.5.1 Absorption Present
- ABSORPTION_DETECTED(side)

Definition:
- Large opposing volume absorbs aggressive flow
- Price fails to advance despite pressure

---

### 11.5.2 Large Orders Detected
- LARGE_LIMIT_ORDERS_PRESENT(region)
- LARGE_MARKET_ORDERS_PRESENT(side)

---

### 11.5.3 Absorption + Liquidations Correlation
- LIQUIDATIONS_WITH_ABSORPTION

Highly relevant for:
- Partial exit logic
- Risk tightening

---

## 11.6 ZONE-BASED PRIMITIVES

### 11.6.1 Entry Zone
- ENTRY_ZONE_ACTIVE(region)

Region types:
- Demand
- Supply
- Liquidity void
- Prior imbalance

---

### 11.6.2 Exit Zone
- EXIT_ZONE_ACTIVE(region)

Exit zones may overlap:
- Liquidity regions
- Absorption zones
- Prior cascade regions

---

### 11.6.3 Zone Reaction
- ZONE_HOLD
- ZONE_REJECT
- ZONE_FAILURE

---

## 11.7 TIME & SESSION PRIMITIVES

### 11.7.1 Session State
- SESSION_OPEN
- SESSION_MID
- SESSION_CLOSE

---

### 11.7.2 High-Risk Windows
- NEWS_WINDOW_ACTIVE
- ROLLOVER_WINDOW_ACTIVE

These primitives **only restrict ENTER/ADD**, never EXIT.

---

## 11.8 POSITION-RELATIVE PRIMITIVES

### 11.8.1 Position Context
- POSITION_IN_PROFIT
- POSITION_AT_RISK
- POSITION_NEAR_LIQUIDATION

---

### 11.8.2 Risk Compression
- RISK_BUFFER_SHRINKING
- RISK_BUFFER_STABLE

---

### 11.8.3 Opposite Conditions While In Position
- OPPOSITE_LIQUIDITY_TRIGGERED
- OPPOSITE_STRUCTURE_BREAK

These never auto-trigger reversal.
They only influence REDUCE or EXIT eligibility.

---

## 11.9 MEMORY PRIMITIVES (NON-INTERPRETIVE)

Memory is **fact storage**, not belief.

### Examples:
- REGION_HAS_HISTORY_OF_LIQUIDATIONS
- REGION_HAS_HISTORY_OF_ABSORPTION
- REGION_HAS_HISTORY_OF_REVERSALS

Memory facts:
- Do not decay unless explicitly defined
- Do not imply future behavior
- Only modify mandate resolution, not creation

---

## 11.10 PRIMITIVE DESIGN RULES

- Primitives must be:
  - Observable
  - Testable
  - Non-predictive
- No primitive may encode:
  - Bias
  - Directional intent
  - Trade desirability
- Primitives may conflict simultaneously

Resolution happens **outside** this section.

---

## 11.11 EXPLICIT NON-GOALS

This section does NOT:
- Decide trades
- Rank conditions
- Assign confidence
- Encode narrative
- Resolve contradictions

It only defines **what can be known as a fact**.

---

END OF SECTION 11
## 12. MANDATE GENERATION RULES

This section defines **how mandates may be generated** from condition primitives.

Mandates are:
- Permissions to act
- Not obligations
- Not predictions
- Not strategies

A mandate expresses:  
**“Given these observable facts, this category of action is allowed to be considered.”**

---

## 12.1 WHAT A MANDATE IS (FORMAL DEFINITION)

A mandate is a structured declaration with:

- Type (ENTER / ADD / REDUCE / EXIT / HOLD / BLOCK)
- Scope (symbol-specific)
- Direction (LONG / SHORT / BOTH / NONE)
- Constraints (what it cannot violate)
- Preconditions (primitive sets that must be true)

A mandate does **not**:
- Choose size
- Choose price
- Choose timing
- Override risk invariants

---

## 12.2 MANDATE TYPES (CANONICAL SET)

### 12.2.1 ENTER
Permission to open a new position.

Generated only if:
- No existing position on symbol
- All position & risk invariants satisfied
- No BLOCK mandate active

---

### 12.2.2 ADD
Permission to increase exposure on an existing position.

Generated only if:
- Position exists
- Exposure invariants allow increase
- Risk buffer remains valid

---

### 12.2.3 REDUCE
Permission to partially decrease exposure.

Key property:
- REDUCE is **always allowed**
- REDUCE never requires justification
- REDUCE never violates invariants

---

### 12.2.4 EXIT
Permission to fully close a position.

EXIT mandates may:
- Coexist with REDUCE
- Override ADD
- Override HOLD

---

### 12.2.5 HOLD
Explicit permission to do nothing.

Generated when:
- Primitives conflict
- No other mandate is safe
- Risk invariants advise inactivity

---

### 12.2.6 BLOCK
Prohibition mandate.

BLOCK prevents:
- ENTER
- ADD

BLOCK never prevents:
- REDUCE
- EXIT

---

## 12.3 DIRECTIONAL NEUTRALITY

Mandates may specify:

- LONG
- SHORT
- BOTH
- NONE

Important:
- Direction is **conditional**, not predictive
- “LONG” means “if acting, only long actions are allowed”

---

## 12.4 MANDATE GENERATION FROM PRIMITIVES

Mandates are generated via **pattern presence**, not interpretation.

### Example Patterns (Non-Exhaustive)

#### ENTER Eligibility Pattern
May generate ENTER if:
- ENTRY_ZONE_ACTIVE
- STRUCTURE_BREAK aligns
- No high-risk windows active
- No BLOCK present

(No direction implied unless primitives specify it.)

---

#### REDUCE Eligibility Pattern
May generate REDUCE if:
- EXIT_ZONE_ACTIVE
- LIQUIDITY_CLUSTER_EXISTS
- ABSORPTION_DETECTED
- OPPOSITE_LIQUIDITY_TRIGGERED

REDUCE does not require trend change.

---

#### EXIT Eligibility Pattern
May generate EXIT if:
- OPPOSITE_STRUCTURE_BREAK
- LIQUIDATION_CASCADE_EXHAUSTED
- POSITION_NEAR_LIQUIDATION
- RISK_BUFFER_SHRINKING

EXIT may coexist with HOLD or REDUCE.

---

#### BLOCK Pattern
Generated if:
- NEWS_WINDOW_ACTIVE
- ROLLOVER_WINDOW_ACTIVE
- MAX_EXPOSURE_REACHED
- POSITION_IN_OPPOSITE_DIRECTION_EXISTS

---

## 12.5 MULTIPLE MANDATES CAN COEXIST

At any moment, the system may produce:

- ENTER + BLOCK → ENTER suppressed
- REDUCE + EXIT → EXIT dominates
- HOLD + REDUCE → REDUCE allowed
- ADD + REDUCE → REDUCE dominates

No mandate invalidates another automatically.

Resolution occurs later.

---

## 12.6 NO SINGLE-CAUSE MANDATES

No mandate may be generated from:
- A single primitive
- A single data source
- A single timeframe

This prevents brittle behavior.

---

## 12.7 TIMEFRAME AGNOSTICISM

Mandate generation:
- Does not assume weekly/daily relevance
- Accepts primitives regardless of origin timeframe
- Allows multiple timeframe facts to coexist

Timeframes only affect **where primitives come from**, not mandate logic.

---

## 12.8 MEMORY INTEGRATION RULE

Memory primitives:
- May strengthen or weaken mandates
- May enable REDUCE earlier
- May tighten EXIT eligibility
- May NEVER force ENTER

Memory can only:
- Restrict
- De-risk
- Shorten lifecycle

---

## 12.9 POSITION-AWARE MANDATE FILTERING

Mandates must respect position state:

- ENTER forbidden if position exists
- ADD forbidden if exposure maxed
- EXIT always allowed
- REDUCE always allowed

Position lifecycle state gates mandate validity.

---

## 12.10 FAILURE & SILENCE HANDLING

If:
- Observation unavailable
- Primitives incomplete
- Data ambiguous

Then:
- HOLD or BLOCK may be generated
- ENTER and ADD suppressed
- REDUCE and EXIT remain allowed

---

## 12.11 EXPLICIT NON-GOALS

This section does NOT:
- Decide which mandate wins
- Rank mandates
- Execute actions
- Allocate size
- Infer intent

It only defines **what mandates may exist**.

---

END OF SECTION 12
## 13. MANDATE RESOLUTION & PRIORITY RULES

This section defines **how multiple coexisting mandates are resolved** into an actionable allowance set.

Resolution is:
- Deterministic
- Rule-based
- Position-aware
- Risk-first

Resolution does **not**:
- Choose price
- Choose size
- Choose timing
- Predict outcomes

It only answers:  
**“Given multiple allowed mandates, which remain valid?”**

---

## 13.1 CORE RESOLUTION PRINCIPLE

> **Risk-reducing mandates always dominate risk-increasing mandates.**

This principle is absolute and non-negotiable.

---

## 13.2 MANDATE PRIORITY ORDER (GLOBAL)

From highest to lowest priority:

1. **EXIT**
2. **REDUCE**
3. **BLOCK**
4. **HOLD**
5. **ADD**
6. **ENTER**

Lower-priority mandates are suppressed when higher-priority mandates conflict.

---

## 13.3 ABSOLUTE DOMINANCE RULES

### 13.3.1 EXIT DOMINANCE

If EXIT exists:
- EXIT survives
- All ADD, ENTER suppressed
- REDUCE optional (implementation choice)
- HOLD suppressed

EXIT is terminal for the position lifecycle.

---

### 13.3.2 REDUCE DOMINANCE

If REDUCE exists and EXIT does not:
- REDUCE survives
- ADD suppressed
- ENTER suppressed
- HOLD suppressed

REDUCE is always allowed and never blocked.

---

### 13.3.3 BLOCK DOMINANCE

If BLOCK exists:
- ENTER suppressed
- ADD suppressed
- REDUCE allowed
- EXIT allowed
- HOLD allowed

BLOCK never forces action.

---

## 13.4 HOLD AS DEFAULT STABLE STATE

HOLD:
- Is not inactivity by ignorance
- Is an explicit safe state

HOLD survives only if:
- No EXIT
- No REDUCE
- No BLOCK requiring suppression

HOLD never suppresses other mandates.

---

## 13.5 ADD VS ENTER RESOLUTION

ADD and ENTER cannot coexist by definition.

Rules:
- If position exists → ENTER invalid
- If no position exists → ADD invalid

No ambiguity allowed.

---

## 13.6 DIRECTIONAL CONFLICT RESOLUTION

If conflicting directional mandates exist:

Example:
- ENTER LONG
- ENTER SHORT

Resolution:
- ENTER suppressed
- HOLD allowed
- BLOCK may be generated

Directional ambiguity defaults to inaction.

---

## 13.7 MEMORY-BASED MODIFIERS (NON-FORCING)

Memory primitives may:
- Promote REDUCE earlier
- Promote EXIT sooner
- Downgrade ADD to HOLD
- Downgrade ENTER to HOLD

Memory primitives may NOT:
- Force ENTER
- Force ADD
- Override EXIT suppression

---

## 13.8 POSITION LIFECYCLE GATING

Mandates must be compatible with current position state:

| Position State | Allowed Mandates |
|---------------|------------------|
| NO_POSITION | ENTER, HOLD, BLOCK |
| OPEN | ADD, REDUCE, EXIT, HOLD |
| REDUCING | REDUCE, EXIT |
| EXITING | EXIT only |
| CLOSED | ENTER, HOLD |

Invalid mandates are discarded before resolution.

---

## 13.9 MULTI-MANDATE SURVIVAL SET

After resolution, the system may output:

- EXIT only
- REDUCE only
- HOLD only
- BLOCK + HOLD
- REDUCE + HOLD
- EXIT + REDUCE (optional)

It may NEVER output:
- ENTER + ADD
- ADD + REDUCE
- ENTER + BLOCK
- ADD + BLOCK

---

## 13.10 FAILURE & SILENCE OVERRIDE

If:
- Observation unavailable
- Primitives incomplete
- Mandate generation failed

Then:
- Only HOLD, REDUCE, or EXIT may survive
- ENTER and ADD forcibly removed

Silence biases toward capital preservation.

---

## 13.11 EXPLICIT NON-GOALS

This section does NOT:
- Choose which mandate executes
- Convert mandates into orders
- Decide percentages
- Decide partial vs full exit amounts
- Interpret market meaning

It only defines **which mandates remain permissible**.

---

END OF SECTION 13
## 14. POSITION LIFECYCLE STATES & TRANSITIONS

This section defines the **formal lifecycle of a position** as a finite state machine.

The lifecycle governs:
- Which mandates are admissible
- Which transitions are legal
- When actions are irreversible

It does **not**:
- Decide execution timing
- Decide order size
- Decide price
- Interpret market conditions

---

## 14.1 CORE PRINCIPLE

> A position exists in **exactly one lifecycle state at any moment**.

Transitions are:
- Explicit
- Directional
- Irreversible where specified

---

## 14.2 POSITION STATES (ENUMERATION)

### 14.2.1 NO_POSITION

Definition:
- No exposure on symbol
- No residual orders
- No partial exposure

Allowed mandates:
- ENTER
- HOLD
- BLOCK

Disallowed mandates:
- ADD
- REDUCE
- EXIT

---

### 14.2.2 OPEN

Definition:
- Active exposure exists
- Position not yet reducing
- Full lifecycle optionality remains

Allowed mandates:
- ADD
- REDUCE
- EXIT
- HOLD

Disallowed mandates:
- ENTER

---

### 14.2.3 REDUCING

Definition:
- Position size is actively decreasing
- Partial exits have occurred
- Exposure still exists

Allowed mandates:
- REDUCE
- EXIT

Disallowed mandates:
- ADD
- ENTER
- HOLD

REDUCING is **directionally monotonic**:
- Size may only decrease

---

### 14.2.4 EXITING

Definition:
- Terminal unwind initiated
- No discretionary decisions remain

Allowed mandates:
- EXIT only

Disallowed mandates:
- ADD
- ENTER
- REDUCE
- HOLD
- BLOCK

EXITING is **irreversible**.

---

### 14.2.5 CLOSED

Definition:
- Exposure fully removed
- Orders resolved
- Lifecycle complete

Allowed mandates:
- ENTER
- HOLD

Disallowed mandates:
- ADD
- REDUCE
- EXIT

CLOSED transitions immediately to NO_POSITION.

---

## 14.3 LEGAL STATE TRANSITIONS

### 14.3.1 State Transition Table

| From State | To State | Trigger |
|----------|---------|--------|
| NO_POSITION | OPEN | ENTER executed |
| OPEN | REDUCING | First REDUCE executed |
| OPEN | EXITING | EXIT executed |
| REDUCING | REDUCING | Additional REDUCE |
| REDUCING | EXITING | EXIT executed |
| EXITING | CLOSED | Exposure reaches zero |
| CLOSED | NO_POSITION | Lifecycle reset |

---

## 14.4 ILLEGAL TRANSITIONS (HARD ERRORS)

The following transitions are forbidden:

- NO_POSITION → REDUCING
- NO_POSITION → EXITING
- OPEN → NO_POSITION (must pass through EXITING)
- REDUCING → OPEN
- EXITING → OPEN
- EXITING → REDUCING
- CLOSED → REDUCING

Illegal transitions must be rejected, not corrected.

---

## 14.5 MANDATE–STATE COMPATIBILITY GATE

Before mandate resolution (Section 13):

1. Read current position state
2. Discard mandates incompatible with state
3. Resolve remaining mandates

This prevents:
- Late ADD after reduction
- Re-entry during exit
- Accidental doubling

---

## 14.6 POSITION DIRECTION INVARIANT

Direction (LONG / SHORT):

- Is fixed at ENTER
- Cannot change mid-lifecycle
- Opposite-direction ENTER requires:
  - EXIT → CLOSED → NO_POSITION → ENTER

Flip-through is forbidden.

---

## 14.7 MULTI-SYMBOL ISOLATION

Position lifecycle is evaluated:
- Per symbol
- Independently

No symbol may affect the lifecycle of another.

---

## 14.8 FAILURE & SILENCE HANDLING

If:
- Observation unavailable
- Mandate resolution returns EXIT
- System invariant violated

Then:
- OPEN → EXITING
- REDUCING → EXITING
- NO_POSITION → HOLD

Lifecycle bias is always toward **exposure reduction**.

---

## 14.9 EXPLICIT NON-GOALS

This section does NOT:
- Decide how much to reduce
- Decide partial vs full exit thresholds
- Decide timing or urgency
- Infer risk or opportunity

It defines **what is structurally allowed**, not what is chosen.

---

END OF SECTION 14
## 15. RISK & EXPOSURE ACCOUNTING INVARIANTS

This section defines **non-negotiable accounting rules** governing leverage, exposure, and liquidation safety.

These rules are:
- Deterministic
- Pre-execution
- Symbol-scoped and portfolio-scoped

They are enforced **before** mandate execution.

---

## 15.1 CORE PRINCIPLE

> Risk is constrained **before** opportunity is evaluated.

No mandate may override a violated risk invariant.

---

## 15.2 DEFINITIONS (CANONICAL)

### 15.2.1 Notional Exposure

For a position `P` on symbol `S`:

Notional(P) = |Position Size| × Mark Price


---

### 15.2.2 Account Equity

Equity = Wallet Balance + Unrealized PnL


---

### 15.2.3 Leverage (Effective)

Effective Leverage = Total Notional Exposure / Equity


This is computed:
- Per symbol
- Across portfolio

---

### 15.2.4 Liquidation Price (Abstract)

Liquidation price is treated as a **known external fact** supplied by venue logic.

This system:
- Does not compute liquidation mechanics
- Only reasons about **distance to liquidation**

---

### 15.2.5 Liquidation Distance

Liquidation Distance (%) =
|Mark Price − Liquidation Price| / Mark Price


---

## 15.3 HARD INVARIANTS (MUST HOLD)

### 15.3.1 Maximum Account Leverage

Effective Leverage ≤ MAX_LEVERAGE_ACCOUNT


Violation consequence:
- All ENTER and ADD mandates invalidated
- REDUCE / EXIT remain admissible

---

### 15.3.2 Maximum Symbol Leverage

For each symbol `S`:

Notional(S) / Equity ≤ MAX_LEVERAGE_SYMBOL


Prevents:
- Single-symbol concentration
- Cascade liquidation risk

---

### 15.3.3 Minimum Liquidation Distance

For any OPEN or REDUCING position:

Liquidation Distance ≥ MIN_LIQUIDATION_BUFFER


If violated:
- ADD forbidden
- Mandatory REDUCE or EXIT triggered

This invariant **dominates** all opportunity mandates.

---

### 15.3.4 Risk per Trade Cap

At ENTER:

Max Loss ≤ RISK_PER_TRADE × Equity


Where Max Loss is defined by:
- Entry price
- Stop definition
- Position size

If stop undefined → ENTER forbidden.

---

## 15.4 SOFT INVARIANTS (MANDATE SHAPERS)

These do not block execution but **bias mandate resolution**.

### 15.4.1 Exposure Gradient

As Effective Leverage increases:
- ADD priority decreases
- REDUCE priority increases

This is monotonic and continuous.

---

### 15.4.2 Correlated Exposure Cap

If symbols are correlated (externally defined):

Σ Notional(correlated group) ≤ MAX_CORRELATED_EXPOSURE


Violation consequence:
- ENTER forbidden on correlated symbols
- ADD forbidden
- Existing positions unaffected

---

## 15.5 ADD / REDUCE SPECIFIC RULES

### 15.5.1 ADD Constraints

ADD is allowed only if ALL hold:

- Position state == OPEN
- Liquidation Distance remains ≥ buffer after ADD
- Symbol leverage cap respected
- Account leverage cap respected

Otherwise:
- ADD mandate discarded

---

### 15.5.2 REDUCE Guarantees

REDUCE is always allowed unless:
- Position already EXITING
- No remaining exposure

REDUCE may be:
- Partial
- Progressive
- Forced (risk violation)

---

## 15.6 FORCED RISK ACTIONS

Certain invariant violations **inject mandates automatically**.

### 15.6.1 Mandatory REDUCE

Triggered when:
- Liquidation distance breached
- Leverage spike due to PnL or funding

Injected mandate:
- REDUCE (size unspecified)

---

### 15.6.2 Mandatory EXIT

Triggered when:
- Multiple invariants violated simultaneously
- Risk state deemed unrecoverable

Injected mandate:
- EXIT (terminal)

---

## 15.7 CROSS-SECTION WITH LIFECYCLE

| Lifecycle State | Risk Action Allowed |
|----------------|--------------------|
| NO_POSITION | ENTER gated by risk |
| OPEN | ADD / REDUCE / EXIT |
| REDUCING | REDUCE / EXIT only |
| EXITING | EXIT only |
| CLOSED | ENTER gated by risk |

Risk invariants may **only push lifecycle forward**, never backward.

---

## 15.8 FAILURE & SILENCE BEHAVIOR

If:
- Equity undefined
- Liquidation price unavailable
- Mark price unavailable

Then:
- ENTER forbidden
- ADD forbidden
- REDUCE permitted
- EXIT permitted

Silence defaults to **exposure minimization**.

---

## 15.9 EXPLICIT NON-GOALS

This section does NOT:
- Optimize position sizing
- Decide trade direction
- Predict volatility
- Interpret market structure

It defines **what is allowed to exist**, not what should be pursued.

---

END OF SECTION 15
## 16. MANDATE SEMANTICS (ENTER / ADD / REDUCE / EXIT)

This section defines the **formal meaning** of mandates.
Mandates are **intent declarations**, not strategies.

They do not decide *why* an action is taken — only *what action is permitted*.

---

## 16.1 MANDATE DEFINITION

A mandate is a **single, atomic instruction** applied to exactly one symbol and one position lifecycle.

Mandates:
- Are evaluated against invariants
- May be rejected silently
- Never override risk constraints
- Never interpret market conditions

---

## 16.2 MANDATE TYPES (CANONICAL SET)

The system supports exactly four mandate types:

ENTER
ADD
REDUCE
EXIT


No other mandate types are permitted.

---

## 16.3 ENTER MANDATE

### 16.3.1 Meaning

ENTER requests the creation of a **new position** on a symbol.

ENTER:
- Creates exposure
- Initializes lifecycle
- Requires full risk definition

---

### 16.3.2 Preconditions (ALL REQUIRED)

ENTER is admissible only if:

- Lifecycle state == NO_POSITION
- No open position exists for symbol
- Risk per trade invariant satisfied
- Stop definition exists
- Liquidation buffer respected
- Symbol and account leverage caps respected

If any precondition fails → ENTER is rejected.

---

### 16.3.3 Effects

If executed, ENTER:
- Transitions lifecycle → OPEN
- Establishes initial size
- Establishes direction (long / short)
- Registers stop reference (immutable)

ENTER may not:
- Scale dynamically
- Modify other positions
- Bypass invariants

---

## 16.4 ADD MANDATE

### 16.4.1 Meaning

ADD requests **increasing exposure** to an existing position.

ADD:
- Increases notional
- Increases leverage
- Does not reset lifecycle

---

### 16.4.2 Preconditions

ADD is admissible only if:

- Lifecycle state == OPEN
- Position exists
- All leverage and liquidation invariants hold *after* ADD
- No mandatory REDUCE is active

If any fail → ADD is rejected.

---

### 16.4.3 Effects

If executed, ADD:
- Increases position size
- Does NOT alter original stop reference
- Does NOT reset entry timestamp
- Does NOT change lifecycle state

ADD may not:
- Flip direction
- Remove stop
- Reset risk accounting

---

## 16.5 REDUCE MANDATE

### 16.5.1 Meaning

REDUCE requests **partial exposure reduction** of an existing position.

REDUCE:
- Decreases notional
- Decreases leverage
- Preserves position identity

---

### 16.5.2 Preconditions

REDUCE is admissible if:

- Lifecycle state ∈ {OPEN, REDUCING}
- Position size > 0

No upper risk bound blocks REDUCE.

---

### 16.5.3 Effects

If executed, REDUCE:
- Decreases size by specified or computed amount
- Transitions lifecycle → REDUCING (if not already)
- Preserves direction
- Preserves stop reference (unless size → 0)

REDUCE may be:
- Partial
- Repeated
- Forced by risk

---

## 16.6 EXIT MANDATE

### 16.6.1 Meaning

EXIT requests **complete position closure**.

EXIT:
- Removes all exposure
- Terminates lifecycle
- Is final for the position instance

---

### 16.6.2 Preconditions

EXIT is admissible if:

- Lifecycle state ∈ {OPEN, REDUCING, EXITING}

EXIT is **never blocked** by risk.

---

### 16.6.3 Effects

If executed, EXIT:
- Sets position size → 0
- Transitions lifecycle → CLOSED
- Releases symbol slot
- Finalizes PnL accounting

EXIT may not:
- Be reversed
- Be partially executed
- Be delayed by opportunity logic

---

## 16.7 MANDATE PRIORITY ORDER

When multiple mandates are admissible simultaneously:

EXIT > REDUCE > ADD > ENTER


This ordering is absolute.

Risk-driven mandates dominate opportunity-driven mandates.

---

## 16.8 CONFLICT RESOLUTION

If mandates conflict:

| Conflict | Resolution |
|-------|-----------|
| ADD vs REDUCE | REDUCE wins |
| ENTER vs EXIT | EXIT wins |
| ADD vs EXIT | EXIT wins |
| Multiple REDUCE | Largest reduction wins |

No mandate aggregation is allowed.

---

## 16.9 SILENCE & NO-OP

If:
- No mandate is admissible
- Or all mandates violate invariants

Then:
- System does nothing
- No logs
- No state mutation

Silence is a valid outcome.

---

## 16.10 EXPLICIT NON-GOALS

Mandates do NOT:
- Decide timing
- Decide direction logic
- Encode strategy
- Predict outcomes
- Assess confidence

They are **mechanical permissions**, nothing more.

---

END OF SECTION 16
## 17. POSITION SIZING & EXPOSURE CALCULATION RULES

This section defines **all admissible sizing mechanics** for ENTER, ADD, REDUCE, and EXIT mandates.

Sizing is:
- Deterministic
- Invariant-bound
- Independent of strategy logic
- Independent of signal confidence

---

## 17.1 GENERAL SIZING PRINCIPLES

All sizing must satisfy:

- Determinism (same inputs → same size)
- Invariant compliance (risk, leverage, liquidation)
- Monotonic safety (REDUCE always allowed, ADD constrained)
- No implicit scaling

No mandate may infer size from:
- “Strength”
- “Confidence”
- “Quality”
- “Conviction”

---

## 17.2 RISK-ANCHORED SIZING (PRIMARY)

All ENTER sizing is anchored to **maximum allowed loss**, not notional.

### 17.2.1 Definitions

Let:

- `R_max` = maximum risk per trade (absolute or % of equity)
- `SL_dist` = distance between entry reference and stop reference
- `Q` = position size
- `P` = price unit value

Then:

Q = R_max / (SL_dist × P)


This formula is mandatory for ENTER.

---

## 17.3 LEVERAGE CONSTRAINT ENVELOPE

All sizing must satisfy **post-mandate** leverage constraints.

### 17.3.1 Definitions

- `E` = account equity
- `N` = total notional exposure after mandate
- `L_eff = N / E`

Invariant:

L_eff ≤ L_max


If violated → mandate rejected.

---

## 17.4 LIQUIDATION DISTANCE CONSTRAINT

All ENTER and ADD mandates must satisfy a minimum liquidation buffer.

### 17.4.1 Definitions

- `L_price` = estimated liquidation price
- `SL_price` = stop price
- `Δ_min` = minimum allowed buffer

Invariant:

|L_price - SL_price| ≥ Δ_min


If violated → mandate rejected.

This invariant exists to prevent:
- Forced liquidation before stop
- Margin-driven exits overriding intent

---

## 17.5 ENTER SIZING RULES

ENTER size is:

ENTER_size = min(
risk_based_size,
leverage_cap_size,
liquidation_safe_size
)


ENTER may not:
- Exceed any single cap
- Be split into multiple ENTERs
- Be resized after submission

---

## 17.6 ADD SIZING RULES

ADD increases exposure incrementally.

### 17.6.1 Maximum ADD Size

ADD is bounded by:

ADD_size ≤ min(
remaining_risk_capacity,
remaining_leverage_capacity,
liquidation_safe_increment
)


If result ≤ 0 → ADD rejected.

---

### 17.6.2 ADD Does NOT Reset

ADD does NOT:
- Reset stop reference
- Reset risk clock
- Reset lifecycle
- Re-anchor risk to new stop

All risk is cumulative.

---

## 17.7 REDUCE SIZING RULES

REDUCE sizing is always admissible.

### 17.7.1 Partial Reduction

REDUCE may specify:
- Absolute quantity
- Percentage of current size

Invariant:

0 < REDUCE_size ≤ current_position_size


---

### 17.7.2 Forced Reduction

REDUCE may be forced when:
- Leverage approaches cap
- Margin buffer degrades
- External risk constraints trigger

Forced REDUCE overrides ADD and ENTER.

---

## 17.8 EXIT SIZING RULES

EXIT is absolute.

EXIT_size = full remaining position


No partial EXIT exists.
EXIT terminates the position instance.

---

## 17.9 MULTI-MANDATE INTERACTION

If multiple mandates apply sizing changes:

- Sizes are evaluated sequentially
- Invariant checks apply after each hypothetical application
- First violation aborts remaining mandates

No batching.

---

## 17.10 PROHIBITED SIZING PRACTICES

Explicitly forbidden:

- Martingale scaling
- Averaging down without ADD invariant checks
- Size increases after stop tightening
- Volatility-based confidence sizing
- Signal-weighted sizing
- Time-based scaling

---

## 17.11 SILENCE ON FAILURE

If sizing computation results in:
- Zero
- Negative
- NaN
- Invariant violation

Then:
- Mandate is rejected
- No logs
- No fallback sizing

Silence is correct behavior.

---

END OF SECTION 17

It is immutable.

---

### 18.2.2 Structural Stop Rules

- Exactly one structural stop per position
- Set at ENTER
- Must exist before order submission
- Must be known to sizing logic (Section 17)

Structural stops:
- Do not trail
- Do not widen
- Do not tighten automatically

---

## 18.3 RISK STOP (ACCOUNT-LEVEL)

Risk Stops protect the account, not the position.

### 18.3.1 Trigger Conditions

A Risk Stop triggers when:

- Aggregate unrealized loss exceeds allowed risk envelope
- Portfolio drawdown limit is breached
- Cross-position correlation amplifies loss beyond cap

---

### 18.3.2 Behavior

When Risk Stop triggers:

- All positions are force-closed (EXIT)
- No REDUCE or ADD allowed
- System enters FAILED or HALTED state (external to this spec)

Risk Stop overrides all position logic.

---

## 18.4 LIQUIDATION-PROXIMITY STOP

This stop exists to prevent **exchange-enforced liquidation**.

### 18.4.1 Trigger Condition

If estimated liquidation price approaches current price closer than allowed buffer:

|P_current - P_liq| < Δ_liq_min


Then:
- Immediate EXIT is triggered

---

### 18.4.2 Priority

Liquidation-Proximity Stop has higher priority than:
- Structural Stop
- Mandate sequencing
- Partial exits

This stop is absolute and non-negotiable.

---

## 18.5 SYSTEM-INITIATED FORCED EXIT

Forced exits may be triggered by **non-market causes**.

### 18.5.1 Valid Causes

- Observation layer enters FAILED
- Execution system invariant violation
- Connectivity loss exceeding tolerance
- Exchange rejects protective orders
- Margin mode mismatch or error

---

### 18.5.2 Behavior

On forced exit:

- EXIT entire position
- Cancel all pending orders
- Do not attempt re-entry
- Do not log interpretive reason externally

---

## 18.6 STOP EXECUTION PRIORITY ORDER

If multiple exit conditions trigger simultaneously:

1. Liquidation-Proximity Stop
2. Risk Stop
3. System-Initiated Forced Exit
4. Structural Stop

Only the highest-priority exit executes.

---

## 18.7 STOP VS PARTIAL REDUCTION

Stops are **terminal**.

If stop condition triggers:
- REDUCE is NOT permitted
- Partial exit logic is bypassed
- EXIT is immediate

---

## 18.8 STOP IMMUTABILITY INVARIANTS

Once a position is live:

- Stop may not move against risk
- Stop may not be removed
- Stop may not be disabled
- Stop may not be overridden by mandate

Any attempt to violate this:
- Rejects mandate
- Preserves original stop

---

## 18.9 STOP & ADD INTERACTION

ADD mandates must satisfy:

- Original stop remains valid
- Combined position still respects stop-defined risk

ADD may not:
- Move stop further away
- Convert stop into trailing logic
- Reset invalidation logic

---

## 18.10 STOP VISIBILITY & SILENCE

Stop execution:
- Produces no explanatory output
- Emits no interpretation
- Does not annotate “why”

The only externally observable fact:
- Position is closed

---

## 18.11 PROHIBITED STOP PRACTICES

Explicitly forbidden:

- Mental stops
- Time-based stops
- Indicator-based stops
- Volatility-adaptive stops
- Trailing stops (unless explicitly defined in a future section)
- “Emergency” discretionary overrides

---

END OF SECTION 18
## 19. PROFIT REALIZATION & EXIT MANDATES

This section defines **non-terminal exits** whose purpose is *capital realization*, not risk invalidation.

Profit exits:
- Are optional
- Are conditional
- Do not imply correctness of entry
- Do not terminate the position unless explicitly defined

They are categorically distinct from Stops (Section 18).

---

## 19.1 EXIT CATEGORIES

There are only two admissible exit categories:

1. PARTIAL EXIT (REDUCE)
2. FULL EXIT (EXIT)

No other exit semantics are permitted.

---

## 19.2 PARTIAL EXIT (REDUCE)

A Partial Exit reduces exposure while preserving the position.

### 19.2.1 Definition

A REDUCE mandate:
- Lowers position size
- Keeps direction unchanged
- Preserves original structural stop
- Preserves position lifecycle state (ACTIVE)

---

### 19.2.2 Reduction Constraints

For any REDUCE:

- Reduction fraction ∈ (0, 1)
- Remaining position size > 0
- Structural stop remains valid
- Liquidation buffer must still be satisfied

If any constraint fails → REDUCE is rejected.

---

### 19.2.3 Permitted Triggers (Abstract)

REDUCE may be triggered by:

- Encountering predefined exit zones
- Realization at historical liquidity regions
- Exposure rebalancing requirements
- Portfolio-level risk normalization

Triggers are **inputs**, not interpretations.

---

## 19.3 FULL EXIT (EXIT)

A Full Exit closes the position completely.

### 19.3.1 Definition

An EXIT mandate:
- Closes entire remaining position
- Cancels all associated orders
- Transitions lifecycle to CLOSED
- Releases margin and exposure

EXIT is terminal.

---

### 19.3.2 EXIT vs STOP

| Aspect | EXIT | STOP |
|------|------|------|
| Motivation | Capital realization | Risk protection |
| Optional | Yes | No |
| Trigger | Conditional | Mandatory |
| Lifecycle | Controlled close | Forced close |

---

## 19.4 EXIT ZONES (MECHANICAL)

Exit Zones are **price regions**, not predictions.

### 19.4.1 Definition

An Exit Zone is a predefined price interval:

[Z_low, Z_high]


Defined **before or during** the position lifecycle.

---

### 19.4.2 Exit Zone Properties

- May trigger REDUCE or EXIT
- May be overlapping or nested
- May be historical or derived
- Must not depend on future data

Exit Zones do not imply:
- Reversal
- Resistance/support
- Market intent

---

## 19.5 MULTI-ZONE EXIT LOGIC

Multiple Exit Zones may coexist.

Rules:

- Zones are evaluated independently
- First-valid zone may trigger REDUCE
- Later zones may trigger EXIT
- Zones do not block one another

Exit sequencing is deterministic.

---

## 19.6 CONDITIONAL ESCALATION: REDUCE → EXIT

A REDUCE may escalate to EXIT if:

- Remaining position violates minimum size
- Liquidation buffer becomes insufficient
- Risk envelope is breached post-reduction
- System-level constraint activates

Escalation is mechanical, not discretionary.

---

## 19.7 PROFIT REALIZATION VS POSITION THESIS

Critical invariant:

> Profit-taking does NOT validate the position thesis.

Therefore:
- REDUCE does not imply “good trade”
- EXIT does not imply “correct prediction”
- No learning or reinforcement occurs here

---

## 19.8 EXIT PRIORITY ORDER

When multiple exit conditions are true:

1. STOP logic (Section 18)
2. Risk Stop
3. Liquidation-Proximity Stop
4. System Forced Exit
5. EXIT mandate
6. REDUCE mandate

Lower-priority exits are ignored once a higher-priority exit triggers.

---

## 19.9 EXIT & ADD INTERACTION

If ADD and EXIT conditions are simultaneously valid:

- EXIT dominates
- ADD is discarded
- No netting or averaging permitted

---

## 19.10 EXIT VISIBILITY & SILENCE

External systems may observe only:

- Position size change
- Position closure

They must not receive:
- Reason codes
- Profit labels
- Zone names
- Narrative explanation

---

## 19.11 PROHIBITED EXIT PRACTICES

Explicitly forbidden:

- “Let winners run” logic
- Trailing profit exits (unless explicitly specified later)
- Time-based profit exits
- Indicator-based exits
- Emotional or discretionary overrides

---

END OF SECTION 19
## 20. CONDITION PRIMITIVES (NON-INTERPRETIVE MARKET FACTS)

This section defines the **atomic condition primitives** the system is allowed to observe and reference.

Condition primitives:
- Are descriptive, not predictive
- Do not imply direction
- Do not imply opportunity
- Do not imply intent
- May be true simultaneously, independently, or contradictorily

They are **inputs**, never decisions.

---

## 20.1 PRIMITIVE DESIGN PRINCIPLES

All primitives must satisfy:

1. Observability — derived from recorded or streaming data
2. Locality — defined relative to price, time, or region
3. Statelessness — no internal memory beyond the primitive definition
4. Non-semantic — names must not encode meaning or outcome
5. Composability — primitives may be combined, never upgraded

If a primitive implies *why* something happens, it is invalid.

---

## 20.2 PRICE-REGION PRIMITIVES

### 20.2.1 REGION

A REGION is a bounded price interval.

REGION := [P_low, P_high]


Properties:
- Static once defined
- May overlap other regions
- May be nested

REGION does not imply:
- Support
- Resistance
- Supply
- Demand

---

### 20.2.2 REGION_INTERACTION

Describes interaction between price and a REGION.

Allowed states:
- ENTER
- INSIDE
- EXIT
- REJECT (enter then exit within threshold time)

No directionality implied.

---

## 20.3 HISTORICAL LIQUIDITY PRIMITIVES

### 20.3.1 LIQUIDATION_CLUSTER (HISTORICAL)

A recorded aggregation of liquidation events within a REGION.

Attributes:
- Region
- Time window (past)
- Aggregate size
- Density (events per unit time)

No assumption:
- Future relevance
- Repeatability
- Causation

---

### 20.3.2 STOP_CONCENTRATION (HISTORICAL)

A REGION where repeated rapid price excursions occurred historically.

Attributes:
- Region
- Count of excursions
- Mean excursion depth
- Mean excursion duration

Does not imply:
- Stop hunts
- Intentional targeting

---

## 20.4 PRICE DYNAMICS PRIMITIVES

### 20.4.1 PRICE_VELOCITY

Magnitude of price change per unit time.

PRICE_VELOCITY := |Δprice| / Δtime


Attributes:
- Instantaneous
- Windowed
- Peak value
- Mean value

Velocity has no direction semantics.

---

### 20.4.2 PRICE_ACCELERATION

Change in PRICE_VELOCITY over time.

Attributes:
- Positive acceleration
- Negative acceleration
- Zero acceleration

Acceleration does not imply momentum or exhaustion.

---

## 20.5 ORDERFLOW PRIMITIVES

### 20.5.1 LARGE_ORDER_PRESENCE

Detection of orders exceeding a size threshold.

Attributes:
- Size
- Side (buy/sell) — descriptive only
- Region
- Duration (resting vs transient)

Presence does not imply:
- Absorption
- Defense
- Intent

---

### 20.5.2 ORDER_ABSORPTION_PATTERN

Observed condition where:
- Price remains bounded
- Executions continue
- Net price displacement remains constrained

Attributes:
- Region
- Duration
- Executed volume
- Net price change

This primitive does **not** assert absorption motive.

---

## 20.6 LIQUIDATION–PRICE RELATION PRIMITIVES

### 20.6.1 LIQUIDATION_WITHOUT_DISPLACEMENT

Condition where liquidation events occur without proportional price movement.

Attributes:
- Region
- Liquidation size
- Net price displacement
- Time window

No inference about strength or defense.

---

### 20.6.2 LIQUIDATION_CASCADE (PAST)

A sequence of liquidation clusters with increasing density over time.

Attributes:
- Regions involved
- Sequence duration
- Peak density

Cascade is historical only.

---

## 20.7 MEMORY PRIMITIVES (HISTORICAL CONTEXT)

### 20.7.1 HISTORICAL_REGION_INTERACTION

Records prior interactions between price and a REGION.

Attributes:
- Count
- Last interaction time
- Interaction types

No belief about recurrence.

---

### 20.7.2 REGION_ACTIVITY_PROFILE

Aggregate statistics of activity within a REGION.

Attributes:
- Mean traded volume
- Mean velocity
- Mean dwell time

Purely descriptive.

---

## 20.8 TIMEFRAME NORMALIZATION

No primitive is bound to:
- Weekly
- Daily
- Intraday
- Session-based labels

All primitives are defined in:
- Absolute time
- Rolling windows
- Event-relative windows

This removes timeframe bias.

---

## 20.9 PRIMITIVE COEXISTENCE

Multiple primitives may be true at the same time:

Examples:
- PRICE_VELOCITY high + LIQUIDATION_WITHOUT_DISPLACEMENT
- REGION_INTERACTION INSIDE + LARGE_ORDER_PRESENCE
- STOP_CONCENTRATION historical + current REGION_ENTRY

No resolution occurs at this layer.

---

## 20.10 EXPLICITLY FORBIDDEN PRIMITIVES

The following are not primitives and must never appear:

- Trend
- Bias
- Bullish / Bearish
- Reversal
- Continuation
- Strength / Weakness
- Smart money
- Trapped traders
- Manipulation
- Intent

---

## 20.11 ROLE OF CONDITION PRIMITIVES

Condition primitives:
- Feed mandates
- Gate position actions
- Influence risk adjustments
- Influence exit eligibility

They do **not**:
- Trigger trades directly
- Rank opportunities
- Compete with one another

---

END OF SECTION 20
## 21. MANDATE COMPOSITION (NON-INTERPRETIVE RESPONSE LOGIC)

This section defines how **mandates** are constructed, combined, and evaluated.

Mandates:
- Do not predict outcomes
- Do not rank signals
- Do not encode strategy
- Do not assume intent
- Do not imply optimality

Mandates express:  
**“If a defined set of conditions is simultaneously true, a specific class of response becomes permissible.”**

Nothing more.

---

## 21.1 WHAT A MANDATE IS

A MANDATE is a declarative rule of the form:

MANDATE := {
required_primitives: Set[ConditionPrimitive],
optional_primitives: Set[ConditionPrimitive],
prohibited_primitives: Set[ConditionPrimitive],
permitted_responses: Set[ResponseType]
}


A mandate does **not** execute a response.  
It only **permits** one.

---

## 21.2 MANDATE VS STRATEGY (HARD SEPARATION)

| Concept | Meaning |
|------|--------|
Mandate | Declares permission boundaries |
Strategy | Chooses actions (forbidden here) |
Signal | Implies prediction (forbidden) |
Decision | Occurs outside mandate layer |

Mandates **never decide** — they only constrain.

---

## 21.3 RESPONSE TYPES (CANONICAL, NON-DIRECTIONAL)

Permitted response classes:

- OPEN_POSITION
- CLOSE_POSITION
- REDUCE_POSITION
- INCREASE_POSITION
- HOLD_POSITION
- MODIFY_RISK
- NO_ACTION

These are **categories**, not instructions.

---

## 21.4 MULTIPLE MANDATES — ALLOWED AND EXPECTED

Multiple mandates may be valid at the same time.

There is:
- No priority
- No override
- No conflict resolution here

Example (valid simultaneously):

- Mandate A permits: REDUCE_POSITION
- Mandate B permits: CLOSE_POSITION
- Mandate C permits: HOLD_POSITION

All three are true.  
None block the others.

---

## 21.5 NON-BLOCKING DESIGN (CRITICAL)

Mandates must **never** invalidate other mandates by default.

This directly resolves your concern:

> “liquidity zones can force partial exit but also full exit”

Correct — therefore:

- No mandate may encode exclusivity
- No mandate may encode finality
- No mandate may encode dominance

Blocking behavior is forbidden.

---

## 21.6 EXAMPLE: LIQUIDITY-RELATED MANDATES (STRUCTURAL)

### Mandate: REGION_ACTIVITY_RESPONSE

required_primitives:

    REGION_INTERACTION(INSIDE)

    HISTORICAL_REGION_INTERACTION

permitted_responses:

    REDUCE_POSITION

    CLOSE_POSITION

    HOLD_POSITION


Note:
- No assertion that exit *should* occur
- No preference between partial vs full exit
- All responses are simultaneously legal

---

## 21.7 PARTIAL VS FULL EXIT — FORMAL RESOLUTION

Partial and full exits are **not mutually exclusive mandates**.

They differ only by:
- Quantity
- Timing
- Risk context

Thus:

- REDUCE_POSITION and CLOSE_POSITION may both be permitted
- Quantity selection occurs **after mandates**, not inside them

Mandates do not encode sizing.

---

## 21.8 OPPOSING CONDITIONS — NO COLLAPSE

Example:

- Mandate X permits INCREASE_POSITION
- Mandate Y permits REDUCE_POSITION

This is allowed.

Interpretation such as:
> “these cancel out”

is **explicitly forbidden** at this layer.

Higher layers may choose — mandates do not.

---

## 21.9 MANDATE TRUTH IS BINARY

A mandate is either:
- ACTIVE
- INACTIVE

There is:
- No confidence
- No strength
- No weighting
- No scoring

---

## 21.10 MANDATE LIFETIME

Mandates:
- Are evaluated on each observation
- Do not persist state
- Do not remember past activation
- May flicker on/off without consequence

Stability is not enforced here.

---

## 21.11 MANDATES DO NOT CAUSE ACTION

Mandates only define **what is allowed**, never what is done.

They cannot:
- Trigger orders
- Trigger exits
- Trigger scaling
- Trigger risk changes

They can only *permit* those classes of actions.

---

## 21.12 EXPLICITLY FORBIDDEN IN MANDATES

Mandates must never contain:

- “prefer”
- “stronger”
- “weaker”
- “should”
- “likely”
- “expected”
- “best”
- “optimal”

Any comparative or evaluative language invalidates the mandate.

---

## 21.13 WHY THIS LAYER EXISTS

This layer exists to:

- Allow multiple simultaneous truths
- Preserve optionality
- Avoid premature collapse
- Prevent strategy leakage
- Support contradictory market states

It is intentionally permissive.

---

## 21.14 RELATION TO POSITION & RISK INVARIANTS

Mandates cannot violate:
- Position invariants (Section 16)
- Risk invariants (Section 17)

If a mandate permits an action that violates an invariant, the invariant wins silently.

No error.
No override.
No escalation.

---

## 21.15 SUMMARY

- Mandates describe **permission space**
- Multiple mandates may coexist
- Partial and full exits are never exclusive
- No mandate blocks another
- Decisions occur strictly later

---

END OF SECTION 21
## 22. DECISION ARBITRATION (CONSTRAINT-DRIVEN SELECTION)

This section defines how the system selects **one concrete action** from a set of **permitted responses**, without:

- Strategy
- Prediction
- Scoring
- Interpretation
- Optimization
- Market understanding

Arbitration is mechanical, not intelligent.

---

## 22.1 PURPOSE OF ARBITRATION

After Section 21, the system may have:

Permitted Responses = {
HOLD_POSITION,
REDUCE_POSITION,
CLOSE_POSITION
}


This section defines **how one response is chosen** without asserting *why*.

---

## 22.2 ARBITRATION IS NOT STRATEGY

Arbitration does **not** answer:

- “What is best?”
- “What is likely?”
- “What should we do?”

It answers only:

> “Which actions are still allowed after applying all constraints?”

and then selects **the most restrictive surviving action**.

---

## 22.3 CORE RULE: RESTRICTION DOMINANCE

Actions are ordered **only by how much optionality they remove**.

From least to most restrictive:

1. HOLD_POSITION
2. REDUCE_POSITION
3. CLOSE_POSITION

This ordering is **structural**, not evaluative.

---

## 22.4 RESTRICTION DOMINANCE RULE

Given a set of permitted responses:

> **Select the most restrictive response that does not violate any invariant.**

This ensures:
- No unnecessary exposure
- No forced optimism
- No assumption of continuation

---

## 22.5 WHY THIS IS NOT STRATEGY

This rule does **not** claim:

- Reduction is safer
- Closing is better
- Holding is risky

It only claims:

> Closing removes more future options than reducing, which removes more than holding.

This is a fact about **state space**, not markets.

---

## 22.6 EXAMPLE: LIQUIDITY REGION INTERACTION

Active mandates permit:

{ HOLD_POSITION, REDUCE_POSITION, CLOSE_POSITION }


Risk invariants allow all three.

Arbitration selects:

CLOSE_POSITION


Not because:
- Liquidity is dangerous
- Price will reverse

But because:
- CLOSE_POSITION is the **most restrictive allowed state transition**

---

## 22.7 EXAMPLE: PARTIAL EXIT BLOCKED BY INVARIANT

Permitted responses:

{ REDUCE_POSITION, CLOSE_POSITION }


Invariant violation:
- REDUCE_POSITION would leave position size below minimum lot size

Remaining valid set:

{ CLOSE_POSITION }


Arbitration selects:

CLOSE_POSITION


No interpretation involved.

---

## 22.8 EXAMPLE: REDUCTION WITHOUT FULL EXIT

Permitted responses:

{ HOLD_POSITION, REDUCE_POSITION }


Invariant violation:
- CLOSE_POSITION forbidden (e.g. hedge lock, regulatory constraint)

Arbitration selects:

REDUCE_POSITION


---

## 22.9 NO CONFLICT RESOLUTION LOGIC

There is:
- No tie-breaking
- No priority system
- No mandate ranking

Mandates never conflict.  
Only invariants constrain.

---

## 22.10 ARBITRATION IS STATELESS

Arbitration:
- Does not know past actions
- Does not know trade history
- Does not remember prior choices

Each decision is isolated.

---

## 22.11 ARBITRATION DOES NOT SCALE SIZE

Arbitration selects **action class only**.

It does not decide:
- How much to reduce
- Where to exit
- At what price

Sizing is deferred.

---

## 22.12 ARBITRATION FAIL-SAFE

If **no permitted response survives invariants**:

ACTION = NO_ACTION


Silence is valid.

---

## 22.13 WHY THIS MATTERS FOR YOUR EARLIER CONCERN

> “liquidity zones can force partial exit or full exit depending on circumstances”

Correct — and now formally resolved:

- Mandates permit both
- Invariants may block one
- Arbitration chooses the most restrictive remaining
- No scenario is blocked prematurely

---

## 22.14 RELATION TO RISK

Risk is enforced **only** through invariants.

Arbitration never reasons about:
- Volatility
- Danger
- Exposure desirability

It only respects hard limits.

---

## 22.15 WHAT THIS LAYER GUARANTEES

- No optimism bias
- No hidden strategy
- No interpretation leakage
- Deterministic behavior
- Auditability

---

## 22.16 WHAT COMES NEXT

You now have:

1. Facts (primitives)
2. Permissions (mandates)
3. Constraints (invariants)
4. Choice (arbitration)

What remains is:

**23 — Quantity Resolution (How much to reduce / close without strategy)**

This is where leverage, liquidation avoidance, and exposure math live — cleanly.

---

END OF SECTION 22
## 23. QUANTITY RESOLUTION (EXPOSURE & RISK MECHANICS)

This section defines **how much** position is changed *after* an action has already been selected by arbitration.

It is purely mechanical.

No prediction.  
No interpretation.  
No optimization.  
No market opinion.

---

## 23.1 POSITION OF THIS LAYER IN THE SYSTEM

Order of operations (now explicit):

1. Observation produces facts (no meaning)
2. Mandates permit possible actions
3. Invariants restrict actions
4. Arbitration selects **action class**
5. **Quantity Resolution determines size**

This section is **step 5 only**.

---

## 23.2 INPUTS TO QUANTITY RESOLUTION

Quantity Resolution receives:

- `selected_action` ∈ { HOLD, REDUCE, CLOSE }
- `current_position_size`
- `current_leverage`
- `account_equity`
- `symbol_constraints` (min size, step size)
- `risk_invariants` (defined earlier)

It does **not** receive:
- Liquidity interpretation
- Narrative
- Confidence
- Signal strength

---

## 23.3 ACTION-SPECIFIC RULES

### 23.3.1 HOLD_POSITION

resolved_quantity_change = 0


No further computation.

---

### 23.3.2 CLOSE_POSITION

resolved_quantity_change = -100% of open position


Full liquidation of exposure.

No partial logic allowed.

---

### 23.3.3 REDUCE_POSITION

This is the only non-trivial case.

Reduction is bounded by **three independent ceilings**.

---

## 23.4 REDUCTION CEILINGS (HARD BOUNDS)

Reduction size is the **maximum amount that satisfies all ceilings simultaneously**.

### Ceiling A: Structural Minimum

Position after reduction must satisfy:

- Exchange minimum size
- Symbol step size
- Internal minimum exposure invariant

If violated → reduction invalid.

---

### Ceiling B: Leverage Safety

Reduction must move leverage **away from liquidation**, not toward it.

Formally:

post_reduction_liquidation_distance ≥ pre_reduction_liquidation_distance


If reduction worsens liquidation proximity → forbidden.

This ensures:
- No cosmetic reduction
- No leverage illusion
- No false safety

---

### Ceiling C: Exposure Invariant

Reduction must not violate global exposure rules, such as:

- Max % equity per symbol
- Max correlated exposure
- Max notional exposure

Reduction may be forced to satisfy these.

---

## 23.5 CANONICAL REDUCTION RULE

When REDUCE_POSITION is selected:

> **Reduce the minimum amount required to satisfy all violated or at-risk invariants.**

Not more.  
Not less.

This avoids:
- Over-deleveraging
- Strategy masquerading as risk control

---

## 23.6 MULTIPLE TRIGGERS, ONE REDUCTION

If multiple invariants indicate reduction:

- They do **not** stack additively
- The most restrictive single reduction dominates

This preserves determinism.

---

## 23.7 PARTIAL VS FULL EXIT — FORMALLY RESOLVED

Your earlier concern is now resolved mechanically:

- Liquidity zones, memory, absorption → mandates
- Mandates permit REDUCE and/or CLOSE
- Invariants may block REDUCE
- Arbitration chooses action
- Quantity resolution executes mathematically

No scenario blocks another prematurely.

---

## 23.8 LIQUIDATION-AWARE REDUCTION (NO PREDICTION)

Liquidation math uses **only current parameters**:

- Entry price
- Mark price
- Maintenance margin
- Leverage

No volatility forecast.  
No future price assumption.

---

## 23.9 EXAMPLE: LIQUIDITY ZONE APPROACH

Inputs:
- Action: REDUCE_POSITION
- Position: 10 contracts
- Invariant breach threshold at 7 contracts

Resolved reduction:

reduce_to = 7 contracts


Even if:
- Liquidity zone is “strong”
- Prior cascades existed

Those facts never enter this layer.

---

## 23.10 EXAMPLE: REDUCTION BLOCKED → FULL EXIT

If:
- REDUCE violates min size
- Or worsens liquidation distance

Then REDUCE is invalid.

Arbitration fallback applies:

CLOSE_POSITION


---

## 23.11 NO PROGRESSIVE SCALING

This system does **not**:
- Scale out gradually
- Trail size dynamically
- “Feel” the market

All reductions are **event-driven and invariant-bound**.

---

## 23.12 NO MEMORY OF PREVIOUS REDUCTIONS

Each quantity resolution is stateless.

No:
- “Already reduced once”
- “Remaining conviction”
- “Let it breathe”

---

## 23.13 WHY THIS IS COMPATIBLE WITH COMPLEX BEHAVIOR

Even advanced behavior emerges:

- Multiple partial exits across time
- Forced exits near liquidation
- Early exits in dense regions

But none are *coded as behavior*.

They emerge from constraints.

---

## 23.14 WHAT THIS LAYER GUARANTEES

- Liquidation-aware leverage control
- Deterministic sizing
- No emotional scaling
- No hidden strategy leakage
- Auditability

---

## 23.15 WHAT THIS LAYER DOES NOT DO

- Choose direction
- Choose entry
- Choose exit price
- Choose timing
- Choose confidence

---

## 23.16 NEXT SECTION

You now have:

- Position states
- Risk invariants
- Mandates
- Arbitration
- Quantity resolution

Next logical step:

**24 — Entry & Exit Zone Formalization (Without Signals)**

This is where “zones” exist as *spatial constraints*, not triggers.

---

END OF SECTION 23
## 24. ENTRY & EXIT ZONE FORMALIZATION (GEOMETRIC, NON-SIGNAL)

This section defines **what zones are**, **what they are not**, and **how they constrain execution** without triggering it.

Zones are *spatial facts*, not decisions.

No prediction.  
No confidence.  
No timing.  
No intent.

---

## 24.1 PURPOSE OF ZONES IN THIS SYSTEM

Zones exist to answer only one question:

> **Where is execution allowed or restricted?**

They do **not** answer:
- Should we trade?
- Which direction?
- How strong is the setup?
- What will price do?

---

## 24.2 ZONES ARE GEOMETRY, NOT MEANING

A zone is defined as:

Zone = [price_low, price_high] on a symbol


Nothing more.

Any interpretation (liquidity, absorption, stop hunts) is **upstream** and **separate**.

---

## 24.3 ZONE TYPES (CANONICAL, NON-INTERPRETIVE)

Zones are classified only by **origin**, not expectation.

### 24.3.1 ENTRY_ALLOWED_ZONE

Price region where **new exposure is permitted** *if* other mandates allow it.

Examples of origins:
- Prior high-velocity move region
- Imbalance region
- Prior liquidation cluster region
- Structural range boundary

No implication of success.

---

### 24.3.2 EXIT_ALLOWED_ZONE

Price region where **exposure reduction or closure is permitted**.

Examples of origins:
- Historical liquidity cascade region
- Prior stop-hunt region
- Dense historical transaction region
- Memory-correlated reaction region

Exit zones may permit:
- REDUCE
- CLOSE

But never force.

---

### 24.3.3 ENTRY_FORBIDDEN_ZONE

Price region where **opening new exposure is forbidden**, regardless of mandates.

Common causes:
- Spread / liquidity vacuum
- Maintenance margin proximity
- Known event windows (rollover, auction)
- Exchange constraint regions

---

### 24.3.4 EXIT_FORBIDDEN_ZONE (RARE)

Region where exit execution is forbidden due to:
- Exchange halt
- Market suspension
- Execution impossibility

Used sparingly.

---

## 24.4 ZONES DO NOT EXPIRE BY TIME

Zones are invalidated only by **price interaction**, not clocks.

Invalidation rules are explicit and deterministic.

No “freshness”.

---

## 24.5 ZONE INTERACTION STATES

A zone can be in one of four states:

1. **UNTOUCHED**
2. **ENTERED**
3. **PARTIALLY TRAVERSED**
4. **FULLY TRAVERSED**

State transitions are factual:
- Based solely on price crossing boundaries

---

## 24.6 ZONE INVALIDATION RULES

A zone is invalidated when **any** of the following occur:

- Price fully traverses the zone
- Zone is structurally overridden (higher-level geometry replaces it)
- Zone is explicitly removed by system update

No probabilistic decay.

---

## 24.7 MULTIPLE ZONES OVERLAP — NO PRIORITY BY DEFAULT

If zones overlap:
- No zone is “stronger”
- No implicit priority

Resolution occurs **only** at arbitration, not here.

---

## 24.8 ZONES VS MANDATES (CRITICAL DISTINCTION)

- **Zones constrain where**
- **Mandates constrain what**

Examples:

| Scenario | Zone | Mandate |
|--------|------|---------|
| Liquidity region | EXIT_ALLOWED | REDUCE permitted |
| Structural break | ENTRY_ALLOWED | OPEN permitted |
| High-risk region | ENTRY_FORBIDDEN | Blocks OPEN |

Zones never issue commands.

---

## 24.9 PARTIAL VS FULL EXIT COMPATIBILITY

Your earlier concern is formally resolved here:

- Zone merely allows exit
- Mandates decide REDUCE vs CLOSE
- Invariants may override both
- Quantity resolution executes size

Zones **never block future alternatives**.

---

## 24.10 ZONES ARE DIRECTION-AGNOSTIC

A zone has **no directional bias**.

Direction only appears when:
- Paired with a position
- Interpreted by mandates
- Resolved by arbitration

---

## 24.11 ZONES DO NOT “REACT”

Zones do not:
- Absorb
- Reject
- Hold
- Break
- Fail

Those are narrative overlays handled elsewhere.

Here: geometry only.

---

## 24.12 MEMORY-BASED ZONES (PAST EVENTS)

Past phenomena may define zones:
- Liquidation cascades
- Stop hunts
- High execution density
- High velocity price movement

But **only their spatial footprint survives**.

No memory of outcome.

---

## 24.13 ENTRY & EXIT ZONES MAY COEXIST

A region may simultaneously be:
- ENTRY_ALLOWED
- EXIT_ALLOWED

This is not a contradiction.

Example:
- Mean reversion region
- Range mid

Resolution is deferred.

---

## 24.14 ZONES DO NOT TRIGGER ACTIONS

Explicitly forbidden:
- “If price enters zone → trade”
- “Zone touched → exit”
- “Zone respected → add”

Zones are passive constraints only.

---

## 24.15 AUDITABILITY

Every zone must be reconstructible from:
- Historical price data
- Deterministic rule
- Explicit source reference

No discretionary drawing.

---

## 24.16 WHAT THIS ENABLES

Without coding behavior:
- Partial exits near memory regions
- Full exits in dense risk zones
- Multiple exit attempts across time
- No forced commitment

All emerge from constraints.

---

## 24.17 WHAT THIS PREVENTS

- Zone worship
- Signal leakage
- Overfitting geometry
- Narrative hardcoding

---

## 24.18 RELATION TO TIMEFRAMES

Zones are **scale-relative**, not timeframe-bound.

Weekly, daily, intraday labels are irrelevant.

Only price geometry matters.

This resolves your concern about weekly not applying.

---

## 24.19 NEXT SECTION

With zones defined as geometry, the next constraint is **when actions are forbidden regardless of zones**.

**25 — Temporal & Cooldown Invariants**

This handles:
- Overtrading
- Rollover
- News windows
- Execution silence

---

END OF SECTION 24
## 25. TEMPORAL & COOLDOWN INVARIANTS (NON-PREDICTIVE)

This section defines **when execution is forbidden**, regardless of:
- Price
- Zones
- Mandates
- Opportunity

Time here is not predictive.  
It is **operational hygiene**.

---

## 25.1 PURPOSE OF TEMPORAL INVARIANTS

Temporal invariants exist to prevent:
- Mechanical overtrading
- Execution feedback loops
- Liquidity distortions
- Structural self-collision

They do **not** imply:
- Market expectation
- Directional bias
- Quality assessment

---

## 25.2 HARD TEMPORAL FORBIDDANCE WINDOWS

These windows **hard-block execution**.

No mandate may override them.

### 25.2.1 EXCHANGE ROLLOVER WINDOW

Definition:
- Broker / exchange-defined rollover or funding transition period

Invariant:

NO OPEN
NO INCREASE
NO REVERSE


Allowed:
- CLOSE (risk escape only)
- REDUCE (optional, risk-limited)

Rationale:
- Spread expansion
- Liquidity thinning
- Price discontinuities

---

### 25.2.2 MAINTENANCE / AUCTION WINDOWS

Includes:
- Exchange maintenance
- Symbol-specific halts
- Auction opens/closes

Invariant:

NO EXECUTION OF ANY KIND


Only position marking allowed.

---

### 25.2.3 SYSTEM DEGRADED WINDOW

If execution subsystem reports:
- Order rejection
- Latency breach
- Inconsistent fills

Invariant:

NO OPEN
NO INCREASE


Allowed:
- CLOSE
- REDUCE

---

## 25.3 SOFT COOLDOWN WINDOWS

Cooldowns **throttle frequency**, not direction.

They apply per:
- Symbol
- Position
- Mandate type

---

### 25.3.1 POST-ENTRY COOLDOWN

After OPEN or REVERSE:

cooldown_entry(symbol) = T1


During cooldown:
- No additional OPEN
- No pyramiding
- No re-entry after stop

Prevents:
- Chasing
- Immediate regret trades
- Microstructure noise reaction

---

### 25.3.2 POST-EXIT COOLDOWN

After CLOSE:

cooldown_exit(symbol) = T2


During cooldown:
- No OPEN
- No REVERSE

Prevents:
- Flip-flopping
- Emotional re-entry
- Whipsaw loops

---

### 25.3.3 PARTIAL EXIT COOLDOWN

After REDUCE:

cooldown_reduce(symbol) = T3


During cooldown:
- No further REDUCE
- CLOSE still permitted

Prevents:
- Death by a thousand cuts
- Excessive fee drag
- Over-micro-management

---

## 25.4 EVENT-BASED TEMPORAL LOCKS

These are **externally sourced**, not inferred.

### 25.4.1 HIGH-IMPACT NEWS LOCK

During known high-impact events:

NO OPEN
NO REVERSE


Optional:
- REDUCE
- CLOSE

No assumption about direction.

Only volatility hygiene.

---

### 25.4.2 LIQUIDITY VACUUM LOCK

Triggered when:
- Order book depth collapses
- Spread exceeds threshold
- Execution certainty drops

Invariant:

NO OPEN
NO INCREASE


---

## 25.5 COOLDOWNS ARE NON-RESETTING

Cooldown timers:
- Do not shorten
- Do not refresh on price
- Do not reset on new signals

Only explicit actions start cooldowns.

---

## 25.6 COOLDOWNS DO NOT STACK IMPLICITLY

If multiple cooldowns apply:
- Longest active cooldown governs

No additive penalties.

---

## 25.7 COOLDOWNS VS ZONES

Important interaction:

- Zone may allow execution
- Cooldown may still forbid it

Cooldowns override zones.

---

## 25.8 COOLDOWNS VS MANDATES

- Mandates may request actions
- Cooldowns may block them

Blocked mandates are **ignored**, not queued.

No deferred execution.

---

## 25.9 NO TIME-BASED EXIT REQUIREMENT

Explicitly forbidden:
- “Exit after X minutes”
- “Time stop”
- “Didn’t move fast enough”

All exits must be structural or risk-based.

---

## 25.10 SYMBOL-LOCAL ONLY

Cooldowns apply per symbol.

BTCUSDT cooldown does not affect ETHUSDT.

---

## 25.11 POSITION-LOCAL

Cooldowns are tied to:
- Position lifecycle
- Action taken

Not to account-level behavior.

---

## 25.12 TEMPORAL SILENCE IS NOT SIGNAL

No cooldown expiry implies:
- No readiness
- No opportunity
- No permission

It only removes a restriction.

---

## 25.13 AUDITABILITY

Every cooldown must be traceable to:
- Action timestamp
- Cooldown type
- Duration

No hidden timers.

---

## 25.14 WHAT THIS ENABLES

- Clean execution pacing
- Reduced overtrading
- Protection from microstructure traps
- Coexistence of multiple mandates without chaos

---

## 25.15 WHAT THIS PREVENTS

- Revenge trading
- Rapid flip loops
- Fee bleed
- Signal compounding

---

## 25.16 RELATION TO NARRATIVE

Temporal invariants are **orthogonal** to narrative.

Narrative may suggest opportunity.
Time may forbid action.

This tension is intentional.

---

## 25.17 NEXT SECTION

With **where** (zones) and **when forbidden** defined, the next layer is **how risk is structurally bounded**.

**26 — Exposure, Leverage & Liquidation Invariants**

This will formalize:
- Max exposure per symbol
- Leverage ceilings
- Liquidation distance awareness
- Cross-position risk coupling

---

END OF SECTION 25
## 26. EXPOSURE, LEVERAGE & LIQUIDATION INVARIANTS

This section defines **non-negotiable risk physics**.

These rules do not:
- Predict outcomes
- Optimize returns
- Evaluate opportunity quality

They exist to ensure the system **cannot die**, regardless of correctness.

---

## 26.1 PURPOSE OF EXPOSURE INVARIANTS

Exposure invariants exist to prevent:
- Account liquidation
- Structural overconfidence
- Correlated blowups
- Invisible leverage compounding

They operate **below strategy**, **below mandates**, and **below narrative**.

---

## 26.2 DEFINITIONS (STRICT)

### 26.2.1 NOTIONAL EXPOSURE

notional = position_size * entry_price


Used for:
- Leverage computation
- Cross-symbol exposure coupling

---

### 26.2.2 EFFECTIVE LEVERAGE

effective_leverage = total_notional / account_equity


This is the only leverage that matters.

---

### 26.2.3 LIQUIDATION DISTANCE

liq_distance = |liquidation_price - mark_price|


Measured in:
- %
- absolute price units

Used only as a **safety boundary**, never as a signal.

---

## 26.3 HARD EXPOSURE CAPS

These caps are absolute.

No mandate may override them.

---

### 26.3.1 MAX ACCOUNT LEVERAGE

effective_leverage <= L_max


- Applies across all symbols
- Includes unrealized PnL
- Includes pending orders

Violation result:

NO OPEN
NO INCREASE


---

### 26.3.2 MAX SYMBOL EXPOSURE

symbol_notional <= E_symbol_max


Prevents:
- Single-symbol dominance
- Narrative monoculture
- Event-specific wipeout

---

### 26.3.3 MAX DIRECTIONAL CONCENTRATION

sum(long_notionals) <= D_long_max
sum(short_notionals) <= D_short_max


Prevents:
- One-sided book collapse
- Trend overcommitment

---

## 26.4 LEVERAGE IS DERIVED, NOT SET

There is **no fixed leverage number**.

Leverage emerges from:
- Stop distance
- Position size
- Equity

Invariant:

leverage = consequence, not input


---

## 26.5 LIQUIDATION AWARENESS INVARIANTS

Liquidation is not a trade concept.  
It is a **system death boundary**.

---

### 26.5.1 MINIMUM LIQUIDATION BUFFER

liq_distance >= B_min


If violated:

NO OPEN
NO INCREASE


---

### 26.5.2 DYNAMIC BUFFER SCALING

As:
- Volatility increases
- Spread widens
- Depth thins

Then:

B_min increases


This scaling is mechanical, not interpretive.

---

## 26.6 STOP-LOSS VS LIQUIDATION

Invariant:

stop_price MUST be strictly farther than liquidation_price


If:
- Stop is closer than liquidation
- Or equal

Then:

TRADE FORBIDDEN


Stop must always fail **before** liquidation.

---

## 26.7 RISK PER TRADE (LOSS BOUND)

Loss is bounded **before entry**.

max_loss <= R_trade


Where:
- R_trade is fixed percentage of equity
- Applies to worst-case stop execution

Slippage must be included pessimistically.

---

## 26.8 PARTIAL EXITS & EXPOSURE REDUCTION

Partial exits:
- Reduce notional
- Reduce leverage
- Increase liquidation distance

Invariant:

REDUCE must strictly improve risk metrics


If reduction does not improve:
- Leverage
- Liq distance
- Margin buffer

Then:

REDUCE is forbidden


---

## 26.9 PARTIAL EXIT VS FULL EXIT DECISION

Partial exits are **optional**, not default.

Decision depends on:
- Residual exposure
- Remaining risk buffer
- Proximity to structural hazards (zones, liquidity memory)

Invariant:

If residual risk violates ANY invariant → FULL EXIT REQUIRED


No mandate may force partial if full is required.

---

## 26.10 POSITION REVERSALS

Reversal = CLOSE + OPEN.

Invariant:

Reversal must satisfy all OPEN invariants as a fresh trade


No “netting” logic allowed.

---

## 26.11 NO MARTINGALE, EVER

Explicitly forbidden:
- Increasing size after loss
- Averaging down
- “Improving entry”

Invariant:

Size is independent of past PnL


---

## 26.12 CORRELATED EXPOSURE COUPLING

Symbols may be correlated.

Invariant:

correlated_symbols_exposure <= C_max


Correlation may be:
- Hardcoded
- Conservative
- Overestimated

Never inferred dynamically.

---

## 26.13 LIQUIDATION CASCADE MEMORY (DEFENSIVE)

If historical data indicates:
- Liquidation cascades
- Stop-hunt regions
- High-velocity unwinds

Then:
- Required buffers increase
- Max exposure decreases

This is **defensive**, not predictive.

---

## 26.14 FUNDING & CARRY COST AWARENESS

Funding is not a signal.

Invariant:

Funding cost must not dominate R_trade


If funding bleed exceeds acceptable loss horizon:

NO OPEN


---

## 26.15 GAP & DISCONTINUITY ASSUMPTION

Worst-case assumption:
- Stops slip
- Gaps occur
- Liquidity vanishes

All exposure calculations must survive:

worst-case execution


---

## 26.16 NO “SAFE” LEVERAGE

There is no such thing as:
- Conservative leverage
- Safe leverage
- Small leverage

Only **survivable exposure**.

---

## 26.17 AUDITABILITY

Every position must be able to answer:

- Current effective leverage
- Worst-case loss
- Liquidation distance
- Buffer margins

At all times.

---

## 26.18 WHAT THIS ENABLES

- Survival-first execution
- Deterministic risk behavior
- Multiple mandates without blowup
- Honest failure containment

---

## 26.19 WHAT THIS PREVENTS

- Liquidation
- Death spirals
- Hidden leverage stacking
- Overconfidence via partial wins

---

## 26.20 RELATION TO NARRATIVE

Narrative may suggest direction.
Exposure decides **if participation is allowed**.

Narrative is optional.
Survival is mandatory.

---

## 26.21 NEXT SECTION

With **risk physics** locked, the next layer is **position existence itself**.

**27 — Position Identity & Uniqueness Invariants**

This will define:
- One position per symbol
- Directional exclusivity
- Position identity rules
- Conflict resolution between mandates

---

END OF SECTION 26
## 27. POSITION IDENTITY & UNIQUENESS INVARIANTS

This section defines **what a position is**, when it exists, and how conflicts are resolved.

No strategy, mandate, or signal can violate these rules.

---

## 27.1 PURPOSE OF POSITION IDENTITY

Position identity invariants exist to prevent:
- Position stacking
- Directional ambiguity
- Hidden netting
- Conflicting mandates fighting each other
- Implicit averaging or martingale behavior

They define **existence**, not quality.

---

## 27.2 DEFINITION: POSITION

A **position** is defined by the tuple:

(symbol, direction)


Where:
- `symbol` ∈ traded instruments
- `direction` ∈ {LONG, SHORT}

Size, leverage, stop, and targets are **attributes**, not identity.

---

## 27.3 UNIQUENESS INVARIANT (CORE)

For any symbol S:
at most ONE position may exist at any time


This implies:
- No simultaneous long + short on same symbol
- No multiple partial positions masquerading as one

---

## 27.4 DIRECTIONAL EXCLUSIVITY

For a given symbol:

LONG and SHORT are mutually exclusive


If a position exists:
- Opposite-direction entry is forbidden
- Unless it is explicitly a **reversal** (see 27.6)

---

## 27.5 POSITION STATES (EXISTENCE-LEVEL)

A symbol may be in exactly one of the following states:

1. **FLAT**
   - No open position
2. **LONG**
   - One long position exists
3. **SHORT**
   - One short position exists
4. **CLOSING**
   - Exit is in progress (terminal)
5. **REVERSING**
   - Close → Open sequence (atomic)

No other states are allowed.

---

## 27.6 REVERSAL INVARIANT

A reversal is **not** a modification.

It is strictly:

CLOSE existing position
→ verify FLAT
→ OPEN new position (fresh invariants)


Rules:
- Cannot overlap
- Cannot net sizes
- Cannot reuse stops or risk
- Must pass **all** OPEN constraints as if flat

If CLOSE fails:

REVERSAL ABORTED


---

## 27.7 NO POSITION MERGING

Forbidden behaviors:
- Adding to a position
- Scaling in
- Pyramiding
- “Improving average”

Invariant:

Position size is immutable except via REDUCE or CLOSE


---

## 27.8 POSITION MODIFICATION BOUNDARIES

Allowed modifications:
- REDUCE (partial exit)
- STOP adjustment (risk-reducing only)

Forbidden modifications:
- Size increase
- Risk increase
- Stop widening
- Leverage increase

---

## 27.9 MULTI-MANDATE CONFLICT RESOLUTION

Multiple mandates may:
- Observe the same symbol
- Trigger concurrently
- Suggest conflicting actions

Resolution rules:

### 27.9.1 ENTRY CONFLICTS

If FLAT and multiple ENTRY mandates trigger:
- A **selector** must choose exactly one
- Others are ignored, not queued

No arbitration by averaging.

---

### 27.9.2 IN-POSITION CONFLICTS

If position exists and mandates request:
- HOLD
- REDUCE
- CLOSE

Rules:
1. CLOSE overrides REDUCE
2. REDUCE overrides HOLD
3. HOLD never blocks CLOSE

---

### 27.9.3 OPPOSITE-DIRECTION SIGNALS

If position exists and opposite ENTRY mandate triggers:
- It becomes a **REVERSAL REQUEST**
- Must pass reversal invariants
- Otherwise ignored

---

## 27.10 POSITION OWNERSHIP

A position has **one owner mandate**.

Owner defines:
- Entry rationale
- Initial stop
- Initial risk

Other mandates may:
- Request REDUCE
- Request CLOSE

They may not:
- Modify stops upward/downward beyond safety
- Change direction
- Increase exposure

---

## 27.11 PARTIAL EXIT OWNERSHIP

Partial exits:
- Do not change position identity
- Do not change ownership
- Only modify exposure

After partial exit:
- Remaining position is the **same position**

---

## 27.12 POSITION MEMORY IS FORBIDDEN

The system must not:
- Remember past positions per symbol
- Adjust behavior because of past wins/losses
- Bias re-entry due to history

Each new position is independent.

---

## 27.13 SIMULTANEOUS SYMBOL INDEPENDENCE

Position rules apply **per symbol**.

However:
- Exposure coupling (Section 26) may restrict simultaneous positions
- Correlation rules may prevent multiple opens

Identity remains per symbol.

---

## 27.14 FAILED & UNINITIALIZED INTERACTION

If observation status is:
- **FAILED** → all positions must be CLOSED immediately
- **UNINITIALIZED** → no positions may be OPENED

Position identity does not override system survival.

---

## 27.15 AUDITABILITY REQUIREMENTS

For every open position, the system must be able to state:

- Symbol
- Direction
- Owner mandate
- Entry time
- Current state
- Risk metrics (from Section 26)

At all times.

---

## 27.16 WHAT THIS ENABLES

- Clean mandate composition
- Deterministic conflict resolution
- No accidental scaling
- Clear reversals
- Predictable risk behavior

---

## 27.17 WHAT THIS PREVENTS

- Position stacking
- Hedge illusions
- Hidden leverage growth
- Mandate fighting
- Strategy leakage

---

## 27.18 RELATION TO NARRATIVE

Narrative may suggest:
- Multiple scenarios
- Both directions

Position identity enforces:

Only one reality may be acted upon


---

## 27.19 NEXT SECTION

With **position existence** defined, the next layer is **how positions are born**.

**28 — Entry Preconditions & Entry Zone Primitives**

This will define:
- Entry zones
- Structural prerequisites
- Liquidity-based triggers
- Velocity and absorption conditions

---

END OF SECTION 27
## 28. ENTRY PRECONDITIONS & ENTRY ZONE PRIMITIVES

This section defines **when a position is allowed to be opened**.

It does not define *why* a trade is good.
It defines *what must be true* before any ENTRY mandate may fire.

All entries are gated by these primitives.

---

## 28.1 PURPOSE OF ENTRY PRECONDITIONS

Entry preconditions exist to prevent:
- Impulsive execution
- Ambiguous triggers
- Overlapping rationales
- Entries without context
- Narrative violations

They enforce **reactive trading**:
> If this happens → then entry is permitted

Never the reverse.

---

## 28.2 ENTRY IS A PRIVILEGE, NOT A RIGHT

An ENTRY mandate may only execute if **all** of the following are true:

1. System state allows entry
2. Position invariants allow entry
3. Entry zone exists
4. Entry trigger occurs inside the zone
5. Risk constraints can be satisfied

Failure of any condition → **NO ENTRY**

---

## 28.3 GLOBAL ENTRY GATES (HARD)

An ENTRY is forbidden if any are true:

- Observation status ≠ OK-equivalent (per constitution)
- Symbol already has a position (Section 27)
- Global exposure limit exceeded
- Correlated exposure limit exceeded
- Account risk budget exhausted

These checks happen **before** strategy logic.

---

## 28.4 DEFINITION: ENTRY ZONE

An **entry zone** is a price *region*, not a price level.

Formally:

EntryZone := [price_low, price_high] with semantic meaning


An entry cannot occur:
- Outside the zone
- Before the zone is reached
- After the zone is invalidated

---

## 28.5 CANONICAL ENTRY ZONE TYPES

Entry zones may be formed from one or more of the following primitives.

### 28.5.1 Liquidity-Based Zones

Derived from **memory of forced behavior**:

- Prior liquidation cascades
- Stop-hunt regions (equal highs / equal lows)
- Known liquidation clusters
- Sweep zones (wick-based)

These zones imply:
> Forced participants once existed here → may exist again

---

### 28.5.2 Structural Zones

Derived from price structure:

- Break of structure origin
- Last opposing candle before impulse
- Base of displacement
- Range high / low boundaries

Structure defines **context**, not timing.

---

### 28.5.3 Imbalance Zones

Derived from **asymmetric execution**:

- Single-direction displacement
- Low overlap candles
- Inefficient price traversal

Price often revisits these zones to rebalance.

---

### 28.5.4 Absorption Zones

Derived from **failed continuation**:

- Repeated attempts to move price rejected
- Aggressive market orders absorbed
- Price stalls while volume/liquidations increase

These zones suggest **large passive participants**.

---

### 28.5.5 Velocity Origin Zones

Derived from **high-speed price movement**:

- Sudden expansion
- Large candles relative to recent history
- Rapid liquidation bursts

Zones are marked at the **origin** of velocity, not the extreme.

---

## 28.6 ENTRY ZONE VALIDITY CONDITIONS

An entry zone is considered **valid** if:

- It has not been fully traversed post-creation
- It has not been structurally invalidated
- The narrative has not flipped
- No stronger opposing zone overrides it

Zones decay over time and interaction.

---

## 28.7 MULTI-TIMEFRAME CONSTRAINT (SIMPLIFIED)

Weekly timeframe is **excluded** from execution logic.

Allowed construction hierarchy:
- Context: Higher timeframe (e.g. 4H, 1H)
- Execution: Lower timeframe (e.g. 15m, 5m)

Rule:

Entry trigger timeframe < Entry zone timeframe


---

## 28.8 ENTRY TRIGGERS (INSIDE ZONE)

Being in a zone is **not enough**.

One or more triggers must occur **inside** the zone:

### 28.8.1 Structural Trigger

- Break of minor high/low
- Internal market structure shift
- Failure swing

---

### 28.8.2 Liquidity Trigger

- Sweep of equal highs/lows
- Liquidation spike
- Stop-run followed by rejection

---

### 28.8.3 Absorption Trigger

- Price stalls despite aggressive flow
- Delta divergence
- Repeated rejection of continuation

---

### 28.8.4 Momentum Failure Trigger

- Decreasing velocity
- Shrinking displacement
- Failed follow-through

---

## 28.9 ENTRY DIRECTION DETERMINATION

Direction is determined **only after trigger**, not before.

Rules:
- Structural continuation → trade with impulse
- Liquidity sweep + rejection → trade opposite sweep
- Absorption → trade against absorbed side

No bias without confirmation.

---

## 28.10 ENTRY PRICE SELECTION

Entry price may be:
- Market (on trigger)
- Limit (within zone after trigger)

Forbidden:
- Blind limits
- Pre-positioning
- Entries before trigger

---

## 28.11 STOP-LOSS REQUIREMENT (MANDATORY)

Every entry must define a stop-loss **before execution**.

Stop must:
- Invalidate the entry idea
- Sit beyond the zone or structure
- Respect liquidation and volatility buffers

No stop → no entry.

---

## 28.12 ENTRY ZONE vs EXIT ZONE DISTINCTION

Entry zones and exit zones are **not symmetric**.

- Entry zones → permission to enter
- Exit zones → permission to reduce or close

They may overlap, but serve different roles.

---

## 28.13 MULTIPLE ZONES PER SYMBOL

Allowed:
- Multiple potential entry zones
- Multiple scenarios (narrative)

Constraint:

Only one entry may execute


Zones compete; execution selects one reality.

---

## 28.14 ENTRY INVALIDATION CONDITIONS

An entry zone is invalidated if:

- Opposing structure breaks
- Stronger HTF zone asserts control
- Price consolidates excessively inside zone
- Narrative flips

Invalid zone → mandates disabled.

---

## 28.15 ENTRY IS NOT OBLIGATORY

Even if:
- Zone exists
- Trigger occurs

Entry may still be rejected due to:
- Risk constraints
- Exposure limits
- Correlation limits
- Existing position conflicts

Discipline overrides opportunity.

---

## 28.16 WHAT THIS ENABLES

- Narrative-driven execution
- Liquidity-aware entries
- Reduced false signals
- Clean stop placement
- Modular mandate logic

---

## 28.17 WHAT THIS PREVENTS

- Predictive trading
- Blind limit orders
- Chasing price
- Overlapping entries
- Context-free execution

---

## 28.18 RELATION TO POSITION MANAGEMENT

Entry defines:
- Initial risk
- Ownership mandate
- Stop framework

All later actions (reduce, exit, reverse) build on this.

---

## 28.19 NEXT SECTION

With **entry permitted**, the next question is:

**When and how exposure is reduced.**

**29 — Exit Zones, Partial Exits & Reduction Logic**

---

END OF SECTION 28
## 29. EXIT ZONES, PARTIAL EXITS & REDUCTION LOGIC

This section defines **how exposure is reduced or closed** once a position exists.

It does **not** justify why a trade was taken.
It governs **how risk is unwound** as new information appears.

Exit logic is reactive, hierarchical, and non-binary.

---

## 29.1 PURPOSE OF EXIT LOGIC

Exit logic exists to:
- Lock risk reduction progressively
- Respond to opposing information
- Avoid binary “all-or-nothing” outcomes
- Preserve optionality

Exit ≠ Failure  
Exit = **Information response**

---

## 29.2 EXIT ≠ STOP-LOSS

A stop-loss:
- Is defensive
- Exists from entry
- Represents invalidation

An exit:
- Is adaptive
- Responds to evolving structure/liquidity
- Can be partial or full

Stops end trades.  
Exits **manage** them.

---

## 29.3 DEFINITION: EXIT ZONE

An **exit zone** is a price *region* where **risk reduction is permitted**.

Formally:

ExitZone := [price_low, price_high] with opposing informational weight


Exit zones are derived from:
- Liquidity memory
- Structural opposition
- Absorption
- Velocity exhaustion

---

## 29.4 EXIT ZONES DO NOT FORCE ACTION

An exit zone **allows**, but does not require:
- Partial reduction
- Full exit
- No action

Decision depends on **context + mandate type**.

---

## 29.5 CANONICAL EXIT ZONE TYPES

### 29.5.1 Liquidity-Based Exit Zones

Derived from historical forced behavior:

- Prior liquidation cascades
- Known stop-hunt regions
- Liquidity pools opposite the trade

Interpretation:
> Forced exits occurred here before → risk increases here

These zones **often justify partial exits first**.

---

### 29.5.2 Structural Opposition Zones

Derived from structure opposing the position:

- Prior swing highs (for longs)
- Prior swing lows (for shorts)
- Range boundaries
- Failed breakout levels

These zones may justify:
- Partial exit
- Full exit
- Tightened stop

---

### 29.5.3 Absorption Exit Zones

Derived from **failure to continue**:

- Price reaches zone but stalls
- Large orders absorb momentum
- Liquidations occur but price does not move

Interpretation:
> Opposing participants may be defending this level

Absorption zones often justify **aggressive reduction**.

---

### 29.5.4 Velocity Exhaustion Zones

Derived from:
- Shrinking displacement
- Decreasing momentum
- Multiple failed continuation attempts

These zones suggest:
> The move may be ending or pausing

Common use:
- Scale out
- Move stop
- Reduce leverage

---

## 29.6 PARTIAL EXIT PRIMITIVE

A **partial exit** reduces position size without closing it.

Constraints:
- Must reduce net exposure
- Must not increase risk
- Must not reverse position

Partial exits are **irreversible**.

---

## 29.7 PARTIAL EXIT IS NOT PROFIT-TAKING ONLY

Partial exits may occur:
- In profit
- At breakeven
- Even at small loss (risk reduction)

They respond to **information**, not PnL.

---

## 29.8 PARTIAL EXIT TRIGGERS

Partial exits may be triggered by:

- Entry into exit zone
- Liquidity interaction
- Absorption detection
- Failure to extend
- Opposing structure forming

No single trigger is mandatory.

---

## 29.9 PARTIAL EXIT SIZING

Reduction amount may be:
- Fixed fraction (e.g. 25%, 50%)
- Exposure-based (reduce leverage)
- Risk-based (reduce worst-case loss)

Forbidden:
- Increasing size during exit logic
- Oscillating size up/down

---

## 29.10 FULL EXIT CONDITIONS

A **full exit** closes the entire position.

May be justified by:
- Structural invalidation
- Strong opposing zone
- Confirmed absorption
- Narrative flip
- Mandate exhaustion

Full exit does **not** imply error.

---

## 29.11 EXIT ZONES VS STOP-LOSS INTERACTION

Exit logic may:
- Preempt stop-loss
- Reduce risk before stop
- Move stop after partial exit

Stop-loss remains the final backstop.

---

## 29.12 MULTIPLE EXIT ZONES PER POSITION

Allowed:
- Sequential exit zones
- Nested exit zones
- Competing exit signals

Constraint:

Exit actions must be monotonic (only reduce)


---

## 29.13 EXIT PRIORITY ORDER

When multiple exit signals occur:

1. Structural invalidation
2. Absorption at opposing zone
3. Liquidity interaction
4. Velocity exhaustion
5. Time-based decay (if defined)

Higher priority overrides lower.

---

## 29.14 EXIT ≠ REVERSAL

A full exit:
- Ends exposure
- Does NOT open opposite position

Reversal requires:
- Position closed
- New entry conditions satisfied
- New mandate fired

---

## 29.15 EXIT SILENCE IS VALID

If:
- No exit zone reached
- No opposing signal
- Narrative intact

Then:
> **Do nothing**

Inaction is a valid outcome.

---

## 29.16 WHAT THIS ENABLES

- Graduated risk reduction
- Adaptive trade management
- Liquidity-aware profit protection
- Avoidance of binary outcomes

---

## 29.17 WHAT THIS PREVENTS

- Panic exits
- All-or-nothing thinking
- Premature profit-taking
- Reversal without confirmation

---

## 29.18 RELATION TO POSITION LIFECYCLE

Exit logic operates in:
- OPEN
- PARTIALLY_REDUCED
- EXITING states

It transitions positions toward closure.

---

## 29.19 NEXT SECTION

With exit logic defined, the next concern is:

**How risk, leverage, and liquidation constraints bound all actions.**

**30 — Risk, Leverage & Liquidation Constraints**

---

END OF SECTION 29
## 30. RISK, LEVERAGE & LIQUIDATION CONSTRAINTS

This section defines **hard, non-negotiable constraints** governing
risk, leverage, and liquidation avoidance.

These constraints sit **above strategy, narrative, and mandates**.

If violated → action is forbidden.

---

## 30.1 PURPOSE OF RISK CONSTRAINTS

Risk constraints exist to ensure:

- Survival across adverse sequences
- Bounded downside per position
- Immunity from single-event liquidation
- Consistency across mandates

They do **not** optimize returns.  
They **preserve existence**.

---

## 30.2 CORE PRINCIPLE

> **No position may exist if its liquidation probability is non-negligible under reasonable volatility.**

This is a **hard invariant**.

---

## 30.3 DEFINITIONS

### 30.3.1 Exposure

Exposure := Notional Position Size / Account Equity


Exposure includes:
- Leverage
- Partial positions
- Residual exposure after reductions

---

### 30.3.2 Risk

Risk := Maximum possible loss if stop-loss is hit


Risk is measured in:
- % of equity
- Absolute account units

---

### 30.3.3 Liquidation Threshold

The price level at which the exchange forcibly closes the position.

Liquidation is **categorically forbidden**.

---

## 30.4 ABSOLUTE RISK INVARIANTS

### 30.4.1 Max Risk Per Position

Risk_per_position ≤ R_max


Typical:
- R_max = 0.5% – 1.0% of equity

This applies **before** any partial exits.

---

### 30.4.2 Aggregate Risk Cap

Σ Risk_open_positions ≤ R_total_max


Prevents correlated drawdowns.

---

### 30.4.3 One Position Per Symbol

Already defined earlier, reinforced here:
- Prevents hidden leverage stacking
- Simplifies liquidation modeling

---

## 30.5 LEVERAGE CONSTRAINTS

### 30.5.1 Leverage Is Derived, Not Fixed

Leverage is **calculated**, not chosen.

Derived from:
- Stop distance
- Risk cap
- Volatility
- Liquidation buffer

---

### 30.5.2 Maximum Allowable Leverage

Leverage ≤ L_max_structural


Where L_max_structural ensures:
- Liquidation price is far beyond stop-loss
- Liquidation requires extreme, abnormal move

---

## 30.6 LIQUIDATION AVOIDANCE INVARIANT

### 30.6.1 Hard Constraint

Liquidation_price must be outside all plausible price paths


If:
- Liquidation < stop-loss buffer
- Liquidation within known liquidity zones
- Liquidation within historical volatility bands

→ **Position forbidden**

---

### 30.6.2 Liquidation Buffer

Define:

Liquidation_Buffer := Distance(liquidation_price, stop_loss)


Constraint:

Liquidation_Buffer ≥ K * Expected_Volatility


K is conservative (e.g. 2–3×).

---

## 30.7 VOLATILITY-AWARE POSITION SIZING

Position size must shrink when:
- Volatility expands
- Liquidity thins
- Event risk increases

Risk is constant; size adapts.

---

## 30.8 LIQUIDITY-ADJUSTED RISK

If entry or exit relies on:
- Thin liquidity
- Known stop-hunt zones
- Prior cascade regions

Then:
- Reduce leverage
- Increase liquidation buffer
- Or forbid position entirely

---

## 30.9 PARTIAL EXITS & RISK RECOMPUTATION

After partial exit:
- Recompute:
  - Remaining risk
  - New liquidation level
  - Exposure

Partial exit **must improve** liquidation safety.

If not → forbidden.

---

## 30.10 ADDING TO POSITION IS FORBIDDEN

No pyramiding unless explicitly allowed by a mandate.

Default rule:
> **Exposure may only decrease after entry.**

---

## 30.11 OPPOSING SIGNALS & RISK RESPONSE

If opposing information appears:
- Risk must reduce
- Never increase

Risk response precedes strategy logic.

---

## 30.12 TIME-BASED RISK DECAY (OPTIONAL)

Optional invariant:
- Risk allowance decays over time if no progress
- Prevents capital stagnation

Time decay never forces action — only forbids continuation.

---

## 30.13 GAP & EVENT RISK

Before known high-risk events:
- Exposure must be reduced
- Or position must be closed

Holding through uncontrolled gaps violates risk invariants.

---

## 30.14 CORRELATED EXPOSURE

If multiple symbols are:
- Highly correlated
- Driven by same liquidity regime

Then:

Effective_Risk = Sum(weighted risks)


Must remain ≤ aggregate cap.

---

## 30.15 LIQUIDATION IS A SYSTEM FAILURE

Liquidation is not:
- A trade loss
- A strategy outcome

It is a **design failure**.

Any mandate that allows liquidation is invalid.

---

## 30.16 WHAT THIS ENABLES

- Survival through volatility
- Robust long-term execution
- Confidence in worst-case outcomes

---

## 30.17 WHAT THIS PREVENTS

- Overleveraging
- Catastrophic loss
- Emotional liquidation
- False sense of safety

---

## 30.18 RELATION TO OTHER SECTIONS

Risk constraints override:
- Narrative
- Entry logic
- Mandates
- Exit logic

They are supreme.

---

## 30.19 NEXT SECTION

With risk bounded, we can define:

**31 — Position Lifecycle & State Transitions**

---

END OF SECTION 30
## 31. POSITION LIFECYCLE & STATE TRANSITIONS

This section defines the **finite, explicit lifecycle of a position**.

A position is not a trade idea.
It is a **stateful object** with strict entry, mutation, and termination rules.

No implicit states.
No ambiguous transitions.
No strategy-dependent reinterpretation.

---

## 31.1 PURPOSE OF POSITION LIFECYCLE

The lifecycle exists to:

- Eliminate undefined behavior
- Enforce risk discipline
- Separate *decision* from *execution*
- Prevent accidental exposure expansion
- Make mandates composable and auditable

---

## 31.2 CORE PRINCIPLE

> **A position may only move forward through allowed states.  
Backward or circular transitions are forbidden.**

---

## 31.3 POSITION STATES (ENUMERATION)

A position may exist in **exactly one** of the following states.

### 31.3.1 `FLAT`
- No position exists
- Zero exposure
- Default state

---

### 31.3.2 `PENDING_ENTRY`
- Entry conditions satisfied
- Order not yet filled
- Exposure not yet realized

Constraints:
- Risk calculated
- Leverage validated
- Liquidation safety validated

If any invariant fails → revert to `FLAT`

---

### 31.3.3 `OPEN`
- Position is live
- Exposure > 0
- Stop-loss active

This is the **only state** where market risk exists.

---

### 31.3.4 `PARTIALLY_REDUCED`
- Exposure reduced from initial size
- Risk recomputed
- Liquidation buffer increased

This state may be entered multiple times.

---

### 31.3.5 `EXIT_PENDING`
- Exit decision made
- Order not yet fully executed
- Exposure may be partial or full

No new decisions allowed in this state.

---

### 31.3.6 `CLOSED`
- Exposure = 0
- Position terminated
- PnL finalized

Terminal state.

---

## 31.4 FORBIDDEN STATES (EXPLICITLY)

The following **do not exist**:

- “Scaling in”
- “Hedged”
- “Paused”
- “Recovery”
- “Waiting”
- “Monitoring”
- “Soft exit”
- “Re-entry without closure”

If it cannot be mapped to a defined state → it is illegal.

---

## 31.5 STATE TRANSITION GRAPH

Allowed transitions only:

FLAT
↓
PENDING_ENTRY
↓
OPEN
↓
PARTIALLY_REDUCED (0..n times)
↓
EXIT_PENDING
↓
CLOSED


---

## 31.6 ILLEGAL TRANSITIONS

The following transitions are **forbidden**:

- `OPEN → PENDING_ENTRY`
- `PARTIALLY_REDUCED → OPEN` (re-expansion)
- `CLOSED → OPEN` (without returning to FLAT)
- Any transition that increases exposure

---

## 31.7 ENTRY STATE RULES

A position may enter `PENDING_ENTRY` **only if**:

- No existing position on symbol
- Risk invariants satisfied
- Leverage derived and approved
- Liquidation buffer validated
- Entry zone defined
- Stop-loss defined
- Exit zones defined (partial + full)

If any requirement missing → entry forbidden.

---

## 31.8 OPEN STATE INVARIANTS

While `OPEN`:

- Exposure may **never increase**
- Stop-loss must exist at all times
- Liquidation must remain impossible under invariants
- Position must respond to opposing signals by **risk reduction only**

---

## 31.9 PARTIAL REDUCTION RULES

Partial reduction is allowed **only if**:

- Triggered by predefined exit logic
- Exposure strictly decreases
- Liquidation buffer increases
- Remaining position remains valid under risk constraints

Partial reduction **cannot**:
- Reset narrative
- Justify holding indefinitely
- Enable re-expansion later

---

## 31.10 FULL EXIT CONDITIONS

A position must transition to `EXIT_PENDING` when:

- Stop-loss hit
- Full target hit
- Hard opposing condition triggered
- Risk invariant threatened
- Mandate explicitly commands exit

---

## 31.11 EXIT PENDING CONSTRAINTS

While in `EXIT_PENDING`:

- No new decisions
- No interpretation
- No mandate evaluation
- Only execution completion

---

## 31.12 CLOSED STATE FINALITY

Once `CLOSED`:

- Position is immutable
- No reactivation
- Any new trade requires fresh lifecycle from `FLAT`

Memory of the trade may exist, but **the position object does not**.

---

## 31.13 POSITION IDENTITY

Each position has:
- Unique ID
- Symbol
- Direction
- Entry timestamp
- Final exit timestamp

Identity does **not** persist across trades.

---

## 31.14 RELATION TO MANDATES

Mandates may:
- Trigger transitions
- Forbid transitions
- Force exits

Mandates may **not**:
- Create new states
- Bypass lifecycle
- Reverse transitions

---

## 31.15 FAILURE HANDLING

If any invariant is violated at runtime:

- Immediate forced transition → `EXIT_PENDING`
- Then → `CLOSED`

No recovery logic permitted.

---

## 31.16 WHY THIS MATTERS

This lifecycle:

- Prevents strategy drift
- Eliminates emotional logic
- Makes execution deterministic
- Enables formal verification
- Allows multiple mandates to coexist safely

---

## 31.17 NEXT SECTION

With lifecycle defined, we can define:

**32 — Mandate Types & Authority Hierarchy**

---

END OF SECTION 31
## 32. MANDATE TYPES & AUTHORITY HIERARCHY

This section defines **what mandates are**, **what kinds exist**, and **how conflicts are resolved**.

Mandates are **not strategies**.  
Mandates are **binding instructions** that operate on positions and risk.

They do not predict.
They do not interpret.
They do not reason.

They **constrain and command**.

---

## 32.1 WHAT A MANDATE IS

A **Mandate** is a rule that:

- Observes a defined condition
- Issues an explicit command
- Operates only within allowed lifecycle transitions

A mandate answers only one question:

> **“Given this condition, what must be done now?”**

Not *why*. Not *what next*. Only *what now*.

---

## 32.2 MANDATES VS STRATEGY

| Concept | Strategy | Mandate |
|------|---------|--------|
| Purpose | Generate ideas | Enforce behavior |
| Predictive | Yes / Often | Never |
| Optional | Yes | No |
| Can be ignored | Yes | No |
| Operates on | Market | Position / Risk |
| Creates exposure | Yes | Never |

Strategy proposes.  
Mandates dispose.

---

## 32.3 MANDATE EXECUTION MODEL

Mandates are:

- Stateless
- Deterministic
- Evaluated independently
- Allowed to fire simultaneously

Each mandate produces **at most one command**.

---

## 32.4 MANDATE COMMAND SET (CANONICAL)

Mandates may issue **only** the following commands:

- `ENTER` *(rare; usually strategy-level)*
- `REDUCE`
- `EXIT`
- `BLOCK_ENTRY`
- `BLOCK_REENTRY`
- `NO_OP`

No other commands exist.

---

## 32.5 CORE MANDATE CATEGORIES

### 32.5.1 ENTRY BLOCKING MANDATES

Purpose:
- Prevent bad trades
- Enforce discipline

Examples:
- Existing position on symbol
- Risk budget exceeded
- Leverage unsafe
- News window active
- Exposure concentration breached

These mandates **only block**, never exit.

---

### 32.5.2 RISK CONTROL MANDATES

Purpose:
- Protect account survival
- Enforce invariants

Examples:
- Liquidation buffer threatened
- Exposure exceeds allowed ratio
- Correlation risk spike
- Volatility regime breach

These mandates **override everything**.

---

### 32.5.3 POSITION MANAGEMENT MANDATES

Purpose:
- Modify exposure safely

Examples:
- Partial exit at liquidity zone
- Reduce size near opposing memory region
- Reduce on absorption detection
- Reduce on adverse velocity

These mandates may issue `REDUCE` or `EXIT`.

---

### 32.5.4 HARD EXIT MANDATES

Purpose:
- Terminate position immediately

Examples:
- Stop-loss hit
- Structural invalidation
- Opposing higher-order condition
- Risk invariant violation

These mandates always issue `EXIT`.

---

### 32.5.5 COOL-DOWN / LOCKOUT MANDATES

Purpose:
- Prevent re-entry churn

Examples:
- Recently exited same symbol
- Stop-loss just hit
- Liquidity sweep detected

These mandates issue `BLOCK_ENTRY` or `BLOCK_REENTRY`.

---

## 32.6 AUTHORITY HIERARCHY (CRITICAL)

When multiple mandates fire, **priority is absolute**.

### Priority Order (Highest → Lowest)

1. **Risk Control Mandates**
2. **Hard Exit Mandates**
3. **Position Management Mandates**
4. **Entry Blocking Mandates**
5. **Strategy / Entry Proposals**

Lower-priority mandates **cannot override** higher ones.

---

## 32.7 CONFLICT RESOLUTION RULE

If multiple mandates issue commands:

- The **highest-priority command wins**
- Lower-priority commands are discarded
- No aggregation or averaging allowed

Example:
- One mandate says `REDUCE`
- One mandate says `EXIT`

→ `EXIT` wins.

---

## 32.8 MULTIPLE MANDATES: ALLOWED AND EXPECTED

Yes — **multiple mandates are allowed**.

This is not optional; it is required.

A healthy system expects:
- Several mandates firing simultaneously
- Most resolving to `NO_OP`
- One decisive command winning

Mandates are **orthogonal**, not exclusive.

---

## 32.9 REDUCTION IS A FIRST-CLASS ACTION

Reduction is not a failure.
Reduction is not hesitation.

Reduction exists to:
- Respect uncertainty
- Monetize partial information
- Increase liquidation safety
- Preserve optionality

Many mandates naturally lead to `REDUCE`.

---

## 32.10 WHAT MANDATES MUST NEVER DO

Mandates must **never**:

- Increase exposure
- Justify holding
- Delay exits
- Interpret narratives
- Predict outcomes
- Change lifecycle rules
- Introduce new states

---

## 32.11 MANDATES AND NARRATIVE

Narrative informs **strategy**, not mandates.

Mandates:
- Do not know the narrative
- Do not care about bias
- Do not remember intent

They only react to **current conditions**.

---

## 32.12 EXAMPLE: MULTI-MANDATE EVENT

Scenario:
- Position open
- Price enters known liquidity zone
- Absorption detected
- Opposing structure nearby

Mandates fire:
- Liquidity-zone mandate → `REDUCE`
- Absorption mandate → `REDUCE`
- Risk mandate → `NO_OP`

Result:
- Single `REDUCE` action
- Exposure decreases
- Position remains valid

---

## 32.13 WHY THIS ARCHITECTURE MATTERS

This structure ensures:

- No single rule dominates
- No hidden coupling
- No emotional overrides
- Deterministic outcomes
- Extensibility without chaos

You can add mandates **without breaking the system**.

---

## 32.14 NEXT SECTION

With mandate authority defined, next we formalize:

**33 — Condition Primitives (Canonical Set)**

This will extract and normalize all conditions implied by your research.

---

END OF SECTION 32
## 33. CONDITION PRIMITIVES (CANONICAL SET)

This section defines the **atomic, non-interpretive conditions** from which all mandates and strategies are built.

Condition primitives are **not signals**.  
They do **not imply action**.  
They only answer:

> **“Is this condition true right now?”**

Everything downstream depends on these being clean, minimal, and composable.

---

## 33.1 DESIGN PRINCIPLES FOR PRIMITIVES

All condition primitives must satisfy:

1. **Binary truth** (true / false)
2. **Stateless evaluation** (no memory unless explicitly passed)
3. **No interpretation**
4. **No embedded action**
5. **Composable with others**

A primitive never says *what to do*.  
It only says *what is*.

---

## 33.2 PRICE–POSITION RELATION PRIMITIVES

These describe **where price is relative to known regions or references**.

### 33.2.1 Price Inside Region
- Price is currently within a defined region

Examples:
- Entry zone
- Exit zone
- Liquidity zone
- Stop-hunt region
- Memory region

---

### 33.2.2 Price Entered Region
- Price has crossed into a region from outside

Important distinction:
- Entry event ≠ being inside

---

### 33.2.3 Price Exited Region
- Price has left a defined region

Used to:
- Invalidate zones
- Release blocks
- End effects

---

### 33.2.4 Price Proximity to Region
- Distance from region boundary ≤ threshold

Used for:
- Pre-emptive risk control
- Gradual reductions

---

## 33.3 STRUCTURE PRIMITIVES

These describe **objective market structure events**.

### 33.3.1 Swing High Broken
- Price exceeded a confirmed swing high

---

### 33.3.2 Swing Low Broken
- Price exceeded a confirmed swing low

---

### 33.3.3 Equal Highs Present
- Two or more highs within tolerance

---

### 33.3.4 Equal Lows Present
- Two or more lows within tolerance

---

### 33.3.5 Structure Held
- Key high/low remains intact

---

### 33.3.6 Structure Invalidated
- Previously defining structure is broken

---

## 33.4 LIQUIDITY & MEMORY PRIMITIVES

These describe **historical behavior mapped to regions**, not predictions.

### 33.4.1 Historical Liquidation Cluster Present
- Region has prior liquidation concentration

---

### 33.4.2 Historical Stop-Hunt Region Present
- Region previously swept stops aggressively

---

### 33.4.3 Historical High Velocity Zone
- Region previously experienced rapid price movement

---

### 33.4.4 Historical Absorption Zone
- Region previously absorbed aggressive flow

---

### 33.4.5 Memory Overlap
- Multiple historical behaviors overlap in region

---

## 33.5 FLOW & MICROSTRUCTURE PRIMITIVES

These describe **current behavior**, not intent.

### 33.5.1 Liquidations Detected
- Liquidation events observed in current window

---

### 33.5.2 Liquidation Intensity Above Threshold
- Liquidation count/size exceeds baseline

*(Baseline here is internal reference, not exposed)*

---

### 33.5.3 Aggressive Orders Present
- Market orders dominate volume

---

### 33.5.4 Large Passive Orders Present
- Significant resting liquidity detected

---

### 33.5.5 Absorption Detected
- Aggressive flow fails to move price materially

---

### 33.5.6 Flow Divergence
- Flow direction and price direction diverge

---

## 33.6 VELOCITY & VOLATILITY PRIMITIVES

These describe **how price is moving**, not why.

### 33.6.1 Price Velocity Above Threshold
- Rate of price change exceeds limit

---

### 33.6.2 Price Velocity Below Threshold
- Price movement stalls

---

### 33.6.3 Volatility Expansion
- Range expansion detected

---

### 33.6.4 Volatility Compression
- Range contraction detected

---

### 33.6.5 Impulsive Move Detected
- Directional move without meaningful retrace

---

## 33.7 TIME & SESSION PRIMITIVES

Time is contextual, never predictive.

### 33.7.1 Session Open
- New session started

---

### 33.7.2 Session Close Approaching
- Time to session end below threshold

---

### 33.7.3 Rollover Window Active
- Known spread-widening period

---

### 33.7.4 News Window Active
- High-impact scheduled event imminent or active

---

## 33.8 POSITION CONTEXT PRIMITIVES

These relate price behavior to **current position**.

### 33.8.1 In Position
- Position exists for symbol

---

### 33.8.2 Flat
- No position exists

---

### 33.8.3 Position Direction Matches Move
- Price moving in favor of position

---

### 33.8.4 Position Direction Opposes Move
- Price moving against position

---

### 33.8.5 Unrealized PnL Positive
- Position currently profitable

---

### 33.8.6 Unrealized PnL Negative
- Position currently losing

---

## 33.9 RISK & EXPOSURE PRIMITIVES

These underpin survival.

### 33.9.1 Max Positions Reached
- Symbol or global limit hit

---

### 33.9.2 Exposure Limit Approached
- Margin usage near threshold

---

### 33.9.3 Liquidation Buffer Below Threshold
- Distance to liquidation unsafe

---

### 33.9.4 Leverage Unsafe Given Volatility
- Current leverage incompatible with conditions

---

### 33.9.5 Correlated Exposure Present
- Multiple positions exposed to same driver

---

## 33.10 COMPOSITION RULES

Primitives are combined using:

- AND
- OR
- NOT

No arithmetic.
No weighting.
No scoring.

Example:

InPosition
AND PriceInside(LiquidityZone)
AND AbsorptionDetected


---

## 33.11 WHAT IS EXPLICITLY NOT A PRIMITIVE

The following are **forbidden** as primitives:

- “Bullish”
- “Bearish”
- “Strong”
- “Weak”
- “Reversal”
- “Continuation”
- “Good trade”
- “Bad trade”

These belong nowhere in execution logic.

---

## 33.12 WHY THIS MATTERS

With this set:

- Strategies become scenario graphs
- Mandates become deterministic enforcers
- Risk becomes explicit
- Expansion is safe

You are no longer coding *opinions* —  
you are wiring **facts to constraints**.

---

## 33.13 NEXT SECTION

**34 — Position & Risk Invariants (Formal Specification)**

This will turn constraints into **non-negotiable laws**.

---

END OF SECTION 33
## 34. POSITION & RISK INVARIANTS (FORMAL SPECIFICATION)

This section defines **non-negotiable laws** governing position existence, sizing, exposure, and survival.

Invariants are **always enforced**.  
They are **not strategies**.  
They are **not mandates**.  
They cannot be overridden by “better conditions”.

If an invariant is violated → **execution must refuse or terminate**.

---

## 34.1 INVARIANT PHILOSOPHY

An invariant answers:

> “Is this action allowed to exist at all?”

Not:
- Is it good?
- Is it profitable?
- Is it likely to work?

Only:
- **Is it permitted under survival rules?**

Invariants exist **above** narratives, mandates, and signals.

---

## 34.2 GLOBAL POSITION INVARIANTS

### 34.2.1 Single Position per Symbol

**Invariant**
- At most **one open position per symbol**

**Formal**

count(open_positions[symbol]) ≤ 1


**Implications**
- No pyramiding by default
- No hedged long+short on same symbol
- Directional conflict impossible

---

### 34.2.2 Opposite Direction Resolution

**Invariant**
- If a valid entry condition appears in the opposite direction:
  - Existing position must be **closed before** any new position can be opened

**Formal**

If InPosition(symbol)
AND NewEntryDirection ≠ CurrentPositionDirection
→ ClosePosition(symbol) BEFORE OpenPosition(symbol)


No partial overlap.
No netting.
No averaging.

---

## 34.3 POSITION COUNT & PORTFOLIO INVARIANTS

### 34.3.1 Maximum Concurrent Positions

**Invariant**
- Total open positions ≤ configured maximum

**Formal**

count(open_positions) ≤ MAX_POSITIONS


Prevents:
- Over-diversification illusion
- Execution overload
- Hidden correlation

---

### 34.3.2 Correlated Exposure Cap

**Invariant**
- Positions sharing correlated drivers must be limited

Examples:
- Same base asset
- Same sector
- Same macro driver

**Formal**

count(positions where correlation_group == X) ≤ MAX_CORRELATED


Correlation is structural, not statistical.

---

## 34.4 RISK PER POSITION INVARIANTS

### 34.4.1 Fixed Risk per Position

**Invariant**
- Each position risks **at most R% of equity**

**Formal**

(position_size * stop_distance) ≤ equity * R


R is constant.
Confidence does not change R.
Narrative does not change R.

---

### 34.4.2 Stop Must Exist Before Entry

**Invariant**
- A position cannot be opened unless a stop level is defined

**Formal**

OpenPosition requires StopDefined == True


No delayed stops.
No mental stops.
No “I’ll manage it manually”.

---

## 34.5 LEVERAGE & LIQUIDATION INVARIANTS

### 34.5.1 Liquidation Distance Minimum

**Invariant**
- Distance to liquidation must exceed safety buffer

**Formal**

(liquidation_price_distance) ≥ MIN_LIQUIDATION_BUFFER


This buffer accounts for:
- Volatility
- Spread expansion
- Wicks
- Forced moves

---

### 34.5.2 Volatility-Adjusted Leverage

**Invariant**
- Maximum leverage decreases as volatility increases

**Formal**

effective_leverage ≤ f(volatility, liquidity, spread)


Leverage is not a fixed number.
It is **context-aware**.

---

### 34.5.3 Exposure-Based Leverage Clamp

**Invariant**
- If total exposure rises, per-position leverage must fall

**Formal**

total_exposure ↑ → max_allowed_leverage ↓


Prevents:
- Death by correlation
- Hidden leverage stacking

---

## 34.6 POSITION MANAGEMENT INVARIANTS

### 34.6.1 Partial Reductions Are Allowed

**Invariant**
- Positions may be reduced partially without violating rules

**Purpose**
- Risk relief
- Exposure control
- Environmental response

Partial ≠ exit.
Partial ≠ reversal.

---

### 34.6.2 Forced Full Exit Conditions

**Invariant**
- Certain conditions require **full exit**, not reduction

Examples:
- Invariant violation
- Liquidation buffer breach
- Structural invalidation

**Formal**

If CriticalInvariantViolated → ClosePositionFully


No discretion.
No delay.

---

### 34.6.3 No Position Repair

**Invariant**
- Adding to a losing position is forbidden unless explicitly allowed later

Default:

If UnrealizedPnL < 0 → No Size Increase


This prevents:
- Martingale
- Emotional averaging
- Narrative anchoring

---

## 34.7 TEMPORAL & EVENT INVARIANTS

### 34.7.1 News & Rollover Protection

**Invariant**
- New positions forbidden during:
  - High-impact news windows
  - Known spread-expansion periods

**Formal**

If NewsWindowActive OR RolloverActive → EntryForbidden


---

### 34.7.2 Session Boundary Constraints

**Invariant**
- Optional restriction on holding through session transitions

Example:
- Close intraday positions before session end

---

## 34.8 FAILURE INVARIANTS

### 34.8.1 Observation Failure Propagation

**Invariant**
- If observation layer reports FAILED:
  - Execution must halt
  - Positions may be force-closed depending on policy

Observation failure is **fatal to interpretation**.

---

### 34.8.2 Data Absence Handling

**Invariant**
- Absence of information ≠ permission to act

If ObservationSilent → No New Action


Silence is a hard stop, not a hint.

---

## 34.9 INVARIANT PRIORITY ORDER

If conflicts arise:

1. Survival (liquidation, exposure)
2. Observation validity
3. Position count & correlation
4. Risk per position
5. Management rules
6. Strategy mandates

Lower layers **never override** higher ones.

---

## 34.10 WHAT INVARIANTS ARE NOT

Invariants are **not**:
- Entry logic
- Exit logic
- Signals
- Optimization targets

They are **guardrails**, not drivers.

---

## 34.11 WHY THIS STRUCTURE WORKS

Because:
- Strategies can fail
- Narratives can be wrong
- Mandates can conflict

But invariants **must not**.

This is what allows:
- Multiple mandate types
- Conditional exits
- Partial exits
- Reactive systems

Without collapse.

---

## 34.12 NEXT SECTION

**35 — Position Lifecycle States**

This will define:
- How positions are born
- How they evolve
- How they die

Formally, without interpretation.

---

END OF SECTION 34
## 35. POSITION LIFECYCLE STATES (FORMAL MODEL)

This section defines **what a position is allowed to be**, **when**, and **why**.

Lifecycle states are **descriptive**, not interpretive.  
They do **not** explain market behavior.  
They explain **system posture** relative to an open position.

A position may only exist in **one state at a time**.

---

## 35.1 CORE PRINCIPLE

A position is not a trade idea.

A position is a **managed exposure object** that:
- Is born
- Evolves
- Terminates

Each transition is **explicit** and **auditable**.

No implicit transitions.
No fuzzy states.
No “kind of in a trade”.

---

## 35.2 ENUMERATION OF POSITION STATES

### 35.2.1 `FLAT`

**Definition**
- No position exists for the symbol

**Properties**
- No exposure
- No leverage
- No risk
- No management logic active

**Permitted Transitions**
- `FLAT → PENDING_ENTRY`

---

### 35.2.2 `PENDING_ENTRY`

**Definition**
- Entry intent exists
- No position yet opened

**Used When**
- Mandate conditions satisfied
- Invariants passed
- Awaiting execution mechanics (price, liquidity, confirmation)

**Properties**
- Zero exposure
- No stop active yet
- No PnL

**Permitted Transitions**
- `PENDING_ENTRY → OPEN`
- `PENDING_ENTRY → FLAT` (conditions invalidated)

---

### 35.2.3 `OPEN`

**Definition**
- Position is live
- Full size established

**Properties**
- Exposure exists
- Stop defined
- Liquidation price defined
- Risk locked-in

**Permitted Transitions**
- `OPEN → REDUCED`
- `OPEN → EXITING`
- `OPEN → FORCED_EXIT`

---

### 35.2.4 `REDUCED`

**Definition**
- Position partially closed
- Residual exposure remains

**Why This Exists**
- Risk reduction
- Liquidity zone interaction
- Volatility response
- Exposure rebalance

**Important**
- REDUCED ≠ weakened thesis
- REDUCED ≠ exit intent

**Properties**
- Smaller size
- Stop may be adjusted
- Direction unchanged

**Permitted Transitions**
- `REDUCED → OPEN` (only if explicitly allowed later)
- `REDUCED → EXITING`
- `REDUCED → FORCED_EXIT`

_Default_: No re-expansion unless explicitly enabled.

---

### 35.2.5 `EXITING`

**Definition**
- Intentional position termination underway

**Used When**
- Target reached
- Mandate completed
- Narrative invalidated
- Opposite direction condition confirmed

**Properties**
- May be partial or full
- Directional exposure winding down

**Permitted Transitions**
- `EXITING → FLAT`

---

### 35.2.6 `FORCED_EXIT`

**Definition**
- Immediate, non-negotiable termination

**Triggers**
- Invariant violation
- Liquidation buffer breach
- Observation FAILED
- Exchange / execution emergency

**Properties**
- No discretion
- No delay
- Overrides all mandates

**Permitted Transitions**
- `FORCED_EXIT → FLAT`

---

## 35.3 STATE TRANSITION GRAPH (TEXTUAL)

FLAT
↓
PENDING_ENTRY
↓
OPEN
↓
REDUCED ──→ EXITING ──→ FLAT
↓
FORCED_EXIT ──→ FLAT


No other transitions are allowed.

---

## 35.4 FORBIDDEN STATES

The following states **must never exist**:

- `PARTIALLY_PENDING`
- `HEDGED`
- `REVERSING`
- `REPAIRING`
- `AVERAGING`
- `WAIT_AND_SEE`
- `TEMPORARILY_IGNORED`

If it cannot be named precisely, it cannot exist.

---

## 35.5 STATE TRANSITION RULES

### 35.5.1 Single Transition per Event

Only **one state transition** may occur per triggering event.

No cascading.
No chained transitions.

---

### 35.5.2 No Silent Transitions

Every transition must be caused by:
- Mandate
- Invariant
- Explicit operator instruction
- System failure

Never by:
- Time passing
- Hope
- Price drift alone

---

## 35.6 STATE VS MANDATES

States answer:
> “What is the position right now?”

Mandates answer:
> “What actions are allowed or required?”

States do **not** decide actions.
Mandates do **not** redefine states.

They are orthogonal.

---

## 35.7 STATE VS NARRATIVE

Narratives may:
- Justify entry
- Justify exit
- Justify reduction

But narratives **do not change state definitions**.

State transitions remain mechanical.

---

## 35.8 WHY THIS MODEL IS NECESSARY

Without explicit lifecycle states:
- Partial exits become ambiguous
- Opposite-direction logic becomes unsafe
- Risk logic leaks
- Strategy logic bleeds into execution

This model allows:
- Multiple mandate types
- Conflicting signals
- Conditional exits
- Liquidity-based reductions

Without collapse.

---

## 35.9 NEXT SECTION

**36 — Mandate Types & Action Classes**

This will define:
- What mandates exist
- What actions they may request
- What they may never do

Formally and cleanly.

---

END OF SECTION 35
## 36. MANDATE TYPES & ACTION CLASSES (FORMAL DEFINITION)

This section defines **what a mandate is allowed to request**  
and **what it is never allowed to do**.

Mandates are **permissioned intent**, not execution logic.  
They do not move money.  
They do not mutate state directly.  
They request actions that are either **accepted or rejected** by invariants.

---

## 36.1 CORE PRINCIPLE

A mandate answers one question only:

> “Given current information, what action is allowed or required?”

A mandate:
- Does **not** assume it will be executed
- Does **not** override invariants
- Does **not** know execution details
- Does **not** interpret observation quality

Mandates are **stateless**, **composable**, and **fail-safe**.

---

## 36.2 WHY MANDATES EXIST

Without mandates:
- Logic becomes entangled with execution
- Partial exits block full exits
- Opposite-direction logic becomes unsafe
- Risk logic leaks into strategy logic

Mandates allow:
- Multiple simultaneous intentions
- Priority resolution
- Clean refusal paths
- Extensibility without rewrites

---

## 36.3 MANDATE ≠ STRATEGY

- Strategy = how ideas are generated
- Mandates = what actions are permitted

A single strategy may emit:
- Zero mandates
- One mandate
- Multiple competing mandates

Execution chooses **at most one** action.

---

## 36.4 MANDATE CATEGORIES (TOP LEVEL)

### Category A — ENTRY MANDATES  
### Category B — POSITION MANAGEMENT MANDATES  
### Category C — EXIT MANDATES  
### Category D — RISK / SAFETY MANDATES  

No other categories are permitted.

---

## 36.5 CATEGORY A — ENTRY MANDATES

### 36.5.1 `OPEN_POSITION`

**Intent**
- Request creation of a new position

**Requirements**
- Current state must be `FLAT`
- All position invariants must pass
- Risk sizing computable
- Stop & liquidation buffers definable

**Parameters (Descriptive Only)**
- symbol
- direction (long / short)
- entry_zone (range, not price)
- invalidation_zone
- risk_budget_reference

**Forbidden**
- Cannot specify leverage directly
- Cannot assume fill
- Cannot bypass exposure limits

---

## 36.6 CATEGORY B — POSITION MANAGEMENT MANDATES

These operate **only when a position already exists**.

### 36.6.1 `REDUCE_POSITION`

**Intent**
- Reduce exposure without closing position

**Use Cases**
- Liquidity zone ahead
- Historical liquidation region
- High-velocity rejection memory
- Absorption detected
- Exposure rebalance

**Key Point**
Reduction is **natural** and **first-class**  
—not a workaround.

**Parameters**
- reduction_fraction (e.g. 25%, 50%)
- reason_code (descriptive, not interpretive)

**Forbidden**
- Cannot flip direction
- Cannot increase size
- Cannot be silent

---

### 36.6.2 `HOLD_POSITION`

**Intent**
- Explicitly request no action

**Why This Exists**
- Prevents accidental default actions
- Makes inaction auditable
- Allows mandate comparison

**Important**
HOLD is not passive.  
It is an **explicit decision**.

---

### 36.6.3 `ADJUST_RISK` (OPTIONAL / ADVANCED)

**Intent**
- Modify stop placement or exposure buffers

**Allowed Only If**
- Position already reduced OR
- Volatility regime changed

**Forbidden**
- Cannot widen risk beyond initial invariant
- Cannot increase liquidation probability

---

## 36.7 CATEGORY C — EXIT MANDATES

### 36.7.1 `CLOSE_POSITION`

**Intent**
- Fully exit position

**Triggers**
- Target achieved
- Opposite-direction condition confirmed
- Narrative invalidated
- Time-based expiry (if enabled)

**Properties**
- Deterministic
- Overrides HOLD and REDUCE

---

### 36.7.2 `REVERSE_POSITION` ❌ (FORBIDDEN)

Reversal is **not** a mandate.

Correct sequence is always:

CLOSE_POSITION
→ FLAT
→ OPEN_POSITION (new mandate)


This prevents:
- Hidden hedging
- Netting errors
- Direction ambiguity

---

## 36.8 CATEGORY D — RISK / SAFETY MANDATES

These mandates **override everything**.

### 36.8.1 `FORCED_EXIT`

**Triggers**
- Invariant violation
- Liquidation buffer breach
- Observation FAILED
- Execution failure

**Properties**
- No debate
- No delay
- No partial logic

---

### 36.8.2 `BLOCK_ENTRY`

**Intent**
- Explicitly deny new entries

**Use Cases**
- Correlated exposure too high
- Leverage compression
- Market regime exclusion
- Operational constraints

---

## 36.9 MANDATE PRIORITY ORDER

When multiple mandates exist:

1. `FORCED_EXIT`
2. `CLOSE_POSITION`
3. `REDUCE_POSITION`
4. `ADJUST_RISK`
5. `OPEN_POSITION`
6. `HOLD_POSITION`

Lower-priority mandates are ignored if a higher one is valid.

---

## 36.10 MANDATES VS POSITION STATES

| Position State | Allowed Mandates |
|----------------|------------------|
| FLAT | OPEN_POSITION |
| PENDING_ENTRY | OPEN_POSITION, HOLD |
| OPEN | REDUCE, CLOSE, HOLD |
| REDUCED | REDUCE, CLOSE, HOLD |
| EXITING | HOLD |
| FORCED_EXIT | (none) |

No exceptions.

---

## 36.11 WHAT MANDATES MUST NEVER DO

- Never assume execution success
- Never reference internal observation quality
- Never assert market meaning
- Never mutate position directly
- Never bypass invariants
- Never depend on time passing
- Never depend on memory outside explicit inputs

---

## 36.12 WHY THIS SOLVES YOUR EARLIER CONCERN

You identified a real issue:

> “Liquidity zones can force partial exit **or** full exit — depends on circumstances.”

This model solves it cleanly:

- Liquidity presence → `REDUCE_POSITION`
- Liquidity failure / absorption break → `CLOSE_POSITION`

Both can exist **without blocking each other**  
because they are **distinct mandates** with **priority resolution**.

No hard-coded branching.
No scenario blocking.
No overfitting.

---

## 36.13 NEXT SECTION

**37 — Condition Primitives (Atomic Building Blocks)**

This will extract:
- All condition primitives from your research
- Plus derived ones not stated explicitly
- Clean, reusable, non-interpretive


- A prior swing low has been exceeded to the downside

### 37.2.3 `RANGE_HIGH_DEFINED`
- A local range high is established (no break yet)

### 37.2.4 `RANGE_LOW_DEFINED`
- A local range low is established

### 37.2.5 `IN_RANGE`
- Price remains between defined high/low boundaries

---

## 37.3 TIMEFRAME RELATION PRIMITIVES

(Weekly is **not special** — all timeframes are symmetric)

### 37.3.1 `HIGHER_TF_STRUCTURE_INTACT`
- Higher timeframe range not violated

### 37.3.2 `HIGHER_TF_STRUCTURE_BROKEN`
- Higher timeframe range violated

### 37.3.3 `LOWER_TF_COUNTER_MOVE`
- Lower timeframe move against higher timeframe structure

---

## 37.4 LIQUIDITY PRIMITIVES

### 37.4.1 `EQUAL_HIGHS_PRESENT`
- Two or more highs at statistically similar prices

### 37.4.2 `EQUAL_LOWS_PRESENT`
- Two or more lows at statistically similar prices

### 37.4.3 `LIQUIDITY_ZONE_ENTERED`
- Price trades inside known liquidity cluster

### 37.4.4 `LIQUIDITY_ZONE_TAKEN`
- Liquidity cluster has been breached

### 37.4.5 `LIQUIDITY_ZONE_RESPECTED`
- Price enters liquidity zone but fails to break through

---

## 37.5 HISTORICAL MEMORY PRIMITIVES

These encode **memory without interpretation**.

### 37.5.1 `HISTORICAL_LIQUIDATION_CLUSTER_PRESENT`
- Region where liquidations occurred in the past

### 37.5.2 `HISTORICAL_STOP_HUNT_REGION`
- Region previously associated with sharp stop runs

### 37.5.3 `HISTORICAL_HIGH_VELOCITY_MOVE`
- Past rapid price expansion through region

### 37.5.4 `PRICE_REENTERS_MEMORY_REGION`
- Current price trades into any historical region

---

## 37.6 VELOCITY & FLOW PRIMITIVES

### 37.6.1 `PRICE_ACCELERATION_UP`
- Positive second derivative of price

### 37.6.2 `PRICE_ACCELERATION_DOWN`
- Negative second derivative of price

### 37.6.3 `VELOCITY_DECELERATION`
- Momentum slowing relative to prior impulse

---

## 37.7 ABSORPTION & ORDER FLOW PRIMITIVES

(Descriptive only — no intent assumed)

### 37.7.1 `LARGE_ORDERS_PRESENT`
- Large resting or aggressive orders observed

### 37.7.2 `PRICE_STALL_WITH_LIQUIDATIONS`
- Liquidations occur but price fails to advance

### 37.7.3 `ABSORPTION_DETECTED`
- Orders absorb aggressive flow without displacement

### 37.7.4 `ABSORPTION_FAILURE`
- Absorption ceases and price displaces

---

## 37.8 ZONE-BASED PRIMITIVES

### 37.8.1 `ENTRY_ZONE_DEFINED`
- Region identified for potential entry

### 37.8.2 `EXIT_ZONE_DEFINED`
- Region identified for potential exit or reduction

### 37.8.3 `ZONE_RETEST`
- Price revisits previously defined zone

### 37.8.4 `ZONE_REJECTION`
- Price fails to trade through zone

### 37.8.5 `ZONE_ACCEPTANCE`
- Price trades and consolidates within zone

---

## 37.9 POSITION-RELATIVE PRIMITIVES

These depend on **existing position**, not market bias.

### 37.9.1 `PRICE_MOVING_IN_FAVOR`
- Price displacement aligns with position direction

### 37.9.2 `PRICE_MOVING_AGAINST`
- Price displacement opposes position direction

### 37.9.3 `OPPOSITE_DIRECTION_CONDITION_MET`
- Structure break against position

---

## 37.10 RISK-AWARE PRIMITIVES (NON-ACTIONABLE)

### 37.10.1 `LIQUIDATION_DISTANCE_SHRINKING`
- Price approaches estimated liquidation boundary

### 37.10.2 `EXPOSURE_CONCENTRATION_HIGH`
- Exposure relative to account exceeds threshold

### 37.10.3 `VOLATILITY_EXPANSION`
- Volatility exceeds recent baseline

---

## 37.11 TIME & SESSION PRIMITIVES (OPTIONAL)

### 37.11.1 `SESSION_OPEN`
### 37.11.2 `SESSION_CLOSE`
### 37.11.3 `LOW_LIQUIDITY_PERIOD`

(Used only if explicitly enabled)

---

## 37.12 COMPOSITION EXAMPLES (NON-ACTION)

Example only — **not logic**:

- `PRICE_REENTERS_MEMORY_REGION`
- AND `ABSORPTION_DETECTED`
- AND `PRICE_MOVING_IN_FAVOR`

→ may emit `REDUCE_POSITION` mandate  
(depending on higher-level rules)

---

## 37.13 WHAT IS INTENTIONALLY NOT A PRIMITIVE

- “Bullish”
- “Bearish”
- “Good trade”
- “Strong level”
- “High probability”
- “Trap”
- “Fakeout”

Those are **interpretations**, not observations.

---

## 37.14 NEXT SECTION

**38 — Narrative Assembly (Scenario Graphs)**  
How primitives combine into **if–then structures**  
without prediction or bias.

## 38. NARRATIVE ASSEMBLY (SCENARIO GRAPHS)

This section defines how **condition primitives** are assembled into  
**non-predictive, reactive narrative structures**.

Narratives do **not**:
- predict direction
- imply probability
- enforce trades
- override risk or position constraints

Narratives are **graphs of conditions**, not signals.

---

## 38.1 WHAT A NARRATIVE IS (FORMALLY)

A **Narrative** is:

> A bounded set of conditional branches describing **what the system will do IF certain observable states occur**.

Formally:
- Input: primitives (Section 37)
- Output: **eligible mandates** (not actions)

Narrative ≠ Strategy  
Narrative ≠ Bias  
Narrative ≠ Forecast  

Narrative = **structured contingency map**

---

## 38.2 DESIGN CONSTRAINTS

A valid narrative must:

1. Be **conditional only** (if–then)
2. Contain **multiple mutually exclusive paths**
3. Never assert inevitability
4. Never collapse to a single outcome
5. Be invalidated cleanly by structure breaks

---

## 38.3 NARRATIVE GRAPH MODEL

Narratives are modeled as **Directed Acyclic Graphs (DAGs)**.

### Nodes
- Condition nodes (primitives)
- Composite condition nodes (AND / OR)

### Edges
- Logical implication
- Temporal dependency (after / before)

### Leaves
- **Mandate eligibility**, not execution

---

## 38.4 CORE NARRATIVE TYPES

### 38.4.1 RANGE NARRATIVE

Describes behavior **while price remains bounded**.

**Root Condition**
- `IN_RANGE`

**Branches**
- If `RANGE_HIGH_DEFINED` → watch upside behavior
- If `RANGE_LOW_DEFINED` → watch downside behavior

No direction implied.

---

### 38.4.2 BREAKOUT NARRATIVE

Triggered by **structure violation**.

**Entry Condition**
- `STRUCTURE_HIGH_BROKEN` OR `STRUCTURE_LOW_BROKEN`

**Branch Examples**
- Break + `VELOCITY_EXPANSION`
- Break + `ZONE_RETEST`
- Break + `ABSORPTION_FAILURE`

Each branch is distinct.

---

### 38.4.3 LIQUIDITY SWEEP NARRATIVE

Describes **liquidity interaction without outcome assumption**.

**Root**
- `LIQUIDITY_ZONE_ENTERED`

**Branches**
- If `LIQUIDITY_ZONE_TAKEN`
- If `LIQUIDITY_ZONE_RESPECTED`
- If `PRICE_STALL_WITH_LIQUIDATIONS`

No assumption of reversal or continuation.

---

### 38.4.4 MEMORY REVISIT NARRATIVE

Uses historical memory **without projecting behavior**.

**Root**
- `PRICE_REENTERS_MEMORY_REGION`

**Branches**
- + `HISTORICAL_LIQUIDATION_CLUSTER_PRESENT`
- + `HISTORICAL_HIGH_VELOCITY_MOVE`
- + `ABSORPTION_DETECTED`

Used primarily for **exit / reduction eligibility**.

---

### 38.4.5 OPPOSITION NARRATIVE (IN-POSITION)

Only exists **after position open**.

**Root**
- `OPPOSITE_DIRECTION_CONDITION_MET`

**Branches**
- + `STRUCTURE_BREAK_CONFIRMED`
- + `VOLATILITY_EXPANSION`
- + `LIQUIDATION_DISTANCE_SHRINKING`

Feeds **close / reverse eligibility**, not bias.

---

## 38.5 MULTI-TIMEFRAME COHERENCE

Timeframes are **peers**, not hierarchy.

Rules:
- Higher TF does not override lower TF
- Lower TF does not invalidate higher TF
- Conflicts produce **multiple active narratives**

Example:
- HTF: `IN_RANGE`
- LTF: `STRUCTURE_LOW_BROKEN`

→ both narratives remain valid until invalidated.

---

## 38.6 PARALLEL NARRATIVES

Multiple narratives may be active simultaneously.

This is **required**, not optional.

Example:
- Range Narrative (still valid)
- Liquidity Sweep Narrative (triggered)
- Memory Revisit Narrative (triggered)

Mandate resolution decides outcome — not narrative.

---

## 38.7 NARRATIVE INVALIDATION

Narratives must **terminate cleanly**.

Invalidation occurs when:
- Root condition becomes false
- Structure boundary violated
- Timeframe scope expires

No narrative may linger after invalidation.

---

## 38.8 NARRATIVE → MANDATE INTERFACE

Narratives **do not act**.

They only emit:
- `ALLOW_ENTRY`
- `ALLOW_REDUCE`
- `ALLOW_CLOSE`
- `ALLOW_REVERSE`
- `ALLOW_HOLD`

Final decision always gated by:
- Position invariants
- Risk invariants
- Exposure limits

---

## 38.9 WHY THIS MATTERS

This structure prevents:
- Bias locking
- Overfitting
- Strategy rigidity
- Emotional overrides

And enables:
- Multiple responses to same condition
- Partial exits vs full exits
- Adaptive but disciplined behavior

---

## 38.10 NEXT SECTION

**39 — Mandate System (Types & Resolution)**  
How multiple mandates coexist, conflict, and resolve  
under invariant enforcement.

## 39. MANDATE SYSTEM (TYPES, PRIORITY, RESOLUTION)

This section defines **what a mandate is**, how mandates are **emitted**,  
how **multiple mandates coexist**, and how they are **resolved without interpretation**.

Mandates are the **only bridge** between narrative logic and execution.

---

## 39.1 WHAT A MANDATE IS (FORMALLY)

A **Mandate** is:

> A permission token that allows a specific class of action  
> **if and only if** all invariants permit it.

Mandates do **not**:
- execute actions
- imply confidence
- override risk rules
- assert correctness

Mandates only say:  
**“This action class is now allowed.”**

---

## 39.2 MANDATE ≠ SIGNAL

| Concept | Meaning |
|------|-------|
Signal | “Do this now”
Bias | “Market should go this way”
Prediction | “This will happen”
Mandate | “You may do this if rules allow”

Mandates are **negative constraints**, not instructions.

---

## 39.3 CORE MANDATE TYPES

### 39.3.1 ENTRY MANDATES

Allow **opening** a new position.

- `ALLOW_LONG_ENTRY`
- `ALLOW_SHORT_ENTRY`

Conditions:
- No existing position on symbol (see Position Invariants)
- Risk budget available
- Exposure limits respected

---

### 39.3.2 HOLD MANDATE

Allows **maintaining** current position.

- `ALLOW_HOLD`

Emitted when:
- No opposing mandate exists
- No exit condition triggered

HOLD is **explicit**, not default.

---

### 39.3.3 REDUCE MANDATE (CRITICAL)

Allows **partial position reduction**.

- `ALLOW_REDUCE`

Key properties:
- Does not imply full exit
- Does not reverse bias
- Can coexist with HOLD

Typical sources:
- Liquidity memory revisit
- Absorption detected
- Risk compression (liquidation distance)
- Volatility expansion into known zone

This mandate exists because **partial exits are first-class behavior**.

---

### 39.3.4 CLOSE MANDATE

Allows **full position exit**.

- `ALLOW_CLOSE`

Triggered by:
- Opposing structure break
- Risk invariant violation
- Hard invalidation of narrative
- Terminal condition

CLOSE dominates REDUCE.

---

### 39.3.5 REVERSE MANDATE

Allows **close + opposite entry**.

- `ALLOW_REVERSE`

Properties:
- Always implies CLOSE first
- Requires stricter confirmation than ENTRY
- Must satisfy entry invariants immediately after close

REVERSE is **rare and expensive** in risk terms.

---

## 39.4 MULTIPLE MANDATES ARE ALLOWED (AND EXPECTED)

At any time, the system may emit:

- REDUCE + HOLD
- HOLD + OPPOSITION_WARNING (non-mandate)
- CLOSE + REVERSE
- ENTRY (long) + ENTRY (short) — *resolved later*

Mandates **do not cancel each other by default**.

---

## 39.5 MANDATE PRIORITY ORDER

Mandates are resolved by **structural precedence**, not confidence.

Priority (highest → lowest):

1. `FORCE_FAIL` (system invariant)
2. `ALLOW_CLOSE`
3. `ALLOW_REVERSE`
4. `ALLOW_REDUCE`
5. `ALLOW_ENTRY`
6. `ALLOW_HOLD`

Lower mandates are **ignored**, not invalidated, when higher ones apply.

---

## 39.6 SYMBOL-LEVEL ISOLATION

Mandates are resolved **per symbol**.

Rules:
- No cross-symbol interference
- BTC mandates do not affect ETH
- Global risk limits may override locally allowed mandates

---

## 39.7 MANDATE EMISSION RULES

A mandate may only be emitted if:
- Derived from narrative conditions
- All required primitives are observable
- No invariant is already violated

Mandates **must be stateless**.

---

## 39.8 MANDATE RESOLUTION PIPELINE

Order of operations:

1. Collect all active narratives
2. Emit all eligible mandates
3. Apply invariant filters
4. Resolve conflicts by priority
5. Output **zero or one executable intent**

Zero output is valid.

---

## 39.9 WHY REDUCE EXISTS AS FIRST-CLASS

Without REDUCE:
- Every threat becomes CLOSE
- Memory zones force exits
- Risk management becomes binary

REDUCE allows:
- Liquidity-aware scaling
- Volatility-aware trimming
- Risk-aware survival without bias flip

This directly resolves the issue you raised earlier.

---

## 39.10 WHAT MANDATES CANNOT DO

Mandates cannot:
- size positions
- set leverage
- set stops
- define targets
- infer probability
- override liquidation safety

Those belong to **Risk & Position Systems**.

---

## 39.11 NEXT SECTION

**40 — Position & Risk Invariants (Formal Definitions)**  
Hard, absolute constraints that no mandate may violate.

## 40. POSITION & RISK INVARIANTS (HARD CONSTRAINTS)

This section defines **non-negotiable invariants** governing positions and risk.

Invariants are **stronger than mandates**.
If an invariant is violated, **no mandate may execute**, regardless of narrative strength.

Invariants are:
- absolute
- always enforced
- context-independent
- not probabilistic

---

## 40.1 INVARIANT DEFINITION (FORMAL)

An **Invariant** is:

> A condition that must be true **before**, **during**, and **after** any position-related action.

If false:
- action is forbidden
- mandates are ignored
- system must either HOLD or CLOSE (depending on invariant)

---

## 40.2 SYMBOL-LEVEL POSITION INVARIANTS

### 40.2.1 SINGLE POSITION PER SYMBOL

**Invariant:**  
At most **one open position per symbol**.

Formally:
```text
∀ symbol:
    open_positions(symbol) ∈ {0, 1}

Implications:

    No pyramiding

    No scaling-in

    No multiple entries at different prices

Rationale:

    Simplifies liquidation math

    Eliminates hidden leverage stacking

    Preserves narrative clarity

40.2.2 DIRECTIONAL EXCLUSIVITY

Invariant:
A symbol cannot have both long and short exposure simultaneously.

Formally:

position.direction ∈ {LONG, SHORT}

Opposite-direction entry requires:

    CLOSE existing position

    Pass all invariants again

    Then allow new ENTRY

40.3 GLOBAL EXPOSURE INVARIANTS
40.3.1 MAX TOTAL EXPOSURE

Invariant:
Total notional exposure must not exceed configured maximum.

Example:

Σ |position.notional| ≤ MAX_EXPOSURE

This protects against:

    correlated liquidation cascades

    systemic drawdown

    hidden leverage accumulation

40.3.2 CORRELATED SYMBOL CAP

Invariant:
Highly correlated symbols may not exceed group exposure limits.

Example:

    BTC + ETH group exposure cap

    Majors vs alts buckets

Correlation logic is external to this invariant — enforcement is binary.
40.4 LEVERAGE & LIQUIDATION INVARIANTS
40.4.1 LIQUIDATION DISTANCE FLOOR

Invariant:
Position must maintain minimum distance from liquidation price.

Formally:

(liquidation_price − mark_price) / mark_price ≥ MIN_LIQUIDATION_BUFFER

If violated:

    REDUCE or CLOSE only

    ENTRY forbidden

    REVERSE forbidden

This invariant exists to:

    prevent forced liquidation

    preserve optionality

    ensure survival under volatility

40.4.2 DYNAMIC LEVERAGE CAP

Invariant:
Effective leverage must adapt to volatility and exposure.

Leverage is derived, not fixed.

Example factors:

    distance to liquidation

    recent volatility

    existing exposure

    margin usage

Fixed leverage numbers are not allowed without safety proof.
40.5 RISK PER POSITION INVARIANTS
40.5.1 MAX RISK PER TRADE

Invariant:
Maximum loss per position ≤ fixed account fraction.

Example:

max_loss ≤ 1% of equity

Loss defined as:

    stop-loss distance

    liquidation fallback

    worst-case slippage

No trade allowed without bounded loss.
40.5.2 STOP REQUIREMENT

Invariant:
Every position must have a defined invalidation point.

This may be:

    explicit stop-loss

    liquidation buffer

    hard structural invalidation

Positions without exit logic are illegal.
40.6 TIME & EVENT RISK INVARIANTS
40.6.1 NEWS / EVENT LOCKOUT

Invariant:
No ENTRY during predefined high-risk events.

Examples:

    major economic releases

    known exchange maintenance

    rollover periods

REDUCE and CLOSE remain allowed.
40.6.2 VOLATILITY HALT

Invariant:
If volatility exceeds threshold:

    ENTRY forbidden

    REDUCE allowed

    CLOSE allowed

Protects against:

    spread expansion

    execution failure

    stop invalidation

40.7 PARTIAL EXIT SAFETY INVARIANTS
40.7.1 REDUCE MUST IMPROVE SAFETY

Invariant:
Any REDUCE action must strictly improve at least one of:

    liquidation distance

    margin usage

    exposure concentration

REDUCE that does not improve safety is invalid.
40.7.2 REDUCE CANNOT FLIP BIAS

Invariant:
Partial exit cannot:

    reverse position

    imply opposite narrative

    change directional state

Bias changes require CLOSE or REVERSE.
40.8 FAILURE INVARIANTS
40.8.1 INVARIANT VIOLATION RESPONSE

If any invariant fails:

    No ENTRY

    No REVERSE

    Only REDUCE or CLOSE permitted

If violation is terminal:

    FORCE_CLOSE

    HALT symbol trading

40.9 INVARIANTS VS MANDATES (PRECEDENCE)

Order of authority:

    Invariants

    Mandates

    Narrative logic

    Execution mechanics

Mandates do not override invariants. Ever.
40.10 WHY INVARIANTS ARE BINARY

Invariants do not:

    scale

    weaken

    degrade

    negotiate

They exist to prevent irrecoverable states, not optimize performance.
40.11 NEXT SECTION

41 — Position Lifecycle States

Defines:

    how a position moves from ENTRY → HOLD → REDUCE → CLOSE

    which mandates are legal in each state


    ## 41. POSITION LIFECYCLE STATES

Meaning:
Position is live with full intended size.

Required Properties:

direction (LONG or SHORT)

size

liquidation price known

invalidation logic defined

Allowed Actions:

HOLD

REDUCE

CLOSE

(conditional) REVERSE via CLOSE → ENTRY

Forbidden Actions:

ADD (no pyramiding)

SCALE-IN

OPEN does not imply safety, correctness, or confidence.

41.2.4 REDUCING

Meaning:
Position size is being intentionally decreased.

Why this state exists:

partial exits near liquidity zones

risk reduction

exposure normalization

Invariant Requirements:

reduction must strictly improve safety

reduction cannot increase leverage

reduction cannot flip bias

Allowed Actions:

further REDUCE

CLOSE

Forbidden Actions:

ENTRY

ADD

REVERSE

REDUCING is not a signal of weakness or strength — only risk adjustment.

41.2.5 CLOSING

Meaning:
Position is in the process of being fully exited.

This includes:

market close

limit close

forced close

Allowed Actions:

NONE (terminal execution state)

Forbidden Actions:

REDUCE (already closing)

REVERSE

ENTRY

Once CLOSING begins, it must complete.

41.2.6 CLOSED

Meaning:
Position is fully exited and settled.

Allowed Actions:

NONE

Next valid state:

NO_POSITION (implicit)

This state exists for:

accounting

post-trade analysis

audit trails

41.3 STATE TRANSITION TABLE
From State	To State	Condition
NO_POSITION	ENTRY_PENDING	ENTRY mandate + invariants
ENTRY_PENDING	OPEN	Entry filled
ENTRY_PENDING	NO_POSITION	Entry canceled / failed
OPEN	REDUCING	Reduce mandate
OPEN	CLOSING	Close mandate
REDUCING	REDUCING	Additional reduce
REDUCING	CLOSING	Close mandate
CLOSING	CLOSED	Exit filled
CLOSED	NO_POSITION	Settlement complete

No other transitions are legal.

41.4 REVERSE IS NOT A STATE

Important:
REVERSE is not a lifecycle state.

REVERSE is defined as:

CLOSE → NO_POSITION → ENTRY_PENDING


This ensures:

invariant re-evaluation

no hidden exposure overlap

clean direction change

41.5 MANDATE COMPATIBILITY BY STATE
State	ENTRY	HOLD	REDUCE	CLOSE
NO_POSITION	✅	❌	❌	❌
ENTRY_PENDING	❌	❌	❌	❌
OPEN	❌	✅	✅	✅
REDUCING	❌	❌	✅	✅
CLOSING	❌	❌	❌	❌
CLOSED	❌	❌	❌	❌

Mandates violating this table are invalid.

41.6 FAILURE & INTERRUPT HANDLING

If a failure occurs:

invariant violation

execution failure

exchange error

Then:

transition immediately to CLOSING

skip REDUCING

force exit if required

No recovery logic exists inside lifecycle states.

41.7 WHY EXPLICIT STATES MATTER

This model prevents:

ambiguous partial positions

accidental pyramiding

hidden reversals

emotional execution drift

It ensures:

auditable behavior

deterministic execution

enforceable constraints

41.8 NEXT SECTION

42 — Mandate Types & Authority Levels

Defines:

ENTRY / HOLD / REDUCE / CLOSE mandates

precedence rules

conflict resolution

## 42. MANDATE TYPES & AUTHORITY LEVELS

This section defines **what kinds of actions are allowed to be requested** (mandates),
**who/what may issue them**, and **how conflicts are resolved**.

Mandates are **requests**, not guarantees.
They are executed **only if all invariants and lifecycle constraints permit**.

---

## 42.1 WHAT A MANDATE IS (PRECISELY)

A **mandate** is:
- a declarative instruction
- issued by a decision layer (M6 or higher)
- requesting a position lifecycle transition

A mandate:
- does NOT execute trades directly
- does NOT bypass invariants
- does NOT imply correctness or confidence

Mandates are evaluated, not obeyed blindly.

---

## 42.2 CORE MANDATE TYPES (MINIMAL SET)

There are exactly **four primary mandate types**:

```text
ENTRY
HOLD
REDUCE
CLOSE

No other mandate types are permitted.
42.2.1 ENTRY

Purpose:
Request creation of a new position.

Valid Only If:

    lifecycle state = NO_POSITION

    all position & risk invariants pass

    exposure constraints pass

Forbidden If:

    position already exists

    ENTRY_PENDING

    during REDUCING or CLOSING

ENTRY does not imply:

    direction certainty

    success expectation

    continuation

42.2.2 HOLD

Purpose:
Explicitly request no action.

This mandate exists to:

    prevent implicit continuation

    force re-validation of invariants

    document conscious inaction

Valid Only If:

    lifecycle state = OPEN

HOLD is not passive — it is an explicit decision.
42.2.3 REDUCE

Purpose:
Request partial position size reduction.

Typical triggers:

    approach to historical liquidity zone

    adverse structure change

    risk normalization

    exposure rebalance

Valid Only If:

    lifecycle state = OPEN or REDUCING

    reduction strictly improves risk profile

REDUCE must never:

    increase leverage

    flip directional bias

    create hidden reversal

42.2.4 CLOSE

Purpose:
Request full position exit.

Triggers include:

    invalidation of original premise

    opposing narrative confirmed

    risk breach

    forced liquidation avoidance

Valid If:

    lifecycle state = OPEN or REDUCING

CLOSE is terminal.
No further mandates apply until NO_POSITION.
42.3 AUTHORITY LEVELS (WHO MAY ISSUE MANDATES)

Mandates are issued by decision authorities.
Not all authorities are equal.
42.3.1 AUTHORITY LEVELS

LEVEL 0 — Invariants (Highest Authority)
LEVEL 1 — Risk Governor
LEVEL 2 — Strategy / Narrative Engine (M6)
LEVEL 3 — Operator / Manual Override (Optional)

Higher levels override lower ones automatically.
42.3.2 LEVEL 0 — INVARIANTS (ABSOLUTE)

Authority:
Non-negotiable.

Capabilities:

    force CLOSE

    block ENTRY

    block REDUCE (if unsafe)

Invariants do not issue mandates.
They veto mandates.

If invariants fail:

    all mandates are nullified

    system transitions to CLOSING if position exists

42.3.3 LEVEL 1 — RISK GOVERNOR

Authority:
Capital preservation.

May Issue:

    REDUCE

    CLOSE

May NOT Issue:

    ENTRY

    HOLD

Risk governor reacts to:

    liquidation proximity

    leverage thresholds

    exposure concentration

    volatility expansion

Risk mandates override strategy mandates.
42.3.4 LEVEL 2 — STRATEGY / M6

Authority:
Narrative-driven execution logic.

May Issue:

    ENTRY

    HOLD

    REDUCE

    CLOSE

Subject to:

    invariants

    risk governor veto

M6 never:

    forces execution

    overrides risk

    bypasses lifecycle rules

42.3.5 LEVEL 3 — OPERATOR (OPTIONAL)

Authority:
Human intervention (if allowed).

May Issue:

    CLOSE only

Operator cannot:

    force ENTRY

    override invariants

    suppress failures

Operator actions are always logged and terminal.
42.4 MANDATE CONFLICT RESOLUTION

If multiple mandates exist simultaneously:
Priority Order (Highest → Lowest)

INVARIANTS
RISK GOVERNOR
STRATEGY (M6)
OPERATOR

Resolution rules:

    CLOSE overrides all other mandates

    REDUCE overrides ENTRY or HOLD

    HOLD is ignored if higher authority issues action

    ENTRY is lowest priority

No arbitration logic beyond this exists.
42.5 MULTIPLE MANDATES — ALLOWED OR NOT?

Yes, multiple mandates are allowed, but:

    only one mandate may execute per evaluation cycle

    highest-priority valid mandate wins

    others are discarded, not queued

Example:

M6 issues ENTRY
Risk governor issues REDUCE
→ REDUCE executes (ENTRY discarded)

Mandates are stateless and non-persistent.
42.6 WHY REDUCE IS A FIRST-CLASS MANDATE

REDUCE exists because:

    exits are not binary

    liquidity zones may justify partial action

    risk can be modulated without invalidating thesis

This avoids:

    premature full exits

    overreaction to local conditions

    forced all-or-nothing logic

REDUCE is not weakness — it is precision.
42.7 FORBIDDEN MANDATE BEHAVIORS

Explicitly forbidden:

    ADD / SCALE-IN mandates

    MODIFY mandates (implicit state change)

    SOFT CLOSE (ambiguous exits)

    CONDITIONAL ENTRY ("if still good")

    RETRY mandates

All intent must map to the four primitives.
42.8 NEXT SECTION

43 — Position & Risk Invariants (Formal Definition)

Will define:

    leverage ceilings

    liquidation-distance invariants

    exposure limits

    capital at risk bounds

    ## 43. POSITION & RISK CONSTRAINTS AS INVARIANTS

This section defines **non-negotiable constraints** that govern *whether a position may exist at all*.
These are **invariants**, not strategy preferences.

If an invariant is violated:
- the system must **force CLOSE**
- no mandate may override this
- no retry, delay, or mitigation is permitted

Invariants exist to protect **capital, solvency, and system integrity**.

---

## 43.1 INVARIANT PHILOSOPHY

Invariants answer only one question:

> “Is this position allowed to exist right now?”

They do **not** answer:
- whether the trade is good
- whether the narrative is valid
- whether profit is likely

They operate independently of strategy.

---

## 43.2 GLOBAL POSITION INVARIANTS

These apply **across the entire system**, regardless of symbol or strategy.

---

### 43.2.1 ONE POSITION PER SYMBOL

**Rule:**
```text
At most one open position per symbol.

Implications:

    No pyramiding

    No scaling-in

    No hedge positions on same symbol

    No long + short simultaneously

Violation Response:

    Reject ENTRY mandate

    If discovered post-fact → force CLOSE newest position

This simplifies causality and risk attribution.
43.2.2 SINGLE DIRECTION PER SYMBOL

Rule:

A symbol may not have opposing directional exposure.

If conditions arise for opposite direction:

    CLOSE must occur first

    only after NO_POSITION may ENTRY be considered

No direction flipping inside a position.
43.2.3 MAX CAPITAL AT RISK (GLOBAL)

Rule:

Total capital at risk ≤ MAX_RISK_PERCENT of account.

Where:

    capital at risk = sum of worst-case losses at stop

    MAX_RISK_PERCENT is fixed (e.g. 2–5%)

Violation Response:

    Block ENTRY

    Force REDUCE or CLOSE if breached dynamically

This prevents correlated drawdowns.
43.3 LEVERAGE & LIQUIDATION INVARIANTS

Leverage is not a static number — it is contextual risk.
43.3.1 LIQUIDATION DISTANCE INVARIANT

Rule:

Distance to liquidation ≥ MIN_LIQUIDATION_BUFFER

Measured as:

    percentage move from entry to liquidation

    OR price distance in ticks

If liquidation buffer shrinks due to:

    volatility

    funding

    price movement

→ system must REDUCE or CLOSE

This invariant dominates all others.
43.3.2 EFFECTIVE LEVERAGE INVARIANT

Rule:

Effective leverage must be survivable under historical volatility.

Effective leverage considers:

    position size

    stop distance

    recent high-velocity moves

    historical liquidation cascades in region

This prevents:

    “legal” leverage that is practically suicidal

    trades that only survive in calm conditions

43.3.3 NO LIQUIDATION-DEPENDENT POSITIONS

Rule:

A position must never rely on liquidation mechanics to survive.

Meaning:

    no “hoping liquidation engine won’t trigger”

    no positions where stop ≈ liquidation

    no “margin buffer is enough” logic

If liquidation is the primary exit → invalid position.
43.4 POSITION SIZE INVARIANTS
43.4.1 FIXED RISK PER POSITION

Rule:

Each position risks ≤ RISK_PER_TRADE percent of equity.

    Risk is defined at stop-loss

    Confidence does not change risk

    Signal strength does not change risk

Typical value:

    0.5% – 1% per position

43.4.2 STOP LOSS REQUIRED AT ENTRY

Rule:

No position may exist without a defined stop-loss.

Stop must be:

    defined at ENTRY

    placed before or simultaneously with execution

    invariant throughout position lifecycle

No “mental stops”.
No delayed stops.
43.4.3 STOP LOSS VALIDITY

Stop-loss must:

    be beyond invalidation level

    not be inside known liquidity noise

    not be inside obvious stop-hunt clusters (if known)

If stop is invalidated structurally:

    CLOSE or REDUCE required

43.5 EXPOSURE & CORRELATION INVARIANTS
43.5.1 CORRELATED SYMBOL EXPOSURE

Rule:

Highly correlated symbols count as shared exposure.

Examples:

    BTC / ETH

    ETH / major alts

    Index constituents

Risk is aggregated across correlated instruments.
43.5.2 DIRECTIONAL CONCENTRATION

Rule:

Total directional exposure must not exceed MAX_DIRECTIONAL_EXPOSURE.

Prevents:

    being “all-in long” across symbols

    hidden leverage via correlation

43.6 DYNAMIC INVARIANT MONITORING

Invariants are checked:

    at ENTRY

    continuously while OPEN

    before REDUCE

    before HOLD

Violations may emerge due to:

    volatility expansion

    funding changes

    price acceleration

    liquidity evaporation

Invariants are live, not static.
43.7 INVARIANT → ACTION MAP
Violation Type	Required Action
Liquidation buffer breached	FORCE CLOSE
Risk per trade exceeded	REDUCE or CLOSE
Correlation limit breached	REDUCE
Missing stop-loss	FORCE CLOSE
Dual direction detected	FORCE CLOSE
Excess leverage	REDUCE or CLOSE

No discretion exists at this layer.
43.8 EXPLICITLY NOT INVARIANTS

These are not invariants:

    narrative invalidation

    signal weakening

    liquidity zones approaching

    absorption detected

    large orders present

Those belong to strategy mandates, not invariants.
43.9 NEXT SECTION

44 — Position Lifecycle States

Will define:

    NO_POSITION

    ENTRY_PENDING

    OPEN

    REDUCING

    CLOSING

    CLOSED


    ## 44. POSITION LIFECYCLE STATES

Meaning:

Partial exit is in progress

Exposure is being intentionally decreased

Typical Causes:

Liquidity zone proximity

Risk concentration increase

Volatility expansion

Mandated partial profit-taking

Characteristics:

Direction unchanged

Stop-loss may be adjusted

Position still exists

Allowed Transitions:

→ OPEN (reduction complete)

→ CLOSING (if full exit escalated)

Forbidden:

Increasing size

Switching direction

44.3.5 CLOSING

Meaning:

Full exit initiated

Position is terminating

Causes:

Invariant violation

Hard mandate

Forced risk event

Characteristics:

No further strategy evaluation

Only execution mechanics remain

Allowed Transitions:

→ CLOSED

Forbidden:

HOLD

REDUCE

Any new decision logic

44.3.6 CLOSED

Meaning:

Position fully exited

Exposure = 0

Lifecycle completed

Characteristics:

Terminal state

Metrics may be recorded

No further actions allowed

Allowed Transitions:

→ NO_POSITION

44.4 STATE TRANSITION DIAGRAM (TEXTUAL)
NO_POSITION
    ↓
ENTRY_PENDING
    ↓
OPEN
  ↙   ↘
REDUCING  CLOSING
   ↓        ↓
 OPEN     CLOSED
              ↓
          NO_POSITION

44.5 STATE ↔ ACTION CONSTRAINT TABLE
State	ENTRY	HOLD	REDUCE	CLOSE
NO_POSITION	✅	❌	❌	❌
ENTRY_PENDING	❌	❌	❌	❌
OPEN	❌	✅	✅	✅
REDUCING	❌	❌	❌	✅ (escalation)
CLOSING	❌	❌	❌	❌
CLOSED	❌	❌	❌	❌
44.6 IMPORTANT CLARIFICATIONS
REDUCE ≠ CLOSE

REDUCE lowers exposure

CLOSE terminates exposure

HOLD ≠ INACTION

HOLD is an active decision

Invariants are still checked

ENTRY_PENDING ≠ OPEN

No risk exists until OPEN

Partial fills do not count as OPEN

44.7 WHY THIS MATTERS

This lifecycle:

makes illegal states impossible

prevents mandate conflicts

guarantees clean exits

enables auditability

decouples strategy from execution

Every future mandate, primitive, or narrative must map onto these states.

44.8 NEXT SECTION

45 — Mandate Types & Hierarchy

Will define:

ENTRY mandates

HOLD mandates

REDUCE mandates

CLOSE mandates

Priority & conflict resolution

## 45. MANDATE TYPES & HIERARCHY

This section defines **what kinds of mandates exist**, **what they are allowed to do**, and **how conflicts are resolved**.

Mandates are **commands**, not opinions.
They do not describe the market.
They instruct the system **what action is permitted or required**, given current state and invariants.

Mandates never bypass:
- Position lifecycle
- Risk constraints
- Exposure limits

---

## 45.1 MANDATE DESIGN PRINCIPLES

1. **Mandates are action-scoped**
2. **Mandates are state-aware**
3. **Mandates are mutually exclusive by priority**
4. **Mandates never imply interpretation**
5. **Mandates never assume correctness of signals**
6. **Mandates may escalate but not downgrade**

A mandate may exist without being executed.
Execution requires:
- Correct lifecycle state
- All invariants satisfied
- No higher-priority mandate active

---

## 45.2 CORE MANDATE TYPES

There are **four primary mandate types**:

```text
ENTRY
HOLD
REDUCE
CLOSE

These map directly to lifecycle actions.
45.3 ENTRY MANDATES
Definition

An ENTRY mandate authorizes creation of a new position.
Preconditions

    Lifecycle state must be NO_POSITION

    Risk budget available

    Exposure limits satisfied

    Direction explicitly defined

Properties

    Directional (LONG or SHORT)

    Size defined

    Stop-loss defined

    Entry zone defined

Constraints

    Only one ENTRY mandate per symbol at a time

    ENTRY cannot coexist with REDUCE or CLOSE

    ENTRY cannot override risk invariants

Failure Behavior

    If invariants fail → ENTRY is ignored

    No retry, no downgrade, no partial entry

45.4 HOLD MANDATES
Definition

A HOLD mandate explicitly instructs no change to an existing position.
Preconditions

    Lifecycle state must be OPEN

Properties

    Reaffirms current exposure

    Does not modify size, stop, or direction

Purpose

HOLD exists to:

    Prevent accidental default behavior

    Make inaction explicit

    Allow audit of “do nothing” decisions

Constraints

    HOLD cannot block CLOSE

    HOLD cannot override REDUCE

    HOLD cannot suppress invariant-triggered exits

45.5 REDUCE MANDATES
Definition

A REDUCE mandate authorizes partial exposure reduction.
Preconditions

    Lifecycle state must be OPEN

    Position size > minimum lot

Typical Triggers

    Liquidity zone proximity

    Risk concentration increase

    Volatility expansion

    Time-based exposure decay

    Memory-based danger regions

Properties

    Direction preserved

    Size reduced by explicit amount or percentage

    Stop-loss may be adjusted tighter

Constraints

    REDUCE cannot increase size

    REDUCE cannot reverse direction

    REDUCE may escalate to CLOSE

Important Note

REDUCE is not optional if mandated.
If multiple REDUCE mandates exist, the largest reduction wins.
45.6 CLOSE MANDATES
Definition

A CLOSE mandate authorizes full position termination.
Preconditions

    Lifecycle state must be OPEN or REDUCING

Typical Triggers

    Invariant violation

    Opposing higher-confidence setup

    Structural invalidation

    Risk limit breach

    Forced shutdown condition

Properties

    Immediate or market-exit

    No further evaluation once triggered

Constraints

    CLOSE overrides all other mandates

    CLOSE cannot be blocked

    CLOSE cannot be downgraded to REDUCE

45.7 MANDATE PRIORITY HIERARCHY

Mandates resolve strictly by priority:

CLOSE
REDUCE
HOLD
ENTRY

Rules:

    Higher priority always wins

    Lower priority mandates are ignored, not queued

    No arbitration or averaging

Examples:

    ENTRY + CLOSE → CLOSE

    HOLD + REDUCE → REDUCE

    REDUCE + CLOSE → CLOSE

45.8 MULTIPLE MANDATES — ALLOWED OR NOT?
YES, multiple mandates MAY exist simultaneously.

But:

    Only one mandate may execute

    Execution is decided by priority

    Others are discarded silently

This allows:

    Multiple independent triggers

    Redundant safety conditions

    Layered protection

Without causing:

    Conflicting behavior

    Oscillation

    Overfitting logic

45.9 MANDATE ESCALATION RULE

Mandates may escalate, never downgrade:

HOLD → REDUCE → CLOSE
ENTRY → (cancelled only)

Examples:

    Partial exit condition worsens → REDUCE → CLOSE

    Liquidity warning escalates → full exit

Downgrades are forbidden:

    CLOSE → REDUCE ❌

    REDUCE → HOLD ❌

45.10 MANDATES VS SIGNALS (CRITICAL)

Signals:

    Describe conditions

    Can be noisy

    Can be ignored

Mandates:

    Command actions

    Binary (allowed / not allowed)

    Non-negotiable once active

Signals feed mandates.
Mandates control execution.
45.11 WHY THIS STRUCTURE WORKS

This mandate system:

    Prevents overtrading

    Eliminates signal conflicts

    Enforces discipline

    Enables composability

    Supports narrative trading without prediction

It is compatible with:

    Multiple strategies

    Multiple timeframes

    Memory-based logic

    Liquidation-driven logic

45.12 NEXT SECTION

46 — Position & Risk Invariants (Formal Definition)

Will define:

    Exposure caps

    Leverage limits

    Liquidation avoidance

    Cross-position constraints

    ## 46. POSITION & RISK CONSTRAINTS AS INVARIANTS

This section defines **non-negotiable truths** of the system.

Invariants are not logic.
They are not signals.
They are not strategies.

They are **hard boundaries**.
If an invariant is violated, **execution must stop or unwind**, regardless of narrative, mandate, or confidence.

---

## 46.1 INVARIANT DEFINITION

An invariant is a condition that must **always hold true**.

If any invariant evaluates to FALSE:
- ENTRY is forbidden
- HOLD is overridden
- REDUCE may be forced
- CLOSE may be mandatory

Invariants are checked:
- Before entry
- During position lifetime
- On every state transition
- On every mandate evaluation

---

## 46.2 GLOBAL POSITION INVARIANTS

### 46.2.1 ONE POSITION PER SYMBOL

**Invariant**
```text
At most one open position per symbol

Implications

    No pyramiding

    No hedged long/short on same symbol

    No overlapping positions

Violation Handling

    ENTRY mandate rejected

    Opposing ENTRY escalates to CLOSE of existing position

46.2.2 DIRECTIONAL EXCLUSIVITY

Invariant

A symbol may not have simultaneous LONG and SHORT exposure

Implications

    Opposite-direction signal does not open a new trade

    Must close existing position first

Allowed Behavior

    CLOSE → ENTRY (atomic sequence)

    REDUCE → CLOSE → ENTRY (if explicitly permitted)

46.3 RISK PER TRADE INVARIANTS
46.3.1 FIXED MAX RISK PER POSITION

Invariant

Max loss per position ≤ R% of account equity

Typical value:

    R = 0.5% – 1.0%

Applies To

    Initial stop-loss

    Worst-case slippage scenario

    Liquidation distance

Violation Handling

    ENTRY rejected

    Size recalculation required

46.3.2 STOP-LOSS MANDATORY

Invariant

Every position must have a predefined exit condition that limits loss

Notes

    Hard stop, soft stop, or forced close are acceptable

    “Mental stops” are forbidden

Violation Handling

    ENTRY forbidden

    Existing position escalates to CLOSE

46.4 LEVERAGE & LIQUIDATION INVARIANTS
46.4.1 MAX EFFECTIVE LEVERAGE

Invariant

Effective leverage must remain below a system-defined maximum

Effective leverage considers:

    Position size

    Account equity

    Cross-margin effects

This is not a static broker leverage number.
46.4.2 LIQUIDATION AVOIDANCE INVARIANT

Critical Invariant

Distance to liquidation must always exceed safety buffer

Safety buffer considers:

    Historical volatility

    Known liquidation clusters

    Spread expansion

    Slippage risk

If buffer is violated

    REDUCE mandated

    If reduction insufficient → CLOSE mandated

This invariant overrides all narratives.
46.5 EXPOSURE INVARIANTS
46.5.1 MAX TOTAL ACCOUNT EXPOSURE

Invariant

Sum of all open position risks ≤ Global exposure limit

Prevents:

    Correlated blowups

    Overconfidence stacking

    Narrative overextension

46.5.2 CORRELATED SYMBOL EXPOSURE

Invariant

Highly correlated symbols share exposure budget

Examples:

    BTC / ETH

    Indices / index constituents

    Perpetuals vs spot

Correlation awareness is structural, not predictive.
46.6 TIME & EVENT RISK INVARIANTS
46.6.1 NEWS / EVENT BLACKOUT

Invariant

Positions must not be opened during predefined high-risk events

Examples:

    High-impact economic releases

    Known funding / rollover windows

Existing positions may:

    Be reduced

    Be closed

    Never be increased

46.6.2 MAX HOLD TIME (OPTIONAL)

Invariant

Positions exceeding maximum allowed duration must be re-evaluated

Not predictive.
Used to prevent:

    Stale exposure

    Forgotten positions

    Structural drift

Re-evaluation may result in:

    HOLD

    REDUCE

    CLOSE

46.7 PARTIAL EXIT & LIQUIDITY ZONE INVARIANTS
46.7.1 LIQUIDITY ZONE PROXIMITY

Invariant

Approach to known adverse liquidity zones increases risk

Response is not fixed:

    May trigger REDUCE

    May trigger CLOSE

    Depends on confluence with other risks

This avoids hardcoding “partial always” logic.
46.7.2 MEMORY-BASED RISK ZONES

Invariant

Historical regions of liquidation cascades elevate risk

These regions:

    Do not predict reversal

    Do not guarantee exit

    Only constrain exposure

Mandate escalation depends on:

    Position profit

    Volatility regime

    Absorption behavior

46.8 INVARIANT EVALUATION ORDER

Invariants are evaluated in this strict order:

    Liquidation safety

    Max loss per trade

    Directional conflict

    Exposure limits

    Time/event risk

    Structural validity

Earlier failures override later checks.
46.9 INVARIANTS VS MANDATES

    Invariants constrain

    Mandates act

If an invariant fails:

    Mandates cannot override it

    Strategy logic is irrelevant

Invariants are constitutional law.
46.10 NEXT SECTION

47 — Position Lifecycle States

Will define:

    NO_POSITION

    OPEN

    REDUCING

    CLOSING

    CLOSED

    explicit states** a position may occupy.

A position is not a trade idea.
It is not a signal.
It is not a narrative.

It is a **stateful risk-bearing object** that must obey strict transitions.

No implicit states are allowed.
No fuzzy transitions are allowed.
No “kind of open” conditions exist.

---

## 47.1 POSITION STATE MODEL

A position exists in **exactly one** of the following states at any time:

1. NO_POSITION  
2. OPEN  
3. REDUCING  
4. CLOSING  
5. CLOSED  

Transitions are **one-way only** except where explicitly permitted.

---

## 47.2 STATE: NO_POSITION

**Definition**
```text
No exposure exists for the symbol

Characteristics

    Zero size

    Zero leverage

    Zero risk

    No stop-loss

    No target

    No lifecycle timers

Allowed Transitions

    NO_POSITION → OPEN

Forbidden Transitions

    NO_POSITION → REDUCING

    NO_POSITION → CLOSING

    NO_POSITION → CLOSED

(You cannot reduce or close what does not exist.)
47.3 STATE: OPEN

Definition

Position is live with non-zero exposure

Required Properties

    Direction (LONG or SHORT)

    Size > 0

    Defined risk boundary (stop or equivalent)

    Known entry reference

    Liquidation distance evaluated

Allowed Transitions

    OPEN → REDUCING

    OPEN → CLOSING

Forbidden Transitions

    OPEN → OPEN (no re-entry, no stacking)

    OPEN → NO_POSITION (must pass through CLOSED)

47.4 STATE: REDUCING

Definition

Position exposure is being intentionally decreased

Reduction is not failure.
It is risk control.

Common Triggers

    Liquidity zone proximity

    Volatility expansion

    Risk compression (liquidation buffer shrinking)

    Partial profit realization

    Exposure rebalancing

Key Principle
Reduction does not imply exit intent.
47.4.1 REDUCING CONSTRAINTS

Invariant

REDUCE may only decrease size, never increase

Properties

    Direction remains unchanged

    Stop-loss may tighten or remain

    Targets may adjust or remain

    Narrative may remain valid

47.4.2 REDUCING → OPEN

Allowed

If reduction completes and position stabilizes

This transition means:

    Risk normalized

    No exit escalation required

47.4.3 REDUCING → CLOSING

Escalation Conditions

    Further invariant violations

    Adverse liquidity interaction

    Structure invalidation

    Liquidation buffer breach

47.5 STATE: CLOSING

Definition

Position is in terminal exit process

CLOSING is irreversible.

Once entered, the system has decided:

    “This position must not survive.”

47.5.1 CLOSING CHARACTERISTICS

    Full exit intent

    No new mandates allowed

    No narrative reconsideration

    No reduction logic (remaining size is exiting)

47.5.2 ENTRY BLOCKING

Invariant

While CLOSING, no new position on this symbol may be opened

Prevents:

    Flip-flopping

    Emotional reversal

    Structural race conditions

47.6 STATE: CLOSED

Definition

Position fully exited, exposure = 0

Properties

    Final PnL realized

    No risk

    No leverage

    No active stops

Allowed Transitions

    CLOSED → NO_POSITION (implicit cleanup)

    CLOSED → OPEN (new, independent position)

Forbidden

    CLOSED → REDUCING

    CLOSED → CLOSING

47.7 TRANSITION TABLE (SUMMARY)
From \ To	OPEN	REDUCING	CLOSING	CLOSED
NO_POSITION	✅	❌	❌	❌
OPEN	❌	✅	✅	❌
REDUCING	✅	❌	✅	❌
CLOSING	❌	❌	❌	✅
CLOSED	✅	❌	❌	❌
47.8 STATE TRANSITIONS VS MANDATES

Mandates request transitions.
States enforce legality.

Examples:

    ENTRY mandate is ignored unless state == NO_POSITION

    REDUCE mandate ignored unless state == OPEN

    CLOSE mandate valid in OPEN or REDUCING

    No mandate may interrupt CLOSING

47.9 FAILURE HANDLING

If state invariants are violated:

    Position escalates immediately to CLOSING

    No further evaluation occurs

    Preservation of capital overrides intent

47.10 NEXT SECTION

48 — Mandate Types & Semantics

Will define:

    ENTRY

    HOLD

    REDUCE

    CLOSE

    NO_OP

    ## 48. MANDATE TYPES & SEMANTICS

This section defines **all permissible mandates** that may be issued by the decision layer.

A mandate is:
- **An instruction**, not an opinion
- **Stateless**, evaluated against current Position State
- **Non-binding** unless state constraints allow execution

Mandates do **not** force action.
They **request** action, which may be ignored, deferred, or escalated.

---

## 48.1 CORE PRINCIPLE

```text
Mandates propose.
Position state disposes.

No mandate may violate:

    Position Lifecycle invariants

    Risk invariants

    Exposure invariants

    Capital preservation rules

48.2 COMPLETE MANDATE SET

Only the following mandate types are permitted:

    ENTRY

    HOLD

    REDUCE

    CLOSE

    NO_OP

No other mandate types may exist.
No aliases permitted.
No composite mandates permitted.
48.3 MANDATE: ENTRY

Intent

Request opening a new position

Required Preconditions

    Position State == NO_POSITION

    Exposure constraints satisfied

    Risk budget available

    Leverage constraint satisfied

    No conflicting symbol lock

If Preconditions Fail
→ Mandate is ignored silently.

ENTRY Must Define

    Direction (LONG / SHORT)

    Entry reference (price / zone)

    Initial risk boundary

    Intended exposure

    Intended leverage

ENTRY Does NOT Guarantee

    Execution

    Fill

    Persistence

48.4 MANDATE: HOLD

Intent

Explicitly request no change

HOLD is not absence of signal.
It is an affirmative decision to do nothing.

Valid When

    Position State == OPEN

    Position State == REDUCING

Effects

    No size change

    No stop change

    No target change

Why HOLD Exists

    Prevents implicit drift

    Encodes “still valid”

    Blocks accidental escalation

48.5 MANDATE: REDUCE

Intent

Decrease exposure without exiting

REDUCE is a risk action, not a trade signal.

Valid When

    Position State == OPEN

Required Properties

    Reduction fraction or amount

    Reason code (liquidity, volatility, risk compression, etc.)

Forbidden Effects

    Cannot reverse direction

    Cannot increase size

    Cannot reset entry

If Reduction Results in Size == 0
→ Transition automatically escalates to CLOSED (via CLOSING)
48.6 MANDATE: CLOSE

Intent

Exit position completely

CLOSE is terminal.

Valid When

    Position State == OPEN

    Position State == REDUCING

Effects

    Immediate transition to CLOSING

    All other mandates invalidated

    No further evaluation permitted

CLOSE Overrides

    Narrative validity

    Profit potential

    Partial exit logic

48.7 MANDATE: NO_OP

Intent

Explicit declaration of non-engagement

NO_OP is stronger than silence.

Used When

    Conditions insufficient

    Data ambiguous

    Risk unclear

    Structure incomplete

NO_OP Means

    “We choose not to act, intentionally.”

48.8 MANDATE VS POSITION STATE MATRIX
Mandate \ State	NO_POSITION	OPEN	REDUCING	CLOSING	CLOSED
ENTRY	✅	❌	❌	❌	❌
HOLD	❌	✅	✅	❌	❌
REDUCE	❌	✅	❌	❌	❌
CLOSE	❌	✅	✅	❌	❌
NO_OP	✅	✅	✅	❌	✅
48.9 ESCALATION RULES

Certain conditions force escalation regardless of mandate:

    Risk invariant breach → CLOSE

    Liquidation buffer breach → CLOSE

    Exposure violation → REDUCE or CLOSE

    Structural invalidation → CLOSE

Mandates cannot override escalation.
48.10 MANDATE PURITY RULES

    Mandates must not reference PnL

    Mandates must not reference emotions

    Mandates must not reference predictions

    Mandates must not assume future price

Mandates are conditional responses, not forecasts.
48.11 NEXT SECTION

49 — Entry, Reduce, Exit Zones (Structural Primitives)

Will formalize:

    Entry Zone

    Reduction Zone

    Exit Zone

    Overlapping zone resolution

    Zone priority

    ## 49. ENTRY, REDUCTION & EXIT ZONES — STRUCTURAL PRIMITIVES

This section defines **price-space primitives** that govern *where* actions may occur.

Zones are **structural**, not signals.
They constrain *permissible execution locations*.

A mandate may exist without a valid zone.
A zone may exist without a mandate.
**Both must align** for action.

---

## 49.1 CORE PRINCIPLE

```text
Mandates decide WHAT.
Zones decide WHERE.
Risk decides IF.

No execution may occur outside a valid zone.
49.2 ZONE TAXONOMY (COMPLETE)

Only three zone types exist:

    ENTRY ZONE

    REDUCTION ZONE

    EXIT ZONE

No hybrid zones.
No implicit zones.
No dynamic renaming.
49.3 ENTRY ZONE

Definition

A bounded price region where initiating exposure is permitted

ENTRY ZONES define acceptable entry prices, not exact levels.

ENTRY ZONE MAY BE DERIVED FROM

    Liquidity sweep completion

    Stop-hunt region resolution

    Post-liquidation stabilization

    Demand / supply imbalance

    Structure reclaim

    Compression release

    Prior high-velocity origin

ENTRY ZONE MUST

    Be bounded (upper + lower)

    Exist before ENTRY mandate

    Be invalidated if broken structurally

ENTRY ZONE MUST NOT

    Move after definition

    Expand to “fit price”

    Exist inside invalidated structure

49.4 REDUCTION ZONE

Definition

A bounded region where exposure reduction is allowed or required

REDUCTION ≠ weakness
REDUCTION = risk compression

REDUCTION ZONES MAY BE DERIVED FROM

    Prior liquidation clusters

    Historical liquidity absorption zones

    Opposing-side liquidity pools

    Mean reversion magnet zones

    High participation nodes

    Volatility expansion thresholds

    Known check-point regions from memory

REDUCTION ZONE PROPERTIES

    May overlap ENTRY or EXIT zones

    May trigger partial or full reduction

    Must specify reduction ceiling (max reducible %)

REDUCTION ZONES ARE

    Context-sensitive

    Risk-sensitive

    Non-directional

49.5 EXIT ZONE

Definition

A bounded region where full position termination is required

EXIT is non-negotiable once triggered.

EXIT ZONES MAY BE DERIVED FROM

    Structural invalidation

    Opposing liquidity dominance

    Failed continuation through zone

    Absorption against position

    Liquidity cascade in opposite direction

    Risk invariant breach

    Maximum adverse excursion threshold

EXIT ZONE OVERRIDES

    ENTRY logic

    REDUCTION logic

    Narrative persistence

49.6 ZONE PRIORITY HIERARCHY

When zones overlap:

EXIT > REDUCTION > ENTRY

Rules:

    EXIT always wins

    REDUCTION may preempt ENTRY

    ENTRY never overrides REDUCTION or EXIT

49.7 PARTIAL VS FULL EXIT LOGIC

Zones do not encode intent.
They encode permission.

Decision logic determines:

    Partial exit

    Full exit

Example:

    Liquidity zone encountered

    If opposing absorption detected → EXIT

    If momentum persists → REDUCE

    If neither → HOLD

49.8 ZONE INVALIDATION RULES

A zone is invalid if:

    Price fully traverses it without reaction

    Structural premise breaks

    Liquidity expectation fails

    Time-based decay exceeds tolerance

    Higher-priority zone supersedes it

Invalid zones must be destroyed.
No reuse permitted.
49.9 MULTI-ZONE STACKING

Multiple zones may coexist:

    Nested zones

    Sequential zones

    Opposing zones

Rules:

    Zones must be ordered by priority

    Zones must not contradict invariants

    Only one EXIT zone may be active at a time

49.10 ZONE VS TIMEFRAME

Zones are timeframe-agnostic.

Weekly / daily labels are irrelevant.
Only structure origin + memory validity matter.

A zone exists until invalidated — not until a candle closes.
49.11 ZONE SILENCE RULE

If no valid zone exists:
→ NO_OP is mandatory

No forced entries.
No anticipation.
No synthetic zones.
49.12 NEXT SECTION

50 — Position Lifecycle & Transitions

Will formalize:

    State machine

    Allowed transitions

    Transition guards

    Failure paths

    ## 50. POSITION LIFECYCLE & TRANSITIONS — STATE MACHINE PRIMITIVES

This section defines **how a position exists over time**.

A position is not a trade.
A position is a **stateful exposure object** governed by invariants.

No action is allowed outside a valid state transition.

---

## 50.1 CORE PRINCIPLE

```text
Positions do not evolve.
They transition.

Every change must be:

    Explicit

    Valid

    Irreversible (except via defined reverse transition)

50.2 POSITION STATE ENUMERATION (EXHAUSTIVE)

Only the following states are permitted:

    FLAT

    PENDING_ENTRY

    OPEN

    REDUCING

    CLOSING

    CLOSED

    FAILED

No hidden states.
No implicit states.
No “paused”, “waiting”, or “monitoring”.
50.3 STATE DEFINITIONS
50.3.1 FLAT

Definition

No exposure exists for a symbol

Properties:

    Zero position size

    Zero directional bias

    No active risk

    No active zones bound to execution

Allowed transitions:

    → PENDING_ENTRY

50.3.2 PENDING_ENTRY

Definition

A valid entry mandate exists, awaiting execution conditions

Properties:

    Entry zone defined

    Risk calculated

    Size precomputed

    No exposure yet

Allowed transitions:

    → OPEN (on valid entry execution)

    → FLAT (mandate invalidated)

Forbidden:

    Partial fills

    Size modification

    Direction changes

50.3.3 OPEN

Definition

Exposure exists and is fully established

Properties:

    Direction fixed

    Size fixed (unless reducing)

    Risk actively consumed

    Zones actively monitored

Allowed transitions:

    → REDUCING

    → CLOSING

    → FAILED

Forbidden:

    Increasing size (no pyramiding unless explicit future invariant)

    Direction reversal

    Silent exit

50.3.4 REDUCING

Definition

Exposure is being intentionally reduced

Properties:

    Partial exits in progress

    Risk compression active

    Direction unchanged

    Position still alive

Allowed transitions:

    → OPEN (reduction complete)

    → CLOSING

    → FAILED

Rules:

    Reduction % must be monotonic

    Cannot increase exposure

    Cannot reduce beyond zero

50.3.5 CLOSING

Definition

Full exit is in progress or mandated

Properties:

    No new risk allowed

    No new reductions

    Terminal intent

Allowed transitions:

    → CLOSED

    → FAILED

Forbidden:

    Re-entry

    Reversal

    Reduction logic

50.3.6 CLOSED

Definition

Position terminated normally

Properties:

    Exposure = 0

    P&L finalized

    Zones invalidated

    Memory recorded

Allowed transitions:

    → FLAT only (after cleanup)

50.3.7 FAILED

Definition

Position violated an invariant

Properties:

    Forced termination

    Error state

    No recovery permitted

Allowed transitions:

    → CLOSED only (forced)

50.4 TRANSITION GRAPH (CANONICAL)

FLAT
 └─→ PENDING_ENTRY
      ├─→ OPEN
      └─→ FLAT

OPEN
 ├─→ REDUCING
 │    ├─→ OPEN
 │    └─→ CLOSING
 ├─→ CLOSING
 └─→ FAILED

CLOSING
 ├─→ CLOSED
 └─→ FAILED

FAILED
 └─→ CLOSED

Any transition not shown is illegal.
50.5 TRANSITION GUARDS

Every transition requires:

    Valid mandate

    Valid zone

    Risk invariant satisfied

Additionally:

    OPEN → REDUCING requires REDUCTION ZONE

    OPEN → CLOSING requires EXIT ZONE or invariant breach

    Any → FAILED requires invariant violation

50.6 DIRECTIONAL IMMUTABILITY

Once in OPEN:

    Direction cannot change

    Opposite signal must trigger CLOSING, not reversal

    Reversal requires full reset through FLAT

This enforces:

Close first. Then reassess.

50.7 SINGLE POSITION PER SYMBOL INVARIANT

At most one position per symbol may exist.

This applies across:

    Timeframes

    Strategies

    Mandates

Any attempt to open a second position:
→ ILLEGAL
50.8 LIQUIDATION & FORCED FAILURE

Immediate FAILED transition if:

    Liquidation price breached

    Margin invariant broken

    Risk > allowed maximum

    Exchange rejection invalidates protection

FAILED is terminal.
50.9 STATE SILENCE RULE

If state is:

    Undefined

    Ambiguous

    Corrupted

→ Force FAILED

No assumptions permitted.
50.10 NEXT SECTION

51 — Position & Risk Invariants

Will formalize:

    Exposure limits

    Leverage constraints

    Liquidation avoidance

    Account-level coupling

    ## 51. POSITION & RISK CONSTRAINTS — INVARIANTS

This section defines **non-negotiable truths** governing exposure, leverage, and survival.

If any invariant is violated:
→ **Immediate FAILED state**
→ **Forced close**
→ **No recovery**

Risk is not optimized.
Risk is **constrained**.

---

## 51.1 CORE RISK AXIOMS

1. **Survival > Opportunity**
2. **Capital preservation precedes profit**
3. **No trade is mandatory**
4. **All risk must be knowable at entry**
5. **Unknowable risk = forbidden**

---

## 51.2 ACCOUNT-LEVEL INVARIANTS

### 51.2.1 MAX RISK PER TRADE

```text
Risk_per_trade ≤ R_max

Where:

    R_max is a fixed fraction of account equity

    Default canonical value: 1%

Violations:

    Variable risk per trade

    “Confidence-based” sizing

    Ad-hoc overrides

Result:
→ FAILED
51.2.2 MAX CONCURRENT RISK

Σ(all open position risk) ≤ R_total_max

Typical bounds:

    2–3% aggregate

    Hard ceiling, not soft target

Prevents:

    Correlated blowups

    Multi-position liquidation cascades

51.2.3 DRAWDOWN HALT INVARIANT

If account drawdown exceeds threshold:

DD ≥ DD_max → NO NEW POSITIONS

Optional:

    Forced FLAT across all symbols

    Cooling-off period (time-based, not performance-based)

51.3 POSITION-LEVEL INVARIANTS
51.3.1 SINGLE POSITION PER SYMBOL

Re-stated for clarity:

One symbol → one position → one direction

Opposite signal while OPEN:
→ CLOSE
→ Reset to FLAT
→ Re-evaluate
51.3.2 DIRECTIONAL IRREVERSIBILITY

Once OPEN:

    Direction cannot flip

    Scaling in opposite direction forbidden

    Hedging forbidden (unless explicitly designed later)

51.4 LEVERAGE INVARIANTS

Leverage is derived, not selected.
51.4.1 LIQUIDATION-AWARE LEVERAGE

Leverage must satisfy:

Liquidation_price ≠ reachable under normal volatility

Formally:

    Stop-loss must be hit before liquidation

    Liquidation must be structurally impossible within defined stop

If:

Stop_distance ≥ Liquidation_distance

→ Trade forbidden
51.4.2 VOLATILITY-ADJUSTED LEVERAGE

Leverage must account for:

    Recent realized volatility

    Historical wicks

    Known liquidation cascade regions

High volatility → lower leverage
Low volatility → leverage still capped
51.4.3 LEVERAGE HARD CAP

Absolute ceiling regardless of setup quality.

Example:

Max leverage ≤ 5x (illustrative)

No exceptions.
51.5 STOP-LOSS INVARIANTS
51.5.1 STOP REQUIRED AT ENTRY

A position cannot exist without:

    Defined stop-loss

    Known stop distance

    Known loss amount

Market orders without stop:
→ FAILED
51.5.2 STOP IMMUTABILITY (WEAK FORM)

Stops may:

    Move in direction of profit (risk reduction)
    Stops may NOT:

    Increase risk

    Move away from price

51.6 PARTIAL EXIT INVARIANTS
51.6.1 REDUCTION IS NOT EXIT

Partial exits:

    Reduce exposure

    Do not terminate position

    Must not invalidate stop logic

51.6.2 REDUCTION MUST BE JUSTIFIED

Reduction requires:

    Defined reduction zone

    Explicit mandate (liquidity zone, absorption, velocity decay, etc.)

No arbitrary profit-taking.
51.6.3 REDUCTION CANNOT INCREASE RISK

After reduction:

Remaining position risk ≤ prior risk

If reduction increases liquidation proximity:
→ Forbidden
51.7 TIME & EVENT RISK INVARIANTS
51.7.1 NEWS / EVENT RISK

Positions must not:

    Be opened immediately before known high-risk events

    Be held through events unless explicitly allowed

Event windows are:

    Structural risk, not signal risk

51.7.2 ROLLOVER / LIQUIDITY GAPS

If:

    Spread expansion risk high

    Liquidity thinning expected

Then:

    No new entries

    Optional forced reduction

51.8 CORRELATION & CLUSTER RISK

If multiple symbols:

    Share liquidity pools

    Share liquidation clusters

    Move as correlated basket

Then:

    Treat as single risk unit

    Aggregate exposure applies

51.9 FAILURE CONDITIONS (NON-EXHAUSTIVE)

Immediate FAILED if:

    Stop rejected by exchange

    Margin calculation invalid

    Position size mismatch

    Partial fill leaves unprotected exposure

    Slippage invalidates risk assumptions

    Data integrity breach

51.10 SILENCE OVER ASSUMPTION

If risk cannot be computed:
→ No trade

If liquidation proximity uncertain:
→ No trade

If leverage implications unclear:
→ No trade
51.11 NEXT SECTION

52 — Mandate Types & Hierarchy

Will define:

    Entry mandates

    Reduction mandates

    Exit mandates

    Conflict resolution

    ## 52. MANDATE TYPES & HIERARCHY

This section defines **what actions M6 is allowed to take**, under **which conditions**, and **how conflicts are resolved**.

A mandate is **permission**, not obligation.

No mandate may:
- Interpret market intent
- Assert quality
- Override risk invariants
- Force action

---

## 52.1 CORE MANDATE PRINCIPLES

1. **Mandates enable actions, never force them**
2. **Risk invariants dominate all mandates**
3. **Multiple mandates may coexist**
4. **Conflicts resolve by hierarchy, not confidence**
5. **Reduction is a first-class action**

---

## 52.2 MANDATE CATEGORIES (TOP LEVEL)

There are **four** canonical mandate types:

| Category | Purpose |
|--------|--------|
| ENTRY | Permission to open exposure |
| REDUCE | Permission to partially reduce exposure |
| EXIT | Permission to fully close exposure |
| HALT | Mandatory cessation of activity |

---

## 52.3 ENTRY MANDATES

ENTRY mandates allow **opening a new position** from FLAT state.

### 52.3.1 ENTRY PRECONDITIONS (ALL REQUIRED)

An ENTRY mandate is valid only if:
- No existing position on symbol
- All risk invariants satisfied
- Entry zone defined
- Stop-loss defined
- Direction unambiguous
- Time/event constraints satisfied

If any precondition fails:
→ ENTRY mandate is inert

---

### 52.3.2 ENTRY ZONE REQUIREMENT

Every ENTRY mandate must specify:

```text
Entry Zone = [price_low, price_high]

Properties:

    Zone may be narrow or wide

    Market orders allowed only inside zone

    No chasing outside zone

Entry outside zone:
→ Forbidden
52.3.3 ENTRY MANDATE TYPES (NON-EXHAUSTIVE)

Examples:

    Structural break confirmation

    Liquidity sweep completion

    Absorption completion

    Velocity expansion from compression

    Rejection from prior liquidation cluster

Each ENTRY mandate is:

    Independent

    Context-specific

    Non-exclusive

52.4 REDUCTION MANDATES (CRITICAL)

REDUCE mandates allow partial exposure reduction without closing position.

This is not optional behavior — it is fundamental.
52.4.1 REDUCE IS ALWAYS PERMITTED (SUBJECT TO RISK)

If a valid REDUCE mandate exists:
→ Reduction may occur
→ Even if ENTRY mandate still valid

REDUCE never requires EXIT to be valid.
52.4.2 REDUCTION ZONE REQUIREMENT

Every REDUCE mandate must define:

Reduction Zone = [price_low, price_high]
Reduction Fraction = f (0 < f < 1)

Examples:

    Reduce 25% at first liquidity memory zone

    Reduce 50% at prior liquidation cascade

    Reduce 33% at high-velocity rejection region

52.4.3 MULTIPLE REDUCTION MANDATES

Multiple REDUCE mandates may coexist:

    Different zones

    Different fractions

    Same direction

They:

    Execute independently

    Accumulate reductions

    Never reverse direction

52.4.4 REDUCTION VS EXIT CONFLICT

If both REDUCE and EXIT mandates are valid:

Hierarchy:

EXIT > REDUCE

EXIT dominates.
52.5 EXIT MANDATES

EXIT mandates allow full position closure.
52.5.1 EXIT PRECONDITIONS

EXIT mandates may trigger when:

    Stop-loss hit

    Risk invariant violated

    Structural invalidation occurs

    Opposing ENTRY mandate becomes dominant

    Liquidity exhaustion detected

    Forced liquidation risk detected

EXIT does not require consensus.
EXIT is conservative.
52.5.2 EXIT ZONE REQUIREMENT

EXIT mandates must specify:

    Hard exit (market)
    OR

    Exit zone (price band)

Ambiguous exit logic:
→ Forbidden
52.6 HALT MANDATES (OVERRIDING)

HALT mandates disable all other mandates.

Triggers include:

    Observation FAILED

    Risk engine FAILED

    Data integrity breach

    Exchange malfunction

    Clock desync

    Unknown state

HALT is:

    Immediate

    Terminal (until reset)

    Non-negotiable

52.7 MANDATE HIERARCHY (GLOBAL)

When multiple mandates are valid:

HALT
↓
EXIT
↓
REDUCE
↓
ENTRY

Lower mandates are ignored when higher mandates apply.
52.8 MANDATE COEXISTENCE RULES

Allowed:

    Multiple ENTRY mandates (evaluated while FLAT)

    Multiple REDUCE mandates (while OPEN)

    ENTRY + REDUCE (if partial position logic designed later)

Forbidden:

    ENTRY while OPEN

    Opposing ENTRY mandates simultaneously

    REDUCE that increases risk

    EXIT that reopens position

52.9 MANDATE EXPIRY

Mandates are not permanent.

Each mandate must define:

    Expiry condition (price-based, time-based, state-based)

    Invalidating condition

Expired mandate:
→ Removed silently
52.10 SILENCE RULE

If:

    No mandate valid

    Or mandates conflict unresolved

    Or risk unclear

Then:
→ Do nothing

Silence is a valid outcome.
52.11 NEXT SECTION

53 — Position Lifecycle States

Will define:

    FLAT

    PENDING

    OPEN

    REDUCING

    EXITING

    HALTED

    ## 53. POSITION LIFECYCLE STATES

This section defines the **finite, explicit lifecycle states** a position may occupy.
States are **descriptive, not predictive**.
State transitions are **event-driven**, not time-driven.

There are **no hidden states**.
There are **no implied transitions**.
There is **no ambiguity**.

---

## 53.1 CORE PRINCIPLES

1. A position is always in **exactly one** lifecycle state
2. State transitions occur only via **explicit events**
3. Risk invariants apply in **all states**
4. Some states are **terminal**
5. Silence (no transition) is always valid

---

## 53.2 CANONICAL STATES (COMPLETE SET)

```text
FLAT
PENDING
OPEN
REDUCING
EXITING
HALTED

No other states are permitted.
53.3 STATE DEFINITIONS
53.3.1 FLAT

Definition:
No exposure exists for the symbol.

Properties:

    Position size = 0

    No directional bias

    No leverage allocated

    No liquidation risk

Permitted Mandates:

    ENTRY

    HALT

Forbidden Mandates:

    REDUCE

    EXIT

Valid Transitions:

FLAT → PENDING
FLAT → HALTED

53.3.2 PENDING

Definition:
An entry is authorized but not yet filled.

This state exists to prevent:

    Duplicate entries

    Race conditions

    Overlapping orders

Properties:

    Direction defined

    Entry zone defined

    Stop defined

    Size defined

    No exposure yet

Permitted Mandates:

    ENTRY (same direction only)

    EXIT (cancel intent)

    HALT

Forbidden Mandates:

    REDUCE

Valid Transitions:

PENDING → OPEN
PENDING → FLAT   (entry invalidated / expired)
PENDING → HALTED

53.3.3 OPEN

Definition:
A position exists with non-zero exposure.

Properties:

    Direction fixed

    Leverage applied

    Liquidation risk exists

    Stop-loss active

Permitted Mandates:

    REDUCE

    EXIT

    HALT

Forbidden Mandates:

    ENTRY (any direction)

Valid Transitions:

OPEN → REDUCING
OPEN → EXITING
OPEN → HALTED

53.3.4 REDUCING

Definition:
A partial reduction is in progress or has just occurred.

This is a transient but explicit state to avoid:

    Multiple overlapping reductions

    Race conditions on size updates

Properties:

    Position size decreasing

    Direction unchanged

    Risk decreasing

    Stop-loss may be adjusted (optional, rule-defined)

Permitted Mandates:

    REDUCE (additional)

    EXIT

    HALT

Forbidden Mandates:

    ENTRY

Valid Transitions:

REDUCING → OPEN      (if size remains > 0)
REDUCING → FLAT      (if size reaches 0)
REDUCING → EXITING
REDUCING → HALTED

53.3.5 EXITING

Definition:
Full closure is authorized and in progress.

Properties:

    Direction irrelevant

    Size collapsing toward zero

    No new risk allowed

Permitted Mandates:

    HALT

Forbidden Mandates:

    ENTRY

    REDUCE

Valid Transitions:

EXITING → FLAT
EXITING → HALTED

53.3.6 HALTED (TERMINAL)

Definition:
Execution is forcibly stopped due to systemic or constitutional failure.

Properties:

    All mandates ignored

    All transitions blocked

    Manual reset required

Permitted Mandates:

    None

Valid Transitions:

HALTED → (none, until external reset)

HALTED is absorbing.
53.4 STATE TRANSITION RULES (GLOBAL)

    No skipping states

        e.g. FLAT → OPEN is forbidden

    No implicit transitions

    No automatic recovery

    HALT dominates all transitions

    State change must be atomic

53.5 INVALID STATE COMBINATIONS

Forbidden conditions:

    OPEN with size = 0

    FLAT with active stop-loss

    REDUCING with increasing size

    EXITING with new orders

    Any state with both ENTRY and EXIT active

Detection of invalid state:
→ Immediate HALT
53.6 SILENCE RULE (REITERATED)

If:

    No valid mandate

    No valid transition

    No explicit trigger

Then:
→ Remain in current state

Doing nothing is correct.
53.7 NEXT SECTION

54 — Position & Risk Invariants

Will define:

    Max positions per symbol

    Opposite-direction handling

    Leverage constraints

    Liquidation distance rules

    Exposure caps

    Correlation limits

    ## 54. POSITION & RISK CONSTRAINTS AS INVARIANTS

If:

A position exists

A mandate appears in the opposite direction

Then:

Existing position MUST be fully closed first


Explicit Sequence Required:

OPEN → EXITING → FLAT → (new ENTRY allowed)


Forbidden:

Simultaneous close-and-reverse

Partial hedge

Direction overwrite

54.4 MAX RISK PER POSITION
Invariant 54.4.1 — Risk Budget

Each position must define a maximum loss at entry.

Max Loss ≤ RISK_BUDGET


Where:

Risk is measured at stop-loss

Risk budget is defined externally (e.g. % equity)

Forbidden:

Undefined stop-loss

Dynamic risk expansion

Stop placement after entry

54.5 LEVERAGE CONSTRAINTS
Invariant 54.5.1 — Liquidation Safety Margin

Leverage must be chosen such that:

Distance(entry_price, liquidation_price) ≥ MIN_LIQUIDATION_BUFFER


Properties:

Liquidation price must be known before entry

Buffer measured in % or ATR (implementation-defined)

Buffer must remain valid after reductions

If liquidation buffer shrinks below minimum:
→ Forced EXIT or HALT (policy-defined)

Invariant 54.5.2 — Exposure-Aware Leverage

Leverage is not a fixed number.
It is derived from:

Account equity

Position size

Stop distance

Liquidation buffer

Correlated exposure (see 54.8)

Forbidden:

Hard-coded leverage

Ignoring liquidation distance

Increasing leverage after entry

54.6 STOP-LOSS INVARIANTS
Invariant 54.6.1 — Mandatory Stop

Every OPEN or PENDING position MUST have:

A stop-loss

Defined before entry

Immutable unless reducing or exiting

Forbidden:

No stop

Stop added post-entry

Stop widening

Invariant 54.6.2 — Stop Must Precede Liquidation
stop_price MUST be reached before liquidation_price


If not:
→ Entry is invalid

54.7 PARTIAL REDUCTION CONSTRAINTS
Invariant 54.7.1 — Reduction Only Reduces Risk

A REDUCE mandate must satisfy:

New risk < Previous risk


Valid reductions:

Size decrease

Exposure decrease

Forbidden:

Reduction that increases leverage

Reduction that increases liquidation risk

Invariant 54.7.2 — Reduction Is Optional, Never Forced

Presence of:

Liquidity zone

Historical liquidation region

Prior high-velocity move

May allow REDUCE
But must not force EXIT

Full exit vs partial reduction is:
→ Contextual
→ Mandate-driven
→ Never automatic

54.8 CORRELATED EXPOSURE LIMITS
Invariant 54.8.1 — Correlation Awareness

Total exposure must consider correlation:

Examples:

BTC / ETH

BTC / BTC.D

Index constituents

Constraint:

Total correlated risk ≤ CORRELATION_CAP


Forbidden:

Treating correlated symbols as independent

Full risk on multiple highly correlated assets

54.9 EVENT-BASED EXIT DOMINANCE
Invariant 54.9.1 — Forced Exit Events

Certain events override all strategy logic:

Examples:

Exchange instability

Margin rule changes

System HALT

Risk system breach

Result:

Any OPEN → EXITING


No discretion.

54.10 INVARIANT VIOLATION HANDLING

If any invariant fails:

Cancel all pending entries

Block new mandates

Transition to HALTED

Require explicit human intervention

No auto-recovery.

54.11 WHAT THIS ENABLES

These invariants guarantee:

No overexposure

No liquidation by design

Deterministic behavior

Safe partial exits

Clean reversals

Strategy composability

54.12 NEXT SECTION

55 — Mandate Types & Semantics

Will define:

ENTRY

REDUCE

EXIT

HALT

Their payloads

Their allowed contexts



## 55.2 CORE MANDATE TYPES (MINIMAL SET)

There are exactly **four** mandate types.

No others are permitted unless explicitly added.

---

### 55.2.1 ENTRY MANDATE

**Purpose:**  
Request opening a new position.

**Preconditions:**
- No existing position on symbol
- All risk invariants satisfied
- Stop-loss defined
- Direction defined

**Payload (Conceptual):**
```text
symbol
direction (LONG | SHORT)
entry_zone
stop_loss
size (or risk budget)
context (opaque reference only)

Semantics:

    ENTRY is atomic

    ENTRY may be rejected silently

    ENTRY never modifies existing positions

Forbidden:

    ENTRY when position exists

    ENTRY without stop

    ENTRY with implicit leverage

55.2.2 REDUCE MANDATE

Purpose:
Reduce exposure of an existing position.

Important:
You correctly noted this earlier — REDUCE is natural and mandatory to include.

REDUCE is not EXIT.

Preconditions:

    Position exists

    Reduction decreases risk

Payload (Conceptual):

symbol
reduction_type (SIZE | EXPOSURE)
amount (absolute or percentage)
reason (liquidity_zone | volatility | risk_adjustment)

Semantics:

    REDUCE is optional

    REDUCE never increases risk

    REDUCE does not change direction

Use cases:

    Approaching historical liquidity zone

    Prior liquidation cascade region

    Velocity exhaustion

    Absorption detected

Forbidden:

    REDUCE that increases leverage

    REDUCE that widens stop

    REDUCE on non-existent position

55.2.3 EXIT MANDATE

Purpose:
Fully close an existing position.

Preconditions:

    Position exists

Payload (Conceptual):

symbol
exit_reason (structural | risk | invalidation | emergency)

Semantics:

    EXIT is final

    EXIT dominates REDUCE

    EXIT transitions position → FLAT

Use cases:

    Structural invalidation

    Opposite-direction mandate

    Risk invariant breach

    External emergency event

55.2.4 HALT MANDATE

Purpose:
Stop all trading activity.

Preconditions:

    None

Payload (Conceptual):

reason
scope (symbol | global)

Semantics:

    HALT is terminal

    HALT blocks all future mandates

    HALT may force EXITs depending on reason

55.3 MANDATE PRIORITY ORDER

When multiple mandates exist:

HALT
↓
EXIT
↓
REDUCE
↓
ENTRY

Higher priority mandates suppress lower ones.
55.4 MULTIPLE MANDATES — ALLOWED, BUT ORDERED

You asked earlier whether multiple mandates are allowed.

Answer: Yes — with constraints.
55.4.1 Multiple Mandates Per Symbol

Allowed only if:

    They do not conflict

    They respect priority order

Example (VALID):

REDUCE 25%
REDUCE 25%
EXIT

Example (INVALID):

ENTRY LONG
ENTRY SHORT

55.4.2 Conditional Mandates

Mandates may be conditional, but conditions must be explicit.

Example:

IF price enters zone A → REDUCE
IF price breaks structure → EXIT

No implicit chaining.
55.5 WHAT MANDATES MUST NOT DO

Mandates must NOT:

    Interpret observations

    Assert market meaning

    Predict outcomes

    Modify state directly

    Persist memory

    Override invariants

Mandates are requests, not decisions.
55.6 WHY THIS STRUCTURE MATTERS

This design allows:

    Narrative-style “if this then that” logic

    Multiple scenario preparation

    Context-dependent exits vs reductions

    Clean reversals

    Risk-first execution

Without embedding interpretation in execution.
55.7 NEXT SECTION

56 — Position Lifecycle States

Will define:

    FLAT

    PENDING

    OPEN

    REDUCING

    EXITING

    HALTED

    ## 56. POSITION LIFECYCLE STATES

This section defines the **only valid states a position may occupy**  
and the **allowed transitions between them**.

These states are **mechanical**, not interpretive.  
They exist to prevent ambiguity, race conditions, and hidden behavior.

---

## 56.1 CORE PRINCIPLES

1. A position is always in **exactly one state**
2. State transitions are **explicit**
3. No implicit or time-based transitions
4. All transitions are **mandate-driven**
5. Invariants are checked **before every transition**
6. No state may be skipped

---

## 56.2 POSITION STATES (EXHAUSTIVE)

There are **six** and only six states.

No additional states are permitted unless added here.

---

### 56.2.1 FLAT

**Definition:**  
No position exists for the symbol.

**Properties:**
- Zero exposure
- Zero leverage
- No stop
- No direction

**Allowed Transitions:**
- FLAT → PENDING (ENTRY mandate)
- FLAT → HALTED (HALT mandate)

**Forbidden:**
- REDUCE
- EXIT
- Any risk modification

---

### 56.2.2 PENDING

**Definition:**  
An ENTRY mandate has been accepted but not fully executed.

This exists to separate **intent** from **exposure**.

**Properties:**
- Direction defined
- Stop defined
- Size defined
- Exposure not yet live (or partially filled)

**Allowed Transitions:**
- PENDING → OPEN (entry filled)
- PENDING → FLAT (entry canceled / rejected)
- PENDING → HALTED (HALT mandate)

**Forbidden:**
- REDUCE (nothing to reduce yet)
- Reverse direction

---

### 56.2.3 OPEN

**Definition:**  
Position exists and carries exposure.

**Properties:**
- Direction active
- Stop-loss active
- Risk quantified
- Leverage applied

**Allowed Transitions:**
- OPEN → REDUCING (REDUCE mandate)
- OPEN → EXITING (EXIT mandate)
- OPEN → HALTED (HALT mandate)

**Forbidden:**
- ENTRY (one position per symbol invariant)
- Direction change without EXIT

---

### 56.2.4 REDUCING

**Definition:**  
Position exposure is actively being reduced.

**Important:**  
REDUCING is **transient**, not a resting state.

**Properties:**
- Direction unchanged
- Exposure decreasing
- Risk strictly decreasing

**Allowed Transitions:**
- REDUCING → OPEN (reduction complete)
- REDUCING → EXITING (EXIT mandate)
- REDUCING → HALTED (HALT mandate)

**Forbidden:**
- Increasing size
- Widening stop
- Adding leverage

---

### 56.2.5 EXITING

**Definition:**  
Position is in the process of being fully closed.

**Properties:**
- No new exposure allowed
- No stop modification
- No reductions (exit supersedes)

**Allowed Transitions:**
- EXITING → FLAT (exit complete)
- EXITING → HALTED (HALT mandate)

**Forbidden:**
- ENTRY
- REDUCE
- Direction change

---

### 56.2.6 HALTED

**Definition:**  
Trading on this symbol (or globally) is frozen.

**Properties:**
- No new mandates accepted
- No state transitions except forced exit (if defined by HALT reason)

**Allowed Transitions:**
- HALTED → FLAT (only if emergency exit required)
- No resumption allowed unless constitution amended

**Forbidden:**
- ENTRY
- REDUCE
- OPEN
- EXITING by strategy logic

---

## 56.3 STATE TRANSITION DIAGRAM (TEXTUAL)

```text
FLAT
 └─ ENTRY → PENDING
        └─ FILLED → OPEN
               ├─ REDUCE → REDUCING → OPEN
               ├─ EXIT → EXITING → FLAT
               └─ HALT → HALTED

Any State ── HALT → HALTED

56.4 OPPOSITE DIRECTION LOGIC (IMPORTANT)

You raised this explicitly earlier.

Rule:

    If conditions signal opposite direction while OPEN:
    → EXIT current position first
    → Only then may ENTRY occur

There is no direct OPEN → OPEN (opposite) transition.

This enforces:

    Clean reversals

    No hedge ambiguity

    No netting confusion

56.5 WHY REDUCING MUST EXIST AS A STATE

Without REDUCING:

    Partial exits become ambiguous

    Risk changes become opaque

    Execution and accounting blur together

REDUCING allows:

    Liquidity-based trims

    Velocity-based trims

    Absorption-based trims

    Exposure normalization

Without implying full invalidation.
56.6 WHAT THIS ENABLES LATER

This lifecycle cleanly supports:

    Narrative trading

    Multiple scenarios

    Partial exits vs full exits

    Risk-first logic

    Deterministic replay

    Auditable behavior

56.7 NEXT SECTION

57 — Position & Risk Constraints as Invariants

Will formalize:

    One-position-per-symbol

    Max risk per trade

    Leverage constraints

    Liquidation avoidance rules

    SECTION 57 — POSITION & RISK CONSTRAINTS AS INVARIANTS

Status: Binding
Layer: Execution Governance (M6-adjacent)
Scope: All positions, all symbols, all strategies
Purpose: Define non-negotiable constraints that bound execution behavior independently of strategy logic.

57.1 Definition: Invariant

An invariant is a condition that must hold before, during, and after any position-related state transition.

Invariants are not optional

Invariants are not strategy-dependent

Invariants cannot be overridden by mandates

Violation of an invariant results in forced rejection or forced exit, not degradation

57.2 Global Position Cardinality Invariant
57.2.1 One-Position-Per-Symbol Rule

For any symbol S:

At most one active position may exist at any time

Position is defined as any non-zero exposure (long or short)

Invariant:

∀ symbol S:
    count(active_positions[S]) ≤ 1


Implications:

Multiple entries in the same direction are forbidden

Scaling in is forbidden

Any attempt to enter while a position exists must be rejected or converted into a CLOSE/REDUCE mandate

57.3 Directional Exclusivity Invariant

A symbol cannot have simultaneous opposing directional exposure.

Invariant:

Long(S) and Short(S) cannot both be true


Enforcement Rule:

If a mandate proposes ENTRY in the opposite direction:

Existing position must be closed first

No atomic “flip” is allowed

Close → settle → re-evaluate → new entry (if still valid)

57.4 Mandatory Risk Definition Invariant

No position may exist without explicit, bounded risk.

Each position must define, at minimum:

Entry price

Stop-loss price

Position size

Direction

Invariant:

Position without stop-loss = invalid position


Consequences:

ENTRY mandates without a valid stop definition are rejected

Positions missing stops must be force-closed immediately

57.5 Fixed Risk Upper Bound Invariant

Each position must conform to a predefined maximum risk per trade.

Invariant (conceptual):

PositionRisk ≤ MaxRiskPerTrade


Where:

PositionRisk is calculated as:

|entry_price − stop_price| × position_size


MaxRiskPerTrade is a fixed system parameter (e.g., 1% of equity)

Notes:

Confidence, setup quality, or narrative strength are irrelevant

Risk must be normalized, not discretionary

57.6 Exposure Constraint Invariant

Total system exposure must remain bounded.

57.6.1 Per-Symbol Exposure

Exposure per symbol is capped absolutely

No mandate may increase exposure beyond this cap

57.6.2 Aggregate Exposure

Total notional exposure across all symbols must not exceed a global ceiling

Correlated symbols may share stricter joint limits

Invariant:

Σ exposure(all symbols) ≤ GlobalExposureLimit

57.7 Leverage Safety Invariant (Preliminary)

Leverage is constrained not by a fixed number, but by liquidation proximity.

Invariant:

DistanceToLiquidation ≥ MinimumSafetyBuffer


Where:

DistanceToLiquidation is computed from current price, leverage, and margin model

MinimumSafetyBuffer is a fixed safety threshold

Implications:

If leverage increase reduces safety buffer below threshold → forbidden

If price movement reduces buffer below threshold → REDUCE or EXIT required

(Full leverage model formalized in Section 58)

57.8 Risk Monotonicity Invariant

Once a position is opened:

Risk may stay the same or decrease

Risk may never increase

Forbidden actions:

Moving stop further away from entry

Increasing size without tightening stop

Increasing leverage while maintaining same stop

Invariant:

Risk(t+1) ≤ Risk(t)

57.9 Loss Acceptance Invariant

Losses are terminal facts, not negotiable states.

Rules:

Stops must be honored

No mandate may cancel or ignore a stop-loss

No retry, delay, or override is permitted

A stopped-out position transitions directly to CLOSED with realized loss.

57.10 Emergency Dominance Invariant

Risk invariants override all mandates.

Priority order:

HALT / FORCED_EXIT
> EXIT
> REDUCE
> ENTRY


If any invariant is violated:

All lower-priority mandates are ignored

System must move toward risk elimination, not optimization

57.11 Prohibited Behaviors (Explicit)

The following are constitutionally forbidden:

Scaling into positions

Martingale behavior

Averaging down

Risk increase after entry

Position resizing without stop adjustment

Directional flipping without full exit

Strategy-based override of risk limits

57.12 Summary

This section establishes that:

Positions are scarce, bounded, and fragile

Risk is explicit, fixed, and monotonic

Exposure is capped

Leverage is subordinate to liquidation safety

Strategy may propose actions, but invariants decide

Execution is constrained before intelligence is applied.

SECTION 58 — LEVERAGE & LIQUIDATION AWARENESS INVARIANTS

Status: Binding
Layer: Execution Governance (M6-adjacent)
Scope: All leveraged positions, all symbols
Purpose: Prevent liquidation risk by construction, not by reaction.

58.1 Definition: Liquidation Awareness

Liquidation awareness means the system must reason about liquidation mechanically, not heuristically.

Liquidation is treated as a hard terminal failure, not a large loss.

Therefore:

Liquidation risk must be constrained before entry

Liquidation risk must be monitored during position lifetime

Liquidation risk must trigger mandatory reduction or exit

58.2 Absolute Liquidation Prohibition Invariant

Invariant:

Liquidation must be impossible under all allowed execution paths


This means:

A position whose liquidation price can be reached by normal volatility is invalid

Any mandate that could result in liquidation is rejected

Liquidation is not a tolerated outcome under any circumstance.

58.3 Liquidation Distance Definition

For each position P, define:

L(P) = liquidation price (exchange-specific formula)

C = current market price

D(P) = distance to liquidation

For longs:

D(P) = C − L(P)


For shorts:

D(P) = L(P) − C


All liquidation logic must operate on distance, not leverage ratios.

58.4 Minimum Liquidation Safety Buffer Invariant

Each position must maintain a minimum liquidation buffer.

Invariant:

D(P) ≥ LiquidationSafetyBuffer


Where:

LiquidationSafetyBuffer is a fixed system parameter

Defined in price terms or percentage terms (implementation-specific)

This buffer must hold:

At entry

After any modification

Continuously during position lifetime

58.5 Leverage Is a Derived Quantity (Not a Control)

Leverage is not an independent control variable.

Rule:

Leverage is whatever value satisfies risk, stop, and liquidation invariants — nothing more.

Therefore:

No fixed leverage numbers (e.g. “10x”, “20x”) are authoritative

Leverage is computed after position size and stop are defined

58.6 Entry-Time Leverage Constraint

At entry, leverage must satisfy both:

Risk constraint (Section 57)

Liquidation buffer constraint

Invariant:

Leverage(P) such that:
    Risk(P) ≤ MaxRiskPerTrade
AND
    D(P) ≥ LiquidationSafetyBuffer


If no leverage satisfies both → ENTRY is forbidden

58.7 Runtime Liquidation Drift Invariant

Price movement may reduce liquidation distance even without leverage changes.

Invariant:

If D(P) < LiquidationSafetyBuffer:
    Mandatory action required


Mandatory actions (priority order):

REDUCE position size

Tighten stop (if valid)

EXIT position entirely

No waiting, no retries, no discretionary delay.

58.8 Liquidation vs Stop-Loss Relationship

A valid position must satisfy:

Invariant:

StopLossPrice must be strictly safer than LiquidationPrice


For longs:

StopLoss > LiquidationPrice


For shorts:

StopLoss < LiquidationPrice


This guarantees:

Stop executes before liquidation

Stop is the worst-case loss event

If violated → position is invalid and must be exited immediately.

58.9 Leverage Monotonicity Invariant

Once a position is open:

Effective leverage may only decrease

Effective leverage may never increase

Forbidden actions:

Increasing position size without capital increase

Reducing margin while position is open

Any action that reduces D(P)

58.10 Correlated Exposure Liquidation Invariant

If multiple positions are correlated:

Liquidation buffers must be evaluated jointly

Worst-case correlated move must be assumed

Invariant:

WorstCaseJointMove does not cause liquidation in any position


This prevents:

Individually “safe” positions causing collective liquidation

Hidden leverage via correlation

58.11 Emergency Liquidation Avoidance Rule

If liquidation risk becomes imminent:

All strategy logic is suspended

Narrative, mandates, and signals are ignored

Priority order:

FORCED_EXIT
> REDUCE
> STOP MANAGEMENT
> STRATEGY


The only objective is to restore liquidation safety or exit.

58.12 Prohibited Behaviors (Explicit)

The following are constitutionally forbidden:

Fixed leverage presets (“always 20x”)

Increasing leverage to “improve R:R”

Ignoring liquidation price because “stop is close”

Hoping for bounce near liquidation

Using liquidation as a stop-loss

Averaging down near liquidation

Partial exits that increase liquidation risk

58.13 Summary

This section establishes that:

Liquidation is not a risk, it is a system failure

Leverage is derived, not chosen

Distance to liquidation is the primary control variable

Safety buffers are mandatory and enforced

Strategy cannot justify liquidation exposure

Risk is bounded mechanically, not psychologically.

SECTION 59 — POSITION LIFECYCLE STATES & TRANSITIONS

Status: Binding
Layer: Execution Governance (M6)
Scope: All symbols, all positions
Purpose: Eliminate undefined behavior by enforcing a closed, explicit position state machine.

59.1 Core Principle

A position must always be in exactly one state.

There are:

No hybrid states

No implicit states

No inferred states

If a state cannot be named, it cannot exist.

59.2 Canonical Position States

The system recognizes exactly the following states:

59.2.1 FLAT

No open position exists for the symbol

Zero exposure

Zero leverage

Zero risk

59.2.2 ENTRY_PENDING

Entry conditions satisfied

Order submitted but not yet filled

No exposure yet

Cancelable

59.2.3 OPEN

Position is live and fully established

Exposure exists

Stop-loss defined

Liquidation-safe (Section 58 enforced)

59.2.4 REDUCING

Partial exit in progress

Exposure decreasing

Liquidation distance must increase, never decrease

59.2.5 EXIT_PENDING

Full exit initiated

Orders submitted to flatten position

No new actions permitted except exit completion

59.2.6 CLOSED

Position fully exited

PnL realized

Returns to FLAT after accounting

59.2.7 FORCED_EXIT

Emergency exit due to invariant violation

Triggered by:

Liquidation risk breach

Risk invariant breach

System failure

Strategy is ignored

59.3 Forbidden States (Explicit)

The following states must never exist:

“Half-open”

“Scaling in”

“Re-entering”

“Paused”

“Waiting”

“Recovering”

“Hedged but flat”

“Synthetic flat”

“Dormant”

If a concept requires one of these, it must be decomposed into valid states.

59.4 Allowed State Transitions

The state machine is strictly directed.

Valid transitions:
FLAT → ENTRY_PENDING
ENTRY_PENDING → OPEN
ENTRY_PENDING → FLAT          (cancel)
OPEN → REDUCING
REDUCING → OPEN               (reduction complete)
OPEN → EXIT_PENDING
REDUCING → EXIT_PENDING
EXIT_PENDING → CLOSED
CLOSED → FLAT
ANY → FORCED_EXIT
FORCED_EXIT → CLOSED
CLOSED → FLAT

59.5 Forbidden Transitions

The following transitions are illegal:

OPEN → ENTRY_PENDING

REDUCING → ENTRY_PENDING

OPEN → OPEN (re-entry / add)

REDUCING → REDUCING (chained partials)

EXIT_PENDING → OPEN

FORCED_EXIT → OPEN

CLOSED → OPEN (must pass through FLAT)

If such a transition is attempted, execution must halt.

59.6 Single-Position-Per-Symbol Invariant (Reinforced)

Invariant:

At most one non-FLAT position may exist per symbol


This applies across all states except FLAT.

If a symbol is not FLAT:

ENTRY is forbidden

Only REDUCE or EXIT actions are permitted

59.7 Entry Exclusivity Invariant

A symbol may enter ENTRY_PENDING only if:

Current state is FLAT

No other pending orders exist

Risk and liquidation invariants are satisfied

No retries.
No overlapping entry logic.

59.8 Reduction Semantics

REDUCING means:

Exposure strictly decreases

Leverage strictly decreases

Liquidation distance strictly increases

Invariant:

REDUCING must move the system toward FLAT


A reduction may never:

Increase risk

Increase leverage

Add exposure

Reverse direction

59.9 Exit Semantics

EXIT_PENDING means:

Full flattening intent

No partial logic

No conditional logic

No strategy logic

Once in EXIT_PENDING:

Only execution mechanics remain

All mandates are ignored

59.10 Forced Exit Supremacy

FORCED_EXIT overrides all other logic.

Triggers include:

Liquidation buffer breach

Risk invariant breach

Invalid state transition

Internal consistency failure

Invariant:

FORCED_EXIT cannot be blocked, delayed, or overridden

59.11 State Purity Invariant

Each state has exactly one responsibility:

State	Responsibility
FLAT	Allow entry evaluation
ENTRY_PENDING	Await fill or cancel
OPEN	Manage risk
REDUCING	Reduce exposure
EXIT_PENDING	Exit completely
CLOSED	Finalize accounting
FORCED_EXIT	Emergency neutralization

No state may assume another’s responsibility.

59.12 Strategy Isolation Rule

Strategies and mandates may:

Propose transitions

They may never:

Enforce transitions

Bypass transitions

Invent states

Execution governance owns the state machine.

59.13 Summary

This section guarantees:

No ambiguous position behavior

No overlapping trades per symbol

No hidden scaling

No accidental leverage increases

Deterministic execution paths

Mechanical safety over strategy intent

A position is not an idea — it is a state machine with invariants.


SECTION 60 — MANDATE TYPES & RESOLUTION RULES

Status: Binding
Layer: Strategy → Execution Interface
Scope: All execution decisions
Purpose: Allow multiple mandates without allowing contradiction, escalation, or interpretation.

60.1 Core Principle

A mandate is a constrained permission, not a command.

Mandates:

Propose what may be done

Never assert what must be done

Never override execution invariants

Never override position state machine (Section 59)

Execution governance remains supreme.

60.2 Definition of a Mandate

A mandate is a structured declaration of the form:

IF [conditions]  
THEN [permitted action set]


A mandate:

Does not guarantee execution

Does not assert correctness

Does not imply urgency

Does not imply exclusivity

60.3 Canonical Mandate Types

The system recognizes exactly five mandate types.

No others are permitted.

60.3.1 ENTRY_MANDATE

Purpose: Allow the opening of a new position.

Permitted Actions:

Transition FLAT → ENTRY_PENDING

Hard Constraints:

Symbol must be FLAT

Risk invariants satisfied

Liquidation buffer satisfied

No other ENTRY_MANDATE currently active for symbol

Notes:

ENTRY mandates are mutually exclusive per symbol

Multiple ENTRY mandates across symbols are allowed

60.3.2 REDUCE_MANDATE

Purpose: Allow partial exposure reduction.

Permitted Actions:

Transition OPEN → REDUCING

Transition REDUCING → OPEN

Hard Constraints:

Position must already be OPEN or REDUCING

Reduction must strictly decrease exposure

Cannot reverse direction

Cannot increase leverage

Notes:

Multiple REDUCE mandates may coexist

Reductions are cumulative but bounded

60.3.3 EXIT_MANDATE

Purpose: Allow full position exit.

Permitted Actions:

Transition to EXIT_PENDING

Hard Constraints:

Position must exist

Overrides ENTRY and REDUCE mandates

Cannot be blocked by strategy logic

Notes:

EXIT mandates supersede all non-emergency intent

EXIT is final (no re-entry without FLAT)

60.3.4 BLOCK_MANDATE

Purpose: Explicitly prohibit new actions.

Permitted Actions:

None

Effect:

ENTRY prohibited

REDUCE prohibited

EXIT still permitted

Use Cases:

News windows

Rollover windows

Structural uncertainty

External risk

60.3.5 FORCED_EXIT_MANDATE

Purpose: Emergency liquidation prevention.

Permitted Actions:

Immediate transition to FORCED_EXIT

Hard Constraints:

Cannot be overridden

Cannot be delayed

Cannot be suppressed

Notes:

Generated only by execution/risk layer

Never strategy-generated

60.4 Mandate Priority Order

When multiple mandates are active, resolution is strictly ordered:

FORCED_EXIT
EXIT
REDUCE
BLOCK
ENTRY


Lower-priority mandates are ignored if higher-priority mandates are present.

60.5 Mandate Compatibility Matrix
Mandate A	Mandate B	Compatible
ENTRY	ENTRY	❌
ENTRY	REDUCE	❌
ENTRY	EXIT	❌
ENTRY	BLOCK	❌
REDUCE	REDUCE	✅
REDUCE	EXIT	❌
REDUCE	BLOCK	❌
EXIT	BLOCK	❌
BLOCK	EXIT	❌
FORCED_EXIT	Any	❌

If incompatible mandates are simultaneously active:

Lower priority mandate is discarded

No merge logic exists

60.6 Multi-Mandate Resolution Rule

Execution resolves mandates as follows:

Filter mandates by symbol

Sort by priority

Select highest-priority mandate

Validate against position state

Validate against invariants

Execute permitted action or do nothing

No retries.
No arbitration.
No negotiation.

60.7 Mandates Do Not Stack Directionally

Mandates:

Do not add exposure

Do not scale positions

Do not imply strength

Example (forbidden):

“Two ENTRY mandates imply higher confidence”

This is explicitly illegal.

60.8 Partial vs Full Exit Resolution

If both exist:

REDUCE_MANDATE + EXIT_MANDATE → EXIT wins

Liquidity zones may generate REDUCE

Risk breach must generate EXIT or FORCED_EXIT

This resolves your earlier concern:

“Liquidity zones can force partial exit OR full exit depending on circumstances”

The circumstance is mandate type, not interpretation.

60.9 Strategy Isolation Guarantee

Strategies:

Emit mandates

Never see execution outcome

Never adjust mandates based on fills

Execution:

Consumes mandates

Ignores intent when unsafe

Enforces invariants mechanically

60.10 Mandate Expiration

All mandates must define:

Scope (symbol)

Validity window (event-based or time-based)

Expired mandates are discarded silently.

No carryover.
No memory.
No persistence.

60.11 Summary

This section guarantees:

Multiple mandates are allowed

Conflicts are mechanically resolved

No mandate escalation

No strategy dominance

Partial vs full exit ambiguity eliminated

Execution remains deterministic and safe

Mandates describe permission, not belief.

SECTION 61 — RISK BUDGETING & EXPOSURE ACCOUNTING

Status: Binding
Layer: Execution / Risk
Scope: Portfolio-wide
Purpose: Ensure survivability, prevent liquidation cascades, and bound system exposure across symbols.

61.1 Core Principle

Risk is allocated, not inferred.

The system does not “feel” risk, estimate risk, or interpret danger.
It enforces pre-allocated, mechanically provable limits.

61.2 Definitions
61.2.1 Notional Exposure

For a position 
p
p:

notional_p = position_size × entry_price


This is direction-agnostic.

61.2.2 Account Equity
equity = balance + unrealized_pnl


Equity is sampled at execution time only.

61.2.3 Leverage (Effective)
effective_leverage = total_notional / equity


This is portfolio-wide, not per-position.

61.3 Global Risk Budget

The system defines a Global Risk Budget (GRB):

GRB = max_fraction_of_equity_at_risk


Example (illustrative, not prescriptive):

GRB = 5% of equity

This is the maximum loss tolerated across all open positions combined, assuming worst-case stop execution.

61.4 Per-Position Risk Allocation

Each position must reserve risk from the GRB.

For position 
p
p:

risk_reserved_p = |entry_price − stop_price| × position_size


Invariant:

Σ risk_reserved_p ≤ GRB × equity


If violated:

ENTRY_MANDATE rejected

REDUCE_MANDATE allowed

EXIT / FORCED_EXIT allowed

61.5 Cross-Symbol Exposure Constraint

Exposure is bounded not only by risk, but by correlation ignorance.

Invariant:

total_notional ≤ max_notional_multiplier × equity


This prevents:

Overexposure during volatility compression

Liquidation during correlated moves

Correlation is not estimated.
The system assumes worst-case correlation = 1.

61.6 Leverage as a Derived Quantity

Leverage is never set directly.

Instead, it is derived from:

Position size

Equity

Risk distance to stop

This prevents:

Arbitrary leverage selection

Hidden liquidation risk

Any ENTRY that implies leverage beyond allowed bounds is rejected.

61.7 Liquidation Distance Invariant

For every position:

distance_to_liquidation ≥ liquidation_buffer


Where liquidation_buffer is a fixed percentage or price distance.

If violated:

ENTRY prohibited

REDUCE permitted

EXIT / FORCED_EXIT triggered depending on severity

This directly satisfies your requirement:

“Leverage calculation must prevent liquidation and be aware of risk”

61.8 Exposure Rebalancing via Reduction

When new risk is proposed but GRB is exhausted:

System does not reshuffle

System does not net

System does not rebalance automatically

Only allowed path:

REDUCE_MANDATE on existing positions

Followed by new ENTRY if invariants pass

61.9 No Netting Assumption

Long and short positions do not cancel risk.

Example:

Long BTC

Short ETH

Risk is counted independently.

This avoids false safety from directional assumptions.

61.10 Worst-Case Accounting Rule

All risk calculations assume:

Stops slip

Liquidity vanishes

Correlation spikes

Execution delayed

If system survives worst-case, it survives all cases.

61.11 Interaction With Mandates
Mandate Type	Risk Budget Impact
ENTRY	Consumes GRB
REDUCE	Frees GRB
EXIT	Frees all reserved GRB
BLOCK	No change
FORCED_EXIT	Frees GRB immediately

Mandates cannot override risk accounting.

61.12 Summary

This section guarantees:

Portfolio-level risk control

Liquidation avoidance by construction

Leverage emerges from math, not choice

No correlation assumptions

No hidden exposure stacking

Deterministic rejection of unsafe actions

The system cannot accidentally blow up unless invariants are violated.
SECTION 62 — ENTRY QUALIFICATION & INVALID ENTRY CONDITIONS

Status: Binding
Layer: Execution / Control
Scope: Per-symbol, per-attempt
Purpose: Prevent forced, late, redundant, or structurally incoherent entries.

62.1 Core Principle

An entry is a response to conditions, not a desire to participate.

The system never enters because:

Price moved

Opportunity is “missed”

Conditions are “almost” met

An entry exists only when all qualification invariants are satisfied simultaneously.

62.2 Entry Qualification Model

An ENTRY is permitted if and only if all categories below pass:

Structural Eligibility

Positional Eligibility

Risk Eligibility

Temporal Eligibility

Conflict Eligibility

Failure in any category invalidates the entry.

62.3 Structural Eligibility

An entry must be tied to a defined entry zone.

62.3.1 Entry Zone Definition

An entry zone is a bounded price region derived from prior market behavior, such as:

Liquidity sweep region

Stop-hunt region

High-velocity origin region

Imbalance resolution zone

Liquidation cascade origin zone

The system does not name these externally.
They exist as internal structural references.

62.3.2 Zone Contact Requirement

Invariant:

current_price ∈ entry_zone


If price has already moved through the zone:

ENTRY is invalid

No chasing permitted

62.4 Positional Eligibility
62.4.1 Single Position Per Symbol

Invariant:

positions_open(symbol) ≤ 1


If violated:

ENTRY rejected

Only REDUCE or EXIT allowed

62.4.2 Opposite Direction Handling

If a position exists on the same symbol and a new valid entry is detected in the opposite direction:

Allowed sequence:

EXIT existing position

(Optional) wait for confirmation boundary

ENTER new position

Disallowed:

Simultaneous long + short

Partial hedge

Netting behavior

62.5 Risk Eligibility
62.5.1 Stop Must Exist Before Entry

Invariant:

stop_price defined BEFORE execution


If no stop exists:

ENTRY invalid

62.5.2 Risk Budget Availability

ENTRY must satisfy all constraints from Section 61.

If GRB exhausted:

ENTRY rejected

REDUCE permitted

EXIT permitted

62.5.3 Liquidation Safety

ENTRY invalid if it violates:

distance_to_liquidation ≥ liquidation_buffer


No exceptions.

62.6 Temporal Eligibility
62.6.1 No Late Entries

If price has moved more than a fixed fraction of the planned risk distance away from the zone:

|current_price − optimal_entry| > late_entry_threshold


Then:

ENTRY invalid

Prevents FOMO-style participation

62.6.2 No Re-Entry Without Structural Reset

After an EXIT or STOP:

The same zone cannot be reused

A new structural event must occur

This prevents:

Repeated losses in the same idea

Grinding behavior in chop

62.7 Conflict Eligibility
62.7.1 Higher-Order Conflict

If an active exit mandate or risk mandate conflicts with a proposed entry:

EXIT / REDUCE takes precedence

ENTRY rejected

62.7.2 Exposure Conflict

If entry increases exposure in a way that violates portfolio constraints (even if per-symbol is valid):

ENTRY rejected

62.8 Entry Is Binary

There is no concept of:

“Small probe”

“Test entry”

“Starter position”

ENTRY is atomic:

Either fully valid

Or not allowed

Scaling is handled only via explicit ADD mandates, defined later.

62.9 Entry Failure Is Silent

When an entry is rejected:

No retry

No downgrade

No alternative entry

The system simply does nothing.

Silence is the correct behavior.

62.10 Summary

This section ensures:

No chasing

No revenge entries

No overlapping positions

No late participation

No structurally incoherent trades

No risk-violating entries

An ENTRY exists only when the market hands it to the system.

SECTION 63 — EXIT TYPES & EXIT QUALIFICATION (FULL vs PARTIAL)

Status: Binding
Layer: Execution / Control
Scope: Per-position, per-symbol
Purpose: Define when and how positions may be reduced or closed, without prediction or discretionary interpretation.

63.1 Core Principle

Entries are optional. Exits are mandatory when conditions are met.

An EXIT is a response to conditions, not an opinion about future price.

There are only two exit classes:

PARTIAL EXIT (REDUCE)

FULL EXIT (CLOSE)

No other exit behaviors exist.

63.2 Exit Classification
63.2.1 PARTIAL EXIT (REDUCE)

A REDUCE:

Decreases position size

Keeps the position open

Does not invalidate the original trade thesis

REDUCE is permitted only when explicitly qualified.

63.2.2 FULL EXIT (CLOSE)

A CLOSE:

Terminates the position entirely

Ends the lifecycle of the trade

Resets eligibility for future entries (subject to Section 62.6.2)

CLOSE always has precedence over REDUCE.

63.3 Exit Qualification Model

An EXIT is evaluated across three independent dimensions:

Risk-Driven

Structure-Driven

Conflict-Driven

If any dimension qualifies for CLOSE → CLOSE is executed
If none qualify for CLOSE but at least one qualifies for REDUCE → REDUCE is executed
If none qualify → NO ACTION

63.4 Risk-Driven Exits (Highest Priority)
63.4.1 Stop-Loss (Hard Close)

Invariant:

current_price reaches stop_price


Action:

Immediate FULL EXIT

No partials

No delays

No overrides

This is non-negotiable.

63.4.2 Liquidation Risk Breach

If at any point:

distance_to_liquidation < liquidation_buffer


Action:

FULL EXIT immediately

This exit overrides all structural logic.

63.4.3 Portfolio Risk Breach

If global or symbol-level risk constraints are violated while a position is open:

REDUCE if reduction restores compliance

Otherwise FULL EXIT

Risk safety dominates trade logic.

63.5 Structure-Driven Exits
63.5.1 Partial Exit at Known Liquidity Regions

A REDUCE is permitted when price approaches a historically significant region, such as:

Prior liquidation clusters

Known stop-hunt regions

High-velocity rejection zones

Previously observed absorption zones

Conditions:

Trade is in profit

No opposing structural break has occurred

Position thesis remains valid

Purpose:

De-risk exposure

Realize partial gains

Preserve optionality

63.5.2 Full Exit at Structural Invalidation

A FULL EXIT is required when:

The structural premise that justified the entry no longer exists

Price invalidates the entry zone logic

Opposing structure confirms dominance

This applies even if:

Trade is in profit

Trade has not hit stop

Partial exits already occurred

63.6 Same Zone, Different Exit Outcomes

The same region may trigger REDUCE or CLOSE depending on context.

This is intentional.

Example (Abstract, Non-Interpretive):

Liquidity region approached:

If price stalls with no invalidation → REDUCE permitted

If price reacts violently against position → CLOSE required

The exit type is determined by what is violated, not by the zone itself.

Zones do not imply outcomes.

63.7 Conflict-Driven Exits
63.7.1 Opposite Entry Qualification While in Position

If, while in a position, conditions qualify for an opposite-direction entry:

Action:

FULL EXIT of current position

Position lifecycle ends

New entry evaluated independently under Section 62

There is no reversal without exit.

63.7.2 Mandate Conflict

If any higher-priority mandate requires exposure reduction or neutrality:

REDUCE if sufficient

Otherwise CLOSE

Execution mandates override trade-specific logic.

63.8 Exit Is Non-Symmetric to Entry

Important invariant:

Entry logic and Exit logic are not mirrors.

An entry zone:

Does not imply an exit zone

An exit zone:

Does not imply a new entry

This prevents oscillation and overfitting.

63.9 No Exit Prediction

The system does not:

Target exact highs/lows

Predict reversals

“Let winners run” by belief

All exits are condition-triggered.

63.10 Exit Finality

After a FULL EXIT:

Position lifecycle ends

Zone is invalidated

Re-entry requires a new structural event

No recycling of ideas.

63.11 Summary

This section enforces:

Absolute stop discipline

Liquidation safety

Context-aware partial exits

Mandatory exits on invalidation

No discretionary holding

No hedging

No hope-based behavior

The system exits because it must, not because it wants to.

SECTION 64 — ADD / SCALE RULES (POSITION INCREASE)

Status: Binding
Layer: Execution / Control
Scope: Per-position, per-symbol
Purpose: Define when increasing exposure is permitted, constrained, or forbidden.

64.1 Core Principle

Adding to a position is an exception, not a default behavior.

The system assumes:

A position is complete at entry

Additional exposure is opt-in, strictly gated

Scaling exists to exploit confirmation, not to repair error.

64.2 Absolute Prohibitions (Never Allowed)

The system MUST NEVER add to a position when:

Position is at a loss

Price has moved against the original structural premise

Liquidation distance has decreased since entry

Risk budget is fully allocated

Entry thesis is no longer dominant

Exposure increase would violate leverage constraints

Add would reduce liquidation buffer below invariant

Add is motivated by “averaging” or drawdown reduction

Averaging down is forbidden.

64.3 Add Classification

Only two add types exist:

STRUCTURAL ADD

CONFIRMATION ADD

No other add behaviors are valid.

64.4 Structural Add (Primary Add Type)
64.4.1 Definition

A STRUCTURAL ADD is permitted only when:

A new, independent structural event occurs

That event would justify a fresh entry if no position existed

The add is treated as:

A second entry sharing the same position container

64.4.2 Structural Add Conditions

All must be true:

Current position is in profit

Original entry thesis remains valid

New structure forms in favor of position direction

Add occurs from a qualified entry zone

Stop for entire position can be recalculated safely

Liquidation distance improves or remains unchanged

If any fail → ADD is forbidden.

64.4.3 Risk Handling

After a structural add:

Stop-loss is recalculated for entire position

Maximum loss must still respect per-trade risk cap

Liquidation buffer invariant must still hold

If recalculation fails → ADD rejected.

64.5 Confirmation Add (Secondary, Limited)
64.5.1 Definition

A CONFIRMATION ADD is a minor size increase used to:

Increase exposure after momentum confirmation

Exploit continuation after uncertainty resolves

This is not a full re-entry.

64.5.2 Confirmation Add Constraints

Size must be smaller than original entry

No more than one confirmation add per position

Must occur after structural confirmation (e.g., break + hold)

Cannot worsen liquidation profile

Cannot consume more than remaining risk budget

64.6 Add Frequency Limits

Per position:

Maximum STRUCTURAL ADDS: configurable (default = 1)

Maximum CONFIRMATION ADDS: 1

Maximum total adds per position: capped

Once add limit is reached → position becomes non-expandable

64.7 Add vs Partial Exit Interaction

Critical rule:

A position that has partially exited may NOT be added to.

Once exposure is reduced:

The system has acknowledged risk realization

Re-expansion would violate causal consistency

Partial exit locks add capability permanently.

64.8 Add vs Opposite Signal

If, at any point during add evaluation:

Opposite-direction entry conditions are met

Action:

CANCEL add

Trigger FULL EXIT under Section 63.7.1

Adds never override conflict resolution.

64.9 Add Is Not Recovery

Explicit invariant:

Adds may not be used to “improve average price.”

There is no concept of:

Cost basis optimization

Break-even rescue

“Better fill” after adverse move

Adds exist only for confirmation, never correction.

64.10 Add Visibility & Accountability

Every add must be attributable to:

A specific structural event

A specific rule path

If the system cannot state why an add occurred → it must not occur.

64.11 Summary

This section enforces:

No averaging down

No emotional scaling

No hidden martingale

Controlled, justified exposure increase

Risk-first recalculation on every add

Clear termination of add capability

The system adds because structure expanded — not because price moved.

SECTION 65 — ENTRY VALIDATION & ENTRY ZONE PRIMITIVES

Status: Binding
Layer: Decision / Execution Boundary
Scope: Per-entry, per-symbol
Purpose: Define what constitutes a valid entry zone and the minimum conditions required before any position may be opened.

65.1 Core Principle

An entry is not a signal — it is a location + condition pair.

The system does not enter because something happened.
It enters because price is at a place and a condition resolved.

Both are required.

65.2 Entry Zone Definition

An ENTRY ZONE is a bounded price region that satisfies:

Historical relevance

Structural justification

Liquidity interaction potential

An entry zone is pre-identified.
The system does not invent zones at runtime.

65.3 Canonical Entry Zone Types

The following entry zone primitives are allowed:

Liquidity Sweep Zone

Liquidation Memory Zone

Supply / Demand Zone

High-Velocity Origin Zone

Compression / Range Extremity Zone

Reclaimed Structure Zone

No other zone types are valid unless explicitly added later.

65.4 Liquidity Sweep Zone
Definition

A zone derived from:

Equal highs / equal lows

Obvious stop clustering

Prior failed extremes

Purpose:

Capture reactions after stop-hunts or engineered liquidity grabs.

Validation Requirements

Liquidity pool must be visible in historical price

Sweep must be detectable (wick or fast excursion)

Entry only permitted after sweep completes

No anticipation entries allowed.

65.5 Liquidation Memory Zone
Definition

A region where:

Forced liquidations occurred in the past

High volume coincided with extreme velocity

Price reacted violently and then normalized

Purpose:

Markets remember forced unwinds.

Validation Requirements

Historical liquidation data or proxy must exist

Zone must align with past volatility spike

Entry is conditional on current revisit or approach

Liquidation memory is context, not a signal.

65.6 Supply / Demand Zone
Definition

A bounded region where:

Price departed rapidly

Little to no trading occurred inside the zone

Imbalance remains unfilled

Purpose:

Exploit asymmetry left by aggressive participants.

Validation Requirements

Clear impulsive departure

No full mitigation since creation

Zone must not be invalidated structurally

Freshness increases priority but does not guarantee entry.

65.7 High-Velocity Origin Zone
Definition

The origin point of:

Sharp directional expansion

Large range candle(s)

Sudden volatility regime change

Purpose:

Velocity implies urgency; origins often matter.

Validation Requirements

Measurable acceleration

Clear before/after regime shift

Zone must not be fully traversed previously

Velocity without structure is insufficient.

65.8 Compression / Range Extremity Zone
Definition

A zone at:

Edge of prolonged consolidation

End of compression before expansion

Repeated rejection boundary

Purpose:

Compression resolves — extremes define risk.

Validation Requirements

Range must be statistically identifiable

Extremity must be tested multiple times

Entry requires resolution trigger

Mid-range entries are forbidden.

65.9 Reclaimed Structure Zone
Definition

A prior structural level that:

Was broken

Then reclaimed

Then held

Purpose:

Failed breakdowns/breakouts often reverse control.

Validation Requirements

Clear structural break

Reclaim must be decisive

Hold must persist beyond noise threshold

Reclaim without hold is invalid.

65.10 Entry Trigger Conditions

Being inside an entry zone is not sufficient.

At least one of the following must resolve:

Structural break in favor of direction

Absorption signature (price stalls + liquidations)

Momentum failure against opposing side

Reclaim-and-hold behavior

Opposing liquidity exhaustion

Triggers resolve inside or immediately adjacent to the zone.

65.11 Entry Direction Consistency

Entry direction must align with:

Higher-order narrative (if defined)

Active scenario logic

Position constraint invariants

If direction conflicts → entry is forbidden.

65.12 Entry Invalidators

An entry is automatically invalidated if:

Zone has been fully consumed

Structural premise breaks before trigger

Opposite zone activates first

Risk constraints cannot be satisfied

Liquidation buffer invariant fails

Invalidated zones are retired.

65.13 Single-Use Rule

Unless explicitly allowed:

An entry zone may only be used once.

Repeated attempts imply diminishing edge.

65.14 Entry Is Optional

Presence of:

A valid zone

A valid trigger

Does not force an entry.

Risk constraints, exposure limits, and system state always override.

65.15 Summary

This section enforces:

Entry as location + condition

Predefined, bounded zones

No reactive chasing

No mid-range gambling

Clear invalidation logic

Structural consistency before execution

The system enters where it has permission — not where it has excitement.


SECTION 66 — EXIT ZONE PRIMITIVES & EXIT CLASSIFICATION

Status: Binding
Layer: Position Management
Scope: Per-position, per-symbol
Purpose: Define how exits are formed, classified, and executed without ambiguity or contradiction.

66.1 Core Principle

Exits are not reactions — they are permissions.

A position is not exited because something feels wrong.
It is exited because a defined exit condition has been satisfied.

Exit logic is explicit, hierarchical, and non-emotional.

66.2 Exit Is a Classification, Not an Action

Every exit must belong to exactly one of the following classes:

Risk Exit

Structural Exit

Liquidity Exit

Objective Exit

Constraint Exit

Failure Exit

No exit may belong to more than one class simultaneously.

66.3 Exit Zones vs Exit Triggers

An EXIT ZONE is a price region where an exit may occur.
An EXIT TRIGGER is the condition that authorizes the exit.

Both must be defined.

Being inside an exit zone alone is insufficient.

66.4 Canonical Exit Zone Types

The system recognizes the following exit zone primitives:

Opposing Liquidity Zone

Liquidation Memory Zone

Opposing Supply / Demand Zone

High-Velocity Exhaustion Zone

Range Extremity / Compression Boundary

Structural Invalidation Level

66.5 Opposing Liquidity Zone
Definition

A region where:

Opposite-side stops are clustered

Equal highs/lows exist against the position

Prior liquidity sweeps originated

Purpose:

Liquidity is where reactions occur.

Exit Use

May authorize partial or full exit

Classification depends on trigger resolution

Presence alone does not force exit.

66.6 Liquidation Memory Zone (Exit Context)
Definition

A historical region of:

Forced liquidations

High volatility unwind

Violent resolution

Purpose:

Markets often react again where they previously broke participants.

Exit Use

Partial exit if momentum persists

Full exit if absorption or reversal emerges

Memory increases caution, not certainty.

66.7 Opposing Supply / Demand Zone
Definition

A zone where:

Strong counterparty previously dominated

Price departed aggressively in the opposite direction

Purpose:

This is where opposing intent may reassert.

Exit Use

Structural exit if rejection forms

Objective exit if zone is the target

Risk exit if rejection threatens stop integrity

66.8 High-Velocity Exhaustion Zone
Definition

A region where:

Expansion becomes unsustainable

Range or volatility spikes abruptly

Follow-through weakens

Purpose:

Speed often ends moves.

Exit Use

Partial exit favored

Full exit if velocity collapses or reverses

Velocity exhaustion without structure = caution, not exit.

66.9 Range Extremity / Compression Boundary
Definition

The outer boundary of:

A known range

A resolved compression

A previously defined trading box

Purpose:

Extremes cap expectations.

Exit Use

Objective exit if pre-defined

Liquidity exit if reaction forms

Structural exit if break-and-fail occurs

66.10 Structural Invalidation Level
Definition

A price level where:

The original trade premise is broken

Structure no longer supports direction

Purpose:

Premise failure ends participation.

Exit Use

Always a full exit

Classified as Structural Exit

No partial exits permitted here.

66.11 Exit Trigger Conditions

An exit may only occur if one or more of the following resolve:

Structural break against position

Absorption detected at exit zone

Momentum failure after expansion

Liquidity sweep completion

Invalidation level breached

Triggers resolve inside or immediately adjacent to exit zones.

66.12 Partial vs Full Exit Rules
Partial Exit Allowed When:

Position remains structurally valid

Risk has been reduced

Opportunity for continuation exists

Full Exit Required When:

Trade premise invalidates

Risk constraints are violated

Structural exit triggers

Failure exit triggers

Partial exits must never increase risk.

66.13 Exit Priority Hierarchy

When multiple exits are possible, priority is:

Failure Exit

Structural Exit

Risk Exit

Constraint Exit

Liquidity Exit

Objective Exit

Higher priority always overrides lower.

66.14 Exit Is Final Per State

Once a full exit is executed:

Position lifecycle terminates

No re-entry allowed without new lifecycle

Previous context is archived

No “flip” exits allowed.

66.15 Exit Is Optional Unless Forced

Being at an exit zone does not mandate exit unless:

Trigger resolves

Constraint requires it

Premise fails

Patience is a valid state.

66.16 Summary

This section enforces:

Explicit exit classification

Clear separation of zone vs trigger

Partial exits as controlled reductions

Full exits as premise termination

Hierarchical, conflict-free resolution

The system exits because it must — not because it is afraid.


SECTION 67 — PARTIAL EXIT GOVERNANCE & SCALING LOGIC

Status: Binding
Layer: Position Management
Scope: Per-position, per-symbol
Purpose: Define when partial exits are allowed, how they are sized, and how they interact with risk, structure, and continuation.

67.1 Core Principle

Partial exits reduce exposure — they must never add uncertainty.

A partial exit exists to:

Reduce risk

Lock realized profit

Preserve optionality

It must never:

Obscure trade intent

Delay an invalidation

Replace a full exit when one is required

67.2 Partial Exit Is a Permissioned Action

A partial exit is not automatic.

It is permitted only if all conditions below are true:

Position premise remains valid

Structural direction remains intact

Risk after partial exit is ≤ risk before

Exit zone has resolved with a valid trigger

No higher-priority full-exit condition exists

If any condition fails → partial exit is forbidden.

67.3 Canonical Partial Exit Reasons

Partial exits may occur only for the following reasons:

Liquidity Interaction

Exhaustion / Deceleration

Objective Milestone

Risk Rebalancing

Exposure Constraint Enforcement

No other justification is valid.

67.4 Liquidity-Based Partial Exit
Conditions

Price enters a known opposing liquidity zone

No structural invalidation occurs

Absorption or pause is detected, not reversal

Intent

Reduce exposure ahead of possible reaction without exiting a valid move.

Constraints

Must not exceed predefined partial size limit

Must not remove entire position

Must preserve continuation capacity

67.5 Exhaustion-Based Partial Exit
Conditions

Expansion decelerates after high velocity

Range compression or wick-dominant candles appear

Momentum weakens without reversal

Intent

Lock gains when speed suggests diminishing marginal return.

Constraints

Cannot occur if structure is breaking

Cannot be repeated consecutively without new expansion

67.6 Objective-Based Partial Exit
Conditions

Predefined objective level is reached

Objective is not structural invalidation

Position remains structurally sound

Intent

Convert plan into realized profit.

Constraints

Objective must be defined at entry

No retroactive objectives allowed

67.7 Risk Rebalancing Partial Exit
Conditions

Unrealized profit materially exceeds initial risk

Reducing size materially lowers liquidation risk

No invalidation present

Intent

Improve risk asymmetry while maintaining exposure.

Constraints

Must be calculated, not discretionary

Must not distort original thesis

67.8 Exposure Constraint Partial Exit
Conditions

Portfolio-level or symbol-level exposure limit is breached

Multiple positions increase correlated risk

System constraint demands reduction

Intent

Enforce global risk discipline.

Constraints

Priority overrides liquidity and objective exits

Cannot override structural or failure exits

67.9 Partial Exit Size Governance

Partial exit size must be:

Explicitly bounded

Deterministic

Non-escalating

Examples (non-prescriptive):

Fixed percentage of position

Risk-normalized reduction

Exposure-threshold-based reduction

Random sizing is forbidden.

67.10 Maximum Partial Exit Count

A position may perform multiple partial exits, but only if:

Each is justified by a new, distinct condition

Total partial exits do not fragment intent

Remaining size remains meaningful

Excessive fragmentation is prohibited.

67.11 Partial Exit Does Not Reset Lifecycle

Partial exits:

Do NOT reset position lifecycle

Do NOT invalidate original entry logic

Do NOT permit re-entry logic

They only adjust size.

67.12 Partial Exit vs Stop Adjustment

Partial exit and stop movement are independent.

However:

Stop tightening after partial exit is allowed

Stop loosening is forbidden

Stop changes must obey risk invariants

67.13 Partial Exit Prohibitions

Partial exits are explicitly forbidden when:

Structural invalidation occurs

Failure exit is triggered

Risk limits are breached

Position is already at minimum size

Exit is being used to “delay” a loss

67.14 Escalation Rule

If partial exits fail to restore favorable conditions:

Next eligible exit must be full

Repeated partials may not postpone invalidation

67.15 Summary

This section enforces:

Partial exits as controlled reductions

Clear justification requirements

Separation between caution and termination

Non-fragmented position intent

Absolute priority of structure and risk

Partial exits manage exposure.
Full exits end belief.

SECTION 68 — STOP GOVERNANCE & STOP EVOLUTION RULES

Status: Binding
Layer: Position Management
Scope: Per-position, per-symbol
Purpose: Define how stops are set, when they may move, and when they must terminate the position.

68.1 Core Principle

The stop defines truth.

A stop represents:

Structural invalidation

Risk boundary

Premise failure

It is not:

A suggestion

A comfort mechanism

A dynamic prediction tool

68.2 Mandatory Stop at Entry

Every position must have a stop defined at entry.

A position without a stop is invalid and must not exist.

68.3 Stop Placement Authority

Stop placement must be based on structure, not PnL.

Valid bases:

Structural high / low

Range boundary

Liquidity sweep invalidation

Thesis-defining level

Invalid bases:

Fixed tick distance

Random percentage

Emotional tolerance

“Room to breathe”

68.4 Stop Is Singular

Each position has one active stop at any time.

Multiple concurrent stops are forbidden.

68.5 Stop Movement Is Permissioned

Stops may move only under explicitly allowed conditions.

If a condition is not listed below, stop movement is forbidden.

68.6 Allowed Stop Movements
1. Risk Reduction

Move stop closer to entry or into profit

Must reduce maximum loss

Must not increase risk

2. Structure Confirmation

New structure forms that supersedes original invalidation

Stop may be re-anchored to stronger structure

3. Partial Exit Synchronization

After partial exit, stop may be tightened

Must reflect reduced exposure

68.7 Forbidden Stop Movements

Stops must never be:

Moved further away

Loosened to avoid exit

Adjusted because price “almost turned”

Modified to justify staying in trade

Tied to hope, time, or external belief

Any loosening is a violation.

68.8 Break-Even Is Not Mandatory

Moving stop to break-even is optional, not required.

It is permitted only if:

Structure supports it

It does not contradict trade intent

It does not increase stop-out probability unfairly

68.9 Stop vs Partial Exit Priority

If both are triggered:

Stop has priority

Partial exits must not override invalidation

If stop is hit → position is terminated immediately.

68.10 Stop Hit = Full Exit

When stop is hit:

Position is closed in full

No partial logic applies

No re-entry is permitted under same thesis

68.11 Stop Execution Is Final

Stops are:

Non-negotiable

Non-delayable

Non-reversible

There is no “soft stop”.

68.12 Stop & Liquidity Interaction

A stop may intentionally sit:

Beyond liquidity

Beyond equal highs/lows

Beyond sweep zones

But once hit, the premise is invalid regardless of intent.

68.13 Stop Evolution Frequency

Stops may not be adjusted excessively.

Guideline:

One logical adjustment per structural phase

Continuous micro-adjustment is forbidden

68.14 Stop & Time

Stops must never move because of time elapsed.

Time-based stops are forbidden.

68.15 Stop Visibility

The system must always know:

Current stop price

Reason for stop placement

Last modification reason

Hidden or implicit stops are forbidden.

68.16 Stop Conflict Resolution

If multiple justifications suggest different stop locations:

Choose the most conservative

Risk reduction > continuation preference

68.17 Stop Under System Stress

During:

Volatility spikes

Liquidity events

Execution stress

Stops must still execute without reinterpretation.

68.18 Stop & Re-entry Separation

After a stop:

Original narrative is invalid

Re-entry requires a new thesis

Stops may not be reused conceptually

68.19 Summary

This section enforces:

Stops as truth boundaries

One stop per position

Only tightening, never loosening

Structural justification only

Absolute authority of invalidation

If the stop is hit, the story is over.

SECTION 69 — ENTRY VALIDATION & THESIS LOCKING

Status: Binding
Layer: Trade Initiation
Scope: Per-entry, per-symbol
Purpose: Define when an entry is allowed, how it is validated, and how the trade thesis becomes immutable once entered.

69.1 Core Principle

An entry is a commitment to a thesis.

Once entered:

The thesis is locked

Interpretation stops

Only invalidation or execution remains

69.2 Entry Requires a Thesis

No position may be opened without an explicit thesis.

A thesis must define:

What condition triggered the entry

What invalidates the idea (stop)

What confirms continuation

What outcomes are acceptable (partial, full exit)

Implicit or assumed theses are forbidden.

69.3 Thesis Is Conditional, Not Predictive

A valid thesis is always of the form:

If X occurs, then Y is permitted.

Forbidden forms:

“Price will go up”

“This looks strong”

“Market should reverse here”

69.4 Entry Preconditions

An entry is permitted only if all of the following are true:

Observation layer is valid (not FAILED)

No existing position violates exposure constraints

Symbol is not already in conflicting position

Entry condition is explicitly satisfied

Stop location is defined and valid

Position sizing respects risk constraints

Failure of any precondition blocks entry.

69.5 Entry Is Atomic

Entry must occur as a single atomic action:

Position opened

Stop set

Size fixed

Thesis locked

Staggered or speculative entries are forbidden.

69.6 One Thesis per Position

Each position corresponds to exactly one thesis.

Multiple overlapping rationales are forbidden.

If multiple narratives exist → no trade.

69.7 Thesis Locking

Once a position is opened:

Thesis cannot change

Rationale cannot be edited

Intent cannot be reinterpreted

Only execution outcomes may change (partial exit, stop hit).

69.8 Entry Confirmation vs Entry Trigger

Entry confirmation must be objective and binary.

Valid confirmation examples:

Structure break

Level acceptance

Liquidity sweep completion

Rejection + continuation

Invalid confirmations:

“Feels right”

“Looks strong”

“Momentum seems good”

69.9 Entry Timing Discipline

Late entries are forbidden.

If the condition occurred and price moved materially away:

Entry is invalid

No chasing allowed

69.10 No Retroactive Justification

Entries must not be justified after execution.

If the thesis cannot be articulated before entry:

The trade is invalid

69.11 Entry vs Re-entry

Re-entry is not an extension of the original thesis.

Re-entry requires:

New structure

New condition

New stop

New thesis

69.12 Entry & Liquidity Events

Entries may be triggered by:

Liquidity sweeps

Stop hunts

Liquidation cascades

But only when:

Sweep is complete

Reaction confirms intent

Entry is reactive, not anticipatory

69.13 Entry & Multi-Timeframe Context

Higher timeframe context may constrain entries but must not force them.

Lower timeframe confirmation is mandatory.

HTF bias without LTF confirmation forbids entry.

69.14 Entry Quantity Discipline

Entry size must be fixed at execution.

Scaling into entries is forbidden unless explicitly defined in thesis.

69.15 Entry Failure Handling

If entry condition invalidates immediately:

Stop must execute

No hesitation

No thesis salvage

69.16 Entry & Opposing Signals

If an opposing condition triggers before entry:

Original thesis is void

Entry is canceled

No “stronger signal overrides”.

69.17 Entry Memory Prohibition

Past missed entries must not influence new decisions.

“There was a signal earlier” is irrelevant.

69.18 Entry Transparency

The system must be able to answer:

Why was this trade entered?

What condition triggered it?

Where is it invalidated?

If not answerable → entry forbidden.

69.19 Summary

This section enforces:

Explicit, conditional theses

Atomic entry execution

Immutable rationale post-entry

Objective confirmation only

Zero retroactive justification

An entry is not a guess.
It is a locked commitment to a condition.

SECTION 70 — PARTIAL EXITS & THESIS DEGRADATION

Status: Binding
Layer: Position Management
Scope: In-position behavior
Purpose: Define when partial exits are permitted, how they affect the thesis, and when they force full exit.

70.1 Core Principle

A partial exit reduces exposure, not conviction.

Partial exits are permitted only when they are:

Predefined

Conditional

Non-reactive

Improvisational partial exits are forbidden.

70.2 Partial Exit Is a First-Class Action

A partial exit is not:

A panic response

A discretionary adjustment

A reaction to discomfort

It is a planned execution branch of the original thesis.

70.3 Partial Exit Must Be Defined at Entry

A position may only perform partial exits if the entry thesis explicitly defines:

Conditions that trigger a partial exit

Fraction(s) of position to be reduced

Consequences for the remaining position

If not defined at entry → partial exits are forbidden.

70.4 Valid Partial Exit Triggers

Permitted triggers include:

Arrival at predefined liquidity zone

Historical liquidation region

Known stop-hunt region

Prior high-velocity rejection area

Predefined opposing imbalance

Scheduled risk events (if allowed)

Triggers must be structural, not emotional.

70.5 Liquidity-Based Partial Exits

When price approaches a historically significant liquidity region:

Two paths are valid:

Reduce exposure (partial exit)

Invalidate thesis (full exit)

The choice must be defined before entry.

70.6 Partial Exit vs Full Exit Decision Rule

If the liquidity region:

Historically caused continuation → partial exit allowed

Historically caused reversal → full exit required

Ambiguity defaults to full exit.

70.7 Partial Exit Does NOT Reset the Thesis

After a partial exit:

The original thesis remains active

The stop logic remains intact

The remaining position is not a new trade

If the thesis changes → full exit required.

70.8 Partial Exit & Stop Adjustment

Stop movement after partial exit is allowed only if:

Explicitly defined in thesis

Rule-based (e.g., to breakeven after X)

Ad hoc stop tightening is forbidden.

70.9 Partial Exit Frequency Limits

Multiple partial exits are permitted only if:

Explicitly enumerated

Non-overlapping

Ordered

Unlimited scaling out is forbidden.

70.10 Partial Exit & Opposing Signals

If an opposing signal appears:

Partial exit is NOT a substitute for invalidation

Thesis must be evaluated

If opposing signal violates thesis → full exit.

70.11 Partial Exit Under Volatility Expansion

During sudden volatility expansion:

Partial exits must NOT be triggered reactively

Only pre-authorized triggers apply

Volatility alone is not a trigger.

70.12 Partial Exit & Liquidation Cascades

When price moves favorably but enters:

Prior liquidation cascade region

High historical forced-exit density

Partial exit is permitted only if:

Cascade historically resolves continuation

Absorption evidence exists

Otherwise → full exit.

70.13 Partial Exit Does Not Create Optionality

Partial exit does not allow:

Reinterpretation of thesis

“Let’s see what happens”

New narratives

Remaining position still obeys original logic.

70.14 Thesis Degradation Definition

A thesis is considered degraded when:

Partial exit removes >50% of position

Or continuation conditions weaken materially

Degraded thesis must be explicitly classified.

70.15 Degraded Thesis Rules

When thesis is degraded:

No new risk may be added

No size increases allowed

Stops may only tighten, never loosen

70.16 Partial Exit Failure Handling

If partial exit condition triggers and:

Execution fails

Liquidity is insufficient

The system must default to full exit.

70.17 Partial Exit Transparency

The system must be able to answer:

Why was exposure reduced?

What condition triggered it?

What remains true about the thesis?

If not answerable → partial exit forbidden.

70.18 No Partial Exit as Emotional Relief

Partial exits must not be used to:

Reduce anxiety

Lock profits prematurely

Avoid stop execution

Emotional mitigation is not a valid trigger.

70.19 Summary

This section enforces:

Partial exits as predefined logic

Clear distinction between reduction and invalidation

Protection against discretionary scaling

Explicit handling of liquidity-based uncertainty

Formal thesis degradation handling

Partial exits manage risk.
They do not manage doubt.

SECTION 71 — FULL EXIT CONDITIONS & THESIS INVALIDATION

Status: Binding
Layer: Position Management
Scope: In-position termination
Purpose: Define when a position must be fully closed and the thesis declared invalid.

71.1 Core Principle

A full exit is a truth assertion: the thesis is no longer valid.

Full exits are not losses or failures.
They are logical conclusions.

71.2 Full Exit Supersedes All Other Actions

When a full exit condition is met:

Partial exits are forbidden

Risk reduction is irrelevant

Position must be closed entirely

No further discretion is allowed.

71.3 Full Exit Must Be Deterministic

Every full exit must be triggered by:

A predefined invariant violation

A structural contradiction

A risk boundary breach

Full exits must never be discretionary.

71.4 Thesis Invalidation Definition

A thesis is invalidated when any core assumption is proven false by price behavior.

If the “if” in if-this-then-that fails → exit.

71.5 Structural Invalidation Triggers

Mandatory full exit triggers include:

Break of defining structure level (high/low)

Failure to hold entry zone

Loss of required market regime

Violation of directional bias boundary

Entry zone acceptance failure

71.6 Opposing Narrative Confirmation

If price confirms the opposite narrative, full exit is mandatory.

Examples:

Bullish thesis + bearish structure confirmation

Liquidity sweep fails and reverses

Absorption flips direction

No “wait and see” allowed.

71.7 Stop Loss Is a Full Exit

Stop loss execution is:

A valid full exit

A deterministic outcome

Not a failure

Stops are non-negotiable.

71.8 Time-Based Invalidation

If a thesis requires resolution within a defined time window and:

Resolution does not occur

Structure degrades

Full exit is mandatory.

Time decay is thesis decay.

71.9 Liquidity-Based Invalidation

Full exit required when price enters:

Prior stop-hunt region and

Shows acceptance instead of rejection

Acceptance where rejection was expected invalidates the thesis.

71.10 Liquidation Cascade Failure

If a liquidation cascade:

Does not produce expected continuation

Shows immediate absorption against the thesis

Full exit is mandatory.

71.11 Absorption Against Position

Ongoing absorption opposing the position that:

Persists across multiple attempts

Prevents expected continuation

Invalidates the thesis.

71.12 Range Expansion Against Thesis

If price expands range against the thesis:

With velocity

Without meaningful rejection

Full exit is mandatory.

71.13 Partial Exit Does Not Prevent Full Exit

A partial exit:

Does not protect the remaining position

Does not delay invalidation

Does not soften full exit conditions

Full exit overrides all.

71.14 No Reinterpretation After Invalidation

Once invalidated:

No re-framing

No “it might still work”

No thesis mutation

Exit means exit.

71.15 Full Exit Execution Priority

Full exits must be:

Immediate

Atomic

Non-negotiable

Execution quality > price perfection.

71.16 Post-Exit Cooldown

After a full exit:

Re-entry on same symbol is forbidden until new thesis is formed

Cooldown duration must be predefined

No revenge trading.

71.17 Full Exit Logging (Internal)

Internally, the system must record:

Invalidation reason

Triggering condition

Timestamp

This is not external interpretation — it is internal accountability.

71.18 No “Soft” Invalidations

The system must not support:

“Weak invalidation”

“Partial failure”

“Degraded but still valid”

Invalidated = closed.

71.19 Summary

This section enforces:

Clear thesis invalidation logic

Structural over emotional exits

Deterministic termination

Immunity to hope-based behavior

Positions do not die slowly.
They end decisively.

SECTION 72 — RE-ENTRY RULES & THESIS RECONSTRUCTION

Status: Binding
Layer: Position Management / Strategy Control
Scope: Post-exit behavior
Purpose: Define when and how a new position may be formed after a full exit.

72.1 Core Principle

Re-entry is not continuation.
Re-entry requires a new thesis.

A closed position is dead.
No logic may treat it as dormant or paused.

72.2 Re-Entry Is Forbidden by Default

After a full exit:

Re-entry is disallowed

Action requires explicit justification

Silence is the correct default.

72.3 Re-Entry Requires Thesis Reconstruction

A valid re-entry requires:

A newly constructed narrative

New structural assumptions

New invalidation conditions

Re-using the previous thesis is prohibited.

72.4 Mandatory Cooldown Enforcement

After a full exit:

A cooldown period must elapse

Duration must be predefined

Cooldown cannot be shortened dynamically

Cooldown exists to prevent emotional or reflexive trades.

72.5 Structural Reset Requirement

Re-entry requires at least one of the following:

New structure formation

New range definition

Clear regime change

Liquidity event that resets context

Without reset, no re-entry.

72.6 Prohibited Re-Entry Motivations

Re-entry must not be based on:

Desire to “get it back”

Minor price retracement

Improved entry price alone

Reduced position size

“It looks better now”

Motivation must be structural, not emotional.

72.7 Opposite Direction Re-Entry

Re-entering in the opposite direction is allowed only if:

Opposing narrative is fully formed

Previous invalidation supports the new thesis

Structural confirmation exists

Opposite direction ≠ hedge.
It is a new trade.

72.8 Liquidity-Driven Re-Entry

Re-entry may be allowed if:

A prior invalidation zone becomes a valid entry zone

Liquidity sweep completes and reverses

Acceptance/rejection dynamics flip

This requires explicit confirmation.

72.9 Time-Based Re-Entry Eligibility

If sufficient time passes:

Context may decay

Old invalidations may become irrelevant

Time alone does not justify re-entry — it only enables reassessment.

72.10 Re-Entry Must Obey All Position Invariants

Re-entered positions must obey:

One position per symbol

Risk limits

Exposure constraints

Leverage rules

Lifecycle states

No exceptions.

72.11 Re-Entry Is a New Lifecycle

A re-entry:

Starts at FLAT

Transitions through full lifecycle

Has independent management rules

There is no “continuation” state.

72.12 Re-Entry Cannot Override Invalidations

If an invalidation condition:

Still holds

Has not been structurally resolved

Re-entry is forbidden.

72.13 Confirmation Required Before Re-Entry

Re-entry requires at least one:

Break of structure

Acceptance/rejection confirmation

Liquidity resolution

Volatility regime shift

Hope is not confirmation.

72.14 No Rapid Re-Entry Loops

The system must prevent:

Exit → immediate re-entry → exit loops

Micro-flip behavior

Noise-driven churn

Re-entry frequency must be constrained.

72.15 Re-Entry Logging (Internal)

Internally record:

Prior exit reason

New thesis identifier

Structural justification

Cooldown satisfaction

This is accountability, not interpretation.

72.16 Re-Entry Is Optional

The system is not obligated to re-enter:

Missing a move is acceptable

Capital preservation is primary

No trade is better than a bad trade.

72.17 Summary

This section enforces:

Clean separation between trades

Structural justification for re-entry

Protection against revenge trading

Discipline after invalidation

A new trade must be earned.
Price alone is not enough.

SECTION 73 — POSITION SCALING, ADD-ONS, AND REDUCTIONS

Status: Binding
Layer: Position Management / Risk Control
Scope: Active positions only
Purpose: Define when and how position size may change after entry.

73.1 Core Principle

Scaling changes risk.
Risk changes require justification.

Position size is not cosmetic.
Every adjustment is a decision.

73.2 Default Rule: No Scaling

By default:

Position size is fixed at entry

No add-ons

No reductions

Scaling is opt-in, not assumed.

73.3 Separation of Concepts

Scaling actions are strictly separated:

Add-On: Increasing exposure

Reduction: Decreasing exposure

Exit: Closing exposure

They are governed by different rules.

73.4 Add-Ons Are More Dangerous Than Entries

Adding to a position:

Increases exposure

Increases liquidation risk

Reduces margin for error

Therefore, add-ons have stricter requirements than initial entries.

73.5 Add-On Preconditions (ALL REQUIRED)

An add-on is allowed only if:

Original thesis remains valid

No invalidation has occurred

Position is not under stress

Risk after add-on remains within limits

New structural information exists

If any condition fails → add-on forbidden.

73.6 Prohibited Add-On Motivations

Add-ons must not be based on:

“It’s going my way”

Unrealized profit

Fear of missing out

Emotional confidence

Reduced entry price

Profit ≠ permission.

73.7 Structural Justification for Add-Ons

Valid add-on justifications include:

Break of structure in trade direction

Acceptance above/below key level

Liquidity sweep that confirms thesis

Regime shift that strengthens bias

Add-ons require new information, not old conviction.

73.8 Risk Recalculation Is Mandatory

Before any add-on:

Total position risk must be recomputed

Worst-case loss must be reassessed

Liquidation buffer must be revalidated

If recalculation fails → add-on rejected.

73.9 Add-Ons Must Be Explicitly Sized

Rules:

Add-on size must be predefined

No “fill the rest” logic

No dynamic intuition sizing

Each add-on is a discrete decision.

73.10 Maximum Number of Add-Ons

A hard cap must exist on:

Number of add-ons per position

Total exposure per symbol

Infinite scaling is prohibited.

73.11 Add-Ons Do Not Reset Stops by Default

Unless explicitly allowed:

Original stop remains authoritative

Stop cannot be loosened to accommodate add-on

Scaling must adapt to risk — not rewrite it.

73.12 Reductions Are Defensive, Not Failure

Reducing a position:

Is risk control

Is not an admission of error

Is allowed more freely than add-ons

Defense is always allowed.

73.13 Valid Reduction Triggers

Reductions may occur due to:

Approaching liquidity zones

Volatility expansion

Adverse absorption

Exposure imbalance

Risk concentration concerns

Reductions require less justification than add-ons.

73.14 Partial Exits vs Reductions

Partial exit: Profit-taking logic

Reduction: Risk mitigation logic

They may overlap, but intent must be clear.

73.15 Mandatory Reduction Scenarios

Reductions are required if:

Liquidation buffer deteriorates

Correlated exposure increases

Market regime becomes hostile

Position becomes oversized due to price movement

Ignoring required reductions is a violation.

73.16 Reductions Must Preserve Thesis or End It

After reduction:

Either thesis remains valid

Or full exit must occur

A “half-alive” thesis is not allowed.

73.17 No Scaling Against the Position

Adding to a losing position is forbidden unless:

Explicitly designed as a separate strategy

Fully risk-contained

Governed by different invariants

Default: no averaging down.

73.18 Scaling Cannot Override Exit Rules

Scaling actions:

Cannot delay exits

Cannot bypass invalidations

Cannot prevent mandatory exits

Exit rules dominate scaling rules.

73.19 Scaling Is Part of Lifecycle

Scaling actions are valid only in:

OPEN

ACTIVE

Scaling is forbidden in:

INVALIDATED

EXIT_PENDING

FLAT

73.20 Scaling Actions Must Be Finite

The system must prevent:

Infinite micro-adjustments

Noise-driven resizing

Thrashing behavior

Stability > optimization.

73.21 Internal Accountability (Non-Interpretive)

Internally record:

Scaling reason

Structural trigger

Risk before and after

Updated exposure

This is bookkeeping, not justification.

73.22 Summary

This section enforces:

Discipline in increasing exposure

Freedom to reduce risk

Structural justification over emotion

Hard limits on scaling behavior

Adding is a privilege.
Reducing is a responsibility.
Exiting is always allowed.

SECTION 74 — STOP-LOSS, INVALIDATION, AND FAILURE MODES

Status: Binding
Layer: Risk / Position Integrity
Scope: All positions
Purpose: Define how and when a position is proven wrong and must be terminated.

74.1 Core Principle

A stop-loss is not a suggestion.
It is a proof boundary.

When crossed, the position is wrong — not unlucky.

74.2 Stop-Loss vs Invalidation

These are related but distinct:

Stop-Loss: Mechanical risk boundary

Invalidation: Logical proof the thesis failed

A position may be invalidated before stop is hit.

74.3 Every Position Must Have an Invalidation Rule

No position may exist without:

A clearly defined invalidation condition

A non-ambiguous failure criterion

“If unclear, stay in” is forbidden.

74.4 Invalidation Takes Precedence Over Price

If invalidation occurs:

Exit immediately

Ignore unrealized PnL

Ignore proximity to stop

Logic beats price.

74.5 Stop-Loss Must Be Known at Entry

At entry time:

Stop location must be defined

Risk must be computable

Liquidation buffer must exist

Unknown stop = forbidden entry.

74.6 Stop-Loss Is a Worst-Case Guard

The stop represents:

Maximum acceptable loss

Failure containment

Capital preservation

It is not an optimization tool.

74.7 Stop Placement Must Be Structural

Valid stop locations include:

Beyond invalidation level

Beyond structural high/low

Beyond liquidity region that negates thesis

Stops must align with why the trade exists.

74.8 Arbitrary Stops Are Forbidden

Forbidden stop logic:

Fixed pip distance

“Feels safe”

Volatility guessing without structure

Round numbers without justification

Structure determines stops.

74.9 Stops Must Not Be Moved to Increase Risk

After entry:

Stop may only move toward safety

Never farther from entry

Never to “give it room”

Risk expansion is prohibited.

74.10 Stop Adjustments Are Allowed Only for Risk Reduction

Permitted stop movements:

Break-even shifts

Locking profits

Reducing exposure during regime change

Stop movement must reduce worst-case loss.

74.11 Stop Removal Is Forbidden

A stop may never be:

Removed

Disabled

Temporarily ignored

“No stop” equals system violation.

74.12 Hard Failure Conditions

Immediate full exit is required if:

Invalidation condition triggers

Stop-loss is breached

Liquidation threshold approached

Margin integrity compromised

No negotiation.

74.13 Liquidation Is Not an Acceptable Outcome

Liquidation implies:

Risk miscalculation

Leverage failure

System breach

Liquidation is always a violation.

74.14 Stop-Loss vs Partial Exits

Partial exits:

Do not replace stop-loss

Do not nullify invalidation

Cannot delay mandatory exit

Stop remains authoritative.

74.15 Gap Risk and Slippage

If price gaps through stop:

Exit at first available price

Record slippage internally

Do not attempt recovery logic

Reality overrides design.

74.16 Failure Modes Must Be Explicit

Each position must enumerate:

Price-based failure

Structure-based failure

Liquidity-based failure

Risk-based failure

Unknown failure modes are forbidden.

74.17 Stop-Loss vs Time

Time alone:

Is not a stop

Is not invalidation

Time-based exits require explicit mandate.

74.18 Re-Entry After Stop

After stop-loss:

Re-entry is not automatic

New thesis required

New risk calculation required

Stopping out resets the state.

74.19 Stop Discipline Overrides Narrative

Even if narrative still “feels right”:

Stop breach ends the position

No emotional override

No revenge logic

Discipline > conviction.

74.20 Failure Must Be Final

Once failed:

Position becomes FLAT

No partial continuation

No “let’s see”

Failure closes the book.

74.21 Recording Failure (Internal Only)

Internally record:

Failure reason

Stop or invalidation trigger

Risk outcome

This is learning, not justification.

74.22 Summary

This section enforces:

Stops as proof boundaries

Invalidation as logic, not loss

Zero tolerance for liquidation

Absolute exit discipline

A stopped trade is a completed trade.
A violated stop is a system error.
Failure ends the position — always.

SECTION 75 — POSITION ENTRY QUALIFICATION & FILTERING

Status: Binding
Layer: Entry Governance
Scope: All new positions
Purpose: Ensure positions are opened only when minimum structural, risk, and contextual conditions are satisfied.

75.1 Core Principle

A position is not earned by opportunity.
It is earned by qualification.

If conditions are not met, the system must remain flat.

75.2 Entry Is a Privilege, Not a Default

The system defaults to:

No position

No exposure

No action

Action requires justification.

75.3 Mandatory Entry Qualification Layers

A position may be opened only if all layers pass:

Structural qualification

Context qualification

Risk qualification

Exposure qualification

Conflict qualification

Failure at any layer blocks entry.

75.4 Structural Qualification (Price Logic)

Structural conditions may include (non-exhaustive):

Break of structure

Reclaim or loss of key level

Acceptance/rejection at zone

Resolution of compression

Completion of impulse–pullback sequence

If structure is ambiguous, entry is forbidden.

75.5 Context Qualification (Market Memory)

Context must support the trade:

Relevant liquidity in memory

Prior liquidation or stop-hunt zones

Historical reaction zones

Velocity regimes consistent with thesis

Context must agree, not merely allow.

75.6 Timeframe Consistency Requirement

The entry timeframe must not contradict:

Higher-timeframe bias (if defined)

Active regime constraints

Current volatility regime

Lower timeframe entries may refine — not negate — context.

75.7 Entry Zone Definition Is Mandatory

Every entry must define:

Entry zone (range, not point)

Invalid entry region

No-trade region

Entering outside the defined zone is prohibited.

75.8 No-Chase Rule

Forbidden entries include:

Late impulse chasing

Entries far from invalidation logic

Entries after extended velocity bursts

FOMO-driven fills

Price must come to the level — not vice versa.

75.9 Risk Qualification Is Absolute

Before entry, the system must know:

Stop-loss location

Risk per unit

Total risk percentage

Worst-case loss

If any is unknown → no entry.

75.10 Risk-to-Structure Compatibility

Risk must make sense structurally:

Stop must sit beyond invalidation

Position size must respect stop distance

Leverage must not compress safety margin

If structure demands excessive risk, skip the trade.

75.11 Exposure Qualification

Before entry, system must verify:

Symbol exposure limits

Directional exposure limits

Correlated asset exposure

Aggregate leverage limits

If exposure ceiling breached → entry blocked.

75.12 One-Position-Per-Symbol Rule

Unless explicitly overridden by mandate:

Only one position per symbol

No stacking

No pyramiding by default

Clarity beats complexity.

75.13 Conflict Qualification

Entry is forbidden if:

Opposing thesis already active

Pending exit conditions exist

Partial exit logic conflicts with new entry

System is in drawdown lock

Conflicts must resolve before entry.

75.14 Liquidity Proximity Filter

Entry must consider proximity to:

Known liquidity pools

Stop-hunt zones

Prior liquidation cascades

Entering directly into opposing liquidity is forbidden unless explicitly intended.

75.15 Velocity Filter

Entry must respect velocity state:

Extremely high velocity requires confirmation

Low velocity requires patience

Sudden acceleration requires caution

Velocity mismatch blocks entry.

75.16 News & Event Filter (If Enabled)

If high-impact event is imminent:

Entry may be blocked

Or risk must be reduced

Or mandate must explicitly allow it

Silence is preferred to guessing.

75.17 No “Almost Qualified” Trades

Partial qualification is failure.

Examples of forbidden logic:

“Everything lines up except…”

“It’s close enough”

“I’ll manage it manually”

Binary rules only.

75.18 Entry Confirmation Must Be Observable

Entry triggers must be:

Price-based

Event-based

Objectively detectable

Subjective confirmation is forbidden.

75.19 Entry Timing vs Entry Reason

Timing refines entry.
Reason authorizes entry.

Good timing without reason is forbidden.

75.20 Entry Must Be Reversible

The system must be able to say:

“If X happens, this entry was wrong.”

If not, entry is invalid.

75.21 Entry Does Not Guarantee Continuation

Entry implies:

Permission to participate

Not entitlement to profit

Management logic takes over immediately.

75.22 Entry Is a Discrete State Transition

On entry:

State moves from FLAT → OPEN

Risk is live

Rules tighten, not loosen

75.23 Entry Failure Is Neutral

A blocked entry is:

Not a missed trade

Not an error

Not a loss

It is discipline functioning correctly.

75.24 Summary

This section enforces:

Multi-layer qualification

Structural and contextual alignment

Absolute risk clarity

Exposure and conflict discipline

The best trade is the one you are allowed to take.
Everything else is noise.

SECTION 76 — POSITION MANAGEMENT & ACTIVE RISK CONTROL

Status: Binding
Layer: Live Position Governance
Scope: All open positions
Purpose: Control risk dynamically after entry without violating invariants or introducing interpretation.

76.1 Core Principle

Once a position is open, risk dominates logic.

The system’s first obligation is survival, not optimization.

76.2 Management Begins Immediately at Entry

The moment a position transitions to OPEN:

Risk is live

Capital is at stake

No further justification is required to act defensively

There is no “grace period.”

76.3 Position Management Is Not Prediction

Management actions are:

Reactive

Rule-based

Conditional

They must never depend on:

Expectations

Confidence

Belief in continuation

76.4 Immutable Entry Invariants

The following must never change after entry:

Entry thesis (directional intent)

Maximum allowed loss

Initial invalidation logic

Exposure ceilings

If any are violated, the position must exit.

76.5 Stop-Loss Is Mandatory and Sacred

Every open position must have:

A defined stop-loss

A known worst-case loss

A mechanically enforceable exit

No stop-loss = no position.

76.6 Stop-Loss Movement Rules

Stop-loss may be moved only if:

Risk is reduced (never increased)

New stop is structurally justified

Move does not invalidate original logic

Forbidden:

Widening stops

“Giving it room”

Emotional adjustments

76.7 Break-Even Is a Risk Tool, Not a Goal

Moving to break-even is allowed when:

Initial risk has been paid for by structure

Market has confirmed participation

Doing so does not expose to noise

Break-even is protection, not profit-taking.

76.8 Partial Exits Are Risk Instruments

Partial exits exist to:

Reduce exposure

Lock in capital

Lower liquidation risk

They are not a signal of trade success.

76.9 Partial Exit Eligibility

Partial exits may occur when:

Price enters known opposing liquidity

Prior liquidation or stop-hunt zones are approached

Velocity changes materially

Absorption is detected

Risk asymmetry degrades

Partial exits are optional, not mandatory.

76.10 Partial vs Full Exit Distinction

The system must decide:

Partial exit → thesis intact, risk elevated

Full exit → thesis broken or invalidated

Liquidity presence alone does not force a full exit.

76.11 Liquidity-Based Management

When price approaches known liquidity:

Exposure may be reduced

Stops may be tightened

Full exit may occur if continuation probability collapses

Context determines response, not the liquidity label itself.

76.12 Velocity-Based Management

High velocity implies:

Increased slippage risk

Reduced reaction time

Elevated liquidation risk

Management may include:

Partial exits

Hard stop enforcement

Emergency flattening

76.13 Absorption-Aware Management

If price stalls while:

Liquidations continue

Large orders absorb flow

Progress halts

Then:

Risk must be reduced

Continuation assumptions are invalid

Absorption without movement is a warning.

76.14 Leverage Adjustment Rules

Leverage is not static after entry.

Permitted actions:

Reduce leverage as risk rises

Reduce size as margin safety decreases

Forbidden:

Increasing leverage to “optimize”

Doubling down under pressure

76.15 Liquidation Distance Monitoring

The system must continuously monitor:

Distance to liquidation

Margin utilization

Worst-case slippage scenarios

If liquidation risk rises beyond tolerance → reduce or exit.

76.16 Time-in-Trade Awareness

Extended time without progress implies:

Opportunity cost

Increased uncertainty

Potential structural failure

Time alone does not force exit, but it degrades confidence.

76.17 No “Hope Management”

Forbidden behaviors include:

Holding because “it should work”

Delaying exits for emotional reasons

Ignoring warning signals

Hope is not a variable.

76.18 Active Conflict Detection

While position is open, system must detect:

Opposing signals

Structural breaks against position

New liquidity forming against thesis

Conflicts require action, not debate.

76.19 Drawdown Escalation Protocol

If drawdown exceeds predefined thresholds:

Management rules tighten

Partial exits favored

Full exits become more likely

Risk tolerance shrinks under stress.

76.20 Position Must Remain Coherent

A managed position must still make sense:

Direction aligns with structure

Risk aligns with reward

Exposure aligns with capital rules

If coherence is lost → exit.

76.21 Management Is Continuous, Not Discrete

Management is:

Ongoing

Iterative

Event-driven

It does not wait for targets or stops alone.

76.22 Emergency Exit Authority

The system must retain authority to:

Flatten immediately

Ignore targets

Ignore planned exits

Survival overrides planning.

76.23 No Re-Entry Assumptions

Exiting does not imply:

Re-entry will be possible

Opportunity will repeat

Market owes continuation

Each entry is independent.

76.24 Management Actions Are Final

Once an exit action is taken:

It is not reversed

It is not regretted

It is not debated

The system moves forward.

76.25 Summary

This section enforces:

Continuous risk control

Liquidity- and velocity-aware management

Strict leverage discipline

Clear separation of partial vs full exits

A position is not something you “hold.”
It is something you continuously justify.

SECTION 77 — EXIT LOGIC, INVALIDATION & TERMINATION CONDITIONS

Status: Binding
Layer: Position Termination
Scope: All positions, partial or full
Purpose: Define when and why a position must end, without ambiguity or interpretation.

77.1 Exit Is a First-Class Action

Exiting a position is not a failure state.
It is a deliberate system action governed by rules.

The system must be as precise about exits as it is about entries.

77.2 Two Categories of Exit

All exits fall into exactly one category:

Invalidation Exit — thesis is broken

Risk Exit — risk is no longer acceptable

There are no other exit types.

77.3 Invalidation Exit (Hard Exit)

A position must be fully closed immediately if any of the following occur:

Structural break against the position

Invalidation level is breached

Directional premise no longer holds

Entry condition is explicitly negated

Invalidation exits are non-negotiable.

77.4 Structural Invalidation

Structural invalidation includes, but is not limited to:

Break of a defining high/low against position

Failure to hold a critical zone that justified entry

Opposing structure forming with dominance

Once structure is broken, continuation is no longer justified.

77.5 Risk Exit (Protective Exit)

A position may be exited due to risk even if thesis remains intact.

Risk exits include:

Liquidation proximity breach

Margin stress escalation

Volatility regime change

Liquidity conditions turning hostile

Risk exits preserve capital, not logic.

77.6 Stop-Loss Trigger Is Absolute

If stop-loss is hit:

Position is closed

No re-evaluation occurs

No exception is allowed

Stops are final.

77.7 Partial Stop vs Full Stop

If position has been partially reduced:

Remaining stop governs remaining size only

Stop hit still triggers full closure of remaining exposure

Partial exits do not soften stop authority.

77.8 Liquidity-Driven Termination

A full exit may occur if:

Price enters a dominant opposing liquidity zone

Historical liquidation clusters reassert control

Continuation probability collapses abruptly

Liquidity can terminate trades, not just manage them.

77.9 Absorption-Based Exit

If absorption is detected such that:

Aggressive orders fail to move price

Liquidations occur without progress

Large resting orders cap movement

Then:

Thesis is functionally invalid

Full exit is justified

Absorption is silent rejection.

77.10 Velocity Failure Exit

If expected velocity fails to materialize:

After a breakout

After a trigger

After liquidity sweep

Then continuation assumption weakens.

Failure-to-move is information.

77.11 Time-Based Termination (Conditional)

Time alone does not invalidate a trade.

However, extended time combined with:

No progress

Rising opposing signals

Degrading reward asymmetry

Justifies exit.

77.12 Reward Degradation Exit

If remaining reward no longer compensates for risk:

Exit is allowed

Holding is unjustified

Risk-to-reward must remain favorable throughout the trade.

77.13 Conflict Resolution Rule

When conflicting signals arise:

Exit dominates hold

Safety dominates opportunity

Ambiguity resolves to flat.

77.14 No “Just One More Candle”

The system must not delay exits for:

Confirmation

Hope

Emotional attachment

Aesthetic chart reasons

If exit conditions are met, exit now.

77.15 Emergency Termination

Immediate full exit is mandatory if:

Exchange instability occurs

Data integrity is compromised

Execution reliability degrades

System invariants are violated

Capital safety overrides strategy.

77.16 Exit Does Not Imply Reversal

Exiting a position:

Does not imply opposite entry

Does not signal directional bias

Does not create obligation

Flat is a valid state.

77.17 No Exit Rationalization

After exit:

No justification is required

No narrative is constructed

No regret processing occurs

The system moves on.

77.18 Exit Atomicity

An exit must be:

Complete

Atomic

Final

Partial fills must resolve to zero exposure.

77.19 Termination Clears State

Upon full exit:

Position lifecycle resets

No memory bias is retained

No implicit preference is stored

Next trade starts clean.

77.20 Exit Overrides All Other Logic

When exit conditions are met:

Targets are ignored

Trailing logic is ignored

Management plans are ignored

Exit has highest priority.

77.21 Summary

This section enforces:

Clear invalidation logic

Risk-first termination

Liquidity- and absorption-aware exits

Zero tolerance for ambiguity

A trade ends the moment it no longer deserves to exist.

SECTION 78 — MANDATES, RESPONSES & MULTI-ACTION TRIGGERS

Status: Binding
Layer: Decision → Action Translation
Scope: M6 and above
Purpose: Define how conditions produce actions, including multiple possible responses without contradiction.

78.1 Definition: Mandate

A mandate is a formally defined permission for the system to act.

A mandate is not a prediction, signal, or opinion.
It is a conditional authorization.

If conditions are met → specific actions become allowed
If not → system remains inert

78.2 Mandates Are Conditional, Not Absolute

No mandate is “always on.”

Each mandate is activated only when:

Preconditions are satisfied

Constraints are respected

No higher-priority block exists

Mandates are context-bound.

78.3 One Condition May Produce Multiple Mandates

A single market condition may simultaneously authorize:

Reduce position

Tighten stop

Prepare exit

Disable adds

Allow reversal (after exit)

This is expected and correct.

Mandates are non-exclusive.

78.4 Mandates Do Not Imply Execution

A mandate only states what may be done.

Execution requires:

Explicit invocation

Valid position state

No blocking invariants

Compliance with risk limits

Mandate ≠ action.

78.5 Categories of Mandates

Mandates fall into exactly four categories:

Entry Mandates

Reduction Mandates

Exit Mandates

Prohibition Mandates

There are no other types.

78.6 Entry Mandates

Authorize creation of a new position.

Conditions may include:

Structure alignment

Liquidity event

Velocity confirmation

Narrative consistency

Entry mandates never override prohibitions.

78.7 Reduction Mandates

Authorize partial position reduction.

Typical triggers:

Approaching liquidity zones

Historical reaction regions

Risk concentration increase

Volatility expansion

Reduction mandates preserve optionality.

78.8 Exit Mandates

Authorize or require full position termination.

Exit mandates may be:

Mandatory (hard exit)

Permissive (allowed exit)

Mandatory exit mandates override all others.

78.9 Prohibition Mandates (Blocks)

Explicitly forbid actions.

Examples:

No new entries

No adds

No reversals

No leverage increase

Blocks have highest priority.

78.10 Priority Ordering

When multiple mandates coexist, priority is:

Prohibition

Mandatory Exit

Risk Reduction

Optional Exit

Entry

Lower-priority mandates are ignored if conflict exists.

78.11 Mandates Are Stateless

Mandates do not persist.

They exist only at the moment conditions are evaluated.

No mandate carries memory.

78.12 Mandates Are Idempotent

Repeated evaluation yielding the same mandate:

Does not compound

Does not escalate

Does not accumulate

Mandates describe permission, not pressure.

78.13 Mandates May Be Concurrent

Example:

Liquidity zone ahead → Reduction Mandate

Structural weakness → Exit Mandate

High volatility → Prohibition on adds

All may exist simultaneously.

Resolution is governed by priority.

78.14 Partial vs Full Resolution

If a condition supports both:

Partial exit

Full exit

Then:

Full exit dominates only if invalidation or risk breach exists

Otherwise reduction may occur first

Context determines extent.

78.15 Mandates Must Be Explicitly Typed

Every mandate must declare:

Type (entry / reduce / exit / prohibit)

Scope (symbol, position, global)

Strength (mandatory vs permissive)

Implicit mandates are forbidden.

78.16 No Narrative Inside Mandates

Mandates contain:

Conditions

Allowed actions

They do not contain explanations, reasoning, or interpretation.

78.17 No Time-Based Mandates Alone

Time passage alone cannot create a mandate.

Time may only contribute when paired with:

Lack of progress

Risk degradation

Opportunity decay

78.18 Mandates Do Not Chain Automatically

One mandate does not trigger another.

Each evaluation cycle is independent.

78.19 Reversal Requires Two Mandates

Reversal is only permitted if:

Exit mandate is satisfied and executed

Independent entry mandate exists in opposite direction

No single mandate may both exit and enter.

78.20 Mandate Silence Is Valid

If no mandate exists:

System does nothing

No compensation action

No forced trade

Silence is compliant behavior.

78.21 Mandates Are Observable, Not Debated

Mandates are:

Determined

Evaluated

Applied

They are not discussed, weighed, or second-guessed.

78.22 Summary

This section establishes that:

Multiple responses may be valid simultaneously

Reduction and exit are not mutually exclusive

Priority resolves conflicts

Mandates authorize, not compel

The system reacts through permissions, not impulses.

SECTION 79 — POSITION LIFECYCLE INTEGRATION WITH MANDATES

Status: Binding
Layer: Position Management
Scope: M6
Purpose: Define how mandates interact with the lifecycle of a position without ambiguity or leakage.

79.1 Definition: Position Lifecycle

A position lifecycle is the finite sequence of states a position may occupy from non-existence to termination.

Lifecycle states are structural, not interpretive.

79.2 Canonical Position States

A position may exist in exactly one of the following states:

FLAT — no position exists

OPENING — order submitted, not fully filled

OPEN — position active

REDUCING — partial exit in progress

CLOSING — full exit in progress

CLOSED — terminal state (returns to FLAT)

No other states are permitted.

79.3 State Transitions Are Explicit

Transitions may occur only via:

Order acknowledgements

Fill confirmations

Hard failures (forced close)

No implicit or inferred transitions are allowed.

79.4 Mandates Are State-Aware

Each mandate declares which position states it applies to.

Mandate Type	Valid Position States
Entry	FLAT only
Reduce	OPEN only
Exit	OPEN, REDUCING
Prohibit	ALL

Mandates evaluated outside valid states are ignored.

79.5 Entry Mandates and OPENING State

When an entry mandate is executed:

Position transitions: FLAT → OPENING

No other mandates may act on the symbol until resolution

If entry fails → returns to FLAT

OPENING is non-interruptible.

79.6 OPEN State Responsibilities

While OPEN:

Risk constraints apply continuously

Reduction and exit mandates are evaluated

Entry mandates are ignored

Adds are treated as separate entries and may be prohibited

79.7 REDUCING State Semantics

REDUCING indicates:

Partial exit orders are active

Position still exists

Further reductions may be allowed

Adds are forbidden unless explicitly permitted (rare)

REDUCING does not imply weakness or strength.

79.8 Reduction vs Exit Resolution

If during REDUCING an exit mandate appears:

REDUCING → CLOSING immediately

Remaining position is closed fully

Partial logic is abandoned

Exit dominates reduction.

79.9 CLOSING State Semantics

CLOSING indicates:

Full exit order is active

No further mandates apply

No adds, reductions, or reversals allowed

This state is terminal except for completion.

79.10 CLOSED State Is Silent

Once CLOSED:

All mandates for that symbol are discarded

No memory of prior position is retained

System returns to FLAT

No cooldown is implied unless explicitly defined elsewhere.

79.11 Prohibition Mandates Across States

Prohibitions may:

Block entry while FLAT

Block adds while OPEN

Block reversals after CLOSE

Block leverage changes at all times

Prohibitions do not change state; they restrict actions.

79.12 Lifecycle × Mandate Matrix
State	Entry	Reduce	Exit	Prohibit
FLAT	✅	❌	❌	✅
OPENING	❌	❌	❌	✅
OPEN	❌	✅	✅	✅
REDUCING	❌	✅	✅	✅
CLOSING	❌	❌	❌	✅
CLOSED	❌	❌	❌	❌
79.13 Reversal Is a Two-Step Lifecycle

Reversal is not a state.

It requires:

OPEN → CLOSING → CLOSED

CLOSED → OPENING (new entry)

No overlapping positions allowed.

79.14 Position State Is the Ultimate Arbiter

Even valid mandates cannot act if:

State disallows action

Order already in-flight

Risk invariant blocks transition

State always overrides intent.

79.15 Lifecycle Is Per Symbol

Each symbol has an independent lifecycle.

Global constraints may override, but states are not shared.

79.16 No Time-Based Transitions

Time alone does not advance lifecycle.

Only execution events may do so.

79.17 Lifecycle Has No Memory

Past states do not bias future permissions.

Each evaluation is fresh.

79.18 Failure Handling

On execution failure:

Position transitions to CLOSING if open

Otherwise returns to FLAT

Mandates are cleared

Failure collapses lifecycle safely.

79.19 Determinism Guarantee

Given:

Same position state

Same mandates

Same constraints

→ Outcome is deterministic.

79.20 Summary

This section establishes that:

Mandates act through lifecycle states

Lifecycle governs what is possible

Reduction and exit are cleanly separated

Reversal is explicit, never implicit

Positions move through states.
Mandates merely permit transitions.

SECTION 80 — RISK & EXPOSURE INVARIANTS (NON-NEGOTIABLE)

Status: Binding
Layer: Risk / Position Control
Scope: Global + Per-Symbol
Purpose: Define absolute constraints that cannot be overridden by mandates, narratives, or signals.

80.1 Definition: Invariant

A risk invariant is a rule that must hold at all times.

If an invariant would be violated:

The action is rejected

No mandate may override it

No fallback or degradation is permitted

Risk invariants sit above mandates and lifecycle logic.

80.2 Global Exposure Invariant

Invariant G-1:
Total account exposure must never exceed configured maximum.

Exposure includes:

All open positions

Pending OPENING positions

Worst-case loss to stop (not margin used)

If violated → new entries are forbidden.

80.3 Per-Symbol Exposure Invariant

Invariant S-1:
At most one net position per symbol may exist.

Implications:

No pyramiding unless explicitly allowed

No simultaneous long + short

Reversal requires full close first

This invariant is absolute.

80.4 Risk-Per-Trade Invariant

Invariant R-1:
Maximum loss per position ≤ configured risk budget (e.g. 1%).

Calculation must be based on:

Entry price

Stop price

Position size

Fees + slippage buffer

If stop is undefined → entry is forbidden.

80.5 Liquidation Avoidance Invariant

Invariant R-2:
Position must not be liquidatable under plausible adverse movement.

This includes:

Maintenance margin

Worst-case wick assumptions

Funding impact if applicable

Leverage is derived, not fixed.

If leverage implies liquidation before stop → entry forbidden.

80.6 Leverage Is a Consequence, Not a Parameter

Leverage may only be:

Computed from risk budget and stop distance

Reduced, never increased, after entry

Manual leverage targets are non-binding.

80.7 Add-On Risk Invariant

Invariant R-3:
Adds must not increase total position risk beyond original allocation.

Options:

Adds are forbidden entirely

Or adds require stop improvement that keeps risk constant or lower

If risk increases → add rejected.

80.8 Reduction Safety Invariant

Invariant R-4:
Reductions must strictly reduce exposure.

Partial exits:

Must lower absolute position size

Must not worsen liquidation profile

Must not move stop further away

Any reduction that increases risk is invalid.

80.9 Opposing Signal Handling Invariant

Invariant R-5:
Opposing entry signals do not justify additive exposure.

If in position:

Opposite direction signal → exit or reduce only

Never flip without full close

80.10 Correlated Exposure Invariant

Invariant G-2:
Highly correlated symbols count toward shared exposure.

Examples:

BTC / BTC-perps

ETH / ETH-beta alts

Correlation mapping is static or conservative.

80.11 News / Volatility Guard Invariant (Optional but Binding if Enabled)

If enabled:

Entries forbidden during defined volatility windows

Reductions and exits remain allowed

Risk reduction always permitted.

80.12 Time Does Not Relax Risk

Risk constraints do not decay over time.

A bad position does not become acceptable because it is old.

80.13 No Averaging Down Invariant

Invariant R-6:
Adding to a losing position is forbidden unless explicitly allowed by design.

Default state: forbidden.

80.14 Stop Integrity Invariant

Invariant R-7:
Every OPEN position must always have an effective stop.

If stop becomes invalid:

Immediate CLOSING is triggered

No discretionary delay allowed

80.15 Partial Exit vs Full Exit Priority

If both are valid:

Full exit dominates if risk violation is imminent

Partial exits are opportunistic, not protective

Risk protection outranks optimization.

80.16 Exposure Floor Invariant

Positions below minimum meaningful size:

Must be fully closed

No “dust” positions allowed

80.17 Failure Mode

On any invariant breach:

New actions are blocked

Existing positions move toward reduction or close

System never increases exposure to resolve violation

80.18 Invariants Are Configuration-Bound, Not Strategy-Bound

Strategies, narratives, and mandates:

Propose actions

Do not define safety

Risk configuration defines safety.

80.19 Determinism Guarantee

Given:

Same prices

Same stops

Same balances

Risk acceptance or rejection is deterministic.

80.20 Summary

This section establishes that:

Risk rules are absolute

Leverage is computed, not chosen

Exposure is capped globally and locally

No signal can justify unsafe exposure

Reduction is always allowed; expansion is conditional

The system survives by refusing trades.
Profit is optional. Survival is not.

SECTION 81 — MANDATE TAXONOMY & PRIORITY ORDERING

Status: Binding
Layer: Decision / Control
Scope: Cross-cutting (Signals, Positions, Risk, Execution)
Purpose: Define what a mandate is, the allowed types, and how conflicts are resolved.

81.1 Definition: Mandate

A mandate is a constrained instruction of the form:

“When condition(s) X are true, the system is permitted or required to perform action Y, subject to invariants.”

Key properties:

Mandates do not predict

Mandates do not assert truth

Mandates propose actions

Mandates are subordinate to invariants

A mandate may fail silently if blocked by invariants.

81.2 Mandates vs Signals vs Narratives
Concept	Role
Narrative	Defines contextual scenarios (“if this then that”)
Signal	Detects a local condition or event
Mandate	Authorizes or requires an action

Signals inform mandates.
Narratives constrain which mandates may activate.

81.3 Canonical Mandate Types
81.3.1 Entry Mandates

Authorize opening a new position.

Examples:

OPEN_LONG

OPEN_SHORT

Constraints:

Require no existing position (Invariant S-1)

Require defined stop

Require risk compliance

Entry mandates are lowest priority.

81.3.2 Exit Mandates

Authorize closing a position fully.

Examples:

CLOSE_POSITION

FORCE_EXIT

Exit mandates outrank entry mandates.

81.3.3 Reduction Mandates (First-Class)

Authorize partial exits.

Examples:

REDUCE_25

REDUCE_50

REDUCE_TO_BREAK_EVEN

Key property:

Reductions are always safer than holding

Reductions are always allowed unless explicitly forbidden

Reduction mandates are higher priority than entries.

81.3.4 Protective Mandates

Triggered by risk or structural threats.

Examples:

EXIT_ON_LIQUIDATION_RISK

EXIT_ON_STOP_INVALIDATION

EXIT_ON_VOLATILITY_SPIKE

Protective mandates override:

Entry mandates

Narrative bias

Optimization mandates

81.3.5 Structural Mandates

Derived from market structure changes.

Examples:

EXIT_ON_STRUCTURE_BREAK

REDUCE_ON_RANGE_REENTRY

EXIT_ON_FAILED_BREAKOUT

These may trigger:

Partial exit

Full exit
depending on context

81.3.6 Reversal Mandates (Composite)

Reversals are not atomic.

They decompose into:

CLOSE existing position

(Optionally) OPEN opposite position

If step 1 fails → step 2 forbidden.

81.3.7 Optimization Mandates (Lowest Safety Priority)

Examples:

SCALE_OUT_AT_TARGET

TRAIL_STOP

MOVE_STOP_TO_BE

Optimization mandates:

Must never increase risk

Must yield to all protective mandates

81.4 Mandate Priority Ordering (Hard)

When multiple mandates are active, resolve in this order:

Invariant Enforcement

Protective Mandates

Exit Mandates

Reduction Mandates

Structural Mandates

Optimization Mandates

Entry Mandates

Lower-priority mandates are ignored if blocked.

81.5 Conflict Resolution Rules
Rule C-1: Exit Dominates Entry

If EXIT and ENTRY are both active → EXIT wins.

Rule C-2: Reduce Beats Hold

If REDUCE and HOLD implied → REDUCE executes.

Rule C-3: Full Exit Beats Partial Exit

If both are valid → full exit preferred when risk is rising.

Rule C-4: No Mandate Escalation

A mandate may not escalate itself:

Reduce → cannot become Add

Optimize → cannot become Entry

81.6 Mandate Multiplicity

Multiple mandates may coexist.

Examples:

Structural reduction + optimization reduction

Protective exit + structural exit (coalesce)

The system resolves to a single net action.

81.7 Mandate Idempotence

Executing the same mandate twice must:

Either be impossible

Or result in no additional effect

Example:

REDUCE_50 executed twice must not reduce 100% unless explicitly allowed.

81.8 Mandate Preconditions

Every mandate must declare:

Required position state(s)

Required observation availability

Required invariants

If preconditions fail → mandate is inactive.

81.9 Mandates Are Stateless

Mandates:

Do not remember past executions

Are evaluated fresh each cycle

Do not accumulate intent

State lives in positions, not mandates.

81.10 Silence Is Not a Mandate

Absence of a mandate:

Does not imply HOLD

Does not imply CONFIDENCE

Means “no action proposed”

81.11 Failure Handling

If mandate execution fails:

No retry loops

No alternative mandate substitution

Next cycle re-evaluates from scratch

81.12 Extensibility Rule

New mandate types may be added only if:

They fit into the priority order

They cannot increase risk

They do not bypass invariants

81.13 Summary

This section establishes that:

Mandates are action proposals, not beliefs

Multiple mandates may exist simultaneously

Priority is absolute and deterministic

Reduction is first-class, not secondary

Reversals are composite, never implicit

The system does not “decide what it thinks.”
It decides what it is allowed to do.

SECTION 82 — POSITION LIFECYCLE STATES & TRANSITIONS

Status: Binding
Layer: Position Management
Scope: Per-symbol
Purpose: Define the only valid states a position may occupy and the legal transitions between them.

82.1 Definition: Position

A position is a live exposure on a single symbol, characterized by:

Direction

Size

Entry price

Risk constraints

Lifecycle state

A position is not a signal, mandate, or narrative.
It is a fact of exposure.

82.2 Canonical Position States

A position may exist in exactly one of the following states:

82.2.1 FLAT

No exposure exists

No position object allocated

Default state per symbol

82.2.2 OPEN

Exposure exists

Entry executed

Stop-loss defined

Full size active

82.2.3 REDUCED

Exposure exists

Size < initial size

One or more reductions executed

Stop may be adjusted or unchanged

This is not a transient state — it may persist indefinitely.

82.2.4 PROTECTED

Exposure exists

Worst-case loss ≤ 0

Examples:

Stop at breakeven

Guaranteed profit locked

Protection does not imply safety or correctness.

82.2.5 EXITING

Exit order submitted

Execution pending

No new mandates allowed except FORCE_EXIT

This is a terminal-in-progress state.

82.2.6 CLOSED

Exposure fully removed

Position finalized

PnL realized

No further actions allowed

82.3 Forbidden States (Explicit)

The following states are not allowed to exist:

HOLDING

WAITING

CONFIDENT

LOSING

WINNING

SAFE

RISKY

Positions do not carry opinions or evaluations.

82.4 State Transition Graph (Legal Only)
82.4.1 Allowed Transitions
FLAT → OPEN
OPEN → REDUCED
OPEN → PROTECTED
OPEN → EXITING
REDUCED → PROTECTED
REDUCED → EXITING
PROTECTED → EXITING
EXITING → CLOSED

82.4.2 Forbidden Transitions
REDUCED → OPEN      ❌ (cannot increase size)
PROTECTED → OPEN    ❌
CLOSED → ANY        ❌
EXITING → REDUCED   ❌
EXITING → PROTECTED ❌


No transition may increase exposure.

82.5 Transition Drivers

Transitions may be triggered only by:

Mandate execution

Invariant enforcement

Exchange execution events

Transitions may not be triggered by:

Time passage

Hope

Narrative bias

Missing data

82.6 Entry Transition (FLAT → OPEN)

Requires:

Entry mandate

Risk invariant satisfied

Stop defined

Position size calculated

Failure → remain FLAT.

82.7 Reduction Transition (OPEN → REDUCED)

Triggered by:

Reduction mandate

Structural threat

Liquidity interaction

Risk compression

Properties:

Irreversible

Size strictly decreases

Multiple reductions allowed

82.8 Protection Transition (OPEN/REDUCED → PROTECTED)

Triggered by:

Stop moved to non-loss region

Guaranteed profit condition

Important:

PROTECTED ≠ risk-free

Slippage and gaps still possible

82.9 Exit Transition (* → EXITING → CLOSED)

Triggered by:

Exit mandate

Stop-loss hit

Force exit

Properties:

Atomic intent, asynchronous execution

EXITING blocks all other mandates

82.10 Partial vs Full Exit Semantics

REDUCED ≠ EXITING

EXITING always implies intent to fully close

Partial exits never imply eventual full exit

82.11 Position Identity Rules

One position per symbol (Invariant S-1)

Direction is immutable

Reversal requires full closure first

82.12 Idempotence Guarantee

Executing the same transition twice must:

Either be impossible

Or produce no additional effect

Example:

Reducing an already reduced size below zero is forbidden.

82.13 Error Handling

If a transition fails:

Position state remains unchanged

No retries

No fallback transitions

Next evaluation cycle re-evaluates mandates.

82.14 Position State Is the Only Memory

No other component may infer:

“How long” a position has existed

“How well” it is performing

“What should happen next”

All logic reads state only.

82.15 Summary

This section establishes that:

Position state is finite and explicit

Transitions are strictly monotonic toward zero exposure

Reduction and protection are first-class states

No opinionated or evaluative states exist

Exposure can only decrease over time

Positions do not think.
They only change shape until they disappear.

SECTION 83 — POSITION & RISK INVARIANTS (FORMAL DEFINITION)

Status: Binding
Layer: Risk / Position Control
Scope: Global + Per-symbol
Purpose: Define conditions that must always be true. Invariants are enforced, not debated.

83.1 Definition: Invariant

An invariant is a condition that:

Must hold at all times

Is checked before and after every mandate

Cannot be overridden by strategy, narrative, or confidence

Triggers enforcement, not interpretation, when violated

If an invariant is violated, execution halts or exposure is reduced.

83.2 Global Risk Invariants

These apply across all symbols and positions.

83.2.1 G-1: Max Concurrent Positions
Σ open_positions ≤ MAX_POSITIONS


Default: configurable

Hard ceiling

If violated → deny new entries

83.2.2 G-2: Max Total Exposure
Σ |position_notional| ≤ MAX_TOTAL_EXPOSURE


Exposure measured in notional terms

Applies across directions

Violations trigger forced reductions, not blocking

83.2.3 G-3: Max Account Risk
Σ worst_case_loss ≤ MAX_ACCOUNT_RISK


Where:

worst_case_loss = distance to stop × size

This is pre-trade and continuous.

Violation handling:

Pre-entry → deny entry

Post-entry → force reduction or exit

83.2.4 G-4: No Unbounded Loss

Every open position must have:

A stop-loss

A computable worst-case loss

Positions without a stop are illegal.

83.2.5 G-5: Liquidation Avoidance
distance_to_liquidation ≥ LIQUIDATION_BUFFER


Buffer expressed as % or ticks

Must hold after every price update

If violated → immediate reduction or exit

This invariant supersedes all strategy logic.

83.3 Per-Symbol Position Invariants
83.3.1 S-1: One Position per Symbol
∀ symbol: count(open_positions[symbol]) ≤ 1


Already defined, restated for enforcement.

83.3.2 S-2: Direction Immutability

Once opened:

Direction cannot change

Reversal requires full close first

Violation → deny action.

83.3.3 S-3: No Size Increase
position_size(t+1) ≤ position_size(t)


Applies after OPEN

Scaling in is forbidden

Only reductions allowed

83.3.4 S-4: Entry Requires Exit Definition

At entry time:

Stop-loss must be defined

Invalid stop (too close, too far) → deny entry

83.3.5 S-5: Worst-Case Loss Monotonicity
worst_case_loss(t+1) ≤ worst_case_loss(t)


Loss profile may improve or stay equal

May never worsen after entry

Stop widening is forbidden.

83.4 Leverage Invariants
83.4.1 L-1: Effective Leverage Bound
effective_leverage = position_notional / account_equity
effective_leverage ≤ MAX_EFFECTIVE_LEVERAGE


Calculated dynamically

Price movement aware

Not static leverage setting

83.4.2 L-2: Liquidation Distance Constraint

Leverage is valid only if:

distance_to_liquidation > risk_buffer + volatility_buffer


This ties leverage to:

Volatility regime

Historical wicks

Known liquidity zones

83.4.3 L-3: Leverage Shrinks Before Exit

If leverage constraint is threatened:

Reduce size

Recalculate

Exit only if reduction insufficient

Never jump directly to full exit unless forced.

83.5 Reduction-Specific Invariants
83.5.1 R-1: Reduction Is Irreversible

Once reduced:

Original size is forgotten

No restoration allowed

83.5.2 R-2: Reduction Must Improve Risk

Every reduction must satisfy at least one:

Lower worst-case loss

Increase liquidation distance

Reduce notional exposure

Reductions without benefit are invalid.

83.6 Protection Invariants
83.6.1 P-1: Protection Is Loss-Bound Only

PROTECTED means:

worst_case_loss ≤ 0


It does not imply:

Trade success

Exit imminence

Immunity to gaps

83.6.2 P-2: Protection Cannot Be Removed

Once PROTECTED:

Stop cannot be moved back into loss

Only forward or exit

83.7 Exit Invariants
83.7.1 E-1: Exit Is Terminal Intent

Once EXITING:

No new mandates allowed

No reductions

No stop changes

Only execution events may follow.

83.7.2 E-2: Forced Exit Supremacy

Forced exits override:

Narrative

Partial exit plans

Protection state

83.8 Invariant Enforcement Order

When multiple invariants are violated:

Liquidation avoidance

Account risk

Symbol constraints

Strategy mandates

Risk invariants always win.

83.9 Invariant Silence Rule

Invariant enforcement:

Produces actions, not explanations

Does not log opinions

Does not justify itself

83.10 Summary

This section establishes that:

Risk is enforced, not discussed

Exposure only decreases over time

Leverage is dynamic and conditional

Liquidation avoidance dominates all logic

Strategy exists inside invariant walls

The system is allowed to miss trades.
It is not allowed to break invariants.

SECTION 84 — MANDATE TYPES & EXECUTION SEMANTICS

Status: Binding
Layer: Execution Control
Scope: Per-symbol, event-scoped
Purpose: Define what actions the system is allowed to take, and exactly how they behave.

A mandate is an instruction to act.
Mandates are not strategy, not interpretation, and not opinion.
They are executable intents evaluated against invariants.

84.1 Definition: Mandate

A mandate is:

A single, atomic intent

Evaluated at a point in time

Either accepted and executed, or rejected silently

Never partially applied

Mandates do not explain themselves.
Mandates do not retry themselves.

84.2 Mandate Classification (Canonical Set)

Only the following mandate types are permitted.

84.2.1 ENTRY

Intent: Open a new position

Preconditions:

No open position on symbol

All global and symbol invariants satisfied

Stop-loss defined

Size defined

Direction defined

Execution Result:

Position enters OPEN state

Exposure increases

Risk immediately bounded

Failure Handling:

If any invariant fails → ENTRY is denied

No partial entry allowed

84.2.2 EXIT

Intent: Fully close an existing position

Preconditions:

Position exists

Execution Result:

Position transitions to EXITING

Exposure reduced to zero

Terminal for that position

Notes:

EXIT always succeeds

EXIT overrides all other mandates

84.2.3 REDUCE

Intent: Decrease position size

Definition:
REDUCE is the only non-terminal mandate after entry.

Preconditions:

Position exists

Reduction size > 0

Reduction improves risk (Section 83.5.2)

Execution Result:

Position size strictly decreases

Risk metrics improve

Position remains OPEN

Notes:

Partial exits are REDUCE

Scaling out is REDUCE

REDUCE does not change direction

84.2.4 PROTECT

Intent: Remove downside risk

Definition:
A PROTECT mandate moves the stop-loss to eliminate loss.

Preconditions:

Position exists

Stop adjustment results in worst_case_loss ≤ 0

Execution Result:

Position becomes PROTECTED

Loss is no longer possible

Constraints:

Stop may not move backward after PROTECT

PROTECT does not imply exit

84.2.5 FORCE_EXIT

Intent: Immediate exit due to invariant violation

Source:

Risk engine

Liquidation proximity

Margin constraint

System integrity failure

Execution Result:

Position exits regardless of strategy

No confirmation required

Notes:

FORCE_EXIT bypasses all logic

Cannot be blocked or delayed

84.3 Explicitly Forbidden Mandates

The following do not exist:

SCALE_IN

ADD

REVERSE

HEDGE

AVERAGE_DOWN

PAUSE

WAIT

HOLD

MODIFY (generic)

REENTER

PARTIAL_ENTRY

Any attempt to simulate these through combinations is invalid.

84.4 Mandate Evaluation Order

If multiple mandates are proposed simultaneously:

FORCE_EXIT

EXIT

REDUCE

PROTECT

ENTRY

Lower-priority mandates are discarded if higher-priority ones execute.

84.5 Mandate Atomicity

Each mandate must be:

Fully applied

Or not applied at all

There is no:

Partial fill logic

Multi-step mandates

Deferred execution inside a mandate

84.6 Mandate vs Invariants

Mandates are requests.
Invariants are laws.

If a mandate conflicts with an invariant:

The invariant wins

The mandate is rejected

No explanation is produced

84.7 Mandate Silence Rule

Mandates do not:

Log intentions

Log rejections

Explain outcomes

Emit confidence

They either change state or do nothing.

84.8 Mandate Determinism

Given:

Same position state

Same market state

Same mandate

The result must be identical.

No randomness.
No adaptive interpretation.

84.9 Mandate Composition Rule

Multiple mandates may be proposed, but:

Only one mandate may execute per symbol per evaluation cycle

Execution changes state

Remaining mandates are discarded

84.10 Mandates Are Stateless

Mandates:

Do not remember past outcomes

Do not reference prior mandates

Do not adapt behavior

State lives in positions, not mandates.

84.11 Summary

This section establishes that:

There are very few allowed actions

Every action is sharply defined

Risk-driven exits dominate everything

Partial exits are REDUCE, nothing more

No mandate increases exposure

No mandate reverses direction

Strategy decides when to propose.
Invariants decide whether it happens.
Mandates decide what is allowed.


SECTION 85 — POSITION LIFECYCLE & STATE MACHINE

Status: Binding
Layer: Execution / Risk
Scope: Per-symbol, per-position
Purpose: Define all valid position states and the only legal transitions between them.

A position is a stateful entity governed by invariants.
No behavior is permitted outside this state machine.

85.1 Definition: Position

A position is a concrete exposure instance defined by:

Symbol

Direction (LONG / SHORT)

Size

Entry price

Stop-loss

Risk envelope

A position exists only while in a valid lifecycle state.

85.2 Canonical Position States

Only the following states are permitted.

85.2.1 NON_EXISTENT

Meaning:
No position exists for the symbol.

Properties:

Zero exposure

Zero risk

Only ENTRY mandates allowed

Terminal: No

85.2.2 OPENING

Meaning:
An ENTRY mandate has been accepted but execution is not yet finalized.

Properties:

Position parameters fixed

Exposure pending

Stop-loss already defined

Constraints:

No other mandates allowed

Cannot be re-entered

Terminal: No

85.2.3 OPEN

Meaning:
Position is live and exposed to market movement.

Properties:

Exposure active

Risk bounded by stop-loss

Eligible for REDUCE, PROTECT, EXIT

Constraints:

Direction immutable

Size may only decrease

Terminal: No

85.2.4 PROTECTED

Meaning:
Worst-case loss has been eliminated.

Definition:
A position is PROTECTED when:

worst_case_loss ≤ 0


Properties:

Downside risk removed

Upside exposure retained

Constraints:

Stop-loss may not worsen

Size may still be reduced

Terminal: No

85.2.5 REDUCING

Meaning:
A REDUCE mandate is being applied.

Properties:

Position size decreasing

Exposure strictly reduced

Constraints:

Cannot increase size

Cannot reverse direction

Terminal: No

85.2.6 EXITING

Meaning:
An EXIT or FORCE_EXIT mandate is being executed.

Properties:

Position winding down

Exposure collapsing to zero

Constraints:

No other mandates permitted

Irreversible

Terminal: Yes

85.2.7 CLOSED

Meaning:
Position fully closed.

Properties:

Zero exposure

Zero risk

Historical only

Constraints:

Cannot transition to any other state

Terminal: Yes

85.3 Legal State Transitions

Only the following transitions are allowed:

NON_EXISTENT → OPENING
OPENING → OPEN
OPEN → PROTECTED
OPEN → REDUCING
PROTECTED → REDUCING
OPEN → EXITING
PROTECTED → EXITING
REDUCING → OPEN
REDUCING → PROTECTED
REDUCING → EXITING
EXITING → CLOSED


Any transition not listed is illegal.

85.4 Forbidden Transitions (Explicit)

The following transitions must never occur:

CLOSED → ANY

OPEN → OPENING

PROTECTED → OPENING

REDUCING → OPENING

ANY → NON_EXISTENT

OPEN → OPPOSITE DIRECTION

REDUCING → INCREASED SIZE

85.5 Direction Immutability

Once a position enters OPENING, its direction:

Cannot change

Cannot be inverted

Cannot be neutralized except by EXIT

Reversal requires:

EXIT → NON_EXISTENT → ENTRY

85.6 Single-Position Rule (Reinforced)

At most one position per symbol may exist.

Implications:

No overlapping positions

No pyramiding

No hedging

No simultaneous long and short

85.7 Lifecycle vs Mandates
Mandate	Allowed States	Resulting State
ENTRY	NON_EXISTENT	OPENING
REDUCE	OPEN, PROTECTED	REDUCING
PROTECT	OPEN	PROTECTED
EXIT	OPEN, PROTECTED	EXITING
FORCE_EXIT	ANY (except CLOSED)	EXITING
85.8 Failure Handling

If at any point:

Risk invariant is violated

Margin invariant is violated

Liquidation proximity invariant is violated

Then:

ANY STATE → EXITING


No exceptions.

85.9 Silence Rule (Reaffirmed)

State transitions do not:

Log

Notify

Explain

Emit reasoning

They mutate state or do nothing.

85.10 Determinism Guarantee

Given:

Same initial state

Same mandate

Same invariant results

The resulting state must be identical.

85.11 Summary

This section guarantees that:

A position is never ambiguous

Direction cannot flip silently

Size can only go down

Risk only decreases over time

Every position ends in CLOSED

No hidden or implicit states exist

Positions are finite, directional, and mortal.

SECTION 86 — RISK INVARIANTS & EXPOSURE GOVERNANCE

Status: Binding
Layer: Execution / Risk
Scope: Per-position, per-symbol, portfolio-aware
Purpose: Define immutable risk constraints that must hold at all times, regardless of strategy, mandate, or market condition.

Risk is not a preference.
Risk is a hard invariant.

86.1 First Principle

A position may exist only if its worst-case outcome is known, bounded, and acceptable.

If this cannot be proven, the position must not exist.

86.2 Canonical Risk Units

All risk is expressed in account equity units, not price units.

Definitions:

Account Equity (E) — current net account value

Risk Budget per Position (Rₚ) — maximum allowed loss for one position

Portfolio Risk (Rₜ) — sum of worst-case losses across all open positions

86.3 Core Risk Invariants (Always Enforced)

These invariants must hold at all times, including during volatility, gaps, and execution latency.

86.3.1 Maximum Risk per Position
worst_case_loss(position) ≤ Rₚ


Where:

Rₚ = E × risk_fraction


Default constraint:

risk_fraction ≤ 1%


Violation → EXITING

86.3.2 Stop-Loss Mandatory Invariant

A position must not exist without a stop-loss.

Rules:

Stop defined before or at entry

Stop must be executable

Stop must cap loss within Rₚ

Violation → EXITING

86.3.3 Risk Monotonicity

Once a position is OPEN:

worst_case_loss(t+1) ≤ worst_case_loss(t)


Implications:

Risk may only decrease

Risk may never increase

Moving stop away is forbidden

Increasing size is forbidden

Violation → EXITING

86.4 Leverage Constraint (Liquidation-Aware)

Leverage is not a fixed number.
Leverage is derived from liquidation distance.

86.4.1 Liquidation Proximity Invariant

Define:

Pₗ = estimated liquidation price

Pₛ = stop-loss price

Invariant:

|Pₗ − P_entry| > |Pₛ − P_entry|


Meaning:

Stop-loss must trigger before liquidation

Liquidation must be unreachable without stop violation

Violation → EXITING

86.4.2 Maximum Effective Leverage

Effective leverage is constrained by:

Stop distance

Volatility

Margin requirements

Fee + slippage buffer

There is no static leverage value.

Any position whose size implies:

liquidation_distance ≤ stop_distance


is illegal.

86.5 Exposure Invariants
86.5.1 Single-Symbol Exposure

Reaffirmed:

max_positions_per_symbol = 1

86.5.2 Directional Exclusivity

A symbol may have:

One LONG

Or one SHORT

Or none

Never both.

86.5.3 Correlated Exposure Awareness

If multiple symbols are strongly correlated:

Σ worst_case_loss(correlated_positions) ≤ Rₜ


Correlation awareness is conservative:

When uncertain → assume correlated

When unknown → assume correlated

86.6 Portfolio Risk Ceiling

At any time:

Σ worst_case_loss(all_positions) ≤ Rₜ


Where:

Rₜ ≤ E × portfolio_risk_fraction


Default:

portfolio_risk_fraction ≤ 3%


Violation → reject ENTRY mandates

86.7 Partial Reduction Rules

REDUCE mandates must satisfy:

Position size strictly decreases

Worst-case loss strictly decreases

Liquidation distance weakly increases

REDUCE may never:

Increase leverage

Increase liquidation proximity

Increase worst-case loss

Violation → reject REDUCE

86.8 Forced Exit Conditions

Immediate transition to EXITING occurs if any of the following are true:

Stop-loss invalidated

Margin requirement violated

Liquidation proximity invariant violated

Exchange risk parameters change unfavorably

Price gaps beyond stop

No retries. No recovery.

86.9 Risk vs Opportunity Asymmetry

Risk constraints always override opportunity.

Even if:

Setup is “perfect”

Signal is “high confidence”

Narrative strongly aligns

Risk invariants are absolute.

86.10 Silence Rule (Reaffirmed)

Risk checks do not:

Log

Signal

Explain

Warn

They allow or they exit.

86.11 Determinism Guarantee

Given:

Same equity

Same prices

Same parameters

Risk decisions must be identical.

No stochastic tolerance.

86.12 Summary

This section guarantees:

No trade can blow up the account

Liquidation is structurally prevented

Risk never increases after entry

Leverage is derived, not chosen

Portfolio exposure is capped

All exits are deterministic and final

Risk is the law. Opportunity is optional.

SECTION 87 — MANDATE TYPES & EXECUTION SEMANTICS

Status: Binding
Layer: Execution (M6)
Scope: Action taxonomy, legality, and effects
Purpose: Define the only allowed execution intents, their preconditions, and their effects on position state.

Mandates are requests.
Execution is conditional.

87.1 First Principle

M6 executes effects, not interpretations.

Mandates encode what may be done, never why it should be done.

87.2 Canonical Mandate Set (Closed)

Only the following mandate types are permitted.
No extensions without constitutional amendment.

87.2.1 ENTRY

Create a new position.

87.2.2 REDUCE

Reduce an existing position (partial exit).

87.2.3 EXIT

Fully close an existing position.

87.2.4 REVERSE

Atomic EXIT followed by ENTRY in opposite direction.

87.2.5 HOLD

Explicit no-op (used for traceability; no execution).

87.3 ENTRY Mandate Semantics
Preconditions (ALL required)

No existing position on symbol

Stop-loss specified

Worst-case loss ≤ Rₚ

Liquidation proximity invariant satisfied

Portfolio risk ceiling not exceeded

Direction exclusivity satisfied

Effects

Position state → OPEN

Stop-loss becomes immutable reference

Risk monotonicity enforced from this point forward

Illegal ENTRY Conditions

Missing stop

Size increase without defined stop

Any ambiguity in risk bounds

Illegal ENTRY → REJECT

87.4 REDUCE Mandate Semantics

REDUCE is structural, not tactical.

Preconditions

Position exists

Reduction size < current size

Effects

Position size strictly decreases

Worst-case loss strictly decreases

Stop-loss may tighten only

Liquidation distance weakly increases

Notes on Liquidity-Driven REDUCE

A REDUCE may be triggered by:

Approaching historical liquidity zone

Prior liquidation cascade region

Known absorption zone

Prior high-velocity reversal region

Importantly:

REDUCE does not imply EXIT intent

REDUCE does not invalidate continuation scenarios

87.5 EXIT Mandate Semantics

EXIT is final.

Preconditions

Position exists

Effects

Position size → 0

State → CLOSED

All associated risk removed

EXIT Sources (Non-Exhaustive)

Stop-loss hit

Risk invariant violation

Structural invalidation

Mandate override

Forced exit conditions (Section 86)

EXIT cannot be blocked.

87.6 REVERSE Mandate Semantics

REVERSE = EXIT + ENTRY (atomic).

Preconditions

EXIT must be legal

ENTRY must independently satisfy all ENTRY conditions

Effects

Old position closed

New position opened in opposite direction

No transient flat exposure ambiguity

Illegal REVERSE

If ENTRY would be illegal:

REVERSE is illegal

EXIT may still proceed independently

87.7 HOLD Mandate Semantics

HOLD is explicit silence.

Purpose

Preserve determinism

Allow mandate evaluation without action

Encode “do nothing” as a conscious outcome

Effects

No state change

No risk change

No execution

87.8 Mandate Priority Ordering

If multiple mandates are proposed simultaneously:

Priority order (highest first):

EXIT

REDUCE

REVERSE

ENTRY

HOLD

Lower-priority mandates are ignored if higher-priority mandates are legal.

87.9 Multiple Mandates per Symbol

Allowed only if they are compatible:

Examples:

REDUCE + HOLD → legal (REDUCE executes)

REDUCE + EXIT → EXIT executes

ENTRY + EXIT → EXIT executes (ENTRY ignored)

ENTRY + REVERSE → REVERSE ignored (illegal)

Conflicts resolve by priority, not negotiation.

87.10 Temporal Constraints

Mandates are event-scoped.

Evaluated once

Executed once or rejected

Never retried

Never cached

87.11 Determinism Guarantee

Given:

Same mandates

Same state

Same prices

Execution outcome must be identical.

No randomness. No heuristics.

87.12 Summary

This section guarantees:

A closed, finite action vocabulary

Clear legality rules for each action

Safe coexistence of partial exits and full exits

Support for liquidity-driven reductions without blocking continuation

Deterministic conflict resolution

Absolute separation between intent and interpretation

Mandates describe permission. Execution enforces law.

SECTION 88 — POSITION LIFECYCLE & STATE TRANSITIONS

Status: Binding
Layer: Execution (M6)
Scope: Position state machine
Purpose: Define all legal position states and the only valid transitions between them.

This section removes ambiguity around what state a position is in and what actions are legally possible from that state.

88.1 Core Principle

A position is always in exactly one state.
State transitions are discrete, irreversible, and law-governed.

No fuzzy, overlapping, or inferred states exist.

88.2 Canonical Position States (Closed Set)

Only the following states are permitted.

88.2.1 NONE

No position exists for the symbol.

88.2.2 OPEN

A live position exists with non-zero size and an active stop-loss.

88.2.3 REDUCED

A live position exists with reduced size relative to original entry.

(REDUCED is not a terminal state; it is a subtype of OPEN with additional invariants.)

88.2.4 EXITING

A position is in the process of being closed (execution in-flight).

88.2.5 CLOSED

The position has been fully exited. No exposure remains.

88.3 State Invariants

Each state carries strict invariants.

NONE

Size = 0

No stop-loss

No liquidation risk

No mandates except ENTRY or HOLD allowed

OPEN

Size > 0

Stop-loss exists

Worst-case loss bounded

Liquidation distance defined

Only REDUCE, EXIT, REVERSE, HOLD allowed

REDUCED

Size > 0

Size < original entry size

Worst-case loss < original worst-case loss

Stop-loss ≥ original stop (directionally tightened or equal)

ENTRY forbidden

Further REDUCE allowed

EXIT allowed

EXITING

Size > 0 (temporarily)

No new mandates allowed

Only execution completion permitted

CLOSED

Size = 0

All risk = 0

Only ENTRY or HOLD allowed

88.4 Legal State Transitions

All legal transitions are explicitly listed below.
Any transition not listed is illegal.

From NONE

NONE → OPEN (via ENTRY)

NONE → NONE (via HOLD)

From OPEN

OPEN → REDUCED (via REDUCE)

OPEN → EXITING (via EXIT)

OPEN → EXITING (via REVERSE)

OPEN → OPEN (via HOLD)

From REDUCED

REDUCED → REDUCED (via REDUCE)

REDUCED → EXITING (via EXIT)

REDUCED → EXITING (via REVERSE)

REDUCED → REDUCED (via HOLD)

From EXITING

EXITING → CLOSED (execution completes)

From CLOSED

CLOSED → OPEN (via ENTRY)

CLOSED → CLOSED (via HOLD)

88.5 Forbidden Transitions (Explicit)

The following transitions are never allowed:

NONE → REDUCED

NONE → EXITING

OPEN → NONE

REDUCED → NONE

CLOSED → REDUCED

CLOSED → EXITING

CLOSED → REVERSE

Any state → ENTRY except NONE or CLOSED

Illegal transition attempt → HARD REJECT

88.6 Relationship to Mandates

Mandates do not force transitions; they request them.

Mandate	Allowed From States	Resulting Transition
ENTRY	NONE, CLOSED	→ OPEN
REDUCE	OPEN, REDUCED	→ REDUCED
EXIT	OPEN, REDUCED	→ EXITING
REVERSE	OPEN, REDUCED	→ EXITING → OPEN
HOLD	Any	No transition
88.7 Partial Exit Semantics Clarified

Partial exits do not imply:

Weakness

Exit intent

Strategy failure

Bias change

REDUCED simply encodes:

“Exposure has been intentionally lowered while preserving optionality.”

This is critical for:

Liquidity-zone reactions

Absorption zones

Prior liquidation regions

High-velocity memory zones

88.8 Temporal Guarantees

State transitions are atomic

No intermediate or half-states

EXITING is the only transient state

EXITING cannot be reversed

88.9 Determinism & Replay Safety

Given:

Same initial state

Same mandate

Same price inputs

The resulting state transition must be identical.

This enables:

Deterministic backtesting

Replay validation

Formal verification

88.10 Summary

This section guarantees:

A complete, closed position state machine

Explicit legality of every transition

Clean handling of partial exits

No ambiguity between REDUCE and EXIT

Strong compatibility with narrative-based trading

Deterministic execution behavior

Positions do not “drift.” They move between named states under law.

SECTION 89 — RISK & POSITION INVARIANTS (FORMAL DEFINITION)

Status: Binding
Layer: Execution (M6)
Scope: Risk, exposure, leverage, liquidation safety
Purpose: Define non-negotiable invariants that must hold at all times for any position.

This section converts “risk management” from heuristics into hard laws.

89.1 Core Principle

A position may only exist if its worst-case outcome is known, bounded, and acceptable.

Anything else is not a position — it is undefined exposure.

89.2 Global Risk Invariants (Always Enforced)

These invariants apply regardless of strategy, symbol, or mandate.

89.2.1 Bounded Loss Invariant

For every OPEN or REDUCED position:

Maximum loss must be computable

Maximum loss must be ≤ allowed risk budget

If max loss cannot be computed → position is illegal

No exceptions.

89.2.2 Stop-Loss Existence Invariant

Every OPEN or REDUCED position must have a stop-loss

Stop-loss must exist before or at entry

Stop-loss removal is forbidden

No “mental stops.” No deferred placement.

89.2.3 Liquidation Safety Invariant

Liquidation price must never be reachable before stop-loss

Distance(stop → liquidation) must be strictly positive

If liquidation would occur before stop → position is illegal

This applies dynamically as leverage, funding, or price changes.

89.3 Leverage Invariants

Leverage is not a number — it is a derived constraint.

89.3.1 Maximum Effective Leverage

Effective leverage is constrained by:

Stop distance

Account equity

Risk per trade

Maintenance margin

Allowed leverage = min(leverage from risk, leverage from liquidation safety)

Any leverage value not derived from these is forbidden.

89.3.2 No Fixed Leverage Rule

Rules like:

“Always use 10x”

“Cap at 5x”

“Scale leverage by confidence”

are illegal.

Leverage must be computed per trade.

89.4 Exposure Invariants
89.4.1 Single-Symbol Exposure

At most one net position per symbol

Long and short simultaneously on same symbol is forbidden

Opposite-direction signal ⇒ CLOSE then optionally OPEN

89.4.2 Aggregate Exposure Constraint

Total account exposure must satisfy:

Sum of worst-case losses ≤ total risk cap

Correlated symbols count toward same risk bucket

Correlation ignorance is forbidden

89.5 Reduction Invariants

REDUCE is not cosmetic; it must improve safety.

89.5.1 Loss Reduction Invariant

After REDUCE:

New worst-case loss < previous worst-case loss

If not, REDUCE is illegal.

89.5.2 Liquidation Distance Improvement

After REDUCE, at least one must improve:

Liquidation distance

Margin buffer

Required maintenance margin

Otherwise REDUCE is rejected.

89.6 Exit Invariants

EXIT is mandatory under the following conditions:

Stop-loss is invalidated

Liquidation distance ≤ safety threshold

Execution uncertainty exceeds tolerance

Observation FAILED (hard dependency)

EXIT overrides all other mandates.

89.7 Reversal Invariants

REVERSE is equivalent to:

EXIT current position

OPEN new position in opposite direction

Both legs must independently satisfy all invariants.

Shortcut reversals are forbidden.

89.8 Temporal Risk Invariants

Risk is evaluated:

At entry

After every price update

After every reduction

After funding / margin change

Before any mandate execution

If any invariant fails at any time → immediate EXIT.

89.9 Forbidden Risk Behaviors (Explicit)

The following are illegal:

Moving stop further away to “give room”

Increasing size while in drawdown

Adding leverage without reducing risk

Assuming volatility “won’t expand”

Relying on liquidation instead of stop

Averaging down without revalidation

89.10 Summary

This section guarantees:

No undefined exposure

No hidden leverage

No liquidation-driven exits

No emotional sizing

No silent risk creep

Risk is not managed. It is enforced.

SECTION 90 — MANDATE TYPES & EXECUTION PRIORITY

Status: Binding
Layer: M6 (Execution)
Scope: Action taxonomy, conflict resolution, ordering
Purpose: Define what M6 is allowed to do and which action wins when multiple are valid.

This section prevents contradictory behavior and race conditions.

90.1 Core Principle

M6 does not decide what is best.
M6 selects the highest-priority permissible mandate.

No scoring. No confidence. No optimization.

90.2 Mandate Definition

A Mandate is a permissioned execution action that:

Is explicitly triggered by upstream conditions

Is evaluated against invariants

Is either executed fully or not at all

Mandates do not partially execute.

90.3 Canonical Mandate Types
90.3.1 EXIT

Meaning: Fully close an existing position.

Properties:

Direction-agnostic

Size = 100% of remaining position

Irreversible

Special Status:
EXIT has absolute priority over all other mandates.

90.3.2 REDUCE

Meaning: Partially close an existing position.

Properties:

Size < 100%

Must strictly reduce risk (see Section 89)

May occur multiple times

Note:
REDUCE does not imply weakness or profit-taking — it is structural.

90.3.3 OPEN

Meaning: Open a new position.

Properties:

Only allowed if no position exists for symbol

Requires full invariant validation

Creates a new Position Lifecycle (Section 91)

90.3.4 REVERSE (Derived)

Meaning: Change directional exposure.

Definition:
REVERSE ≡ EXIT → OPEN (opposite direction)

Constraint:

Treated as two independent mandates

If OPEN fails after EXIT → system remains flat

90.3.5 HOLD (Implicit)

Meaning: Do nothing.

Properties:

Default state

Not an executable mandate

Occurs when no mandate passes validation

90.4 Mandate Priority Order (Strict)

When multiple mandates are simultaneously valid, M6 must apply only the highest-priority one.

Priority Table (Highest → Lowest)

EXIT

REDUCE

REVERSE (only if EXIT not independently required)

OPEN

HOLD

No reordering permitted.

90.5 Conflict Resolution Rules
90.5.1 EXIT vs Anything

If EXIT is valid:

All other mandates are ignored

EXIT executes immediately

90.5.2 REDUCE vs OPEN

If already in position:

REDUCE supersedes OPEN

OPEN is illegal until flat

90.5.3 REDUCE vs EXIT

If both valid:

EXIT wins

REDUCE is skipped

90.5.4 Multiple REDUCE Mandates

If multiple REDUCE candidates exist:

Choose the one that maximally improves safety

Tie-breaker: smallest remaining exposure

No sequencing of reductions in a single tick.

90.6 Liquidity-Zone Ambiguity Rule

When a region implies either partial or full exit:

EXIT and REDUCE may both be valid

EXIT wins

Partial exits are only allowed when full exit is not required

This resolves the ambiguity you identified earlier.

90.7 Mandate Rejection Rules

A mandate is rejected if:

It violates any invariant (Section 89)

It conflicts with a higher-priority mandate

Required inputs are missing

Observation is UNINITIALIZED or FAILED

Rejected mandates do not retry.

90.8 Temporal Execution Rule

At most one mandate per symbol per evaluation cycle.

This prevents flip-flopping and over-execution.

90.9 Forbidden Mandate Patterns

The following are illegal:

Executing multiple mandates sequentially in one tick

Partial EXIT masquerading as REDUCE

Conditional OPEN after REDUCE in same cycle

“Soft exits” or “test exits”

Mandates that depend on future confirmation

90.10 Summary

This section guarantees:

Deterministic execution

No contradictory actions

Clear dominance of safety

Predictable behavior under ambiguity

M6 does not choose opportunities.
It obeys priority.

SECTION 91 — POSITION LIFECYCLE STATES

Status: Binding
Layer: M6 (Execution)
Scope: Position state machine
Purpose: Define exactly how a position exists, changes, and terminates.

This section eliminates ambiguous “in-position” logic.

91.1 Core Principle

A position is always in exactly one state.
State transitions are explicit and irreversible.

No hidden states. No inferred states.

91.2 Canonical Position States
91.2.1 FLAT

Meaning:
No position exists for the symbol.

Properties:

Zero exposure

Zero leverage

Zero risk

Allowed Mandates:

OPEN only

91.2.2 OPENING

Meaning:
An OPEN mandate has been issued but not yet confirmed.

Properties:

Transitional state

Temporary

No new mandates allowed

Exit Conditions:

→ ACTIVE (order confirmed)

→ FLAT (order rejected or failed)

91.2.3 ACTIVE

Meaning:
Position exists and is fully open.

Properties:

Exposure present

Risk present

Direction fixed

Allowed Mandates:

REDUCE

EXIT

Disallowed Mandates:

OPEN

REVERSE (must decompose: EXIT → OPEN)

91.2.4 REDUCING

Meaning:
A REDUCE mandate is executing.

Properties:

Exposure decreasing

Direction unchanged

Cannot accept new mandates

Exit Conditions:

→ ACTIVE (partial reduction)

→ FLAT (reduction completes position)

91.2.5 EXITING

Meaning:
An EXIT mandate is executing.

Properties:

Exposure collapsing to zero

Terminal for this position

Highest-priority state

Exit Conditions:

→ FLAT (successful exit)

→ FAILED (execution failure)

91.2.6 FAILED

Meaning:
Position entered an unrecoverable execution failure.

Properties:

Execution integrity compromised

Manual intervention required

No automatic recovery

Allowed Actions:

None (system halts for symbol)

91.3 State Transition Diagram (Textual)
FLAT
  └─ OPEN → OPENING
               ├─ success → ACTIVE
               └─ failure → FLAT

ACTIVE
  ├─ REDUCE → REDUCING
  │             ├─ partial → ACTIVE
  │             └─ full → FLAT
  └─ EXIT → EXITING
                ├─ success → FLAT
                └─ failure → FAILED


No other transitions exist.

91.4 Direction Immutability Rule

Once ACTIVE:

Direction cannot change

Any opposite exposure requires:

EXIT

Return to FLAT

OPEN in opposite direction

No in-place flips allowed.

91.5 One-Position-Per-Symbol Invariant

At all times:

A symbol may have at most one position

No hedging

No overlapping entries

No layered exposure

This is enforced structurally by state machine.

91.6 Partial Exit Semantics

A REDUCE:

Must reduce absolute exposure

Must not increase liquidation risk

May be repeated over time

Cannot occur while EXITING

REDUCE never implies weakness or profit intent.

91.7 Failure Semantics

If a state enters FAILED:

Symbol execution halts

No retries

No fallback logic

Observation and M6 propagate failure upward

FAILED is terminal.

91.8 Temporal Constraint

Only one state transition per symbol per evaluation cycle.

This prevents:

Rapid flip-flops

Multiple reductions in one tick

Race conditions

91.9 Forbidden States

The following do not exist:

“Scaling in”

“Pyramiding”

“Hedged”

“Soft exit”

“Probe position”

“Test trade”

If a concept is not named here, it is illegal.

91.10 Summary

This section guarantees:

Deterministic behavior

Enforced discipline

Clear lifecycle visibility

No ambiguous exposure

Positions are not strategies.
They are state machines.

SECTION 92 — POSITION & RISK INVARIANTS (FORMALIZED)

Status: Binding
Layer: M6 (Execution)
Scope: All positions, all symbols, all time
Purpose: Define non-negotiable constraints that must always hold true.

An invariant is not a rule of thumb.
An invariant is a condition that must never be violated.

92.1 Global Risk Invariant

The system must be able to survive the worst possible outcome of any single position.

If a position can cause catastrophic loss under any plausible path, it is illegal.

92.2 One-Position-Per-Symbol Invariant

At any moment:

A symbol has either

exactly one position, or

no position

Forbidden:

Multiple concurrent positions per symbol

Long + short simultaneously

Shadow exposure via partial orders

This invariant is enforced by the position lifecycle (Section 91).

92.3 Maximum Risk Per Position

Each position must satisfy:

MaxLoss(position) ≤ R_max


Where:

R_max is a fixed fraction of total account equity

Typically expressed as a percentage (e.g., 0.5%, 1%)

This includes:

Slippage

Fees

Worst-case execution outcome

If worst-case loss cannot be bounded → position forbidden.

92.4 Aggregate Exposure Invariant

At all times:

Σ |NotionalExposure(symbol_i)| ≤ E_max


Where:

E_max is a fixed multiple of account equity

Includes all open positions

This prevents:

Over-correlation blowups

Systemic liquidation cascades

Hidden leverage via many “small” positions

92.5 Leverage Safety Invariant

Leverage is not a constant; it is a derived quantity.

For every position:

DistanceToLiquidation ≥ L_min


Where:

Distance is measured in price units or %

Must account for:

Maintenance margin

Worst-case volatility spike

Known liquidity gaps

If liquidation can occur due to normal market movement → leverage is illegal.

92.6 No-Liquidation-By-Design Rule

Liquidation is a system failure, not a risk management tool.

Therefore:

No position may rely on liquidation as a stop

Liquidation probability must be asymptotically near zero

If liquidation is plausible → position size is invalid

92.7 Stop-Loss Existence Invariant

Every ACTIVE position must have:

A defined exit condition

A defined loss boundary

Whether implemented as:

Hard stop

Soft stop

Structural invalidation

A position without a loss boundary is illegal.

92.8 Opposing Signal Invariant

If conditions arise that justify entry in the opposite direction:

The existing position must be closed first

No overlap

No netting

No internal reversal

This enforces narrative clarity and exposure hygiene.

92.9 Partial Reduction Safety Invariant

A REDUCE action must satisfy:

Absolute exposure decreases

Liquidation distance does not decrease

Remaining position remains valid under all other invariants

If partial reduction increases fragility → forbidden.

92.10 Liquidity-Aware Exposure Invariant

Position size must respect historical and structural liquidity:

Past liquidation cascades

Known stop-hunt regions

High-velocity rejection zones

Thin books near price

If exiting the position would likely cause adverse movement → size is too large.

92.11 Correlated Risk Invariant

If multiple positions exist across symbols:

Correlation must be explicitly assumed as 1.0 unless proven otherwise

Risk must be calculated as if all positions move against the system together

No diversification assumptions by default.

92.12 Time-Based Risk Invariant

Risk is not static.

Before and during:

High-impact news

Rollover periods

Known illiquid sessions

Either:

Exposure is reduced

Or new positions are forbidden

Time is a risk vector.

92.13 Memory-Conflict Invariant

If historical memory indicates:

Prior liquidation cascades

Repeated absorption failures

Structural rejection zones

Then:

Full-size exposure is forbidden

Only reduced or no exposure is allowed

Memory overrides local signals.

92.14 Invariant Enforcement Rule

If any invariant cannot be verified at decision time:

The position must not be opened

Or must be reduced/closed immediately

Unverifiable risk is invalid risk.

92.15 Summary

These invariants guarantee:

Capital preservation

Deterministic exposure

No hidden fragility

No narrative contradictions

Strategy chooses when to act.
Invariants decide whether acting is allowed.

SECTION 93 — MANDATE TYPES & EXECUTION INTENT

Status: Binding
Layer: M6 (Execution)
Scope: How actions are expressed, not why
Purpose: Define what kinds of actions the system is allowed to take, without interpretation.

A mandate is an instruction to act, not a prediction, not a belief, not a signal.

93.1 Definition of a Mandate

A mandate is a structural permission to perform a specific action if and only if all invariants (Section 92) are satisfied.

A mandate does not:

Explain market conditions

Assert confidence

Interpret observation

Predict outcomes

It only authorizes an action.

93.2 Core Mandate Categories

The system recognizes the following canonical mandate types.

No others are permitted unless explicitly added to this document.

93.2.1 OPEN Mandate

Purpose: Create a new position.

Preconditions:

No existing position on the symbol

All Position & Risk Invariants satisfied

Entry zone defined

Exit boundary defined

Parameters (minimum):

symbol

direction (long / short)

max_risk

entry_zone

exit_boundary

If any parameter is undefined → mandate is invalid.

93.2.2 CLOSE Mandate

Purpose: Fully exit an existing position.

Preconditions:

Position exists

Triggers may include (non-exhaustive):

Structural invalidation

Opposing scenario confirmation

Risk invariant violation

Memory conflict escalation

Time-based risk escalation

CLOSE is always allowed.
CLOSE never requires justification.

93.2.3 REDUCE Mandate

Purpose: Decrease exposure without fully exiting.

This is a first-class mandate, not a hack.

Preconditions:

Position exists

Reduction amount specified

Post-reduction state satisfies all invariants

REDUCE does not:

Reverse position

Increase risk

Delay mandatory exits

93.2.4 HOLD Mandate

Purpose: Explicitly do nothing.

HOLD is an active decision, not absence of action.

Used when:

Position remains valid

No exit or reduction conditions met

Risk remains acceptable

This prevents accidental drift into unmanaged exposure.

93.2.5 BLOCK Mandate

Purpose: Forbid opening a position.

Used when:

Entry conditions appear satisfied

But higher-order constraints forbid exposure

Examples:

Time-based risk

Memory conflict

Aggregate exposure limit reached

BLOCK overrides OPEN.

93.3 Compound Mandates (Atomic Sequences)

Some actions require atomic combinations:

93.3.1 CLOSE → OPEN (Reversal)

If an opposite-direction scenario confirms:

CLOSE existing position

OPEN new position

These must be:

Sequential

Non-overlapping

Treated as a single intent

Partial reversals are forbidden.

93.3.2 REDUCE → HOLD

Used when:

Partial profit taken

Risk reduced

Remaining exposure still valid

REDUCE does not imply exit intent.

93.4 Multiple Mandates — Allowed With Constraints

Yes, multiple mandates are allowed, with strict rules:

Only one mandate per symbol at a time

Mandates are evaluated independently per symbol

Global risk invariants apply across all mandates

Example:

Symbol A → HOLD

Symbol B → REDUCE

Symbol C → BLOCK

This is valid.

93.5 Mandate Priority Order

If multiple mandates compete:

FAILED propagation (system halt)

CLOSE

REDUCE

BLOCK

OPEN

HOLD

Lower-priority mandates are discarded if higher-priority ones apply.

93.6 Mandates vs Strategy

Important separation:

Strategy proposes scenarios

Mandates authorize actions

Invariants veto actions

Mandates do not encode strategy logic.

93.7 What Mandates Must NOT Contain

A mandate must never contain:

Confidence scores

Market interpretation

Probability

Expected value

Narrative explanation

Emotional language

Mandates are mechanical permissions.

93.8 Mandate Exhaustiveness Rule

For every symbol at every decision point, exactly one of the following must be true:

OPEN

CLOSE

REDUCE

HOLD

BLOCK

Ambiguity is forbidden.

93.9 Summary

Mandates define:

What the system may do

Not why

Not whether it is good

Observation informs.
Strategy proposes.
Invariants constrain.
Mandates act.


SECTION 94 — ENTRY ZONES, EXIT ZONES & STRUCTURAL BOUNDARIES

Status: Binding
Layer: Strategy → Mandate Interface
Scope: Spatial constraints on execution
Purpose: Define where actions are allowed to occur, independent of timing or interpretation.

This section formalizes price-space constraints that gate all OPEN, REDUCE, and CLOSE mandates.

94.1 Fundamental Principle

No position may be opened, reduced, or exited outside a defined zone.

If a zone is not defined, the action is forbidden.

Zones are structural, not predictive.

94.2 Entry Zone (EZ)
94.2.1 Definition

An Entry Zone is a bounded price interval where opening exposure is permitted.

It is not a point.
It is not “market price”.
It is not a feeling.

It is a range.

94.2.2 Required Properties

Every Entry Zone MUST specify:

lower_bound

upper_bound

origin_type (structural classification)

invalidation_rule

If any property is missing → OPEN mandate is invalid.

94.2.3 Allowed Origin Types (Non-Interpretive)

Entry Zones may be derived from:

Unfilled imbalance region

Prior high-velocity price expansion origin

Stop-hunt sweep origin

Liquidation cascade origin

Structural retest region

Compression release boundary

Range extremity boundary

Zones are defined by historical price behavior, not expectation.

94.2.4 Entry Zone Discipline

Rules:

Entry may only occur inside the zone

Entering late (outside zone) is forbidden

Chasing price invalidates the mandate

Touching the zone does not force entry

Entry Zones permit action; they do not require it.

94.3 Exit Boundary (XB)
94.3.1 Definition

An Exit Boundary is a price level or zone that forces exposure reduction or closure.

Exit Boundaries are mandatory constraints, not suggestions.

94.3.2 Exit Boundary Types

Exit Boundaries include:

Structural invalidation level

Opposing liquidity region

Historical high-velocity rejection zone

Prior liquidation cluster

Memory conflict escalation zone

Risk-derived liquidation proximity boundary

An Exit Boundary may be:

Hard (must close)

Soft (must reduce)

94.3.3 Mandatory Exit Rule

If price reaches an Exit Boundary:

HOLD is forbidden

OPEN is forbidden

Only REDUCE or CLOSE are allowed

Failure to act is a violation.

94.4 Partial Exit Zones (PEZ)
94.4.1 Definition

A Partial Exit Zone is a region where exposure may be reduced, but full exit is not mandatory.

Used to manage:

Liquidity reversion risk

Known historical reaction zones

Memory saturation areas

94.4.2 Partial vs Full Exit Decision

The system MUST NOT encode:

“This zone means partial”

“This zone means full”

Instead:

The zone permits REDUCE

Risk invariants decide whether CLOSE is required

This preserves flexibility without ambiguity.

94.5 Zone Conflict Resolution

If zones overlap:

Priority order:

Exit Boundary

Partial Exit Zone

Entry Zone

Exit always dominates entry.

94.6 Zone Expiry & Invalidity

Zones are not eternal.

A zone becomes invalid if:

Fully traversed without reaction

Structurally broken

Re-tested beyond tolerance

Superseded by stronger structural event

Invalid zones must be removed from consideration.

94.7 Zones vs Timeframes

Zones are timeframe-agnostic.

Weekly, daily, 4H, 15m are:

Sources of structure

Not execution permissions

Zones are normalized into the execution timeframe.

94.8 What Zones Must NOT Contain

Zones must never include:

Directional bias language

Probability

Confidence

Expected reaction

Narrative justification

Zones define where, not what will happen.

94.9 Summary

Entry Zones allow opening exposure

Exit Boundaries force reduction or closure

Partial Exit Zones allow exposure management

Zones are spatial, not temporal

Zones do not predict, they constrain

You do not enter because price moves.
You enter because price enters a zone.

95. Position–Exposure Invariant (Per-Symbol)

Invariant Name: Single-Symbol Exposure Coherence

Statement (Non-Negotiable):
At any point in time, total effective exposure per symbol must be coherent, bounded, and unambiguous.
A symbol may not simultaneously contribute to risk in conflicting directions, magnitudes, or intents.

95.1 Definition of Effective Exposure

For a given symbol S, define:

Direction(S): {LONG, SHORT, NONE}

Notional(S): Absolute notional size currently exposed

Leverage(S): Applied leverage (implicit or explicit)

Liquidation Distance(S): Distance from current price to liquidation price

Risk(S): Maximum loss at stop or forced exit (in account terms)

Effective Exposure(S) is the tuple:

E(S) = { Direction, Notional, Leverage, Risk, Liquidation Distance }


At all times, E(S) must satisfy all downstream invariants.

95.2 One-Direction Rule (Reinforced)

For any symbol S:

There may be at most one active directional exposure

LONG and SHORT exposure may not coexist

Hedged positions (long + short same symbol) are explicitly forbidden

If a condition arises that would imply opposite exposure:

Mandatory sequence:
CLOSE existing position → confirm flat → only then consider new exposure

No overlap, no transition exposure, no netting logic.

95.3 Exposure Boundedness

For each symbol S, enforce hard bounds:

Max Notional(S) ≤ Symbol-specific cap

Max Risk(S) ≤ Fixed % of account (e.g., 1% or architect-defined)

Max Leverage(S) constrained by liquidation-distance invariant (see §96)

If any bound would be exceeded by:

an ADD

a scale-in

a leverage change

→ the action is invalid and rejected

95.4 Exposure Monotonicity Under Risk

Once a position is open:

Exposure may increase only if:

Liquidation distance does not decrease

Absolute risk does not increase beyond cap

Otherwise:

Only REDUCE or CLOSE mandates are permitted

This prevents “doubling down” into higher fragility.

95.5 Exposure Collapse Conditions

The following conditions force exposure reduction, regardless of strategy intent:

Liquidation distance falls below minimum safe threshold

Volatility expansion invalidates initial sizing assumptions

Margin buffer drops below safety floor

External constraints (exchange, funding, risk limits) tighten

Hierarchy:

FORCE_REDUCE > REDUCE > HOLD > ADD


ADD is automatically disabled under any collapse condition.

95.6 Flat State Is Special

When Direction(S) = NONE:

No exposure exists

No liquidation risk exists

No memory, narrative, or intent is carried forward by default

Re-entry must be justified by fresh conditions, not by prior position state.

95.7 Rationale (Why This Exists)

This invariant ensures:

No hidden leverage

No accidental hedging

No exposure ambiguity

No strategy-driven override of risk reality

It converts “position per symbol” from a guideline into a provable constraint.

96. Liquidation Distance & Leverage Invariant

Invariant Name: Non-Negotiable Liquidation Safety

Statement (Non-Negotiable):
A position must never be allowed to exist if its liquidation distance violates predefined safety margins.
Leverage is not a free parameter — it is derived, constrained, and continuously revalidated by liquidation risk.

96.1 Core Principle

Leverage is subordinate to liquidation distance.
Any leverage configuration that produces an unsafe liquidation profile is invalid regardless of strategy confidence, signal strength, or historical edge.

No position is “correct enough” to justify fragility.

96.2 Definitions

For a given position P on symbol S:

Entry Price (E)

Current Price (C)

Liquidation Price (L)

Liquidation Distance (LD)

LD = |C − L| / C


Stop Distance (SD)

SD = |C − Stop| / C


Maintenance Margin Buffer (MMB)
Exchange-defined margin safety buffer

Effective Leverage (Lev)
Derived from notional / margin, not user intent

96.3 Minimum Liquidation Distance Requirement

At all times:

LD ≥ K × SD


Where:

K ≥ 2.0 (architect-defined, conservative default)

Meaning:

Liquidation must be at least twice as far as the stop

Liquidation may never sit inside the stop-loss envelope

If violated:
→ Position is invalid and must be reduced or closed immediately

96.4 Absolute Liquidation Floor

Regardless of stop placement:

LD ≥ LD_min


Where:

LD_min is a hard floor (e.g., 3–5% depending on instrument volatility)

If price action compresses LD below LD_min due to:

volatility expansion

funding shifts

margin rule changes

price movement against position

→ FORCE_REDUCE is triggered

96.5 Leverage Is a Derived Variable

Leverage may not be directly chosen.

Instead:

Lev_max = f(LD_min, volatility, margin rules)


Allowed leverage is computed such that:

Worst-case liquidation remains outside LD_min

Sudden volatility spikes do not instantly collapse margin

Funding or fees cannot push liquidation inside SD

Any manual leverage request is treated as:

a proposal, not a command

If proposed leverage violates invariant:
→ leverage is clamped downward or rejected

96.6 Add / Scale-In Restrictions

Scaling into a position is allowed only if all are true:

New average entry does not reduce LD

New leverage does not increase

Aggregate risk remains within cap

Stop remains valid and unchanged or improved

If adding reduces liquidation distance:
→ ADD is forbidden
→ only HOLD, REDUCE, or CLOSE are permitted

96.7 Volatility-Aware Revalidation

Liquidation distance must be revalidated when:

ATR / realized volatility expands

Spread widens abnormally

Funding rate spikes

Order book thins

Exchange margin parameters update

Revalidation outcomes:

Condition	Action
LD stable	No change
LD compressed	Reduce
LD < LD_min	Force reduce
LD inside SD	Immediate close
96.8 Liquidation Is Treated as System Failure

Liquidation is not an acceptable outcome.

A liquidation event implies:

Risk invariant breach

Leverage miscalculation

Or volatility misestimation

Therefore:

Liquidation is classified as fatal execution failure

System must enter post-mortem mode

No automatic re-entry permitted

96.9 Rationale

This invariant exists to ensure:

Risk is bounded before the trade, not explained after

Stops remain meaningful

Leverage never outruns reality

No position can silently drift into fragility

In short:

If a position can be liquidated, it was oversized.

97. Forced Reduction & Emergency Exit Hierarchy

Invariant Name: Capital Preservation Supremacy

Statement (Non-Negotiable):
When multiple exit drivers are simultaneously valid, the system must follow a strict, deterministic hierarchy.
No discretionary arbitration, no signal “confidence,” no narrative override.

Risk collapse always dominates strategy intent.

97.1 Core Principle

All exits are not equal.

Some exits express intent (targets, zones, narratives).
Others express danger (liquidation compression, volatility shock, margin stress).

When danger appears, intent is void.

97.2 Exit Driver Categories

Every exit condition must belong to exactly one category:

Category A — Fatal Risk (Immediate)

Non-recoverable threats to capital.

Liquidation distance < LD_min

Liquidation inside stop envelope

Margin requirement jump

Exchange constraint change

Funding spike threatening margin

Order book vacuum near price

Sudden volatility expansion beyond modeled bounds

Action: FORCE_CLOSE
Latency: Immediate
Overrides: All other logic

Category B — Structural Risk (Urgent)

Capital still safe, but structure is degrading.

Volatility expansion compressing LD toward limit

Stop distance widening due to spread

ATR expansion invalidating sizing

Partial correlation exposure spike

Multi-symbol drawdown alignment

Action: FORCE_REDUCE
Latency: Immediate
Overrides: Targets, narratives, liquidity logic

Category C — Liquidity / Market Structure

Opportunity-driven exits.

Approaching prior liquidation clusters

Historical stop-hunt zones

High-velocity rejection regions

Known absorption zones

Prior liquidity cascades

Action: PARTIAL_EXIT or FULL_EXIT
Latency: Conditional
Overrides: Targets, but not Category A/B

Category D — Strategic / Intent

Planned exits.

Target hits

Time-based exits

Narrative invalidation

Session boundaries

Action: EXIT or REDUCE
Latency: Planned
Overrides: None

97.3 Absolute Exit Priority Order

When multiple exit conditions trigger simultaneously:

Category A  → Category B → Category C → Category D


Lower categories are silenced when higher ones are active.

Example:

Liquidity zone reached (C)

Liquidation distance compressing (B)

→ B wins
→ Reduce immediately
→ Liquidity logic ignored

97.4 Partial vs Full Exit Arbitration (Category C Only)

Liquidity-based exits may choose between:

PARTIAL_EXIT

FULL_EXIT

But only if:

No Category A or B condition exists

Liquidation distance remains safe after partial exit

Remaining position remains valid under all invariants

If ambiguity exists:
→ Default to FULL_EXIT

No “hopeful partials.”

97.5 Emergency Reduction Ladder

When FORCE_REDUCE is triggered:

Reduction must occur in steps, not discretion:

Reduce to restore LD ≥ K × SD

Reduce to restore LD ≥ LD_min

Reduce to restore volatility envelope

If still invalid → FORCE_CLOSE

Each step must be validated before proceeding.

97.6 No Delayed Exits

Once a forced exit is triggered:

No waiting for candle close

No confirmation logic

No debounce timers

No “next tick” grace

Latency = execution latency only.

97.7 Exit Atomicity Rule

Exit actions are atomic:

A forced exit cannot be combined with:

scale-ins

hedge attempts

offsetting positions

counter-trades

Exit first.
Re-evaluate later.

97.8 Post-Emergency Cooldown

After any Category A or B exit:

Symbol enters cooldown

No re-entry allowed for N bars / time window

Cooldown duration ≥ original holding horizon

Prevents revenge trades and structural blindness.

97.9 Rationale

This hierarchy ensures:

Capital survival dominates narrative elegance

Liquidity logic never masks fragility

Partial exits are privileges, not rights

The system behaves deterministically under stress

In plain terms:

If risk is screaming, the system does not negotiate.

98. Exposure Correlation & Cross-Symbol Risk Invariant

Invariant Name: Single-Cause, Multi-Loss Prohibition

Statement (Binding):
The system must never allow multiple open positions whose losses can be caused by the same underlying market impulse beyond a strictly bounded exposure budget.

Correlation is treated as risk multiplication, not diversification.

98.1 Core Principle

Two positions are unsafe together if:

One market move can damage both at the same time.

This applies regardless of symbol, direction, strategy, or narrative.

98.2 Correlation Is Structural, Not Statistical

The system must not rely on rolling correlations alone.

Correlation sources include:

A. Instrumental Correlation

Same base asset (BTCUSDT, BTCUSD, BTC perpetuals)

Spot + derivatives on same asset

Options + underlying

B. Directional Correlation

Multiple longs or shorts sensitive to the same impulse

Opposing directions that still lose together (e.g., funding spike, volatility crush)

C. Liquidity Correlation

Shared liquidation zones

Shared stop-hunt regions

Shared funding / OI sensitivity

Shared order-book depth collapse risk

D. Volatility Correlation

Assets that expand volatility simultaneously

High-beta assets reacting to a common volatility shock

E. Narrative / Catalyst Correlation

Same macro driver (e.g., BTC dominance move)

Same scheduled risk (funding window, session open)

Same regime (risk-on / risk-off)

If any one category overlaps meaningfully, correlation exists.

98.3 Correlated Exposure Budget

The system must define a Global Correlated Risk Budget (GCRB).

Example form (conceptual):

Σ (risk_i × correlation_weight_i) ≤ MAX_CORRELATED_RISK


Where:

risk_i = % account risk of position i

correlation_weight_i ∈ [0, 1]

Fully correlated positions → weight = 1

Weakly correlated → fractional weight

Hard Rule:
If correlation_weight ≈ 1, risks add linearly, not independently.

98.4 Absolute Prohibitions

The system must reject the following outright:

Two positions whose liquidation zones overlap materially

Two positions whose forced exit would be triggered by the same volatility shock

Two positions whose stop-losses sit inside the same liquidity sweep region

Multiple positions whose margin risk rises together under the same funding or spread event

No partial sizing workaround is allowed unless explicitly permitted by GCRB.

98.5 Correlation Escalation Under Stress

Correlation is state-dependent.

When any of the following occur, correlation weights must increase automatically:

Volatility expansion

Liquidity thinning

Funding divergence

Sudden OI changes

Regime transitions (range → trend, calm → impulsive)

During stress:

Previously “acceptable” correlation becomes forbidden

Positions may require forced reduction even without price movement

98.6 Cross-Symbol Exit Synchronization

If one position enters:

Category A (Fatal Risk)

Category B (Structural Risk)

Then all correlated positions must be evaluated immediately.

Possible outcomes:

Forced reduction across symbols

Full liquidation cascade prevention

Portfolio-level drawdown containment

No symbol is treated in isolation.

98.7 Correlation vs Confidence

Signal quality, narrative alignment, or “high conviction” never justify violating correlation limits.

Confidence does not reduce correlation.
Correlation does not care about thesis strength.

98.8 Correlation Blindness Ban

The system must never:

Assume diversification because symbols differ

Assume hedge because directions differ

Assume safety because entries differ in time

Assume independence because correlation was low historically

Only current structural linkage matters.

98.9 Forced Simplification Rule

When correlation assessment is ambiguous:

Assume worst-case correlation

Reduce exposure

Prefer fewer positions over finer allocation

Complex portfolios fail under stress.
Simple ones survive.

98.10 Summary (Non-Negotiable)

Correlation multiplies risk

Shared failure modes are forbidden

Stress increases correlation

Cross-symbol exits must synchronize

Ambiguity resolves toward reduction

One impulse must never be allowed to destroy multiple positions.

99. Position Lifecycle State Machine (Formal)

Purpose:
Define an explicit, finite, non-ambiguous lifecycle for every position so that no position can exist in an undefined, overlapping, or contradictory state.
All execution, risk, and mandate logic must reference this state machine—not inferred behavior.

99.1 Core Principle

A position is always in exactly one state.

No soft states.
No implicit transitions.
No “partially open”, “kind of closed”, or “mentally exited”.

If a state cannot be named, it cannot exist.

99.2 Canonical Position States
S0 — FLAT

No position exists for the symbol

No exposure

No margin usage

No lifecycle memory retained (except closed trade record)

Entry condition:

System initialization

After FINALIZED

S1 — ENTRY_PENDING

Intent to open a position exists

Conditions validated

Order not yet confirmed filled

Allowed actions:

Cancel entry

Modify order parameters

Abort due to risk constraint

Forbidden:

Risk calculations assuming fill

Partial exits (no position yet)

Transitions:

→ S2 (on fill)

→ S0 (on cancellation / invalidation)

S2 — OPEN

Position is live

Full size established

Stop-loss and liquidation parameters defined

Risk fully accounted for

Mandatory invariants:

Stop-loss exists

Liquidation distance evaluated

Correlated exposure rechecked

Transitions:

→ S3 (partial reduction)

→ S4 (exit intent)

→ S6 (forced exit)

→ S7 (liquidation — exceptional)

S3 — PARTIALLY_REDUCED

Position still open

Size reduced intentionally

Risk profile has changed

Triggers:

Liquidity zone interaction

Historical liquidation region

Absorption / opposing flow

Exposure rebalancing

Rules:

Partial reduction does not imply weakness

Multiple partial reductions allowed

Each reduction must revalidate remaining risk

Transitions:

→ S2 (if re-adding is explicitly allowed)

→ S4 (exit intent)

→ S6 (forced exit)

S4 — EXIT_INTENT

Decision to fully close has been made

Execution may be staged (limit, scale, wait-for-confirmation)

Key rule:
Once in EXIT_INTENT, no new adds are permitted.

Transitions:

→ S5 (closed)

→ S6 (forced exit override)

S5 — CLOSED

Position fully exited

PnL realized

No market exposure remains

Actions:

Record trade outcome

Update memory (zones, reactions, absorption)

Release risk budget

Transition:

→ S0 (after bookkeeping)

S6 — FORCED_EXIT

Position closed due to invariant breach, not strategy choice

Triggers include:

Correlation violation

Margin risk escalation

Volatility regime breach

System-wide risk reduction

Observation failure (M6 dependency)

Rules:

Overrides all strategy logic

Must execute immediately

No re-entry allowed without full reset

Transition:

→ S5

S7 — LIQUIDATED (Terminal Failure State)

Position closed by exchange liquidation

Capital loss incurred

Rules:

Trading halts or degrades (policy-defined)

Mandatory post-mortem

Risk parameters must be reviewed before resuming

Transition:

→ S0 only after explicit system reset

99.3 Forbidden State Transitions

The following are illegal:

S0 → S3 (partial exit without position)

S1 → S3 (reduce before fill)

S3 → S1 (cannot “re-pend” entry)

S4 → S2 (cannot add after exit intent)

S5 → S2 (reopen without new entry cycle)

Any → Any without explicit transition trigger

99.4 State-Dependent Permissions Matrix
Action	Allowed States
Add size	S2 only
Reduce size	S2, S3
Cancel	S1
Exit fully	S2, S3, S4
Force exit	Any except S0
Risk recalculation	S1–S4
Correlation evaluation	S1–S4
Memory write	S5, S7
99.5 Partial Exit Clarification (Critical)

Partial exits do not imply:

Loss of conviction

Strategy failure

Trend reversal

They imply information update.

A position may:

Partially exit due to liquidity

Continue holding core exposure

Later fully exit or even re-add (if allowed)

State machine allows this without contradiction.

99.6 Position Identity Invariant

Each position has:

One symbol

One direction

One lifecycle

One state at a time

Multiple positions per symbol are not allowed unless explicitly modeled as a composite position (advanced case).

99.7 Why This Matters

Without an explicit state machine:

Risk logic becomes inconsistent

Partial exits block valid futures

Forced exits become ambiguous

Mandates conflict silently

With this:

Every action is valid or invalid by state

Conflicts are detectable

Automation becomes safe

99.8 Summary (Non-Negotiable)

Positions move through defined states

No state overlap

No implicit transitions

Partial exits are first-class citizens

Forced exits override everything

If you cannot name the state, you cannot act.

100. Mandate Types & Arbitration (Multi-Response Framework)

Purpose:
Define how multiple mandates (rules, reactions, safeguards) can coexist, trigger simultaneously, and be resolved without contradiction, override ambiguity, or hidden priority assumptions.

This answers your earlier question directly:

Yes — multiple mandates are allowed.
But only if arbitration is explicit and deterministic.

100.1 Core Principle

A mandate is not a strategy.
A mandate is a conditional obligation:

If condition X is true, response Y must be considered.

Mandates:

Do not predict

Do not compete emotionally

Do not imply confidence

Only constrain or react

Multiple mandates may trigger at once.
Arbitration decides the outcome.

100.2 Why Multiple Mandates Are Necessary

Markets regularly present conflicting information:

Entry signal + liquidity wall ahead

Trend continuation + liquidation memory

Profit opportunity + exposure violation

Momentum + funding risk

Setup valid + macro event imminent

A single mandate system breaks under conflict.
A multi-mandate system absorbs conflict.

100.3 Canonical Mandate Categories

Mandates are grouped by intent, not timeframe.

A. Safety Mandates (Highest Authority)

Non-negotiable.
They protect system survival.

Examples:

Max exposure per symbol

Correlation limits

Liquidation distance threshold

Margin utilization cap

Observation FAILED → exit

Outcome:

Force exit

Block entry

Reduce size

Halt trading

B. Position Integrity Mandates

Ensure position logic remains coherent.

Examples:

One position per symbol

Opposite signal → close before reverse

No add after EXIT_INTENT

Stop-loss must exist

Leverage recalculation on size change

Outcome:

Block action

Convert intent (e.g. reverse → close)

C. Risk Optimization Mandates

Adjust exposure without negating thesis.

Examples:

Partial exit at historical liquidation zone

Reduce size near known stop-hunt region

De-risk on volatility expansion

Scale out on liquidity absorption

Outcome:

Partial reduction

Stop tightening

Size normalization

D. Opportunity Mandates

Allow action but never force it.

Examples:

Narrative confirmation

Break of structure

Entry zone activation

Retest validation

Outcome:

Permit entry

Permit add

Permit hold

E. Memory-Based Mandates

Derived from historical interaction, not indicators.

Examples:

Prior liquidation cascade in region

Previous high-velocity rejection

Known absorption zone

Past failed breakout memory

Outcome:

Bias exit vs partial

Bias conservative sizing

Bias faster profit taking

100.4 Mandate Trigger Model

Each mandate produces a proposal, not an action.

Example:

Mandate A: “Reduce risk immediately”

Mandate B: “Hold core position”

Mandate C: “Exit fully”

These proposals enter arbitration.

100.5 Arbitration Hierarchy (Non-Optional)

Mandates are resolved top-down:

Safety Mandates

Position Integrity

Risk Optimization

Memory-Based

Opportunity

A lower-tier mandate cannot override a higher-tier one.

Example:

Opportunity says enter

Safety says exposure exceeded
→ No entry

100.6 Arbitration Outcomes (Finite Set)

After arbitration, only one of the following is allowed:

BLOCK — no action

EXIT_FULL

EXIT_PARTIAL

HOLD

ENTER

ADD

REDUCE

HALT

No blended actions.
No vague “manage”.

100.7 Partial vs Full Exit Resolution

This directly addresses your concern.

When liquidity zones suggest exit, arbitration decides:

Full Exit favored when:

Safety mandate triggered

Opposing structure confirmed

Correlation breach

Liquidation risk increased

Narrative invalidated

Partial Exit favored when:

Thesis intact

Memory suggests reaction, not reversal

Absorption present

Liquidity zone likely temporary

Exposure still acceptable

Key:
Liquidity zones do not imply full exit by default.
They introduce a mandate, not a command.

100.8 Opposing Signals Handling

If a valid opposite-direction setup appears:

Rule:

Must close existing position first

No simultaneous long & short on same symbol

New entry requires fresh ENTRY_PENDING state

This avoids:

Hedge confusion

Net exposure ambiguity

Risk miscalculation

100.9 Mandates vs Strategy Logic

Strategy logic answers:

“Is this a good trade?”

Mandates answer:

“Are we allowed to act, and how?”

A great trade can still be blocked.
A mediocre trade can still be allowed.

This separation is intentional.

100.10 Why This Architecture Scales

Allows many ideas without chaos

Supports multiple response types

Handles conflict explicitly

Prevents silent overrides

Aligns perfectly with narrative trading:

If this → then that

Multiple scenarios, one action

100.11 Non-Negotiable Summary

Multiple mandates are allowed

Mandates propose, arbitration decides

Safety always wins

Partial exits are first-class

Liquidity ≠ mandatory full exit

One action per decision cycle

No hidden priorities

Mandates describe pressure.
Arbitration produces behavior.

100. Mandate Types & Arbitration (Multi-Response Framework)

Purpose:
Define how multiple mandates (rules, reactions, safeguards) can coexist, trigger simultaneously, and be resolved without contradiction, override ambiguity, or hidden priority assumptions.

This answers your earlier question directly:

Yes — multiple mandates are allowed.
But only if arbitration is explicit and deterministic.

100.1 Core Principle

A mandate is not a strategy.
A mandate is a conditional obligation:

If condition X is true, response Y must be considered.

Mandates:

Do not predict

Do not compete emotionally

Do not imply confidence

Only constrain or react

Multiple mandates may trigger at once.
Arbitration decides the outcome.

100.2 Why Multiple Mandates Are Necessary

Markets regularly present conflicting information:

Entry signal + liquidity wall ahead

Trend continuation + liquidation memory

Profit opportunity + exposure violation

Momentum + funding risk

Setup valid + macro event imminent

A single mandate system breaks under conflict.
A multi-mandate system absorbs conflict.

100.3 Canonical Mandate Categories

Mandates are grouped by intent, not timeframe.

A. Safety Mandates (Highest Authority)

Non-negotiable.
They protect system survival.

Examples:

Max exposure per symbol

Correlation limits

Liquidation distance threshold

Margin utilization cap

Observation FAILED → exit

Outcome:

Force exit

Block entry

Reduce size

Halt trading

B. Position Integrity Mandates

Ensure position logic remains coherent.

Examples:

One position per symbol

Opposite signal → close before reverse

No add after EXIT_INTENT

Stop-loss must exist

Leverage recalculation on size change

Outcome:

Block action

Convert intent (e.g. reverse → close)

C. Risk Optimization Mandates

Adjust exposure without negating thesis.

Examples:

Partial exit at historical liquidation zone

Reduce size near known stop-hunt region

De-risk on volatility expansion

Scale out on liquidity absorption

Outcome:

Partial reduction

Stop tightening

Size normalization

D. Opportunity Mandates

Allow action but never force it.

Examples:

Narrative confirmation

Break of structure

Entry zone activation

Retest validation

Outcome:

Permit entry

Permit add

Permit hold

E. Memory-Based Mandates

Derived from historical interaction, not indicators.

Examples:

Prior liquidation cascade in region

Previous high-velocity rejection

Known absorption zone

Past failed breakout memory

Outcome:

Bias exit vs partial

Bias conservative sizing

Bias faster profit taking

100.4 Mandate Trigger Model

Each mandate produces a proposal, not an action.

Example:

Mandate A: “Reduce risk immediately”

Mandate B: “Hold core position”

Mandate C: “Exit fully”

These proposals enter arbitration.

100.5 Arbitration Hierarchy (Non-Optional)

Mandates are resolved top-down:

Safety Mandates

Position Integrity

Risk Optimization

Memory-Based

Opportunity

A lower-tier mandate cannot override a higher-tier one.

Example:

Opportunity says enter

Safety says exposure exceeded
→ No entry

100.6 Arbitration Outcomes (Finite Set)

After arbitration, only one of the following is allowed:

BLOCK — no action

EXIT_FULL

EXIT_PARTIAL

HOLD

ENTER

ADD

REDUCE

HALT

No blended actions.
No vague “manage”.

100.7 Partial vs Full Exit Resolution

This directly addresses your concern.

When liquidity zones suggest exit, arbitration decides:

Full Exit favored when:

Safety mandate triggered

Opposing structure confirmed

Correlation breach

Liquidation risk increased

Narrative invalidated

Partial Exit favored when:

Thesis intact

Memory suggests reaction, not reversal

Absorption present

Liquidity zone likely temporary

Exposure still acceptable

Key:
Liquidity zones do not imply full exit by default.
They introduce a mandate, not a command.

100.8 Opposing Signals Handling

If a valid opposite-direction setup appears:

Rule:

Must close existing position first

No simultaneous long & short on same symbol

New entry requires fresh ENTRY_PENDING state

This avoids:

Hedge confusion

Net exposure ambiguity

Risk miscalculation

100.9 Mandates vs Strategy Logic

Strategy logic answers:

“Is this a good trade?”

Mandates answer:

“Are we allowed to act, and how?”

A great trade can still be blocked.
A mediocre trade can still be allowed.

This separation is intentional.

100.10 Why This Architecture Scales

Allows many ideas without chaos

Supports multiple response types

Handles conflict explicitly

Prevents silent overrides

Aligns perfectly with narrative trading:

If this → then that

Multiple scenarios, one action

100.11 Non-Negotiable Summary

Multiple mandates are allowed

Mandates propose, arbitration decides

Safety always wins

Partial exits are first-class

Liquidity ≠ mandatory full exit

One action per decision cycle

No hidden priorities

Mandates describe pressure.
Arbitration produces behavior.

102. Liquidity Interaction Taxonomy (Canonical, Non-Interpretive)

Purpose:
Define a strict, enumerable set of liquidity interaction primitives that describe how price behaves relative to historical and present liquidity, without implying intent, prediction, or outcome.

This taxonomy is descriptive, not evaluative.
It feeds mandates; it does not decide actions.

102.1 First Principle

Liquidity is not:

a signal

a trade trigger

a guarantee of reversal or continuation

Liquidity is:

A structural property of price regions created by past participation, stops, and flow imbalance.

Interaction with liquidity is observable.
Interpretation is forbidden at this layer.

102.2 Liquidity Objects (Static Memory)

These are historical constructs derived from past price behavior.

102.2.1 Stop Cluster

A price region where:

Multiple swing highs/lows align

Equal highs / equal lows exist

Compression precedes expansion

Properties:

Has no direction

Can be consumed, respected, or ignored

Exists independently of current intent

102.2.2 Liquidation Cluster (Historical)

A region where:

Forced exits occurred previously

High velocity candles + volume spike

Often leaves long wicks or gaps

Properties:

Encodes forced participation, not voluntary trade

Does not imply repetition

Acts as memory, not magnet

102.2.3 High-Velocity Region

A price span characterized by:

Rapid traversal

Minimal overlap

Large candles relative to baseline

Properties:

Low historical agreement

Often revisited

Interaction can stall or accelerate price

102.2.4 Volume Node / Void

Node: Price accepted for extended time (high volume)

Void: Price traversed quickly (low volume)

Properties:

Nodes imply consensus

Voids imply inefficiency

Neither implies direction

102.3 Liquidity States (Dynamic)

These describe current interaction, not structure.

102.3.1 Approaching Liquidity

Price is moving toward a known liquidity object.

No assertion allowed about:

capture

reversal

acceleration

102.3.2 Engaging Liquidity

Price enters the liquidity region.

Observable only:

speed change

volatility change

volume response

102.3.3 Consuming Liquidity

Liquidity object is traversed fully.

Indicators:

Clean pass-through

Stops taken

Minimal rejection

No implication of continuation.

102.3.4 Rejecting Liquidity

Price enters and exits liquidity region without traversal.

Indicators:

Wicks

Failed follow-through

Compression after probe

No implication of reversal.

102.3.5 Stalling at Liquidity

Price remains within region.

Indicators:

Range compression

Repeated tests

Reduced momentum

No implication of outcome.

102.4 Composite Liquidity Phenomena
102.4.1 Liquidity Cascade

Sequential interaction with multiple adjacent liquidity objects.

Observed as:

Stepwise acceleration

Repeated stop consumption

This is a description, not a signal.

102.4.2 Liquidity Overlap

Multiple liquidity types co-located:

Stop cluster + liquidation memory

Volume node inside velocity region

Higher informational density, not higher probability.

102.4.3 Liquidity Vacuum

Absence of nearby historical liquidity.

Price may:

Drift

Accelerate

Chop

Outcome unspecified.

102.5 Absorption vs Exhaustion (Non-Predictive)

These terms describe flow response, not intent.

Absorption

Price movement slows

Volume persists

Progress halts

No assumption about direction.

Exhaustion

Large impulse

Immediate loss of follow-through

Decreasing participation

No assumption of reversal.

102.6 Liquidity Memory Decay

Liquidity relevance decays based on:

Time elapsed

Number of interactions

Structural breaks

Regime changes

Liquidity is not permanent.

102.7 What This Taxonomy Does Not Do

Explicitly forbidden conclusions:

“Liquidity must be taken”

“Stops guarantee reversal”

“This zone is strong”

“This zone will hold”

Those belong nowhere in this system.

102.8 Relationship to Partial & Full Exits

Liquidity interaction permits:

partial exit consideration

full exit consideration

no action

It never mandates any of them alone.

Mandates decide.
Risk arithmetic filters.
Liquidity only describes context.

102.9 Output Form (Machine-Usable)

Liquidity interaction is emitted as:

Type (stop, liquidation, velocity, node, void)

State (approaching, engaging, consuming, rejecting, stalling)

Recency

Overlap count

Velocity delta

Volatility delta

No boolean “signal” flags.

102.10 Summary

Liquidity is memory, not prophecy

Interaction is observable, intent is not

Descriptions feed mandates

Mandates do not assume outcomes

Risk arithmetic still governs action legality

Liquidity tells you where price remembers.
It never tells you what price will do.

103. Market Memory Encoding & Decay (Canonical, Non-Interpretive)

Purpose:
Define how historical market events are encoded as memory, how that memory persists, and how it decays over time and interaction, without implying prediction, intent, or trade direction.

This section formalizes what the system remembers, how it forgets, and what memory may be queried by mandates.

103.1 First Principle

Market memory is descriptive residue, not foresight.

The system does not remember:

why something happened

who caused it

what should happen next

It remembers only:

that something happened, where it happened, and how often it has been interacted with since.

103.2 What Qualifies as Market Memory

An event becomes memory only if it left observable structure.

103.2.1 Memory-Eligible Events

An event is memory-eligible if it satisfies at least one:

Abnormal price velocity

Abnormal traded volume

Forced participation (liquidations)

Structural break (swing high/low violation)

Extended acceptance (volume node)

If none apply → no memory is created.

103.3 Memory Object Definition

Each memory object contains only factual fields:

Field	Description
price_range	[low, high] bounds
timestamp_created	when memory formed
event_type	velocity, liquidation, structure, acceptance
interaction_count	number of subsequent touches
last_interaction_time	last observed interaction
initial_intensity	normalized measure at creation
current_weight	decayed value

No semantic labels allowed.

103.4 Memory Encoding Classes
103.4.1 Velocity Memory

Created when:

Price traverses a region unusually fast

Encodes:

inefficiency

lack of agreement

103.4.2 Liquidation Memory

Created when:

Forced exits detected

High liquidation concentration

Encodes:

stress participation

fragility under leverage

103.4.3 Structural Memory

Created when:

Swing high/low broken

Range boundary violated

Encodes:

prior consensus invalidation

103.4.4 Acceptance Memory

Created when:

Price remains within region for extended time

Volume accumulates

Encodes:

agreement, not direction

103.5 Memory Interaction Types

Each interaction updates memory, never confirms a hypothesis.

Interaction	Effect
First Touch	Validates memory persistence
Partial Traverse	Increments interaction_count
Full Traverse	Accelerates decay
Rejection	Weak decay
Stagnation	Slow decay

No interaction implies prediction.

103.6 Memory Decay Model

Memory decays along three independent axes:

103.6.1 Time Decay

Older memory loses relevance regardless of interaction.

Example:

exponential or piecewise decay

time-only, no inference

103.6.2 Interaction Decay

Each interaction weakens memory.

untouched memory persists longer

repeatedly traversed memory fades faster

103.6.3 Regime Decay

Structural regime changes accelerate decay:

volatility regime shift

session change

macro event boundary

103.7 Memory Invalidators (Hard Reset)

Memory is invalidated (removed) if:

price remains far outside range for extended duration

structural regime changes (e.g., volatility x-multiple)

explicit system reset (backtest boundary)

Invalidation is not interpretation.

103.8 Memory Is Non-Directional

Memory does not encode:

support

resistance

bullishness

bearishness

Memory only answers:

“Has this region mattered before, and how much of that memory remains?”

103.9 Memory Query Interface (For Mandates)

Mandates may ask:

Are we inside a memory region?

What type(s) of memory exist here?

What is the current memory weight?

How many interactions occurred?

When was the last interaction?

Mandates may not ask:

“Will this hold?”

“Is this strong?”

“Is this a reversal zone?”

103.10 Relationship to Partial / Full Exits

Memory permits exit consideration, it never enforces it.

Examples:

High-weight memory + engagement → exit consideration allowed

Low-weight memory + traversal → no constraint

Decision authority remains with:

Position invariants

Risk arithmetic

Mandate logic

103.11 What This Layer Refuses to Do

Explicitly forbidden:

ranking memory as “good/bad”

converting memory into signals

assuming repetition

implying inevitability

103.12 Summary

Memory is factual residue

Decay is mandatory

Interaction weakens memory

No direction, no intent, no prediction

Mandates consume memory, not beliefs

The market remembers.
The system remembers that the market remembered.
Nothing more.

104. Narrative → Mandate Translation Layer (Non-Interpretive)

Purpose:
Define how descriptive observations and memory are converted into actionable mandates without prediction, bias, or semantic interpretation.

This layer is the only bridge between:

what is observed (facts, memory, structure), and

what is permitted to be done (enter, reduce, exit, block).

It does not decide outcomes.
It defines conditional permissions.

104.1 First Principle

A mandate is not a trade idea.
A mandate is a conditional allowance.

“If condition X is observed, then action Y is allowed.”

Nothing more.

104.2 What a Narrative Is (Formally)

A narrative is a set of mutually exclusive condition branches derived from observation state.

Narrative = { branch₁, branch₂, … branchₙ }

Each branch is:

conditionally exclusive

order-independent

non-predictive

Example (abstract, non-directional):

Branch A: structural break observed

Branch B: structure holds

Branch C: memory interaction without break

No branch is “preferred”.

104.3 What a Mandate Is

A mandate is a rule object with four components:

Component	Meaning
conditions	Observable facts only
allowed_actions	What may be done
forbidden_actions	What must not be done
scope	Symbol / position / account

Mandates never contain intent.

104.4 Narrative → Mandate Mapping

Each narrative branch maps to one or more mandates.

Example (Abstract)

Narrative Branch:

Price enters high-weight memory region

Ongoing absorption detected

Existing long position open

Produces Mandate:

allowed_actions: reduce, exit

forbidden_actions: add

scope: existing position only

No direction assumed.
No outcome implied.

104.5 Mandate Types (Canonical)

Mandates are categorized by what they constrain, not why.

104.5.1 Entry Mandates

Permit:

open position

open only if no position exists

open only after close

Block:

duplicate entries

pyramiding (unless explicitly allowed)

104.5.2 Reduction Mandates

Permit:

partial exit

size reduction

exposure trimming

Block:

adding exposure

reversing without close

Reduction is first-class, not derivative.

104.5.3 Exit Mandates

Permit:

full position close

forced flattening

Exit mandates override all others.

104.5.4 Block Mandates

Explicitly forbid actions:

no entry

no add

no reverse

no execution at all

Used for:

risk violations

invariant breaches

undefined state

104.6 Mandate Precedence Rules

When multiple mandates exist:

Exit > Reduce > Block > Entry

Tighter scope overrides broader scope

More restrictive overrides permissive

If conflict remains → no action allowed.

Silence beats ambiguity.

104.7 Mandate Scope

Every mandate declares scope:

symbol

position

account

session

Example:

“Reduce BTCUSDT position”

“Block all entries account-wide”

No implicit scope allowed.

104.8 Temporal Validity

Mandates are ephemeral.

Each mandate has:

created_at

expires_at or invalidation condition

If expired → ignored.

No mandate persists by default.

104.9 Relationship to Memory (Section 103)

Memory:

enables mandates

never triggers them

High-weight memory may:

allow reduce / exit mandates

forbid adds

Low-weight memory may:

produce no mandate

Memory never commands.

104.10 Relationship to Risk Invariants

Risk invariants override mandates.

If mandate allows entry but risk invariant forbids → entry blocked.

Mandates cannot violate:

max positions

leverage constraints

liquidation thresholds

104.11 What This Layer Explicitly Refuses

Forbidden in this layer:

signal generation

confidence scoring

probability estimation

“setup quality”

trade rationale

This layer translates facts → permissions, nothing else.

104.12 Summary

Narratives describe what is happening

Mandates define what is allowed

No prediction

No preference

No bias

Reduction is first-class

Exit always wins

Narrative says: “Here is the situation.”
Mandate says: “Here is what you may do.”


105. Position Lifecycle Finite State Machine (FSM)

Purpose:
Define the complete, explicit lifecycle of a position such that:

no implicit transitions exist

every action is state-validated

risk and mandate constraints are enforced structurally

execution cannot “invent” behavior

This FSM is direction-agnostic, strategy-agnostic, and instrument-agnostic.

105.1 First Principle

A position is not a belief.
A position is a managed exposure object.

It must always be in exactly one state.

105.2 Canonical Position States
105.2.1 State Enumeration
FLAT
ENTERING
OPEN
REDUCING
EXITING
CLOSED
INVALID


No other states are permitted.

105.3 State Definitions (Exact)
FLAT

No position exists for symbol

Exposure = 0

Margin = 0

No PnL tracking active

Allowed transitions:

→ ENTERING

ENTERING

Entry order(s) submitted

Position not yet confirmed open

Partial fills possible

Allowed transitions:

→ OPEN (any fill > 0)

→ FLAT (entry cancelled / rejected)

→ INVALID (execution anomaly)

Forbidden:

reduce

reverse

exit (nothing to exit yet)

OPEN

Position exists

Exposure > 0

PnL tracked

Risk continuously evaluated

Allowed transitions:

→ REDUCING

→ EXITING

→ INVALID

Forbidden:

ENTERING again (no pyramiding unless explicitly allowed)

reverse without EXITING

REDUCING

Partial exit(s) in progress

Exposure decreasing but > 0

Allowed transitions:

→ OPEN (after reduction completes)

→ EXITING (escalation)

→ INVALID

Forbidden:

add exposure

reverse

Reduction is not an exit — it is a distinct state.

EXITING

Full exit order(s) submitted

Goal: exposure → 0

Allowed transitions:

→ CLOSED

→ INVALID

Forbidden:

add

reduce (already exiting)

reverse

Exit overrides everything.

CLOSED

Position fully closed

Exposure = 0

Final PnL realized

Allowed transitions:

→ FLAT (cleanup / archive)

No execution allowed here.

INVALID

Execution inconsistency

Broker anomaly

Risk invariant violated

Undefined partial state

Allowed transitions:

→ EXITING (forced liquidation)

→ CLOSED (if already flat)

INVALID is terminal unless forcibly resolved.

105.4 Mandatory State Invariants
State	Invariant
FLAT	exposure == 0
ENTERING	entry_orders > 0
OPEN	exposure > 0
REDUCING	exposure decreasing
EXITING	exit_orders > 0
CLOSED	exposure == 0
INVALID	invariants violated

Violations → immediate INVALID.

105.5 Transition Guard Conditions

Every transition requires three approvals:

State legality (FSM rules)

Mandate permission

Risk invariant compliance

If any fail → transition denied.

105.6 Interaction With Mandates (Section 104)

Mandates do not move states.
They permit transitions.

Examples:

Mandate	Allowed Transition
Entry mandate	FLAT → ENTERING
Reduce mandate	OPEN → REDUCING
Exit mandate	OPEN/REDUCING → EXITING
Block mandate	none

If mandate expires → transition forbidden.

105.7 Reverse Position Rule (Critical)

Reversal is never a direct transition.

Reverse = EXITING → CLOSED → ENTERING

This enforces:

realized PnL

reset risk

clean state

No exceptions.

105.8 Partial Fill Handling

Partial fills do not change state arbitrarily.

Rules:

ENTERING → OPEN on first fill

REDUCING stays REDUCING until reduction complete

EXITING stays EXITING until exposure = 0

FSM state reflects intent, not fill granularity.

105.9 Failure Escalation Rules

Any of the following force → INVALID:

leverage invariant breach

liquidation proximity violation

execution mismatch (broker vs internal)

unexpected exposure increase

mandate conflict

INVALID must immediately escalate to EXITING if exposure > 0.

105.10 Why This FSM Matters

Without this FSM:

“add by accident” happens

reverse trades leak risk

partial exits blur logic

mandates become advisory instead of binding

With this FSM:

behavior is provable

testing is finite

failures are containable

105.11 Summary

One position = one state

Reduction is first-class

Exit dominates

Reverse is two-step

INVALID exists to prevent silent corruption

If a transition is not explicitly defined, it is forbidden.

106. Liquidation-Aware Leverage & Exposure Arithmetic

Purpose:
Define leverage and position sizing as risk-bounded arithmetic, not configuration.
Leverage is derived, not chosen.
Liquidation is structurally avoided, not reacted to.

This section binds position sizing, margin usage, liquidation distance, and exposure limits into one coherent invariant system.

106.1 First Principle

Leverage is not a knob. It is an outcome.

Any system that sets leverage directly is already broken.

106.2 Core Definitions (Non-Negotiable)
106.2.1 Exposure
exposure = position_size * entry_price

106.2.2 Account Equity
equity = balance + unrealized_pnl

106.2.3 Used Margin
used_margin = exposure / effective_leverage

106.2.4 Liquidation Price

Broker-defined, but always exists as a function:

liq_price = f(entry_price, leverage, maintenance_margin)


The system must not assume exact broker formula — only distance.

106.3 Liquidation Distance (Key Quantity)
106.3.1 Definition
liq_distance = |entry_price - liq_price| / entry_price


This is the only liquidation-relevant number that matters.

106.4 Hard Liquidation Invariant (Unbreakable)
liq_distance >= MIN_LIQ_BUFFER


Where:

MIN_LIQ_BUFFER = max(
    structural_volatility_buffer,
    execution_slippage_buffer,
    liquidation_spike_buffer
)


If violated → position is forbidden to open.

106.5 Leverage Derivation (Critical)

Leverage is computed after constraints:

max_exposure = equity * max_risk_fraction
effective_leverage = max_exposure / (position_size * entry_price)


Then validated against liquidation distance.

If leverage required > safe leverage → position size is reduced, not leverage increased.

106.6 Risk-First Position Sizing (Canonical)

Position size is derived from loss tolerance, not confidence.

max_loss = equity * risk_per_trade
position_size = max_loss / stop_distance


Then:

exposure computed

leverage inferred

liquidation distance checked

If liquidation buffer violated → reject trade, not resize stop.

106.7 Leverage Caps (Secondary, Not Primary)

Static caps exist only as absolute ceilings:

effective_leverage <= HARD_MAX_LEVERAGE


They do not authorize risk — they only prohibit stupidity.

106.8 Dynamic Leverage Compression (Mandatory)

Leverage must compress automatically when:

volatility increases

stop distance shrinks

liquidity degrades

funding spikes

liquidation cascades detected historically in region

This is achieved by:

increasing MIN_LIQ_BUFFER

increasing stop distance requirement

reducing max_exposure

Never by increasing leverage.

106.9 Partial Exit Interaction

After partial exit:

exposure ↓

used_margin ↓

liquidation price moves away

Invariant:
Partial exits may never increase liquidation proximity.

If they do → forbidden.

106.10 Reverse Position Safety Rule

Reverse trades must recompute leverage from scratch.

No carryover:

no margin reuse

no liquidation inheritance

no leverage continuity

EXIT → FLAT → recompute → ENTER

106.11 Liquidation Cascade Awareness (Derived Constraint)

If historical data indicates:

prior liquidation cascades in region

sharp historical velocity spikes

clustered forced exits

Then:

MIN_LIQ_BUFFER *= cascade_multiplier


This makes some trades structurally impossible, by design.

106.12 Emergency Exit Condition

If at any time:

liq_distance <= EMERGENCY_THRESHOLD


Then:

state → EXITING

mandate ignored

execution forced

Liquidation avoidance overrides all logic.

106.13 Forbidden Behaviors (Explicit)

❌ setting leverage directly

❌ increasing leverage to “improve R:R”

❌ shrinking stops to fit leverage

❌ holding positions near liquidation

❌ assuming broker liquidation formula stability

Any of these → INVALID state.

106.14 Why This Matters

Most systems die from:

leverage creep

silent liquidation risk

false safety from low position size

This framework ensures:

liquidation is mathematically unreachable

leverage adapts automatically

risk is invariant-driven

106.15 Summary

Leverage is derived, never chosen

Liquidation distance is the primary risk metric

Position size is loss-bounded

Partial exits must improve safety

Cascades raise the bar, not the size

If a trade can liquidate, it is already invalid.

106. Liquidation-Aware Leverage & Exposure Arithmetic

Purpose:
Define leverage and position sizing as risk-bounded arithmetic, not configuration.
Leverage is derived, not chosen.
Liquidation is structurally avoided, not reacted to.

This section binds position sizing, margin usage, liquidation distance, and exposure limits into one coherent invariant system.

106.1 First Principle

Leverage is not a knob. It is an outcome.

Any system that sets leverage directly is already broken.

106.2 Core Definitions (Non-Negotiable)
106.2.1 Exposure
exposure = position_size * entry_price

106.2.2 Account Equity
equity = balance + unrealized_pnl

106.2.3 Used Margin
used_margin = exposure / effective_leverage

106.2.4 Liquidation Price

Broker-defined, but always exists as a function:

liq_price = f(entry_price, leverage, maintenance_margin)


The system must not assume exact broker formula — only distance.

106.3 Liquidation Distance (Key Quantity)
106.3.1 Definition
liq_distance = |entry_price - liq_price| / entry_price


This is the only liquidation-relevant number that matters.

106.4 Hard Liquidation Invariant (Unbreakable)
liq_distance >= MIN_LIQ_BUFFER


Where:

MIN_LIQ_BUFFER = max(
    structural_volatility_buffer,
    execution_slippage_buffer,
    liquidation_spike_buffer
)


If violated → position is forbidden to open.

106.5 Leverage Derivation (Critical)

Leverage is computed after constraints:

max_exposure = equity * max_risk_fraction
effective_leverage = max_exposure / (position_size * entry_price)


Then validated against liquidation distance.

If leverage required > safe leverage → position size is reduced, not leverage increased.

106.6 Risk-First Position Sizing (Canonical)

Position size is derived from loss tolerance, not confidence.

max_loss = equity * risk_per_trade
position_size = max_loss / stop_distance


Then:

exposure computed

leverage inferred

liquidation distance checked

If liquidation buffer violated → reject trade, not resize stop.

106.7 Leverage Caps (Secondary, Not Primary)

Static caps exist only as absolute ceilings:

effective_leverage <= HARD_MAX_LEVERAGE


They do not authorize risk — they only prohibit stupidity.

106.8 Dynamic Leverage Compression (Mandatory)

Leverage must compress automatically when:

volatility increases

stop distance shrinks

liquidity degrades

funding spikes

liquidation cascades detected historically in region

This is achieved by:

increasing MIN_LIQ_BUFFER

increasing stop distance requirement

reducing max_exposure

Never by increasing leverage.

106.9 Partial Exit Interaction

After partial exit:

exposure ↓

used_margin ↓

liquidation price moves away

Invariant:
Partial exits may never increase liquidation proximity.

If they do → forbidden.

106.10 Reverse Position Safety Rule

Reverse trades must recompute leverage from scratch.

No carryover:

no margin reuse

no liquidation inheritance

no leverage continuity

EXIT → FLAT → recompute → ENTER

106.11 Liquidation Cascade Awareness (Derived Constraint)

If historical data indicates:

prior liquidation cascades in region

sharp historical velocity spikes

clustered forced exits

Then:

MIN_LIQ_BUFFER *= cascade_multiplier


This makes some trades structurally impossible, by design.

106.12 Emergency Exit Condition

If at any time:

liq_distance <= EMERGENCY_THRESHOLD


Then:

state → EXITING

mandate ignored

execution forced

Liquidation avoidance overrides all logic.

106.13 Forbidden Behaviors (Explicit)

❌ setting leverage directly

❌ increasing leverage to “improve R:R”

❌ shrinking stops to fit leverage

❌ holding positions near liquidation

❌ assuming broker liquidation formula stability

Any of these → INVALID state.

106.14 Why This Matters

Most systems die from:

leverage creep

silent liquidation risk

false safety from low position size

This framework ensures:

liquidation is mathematically unreachable

leverage adapts automatically

risk is invariant-driven

106.15 Summary

Leverage is derived, never chosen

Liquidation distance is the primary risk metric

Position size is loss-bounded

Partial exits must improve safety

Cascades raise the bar, not the size

If a trade can liquidate, it is already invalid.

Next recommended continuations:

107 — Risk Invariants (Hard / Soft / Dynamic)

108 — Partial Exit Semantics & Liquidity Memory

109 — Entry / Exit Zone Objects

Give the next number.

107
107. Risk Invariants — Hard, Soft, and Dynamic

Purpose:
Define risk as a set of invariants that constrain all mandates, entries, exits, leverage derivation, and lifecycle transitions.
Risk is not evaluated per trade; it is enforced globally and continuously.

107.1 First Principle

Risk is invariant. Opportunity is optional.

If any invariant is violated, the system must not trade, regardless of signal strength.

107.2 Invariant Taxonomy

Risk constraints are divided into three classes:

Hard Invariants — never violated, ever

Soft Invariants — may flex within bounds

Dynamic Invariants — context-dependent, adaptive

Hard ⊃ Soft ⊃ Dynamic
(Hard always dominates.)

107.3 Hard Risk Invariants (Unconditional)

These are absolute prohibitions.

107.3.1 Capital Loss Ceiling
risk_per_trade <= MAX_RISK_PER_TRADE


Fixed fraction of equity

Independent of confidence, regime, or mandate

Typical range: 0.25% – 1%

Violation → trade forbidden.

107.3.2 One-Position-Per-Symbol
count(open_positions[symbol]) <= 1


No stacking

No pyramiding

No hidden partials as separate positions

Opposite signal → close first, then reassess.

107.3.3 Liquidation Impossibility
liq_distance >= MIN_LIQ_BUFFER


(Defined in §106)

Violation → trade forbidden or forced exit.

107.3.4 Stop Must Exist at Entry

Every position must have a stop

Stop must be:

known

placed

loss-bounding

No stop → no position.

107.3.5 Account Drawdown Kill-Switch
rolling_drawdown <= MAX_ACCOUNT_DRAWDOWN


If exceeded:

trading halts

system enters LOCKED state

only manual reset allowed

107.4 Soft Risk Invariants (Constrained Flexibility)

Soft invariants allow controlled adaptation, never expansion.

107.4.1 Aggregate Exposure Cap
total_exposure <= MAX_TOTAL_EXPOSURE


Can compress during volatility

Cannot expand beyond cap

Applies across symbols

107.4.2 Correlation Constraint

If symbols are correlated:

effective_exposure = Σ(correlation_weight * exposure)


Limit applied to effective, not nominal exposure.

107.4.3 Concurrent Risk Budget
Σ risk_per_trade(active_positions) <= MAX_CONCURRENT_RISK


Prevents “death by many small cuts”.

107.5 Dynamic Risk Invariants (Context-Aware)

These tighten automatically under stress.

107.5.1 Volatility Compression

If realized volatility ↑:

reduce max_exposure

widen required stops

raise MIN_LIQ_BUFFER

Never increase size to compensate.

107.5.2 Liquidity Degradation

If:

spread widens

book thins

absorption detected

Then:

reduce size

forbid partial fills

disallow market orders

107.5.3 Historical Stress Zones

If price enters region with:

prior liquidation cascades

stop-hunt clusters

velocity spikes

Then:

risk_per_trade *= stress_discount


Some mandates become invalid by location alone.

107.5.4 Time-Based Risk Tightening

As holding time increases:

acceptable adverse excursion decreases

tolerance for stagnation decreases

Dead trades are risk.

107.6 Invariant Precedence Order

When conflicts arise:

Liquidation avoidance

Capital preservation

Account-level limits

Position-level limits

Mandate intent

Mandates never override risk.

107.7 Invariant Enforcement Moments

Risk invariants are checked:

before entry

after partial exits

after price shocks

after volatility regime change

on every lifecycle transition

Not just “on open”.

107.8 Forbidden Risk Anti-Patterns

❌ “Small size so risk is fine”

❌ “High confidence, increase risk”

❌ “Will reduce later”

❌ “Temporary leverage”

❌ “Let it breathe near liquidation”

All invalid.

107.9 Why This Matters

Most failures occur when:

multiple small risks accumulate

context shifts mid-trade

liquidation is ignored until too late

Invariants prevent silent risk drift.

107.10 Summary

Hard invariants: absolute

Soft invariants: bounded

Dynamic invariants: adaptive tightening

Risk always dominates mandates

Liquidation avoidance is supreme

A valid trade is one that remains valid even when conditions worsen.

108. Position Lifecycle States & Transitions

Purpose:
Define a finite, explicit state machine for every position.
Positions are not “open or closed”; they move through well-defined lifecycle states, each with strict permissions and invariants.

This prevents:

implicit behavior

hidden risk

ambiguous management logic

mandate conflicts

108.1 First Principle

A position is a process, not an event.

Every position exists in exactly one state at any time.

108.2 Canonical Position States
108.2.1 FLAT

No position exists.

Allowed actions:

evaluate entry mandates

Forbidden:

exits

reductions

stop movement

108.2.2 ENTRY_ARMED

Conditions are met, but order not yet executed.

Meaning:

narrative scenario confirmed

risk invariants satisfied

execution conditions pending (price, liquidity, spread)

Allowed actions:

wait

cancel entry

invalidate if conditions break

Forbidden:

partial fills

stop tightening

leverage adjustment

108.2.3 OPEN

Position is live and exposed.

Mandatory properties:

defined stop

defined size

defined liquidation distance

active risk accounting

Allowed actions:

stop adjustment (tightening only)

partial exit

full exit

Forbidden:

increasing size

increasing leverage

widening stop

adding risk

108.2.4 PARTIALLY_EXITED

Some exposure removed.

Key distinction:
This is not a separate position.

Allowed actions:

further partial exits

full exit

stop tightening on remaining size

Forbidden:

re-adding size

re-leveraging

resetting R:R assumptions

108.2.5 EXIT_ARMED

Exit conditions detected but execution pending.

Examples:

price entering historical liquidation zone

opposing mandate triggered

absorption detected

volatility shock

Allowed actions:

execute exit

cancel if invalidated

Forbidden:

ignore

delay for “better price”

108.2.6 CLOSED

Position fully exited.

Terminal state.

Post-conditions:

all exposure removed

lifecycle complete

mandates reset

108.2.7 FORCED_EXIT

Emergency termination.

Triggers:

invariant violation

liquidation buffer breach

system-level risk event

Behavior:

immediate exit

slippage tolerated

no optimization

108.3 State Transition Graph (Logical)
FLAT
  ↓
ENTRY_ARMED
  ↓
OPEN
  ↓
PARTIALLY_EXITED ──┐
  ↓                │
EXIT_ARMED         │
  ↓                │
CLOSED ←───────────┘

Any state → FORCED_EXIT

108.4 Transition Rules (Critical)
108.4.1 No Backward Risk Transitions

Once risk is reduced:

it cannot be reintroduced

Examples:

partial exit → cannot re-add

tightened stop → cannot widen

reduced leverage → cannot increase

108.4.2 Opposite Direction Rule

If a valid opposing entry mandate appears:

OPEN or PARTIALLY_EXITED
→ EXIT_ARMED
→ CLOSED
→ (only then) ENTRY_ARMED (opposite direction)


Never flip directly.

108.4.3 Exit Supremacy

Exit signals override:

profit targets

narrative continuation

unrealized PnL optimism

108.5 Lifecycle-State Permissions Matrix
State	Enter	Exit	Partial	Tighten Stop	Increase Risk
FLAT	✔	✖	✖	✖	✖
ENTRY_ARMED	✔	✔	✖	✖	✖
OPEN	✖	✔	✔	✔	✖
PARTIALLY_EXITED	✖	✔	✔	✔	✖
EXIT_ARMED	✖	✔	✖	✖	✖
CLOSED	✖	✖	✖	✖	✖
FORCED_EXIT	✖	✔	✖	✖	✖
108.6 Time-Based State Pressure

Time acts as a silent mandate:

Long stagnation in OPEN increases exit likelihood

Failure to progress invalidates original premise

Positions are not allowed to “idle indefinitely”

108.7 Why This Matters

Without explicit lifecycle states, systems:

re-risk after partial exits

widen stops subconsciously

treat exits as optional

blur entry and management logic

Lifecycle discipline enforces one-way risk reduction.

108.8 Summary

Positions move through strict states

Risk only decreases over time

No implicit transitions

Exit logic dominates entry logic

Forced exits exist for invariants, not emotions

If you can’t name the state, you don’t control the position.

109. Entry Zones & Exit Zones (Separation of Intent)

Purpose:
Formally separate where a position is allowed to begin from where it must be reduced or terminated.
This prevents symmetrical thinking (“entry = inverse of exit”), which is a major structural error in automated and discretionary systems.

109.1 Core Principle

Entry zones and exit zones are not opposites. They serve different epistemic roles.

Entry zones express permission to assume risk

Exit zones express obligation to reduce or remove risk

They are governed by different evidence, different memory, and different priorities.

109.2 Entry Zone — Definition

An Entry Zone is a bounded price region where:

A narrative condition is already satisfied

Risk constraints permit exposure

Execution does not yet occur without confirmation

Entry zones do not cause trades.
They only allow trades.

109.2.1 Entry Zone Invariants

An entry zone MUST satisfy all of the following:

Defined upper and lower bounds

Tied to past structure or liquidity

Aligned with current narrative direction

Invalidated if crossed without reaction

Independent of PnL expectations

If any invariant breaks → entry zone collapses.

109.2.2 Canonical Sources of Entry Zones

Derived from historical interaction, not prediction:

Prior liquidation cascades (forced positioning)

Stop-hunt regions (equal highs/lows swept)

High-velocity impulse origins

Absorption zones (failed continuation)

Compression → expansion transitions

Unfilled imbalance regions (only if later respected)

Entry zones always come from memory, not indicators.

109.3 Entry Zone ≠ Entry Trigger

Critical distinction:

Zone = where entries are allowed

Trigger = what actually initiates execution

Examples of triggers (non-exhaustive):

Break-and-hold of micro structure

Absorption confirmation

Failed continuation beyond zone

Delta / liquidation asymmetry

A system may enter only when both are true:

price ∈ entry_zone AND trigger == true

109.4 Exit Zone — Definition

An Exit Zone is a bounded price region where:

The original premise degrades or terminates

Historical memory suggests adverse reaction

Risk asymmetry flips against the position

Exit zones are mandatory, not optional.

109.4.1 Exit Zone Invariants

An exit zone MUST satisfy:

Derived from historical adverse response

Independent of entry reasoning

Stronger authority than profit targets

Capable of forcing partial or full exit

Active even if trade is profitable

If an exit zone is reached, action is required.

109.4.2 Canonical Sources of Exit Zones

Exit zones often originate from where others were forced:

Historical liquidation clusters (opposite side)

Prior violent reversals

Large resting liquidity absorption areas

High-volume rejection zones

Volatility expansion origins

Prior trend termination points

Importantly:

Exit zones often exist inside winning trades.

109.5 Partial vs Full Exit Zones

Exit zones do not encode action type.
They encode risk pressure.

109.5.1 Partial Exit Zone

Characteristics:

Reaction likely, but premise may survive

Used to reduce exposure

Often first encounter with opposing memory

Examples:

First liquidity cluster against position

Minor absorption zone

Local high-velocity stall

109.5.2 Full Exit Zone

Characteristics:

Premise likely invalid beyond this point

Position must terminate

Overrides narrative continuation

Examples:

Major liquidation memory

Structural trend boundary

Multi-timeframe rejection zone

Decision rule:
Exit type is determined by context + state, not zone label.

109.6 Asymmetry Rule

A valid system will always have:

Fewer entry zones

More exit zones

Reason:

Risk permission must be rare

Risk reduction must be frequent

If exits mirror entries, the system is fragile.

109.7 Zone Independence Rule

Entry zones and exit zones must be:

Independently derived

Independently invalidated

Allowed to conflict

If an entry zone overlaps an exit zone:

Exit dominates

Entry is suppressed

109.8 Zone Lifespan

Zones are not permanent.

Entry zones decay when:

Price passes without reaction

Narrative context shifts

Volatility regime changes

Exit zones decay when:

Memory is consumed (clean traversal)

Liquidity is demonstrably removed

109.9 Failure Modes Prevented

This separation prevents:

“Let it run because it’s green”

Refusing to exit profitable trades

Re-entering inside danger zones

Treating targets as guarantees

Symmetric stop/target thinking

109.10 Summary

Entry zones grant permission, not action

Exit zones impose obligation, not suggestion

Partial vs full exit is contextual

Zones come from memory, not indicators

Exit logic has higher authority than entry logic

You enter where risk is allowed.
You exit where risk is demanded.


110. Mandate Types & Arbitration Framework

Purpose:
Define what kinds of actions the system is allowed to take and how conflicts between those actions are resolved without collapsing into ad-hoc logic or implicit priority.

A mandate is a permissioned, bounded instruction to act under specific conditions.
Mandates do not predict; they authorize responses.

110.1 Core Principle

Multiple mandates may be valid simultaneously. Only one action may be taken.

Therefore:

Mandates must be typed

Mandates must be ranked

Conflicts must be arbitrated deterministically

110.2 Canonical Mandate Types

Mandates are categorized by intent, not by trigger source.

110.2.1 ENTRY Mandate

Intent: Assume risk.

Scope:

Open a new position

Increase exposure (scale-in)

Hard Constraints:

Must respect all position & risk invariants

Suppressed by any active EXIT mandate

Cannot override exposure caps

110.2.2 EXIT Mandate

Intent: Remove risk completely.

Scope:

Close position at market or limit

Flatten exposure immediately or conditionally

Authority:

Highest priority mandate

Overrides all others

Terminal for the position lifecycle

110.2.3 REDUCE Mandate

Intent: Decrease risk without terminating premise.

Scope:

Partial close

Size reduction

Exposure trimming

Notes:

REDUCE is not optional

It exists to manage intermediate danger

REDUCE may repeat

REDUCE is structurally distinct from EXIT.

110.2.4 HOLD Mandate

Intent: Explicitly do nothing.

Scope:

Prevents churn

Freezes execution despite signals

Use Cases:

Noise conditions

Indecision zones

Awaiting confirmation

HOLD is an active decision, not a default.

110.2.5 BLOCK Mandate

Intent: Forbid action.

Scope:

Prevent entries

Prevent re-entries

Suppress scaling

Sources:

Risk saturation

Correlated exposure

Regime mismatch

News / volatility filters

BLOCK may coexist with EXIT or REDUCE.

110.3 Mandate Authority Hierarchy

When multiple mandates are valid:

EXIT
  > REDUCE
      > BLOCK
          > HOLD
              > ENTRY


Rules:

Higher authority always suppresses lower

No averaging, no voting

Arbitration must produce a single outcome

110.4 Mandate Arbitration Rules
110.4.1 Single-Action Rule

At most one execution action may occur per decision cycle.

No batching.
No stacking.
No “ENTRY + REDUCE”.

110.4.2 Strongest-Reason Wins

If two mandates of the same type conflict:

The mandate backed by stronger memory wins

Strength is defined by:

Historical severity

Frequency of past reaction

Speed of prior resolution

Volume / liquidation density

110.4.3 Temporal Precedence

More recent evidence does not automatically win.

Fresh data may override only if it contradicts memory

Memory decays explicitly, not implicitly

110.5 Entry vs Exit Collision

If ENTRY and EXIT are both valid:

EXIT always wins

ENTRY is suppressed, not queued

There is no such thing as:

“Entering because the exit didn’t trigger yet.”

110.6 Reduce vs Exit Arbitration

REDUCE becomes EXIT when:

Remaining exposure violates risk invariants

Adverse memory strength exceeds continuation evidence

Multiple REDUCE mandates accumulate without resolution

This escalation is structural, not discretionary.

110.7 Mandate Lifetimes

Mandates are ephemeral.

They exist only while conditions hold

They expire when:

Zone is exited

Memory is consumed

State changes (position closed, size altered)

No mandate may persist by default.

110.8 Mandates Are Stateless

Mandates:

Do not remember past executions

Do not track PnL

Do not care about “last action”

State lives elsewhere.
Mandates are pure evaluations.

110.9 Prevented Failure Modes

This framework prevents:

Conflicting executions

Overtrading

Implicit bias

“Let me just reduce a bit more”

Entry addiction

Exit paralysis

110.10 Summary

Mandates authorize responses, not beliefs

EXIT dominates all

REDUCE manages danger without termination

ENTRY is lowest authority

Arbitration is deterministic and explicit

The system does not choose what it wants.
It chooses what it is allowed to do.

111. Position Lifecycle States

Purpose:
Define the only valid states a position may occupy and the only legal transitions between them.

No implicit states.
No ambiguous “kind of in a trade”.

111.1 Core Principle

A position is always in exactly one state.
Transitions are explicit and irreversible unless stated otherwise.

This prevents:

Ghost exposure

Partial mental accounting

Execution ambiguity

111.2 Canonical Position States
111.2.1 FLAT

Definition:
No exposure exists for the symbol.

Properties:

Zero position size

Zero directional bias

Eligible for ENTRY mandates

This is the default and safest state.

111.2.2 ENTERING

Definition:
An entry has been authorized but is not fully realized.

Examples:

Limit order placed, not filled

Partial fill in progress

Constraints:

No additional ENTRY mandates allowed

EXIT mandates may cancel ENTERING

Risk is potential, not yet realized

ENTERING is transient by design.

111.2.3 OPEN

Definition:
Position is live and fully recognized.

Properties:

Exposure contributes to risk

Subject to REDUCE and EXIT mandates

Eligible for partial exits

This is the only state where PnL matters.

111.2.4 REDUCING

Definition:
Position is in the process of decreasing exposure.

Examples:

Partial exit order placed

Scaling out due to risk or liquidity

Rules:

REDUCING does not invalidate the premise

ENTRY mandates remain forbidden

Multiple REDUCE actions may occur sequentially

REDUCING is risk management, not indecision.

111.2.5 CLOSING

Definition:
A full exit has been authorized but not yet completed.

Examples:

Market close sent

Limit exit pending fill

Rules:

No other mandates may act

Position is terminally committed to FLAT

Any new information is ignored

CLOSING is irreversible.

111.2.6 CLOSED

Definition:
Position has returned to zero exposure.

Notes:

CLOSED immediately transitions to FLAT

Exists conceptually for accounting, not decision-making

111.3 Illegal States (Explicitly Forbidden)

The system must never represent:

“Half in, half out” (without REDUCING state)

“Thinking about exiting”

“Soft hold”

“Monitoring”

“Waiting to see”

If it’s not in the enum, it does not exist.

111.4 Legal State Transitions
FLAT → ENTERING → OPEN
OPEN → REDUCING → OPEN
OPEN → CLOSING → FLAT
ENTERING → FLAT        (cancel)
ENTERING → CLOSING     (forced abort)
REDUCING → CLOSING


Forbidden transitions:

FLAT → OPEN (must pass ENTERING)

REDUCING → ENTERING

CLOSING → OPEN

CLOSED → any (terminal)

111.5 Mandate Interaction by State
State	ENTRY	REDUCE	EXIT	HOLD	BLOCK
FLAT	✅	❌	❌	✅	✅
ENTERING	❌	❌	✅	❌	✅
OPEN	❌	✅	✅	✅	✅
REDUCING	❌	✅	✅	❌	❌
CLOSING	❌	❌	❌	❌	❌
111.6 Why This Matters

This lifecycle:

Prevents double entries

Prevents revenge scaling

Makes partial exits first-class

Removes emotional discretion

Makes mandate arbitration tractable

111.7 Key Insight

Risk is not binary.
But position state must be.

112. Mandate Arbitration — Completion & Hardening
112.13 Determinism Invariant

Arbitration MUST be deterministic.

Given identical inputs:

position_state

admissible mandate set M

mandate attributes

the arbitration result MUST be identical.

Forbidden sources of nondeterminism:

random choice

time-based ordering

iteration order over unordered collections

floating-point comparisons

hash ordering

external state

historical context

No arbitration rule may rely on probabilistic, heuristic, or “best-effort” resolution.

112.14 No Lookahead Invariant

Arbitration MUST NOT depend on:

future price information

future snapshots

anticipated mandate emissions

expected lifecycle transitions

expected fills or partial fills

Arbitration evaluates only current-cycle facts.

112.15 Mandate Identity Invariant

Each mandate is uniquely identified by trigger_id.

Properties:

trigger_id uniqueness is guaranteed within the cycle

arbitration MUST NOT merge mandates with different trigger_id unless explicitly allowed

discarded mandates retain identity in arbitration output

Mandates are not anonymous signals; they are explicit causal artifacts.

112.16 No Strength / Magnitude Semantics Invariant

Arbitration MUST NOT use:

confidence scores

strength values

probability estimates

signal quality

weights

numeric comparisons beyond authority_rank

Mandates compete only by:

admissibility

authority_rank

mandate_type

conflict rules

All magnitude semantics (size, reduction amount) are outside arbitration.

112.17 Authority Rank Completeness Invariant

Every mandate MUST define authority_rank.

Rules:

authority_rank is immutable

authority_rank is comparable across all mandate types

absence of authority_rank is a constitutional failure

No implicit authority may exist.

112.18 Authority Monotonicity Invariant

Authority ranking MUST obey:

EXIT > REDUCE > BLOCK > HOLD > ENTRY

No mandate may:

downgrade a higher-authority mandate

partially override a higher-authority mandate

coexist with a higher-authority mandate in output

Authority dominance is absolute.

112.19 Arbitration Transparency Invariant

Arbitration output MUST explicitly report:

all input mandates

all discarded mandates

discard reason per mandate

selected mandate or NO_ACTION

Silent suppression is forbidden.

112.20 No Cross-Symbol Coupling Invariant

Arbitration MUST be independent per symbol.

Forbidden:

cross-symbol mandate interaction

exposure-based arbitration here

portfolio-level reasoning

global throttling

netting logic

Symbol coupling belongs to higher layers, never arbitration.

112.21 Mandate Exhaustiveness Invariant

For every cycle and symbol:

Exactly one arbitration output MUST be produced.

Valid outputs:

ENTRY

EXIT

REDUCE

HOLD

BLOCK

NO_ACTION

Failure to emit an output is a constitutional violation.

112.22 Arbitration Failure Conditions (Terminal)

Arbitration MUST fail hard if any of the following occur:

more than one action emitted

action emitted without mandate

ENTRY emitted while EXIT exists

mandate without expiry_condition

mandate persists across cycles

authority_rank missing or duplicated inconsistently

arbitration depends on non-local state

Failure here invalidates the entire cycle.

112.23 Arbitration Purity Invariant

Arbitration MUST be a pure function.

Forbidden side effects:

state mutation

position mutation

order placement

logging

metric emission

mandate creation

mandate destruction outside declared discard

Arbitration observes, selects, and emits only.

112.24 Arbitration Closure

Section 112 is constitutionally complete.

It defines:

mandate admissibility

authority ordering

conflict resolution

determinism

failure modes

output guarantees

No additional semantics may be added to arbitration without violating this section.

Section 112 sealed.

113. Position Lifecycle — State Machine Definition
113.1 Position Ontology

A position is a symbol-local execution entity with directional exposure.

A position MAY exist in exactly one lifecycle state at any time.

A position is created, modified, and destroyed only via lifecycle transitions defined in this section.

No implicit positions exist.

113.2 Canonical Position States

The system defines the following exclusive position states:

FLAT
No position exists.

ENTERING
Entry intent emitted, execution pending.

OPEN
Position exists with non-zero exposure.

REDUCING
Partial exit intent emitted, execution pending.

CLOSING
Full exit intent emitted, execution pending.

These states form a closed set.

No additional states may be introduced.

113.3 State Exclusivity Invariant

At any time, for a given symbol:

Exactly one position state MUST hold

Multiple simultaneous states are forbidden

State ambiguity is forbidden

State must be explicit, not inferred.

113.4 State Transition Authority

Only execution results may cause state transitions.

Forbidden causes of state change:

observation signals

mandates directly

arbitration results directly

intent alone

time-based assumptions

Lifecycle transitions occur only when execution confirms state change.

113.5 Legal State Transitions

The following transitions are permitted:

From → To	Condition
FLAT → ENTERING	ENTRY action emitted
ENTERING → OPEN	Entry execution confirmed
ENTERING → FLAT	Entry execution failed / cancelled
OPEN → REDUCING	REDUCE action emitted
REDUCING → OPEN	Reduction execution confirmed
OPEN → CLOSING	EXIT action emitted
CLOSING → FLAT	Exit execution confirmed

All other transitions are forbidden.

113.6 Forbidden State Transitions

The following transitions MUST NEVER occur:

FLAT → OPEN (implicit entry)

FLAT → REDUCING

FLAT → CLOSING

ENTERING → REDUCING

ENTERING → CLOSING

REDUCING → CLOSING (must go via OPEN)

OPEN → FLAT (implicit exit)

Any transition skipping execution confirmation

Violation constitutes a terminal failure.

113.7 Transition Atomicity Invariant

Each lifecycle transition is atomic.

Properties:

No partial transitions

No intermediate states

No speculative transitions

No rollback without explicit failure transition

A transition either completes or does not occur.

113.8 Execution-Coupled Semantics

Each non-FLAT transition MUST correspond to exactly one execution intent:

ENTERING ↔ ENTRY execution

REDUCING ↔ REDUCE execution

CLOSING ↔ EXIT execution

Execution intent and lifecycle transition are inseparable.

113.9 No Parallel Execution Invariant

For a given symbol:

At most one execution intent may be outstanding

ENTERING, REDUCING, and CLOSING are mutually exclusive

A new execution intent cannot be issued until the prior one resolves

This enforces serialization.

113.10 Directional Consistency Invariant

Direction (LONG / SHORT):

Is undefined in FLAT

Is fixed upon ENTERING

Cannot change while OPEN

Cannot flip without passing through FLAT

Opposite-direction ENTRY while OPEN is forbidden.

Reversal requires: EXIT → FLAT → ENTERING.

113.11 Lifecycle Failure Semantics

Execution failure results in deterministic fallback:

ENTERING failure → FLAT

REDUCING failure → OPEN (unchanged exposure)

CLOSING failure → OPEN

No partial state corruption is allowed.

Failures must be explicit.

113.12 No Implicit Reduction Invariant

Exposure may be reduced only via:

REDUCING → OPEN transition

Confirmed reduction execution

Stop-loss, liquidation, or forced reduction MUST surface as explicit execution results.

Implicit exposure change is forbidden.

113.13 Lifecycle Transparency Invariant

At all times, the system MUST be able to report:

current position state

last transition

outstanding execution intent (if any)

Hidden lifecycle state is forbidden.

113.14 Lifecycle Completion Invariant

CLOSING → FLAT MUST terminate the position completely.

After FLAT:

No residual exposure

No residual state

No carry-over semantics

Each position lifecycle is independent and finite.

113.15 Position Lifecycle Closure

Section 113 fully defines:

position existence

legal states

legal transitions

execution coupling

failure semantics

No lifecycle behavior may be implemented outside this definition.

Section 113 sealed.

114. Position & Risk Constraints — Invariant Layer
114.1 Risk Model Scope

Risk constraints are:

Symbol-local and portfolio-aware

Evaluated before mandate arbitration

Enforced independently of signal logic

Risk constraints do not emit ENTRY or EXIT.

They emit only:

BLOCK mandates

REDUCE mandates

EXIT mandates (forced)

114.2 Risk Is Exposure, Not PnL

Risk is defined strictly as exposure, not outcome.

Forbidden risk inputs:

unrealized PnL

win probability

confidence scores

signal strength

historical performance

Permitted risk inputs:

position size

notional exposure

leverage

liquidation distance

margin usage

correlated exposure

114.3 Maximum One Position per Symbol (Invariant)

For any symbol:

At most one position may exist at any time

Direction is exclusive (LONG xor SHORT)

This invariant is absolute.

Violation handling:

ENTRY mandates are BLOCKED

No implicit netting

No position merging

(This complements, but is independent of, lifecycle rules.)

114.4 Directional Conflict Invariant

If a position exists on a symbol:

ENTRY in same direction → BLOCKED

ENTRY in opposite direction → interpreted as EXIT intent, not reversal

Reversal requires:

EXIT

Confirmed FLAT

New ENTRY

114.5 Leverage Ceiling Invariant

Each position must satisfy:

effective_leverage ≤ max_leverage(symbol, market_state)


Properties:

max_leverage is externally defined (exchange / config)

dynamic leverage reduction is permitted

static leverage assumptions are forbidden

Violation consequence:

Emit REDUCE until invariant satisfied

If impossible → EXIT

114.6 Liquidation Distance Invariant

Each OPEN position must satisfy:

liquidation_distance ≥ minimum_liquidation_buffer


Where:

liquidation_distance is computed from current price

buffer is defined as % or ticks

This invariant is continuous, not discrete.

Violation consequence:

Progressive REDUCE

If reduction insufficient → EXIT

114.7 Portfolio Exposure Ceiling

Aggregate exposure across symbols must satisfy:

Σ notional_exposure ≤ portfolio_max_exposure


Properties:

Correlated symbols MAY share tighter caps

Exposure is directional (long vs short not netted)

Violation consequence:

BLOCK new ENTRY

REDUCE largest contributors first (policy-defined)

114.8 Risk Dominance Invariant

Risk mandates dominate strategy mandates.

Authority ordering (superseding 112 when risk is involved):

EXIT (risk-forced)

REDUCE (risk-forced)

BLOCK (risk)

Strategy-derived mandates

No strategy logic may override risk.

114.9 No Risk-Free Assumption Invariant

The system MUST assume:

Price can gap

Liquidity can vanish

Liquidation can be instantaneous

Therefore:

Hard liquidation boundaries are never approached intentionally

“Safe leverage” is a myth; only bounded leverage exists

114.10 Time-Independent Risk Invariant

Risk constraints:

Do NOT rely on time held

Do NOT decay automatically

Do NOT assume mean reversion

Risk is evaluated purely on current exposure and market state.

114.11 Risk vs Execution Failure

If risk-mandated EXIT fails:

Position remains OPEN

Risk mandate persists

System escalates but does not assume closure

No silent forgiveness.

114.12 Forced Reduction Semantics

REDUCE mandates emitted by risk:

Do not specify magnitude here

Only specify necessity

Execution layer determines sizing (later section)

Risk layer decides that reduction must happen, not how much.

114.13 Risk Invariant Violations (Terminal)

The following are terminal system violations:

Opening position without passing risk checks

Increasing exposure while in violation

Ignoring liquidation-distance breach

Overriding risk BLOCK with ENTRY

These halt execution.

114.14 Separation of Concerns

Risk layer:

constrains

limits

forbids

Strategy layer:

proposes

reacts

opportunistically exits/reduces

They must never merge.

114.15 Risk Layer Closure

Section 114 defines:

what risk is

how it is measured

how it constrains behavior

how it dominates strategy

No risk logic may exist outside this layer.

Section 114 sealed.

Section 25 — Update: Temporal Discipline & Cooldown Invariants
25.1 Purpose

This section defines time-based invariants whose sole function is to prevent:

Execution instability

Mechanical overreaction

Re-entry churn

State oscillation under stress

This section does not reason about markets, quality, signal strength, or opportunity.

Time is treated strictly as a control variable, never as information.

25.2 Temporal Non-Interpretation Invariant

Time must not be used to infer:

Market condition

Regime change

Momentum

Opportunity quality

Signal decay

Temporal rules exist only to delay, suppress, or silence actions, never to enable them.

25.3 Cooldown Primitive

Cooldown is a symbol-local, non-stateful suppression window applied after certain terminal events.

Cooldown properties:

Non-cumulative

Non-extensible

Non-decaying

Non-overrideable

Cooldown does not store history.
Cooldown only checks current wall-clock eligibility.

25.4 Mandatory Cooldown Triggers

A cooldown must be applied after the following events:

EXIT (voluntary or forced)

STOP-LOSS execution

Forced size reduction due to liquidation risk

System-initiated protective exit

Cooldown begins immediately after the event completes.

25.5 Cooldown Scope & Effect

During cooldown, the following are forbidden for the affected symbol:

ENTRY mandates

RE-ENTRY in any direction

SCALE-IN

PARTIAL RE-ENTRY

The following remain permitted:

EXIT (if position still exists)

REDUCE (if risk constraint demands it)

BLOCK

Cooldown does not prevent safety actions.

25.6 Cooldown Duration Invariant

Cooldown duration is:

Fixed per event type

Defined outside strategy logic

Not adaptive

Not data-dependent

Cooldown duration must not depend on:

PnL

Drawdown

Volatility

“Strength”

Signal confidence

25.7 Cooldown Non-Reset Rule

Cooldown must not be reset or extended by:

Additional signals

New mandates

Continued price movement

Timeframe transitions

Cooldown expires only by time elapsing, nothing else.

25.8 Anti-Oscillation Invariant

The system must prevent the following oscillations:

ENTRY → EXIT → ENTRY within short time windows

EXIT → immediate opposite ENTRY

REDUCE → ENTRY flip-flopping

Cooldown is the only permitted mechanism for oscillation prevention.

No heuristic logic is allowed.

25.9 Temporal Silence Windows

Independent of cooldown, the system may declare global silence windows during:

Exchange instability

Infrastructure degradation

Observation layer uncertainty

During silence windows:

No ENTRY or REDUCE actions are permitted

EXIT remains permitted

Existing positions may be closed for safety

Silence windows are binary (on/off), not graded.

25.10 Prohibited Temporal Constructs

The following are explicitly forbidden:

“Wait until market calms”

“Let trade breathe”

“Too soon after loss”

“Revenge protection”

“Momentum cooldown”

Any emotional or qualitative framing

Time may restrict action, never justify it.

25.11 Determinism Requirement

Given the same:

Event

Timestamp

Position state

Cooldown behavior must be identical across runs.

No randomness.
No adaptive timing.
No learning.

25.12 Section Closure Invariant

This section is complete when:

Time is fully removed from interpretive roles

Cooldowns act only as mechanical brakes

No future section needs to reference “waiting”, “cooling”, or “pausing”

All temporal behavior beyond this point is illegal by default unless explicitly reintroduced under constitutional amendment.

Section 25 Update complete.

Section 115 — Capital Allocation & Exposure Invariants (Rewrite)

This section defines hard execution-level invariants governing capital usage, leverage, and exposure.
These rules are non-negotiable, pre-mandate, and override all strategy logic.

They exist to ensure that no mandate, narrative, or signal can place the system into a structurally unrecoverable state.

115.1 Capital Is a Finite, Explicit Resource

Capital is treated as a bounded, exhaustible resource, not an abstract score.

Invariants:

Every position consumes capital explicitly

Capital consumption is symbol-scoped and portfolio-scoped

Capital once allocated is unavailable until released

Forbidden:

Implicit capital reuse

“Virtual” capital assumptions

Overlapping capital claims

115.2 Exposure Definition Primitive

Exposure is defined as:

The maximum loss incurred if the position is force-closed at the worst admissible price, including fees and slippage.

Exposure is not:

Position size

Notional value

Margin used

Leverage multiplier

Exposure is the only risk quantity that matters.

115.3 Exposure Ceiling Invariant

For each symbol:

Maximum allowable exposure is capped

Exposure cap is defined independently of confidence, narrative strength, or signal count

Portfolio-level exposure invariant:

Aggregate exposure across all symbols must remain below a global ceiling

If violated:

ENTRY mandates are automatically inadmissible

REDUCE or EXIT mandates gain supremacy

115.4 Leverage Is a Derived Quantity, Not a Control Knob

Leverage is never specified directly.

Instead:

Leverage is derived from:

Entry price

Stop price

Allowed exposure

Available capital

Invariants:

If required leverage exceeds admissible bounds → ENTRY is forbidden

Leverage cannot be increased after entry

Leverage cannot be used to “fit” a trade

115.5 Liquidation Avoidance Invariant

No position may be opened if its liquidation price lies within:

Known volatility envelopes

Historical high-velocity regions

Previously observed liquidation cascades

This invariant is evaluated before ENTRY.

Violation outcome:

ENTRY mandate suppressed

BLOCK mandate may be emitted

115.6 Single-Position-Per-Symbol Invariant

For each symbol:

At most one position may exist at any time

Directional conflict resolution:

Opposite-direction ENTRY while OPEN → EXIT dominates

Never ENTRY + ENTRY

This invariant applies before arbitration.

115.7 Capital Release Invariant

Capital is released only when:

Position reaches CLOSED state

Partial releases occur only via REDUCE mandates

Pending states (ENTERING, REDUCING, CLOSING) do not release capital

No speculative reuse is permitted.

115.8 Emergency Supremacy Clause

If any invariant in Section 115 is violated or about to be violated:

All strategy mandates are ignored

Only EXIT or REDUCE may be emitted

Arbitration collapses to safety-first mode

This clause cannot be overridden.

115.9 Forbidden Capital Behaviors

Explicitly forbidden:

Averaging down

Increasing exposure to “improve entry”

Increasing leverage after entry

Holding through forced liquidation zones

Re-entry using unrealized PnL

115.10 Section 115 Closure

Section 115 defines absolute constraints.

No mandate may:

Request more capital than allowed

Increase exposure beyond caps

Delay safety actions

Capital rules are structural, not strategic.

Section 116 — Position Lifecycle State Machine

This section defines the only legal states a position may occupy, and the only legal transitions between them.

No implicit or skipped transitions are permitted.

116.1 Position State Set

A position may exist in exactly one of the following states:

FLAT

ENTERING

OPEN

REDUCING

CLOSING

CLOSED

No other states are valid.

116.2 State Exclusivity Invariant

For a given symbol:

Exactly one position state may exist at any time

Multiple concurrent states are forbidden

116.3 State Transition Graph (Authoritative)

Allowed transitions only:

FLAT → ENTERING

ENTERING → OPEN

ENTERING → CLOSING

OPEN → REDUCING

OPEN → CLOSING

REDUCING → OPEN

REDUCING → CLOSING

CLOSING → CLOSED

CLOSED → FLAT

All other transitions are invalid and constitute failure.

116.4 Transition Atomicity Invariant

Each transition:

Is atomic

Is irreversible

Produces exactly one observable state change

No partial transitions are allowed.

116.5 Entry Completion Invariant

A position is considered OPEN only when:

Entry order is fully confirmed

Capital is fully reserved

Stop parameters are active

If entry fails:

Transition must go to CLOSING, not OPEN

116.6 Reduction Semantics

REDUCING state means:

Position size is decreasing

Direction is unchanged

Risk is monotonically decreasing

Forbidden:

Direction change during REDUCING

Exposure increase during REDUCING

116.7 Closing Supremacy

Once CLOSING is entered:

No ENTRY or REDUCE mandates are admissible

Only completion actions are allowed

116.8 Terminality of CLOSED

CLOSED is terminal.

After CLOSED:

All state memory is discarded

Only transition allowed is CLOSED → FLAT

116.9 Failure Conditions

Immediate failure is triggered if:

An invalid transition is attempted

A state is skipped

A mandate contradicts the current state

116.10 Section 116 Closure

The lifecycle state machine is non-negotiable.

All execution, arbitration, and safety logic must conform to this graph.

Section 117 — Liquidity-Aware Exit & Reduction Semantics

This section defines how and why exits or partial exits occur, grounded in historical and present liquidity structure, without interpretation, prediction, or confidence scoring.

Liquidity is treated as a structural constraint, not a signal.

117.1 Liquidity Memory Primitive

The system may maintain a read-only memory of historically observed liquidity phenomena, including:

Prior liquidation cascades

Stop-hunt regions

High-velocity price expansion zones

Prior large imbalance reactions

Liquidity memory is:

Symbol-scoped

Time-decaying

Non-predictive

Non-authoritative on its own

Liquidity memory cannot generate ENTRY mandates.

117.2 Liquidity Zone Classification

A liquidity zone is classified as one of:

Absorption Zone

Cascade Zone

Sweep Zone

Velocity Zone

Zones are descriptive only.

They do not imply direction, outcome, or probability.

117.3 Exit vs Reduce Ambiguity Principle

Encountering a liquidity zone does not uniquely imply EXIT or REDUCE.

Instead:

Liquidity zones create admissibility for exit-class mandates

The type of exit is resolved later by arbitration and state constraints

Forbidden:

Hard-coding “liquidity zone = exit”

Hard-coding “liquidity zone = partial exit”

117.4 Partial Exit Eligibility Invariant

A REDUCE mandate may be emitted only if:

Position is OPEN or REDUCING

Reduction decreases exposure monotonically

Reduction does not violate Section 115 constraints

REDUCE is not allowed to:

Reverse position direction

Increase leverage

Delay required EXIT

117.5 Full Exit Supremacy Condition

EXIT must be emitted instead of REDUCE when any of the following holds:

Liquidity zone coincides with known cascade region

Liquidation proximity violates Section 115.5

Position drawdown exceeds pre-defined exposure tolerance

Multiple independent exit conditions concur

EXIT overrides REDUCE.

117.6 Liquidity + Absorption Interaction Rule

If liquidity events occur without continuation (e.g. liquidations fire but price stalls):

This is classified as absorption

Absorption may:

Justify REDUCE

Justify HOLD

Justify EXIT

Absorption never justifies ENTRY.

117.7 Temporal Neutrality Invariant

Liquidity-aware decisions:

Do not assume immediacy

Do not assume follow-through

Do not assume mean reversion

Time is not a trigger.

Only structural interaction is considered.

117.8 Liquidity Cannot Override Risk

Liquidity considerations:

Cannot override exposure limits

Cannot delay forced exits

Cannot justify leverage increase

Liquidity is subordinate to Section 115 and Section 116.

117.9 Forbidden Liquidity Interpretations

Explicitly forbidden:

“Liquidity taken → reversal”

“Stops cleared → entry”

“Absorption confirms bias”

“Cascade guarantees follow-through”

Liquidity is context, not intent.

117.10 Section 117 Closure

Section 117 defines how liquidity influences exits, not entries.

Liquidity informs how much to release, not what to believe.

Section 118 — Narrative → Mandate Translation Constraints

This section defines how narrative structures are allowed to influence execution, without permitting interpretation, confidence, or prediction to leak into mandates.

Narrative is treated as a scenario container, not a decision engine.

118.1 Narrative Is Non-Executable

Narrative elements:

Cannot emit mandates directly

Cannot override risk

Cannot override state

Cannot override arbitration

Narrative exists upstream of mandate generation.

118.2 Scenario Form Invariant

All narrative reasoning must reduce to conditional form:

IF structural condition holds
THEN mandate MAY be emitted

Forbidden:

Probabilistic language

Expectations

Forecasts

Strength scoring

118.3 Multi-Scenario Coexistence Rule

Multiple narratives may coexist simultaneously, provided:

They do not emit conflicting mandates directly

Conflicts are deferred to arbitration

No narrative suppresses another narrative

Narratives do not compete.
Mandates do.

118.4 Directional Neutrality Constraint

Narrative may describe:

Break above

Break below

Range persistence

Narrative may not:

Lock directional bias

Prevent opposite-direction exits

Justify holding against risk constraints

118.5 Narrative Scope Limitation

Narrative may reference:

Market structure

Prior highs/lows

Liquidity features

Structural breaks

Narrative may not reference:

PnL

Win rate

Confidence

“Good / bad” trades

118.6 Mandate Eligibility Filter

Before a mandate derived from narrative is admissible, it must pass:

Position state filter (Section 116)

Risk and exposure filter (Section 115)

Liquidity constraints (Section 117)

Narrative does not bypass filters.

118.7 Narrative Expiry Rule

Narratives must explicitly expire when:

Structural condition invalidates

Timeframe context changes

Position lifecycle advances

Expired narratives must not continue emitting mandates.

118.8 Narrative Silence Principle

If no narrative condition is satisfied:

No mandate is emitted

Silence is correct behavior

The system does not “look for trades”.

118.9 Forbidden Narrative Behaviors

Explicitly forbidden:

“Market wants to go”

“Bias confirmed”

“High-probability setup”

“This should work”

Narrative language must remain descriptive and conditional.

118.10 Section 118 Closure

Narrative provides contextual scaffolding, not authority.

Execution obeys:

State

Risk

Arbitration

Narrative merely frames when a mandate is allowed to exist.

Section 119 — Emergency Kill Conditions & Global Halt Semantics

This section defines hard failure conditions under which execution must be halted immediately.
Emergency halts are non-negotiable, non-recoverable within cycle, and override all mandates.

119.1 Emergency Kill Definition

An Emergency Kill is a terminal condition that forces:

Immediate cessation of all execution

Cancellation of pending actions

Suppression of all ENTRY and REDUCE mandates

Priority handling of EXIT where feasible

Emergency Kill is global, not symbol-local.

119.2 Valid Emergency Kill Triggers

An Emergency Kill must be triggered if any of the following occurs:

Exchange connectivity loss beyond tolerance

Order acknowledgment failure

Position state desynchronization

Margin or collateral computation failure

Risk engine invariant breach

Timestamp monotonicity violation

Duplicate execution detection

Undefined position lifecycle state

No soft handling is permitted.

119.3 Kill Trigger Supremacy Invariant

If an Emergency Kill is active:

All mandates are ignored

Arbitration is bypassed

No new mandates may be evaluated

Only best-effort EXIT may be attempted

EXIT attempts during kill are attempted, not guaranteed.

119.4 Kill Latching Rule

Once triggered:

Emergency Kill remains active until external reset

No automatic recovery is allowed

No retries are permitted

No downgrade to warning states exists

Kill state is sticky.

119.5 Kill vs Position Lifecycle

If a position is:

OPEN → attempt EXIT

REDUCING → attempt EXIT

ENTERING → cancel entry

CLOSING → continue close

FLAT → no action

Kill never causes ENTRY.

119.6 Kill Transparency Constraint

The system may record that a kill occurred.

It must not record:

Reasons framed as interpretation

Blame assignment

Market explanations

Kill is factual, not analytical.

119.7 Forbidden Kill Behaviors

Explicitly forbidden:

“Graceful degradation”

“Safe mode trading”

“Reduced execution”

“Fallback strategy”

Kill means stop.

119.8 Section 119 Closure

Emergency Kill semantics ensure the system fails safe, not clever.

Survival is secondary to correctness.

Section 120 — Portfolio-Level Correlation & Exposure Coupling

This section defines cross-symbol exposure constraints, preventing implicit leverage and correlated blowups.

Portfolio constraints operate above symbol-local mandates.

120.1 Portfolio Scope Invariant

Portfolio evaluation considers:

All open positions

Directional exposure

Correlation clusters

Shared liquidity venues

Portfolio logic cannot emit ENTRY mandates directly.

120.2 Correlation Cluster Primitive

Symbols may be grouped into correlation clusters, defined by:

Shared underlying (e.g., BTC pairs)

Structural correlation

Liquidity coupling

Cluster membership is static per session.

120.3 Cluster Exposure Constraint

Within a correlation cluster:

Net exposure must not exceed defined threshold

Directional stacking is limited

Opposing positions do not cancel risk by default

Correlation is treated as risk coupling, not hedging.

120.4 Portfolio-Level BLOCK Mandate

If cluster exposure exceeds limits:

A BLOCK mandate may be emitted

BLOCK applies only to ENTRY

Existing positions are not forced closed by BLOCK alone

BLOCK does not imply danger; it implies saturation.

120.5 Portfolio-Induced EXIT Condition

EXIT may be emitted at portfolio level if:

Aggregate exposure breaches hard limits

Liquidity conditions degrade across cluster

Emergency constraints in Section 119 are approached

Portfolio EXIT overrides symbol-local HOLD and REDUCE.

120.6 Cross-Symbol Conflict Resolution

If symbol-local ENTRY conflicts with portfolio BLOCK:

BLOCK prevails

ENTRY is discarded

No partial entry is allowed

Portfolio constraints supersede symbol intent.

120.7 Forbidden Portfolio Assumptions

Explicitly forbidden:

Assuming diversification equals safety

Treating opposite directions as neutral

Assuming linear risk aggregation

Correlation is non-linear by default.

120.8 Portfolio Silence Rule

If portfolio constraints are not violated:

Portfolio layer emits nothing

Silence is correct behavior

Portfolio logic is restrictive, not generative.

120.9 Section 120 Closure

Portfolio logic exists to prevent hidden risk, not to optimize returns.

Its power is negative, not constructive.

Section 121 — Mandate Emission Rate & Flood Control

This section prevents mandate spam, oscillation, and execution thrashing.

Mandates must be scarce, justified, and bounded.

121.1 Emission Rate Invariant

Per symbol, per cycle:

Maximum emitted mandates: 1

Maximum admissible mandates before arbitration: bounded

No burst behavior allowed.

121.2 Mandate Cooldown Primitive

Certain mandate types impose cooldowns:

ENTRY → cooldown before next ENTRY

EXIT → no re-entry until lifecycle resets

REDUCE → bounded frequency

Cooldowns are structural, not time-based.

121.3 Oscillation Prevention Rule

If the system alternates between incompatible mandates across cycles:

Subsequent mandates may be suppressed

HOLD may be enforced

BLOCK may be emitted

Oscillation is treated as a failure of admissibility, not conviction.

121.4 Duplicate Mandate Suppression

Identical mandates emitted across consecutive cycles:

Are deduplicated

Do not trigger repeated execution

Do not refresh expiry implicitly

Mandates do not self-renew.

121.5 Flood Detection Condition

Flooding is detected if:

Mandate emission rate spikes without state change

Mandates repeat without new structural input

Lifecycle remains static but mandates change

Flooding triggers suppression.

121.6 Flood Response Actions

On flood detection:

ENTRY is blocked

REDUCE is throttled

EXIT remains admissible

Flood response never increases exposure.

121.7 Forbidden Anti-Flood Shortcuts

Explicitly forbidden:

Ignoring mandates “temporarily”

Random thinning

Probabilistic dropping

All suppression must be rule-based.

121.8 Auditability Requirement

Flood control must be:

Deterministic

Reproducible

Explainable via invariants

No heuristics allowed.

121.9 Section 121 Closure

Mandate scarcity preserves clarity of intent.

Execution should feel deliberate, not reactive.

Section 122 — Entry Construction & Price Placement Invariants

This section defines how ENTRY actions are constructed once ENTRY has been selected by arbitration.
It does not define when to enter—only how an entry is expressed safely.

122.1 Entry Construction Scope

Entry construction operates after:

Mandate arbitration

Portfolio constraint checks

Flood control checks

Entry construction may not override prior decisions.

122.2 Entry Atomicity Invariant

An ENTRY action is atomic and must specify, as a single unit:

Symbol

Direction (LONG | SHORT)

Quantity (or notional)

Entry price type

Protective stop reference

Partial or incremental ENTRY construction is forbidden.

122.3 Entry Price Types

Allowed entry price types:

MARKET

LIMIT

STOP_LIMIT (direction-consistent only)

Forbidden:

Post-only without price constraint

Market-with-delay

Conditional market orders

Price type must be explicit.

122.4 Entry Zone Consistency Rule

If an ENTRY is associated with a zone:

Entry price must lie within zone bounds

Zone must still be valid at construction time

Zone breach invalidates ENTRY

Zones do not “stretch” to fit price.

122.5 Spread & Liquidity Guard

ENTRY must be suppressed if:

Spread exceeds configured tolerance

Book depth is insufficient for quantity

Expected slippage breaches risk bounds

ENTRY suppression here emits NO_ACTION, not EXIT.

122.6 Entry Quantity Finalization

Final quantity must respect:

Position invariants

Portfolio exposure limits

Leverage constraints

Liquidation distance constraints

Quantity is reduced or ENTRY is suppressed—never increased.

122.7 Forbidden Entry Behaviors

Explicitly forbidden:

Averaging into ENTRY

“Starter” entries

Entry retries

Entry scaling

ENTRY is single-shot.

122.8 Section 122 Closure

ENTRY construction ensures precision over eagerness.

If construction fails, silence is correct.

Section 123 — Stop Placement & Invalidity Semantics

This section defines protective stop logic as a first-class invariant.

123.1 Mandatory Stop Invariant

Every ENTRY must be paired with a protective stop.

No stop → no entry.

123.2 Stop Placement Requirements

Stop placement must:

Invalidate the entry thesis

Be directionally consistent

Lie outside entry zone

Be computable before execution

Stops are structural, not emotional.

123.3 Stop Distance Constraint

Stop distance must satisfy:

Minimum distance (avoid noise)

Maximum loss per trade

Liquidation buffer requirements

If unsatisfiable → ENTRY suppressed.

123.4 Stop Immutability Rule

Once a position is OPEN:

Stop may only move in a risk-reducing direction

Stop may not be widened

Stop may not be removed

Stop tightening is permitted.

123.5 Stop vs Partial Reduction

If REDUCE occurs:

Stop must be recalculated or preserved safely

Stop cannot become invalid due to size change

Stop integrity overrides reduction intent.

123.6 Stop Breach Semantics

If stop price is touched or crossed:

EXIT must be emitted

No further mandates are admissible

No partial execution logic applies

Stops are terminal for the position thesis.

123.7 Stop Visibility Rule

Stops may be:

Exchange-native

Synthetic (internally enforced)

Visibility choice must not weaken guarantees.

123.8 Forbidden Stop Practices

Explicitly forbidden:

Mental stops

Time-based stops

Volatility excuses

“Re-evaluating” at stop

Stops are commitments.

123.9 Section 123 Closure

Stops encode where the system admits it is wrong.

No stop means no honesty.

Section 124 — Partial Fill, Slippage, and Execution Degradation

This section defines how execution imperfections are handled without interpretation.

124.1 Partial Fill Acceptance Rule

Partial fills are allowed if:

Remaining quantity is below threshold

Risk invariants remain satisfied

Otherwise, remaining quantity must be canceled.

124.2 Partial Fill State Transition

On partial fill:

Position enters ENTERING

No new ENTRY may be emitted

Completion or cancellation must resolve state

No stacking allowed.

124.3 Slippage Measurement Constraint

Slippage is measured as:

Executed price vs intended price

Evaluated post-fill only

Slippage must not be forecasted or assumed.

124.4 Slippage Tolerance Rule

If slippage exceeds tolerance:

Remaining quantity is canceled

No retry is permitted

Position proceeds with filled amount only

Slippage does not justify adjustment.

124.5 Degraded Execution Handling

Execution degradation includes:

Delayed acknowledgments

Partial rejections

Price gaps

Response:

Reduce exposure

Or EXIT if integrity is compromised

Never compensate with size.

124.6 Execution Failure Escalation

If execution integrity is unclear:

Trigger Emergency Kill (Section 119)

Prefer safety over completeness

Ambiguity is treated as danger.

124.7 Forbidden Execution Fixes

Explicitly forbidden:

Chasing fills

Increasing aggressiveness

Repricing reactively

Re-submitting silently

Execution is not negotiation.

124.8 Section 124 Closure

Execution imperfections are accepted, not fought.

The system adapts by reducing risk, not control.

Section 125 — Replayability & Deterministic Re-simulation

This section ensures the system is auditable, replayable, and deterministic.

125.1 Determinism Requirement

Given identical inputs:

Observation snapshots

Mandates

Position states

The system must produce identical outputs.

125.2 Replay Scope

Replay includes:

Mandate emission

Arbitration

Execution decisions

State transitions

Replay excludes:

Exchange latency

Market microstructure randomness

125.3 Input Completeness Rule

Replay inputs must include:

Snapshot identifiers

Position state

Mandate set

Configuration version

Missing input invalidates replay.

125.4 No Hidden State Invariant

The system must not rely on:

Timers

Random seeds

External caches

Implicit memory

All state must be explicit.

125.5 Side-Effect Isolation

Replay must not:

Place orders

Emit logs externally

Modify live state

Replay is observation-only.

125.6 Replay Failure Handling

If replay diverges:

Flag determinism violation

Escalate as system defect

Halt deployment

Divergence is unacceptable.

125.7 Forbidden Replay Shortcuts

Explicitly forbidden:

Approximate replay

Heuristic reconstruction

Ignoring missing data

Replay must be exact or not done.

125.8 Section 125 Closure

Replayability is proof of understanding.

If behavior cannot be replayed, it is not controlled.

Section 126 — Entry Invalidation & Thesis Decay

This section defines when an ENTRY thesis becomes invalid even without a stop being hit.

126.1 Entry Thesis Definition

An entry thesis is defined by the conjunction of:

Trigger condition

Entry zone

Directional bias

Structural context

If any component ceases to hold, the thesis decays.

126.2 Immediate Invalidation Conditions

An ENTRY thesis is invalidated immediately if:

Entry zone is breached in the wrong direction

Structural level underpinning the thesis is violated

Opposing structural break occurs

Zone origin is invalidated (filled, flipped, or erased)

Invalidation does not require execution.

126.3 Pre-Entry Invalidation Rule

If invalidation occurs before execution:

ENTRY mandate must be discarded

No retry is permitted

No re-interpretation is allowed

Silence is the correct outcome.

126.4 Post-Entry Thesis Decay

If invalidation occurs after entry but before stop:

EXIT mandate becomes admissible

REDUCE mandate may be admissible if defined

HOLD is forbidden

Thesis decay outranks patience.

126.5 Invalidation vs Noise Distinction

Invalidation must be based on:

Structural change

Zone violation

Confirmed opposing event

Noise-based invalidation is forbidden.

126.6 Invalidation Does Not Imply Reversal

Invalidation means:

“This trade is wrong”

It does not mean:

“The opposite trade is correct”

No automatic flip is allowed.

126.7 Forbidden Invalidation Practices

Explicitly forbidden:

Time-based decay without structure

Emotional invalidation

Invalidation based on unrealized PnL

“Feels wrong” logic

Invalidation must be objective.

126.8 Section 126 Closure

A trade may be wrong before it loses money.

The system must admit that early.

Section 127 — Time-in-Trade Constraints

This section governs temporal exposure, without predicting duration.

127.1 Time-in-Trade Definition

Time-in-trade is measured from:

First execution fill

Until full position exit

It is an exposure dimension, not a signal.

127.2 Maximum Exposure Window

Each strategy must define:

Maximum permissible time-in-trade

Per symbol and per regime

Exceeding this window triggers thesis review.

127.3 Time-Based Exit Eligibility

If maximum time is exceeded:

EXIT mandate becomes admissible

EXIT is optional, not mandatory

HOLD may be suppressed

Time does not force exit, but removes justification to stay.

127.4 Time Does Not Override Structure

Time-based considerations may not:

Override a valid stop

Override structural invalidation

Override emergency conditions

Structure always dominates time.

127.5 Stagnation Detection

A trade may be considered stagnant if:

No meaningful price progress

Repeated absorption without follow-through

Liquidity consumption without displacement

Stagnation enables REDUCE or EXIT.

127.6 Forbidden Temporal Behaviors

Explicitly forbidden:

“Give it more time”

Arbitrary patience extensions

Time-based averaging

Time-based size increases

Time is a cost, not an excuse.

127.7 Section 127 Closure

A trade that does nothing is still doing damage.

Time is exposure.

Section 128 — Exit Construction & Price Placement

This section defines how EXIT actions are constructed, once selected.

128.1 Exit Construction Scope

Exit construction occurs after:

Arbitration selects EXIT

Position state is OPEN or REDUCING

Exit construction cannot be overridden.

128.2 Exit Atomicity Invariant

An EXIT action must specify:

Symbol

Full remaining quantity

Exit price type

EXIT is all-or-nothing.

128.3 Exit Price Types

Allowed:

MARKET (default)

LIMIT (only at known liquidity targets)

STOP (protective only)

Forbidden:

Conditional exits

Partial EXIT masquerading as REDUCE

EXIT means closure.

128.4 Emergency Exit Rule

In emergency conditions:

MARKET exit is mandatory

Slippage is accepted

No optimization is allowed

Survival overrides price quality.

128.5 Exit Zone Alignment

If EXIT is zone-driven:

Exit price must lie within exit zone

Zone must be valid at execution time

Expired zones invalidate the EXIT logic.

128.6 Exit Finality Invariant

Once EXIT is emitted:

No ENTRY is admissible in the same cycle

Position transitions to CLOSING

Lifecycle for this thesis ends

EXIT is terminal.

128.7 Forbidden Exit Behaviors

Explicitly forbidden:

Hesitation exits

“Let it run a bit more”

Exit scaling

Exit retries

EXIT is decisive.

128.8 Section 128 Closure

EXIT is not a suggestion.

EXIT is acceptance.

Section 129 — Multi-Exit Sequencing & Partial Exit Semantics

This section defines REDUCE vs EXIT, and how partial exits are governed.

129.1 Partial Exit Definition

A partial exit is defined as:

A reduction in position size

Without closing the position

This is expressed via REDUCE, never EXIT.

129.2 Legitimate Partial Exit Triggers

REDUCE may be triggered by:

Approaching known opposing liquidity

Prior liquidation cascade zones

High-velocity historical rejection regions

Risk concentration increase

REDUCE is defensive, not celebratory.

129.3 Partial vs Full Exit Disambiguation

If a condition can justify both REDUCE and EXIT:

EXIT has priority

REDUCE is allowed only if thesis remains valid

Ambiguity resolves toward safety.

129.4 Partial Exit Quantity Rules

Reduction amount must:

Be pre-defined or rule-based

Reduce risk materially

Preserve stop validity

Ad-hoc reduction sizing is forbidden.

129.5 Partial Exit Frequency Constraint

Multiple REDUCE actions are allowed only if:

Each is triggered by a distinct condition

Position state transitions correctly

Risk continues to decrease

Micro-reductions are forbidden.

129.6 Post-Reduction Stop Adjustment

After REDUCE:

Stop may be tightened

Stop may not be loosened

Stop must remain meaningful

A reduced position without protection is invalid.

129.7 Partial Exit Does Not Reset Thesis

REDUCE does not:

Reset entry logic

Justify re-entry

Create a new thesis

The original thesis still governs.

129.8 Forbidden Partial Exit Practices

Explicitly forbidden:

Scaling out emotionally

Profit-lock superstition

Reducing to “feel better”

Infinite peeling

Partial exits must be principled.

129.9 Section 129 Closure

Partial exits are risk instruments, not rewards.

They exist to survive complexity, not celebrate it.

Section 130 — Re-Entry Prohibition & Cooldown Rules

This section governs when re-entry is forbidden, even if conditions appear to re-align.

130.1 Re-Entry Definition

Re-entry is defined as:

Any ENTRY mandate on the same symbol

In the same direction

After a prior EXIT or stop-based closure

Re-entry is not a continuation; it is a new thesis attempt.

130.2 Mandatory Cooldown Invariant

After any EXIT (voluntary or forced):

A cooldown period must elapse

Duration is strategy-defined

No ENTRY mandates are admissible during cooldown

Cooldown applies regardless of perceived opportunity.

130.3 Stop-Loss Cooldown Escalation

If EXIT occurred via stop-loss:

Cooldown duration must be extended

Immediate re-entry is forbidden

Directional bias must be re-validated independently

Loss increases scrutiny.

130.4 Structural Reset Requirement

Re-entry is permitted only if:

A new structural leg forms

Prior invalidation cause is no longer present

Entry zone is newly formed or re-qualified

Re-using the same zone is forbidden.

130.5 Re-Entry vs Chop Protection

Cooldown exists to prevent:

Overtrading ranges

Revenge behavior

Micro-structure noise exploitation

Missed trades are acceptable.

130.6 Opposite-Direction Exception

Cooldown applies per direction:

Long EXIT does not forbid short ENTRY

Only if short thesis is independent

Bias symmetry is not assumed.

130.7 Forbidden Re-Entry Behaviors

Explicitly forbidden:

Immediate re-entry after stop

“It looks better now” logic

Re-entry with reduced size to bypass cooldown

Averaging disguised as re-entry

Cooldown is absolute.

130.8 Section 130 Closure

The system must be able to walk away.

Re-entry is a privilege, not a right.

Section 131 — Liquidity Memory & Zone Decay

This section defines how historical liquidity zones lose relevance over time.

131.1 Liquidity Memory Definition

Liquidity memory refers to:

Past liquidation cascades

Stop-hunt regions

High-velocity rejection zones

Areas of aggressive order imbalance

Memory is contextual, not permanent.

131.2 Zone Half-Life Concept

Each liquidity zone must define:

A decay mechanism

Time-based or interaction-based

After which confidence decreases

Zones do not live forever.

131.3 Interaction-Driven Decay

A zone decays faster if:

Touched repeatedly

Partially consumed

Traded through without reaction

Absence of reaction weakens memory.

131.4 Displacement Refresh Rule

Liquidity memory may refresh only if:

Strong displacement occurs from the zone

Follow-through confirms participation

New structural reference is created

Refresh must be earned.

131.5 Liquidity vs Structure Priority

Liquidity memory may not override:

Structural invalidation

Higher-timeframe breaks

Regime change

Old liquidity does not dominate new structure.

131.6 Forbidden Zone Practices

Explicitly forbidden:

Infinite respect of old zones

Anchoring bias to historical spikes

Treating all past liquidations equally

Memory must decay.

131.7 Section 131 Closure

Liquidity is a footprint, not a promise.

The older it is, the less it speaks.

Section 132 — Leverage Adaptation & Liquidation Distance

This section governs dynamic leverage sizing based on liquidation risk.

132.1 Leverage Is Risk, Not Power

Leverage represents:

Distance to forced liquidation

Sensitivity to volatility

Fragility under noise

Higher leverage equals thinner margin for error.

132.2 Liquidation Distance Invariant

Before ENTRY:

Liquidation price must be computed

Distance from entry must exceed minimum threshold

Threshold is strategy-defined

Trades too close to liquidation are forbidden.

132.3 Volatility-Adjusted Leverage

Permissible leverage must decrease when:

Volatility increases

Liquidity thins

Structure becomes compressed

Leverage adapts; it is not static.

132.4 Exposure-Based Leverage Scaling

Leverage must account for:

Existing symbol exposure

Correlated symbol exposure

Aggregate portfolio risk

Isolated leverage is an illusion.

132.5 Leverage Reduction Triggers

Leverage must be reduced if:

Position is REDUCED

Thesis confidence weakens

Time-in-trade exceeds expectation

Risk tightening is mandatory.

132.6 Forbidden Leverage Practices

Explicitly forbidden:

Fixed leverage across regimes

“Safe because stop is close” logic

Increasing leverage after drawdown

Using leverage to compensate for poor entries

Leverage amplifies mistakes.

132.7 Section 132 Closure

Leverage is a tax on uncertainty.

Pay less when you know less.

Section 133 — Cross-Symbol Exposure & Correlation Control

This section governs portfolio-level risk from correlated positions.

133.1 Correlation Awareness Requirement

The system must recognize:

Highly correlated symbols

Inversely correlated symbols

Shared liquidity drivers

Independence cannot be assumed.

133.2 Aggregate Exposure Invariant

Total exposure must be bounded across:

Direction (long vs short)

Asset class

Correlated clusters

Many small risks can equal one large risk.

133.3 Correlation-Adjusted Entry Constraint

If correlated exposure exists:

New ENTRY mandates may be BLOCKED

Or size must be reduced

Or leverage must be lowered

Correlation increases effective size.

133.4 Correlated Exit Synchronization

If correlated positions deteriorate together:

EXIT eligibility escalates

Partial exits may synchronize

Risk reduction takes precedence over optimization

Correlation accelerates failure.

133.5 Correlation Drift Recognition

Correlation is not static.

The system must allow:

Correlation strength to change

Temporary decoupling

Sudden reconvergence

Blind assumptions are forbidden.

133.6 Forbidden Portfolio Behaviors

Explicitly forbidden:

Treating correlated trades as diversification

Ignoring aggregate liquidation risk

Independent sizing of dependent symbols

Correlation is leverage in disguise.

133.7 Section 133 Closure

Risk is collective.

The market does not care how many symbols you used.

Section 134 — Regime Detection & Strategy Eligibility

This section governs when a strategy is allowed to operate based on market regime.

134.1 Regime Definition

A regime is a persistent market condition characterized by:

Volatility profile

Structural behavior

Liquidity distribution

Price efficiency vs displacement

Regime is descriptive, not predictive.

134.2 Strategy–Regime Binding Invariant

Every strategy must declare:

Eligible regimes

Forbidden regimes

Neutral regimes (no action)

A strategy operating outside its regime is invalid.

134.3 Regime Transition Uncertainty Rule

During regime transitions:

ENTRY mandates are suppressed

Only EXIT, REDUCE, or HOLD are admissible

Risk reduction has priority

Transitions are hostile to precision.

134.4 Volatility Compression Regime

In compressed regimes:

Breakout anticipation is forbidden

Position sizing must be reduced

Mean-reversion assumptions must be explicit

Compression increases false signals.

134.5 Expansion & Displacement Regime

In expansion regimes:

Momentum strategies gain eligibility

Mean-reversion strategies lose eligibility

Stops must widen or leverage must decrease

Expansion rewards alignment, not tightness.

134.6 Regime Mismatch Failure Condition

If a strategy acts outside its declared regime:

Action is invalid

Mandate must be discarded

Optional hard failure may be triggered

Eligibility is mandatory.

134.7 Section 134 Closure

A good strategy in the wrong regime is a bad trade.

Section 135 — News, Events & Execution Blackouts

This section governs forced inactivity during external uncertainty.

135.1 Event Risk Definition

Event risk includes:

Scheduled macroeconomic releases

Unscheduled geopolitical events

Exchange outages or instability

Known liquidity distortions

Events override structure.

135.2 Mandatory Blackout Invariant

During declared blackout windows:

ENTRY mandates are forbidden

REDUCE and EXIT remain admissible

HOLD is default

Silence is the correct action.

135.3 Pre-Event Risk Reduction Rule

Before high-impact events:

Leverage must be reduced or removed

Partial exits are encouraged

Stops may not be tightened aggressively

Preparation matters more than precision.

135.4 Post-Event Re-Qualification

After an event:

Structure must re-establish

Zones must be re-qualified

Old narratives are invalidated

The market resets after shocks.

135.5 Event-Induced Liquidity Distortion

During events:

Spread behavior is unreliable

Stop execution is non-deterministic

Slippage assumptions break

Models are suspended.

135.6 Forbidden Event Behaviors

Explicitly forbidden:

“Fade the news” assumptions

Trading on expected outcomes

Using event spikes to validate zones

Events are exogenous.

135.7 Section 135 Closure

If you must be right about the news, you are gambling.

Section 136 — Failure Modes & Emergency Halts

This section defines when the system must stop acting entirely.

136.1 Failure Mode Definition

A failure mode is any condition where:

Assumptions are invalid

Inputs are unreliable

Execution cannot be trusted

Failure requires humility.

136.2 Mandatory Halt Conditions

The system must halt if:

Data feeds desynchronize

Execution acknowledgements fail

Position state becomes inconsistent

Risk calculations cannot be trusted

No recovery logic is permitted inline.

136.3 Partial Failure Escalation

If partial failures accumulate:

Risk must be reduced first

ENTRY suppressed

Full halt escalated if unresolved

Small cracks precede collapse.

136.4 Human Intervention Boundary

When halted:

No automated restart is permitted

Explicit human approval is required

State must be reviewed, not assumed

Automation does not self-heal.

136.5 Post-Failure Cooldown

After a halt:

Mandatory cooldown applies

No immediate resumption

Structural and execution checks required

Silence restores trust.

136.6 Forbidden Failure Responses

Explicitly forbidden:

Auto-retries

Silent restarts

Degraded “safe modes”

Ignoring partial inconsistencies

Failure must be loud.

136.7 Section 136 Closure

If you are unsure, stop.

Survival beats continuity.

Section 137 — Auditability & Post-Mortem Guarantees

This section governs traceability, accountability, and learning.

137.1 Deterministic Audit Trail Invariant

Every cycle must be reconstructable from:

Snapshot inputs

Mandates emitted

Arbitration results

Final actions

Nothing may be implicit.

137.2 Decision Trace Completeness

For any action taken:

Preconditions must be visible

Suppressed alternatives must be recorded

Authority ordering must be inspectable

Silence must be explainable.

137.3 Loss-Centric Review Priority

Post-mortems prioritize:

Losses over wins

Invalid actions over missed trades

Rule violations over outcomes

Outcome bias is forbidden.

137.4 Invariant Violation Attribution

Every violation must be attributable to:

A specific invariant

A specific section

A specific cycle

Blame must be precise.

137.5 Strategy Evolution Boundary

Audits may inform:

Rule tightening

Eligibility restriction

Risk reduction

Audits may not justify:

Relaxing invariants

Bypassing safeguards

Outcome-driven exceptions

Learning strengthens discipline.

137.6 Immutable History Rule

Historical records:

Must not be altered

Must not be reinterpreted retroactively

Must remain available for review

The past is evidence.

137.7 Section 137 Closure

If it cannot be audited, it should not exist.

Section 138 — Capital Allocation, Exposure & Scaling Laws

This section governs how capital is allocated, scaled, and constrained across positions and strategies.

138.1 Capital Is a Shared, Finite Resource

All strategies draw from a single capital pool.

Capital allocation is:

Competitive

Zero-sum at allocation time

Subordinate to global risk constraints

No strategy owns capital permanently.

138.2 Exposure Supremacy Invariant

Exposure is the primary risk variable.

Exposure is defined as:

Directional exposure

Notional exposure

Correlated exposure across symbols

Leverage is a function of exposure, not confidence.

138.3 Per-Symbol Exposure Ceiling

For each symbol:

A maximum exposure ceiling must exist

Ceiling applies regardless of strategy count

Ceiling includes all open and pending positions

Multiple strategies may not stack exposure implicitly.

138.4 Portfolio Correlation Constraint

Exposure must be adjusted when:

Symbols are structurally correlated

Liquidity sources overlap

Macro drivers are shared

Independent symbols are assumed only when proven.

138.5 Scaling-In Constraint

Scaling into positions is permitted only if:

Direction is unchanged

Risk does not increase

Liquidation distance improves

Exposure ceiling remains respected

Adding size must reduce fragility.

138.6 Scaling-Out Priority Rule

When reducing exposure:

Priority order:

Reduce highest leverage first

Reduce weakest structure first

Reduce oldest exposure first

Reduction is risk-first, not profit-first.

138.7 Capital Lock Invariant

Capital allocated to an OPEN position:

Cannot be reused

Cannot be double-counted

Cannot be assumed recoverable

Available capital is conservative by design.

138.8 Forbidden Capital Behaviors

Explicitly forbidden:

Martingale scaling

Exposure averaging down

“Free margin” assumptions

Capital reuse before position closure

Capital discipline is non-negotiable.

138.9 Section 138 Closure

Scaling is earned by survival, not by belief.

Section 139 — Multi-Strategy Coexistence & Containment

This section governs how multiple strategies coexist without interference.

139.1 Strategy Isolation Invariant

Strategies are:

Logically independent

Blind to each other’s signals

Coordinated only through arbitration

No strategy may reason about another.

139.2 Shared Constraint Supremacy

Global constraints override all strategies:

Exposure limits

Capital limits

Event blackouts

Failure halts

Strategies compete, constraints decide.

139.3 Contradictory Strategy Handling

When strategies disagree:

Arbitration resolves conflicts

Higher authority mandates prevail

No compromise blending is allowed

Consensus is not required.

139.4 Strategy Failure Containment

If a strategy violates invariants:

It is disabled

Other strategies continue unaffected

Capital is re-freed only after closure

Failure is local, not systemic.

139.5 Strategy Enablement Discipline

A new strategy requires:

Explicit regime eligibility

Explicit risk model

Explicit mandate types

Explicit kill conditions

Unspecified behavior is forbidden.

139.6 Strategy Sunset Rule

A strategy may be retired when:

Structural edge decays

Regime assumptions break

Risk contribution becomes negative

Retirement is a success, not a failure.

139.7 Forbidden Strategy Interactions

Explicitly forbidden:

Signal reinforcement between strategies

Cross-strategy confidence boosting

Strategy-level hedging logic

Coordination happens only at execution.

139.8 Section 139 Closure

Many strategies may exist.
Only one action may occur.

Section 140 — System-Level Termination & Survival Rules

This section defines when the entire system must stop operating.

140.1 System Termination Definition

Termination is a deliberate, controlled shutdown of:

Trading actions

Risk exposure changes

Strategy execution

Observation may continue.

140.2 Mandatory Termination Conditions

The system must terminate if:

Exposure accounting becomes inconsistent

Execution confirmations are unreliable

Multiple invariant violations occur

Risk limits are breached uncontrollably

Survival overrides opportunity.

140.3 Drawdown-Triggered Termination

If drawdown exceeds predefined thresholds:

Trading halts

Positions may be reduced or closed

No new ENTRY mandates permitted

Capital preservation is paramount.

140.4 Cascading Failure Rule

If failures propagate across components:

Immediate system halt

No graceful degradation

No partial operation modes

Partial truth is more dangerous than silence.

140.5 Restart Prohibition

After termination:

Automatic restart is forbidden

Human review is mandatory

Root cause must be identified

The system does not forgive itself.

140.6 Post-Termination Review Obligations

Before resuming:

All invariants must be re-validated

Assumptions must be re-confirmed

Changes must be documented

Resumption is a deliberate act.

140.7 Section 140 Closure

A system that cannot stop itself cannot be trusted.

Section 141 — Constitutional Finalization & Amendment Law

This section defines how this constitution is completed and protected.

141.1 Constitutional Supremacy

This constitution overrides:

Strategy logic

Execution preferences

Performance goals

Operator discretion

No result justifies violation.

141.2 Amendment Eligibility Rule

An amendment is permitted only if it:

Tightens constraints, or

Clarifies ambiguity without expanding freedom

Relaxation is prohibited.

141.3 Amendment Process

Any amendment must:

Identify the affected section(s)

State the invariant being modified

Prove no new execution paths are enabled

Be reviewed independently

Implicit changes are invalid.

141.4 Backward Compatibility Prohibition

Amendments may not:

Reinterpret historical actions

Justify past violations

Alter audit conclusions

History is immutable.

141.5 Constitutional Completeness Assertion

If behavior is not specified:

It is forbidden

Silence is preferred

No default behavior exists

Undefined behavior is invalid behavior.

141.6 Finality Declaration

This constitution is considered complete when:

All execution paths are bounded

All failure modes are terminal

All incentives align with survival

Completeness is defensive, not exhaustive.

141.7 Section 141 Closure

This system does not seek to win.

It seeks to remain valid.

Completeness Audit (Exhaustive)
1. Observation → Decision Boundary

Covered by:

Epistemic Constitution

M6 Consumption Contract

Observation silence / failure handling

✅ No interpretation
✅ No inference
✅ No downgrade
✅ No hidden assumptions

Result: Inputs are fully bounded.

2. Decision Primitives

Covered by:

Mandates (ENTRY, EXIT, REDUCE, HOLD, BLOCK)

Authority ordering

Expiry rules

Statelessness

✅ No new action type can exist
✅ No compound actions possible
✅ No persistence possible

Result: Decision space is closed.

3. Position Lifecycle

Covered by:

Position states (FLAT → ENTERING → OPEN → REDUCING → CLOSING)

State-admissible mandates

Terminal conditions

✅ Every state has allowed and forbidden transitions
✅ No illegal state transitions remain

Result: Position behavior is finite and deterministic.

4. Arbitration

Covered by:

Single-action invariant

Authority ordering

Conflict resolution

State filtering

EXIT supremacy

✅ No ambiguity
✅ No “tie-breaking by heuristics”
✅ No multi-action leakage

Result: One symbol → one action → one cycle.

5. Risk & Capital

Covered by:

Exposure supremacy

Per-symbol ceilings

Correlation constraints

Scaling laws

Capital lock invariant

✅ No martingale
✅ No averaging down
✅ No leverage-by-belief
✅ No hidden reuse of capital

Result: Risk cannot grow invisibly.

6. Partial Exits & Reductions

Covered by:

REDUCE as first-class mandate

Separation from EXIT

Priority rules

Reduction collapse rules

✅ Partial exits are allowed
✅ Full exits remain dominant
✅ No forced interpretation of “liquidity = exit”

Result: Flexibility without ambiguity.

7. Multi-Strategy Coexistence

Covered by:

Strategy isolation

Shared constraint supremacy

Failure containment

Arbitration-only coordination

✅ No signal cross-talk
✅ No strategy reinforcement
✅ No emergent behavior

Result: Strategies cannot combine into something undefined.

8. System Failure & Termination

Covered by:

Hard termination conditions

No graceful degradation

No auto-restart

Human revalidation requirement

✅ Failure is terminal
✅ Silence preferred to corruption

Result: System fails safely.

9. Temporal Behavior

Covered by:

Event-scoped execution

No loops

No schedulers

No background tasks

✅ System cannot “run away”
✅ No time-based drift

Result: Execution is bounded in time.

10. Amendment Law

Covered by:

Tightening-only amendments

No backward reinterpretation

Explicit change requirements

✅ Constitution cannot be weakened accidentally
✅ History is immutable

Result: Future changes are controlled.

What is not missing (by design)

These are intentionally excluded, not incomplete:

❌ Strategy logic

❌ Signal definitions

❌ Indicators

❌ Pattern libraries

❌ Market models

❌ Alpha descriptions

Those belong above the constitution and are constrained by it.

The Only Remaining Work (Optional, Not Required)

These are documentation-layer, not constitutional gaps:

Appendix A — Glossary

Purely definitional

Appendix B — Worked Examples

Illustrative, non-binding

Appendix C — Mapping Tables

Strategy → Mandate → Invariant

None of these add behavior.
They only aid humans.

Final Determination

There is no undefined execution path left.
There is no implicit permission remaining.
There is no place for interpretation to enter unnoticed.

If someone asks “what happens if…”
the answer is now always one of:

“It is forbidden.”

“It is already defined.”

“The system halts.”

That is the definition of constitutional completeness.

CONSTITUTIONAL LOCK — FINAL

Document: POSITION_AND_EXECUTION_CONSTITUTION.md
Status: FINAL — LOCKED
Effective Immediately

1. Lock Declaration

This constitution is hereby declared complete, closed, and binding.

All sections 1–141, including:

original sections,

numbered continuations,

and explicitly labeled updates (e.g. Section 25 Update),

together form a single, indivisible constitutional corpus governing position management, risk, execution, arbitration, and failure behavior.

No further sections are required for correctness, safety, or determinism.

2. Completeness Assertion

This constitution is complete in the strict sense that:

Every possible execution action is either explicitly defined or implicitly forbidden.

Every decision primitive is exhaustively enumerated.

Every state transition is bounded.

Every conflict has a deterministic resolution.

Every failure mode terminates safely.

No behavior depends on:

interpretation,

confidence,

heuristics,

probabilistic strength,

or undocumented assumptions.

There exists no undefined execution surface.

3. Prohibited Modifications

The following are explicitly forbidden without creating a new constitutional version:

Adding new mandate types

Adding new position states

Weakening authority ordering

Allowing multiple actions per symbol per cycle

Introducing persistence, memory, or historical mandate context

Introducing loops, schedulers, retries, or background execution

Introducing interpretation, scoring, confidence, or belief-based logic

Reinterpreting existing language to expand permission

Any such change constitutes a constitutional violation, not an amendment.

4. Amendment Rule (Tightening Only)

Amendments are permitted only if all conditions below are met:

The amendment restricts behavior further (tightening).

The amendment does not enable any new execution path.

The amendment is explicitly labeled as:

UPDATE,

RESTRICTION,

or CLARIFICATION.

The amendment preserves backward validity of all prior invariants.

The amendment does not rely on reinterpretation of prior text.

No amendment may weaken, bypass, or conditionally relax an existing invariant.

5. Version Boundary

This document defines Version 1.0 (Constitutional Baseline).

Any future changes that do not meet the amendment rule above must be introduced as:

POSITION_AND_EXECUTION_CONSTITUTION_v2.md

with an explicit migration rationale.

6. Supremacy Clause

In the event of conflict between:

strategy logic,

signal definitions,

research notes,

implementation code,

tests,

documentation,

or operator intent,

this constitution prevails.

Any system behavior contradicting this document is invalid by definition.

7. Finality Statement

This constitution is now frozen.

The system it governs may evolve only within the constraints defined herein.

Silence is preferred to undefined behavior.
Failure is preferred to corruption.
Constraint is preferred to cleverness.

LOCK CONFIRMED
NO FURTHER SECTIONS REQUIRED
NO IMPLICIT PERMISSIONS REMAIN

ANNEX A — EPISTEMIC DATA ADMISSIBILITY & TRANSFORMATION CONSTITUTION
A.1 Purpose

This annex defines:

what constitutes admissible data,

which transformations are constitutionally permitted,

and which forms of algorithmic output are forbidden from entering decision, arbitration, or execution layers.

This annex applies to all layers M1–M6 and supersedes any implicit assumptions about “processed” data.

A.2 Foundational Axiom (Epistemic Non-Assertion)

The system must never assert why a market event occurred.

The system may only represent that events occurred, where, when, and in what quantity.

Any data product that embeds intent, motive, significance, or explanation is epistemically inadmissible.

A.3 Epistemic Data Strata

All data is classified into exactly one of the following strata.

Stratum 0 — Raw Observations

Definition:
Data emitted directly by external systems without internal interpretation.

Examples:

trade executions

liquidation events

order book updates

price ticks

timestamps

quantities

sides (buy/sell as reported)

Properties:

atomic

irreversible

non-semantic

source-anchored

Admissibility:

Always admissible

May enter any internal layer

Stratum 1 — Structural Derivations

Definition:
Transformations that reorganize raw observations without assigning meaning.

Allowed operations:

aggregation

windowing

counting

sorting

bucketing

thresholding on raw quantities

time-delta measurement

spatial (price) clustering

coincidence detection

Examples:

number of liquidations in a price band

total traded volume over Δt

price displacement over N trades

execution density

order book imbalance ratio

velocity measured as Δprice / Δtime

Properties:

reversible in principle

no causal language

no intent claims

no qualitative labels

Admissibility:

Admissible to mandates only as constraints or triggers

Must not be named semantically

Stratum 2 — Semantic Interpretations (Forbidden for Execution)

Definition:
Any transformation that collapses multiple explanations into a labeled interpretation.

Examples:

“liquidity zone”

“stop hunt”

“absorption”

“cascade”

“high conviction”

“strong signal”

“smart money”

“manipulation”

“regime”

“trend strength”

Properties:

theory-dependent

non-reversible

embeds causality or intent

compresses uncertainty

Admissibility:

Forbidden from:

mandate generation

arbitration

execution

Allowed only in:

offline research

visualization

human analysis

A.4 Semantic Elevation Prohibition

No component may:

rename structural data with semantic terms,

re-export structural metrics under interpretive names,

or treat statistical coincidence as causal explanation.

Renaming is considered semantic elevation and is a constitutional violation.

A.5 Consumption Boundary Rule

M1–M3 may compute Stratum 1 data.

M4–M6 may consume Stratum 1 data only as:

boolean conditions,

numeric bounds,

or ordering constraints.

No layer may convert Stratum 1 into Stratum 2 internally.

A.6 Example (Clarifying)

Allowed:

“liquidations_count_in_band > X”

“price_velocity exceeds threshold”

“order book imbalance ratio > Y”

Forbidden:

“liquidation cascade detected”

“absorption confirmed”

“liquidity targeted”

The difference is not math, it is meaning.

ANNEX A — EPISTEMIC DATA ADMISSIBILITY & TRANSFORMATION CONSTITUTION (COMPLETE)
A.7 Naming Neutrality Invariant

All admissible data products must be named in a purely descriptive, non-semantic manner.

Allowed Naming Characteristics

Names may reference only:

observable quantities

mathematical operations

spatial or temporal relations

ordering or comparison

Examples (allowed):

liquidations_count_Δp

price_displacement_Δt

trade_density_bucket

imbalance_ratio_bid_ask

execution_rate

Forbidden Naming Characteristics

Names must not include:

intent

motive

agency

significance

outcome expectation

Examples (forbidden):

cascade

absorption

hunt

trap

smart

weak / strong

aggressive / defensive

manipulation

conviction

Violation of naming neutrality constitutes semantic elevation, regardless of how the value is computed.

A.8 Semantic Leakage Prohibition

No component may infer, derive, or expose latent meaning from admissible data.

Specifically forbidden:

mapping numeric thresholds to narrative states

attaching explanatory comments to data outputs

branching logic that assumes “why” rather than “what”

Examples (forbidden):

“high liquidation density implies forced sellers”

“velocity spike indicates panic”

“imbalance suggests absorption”

Allowed:

“condition X satisfied”

“threshold exceeded”

“constraint active”

This rule applies equally to:

code

configuration

comments

documentation

logs

UI labels

A.9 Historical Memory Constraint

Historical data may be stored and referenced only as raw or structural data.

Forbidden:

caching prior interpretations

persisting semantic labels

tagging regions with meaning derived from past behavior

Allowed:

storing raw event streams

storing aggregated statistics

storing past structural measurements

Examples:

Allowed: “count of liquidations previously observed in this price band”

Forbidden: “known liquidation zone”

Memory must never evolve from measurement into meaning.

A.10 Multi-Use Ambiguity Preservation Rule

If the same structural pattern can support multiple incompatible explanations, the system must preserve ambiguity.

The system must not:

choose between explanations

weight explanations

privilege one interpretation

Instead:

structural conditions may independently trigger different mandates

arbitration resolves conflicts without interpreting cause

This rule directly enables:

partial exit and full exit as coexisting possibilities

opposing mandates under different constraints

non-deterministic outcomes resolved only by authority ordering

A.11 Mandate Compatibility Requirement

Mandates must be formulated exclusively in terms of:

admissible data (Stratum 0 or 1)

position state

risk constraints

lifecycle state

Mandates must never encode:

beliefs

expectations

predictions

confidence levels

market narratives

Mandates describe what to do if X is true, not why X matters.

A.12 Prohibition on Model-Based Assertions

Any model that outputs:

classifications

regimes

states

labels

predictions

is categorically forbidden from:

feeding mandates

influencing arbitration

influencing execution

Models may exist only:

offline

for research

for visualization

for human study

No learned or fitted model output may cross the constitutional boundary.

A.13 Enforcement & Violation Handling

A violation of this annex occurs if any semantic interpretation:

enters a mandate

enters arbitration

enters execution

is persisted for later decision use

Upon violation:

the affected component is considered constitutionally invalid

downstream outputs are void

execution must halt or ignore the offending input

This annex is not advisory.
It is binding.

A.14 Constitutional Status

This annex has equal authority to:

Position & Risk Constraints

Mandate Definitions

Arbitration Rules

Execution Invariants

No future amendment may weaken:

admissibility rules

semantic prohibitions

ambiguity preservation

Permitted amendments may only:

further restrict admissibility

reduce semantic surface

strengthen enforcement

A.15 Final Statement

This system does not trade narratives.
It does not trade beliefs.
It does not trade explanations.

It reacts to facts, constrained by invariants, resolved by authority, and executed without interpretation.

ANNEX A COMPLETE.

ANNEX A — STRATUM-1 PRIMITIVES (RAW-DERIVED, NON-INTERPRETIVE)

Scope: These primitives are the only admissible inputs to mandates, arbitration, or execution.
Source Constraint: All primitives MUST be derivable directly from raw event streams.
Prohibition: No primitive may encode meaning, expectation, intent, regime, or outcome.

A1. PRICE-DERIVED PRIMITIVES
A1.1 Price Displacement
price_delta = last_price - reference_price


Reference must be explicitly declared (e.g., previous tick, previous bar close)

No implied direction significance

A1.2 Price Displacement Rate
price_delta / time_delta


Pure kinematic measurement

No “velocity”, “momentum”, or urgency semantics permitted

A1.3 Directional Consistency Counter
consecutive_price_moves_same_sign


Counts only

No trend inference allowed

A1.4 Wick Penetration Depth
wick_depth = high_or_low - close


Measured per event window

No rejection or intent implied

A2. TIME PRIMITIVES
A2.1 Event Interarrival Time
Δt = timestamp(n) - timestamp(n-1)


Used only as numeric input

Cannot be labeled “fast”, “slow”, “stall”

A2.2 Event Density
event_count / Δt


No activity or participation interpretation

A3. TRADE-FLOW PRIMITIVES
A3.1 Trade Count
trade_count(symbol, Δt)

A3.2 Trade Size Distribution
trade_size_percentiles(symbol, Δt)


Percentiles only

No “large order” designation allowed

A3.3 Signed Trade Imbalance
Σ(buy_volume) - Σ(sell_volume)


Sign is arithmetic, not directional bias

A3.4 Trade Notional Delta
Σ(price * quantity) over Δt


No inference about commitment or absorption

A4. LIQUIDATION-DERIVED PRIMITIVES
A4.1 Liquidation Event Count
liquidation_count(symbol, Δt)


No cascade, no pressure, no implication

A4.2 Liquidation Notional Sum
Σ(liquidation_notional) over Δt

A4.3 Liquidation Density by Price Band
liquidation_count(price_band, Δt)


Historical only

No persistence beyond explicit lookback

A4.4 Liquidation Rate
liquidation_count / Δt


Rate only, no escalation semantics

A5. PRICE-BAND AGGREGATIONS
A5.1 Trade Density by Price Band
trade_count(price_band, lookback=N)

A5.2 Volume Concentration by Price Band
Σ(volume) per price_band


No “liquidity zone” naming permitted

A5.3 Price Occupancy Duration
time_spent(price_band)


No support/resistance semantics

A6. ORDERBOOK-PROXY PRIMITIVES (IF AVAILABLE)

(Only if raw order book events exist — otherwise forbidden)

A6.1 Visible Depth Snapshot
Σ(size) at price levels at timestamp t

A6.2 Depth Change Delta
depth(t) - depth(t-1)


No inference of intent or absorption

A7. MEMORY-SAFE HISTORICAL PRIMITIVES

Critical Rule: History may be measured, never remembered.

A7.1 Rolling Window Aggregates
metric_over_last_N_events


Window must be explicit

No implicit “important past”

A7.2 Historical Extremum (Declared Scope)
max(metric) over last N events
min(metric) over last N events


No “significance” allowed

A8. FORBIDDEN TRANSFORMATIONS (EXPLICIT)

The following are permanently illegal:

Any primitive that:

combines multiple primitives into meaning

implies expectation or attraction

labels a condition as favorable/unfavorable

references “zones”, “hunts”, “absorption”, “pressure”, “regime”

Examples (FORBIDDEN):

liquidation cascade

stop hunt

liquidity magnet

absorption zone

smart money activity

trapped traders

A9. PRIMITIVE OUTPUT CONTRACT

Each primitive must declare:

name
raw_source
window_definition
units
expiration_scope


No primitive may:

persist across cycles without re-derivation

influence interpretation

survive outside declared scope

FINAL STRATUM-1 GUARANTEE

These primitives describe only what happened, never what it means.

They are:

causally blind

intention-agnostic

constitutionally admissible

ANNEX B — MANDATE REWRITE USING STRATUM-1 PRIMITIVES ONLY

Scope: This annex replaces all previously implied mandate logic.
Guarantee: No mandate may consume interpreted, aggregated, labeled, or semantic data.
Invariant: Mandates operate on facts only, never explanations.

B1. Mandate Input Contract (Revised)

A mandate MAY consume only:

Current Position State

Current Symbol Exposure State

Current Stratum-1 primitives (Annex A)

Explicit lookback-scoped aggregates declared at mandate definition

A mandate MUST NOT consume:

Zones

Patterns

Signals

Regimes

Narratives

Historical memory beyond declared window

B2. Entry Mandate (Stratum-1 Safe)
B2.1 ENTRY Mandate Definition
ENTRY_MANDATE


Permitted Inputs:

price_delta

price_delta_rate

trade_count

liquidation_count

trade_size_percentiles

price_band_occupancy

position_state == FLAT

Forbidden Inputs:

liquidation cascades

stop hunts

support/resistance

prior “zones”

velocity labels

B2.2 Example ENTRY Conditions (Fact-Only)
IF
  liquidation_count(price_band=X, Δt=T) ≥ N
AND
  trade_count(Δt=T) ≥ M
AND
  price_delta within band_bounds
AND
  position_state == FLAT
THEN
  EMIT ENTRY


Notes:

No direction implied

Direction is assigned only at execution time

Mandate does not “expect” continuation or reversal

B3. Exit Mandate (Stratum-1 Safe)
B3.1 EXIT Mandate Definition
EXIT_MANDATE


Permitted Inputs:

adverse price_delta magnitude

liquidation_rate change

time_in_position

position_state ∈ {OPEN, REDUCING}

B3.2 Example EXIT Conditions
IF
  |price_delta| ≥ declared_adverse_threshold
OR
  liquidation_rate drops below declared_floor
OR
  time_in_position ≥ max_duration
THEN
  EMIT EXIT


No profit, loss, strength, or conviction encoded.

B4. Reduce Mandate (Stratum-1 Safe)
B4.1 REDUCE Mandate Definition
REDUCE_MANDATE


Permitted Inputs:

trade_density increase

liquidation_density increase

price_band_overlap with prior high-density bands

B4.2 Example REDUCE Conditions
IF
  trade_density(price_band=X, Δt=T) increases by ≥ K
AND
  position_state == OPEN
THEN
  EMIT REDUCE


Important:
REDUCE does not encode “partial profit taking” — it encodes exposure contraction only.

B5. BLOCK Mandate (Stratum-1 Safe)
B5.1 BLOCK Mandate Definition
BLOCK_MANDATE


Purpose: Prevent ENTRY, nothing else.

Permitted Inputs:

event_density collapse

trade_count below declared minimum

missing raw feeds

B5.2 Example BLOCK Conditions
IF
  trade_count(Δt=T) < min_required
OR
  raw_feed_missing == TRUE
THEN
  EMIT BLOCK

B6. HOLD Mandate (Stratum-1 Safe)

HOLD is absence of change, not conviction.

IF
  no other mandate emitted
THEN
  HOLD

B7. Mandatory Mandate Properties (Reaffirmed)

Every mandate must declare:

raw primitives consumed

window sizes

expiry condition

symbol scope

authority rank

ANNEX C — RESEARCH-ONLY SEMANTIC LAYER (NON-EXECUTABLE)

This layer is explicitly NON-ACTIONABLE.

C1. Purpose of Semantic Layer

To allow human research, labeling, and hypothesis formation
WITHOUT contaminating execution, mandates, or arbitration.

This layer:

MAY use interpretation

MAY use narrative

MAY use historical memory

MAY use human language

This layer:

MUST NEVER emit mandates

MUST NEVER influence execution

MUST NEVER be imported into runtime code

C2. Allowed Semantic Constructs (Research Only)

Examples (allowed here, forbidden elsewhere):

“liquidation cascade”

“stop hunt region”

“absorption”

“liquidity zone”

“market narrative”

“weekly bias”

These are labels, not data.

C3. Hard Separation Invariant
RESEARCH_LAYER ⟂ EXECUTION_LAYER


Violations include:

exporting signals

exporting zones

exporting confidence

exporting thresholds

C4. Research Output Contract

Research outputs MAY ONLY be:

markdown

charts

annotations

comments

notebooks

Research outputs MUST NOT be:

imported

serialized into runtime

referenced by mandates

referenced by M6

C5. Semantic Decay Rule

All research artifacts are:

non-binding

non-persistent

disposable

No semantic conclusion survives into execution.

C6. Final Boundary Statement

Execution is blind.
Research is free.
The boundary is absolute.

ANNEX D — AUDIT OF EXISTING PRIMITIVES AGAINST ANNEX A

Purpose:
Identify and eliminate hidden semantic leakage inside primitives that appear factual but implicitly encode interpretation.

D1. Audit Method

Each primitive is evaluated against this test:

If the primitive answers “what does this mean?” instead of “what happened?”, it is non-compliant.

D2. Primitive Audit Results
❌ NON-COMPLIANT (Semantic Leakage Detected)
Primitive	Hidden Meaning	Reason for Rejection
liquidation_cascade	“forced continuation”	Encodes interpretation of sequence
stop_hunt_region	“intentional liquidity grab”	Assumes motive
absorption	“large players defending”	Intent inference
imbalance	“unfair price move”	Qualitative judgment
pressure	“directional force”	Implies expectation
velocity_spike	“unusual activity”	Comparative semantic

All of the above are research labels, not facts.

✅ COMPLIANT (Stratum-1 Safe)
Primitive	Why Allowed
liquidation_count	Pure event count
trade_count	Observable
trade_size_percentiles	Statistical, not interpretive
price_delta	Measured
price_delta_rate	Measured
time_in_band	Measured
feed_gap_duration	Measured
D3. Mandatory Rewrite Rule

Any rejected primitive must be rewritten as:

count

duration

magnitude

rate

percentile

boolean feed state

No exceptions.

D4. Enforcement Invariant

No execution-reachable code may reference a rejected primitive, even if renamed.

Renaming “liquidation_cascade” → “liq_chain” is still a violation.

ANNEX E — RAW DATA INGESTION & PRIMITIVE INTEGRITY GUARANTEES

This annex formalizes your insight:
👉 Only raw data streams are constitution-compliant.

E1. Raw Data Definition

Raw data is defined as:

Exchange trades

Exchange liquidations

Order book updates (L2/L3)

Funding updates

Open interest updates

Timestamps from exchange payloads

E2. Prohibited Inputs

Execution MUST NOT ingest:

Indicator outputs (RSI, VWAP, etc.)

Aggregated candles (OHLCV)

Zones

Signals

External analytics APIs

“Pre-cleaned” or labeled datasets

E3. Primitive Construction Rule

Primitives MAY ONLY be derived via:

counting

summing

bucketing

ranking

percentiles

sliding windows

Primitives MUST NOT include:

trend detection

regime classification

pattern recognition

clustering

classification

prediction

E4. Determinism Requirement

Given the same raw stream + same window parameters:

Primitive outputs MUST be identical.

No adaptive thresholds.
No learning.
No calibration.

E5. Time Anchoring Rule

All primitives are anchored to:

exchange timestamps only

monotonic internal clock

Wall-clock inference is forbidden.

E6. Failure Mode

If raw data is missing, delayed, or corrupted:

→ EMIT BLOCK
→ NO RECOVERY LOGIC
→ NO SUBSTITUTION


Silence is preserved.

ANNEX F — EXPOSURE & RISK INVARIANTS (RAW-ONLY)

This annex upgrades earlier risk logic to be fully Annex-A compliant.

F1. Exposure Definition (Revised)

Exposure is defined strictly as:

exposure = position_size × price


No confidence.
No conviction.
No “edge”.

F2. Position Count Invariant

Per symbol:

MAX_POSITIONS = 1


Global:

Σ exposure(symbols) ≤ MAX_ACCOUNT_EXPOSURE

F3. Leverage Constraint (Liquidation-Aware)

Leverage is constrained by distance to liquidation, not fixed numbers.

IF
  liquidation_price_distance ≤ declared_floor
THEN
  ENTRY forbidden


Distance is a raw numeric fact.

F4. Reduction vs Exit Rule
Condition	Action
exposure too large	REDUCE
adverse price_delta breach	EXIT
feed integrity failure	EXIT
raw volatility explosion	REDUCE or EXIT (mandate arbitration decides)
F5. Partial Exit Legitimacy

Partial exits are allowed only as REDUCE mandates, never semantic “profit taking”.

REDUCE is justified by:

exposure contraction

volatility expansion

density increase

F6. Forbidden Risk Constructs

Execution MUST NOT use:

“risk-reward ratio”

“expected value”

“probability”

“confidence”

“edge”

“setup quality”

F7. Terminal Invariant

Risk management is arithmetic, not belief.

ANNEX G — ORDER BOOK & MICROSTRUCTURE PRIMITIVES (RAW-SAFE)

Purpose:
Permit use of order book data without embedding intent, support/resistance, or “smart money” narratives.

G1. Allowed Order Book Inputs

Only the following raw inputs are admissible:

price_level

size

side (bid / ask)

timestamp

update_type (add / remove / modify)

No aggregation beyond deterministic bucketing.

G2. Allowed Order Book Primitives

All primitives must be count-, size-, or time-based.

Compliant primitives:

total_bid_size

total_ask_size

bid_ask_size_ratio

size_delta_over_window

order_add_rate

order_remove_rate

order_modify_rate

price_levels_touched

time_at_best_bid

time_at_best_ask

G3. Forbidden Order Book Constructs

The following are explicitly prohibited:

support / resistance

absorption

spoofing

iceberg

defense

intention

smart money

imbalance (semantic)

pressure

dominance

Any construct that implies purpose or strategy is illegal.

G4. Order Book Determinism Invariant

Given identical order book events and window parameters:

Output MUST be identical.

No smoothing.
No adaptive thresholds.
No normalization against history.

G5. Execution Safety Rule

Order book primitives:

MAY influence REDUCE or EXIT

MUST NOT justify ENTRY alone

MUST NOT override exposure constraints

ANNEX H — TIME & WINDOW GOVERNANCE

Purpose:
Prevent temporal interpretation, regime bias, or hidden “session logic”.

H1. Time Source Invariant

Only two time sources exist:

Exchange timestamp (primary)

Internal monotonic clock (secondary)

Wall-clock time is forbidden.

H2. Window Definition

A window is defined strictly as:

[start_timestamp, end_timestamp]


Windows are:

fixed

declared

non-adaptive

H3. Window Types (Allowed)

sliding

tumbling

expanding (bounded)

No “event-aligned” or “market phase” windows.

H4. Multi-Window Rule

Multiple windows MAY coexist, but:

No window may infer meaning from another

No hierarchy of “importance” is allowed

H5. Window Failure Mode

If a window cannot be populated fully:

→ primitive = NULL
→ mandate = BLOCK


No backfilling.
No interpolation.

ANNEX I — MEMORY & HISTORICAL DATA USE

Purpose:
Allow memory without narrative.

I1. Memory Definition

Memory is defined as:

A frozen, read-only record of prior raw primitives.

Memory is not a model.

I2. Allowed Memory Operations

lookup

comparison

distance

frequency

percentile ranking

I3. Forbidden Memory Operations

similarity scoring

pattern matching

clustering

labeling

trend inference

“looks like last time”

I4. Memory Integrity Rule

Memory entries must include:

raw input provenance

window definition

construction parameters

Memory without provenance is invalid.

I5. Memory Use Limitation

Memory MAY:

constrain exposure

trigger REDUCE / EXIT

Memory MUST NOT:

justify ENTRY

modify authority ranking

alter mandate arbitration

ANNEX J — FAILURE, SILENCE & HALT SEMANTICS

Purpose:
Ensure the system fails honestly.

J1. Silence Definition

Silence means:

insufficient data

ambiguous data

conflicting mandates

violated invariant

Silence is not a signal.

J2. Silence Handling

When silence occurs:

→ NO ENTRY
→ NO REDUCE
→ NO EXIT
→ BLOCK emitted

J3. Failure Definition

Failure is defined as:

invariant violation

arithmetic impossibility

data corruption

time regression

J4. Failure Handling

On failure:

→ EXIT (if position exists)
→ HALT symbol
→ no recovery

J5. Operator Interaction Prohibition

Operators:

may observe

may halt globally

Operators must NOT:

override mandates

inject trades

unblock symbols

ANNEX K — RESEARCH / EXECUTION FIREWALL

Purpose:
Formally separate thinking from acting.

K1. Research Layer Permissions

Research may:

name patterns

label regimes

interpret intent

simulate strategies

K2. Execution Layer Prohibitions

Execution MUST NOT ingest:

research outputs

labels

scores

signals

probabilities

classifications

K3. Translation Rule

The ONLY allowed bridge from research → execution is:

manual extraction of raw-safe primitives

No automated pipelines allowed.

K4. Auditability Requirement

Every execution primitive must trace to:

raw stream → window → arithmetic → primitive


If trace fails → primitive invalid.

ANNEX L — COMPLETENESS & LOCK
L1. System Completeness Declaration

This constitution now fully defines:

observation

primitives

mandates

arbitration

execution

risk

failure

memory

time

data provenance

No undefined behavior remains.

L2. Amendment Rule

Amendments:

MAY add stricter constraints

MUST NOT weaken any annex

MUST include audit of downstream effects

L3. Final Lock Statement

This system does not predict.
This system does not interpret.
This system does not believe.
This system acts only on facts and invariants.

