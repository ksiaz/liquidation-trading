EVENT LIFECYCLE AWARENESS
Preventing Temporal Confusion in Real-Time Systems

The Problem:

Your system sees that OI dropped 20%.
But it doesn't know:

- Is this drop happening RIGHT NOW?
- Did it happen 5 minutes ago and stabilize?
- Is the cascade still ongoing?
- Are we in the reversal phase already?

Without temporal awareness:

Strategies enter after events complete (chasing)
Strategies stay positioned during exhausted events
Agents insist events are "in progress" when they're over
No distinction between detection, execution, and completion

This is not a backtesting problem.
This is a real-time state management problem.

---

ROOT CAUSE: SNAPSHOT THINKING

Most systems (and agents) operate on snapshots:

Current OI: 80M
Previous OI: 100M
Change: -20%

But this tells you NOTHING about:

When did the drop happen?
How fast was the drop?
Has it stopped?
How long has it been stable?

Snapshot thinking creates temporal blindness.

---

THE SOLUTION: EVENT LIFECYCLE TRACKING

Every event must have explicit lifecycle states.

Event Lifecycle States:

1. DETECTED
   - Preconditions met
   - Event likely to occur
   - NOT yet triggered

2. TRIGGERED
   - Event initiation confirmed
   - Entry window open
   - IN PROGRESS

3. ACTIVE
   - Event executing
   - Conditions still present
   - Monitor for completion

4. COMPLETING
   - Event showing exhaustion signals
   - Prepare for exit
   - Transition phase

5. COMPLETED
   - Event finished
   - Entry window closed
   - Post-event state

6. EXPIRED
   - Event data stale
   - No longer actionable
   - Archive

Each state transition is timestamped and logged.

---

CONCRETE EXAMPLE: LIQUIDATION CASCADE

Snapshot View (Broken):

OI dropped from 100M to 80M
Volume spiked
Funding dropped

Question: Is the cascade happening now?
Answer from snapshot: UNKNOWN

Lifecycle View (Correct):

Event ID: cascade_BTC_20260121_070000
State: COMPLETED
Lifecycle history:

  DETECTED      07:00:00.123  (OI elevated, funding skewed)
  TRIGGERED     07:01:15.456  (OI started dropping rapidly)
  ACTIVE        07:01:15.500  (Drop ongoing, -5% so far)
  ACTIVE        07:01:18.200  (Drop ongoing, -15% so far)
  COMPLETING    07:01:20.800  (Drop slowing, volume peaked)
  COMPLETED     07:01:22.100  (OI stabilized at 80M)
  EXPIRED       07:06:22.100  (5 minutes passed, no longer fresh)

Current time: 07:08:00
State: EXPIRED
Entry window: CLOSED (missed by 6+ minutes)

Now the system KNOWS:
  - Cascade already happened
  - Too late to enter
  - Don't chase

---

IMPLEMENTATION: EVENT OBJECTS

Every event is a first-class object with state.

Base Event Structure:

event_id: string (unique, monotonic)
event_type: enum (LIQUIDATION_CASCADE, FUNDING_SNAPBACK, etc.)
symbol: string
lifecycle_state: enum (DETECTED, TRIGGERED, ACTIVE, COMPLETING, COMPLETED, EXPIRED)
created_at: int64 (nanoseconds, when first detected)
updated_at: int64 (nanoseconds, last state change)
state_history: array of StateTransition

StateTransition:
  from_state: enum
  to_state: enum
  timestamp: int64
  trigger_reason: string
  metrics_snapshot: JSON (OI, funding, depth, etc.)

Event-Specific Data:

For LIQUIDATION_CASCADE:
  oi_before: int64
  oi_current: int64
  oi_drop_pct: int32 (basis points)
  drop_start_time: int64
  drop_end_time: int64 (nullable, only set when completed)
  peak_volume: int64
  exhaustion_detected: bool
  entry_window_open: bool

Methods:

is_actionable() -> bool:
  Returns: lifecycle_state in [TRIGGERED, ACTIVE, COMPLETING]

time_since_detection() -> int64:
  Returns: current_time - created_at

time_in_current_state() -> int64:
  Returns: current_time - updated_at

is_stale() -> bool:
  Returns: time_since_detection() > staleness_threshold

should_expire() -> bool:
  Returns: lifecycle_state == COMPLETED AND time_in_current_state() > expiration_timeout

---

STATE TRANSITION LOGIC

Transitions must be explicit and rule-based.

Example: Liquidation Cascade State Machine

DETECTED → TRIGGERED
Condition:
  OI starts dropping (rate > threshold)
  Volume spikes
  Price accelerates

TRIGGERED → ACTIVE
Condition:
  OI drop continues
  Drop_pct > 5%

ACTIVE → COMPLETING
Condition:
  OI drop rate decelerating
  Volume peaked and declining
  Price stopped extending

COMPLETING → COMPLETED
Condition:
  OI stabilized (change < threshold for N seconds)
  Volume returned to baseline
  Aggressive flow ended

COMPLETED → EXPIRED
Condition:
  Time since completion > expiration_timeout (e.g., 5 minutes)

Critical Rules:

No state skipping (must follow sequence)
Each transition timestamped
Each transition includes metrics snapshot
State cannot regress (no COMPLETED → ACTIVE)

If conditions reverse (e.g., OI starts rising again):
  Create NEW event
  Don't revert state of old event

---

EVENT REGISTRY

Global registry tracks all active events.

Structure:

active_events: Map<event_id, Event>

Operations:

register_event(event: Event):
  Add to active_events
  Emit EVENT_DETECTED notification

update_event_state(event_id: string, new_state: enum, reason: string):
  Fetch event from registry
  Validate state transition
  Update event.lifecycle_state
  Append to event.state_history
  Update event.updated_at
  Emit EVENT_STATE_CHANGED notification

get_active_events(event_type: enum) -> array<Event>:
  Return events where lifecycle_state in [DETECTED, TRIGGERED, ACTIVE, COMPLETING]

expire_stale_events():
  For each event:
    If should_expire():
      Update state to EXPIRED
      Archive event
      Remove from active_events

Clean-up:

Run expire_stale_events() every second
Archive expired events to cold storage
Keep active registry small (< 100 events)

---

STRATEGY INTEGRATION

Strategies consume events, not raw snapshots.

Old Approach (Broken):

def should_enter(self):
    oi_drop = self.state.oi_pct_change_5s
    if oi_drop < -5:  # OI dropped 5%
        return True  # Enter!
    
Problem: No awareness of WHEN drop happened or if it's still ongoing

New Approach (Correct):

def should_enter(self):
    cascade_event = self.event_registry.get_active_events(LIQUIDATION_CASCADE)
    
    if not cascade_event:
        return False  # No active cascade
    
    if cascade_event.lifecycle_state != COMPLETING:
        return False  # Not at exhaustion point yet
    
    if cascade_event.time_since_detection() > 60_000:  # 60 seconds
        return False  # Too old, don't chase
    
    if not cascade_event.entry_window_open:
        return False  # Window closed
    
    # All checks passed, event is fresh and actionable
    return True

Benefits:

Knows if event is happening NOW vs happened BEFORE
Knows where in event lifecycle we are
Knows if entry window is still open
Prevents chasing stale events

---

TEMPORAL AWARENESS IN STATE BUILDER

State builder is responsible for event lifecycle management.

Responsibilities:

1. Detect event initiation
2. Update event state as conditions evolve
3. Detect event completion
4. Expire stale events
5. Emit notifications on state changes

Example: Cascade Detection and Tracking

continuous_monitoring():
    
    while True:
        current_state = read_hot_state()
        
        # Check for new cascade initiation
        if not cascade_active AND detect_cascade_trigger(current_state):
            event = create_cascade_event(current_state)
            event.lifecycle_state = TRIGGERED
            register_event(event)
            notify_strategies(EVENT_TRIGGERED, event)
        
        # Update existing cascade
        if cascade_active:
            event = get_event(cascade_event_id)
            
            if detect_cascade_exhaustion(current_state):
                update_event_state(event.id, COMPLETING, "exhaustion detected")
                notify_strategies(EVENT_COMPLETING, event)
            
            elif detect_cascade_completion(current_state):
                update_event_state(event.id, COMPLETED, "cascade ended")
                event.entry_window_open = False
                notify_strategies(EVENT_COMPLETED, event)
        
        # Expire old events
        expire_stale_events()
        
        sleep(100ms)

Key Points:

Continuous evaluation (not one-time check)
Explicit state updates
Entry window flag management
Expiration handling

---

AGENT/OBSERVER AWARENESS

When an agent (or you) queries the system, it must show event lifecycle.

Bad Response:

"OI dropped 20%, cascade detected"

Problem: No temporal context

Good Response:

"Liquidation cascade event (ID: cascade_BTC_20260121_070100)
 State: COMPLETED (as of 07:01:22)
 Lifecycle: DETECTED → TRIGGERED → ACTIVE → COMPLETING → COMPLETED
 OI drop: 100M → 80M (-20%)
 Duration: 22 seconds (07:01:00 to 07:01:22)
 Current time: 07:08:00
 Time since completion: 6 minutes 38 seconds
 Entry window: CLOSED
 Action: Do not enter, event is stale"

Now it's clear:
  - Cascade happened in the past
  - It's over
  - Too late to act

---

LOGGING FOR AWARENESS

Every event state transition must be logged.

Log entry format:

{
  "timestamp": 1737441682123456789,
  "event_id": "cascade_BTC_20260121_070100",
  "event_type": "LIQUIDATION_CASCADE",
  "lifecycle_state": "COMPLETED",
  "transition": {
    "from": "COMPLETING",
    "to": "COMPLETED",
    "reason": "OI stabilized for 5 seconds",
    "metrics": {
      "oi": 80000000,
      "oi_change_rate": 0.001,
      "volume_5s": 150000,
      "funding": -0.005
    }
  }
}

Benefits:

Replay knows exact event timeline
Strategies can be debugged
Agents can understand what happened when

---

EXPIRATION VS COMPLETION

Critical distinction:

COMPLETED: Event finished naturally
EXPIRED: Event data is too old to act on

Example:

Cascade completes at 07:01:22
Entry window closes at 07:01:22
Event expires at 07:06:22 (5 minutes later)

Between 07:01:22 and 07:06:22:
  - Event is COMPLETED (don't enter)
  - But still in registry (for post-analysis)

After 07:06:22:
  - Event is EXPIRED (archived)
  - Removed from active registry

Expiration prevents registry bloat.

---

TIMEOUT ENFORCEMENT

Events must timeout if they don't complete normally.

Example: Failed Hunt Detection

Cascade enters TRIGGERED state at 07:00:00
Expected progression: TRIGGERED → ACTIVE → COMPLETING → COMPLETED

But what if:
  - OI stops dropping before cascade threshold
  - Never reaches ACTIVE
  - Stuck in TRIGGERED

Timeout rule:

If lifecycle_state == TRIGGERED for > 30 seconds:
  Force transition to COMPLETED (failed hunt)
  Reason: "timeout - cascade did not develop"
  Entry window: Never opened

This prevents zombie events that never resolve.

---

RACE CONDITION PREVENTION

Events must be thread-safe.

Problem:

Thread A: Checks if cascade is ACTIVE
Thread B: Updates cascade to COMPLETED
Thread A: Enters trade (stale decision)

Solution:

Event updates are atomic
State reads include version number

entry_decision = decide_entry(event_id, expected_state=ACTIVE)

If event state changed between read and decision:
  Reject decision
  Re-evaluate with current state

Or use optimistic locking:

def enter_trade_if_active(event_id):
    with event_lock(event_id):
        event = get_event(event_id)
        if event.lifecycle_state != ACTIVE:
            return False  # State changed, abort
        
        # State is still ACTIVE, safe to enter
        execute_entry()
        return True

---

MULTI-EVENT HANDLING

Multiple events can be active simultaneously.

Example:

BTC liquidation cascade (COMPLETING)
ETH funding snapback (ACTIVE)
SOL liq band approached (DETECTED)

Registry contains all three.

Strategies query by event type and state:

active_cascades = registry.get_active_events(LIQUIDATION_CASCADE)
active_snapbacks = registry.get_active_events(FUNDING_SNAPBACK)

Each event has independent lifecycle.

Prioritization:

If multiple events are actionable:
  - Use priority scores (match_score)
  - Use regime alignment
  - Use time_since_detection (fresher = better)

---

TESTING EVENT LIFECYCLE

Unit tests must cover:

State Transition Tests:

test_cascade_detection_to_trigger()
test_cascade_trigger_to_active()
test_cascade_active_to_completing()
test_cascade_completing_to_completed()
test_cascade_timeout()

Staleness Tests:

test_event_expiration()
test_stale_event_not_actionable()

Race Condition Tests:

test_concurrent_state_updates()
test_entry_decision_with_state_change()

Replay Tests:

test_event_replay_matches_live()

---

DEBUGGING AIDS

When strategies misbehave, event history reveals why.

Example Debug Query:

"Why did strategy enter at 07:05:00?"

Event log shows:

cascade_BTC_20260121_070100:
  DETECTED:   07:01:00
  TRIGGERED:  07:01:15
  ACTIVE:     07:01:16
  COMPLETING: 07:01:20
  COMPLETED:  07:01:22

Strategy log shows:

07:05:00 - Entered trade (reason: cascade detected)

Analysis:

Strategy entered 3:38 after cascade completed
Event was stale (should have been EXPIRED)
Bug: Strategy didn't check lifecycle_state

Fix:

Add entry validation:
  if event.lifecycle_state != COMPLETING:
      reject_entry()

---

METRICS TO TRACK

Per Event Type:

Average duration (DETECTED → COMPLETED)
State distribution (how long in each state)
Timeout rate (events that never complete)
Expiration rate (events that go stale)

Per Strategy:

Entry timing (relative to event lifecycle)
  - How many entries during ACTIVE vs COMPLETING vs COMPLETED
Stale entry rate (entries after COMPLETED)
Optimal entry state (which state has best outcomes)

Example Insight:

"Geometry strategy has best performance when entering during COMPLETING"
"50% of failed trades entered during COMPLETED (too late)"

Action:

Enforce entry gate:
  if event.lifecycle_state != COMPLETING:
      reject_entry()

---

IMPLEMENTATION CHECKLIST

[ ] Define event lifecycle states (enum)
[ ] Create Event base class
[ ] Implement event-specific subclasses (Cascade, Snapback, etc.)
[ ] Build event registry (thread-safe)
[ ] Add lifecycle state machine logic
[ ] Add timeout enforcement
[ ] Add expiration logic
[ ] Integrate with state builder
[ ] Add event queries to strategies
[ ] Add lifecycle logging
[ ] Write unit tests
[ ] Write integration tests
[ ] Add debugging tools

---

BOTTOM LINE

Temporal awareness is not optional.

Without event lifecycle tracking:
  - Strategies chase stale events
  - Agents confuse past and present
  - No distinction between "happening" and "happened"
  - Race conditions cause bad entries

With event lifecycle tracking:
  - Strategies know where in event they are
  - Entry windows are explicit
  - Stale events are rejected
  - Debugging is possible

Events have lifecycles.
Track them explicitly.

Every event must answer:
  - Is this happening RIGHT NOW?
  - How long has it been in this state?
  - Is it still actionable?
  - When did it complete?

If your system can't answer these:
  It has temporal blindness.
  Fix it before trading.
