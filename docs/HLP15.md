MULTI-EVENT ARBITRATION & LOCK-FREE CONCURRENCY
Critical Patterns for Real-Time Trading Systems

---

**VOCABULARY NOTE:**
This document uses "priority_score" instead of "priority_score" throughout.
Priority scoring is used for event selection, not as a measure of certainty.

---

When multiple events are active simultaneously:

BTC cascade (COMPLETING)
ETH snapback (ACTIVE)  
SOL hunt detected (TRIGGERED)

Questions arise:

Which event gets capital?
Which strategy executes first?
How do we prevent race conditions?
How do we avoid lock contention killing latency?

Naive approaches destroy edge through:
  - Lock contention (missed entries)
  - Priority inversions (wrong trade selected)
  - Capital conflicts (overallocation)
  - Race conditions (duplicate entries)

This document solves these problems.

---

PART 1: THE LOCK CONTENTION PROBLEM

Problem Statement:

State builder updates hot state every 100ms
Strategy A reads hot state
Strategy B reads hot state
Both want to enter trades

If hot state uses locks:
  - Reader blocks writer
  - Writers block readers
  - Strategies wait for each other

Latency budget destroyed.

Example Timeline (With Locks):

00.000ms - State builder acquires write lock
00.050ms - Strategy A tries to read, BLOCKS
00.100ms - State builder releases lock
00.100ms - Strategy A acquires read lock
00.105ms - Strategy B tries to read, BLOCKS (Strategy A holds lock)
00.110ms - Strategy A releases lock
00.110ms - Strategy B acquires read lock
00.115ms - Strategy B releases lock

Total latency for Strategy B: 115ms (from first attempt)

This is UNACCEPTABLE for liquidation trading.

---

SOLUTION 1: LOCK-FREE READS (VERSIONED SNAPSHOTS)

Design:

Hot state is versioned
State builder writes new version (never mutates existing)
Readers read without locks (always get consistent snapshot)

Implementation:

struct HotState {
    version: AtomicU64,
    snapshot_a: StateSnapshot,
    snapshot_b: StateSnapshot,
    current_index: AtomicU8,  // 0 or 1
}

Writer (State Builder):

fn update_state(new_data: StateSnapshot) {
    let current = self.current_index.load(Acquire);
    let next = 1 - current;  // Toggle between 0 and 1
    
    // Write to inactive snapshot
    if next == 0 {
        self.snapshot_a = new_data;
    } else {
        self.snapshot_b = new_data;
    }
    
    // Memory barrier
    atomic::fence(Release);
    
    // Atomically switch active snapshot
    self.current_index.store(next, Release);
    self.version.fetch_add(1, Release);
}

Reader (Strategy):

fn read_state() -> (u64, StateSnapshot) {
    loop {
        let version_before = self.version.load(Acquire);
        let index = self.current_index.load(Acquire);
        
        let snapshot = if index == 0 {
            self.snapshot_a.clone()
        } else {
            self.snapshot_b.clone()
        };
        
        let version_after = self.version.load(Acquire);
        
        // Check if state changed during read
        if version_before == version_after {
            return (version_before, snapshot);
        }
        // Retry if version changed (rare)
    }
}

Benefits:

No locks
Readers never block writer
Writer never blocks readers
Readers never block each other
Read latency: ~50 nanoseconds (memory read + atomic load)

Trade-offs:

Small memory overhead (2 snapshots instead of 1)
Rare retry on version mismatch (< 0.1% of reads)

Verdict: MANDATORY for hot path

---

SOLUTION 2: EVENT REGISTRY WITHOUT LOCKS

Problem:

Event registry is accessed by:
  - State builder (writes new events, updates states)
  - All strategies (query active events)

Lock-based registry = contention disaster

Lock-Free Event Registry:

Use concurrent data structures:

Option A: Lock-Free HashMap
  - DashMap (Rust)
  - ConcurrentHashMap (Java)
  - lockfree crate (Rust)

Option B: Append-Only Event Log + Cache
  - Events written to append-only log (lock-free)
  - Cache layer for reads (versioned snapshots)
  - Periodic compaction

Recommended: Option A for simplicity

Implementation (Conceptual):

use dashmap::DashMap;

struct EventRegistry {
    events: DashMap<EventId, Arc<Event>>,
}

impl EventRegistry {
    fn register_event(&self, event: Event) {
        let event_arc = Arc::new(event);
        self.events.insert(event.id, event_arc);
        // No lock needed
    }
    
    fn update_event_state(&self, event_id: EventId, new_state: LifecycleState) {
        if let Some(mut event) = self.events.get_mut(&event_id) {
            // DashMap handles concurrency internally
            event.lifecycle_state = new_state;
            event.updated_at = now();
        }
    }
    
    fn get_active_events(&self, event_type: EventType) -> Vec<Arc<Event>> {
        self.events
            .iter()
            .filter(|e| e.event_type == event_type)
            .filter(|e| e.is_actionable())
            .map(|e| e.value().clone())
            .collect()
        // No lock held during iteration
    }
}

Benefits:

No global lock
Fine-grained locking (per event)
Readers don't block other readers
Minimal contention

Latency:

Insert: ~200ns
Lookup: ~100ns
Iteration: ~1μs per 100 events

---

PART 2: MULTI-EVENT ARBITRATION

Problem:

3 events are actionable:
  - BTC cascade (priority_score: 85%)
  - ETH snapback (priority_score: 70%)
  - SOL hunt (priority_score: 60%)

Capital available: $10,000
Only one position allowed at a time (risk constraint)

Which event gets selected?

---

ARBITRATION STRATEGY 1: PRIORITY SCORING

Assign priority score to each event.

Score Components:

1. Priority_score (from event detection)
   Weight: 40%
   
2. Freshness (time since detection)
   Weight: 30%
   Formula: max(0, 1 - (time_since_detection / 60s))
   
3. Regime alignment (does strategy match regime?)
   Weight: 20%
   
4. Expected value (R:R ratio × win rate)
   Weight: 10%

Total Score:

score = (priority_score × 0.4) + 
        (freshness × 0.3) + 
        (regime_alignment × 0.2) + 
        (expected_value × 0.1)

Selection:

Select event with highest score

Example:

BTC cascade:
  priority_score: 0.85
  freshness: 0.95 (detected 3s ago)
  regime_alignment: 1.0 (expansion → cascade)
  expected_value: 0.8 (2:1 R:R × 40% win rate)
  score = 0.34 + 0.285 + 0.2 + 0.08 = 0.905

ETH snapback:
  priority_score: 0.70
  freshness: 0.50 (detected 30s ago)
  regime_alignment: 0.5 (sideways, but snapback still valid)
  expected_value: 0.6
  score = 0.28 + 0.15 + 0.1 + 0.06 = 0.59

SOL hunt:
  priority_score: 0.60
  freshness: 0.80 (detected 12s ago)
  regime_alignment: 1.0
  expected_value: 0.5
  score = 0.24 + 0.24 + 0.2 + 0.05 = 0.73

Winner: BTC cascade (score: 0.905)

---

ARBITRATION STRATEGY 2: HIERARCHY + EXCLUSION

Define strict hierarchy:

Tier 1: Liquidation cascades (highest priority)
Tier 2: Failed hunts
Tier 3: Funding snapbacks
Tier 4: Inventory distribution trades

Rules:

If Tier 1 event is actionable:
  - Ignore all Tier 2-4 events
  - Select highest-priority_score Tier 1 event

If no Tier 1, check Tier 2
(And so on)

Exclusion Matrix:

Some strategies are mutually exclusive:

                Cascade  FailedHunt  Snapback  Distribution
Cascade         ✓        ✗           ✗         ✗
FailedHunt      ✗        ✓           ✓         ✗
Snapback        ✗        ✓           ✓         ✓
Distribution    ✗        ✗           ✓         ✓

✓ = Can coexist
✗ = Mutually exclusive

If BTC cascade is active:
  - Reject all other events
  - Wait for cascade to complete

This prevents conflicting positions.

---

ARBITRATION STRATEGY 3: CAPITAL ALLOCATION

If multiple positions are allowed:

Capital available: $10,000
Risk per trade: 2% of capital = $200

Multiple events:
  - BTC cascade needs $5,000 (for 1 BTC)
  - ETH snapback needs $3,000 (for 2 ETH)

Capital allocation:

Allocate proportional to priority score:

BTC score: 0.905
ETH score: 0.590
Total: 1.495

BTC allocation: (0.905 / 1.495) × $10,000 = $6,053
ETH allocation: (0.590 / 1.495) × $10,000 = $3,947

Constraint checks:

Is BTC allocation sufficient?
  Need: $5,000
  Have: $6,053
  ✓ OK

Is ETH allocation sufficient?
  Need: $3,000
  Have: $3,947
  ✓ OK

Total allocated: $10,000 (fully utilized)

Execute both trades.

If capital insufficient:

Reject lower-priority event
Allocate all capital to highest-priority

---

PART 3: RACE CONDITION PREVENTION

Problem:

Strategy A decides to enter BTC cascade
Strategy B decides to enter BTC cascade (same event)
Both submit orders

Result: Double position, risk limit violated

---

SOLUTION: ATOMIC POSITION RESERVATION

Design:

Before entering, strategy must reserve position slot
Reservation is atomic (CAS operation)
Only one strategy can reserve per event

Implementation:

struct PositionManager {
    active_positions: DashMap<Symbol, PositionSlot>,
    max_positions_per_symbol: u32,
}

struct PositionSlot {
    reserved_by: Option<StrategyId>,
    event_id: Option<EventId>,
    reserved_at: Timestamp,
}

fn try_reserve_position(
    &self,
    symbol: Symbol,
    strategy_id: StrategyId,
    event_id: EventId
) -> Result<ReservationToken, ReservationError> {
    
    // Check if slot available
    let slot = self.active_positions.entry(symbol).or_insert_with(|| {
        PositionSlot {
            reserved_by: None,
            event_id: None,
            reserved_at: 0,
        }
    });
    
    // Atomic check-and-set
    if slot.reserved_by.is_some() {
        return Err(ReservationError::SlotTaken);
    }
    
    // Reserve slot
    slot.reserved_by = Some(strategy_id);
    slot.event_id = Some(event_id);
    slot.reserved_at = now();
    
    Ok(ReservationToken {
        symbol,
        strategy_id,
        event_id,
    })
}

fn release_reservation(&self, token: ReservationToken) {
    if let Some(mut slot) = self.active_positions.get_mut(&token.symbol) {
        if slot.reserved_by == Some(token.strategy_id) {
            slot.reserved_by = None;
            slot.event_id = None;
        }
    }
}

Strategy Usage:

fn execute_entry(&mut self, event: Event) {
    // Attempt reservation
    let reservation = match self.position_manager.try_reserve_position(
        event.symbol,
        self.strategy_id,
        event.event_id
    ) {
        Ok(reservation) => reservation,
        Err(ReservationError::SlotTaken) => {
            log_info!("Position slot taken by another strategy");
            return;  // Abort entry
        }
    };
    
    // Reservation successful, submit order
    match self.submit_order(event) {
        Ok(_) => {
            // Keep reservation (now active position)
        }
        Err(e) => {
            // Order failed, release reservation
            self.position_manager.release_reservation(reservation);
        }
    }
}

Benefits:

Atomic reservation (no race)
Only one strategy enters per symbol
Clean error handling
No locks in hot path

---

PART 4: DECISION PIPELINE (AVOIDING LOCK CASCADES)

Problem:

Sequential decision-making creates bottlenecks:

1. Update hot state (LOCK)
2. Detect events (LOCK registry)
3. Arbitrate (LOCK position manager)
4. Enter trade (LOCK order book)

Each lock blocks the next.

Solution: Pipeline with Message Passing

Stage 1: State Update (Lock-Free)
  Input: Node messages
  Output: Versioned state snapshot
  Concurrency: Lock-free writes

Stage 2: Event Detection (Lock-Free Read)
  Input: State snapshot (versioned read)
  Output: New/updated events
  Concurrency: No locks, read-only

Stage 3: Event Arbitration (Lock-Free)
  Input: Active events (from registry)
  Output: Prioritized event list
  Concurrency: No locks, read-only

Stage 4: Position Reservation (Atomic CAS)
  Input: Selected event
  Output: Reservation token or rejection
  Concurrency: Lock-free CAS

Stage 5: Order Submission (External API)
  Input: Reservation token + event
  Output: Order ID
  Concurrency: Async, non-blocking

Stages communicate via channels (lock-free queues):

State Update → Event Detection → Arbitration → Reservation → Order Submission

Each stage is independent.
No global lock.
Back-pressure handled via channel capacity.

Rust Implementation (Conceptual):

use crossbeam::channel::{bounded, Receiver, Sender};

// Channels
let (state_tx, state_rx) = bounded(10);
let (event_tx, event_rx) = bounded(100);
let (arb_tx, arb_rx) = bounded(10);

// Stage 1: State updater
thread::spawn(move || {
    loop {
        let state = build_state_from_node();
        state_tx.send(state).ok();
    }
});

// Stage 2: Event detector
thread::spawn(move || {
    for state in state_rx {
        let events = detect_events(state);
        for event in events {
            event_tx.send(event).ok();
        }
    }
});

// Stage 3: Arbitrator
thread::spawn(move || {
    for event in event_rx {
        let selected = arbitrate(event);
        arb_tx.send(selected).ok();
    }
});

// Stage 4: Executor
thread::spawn(move || {
    for selected_event in arb_rx {
        if let Ok(reservation) = reserve_position(selected_event) {
            submit_order(reservation, selected_event);
        }
    }
});

Benefits:

No global locks
Stages run concurrently
Back-pressure automatic (bounded channels)
Easy to reason about

Latency:

State update → Detection: ~100μs
Detection → Arbitration: ~50μs
Arbitration → Reservation: ~10μs
Reservation → Order: ~500μs (network)

Total: ~660μs (sub-millisecond)

---

PART 5: STARVATION PREVENTION

Problem:

High-priority events constantly arriving
Low-priority events never execute

Example:

BTC cascades happen every 10 minutes
ETH snapbacks detected but never selected
Capital always allocated to BTC

Result: Missing edge from ETH trades

Solution 1: Age-Based Priority Boost

Boost priority of old events:

age_bonus = min(0.3, time_waiting / 120s)
adjusted_score = base_score + age_bonus

Events waiting > 2 minutes get +0.3 priority boost
Eventually overtakes even high-priority_score fresh events

Solution 2: Fair Queuing

Round-robin between event types:

Last executed: Cascade
Next preference: FailedHunt (different type)
If no FailedHunt: Snapback
If no Snapback: Back to Cascade

Prevents one event type from monopolizing

Solution 3: Reserved Capital Slots

Allocate capital by event type:

70% - Liquidation cascades
20% - Failed hunts  
10% - Other strategies

Each type has guaranteed allocation
No starvation

---

PART 6: DEBUGGING ARBITRATION DECISIONS

Every arbitration decision must be logged.

Log Entry:

{
  "timestamp": 1737442838123456789,
  "arbitration_id": "arb_20260121_072038",
  "candidates": [
    {
      "event_id": "cascade_BTC_...",
      "event_type": "LIQUIDATION_CASCADE",
      "priority_score": 0.85,
      "freshness": 0.95,
      "score": 0.905,
      "rank": 1
    },
    {
      "event_id": "snapback_ETH_...",
      "event_type": "FUNDING_SNAPBACK",
      "priority_score": 0.70,
      "freshness": 0.50,
      "score": 0.59,
      "rank": 2
    }
  ],
  "selected": "cascade_BTC_...",
  "selection_reason": "highest_score",
  "rejected_events": [
    {
      "event_id": "snapback_ETH_...",
      "reason": "lower_score",
      "score_diff": 0.315
    }
  ],
  "capital_allocated": 10000,
  "reservation_status": "SUCCESS"
}

Benefits:

Understand why event was selected/rejected
Debug suboptimal arbitration
Measure opportunity cost (rejected events that would have won)

---

PART 6B: COUNTERFACTUAL TRACKING (ARBITRATION OPTIMIZATION)

Problem:

Arbitration scoring weights are static:
  - Priority_score: 40%
  - Freshness: 30%
  - Regime: 20%
  - EV: 10%

But are these optimal?

Example scenario:

BTC cascade selected (score: 0.905)
ETH snapback rejected (score: 0.59)

Outcomes:
  BTC cascade: +$150 (win)
  ETH snapback: Would have been +$300 (missed opportunity)

Question: Should we have selected ETH instead?

Counterfactual tracking answers this.

---

What Is Counterfactual Tracking?

For every rejected event:
  - Track what would have happened if we had selected it
  - Compare to actual selected event outcome
  - Measure opportunity cost
  - Use data to optimize scoring weights

Implementation:

Counterfactual Event Log:

struct CounterfactualEntry {
    arbitration_id: String,
    timestamp: i64,
    
    // Selected event
    selected_event_id: String,
    selected_score: f64,
    selected_outcome: Option<TradeOutcome>,  // Filled when trade completes
    
    // Rejected events (tracked counterfactually)
    rejected_events: Vec<CounterfactualEvent>,
}

struct CounterfactualEvent {
    event_id: String,
    event_type: EventType,
    score: f64,
    score_components: ScoreBreakdown,
    
    // Counterfactual tracking
    hypothetical_entry_price: i64,
    hypothetical_exit_price: Option<i64>,  // Filled when event completes
    hypothetical_outcome: Option<TradeOutcome>,
    
    // Would this have been better?
    opportunity_cost: Option<i64>,  // Difference in PnL vs selected event
}

struct ScoreBreakdown {
    priority_score: f64,
    freshness: f64,
    regime_alignment: f64,
    expected_value: f64,
}

struct TradeOutcome {
    entry_price: i64,
    exit_price: i64,
    pnl: i64,
    hold_time_ms: i64,
    exit_reason: String,
}

---

Counterfactual Tracking Process

Step 1: Log All Candidates at Arbitration Time

fn arbitrate(candidates: Vec<Event>) -> Event {
    let scored_events: Vec<(Event, f64, ScoreBreakdown)> = 
        candidates.iter()
            .map(|e| (e.clone(), calculate_score(e), calculate_breakdown(e)))
            .collect();
    
    scored_events.sort_by(|a, b| b.1.cmp(&a.1));
    
    let selected = scored_events[0].0.clone();
    let rejected = &scored_events[1..];
    
    // Log counterfactual entry
    log_counterfactual(
        selected,
        rejected,
        scored_events
    );
    
    selected
}

Step 2: Track Hypothetical Entry/Exit for Rejected Events

For each rejected event:
  - Monitor event lifecycle (even though not traded)
  - When event reaches optimal entry state (e.g., COMPLETING):
    * Record hypothetical_entry_price (current market price)
  - When event completes:
    * Record hypothetical_exit_price
    * Calculate hypothetical_outcome

Background process:

fn track_counterfactuals() {
    loop {
        let pending = get_pending_counterfactuals();
        
        for cf in pending {
            for rejected in cf.rejected_events {
                let event = get_event(rejected.event_id);
                
                // Track entry point
                if event.lifecycle_state == COMPLETING && rejected.hypothetical_entry_price.is_none() {
                    rejected.hypothetical_entry_price = get_market_price(event.symbol);
                }
                
                // Track exit point
                if event.lifecycle_state == COMPLETED && rejected.hypothetical_exit_price.is_none() {
                    rejected.hypothetical_exit_price = get_market_price(event.symbol);
                    
                    // Calculate outcome
                    rejected.hypothetical_outcome = Some(TradeOutcome {
                        entry_price: rejected.hypothetical_entry_price.unwrap(),
                        exit_price: rejected.hypothetical_exit_price.unwrap(),
                        pnl: calculate_pnl(...),
                        hold_time_ms: event.duration_ms(),
                        exit_reason: event.completion_reason(),
                    });
                }
            }
        }
        
        sleep(100ms);
    }
}

Step 3: Calculate Opportunity Cost

When both selected and rejected events have outcomes:

fn calculate_opportunity_cost(cf: &mut CounterfactualEntry) {
    if let Some(selected_outcome) = &cf.selected_outcome {
        for rejected in &mut cf.rejected_events {
            if let Some(rejected_outcome) = &rejected.hypothetical_outcome {
                // Opportunity cost = what we missed
                let opp_cost = rejected_outcome.pnl - selected_outcome.pnl;
                rejected.opportunity_cost = Some(opp_cost);
            }
        }
    }
}

Example:

Selected: BTC cascade
  Entry: $50,000
  Exit: $50,150
  PnL: +$150

Rejected: ETH snapback
  Hypothetical entry: $2,000
  Hypothetical exit: $2,150
  Hypothetical PnL: +$300
  
Opportunity cost: $300 - $150 = $150 (we left $150 on the table)

---

Aggregated Analysis

Periodically (e.g., weekly), aggregate counterfactual data:

Analysis Metrics:

1. Total Opportunity Cost

Sum of all positive opportunity costs:
  Total missed PnL = Σ max(0, opp_cost)

If high: Arbitration is selecting suboptimal events

2. Opportunity Cost by Score Component

Which scoring component causes the most misses?

Group by: "Rejected event had higher X but lower total score"

Example finding:
  "Events with high freshness but low priority_score were rejected
   But had 60% win rate and $2,000 total opportunity cost
   Consider increasing freshness weight"

3. Score Inversion Rate

How often does a rejected event outperform selected?

inversion_rate = (rejected_wins / total_arbitrations) * 100

If > 20%: Scoring is poorly calibrated

4. Optimal Weight Search

Use historical counterfactual data to find optimal weights.

Grid search:

for priority_score_weight in [0.3, 0.35, 0.4, 0.45, 0.5]:
    for freshness_weight in [0.2, 0.25, 0.3, 0.35]:
        for regime_weight in [0.1, 0.15, 0.2, 0.25]:
            ev_weight = 1.0 - (priority_score_weight + freshness_weight + regime_weight)
            
            # Re-score historical events with new weights
            hypothetical_total_pnl = 0
            for historical_arb in counterfactual_log:
                new_selected = reselect_with_weights(
                    historical_arb.candidates,
                    priority_score_weight,
                    freshness_weight,
                    regime_weight,
                    ev_weight
                )
                hypothetical_total_pnl += get_outcome_pnl(new_selected)
            
            if hypothetical_total_pnl > best_pnl:
                best_pnl = hypothetical_total_pnl
                best_weights = (priority_score_weight, freshness_weight, regime_weight, ev_weight)

Output:

"Optimal weights found:
  Priority_score: 35% (was 40%)
  Freshness: 35% (was 30%)
  Regime: 20% (same)
  EV: 10% (same)
  
Improvement: +$1,500 total PnL over last 90 days (+15%)"

---

Counterfactual Log Schema

{
  "arbitration_id": "arb_20260121_072038",
  "timestamp": 1737442838123456789,
  
  "selected": {
    "event_id": "cascade_BTC_...",
    "score": 0.905,
    "components": {
      "priority_score": 0.34,
      "freshness": 0.285,
      "regime": 0.2,
      "ev": 0.08
    },
    "outcome": {
      "entry_price": 50000,
      "exit_price": 50150,
      "pnl": 150,
      "hold_time_ms": 45000,
      "exit_reason": "target_hit"
    }
  },
  
  "rejected": [
    {
      "event_id": "snapback_ETH_...",
      "score": 0.59,
      "components": {
        "priority_score": 0.28,
        "freshness": 0.15,
        "regime": 0.1,
        "ev": 0.06
      },
      "hypothetical_outcome": {
        "entry_price": 2000,
        "exit_price": 2150,
        "pnl": 300,
        "hold_time_ms": 60000,
        "exit_reason": "target_hit"
      },
      "opportunity_cost": 150
    }
  ],
  
  "analysis": {
    "selected_better": false,
    "best_alternative": "snapback_ETH_...",
    "total_opportunity_cost": 150
  }
}

---

Automated Weight Adjustment

Option 1: Manual Review

Weekly report:
  - Show total opportunity cost
  - Show optimal weights from grid search
  - Human reviews and decides whether to update

Option 2: Gradual Adaptation

Automatically adjust weights toward optimal:

new_weight = current_weight + 0.1 * (optimal_weight - current_weight)

This prevents drastic changes from noise.

Re-evaluate every week.
Converges slowly to optimal.

Option 3: A/B Testing

Run two arbitrators in parallel:

Arbitrator A: Current weights
Arbitrator B: Experimental weights

Compare performance over time:
  - Total PnL
  - Win rate
  - Opportunity cost

Promote better arbitrator to production.

Recommended: Start with Option 1, migrate to Option 2 after validation

---

Filtering Noise

Not all counterfactual outcomes are meaningful.

Filters to apply:

1. Ignore events that invalidated

If rejected event invalidated before completing:
  - Don't count as missed opportunity
  - Event was correctly rejected

2. Ignore events with low priority_score

If rejected event had priority_score < 50%:
  - Even if profitable, too risky to generalize
  - Likely lucky outcome

3. Require minimum sample size

Don't adjust weights based on < 30 arbitrations
Need statistical significance

4. Adjust for regime

If market regime changed significantly:
  - Historical optimal weights may not apply
  - Segment analysis by regime

---

Metrics Dashboard

Track counterfactual performance:

Opportunity Cost:
  - Total: $450 (last 7 days)
  - Average per arbitration: $15
  - Max single event: $200 (ETH snapback on 2026-01-18)

Score Inversions:
  - Rate: 18% (9 of 50 arbitrations)
  - Trend: Decreasing (was 25% last week)

Optimal Weights (Current vs Optimal):
  Priority_score:  40% → 35%
  Freshness:   30% → 35%
  Regime:      20% → 20%
  EV:          10% → 10%

Projected Improvement:
  +$350 (if weights adjusted)

---

Implementation Checklist

[ ] Add counterfactual logging to arbitrator
[ ] Build background tracker for rejected events
[ ] Calculate hypothetical entry/exit prices
[ ] Compute opportunity costs
[ ] Build aggregation pipeline
[ ] Implement grid search for optimal weights
[ ] Add counterfactual metrics dashboard
[ ] Write weight adjustment logic
[ ] Test with historical data

---

Benefits of Counterfactual Tracking

Continuous improvement:
  - Scoring evolves with market
  - Adapts to regime changes

Quantified opportunity cost:
  - Know exactly what you're missing
  - Prioritize improvements

Evidence-based tuning:
  - No guessing on weights
  - Data-driven optimization

Prevents regret:
  - "Should I have taken that trade?"
  - Answer is logged and analyzable

---

Caveats

Path dependence:
  - Hypothetical trades don't affect market
  - Real trade might have different slippage

Survivorship bias:
  - Only tracking events that fully developed
  - Missing events that never completed

Regime stability:
  - Optimal weights valid only for similar conditions
  - Need to re-optimize when market changes

Don't over-optimize:
  - Weights that work on last 90 days
  - May not work on next 90 days
  - Keep adjustments gradual

---

Bottom Line on Counterfactuals

Counterfactual tracking converts arbitration from:

"We picked the highest score"

into:

"We picked the event that historically maximizes PnL"

This is the difference between:
  - Static heuristics
  - Adaptive optimization

Every rejected event is a lesson.
Learn from them systematically

---

PART 7: PERFORMANCE METRICS

Track arbitration system health:

Metrics:

arbitration_latency_p50: 50μs
arbitration_latency_p99: 200μs
reservation_success_rate: 98.5%
reservation_conflicts: 15 per hour
multi_event_scenarios: 120 per day
starvation_events: 0
priority_inversions: 0

Alerts:

If arbitration_latency_p99 > 1ms: WARN
If reservation_success_rate < 95%: CRITICAL
If starvation_events > 0: WARN

---

TESTING STRATEGY

Unit Tests:

test_lock_free_state_read_write()
test_event_registry_concurrent_updates()
test_position_reservation_race()
test_arbitration_score_calculation()
test_starvation_prevention()

Stress Tests:

100 strategies querying state simultaneously
50 events updating concurrently
1000 arbitration decisions per second

Measure:
  - Latency distribution
  - Reservation conflict rate
  - Throughput

Chaos Tests:

Random event arrival
Random capital constraints  
Random strategy failures

Verify:
  - No deadlocks
  - No race conditions
  - No position limit violations

---

IMPLEMENTATION CHECKLIST

[ ] Implement versioned snapshot reads
[ ] Implement lock-free event registry
[ ] Implement priority scoring system
[ ] Implement atomic position reservation
[ ] Build decision pipeline (channels)
[ ] Add age-based priority boost
[ ] Add arbitration logging
[ ] Write concurrency tests
[ ] Write stress tests
[ ] Measure latency under load

---

BOTTOM LINE

Multi-event arbitration and lock contention are CRITICAL.

Wrong approach:
  - Global locks
  - Sequential decision-making
  - No priority system

Result:
  - Millisecond latencies
  - Missed entries
  - Capital conflicts
  - Race conditions

Correct approach:
  - Lock-free reads (versioned snapshots)
  - Lock-free registry (concurrent hashmap)
  - Priority-based arbitration
  - Atomic reservations
  - Pipelined stages

Result:
  - Sub-millisecond latencies
  - No contention
  - Clean arbitration
  - No race conditions

In liquidation trading:
  Milliseconds = missed edge
  Lock contention = lost money

Build lock-free or don't build at all.
