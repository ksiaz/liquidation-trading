IMPLEMENTATION ROADMAP
From Conceptual Framework to Production System

This document translates HLP1-8 into a concrete build sequence.
It respects the rulebook constraints and acknowledges hardware limitations.

The goal is not to build everything at once.
The goal is to build in the correct order, so each layer strengthens the next.

---

PHASE 0 — STRUCTURAL VALIDATION (Do This First)

Before writing any integration code, validate structural feasibility.

Why this matters:

If the node client has blocking imports
If strategies have circular dependencies
If the state builder cannot run independently

Then the entire plan fails before you start.

Actions:

1. Enumerate all module imports executed at load time
2. Expand the transitive dependency graph
3. Identify side-effect imports
4. Verify no circular dependencies exist
5. Confirm strategies can be imported without starting the runtime

If this fails, the system is structurally unbuildable.
Fix imports before proceeding.

Expected outcome:
STRUCTURE OK — PROCEED

---

PHASE 1 — DATA INGESTION FOUNDATION

This is the foundation. Nothing works without it.

1.1 — Node Client Wrapper

Build a clean abstraction over the Hyperliquid node API.

Requirements:

Must handle:
  - WebSocket reconnection
  - Subscription management
  - Sequence number tracking
  - Heartbeat/keepalive

Must not:
  - Interpret data
  - Aggregate
  - Filter
  - Block on downstream consumers

Output:
Raw messages with timestamp + sequence number

Implementation status:
node_client.py exists but needs validation

1.2 — Message Persistence Layer

Every message from the node must be logged for replay.

Format:
Append-only, timestamped, sequenced

Storage:
Local disk initially
Can migrate to database later

Why this is non-negotiable:

Without this, you cannot:
  - Debug false positives
  - Replay liquidation cascades
  - Validate strategy logic
  - Improve heuristics

This is where edge compounds over time.

1.3 — Health Monitoring

The node client must detect:

Connection loss
Sequence gaps
Heartbeat timeouts
Data staleness

On failure:

Log the issue
Attempt reconnection
Do not trade during uncertainty

Markets do not pause for your bugs.

Expected deliverables:
✓ node_client.py validated
✓ Append-only message log
✓ Reconnection logic tested
✓ Sequence gap detection working

---

PHASE 2 — STATE NORMALIZATION (Where Edge Lives)

Raw node data is noise. This layer creates coherent market state.

2.1 — State Builder Service

This is the physics engine.

Responsibilities:

Maintain authoritative L2 orderbook
Track mark price
Track open interest
Track funding rate
Detect depth thinning
Classify aggressive vs passive flow
Measure book refill behavior

Critical rules:

Single writer, multiple readers
Lock-free reads
State updates must be atomic
No strategy logic here

2.2 — Rolling Window Aggregates

Strategies need context, not just snapshots.

Required windows:

1-second: Tick behavior
5-second: Microstructure shifts
15-minute: Regime classification
1-hour: Structural trends

For each window:

OI change
Volume (buy vs sell)
Funding drift
Depth asymmetry

All windows must:

Handle warm-up periods
Return NULL until initialized
Never use future data

2.3 — Derived Event Detection

The state builder emits structural events, not opinions.

Examples:

"OI dropped 5% in 10 seconds"
"Bid depth < 100k within 20bps"
"Aggressive buying failed to move price"
"Funding acceleration detected"

These are facts, not signals.

Strategies subscribe to these events.

Expected deliverables:
✓ State builder service running
✓ Rolling windows implemented
✓ Event emission working
✓ No data leakage (validated via tests)

---

PHASE 3 — HOT STATE STORE

This is what strategies read synchronously.

3.1 — In-Memory Store Design

Properties:

Lock-free reads
Single writer (state builder)
Multiple readers (strategies)
Precomputed ratios

Contents:

Latest L2 snapshot
Rolling aggregates (1s, 5s, 15m, 1h)
Ratios: depth vs OI, funding velocity
Wallet activity flags (placeholder for now)

Critical performance requirement:

Read latency < 100 microseconds
No blocking
No allocations on read path

3.2 — Shared Memory Implementation

The state builder and strategies must share state efficiently.

Options:

Shared memory segment (best)
Memory-mapped file (acceptable)
Lock-free ring buffer (advanced)

Do not use:

Sockets
Pipes
Polling files

3.3 — State Staleness Detection

Strategies must know if data is stale.

Each state update includes:

Timestamp (node time)
Sequence number
Age (time since update)

If state is stale:

Strategy must not trade
Log the issue
Wait for recovery

Expected deliverables:
✓ Hot state store implemented
✓ Sub-100μs read latency
✓ Staleness detection working
✓ Multiple readers validated

---

PHASE 4 — REGIME CONTROLLER (Master Orchestrator)

This is the single source of truth for strategy activation.

4.1 — Regime Classification Logic

The controller determines which regime is active.

Regimes (from rulebook):

Sideways:
  - OI stable
  - Funding neutral
  - Depth symmetrical

Expansion:
  - OI rising
  - Funding skewed
  - Depth asymmetrical

Disabled:
  - None of the above clearly true

Critical rule:

If conditions are ambiguous, regime = DISABLED

4.2 — Strategy Enable/Disable Gates

Strategies do not self-activate.

The controller:

Reads hot state
Classifies regime
Enables/disables strategies

Example:

If regime == SIDEWAYS:
  Enable: Geometry, Kinematics
  Disable: Cascade

If regime == EXPANSION:
  Enable: Cascade
  Disable: Geometry, Kinematics

If regime == DISABLED:
  Disable: ALL

4.3 — Mutual Exclusion Enforcement

At no time may conflicting strategies be active simultaneously.

Hard rule:

SLBRS and EFFCS cannot both be enabled

Enforcement:

Controller-level, not strategy-level
Strategies cannot override this
Log all activation/deactivation events

Expected deliverables:
✓ Regime classifier implemented
✓ Strategy gates working
✓ Mutual exclusion enforced
✓ Logging complete

---

PHASE 5 — SINGLE STRATEGY VALIDATION

Do not build all strategies at once.

Pick one. Get it right.

5.1 — Choose: Geometry (Recommended)

Why Geometry first:

Simpler than Cascade
More deterministic than Kinematics
Clear invalidation conditions

5.2 — State Machine Implementation

Implement the exact state machine from HLP10 (to be created).

States:

DISABLED
SCANNING
ARMED
ENTERED
EXITED
COOLDOWN

Transitions must be explicit and tested.

5.3 — Unit Tests (Non-Negotiable)

Every state transition must have:

Valid transition test
Invalid transition test
Forced reset test

Every invalidation condition must have:

Trigger test
No-trigger test

If tests fail, the strategy is not ready.

5.4 — Replay Validation

Use saved node data to replay historical events.

Validate:

No data leakage (only past data used)
Deterministic behavior (same inputs → same outputs)
Correct invalidation handling

Expected deliverables:
✓ Geometry strategy implemented
✓ State machine validated
✓ Unit tests passing
✓ Replay validation complete

---

PHASE 6 — EXECUTION LAYER

Strategies emit intents. Execution translates intents to orders.

6.1 — Intent Schema

Strategies do not place orders directly.

They emit:

direction (LONG/SHORT)
size (percentage of capital)
stop (exact price)
target (exact price)
reason (for logging)

6.2 — Execution Service

Translates intents to orders:

Validates risk
Checks position limits
Submits orders
Monitors fills

Critical rule:

Execution keys are isolated from strategies

6.3 — Position Management

Tracks:

Open positions
Unrealized PnL
Risk exposure

On invalidation:

Close immediately at market
Do not wait
Do not hedge

Expected deliverables:
✓ Intent schema defined
✓ Execution service working
✓ Position tracking accurate
✓ Emergency exit tested

---

PHASE 7 — ADDITIONAL STRATEGIES

Only after Geometry works end-to-end.

7.1 — Add Kinematics

Use the same pattern:

State machine
Unit tests
Replay validation

7.2 — Add Cascade

Most complex. Do last.

7.3 — Validate Mutual Exclusion

With multiple strategies active:

Ensure only one can trade at a time
Validate regime transitions
Test edge cases

Expected deliverables:
✓ All strategies implemented
✓ Regime switching validated
✓ No conflicts observed

---

PHASE 8 — WALLET TRACKING LAYER (Advanced)

This is the final layer. Do not attempt until everything else works.

8.1 — Wallet Activity Detection

Subscribe to transaction feeds
Identify large wallets
Track activity patterns

8.2 — Behavioral Classification

Detect:

Short holding time
Entry timing (pre-liquidation)
Exit timing (post-cascade)

8.3 — Integration with Strategies

Add wallet context to hot state:

is_manipulator_active (boolean)
manipulator_direction (LONG/SHORT/NONE)

Strategies incorporate this as an additional filter.

Expected deliverables:
✓ Wallet tracking working
✓ Behavior classification validated
✓ Strategy integration tested

---

PHASES 9+ — FUTURE ENHANCEMENTS

After all above is working:

Cross-venue monitoring
Funding snapback detection
Failed hunt classifier
Post-liquidation inventory tracking

Do not attempt these until core system is production-ready.

---

WHAT YOU CAN BUILD WITHOUT THE NODE

While waiting for hardware:

State builder (using mock data)
Hot state store
Regime controller
Strategy state machines
Unit tests
Execution service (paper trading)
Replay system (using saved logs from hired VM)

What you cannot build:

Node client validation
Latency optimization
Real-time behavior under stress

---

CRITICAL PATH (Minimum Viable System)

If you want to trade as soon as hardware arrives:

1. Node client (already exists, needs validation)
2. State builder
3. Hot state store
4. Regime controller
5. Geometry strategy
6. Execution service

Skip:

Kinematics
Cascade
Wallet tracking

Get one strategy profitable first.

---

FAILURE MODES TO DESIGN FOR

Every phase must handle:

Data loss
Connection loss
Sequence gaps
Stale state
Strategy exceptions
Execution failures

If any of these occur:

Stop trading
Log the issue
Do not attempt recovery without validation

Visibility over continuity.

---

TESTING STRATEGY

Each component must have:

Unit tests (state transitions)
Integration tests (component interaction)
Replay tests (historical data)
Stress tests (resource limits)

If tests do not pass:

The component is not ready

---

MEASUREMENT CRITERIA

How you know each phase is complete:

Phase 1: Can ingest and log node data without loss
Phase 2: State reflects reality with < 1ms lag
Phase 3: Multiple readers never block
Phase 4: Regime classification matches manual analysis
Phase 5: Strategy triggers match expected behavior
Phase 6: Orders execute correctly
Phase 7: Multiple strategies coexist without conflict
Phase 8: Wallet tracking provides additional observables (HYPOTHESIS - requires validation)

---

BOTTOM LINE

The implementation order is:

Data ingestion → State building → Hot state → Regime control → One strategy → Execution → Additional strategies → Wallet tracking

Each phase builds on the previous.

Skipping phases creates technical debt you will pay later.

The system is only as strong as its weakest layer.

Build correctly, not quickly.
