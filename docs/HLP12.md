WALLET TRACKING SYSTEM DESIGN
From Transaction Observation to Behavioral Classification

---

**STATUS: FUTURE RESEARCH - REQUIRES HISTORICAL DATA COLLECTION**

This document specifies how to build a wallet tracking layer IF historical
data collection has been running for 3+ months.

See HLP4 for critical limitations:
- Node data is a snapshot, not historical behavior
- Classification requires behavioral patterns over time
- No historical data = no reliable classification

Do NOT implement until:
1. Historical position tracking has run for 90+ days
2. Classification criteria are validated
3. Out-of-sample testing shows predictive value

All "match_score" values in this document are HYPOTHESES.

---

This is the most advanced component. Do not attempt until core system works.

The goal is not to copy wallets.
The goal is to infer intent and use it as a timing indicator.

---

HYPERLIQUID NODE: WALLET DATA

All 66,280 wallet positions visible via:
- users_with_positions → Set of all wallets with active positions
- user_to_state[wallet_addr] → Position details:
  * s = size (+ long, - short)
  * e = entry price
  * l = leverage
  * M = margin

Wallet tracking detects when wallet address:
1. Appears in users_with_positions (position opened)
2. Changes in user_to_state[addr].s (position sized)
3. Disappears from users_with_positions (position closed/liquidated)

This provides complete visibility into all position activity.

---

CORE PRINCIPLES

Principle 1: Behavior Over Size

Large wallets are not necessarily manipulators.
Manipulators have distinct behavioral signatures.

You are looking for:
  - Repeatable interaction with market stress
  - Objective-driven execution
  - Predictable entry/exit patterns

Principle 2: Wallets as Arming Signals

Wallets do not generate trades.
They start clocks.

When a known wallet activates:
  - Narrow focus to relevant zones
  - Prepare for structural event
  - Monitor for confirmation

Principle 3: Classification Requires History

A single trade is noise.

Classification requires:
  - Multiple observations
  - Consistent patterns
  - Statistical validation

Do not classify prematurely.

Principle 4: Failed Hunts Are More Informative

Successful hunts confirm patterns.
Failed hunts reveal hierarchy.

When a known wallet fails:
  - Someone bigger intervened
  - Trade against the failed direction

This is the highest-priority indicator.

---

ARCHITECTURAL LAYERS

Layer 1: Transaction Monitoring
Layer 2: Wallet Identification
Layer 3: Behavioral Analysis
Layer 4: Classification
Layer 5: Strategy Integration

Each layer builds on the previous.

---

LAYER 1: TRANSACTION MONITORING

Objective: Capture all on-chain and exchange activity.

Data Sources

Hyperliquid on-chain transactions:
  - Position opens/closes
  - Order placements/cancellations
  - Transfers

Exchange API data:
  - Large trades (> threshold)
  - Wallet positions (if available)
  - Margin usage (if available)

Data to capture:

wallet_address: string
timestamp: int64 (nanoseconds)
transaction_type: enum (OPEN, CLOSE, CANCEL, TRANSFER)
symbol: string
direction: enum (LONG, SHORT)
size: int64 (contracts)
price: int64 (execution price, if applicable)
order_type: enum (MARKET, LIMIT, STOP)
slippage_bps: int32 (if market order)

Monitoring Requirements

Latency: < 500ms from transaction to capture
Coverage: All symbols (not just tracked ones)
Persistence: All transactions logged
Backfill: Historical data for pattern detection

Missing Data Handling

If transaction data incomplete:
  Log the gap
  Do not interpolate
  Flag wallet as "uncertain"

---

LAYER 2: WALLET IDENTIFICATION

Objective: Determine which wallets are worth tracking.

Identification Criteria

Size threshold:
  Position size > percentile (e.g., top 5%)

Activity threshold:
  Trades > N per day

Timing correlation:
  Trades cluster near liquidation events

Effectiveness ratio:
  Success rate in achieving objective > threshold

Initial Identification

Scan historical data
Rank wallets by:
  - Total volume
  - Trade frequency
  - Timing correlation with liq events

Select top N wallets (e.g., 50) for tracking

Ongoing Identification

Continuously monitor for new large wallets
Add to tracking list if:
  - Meets size threshold
  - Shows consistent patterns
  - Correlates with market stress

Removal from tracking:

Inactive for > N days
Behavior becomes random
Size drops below threshold

Wallet Metadata

wallet_id: string (hash for privacy)
first_seen: int64
last_seen: int64
total_volume: int64
trade_count: int32
avg_position_size: int64
behavioral_class: enum (UNKNOWN initially)
tracking_match_score: int32 (0-10000)

---

LAYER 3: BEHAVIORAL ANALYSIS

Objective: Detect repeatable patterns in wallet activity.

Behavioral Dimensions

Dimension 1: Holding Time Distribution

Short (< 5 minutes): Manipulator signature
Medium (5m - 1h): Swing trader
Long (> 1h): Position trader

Compute:
  Mean holding time
  Std deviation
  Percentiles (p10, p50, p90)

Dimension 2: Entry Timing

Pre-event: Enters before liquidation cascade
During-event: Enters during cascade
Post-event: Enters after cascade

Correlation metric:
  Time between wallet entry and OI collapse

Dimension 3: Exit Timing

Immediate: Exits within minutes
Delayed: Exits within hour
Persistent: Holds position

Correlation metric:
  Time between OI collapse and wallet exit

Dimension 4: Order Type Preference

Aggressive: Mostly market orders
Passive: Mostly limit orders
Mixed: Combination

Measure:
  Ratio of market to limit orders

Dimension 5: Slippage Tolerance

Low: Accepts minimal slippage (< 5bps)
Medium: Accepts moderate slippage (5-20bps)
High: Accepts large slippage (> 20bps)

High slippage = objective-driven, not profit-maximizing

Dimension 6: OI Correlation

Builds OI: Position correlated with OI increase
Fades OI: Position inversely correlated with OI

Measure:
  Correlation coefficient between wallet position and OI

Dimension 7: Funding Alignment

With funding: Direction aligns with funding skew
Against funding: Direction opposes funding skew

Measure:
  Correlation between position direction and funding sign

Dimension 8: Price Impact

Causes moves: Trades precede price changes
Reacts to moves: Trades follow price changes

Measure:
  Cross-correlation between trades and price

Behavioral Feature Vector

For each wallet, compute:

holding_time_mean: int64
holding_time_stddev: int64
entry_timing_score: int32 (-10000 to +10000)
  Negative = pre-event, Positive = post-event
exit_timing_score: int32
market_order_ratio: int32 (0-10000)
slippage_tolerance_mean: int32 (bps)
oi_correlation: int32 (-10000 to +10000)
funding_alignment: int32 (-10000 to +10000)
price_impact_score: int32 (0-10000)

---

LAYER 4: CLASSIFICATION

Objective: Assign behavioral class to each wallet.

Behavioral Classes

Class: MANIPULATOR

Signature:
  - Short holding time (< 5m)
  - Pre-event entry (before OI collapse)
  - Immediate exit (after OI collapse)
  - High slippage tolerance
  - Negative OI correlation (fades leverage)
  - Against funding (pushes against skew)
  - High price impact

Example feature vector:
  holding_time_mean: 180_000 (3 minutes)
  entry_timing_score: -5000 (pre-event)
  exit_timing_score: 1000 (quick exit)
  market_order_ratio: 8000 (80% market orders)
  slippage_tolerance_mean: 50 (50bps)
  oi_correlation: -4000 (negative)
  funding_alignment: -6000 (against)
  price_impact_score: 7000 (high)

Class: DIRECTIONAL_TRADER

Signature:
  - Medium holding time (30m - 2h)
  - Post-event or random entry
  - Delayed exit
  - Low slippage tolerance
  - Positive OI correlation (builds leverage)
  - With funding (follows skew)
  - Low price impact

Class: ARBITRAGEUR

Signature:
  - Very short holding time (< 1m)
  - Random entry timing
  - Immediate exit
  - Very low slippage tolerance
  - Zero OI correlation
  - No funding alignment
  - No price impact

Class: LIQUIDATION_ABSORBER

Signature:
  - Short holding time (5-30m)
  - During-event entry (during cascade)
  - Quick exit (after stabilization)
  - Medium slippage tolerance
  - Negative OI correlation
  - Variable funding alignment
  - Moderate price impact

Class: UNKNOWN

Default class for:
  - Insufficient data
  - Inconsistent patterns
  - Low match_score

Classification Algorithm

Option 1: Rule-Based

Define thresholds for each class
Assign class based on feature matching

Pros: Transparent, debuggable
Cons: Brittle, requires manual tuning

Option 2: Clustering

Use k-means or DBSCAN on feature vectors
Identify natural clusters
Label clusters based on characteristics

Pros: Data-driven, discovers patterns
Cons: Requires labeled training data

Option 3: Hybrid

Start with rule-based
Refine with clustering on misclassified wallets

Recommended approach: Hybrid

Classification Match Score

match_score = function(
  sample_size: number of trades observed,
  pattern_consistency: variance in behavior,
  time_span: how long wallet has been tracked
)

Match score formula:

min(
  (sample_size / 100) * 10000,  # More samples = higher score
  (1 - (stddev / mean)) * 10000,  # Less variance = higher score
  (time_span_days / 30) * 10000   # Longer history = higher score
)

Only use wallets with match_score > threshold (e.g., 5000)

---

LAYER 5: STRATEGY INTEGRATION

Objective: Expose wallet intelligence to strategies.

Integration Point: Hot State Store

Add to HotStateSnapshot:

active_manipulators: array of ActiveManipulator

ActiveManipulator:
  wallet_id: string
  direction: enum (LONG, SHORT)
  entry_price: int64
  entry_time: int64
  size_estimate: int64
  execution_phase: enum (PROBING, SCALING, UNWINDING)
  match_score: int32 (0-10000)

Integration Point: Event Stream

Add events:

Event: MANIPULATOR_ACTIVATED
Event: MANIPULATOR_SCALING
Event: MANIPULATOR_EXITING

Strategies subscribe to these events.

Strategy Consumption

Geometry strategy:

If SCANNING:
  If MANIPULATOR_ACTIVATED:
    Start clock
    Narrow focus to liq bands
    Monitor for push confirmation

If ARMED:
  If manipulator exits prematurely:
    Invalidate setup (failed hunt)

Kinematics strategy:

If SCANNING:
  If manipulator switches to passive orders:
    Indicates inventory distribution
    Prepare for range expansion

Cascade strategy:

If SCANNING:
  If MANIPULATOR_ACTIVATED:
    Calculate inevitability threshold
    Monitor for cascade trigger

Usage Rules

Wallet signals are filters, not triggers.

Strategies must still validate:
  - OI conditions
  - Funding conditions
  - Depth conditions
  - Regime alignment

Wallet data adds match_score, does not replace validation.

---

DATA REQUIREMENTS

Minimum Data for Classification

Per wallet:
  - 20+ trades
  - 7+ days of history
  - 3+ liquidation events observed

If insufficient data:
  - Classify as UNKNOWN
  - Do not use in strategy logic

Historical Backfill

To classify wallets, you need historical data.

Sources:
  - Saved logs from hired VM
  - Hyperliquid public APIs
  - On-chain transaction history

Backfill process:

1. Fetch all large transactions (last 90 days)
2. Compute behavioral features
3. Run classification
4. Store wallet metadata
5. Begin live tracking

---

FAILURE MODES

Failure Mode 1: Wallet Stops Behaving

If a classified wallet's behavior changes:
  - Recalculate features
  - Reclassify
  - Lower match_score
  - Flag as "drifting"

Do not assume permanence.

Failure Mode 2: False Positive Classification

If a wallet classified as manipulator fails repeatedly:
  - Reclassify as UNKNOWN
  - Remove from active tracking
  - Log for review

Better to miss signals than act on noise.

Failure Mode 3: Wallet Fragmentation

Manipulators may use multiple wallets.

Detection:
  - Similar behavioral signatures
  - Coordinated timing
  - Shared funding sources (on-chain analysis)

Mitigation:
  - Group wallets into clusters
  - Treat cluster as single entity

Failure Mode 4: Privacy Constraints

Some exchanges do not expose wallet-level data.

Fallback:
  - Aggregate "large trader" metrics
  - Infer behavior from orderflow patterns
  - Lower match_score scores

---

TESTING STRATEGY

Unit Tests

Test behavioral feature calculation:
  - Given trade sequence, compute features
  - Verify correctness

Test classification:
  - Given feature vector, verify class assignment
  - Test edge cases (ambiguous vectors)

Integration Tests

Test wallet tracking pipeline:
  - Ingest mock transactions
  - Compute features
  - Classify
  - Expose to strategies

Replay Tests

Use saved data from hired VM:
  - Replay historical transactions
  - Verify classifications match manual analysis
  - Validate strategy reactions

---

PERFORMANCE REQUIREMENTS

Transaction Ingestion

Latency: < 500ms
Throughput: 1000+ transactions/second

Feature Computation

Latency: < 100ms per wallet
Update frequency: Every trade

Classification

Latency: < 50ms per wallet
Re-classification frequency: Daily (or on behavior drift)

Hot State Update

Latency: < 1ms to update active_manipulators

---

PRIVACY AND SECURITY

Wallet IDs

Never store raw wallet addresses in logs.

Use:
  - Cryptographic hash (SHA256)
  - Keyed hash (HMAC) for consistency

This prevents:
  - Wallet identification from logs
  - Privacy violation

Access Control

Wallet tracking data is sensitive.

Restrict access to:
  - State builder (read/write)
  - Strategies (read-only)
  - Analysis tools (read-only)

Never expose publicly.

---

MONITORING AND ALERTING

Metrics to Track

Active wallets: Count
Classifications: Distribution across classes
Match scores: Mean, min, max
Detection accuracy: % of setups confirmed
False positive rate: % of activations without follow-through

Alerts

Alert if:
  - Wallet count drops significantly (data loss)
  - Match scores drop (behavior drift)
  - False positive rate increases (misclassification)

---

ROADMAP FOR IMPLEMENTATION

Phase 1: Transaction Monitoring

Build transaction ingestion pipeline
Log all large trades
Validate data quality

Phase 2: Historical Analysis

Backfill 90 days of data
Compute behavioral features
Manual classification of top 50 wallets

Phase 3: Classification System

Implement rule-based classifier
Validate against manual classifications
Tune thresholds

Phase 4: Live Tracking

Activate live transaction monitoring
Compute features in real-time
Expose to hot state store

Phase 5: Strategy Integration

Add wallet signals to strategies
Test on paper trading
Validate improvement in detection quality

Phase 6: Refinement

Implement clustering for misclassifications
Add wallet grouping (fragmentation handling)
Optimize performance

---

SUCCESS CRITERIA

How you know wallet tracking is working:

1. Classification accuracy > 80%
   (Validated against manual review)

2. False positive rate < 20%
   (Wallet activates but no event follows)

3. Detection improvement > 20%
   (Strategy win rate with vs without wallet signals)

4. Latency < 1ms
   (From transaction to hot state update)

If these are not met:
  Wallet tracking is not ready for production

---

BOTTOM LINE

Wallet tracking is the final edge layer.

It converts:
  "Is this a liquidation hunt?"
  into
  "This wallet only shows up before hunts."

The system works because:

1. Manipulators have repeatable behavior
2. Behavior is observable
3. Observation precedes events
4. Timing is actionable

But only if:

Classification is accurate
Data is timely
Integration is clean
Strategies still validate fundamentals

Do not build this until core system works.
Wallet tracking amplifies edge, it does not create it.

---

PART 2: REAL-TIME WALLET POSITION MONITORING

The previous sections covered behavioral classification.
This section covers operational monitoring.

How to detect when watched wallets enter/exit positions in real-time.

---

DATA SOURCES FOR WALLET POSITIONS

Hyperliquid Position Data Sources:

Source 1: Public User API
  Endpoint: /info
  Method: userState
  Input: wallet_address
  Returns:
    - Current positions (symbol, size, entry price)
    - Margin info
    - Open orders
  
  Availability: Public, no auth required
  Rate limit: Varies (typically 10 req/sec)
  Latency: 100-500ms

Source 2: On-Chain Data (if available)
  - Transaction logs
  - Position contract events
  - Slower but more complete

Source 3: WebSocket Subscription (if available)
  - Real-time position updates
  - Best latency
  - May require special access

Recommended: Start with Source 1 (Public API), upgrade to WebSocket if available

---

MONITORING FREQUENCY

Polling Strategy:

Tier 1 Wallets (High-priority manipulators):
  - Poll every: 2 seconds
  - Known actors with consistent patterns
  - Highest priority indicator

Tier 2 Wallets (Medium-priority):
  - Poll every: 5 seconds
  - Less consistent or newer wallets

Tier 3 Wallets (Monitoring):
  - Poll every: 15 seconds
  - Low match_score, just watching

Adaptive Polling:

Increase frequency when:
  - Regime conditions met (OI elevated, funding skewed)
  - Wallet shows recent activity
  - Market stress detected

Decrease frequency when:
  - Wallet inactive for > 1 hour
  - No regime triggers
  - Conserve API quota

---

POSITION CHANGE DETECTION

Track for Each Wallet:

wallet_state = {
  "wallet_id": "hash_0xABC",
  "symbol": "BTC-PERP",
  "position_size": 10.0,  # Current position (can be negative for short)
  "entry_price": 50000,
  "last_update": timestamp,
  "position_history": [...],
}

On Each Poll:

1. Query wallet position
2. Compare to last known state
3. Detect changes

Change Detection Logic:

current_position = api.get_wallet_position(wallet_id, symbol)

if current_position != last_known_position:
  
  # Position opened
  if last_known == 0 and current != 0:
    emit_event("MANIPULATOR_POSITION_OPENED", {
      "wallet_id": wallet_id,
      "symbol": symbol,
      "direction": "LONG" if current > 0 else "SHORT",
      "size": abs(current),
      "entry_price": current_entry_price,
      "timestamp": now(),
    })
  
  # Position closed
  elif last_known != 0 and current == 0:
    emit_event("MANIPULATOR_POSITION_CLOSED", {
      "wallet_id": wallet_id,
      "symbol": symbol,
      "hold_time_ms": now() - position_open_time,
      "exit_price": current_price,
      "pnl_estimate": calculate_pnl(...),
    })
  
  # Position size changed (scaling in/out)
  elif abs(current - last_known) > threshold:
    emit_event("MANIPULATOR_POSITION_CHANGED", {
      "wallet_id": wallet_id,
      "previous_size": last_known,
      "new_size": current,
      "change_pct": (current - last_known) / last_known,
    })
  
  # Update internal state
  update_wallet_state(wallet_id, current_position)

---

INTEGRATION WITH HOT STATE STORE

Add to HotStateSnapshot:

active_manipulator_positions = [
  {
    "wallet_id": "hash_0xABC",
    "symbol": "BTC-PERP",
    "direction": "LONG",
    "size": 10.0,
    "entry_price": 50000,
    "time_in_position_ms": 120000,
    "behavioral_class": "MANIPULATOR",
    "match_score": 0.85,
  },
  ...
]

Update Frequency:

Hot state updated every poll (2-15 seconds depending on tier)

Strategies consume:

def should_enter(self):
  state = self.hot_state
  
  # Check if manipulator active
  manipulator_active = any(
    w for w in state.active_manipulator_positions
    if w.symbol == self.symbol and w.direction == self.expected_direction
  )
  
  if not manipulator_active:
    return False  # No manipulator activity detected
  
  # Additional checks...

---

HANDLING DATA GAPS

Problem: API may return stale data or miss updates

Detection:

if current_price_moved_significantly BUT wallet_position_unchanged:
  # Possible stale data
  flag_stale_wallet_data()

Response:

1. Retry query immediately
2. If still stale:
   - Mark wallet data as SUSPECT
   - Don't use for trading signals
3. After N seconds of fresh data:
   - Clear SUSPECT flag

Position Reconciliation:

Cross-check with multiple sources:
  - Compare API data to on-chain data (if available)
  - Detect if position "teleported" (impossible change)
  - Alert on inconsistency

---

RATE LIMIT MANAGEMENT

Problem: Polling 50 wallets every 2 seconds = 25 req/sec

Rate Limit Budget:

Available: 10 req/sec (assumed Hyperliquid limit)
Required: 25 req/sec (50 wallets @ 2s)

Conflict!

Solutions:

Option 1: Prioritize Wallets
  - Tier 1 (10 wallets): 2s polling = 5 req/sec
  - Tier 2 (20 wallets): 5s polling = 4 req/sec
  - Tier 3 (20 wallets): 15s polling = 1.3 req/sec
  Total: ~10.3 req/sec ✓ Fits

Option 2: Batch Requests
  - If API supports batching
  - Single request for multiple wallets
  - Reduces request count

Option 3: WebSocket (if available)
  - Subscribe to wallet position updates
  - No polling needed
  - Best solution

Fallback During Rate Limits:

If rate limited:
  - Double polling intervals
  - Prioritize Tier 1 wallets only
  - Resume normal after limit lifts

---

WALLET POSITION EVENT STREAM

Events Emitted:

Event: MANIPULATOR_POSITION_OPENED
Trigger: Tracked wallet opens position
Payload:
  - wallet_id
  - symbol
  - direction (LONG/SHORT)
  - size
  - entry_price
  - timestamp

Event: MANIPULATOR_POSITION_CLOSED
Trigger: Tracked wallet closes position
Payload:
  - wallet_id
  - symbol
  - hold_time_ms
  - exit_price
  - estimated_pnl

Event: MANIPULATOR_SCALING
Trigger: Wallet increases/decreases position size
Payload:
  - wallet_id
  - size_change
  - new_total_size

Event: MANIPULATOR_EXIT_DETECTED
Trigger: Behavioral exit pattern (switching to passive orders)
Payload:
  - wallet_id
  - exit_phase (UNWINDING, DISTRIBUTING)
  - match_score

Strategies subscribe to these events (integrated with HLP14 lifecycle).

---

PERFORMANCE OPTIMIZATION

Caching:

Cache wallet position data:
  - TTL: 2 seconds (for Tier 1), 5s (Tier 2), 15s (Tier 3)
  - Multiple consumers read from cache
  - Single poller updates cache

Parallel Polling:

Poll wallets concurrently:
  - Use async/await or threading
  - Respect rate limits with semaphore
  - Process results as they arrive

Example (Python):

async def poll_all_wallets():
  semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
  
  async def poll_wallet(wallet_id):
    async with semaphore:
      position = await api.get_wallet_position(wallet_id)
      process_position_update(wallet_id, position)
  
  tasks = [poll_wallet(w) for w in tracked_wallets]
  await asyncio.gather(*tasks)

---

STALENESS DETECTION

Mark wallet data stale if:

1. API query timeout
2. Last successful update > max_staleness_threshold
3. Obvious data inconsistency

Staleness Thresholds:

Tier 1: Stale if > 10 seconds old
Tier 2: Stale if > 20 seconds old
Tier 3: Stale if > 60 seconds old

Response to Stale Data:

1. Flag wallet as STALE in hot state
2. Strategies ignore stale wallet signals
3. Alert if Tier 1 wallet stale
4. Retry polling more frequently
5. After recovery, clear STALE flag

---

WALLET STATE PERSISTENCE

Store wallet position state:

Database Table: wallet_positions

Columns:
  - wallet_id: string
  - symbol: string
  - position_size: float
  - entry_price: int64
  - entry_time: timestamp
  - last_update: timestamp
  - behavioral_class: enum
  - match_score: float

Purpose:
  - Survive restarts
  - Historical analysis
  - Behavioral classification data

Update Frequency:
  - On every position change
  - Async writes (don't block polling)

---

MONITORING METRICS FOR WALLET TRACKING

Track:

Polling Success Rate:
  - Successful polls / attempted polls
  - Target: > 99%

Polling Latency:
  - Time to poll all wallets
  - Target: < 5 seconds (for all tiers)

Detection Latency:
  - Time from wallet position change to event emission
  - Target: < 10 seconds

Stale Wallet Count:
  - Number of wallets with stale data
  - Target: 0

Rate Limit Events:
  - Count of rate limit hits
  - Target: < 1 per hour

---

FAILURE MODES IN WALLET MONITORING

Failure Mode 1: API Unavailable

Response:
  - Use cached data (mark as stale after TTL)
  - Alert operator
  - Strategies ignore wallet signals
  - Retry with exponential backoff

Failure Mode 2: Wallet Data Inconsistent

Example: Position suddenly changes by 100x (impossible)

Response:
  - Reject update as invalid
  - Flag wallet as SUSPECT
  - Alert for investigation
  - Cross-check with alternate source

Failure Mode 3: All Wallets Go Silent

Detection: No position changes for > 30 minutes

Possible Causes:
  - API broken
  - Market actually quiet
  - Data pipeline issue

Response:
  - Verify via manual query
  - Check other data sources
  - If API broken: Alert + disable wallet signals

---

TESTING WALLET MONITORING

Unit Tests:

[ ] Test position change detection (open, close, scale)
[ ] Test rate limit handling
[ ] Test data staleness detection
[ ] Test event emission
[ ] Test polling scheduler

Integration Tests:

[ ] Poll actual wallets (testnet)
[ ] Detect real position changes
[ ] Verify event stream works
[ ] Test under rate limits

Simulation Tests:

[ ] Simulate 50 wallets with position changes
[ ] Verify all changes detected
[ ] Measure polling latency
[ ] Verify rate limits respected

---

WALLET MONITORING BOTTOM LINE

Wallet tracking has two parts:

1. Behavioral Classification (Part 1)
   - Analyze historical patterns
   - Classify wallet types
   - Offline, compute-heavy

2. Real-Time Monitoring (Part 2)
   - Poll wallet positions
   - Detect changes in real-time
   - Online, latency-sensitive

Both are needed:
  - Classification tells you WHO to watch
  - Monitoring tells you WHEN they act

Without monitoring:
  - Behavioral classification is academic
  - Cannot use wallet signals in real-time
  - Miss the "arming indicator" (HLP4)

With monitoring:
  - Know when manipulators activate
  - Get early warning
  - Act pre-emptively

Real-time wallet monitoring is the bridge between:
  - Theory (behavioral classification)
  - Trading signals (event lifecycle)

Build it carefully, respect rate limits, handle failures gracefully.

