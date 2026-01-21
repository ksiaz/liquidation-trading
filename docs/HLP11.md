DATA SCHEMA DESIGN
Formal Specification of All Data Structures

This document defines the exact data schemas for:

1. Hot State Store (what strategies read)
2. Event Stream (what strategies react to)
3. Cold Storage (what gets logged for replay)
4. Primitives (what strategies consume)

Every field is specified with type, range, and staleness constraints.

This is the contract between the state builder and strategies.

---

HYPERLIQUID NODE SOURCES (Exact Fields):

All data comes from these node fields:
- asset_to_oi_szi → OI per asset
- user_to_state[addr] → Position (s=size, e=entry, l=leverage, M=margin)
- users_with_positions → All 66,280 wallets with positions
- funding_tracker.asset_to_premiums → Funding per asset
- books[asset].halfs[0/1] → Orderbook (bids/asks)
- books[asset].last_trade_px → Last price

Schemas below define how this raw node data is transformed into Hot State.

---

DESIGN PRINCIPLES

Principle 1: Immutability

Once created, data structures are immutable.
Updates create new instances, not mutations.

This enables:
  - Lock-free reads
  - Deterministic replay
  - Race-free strategy consumption

Principle 2: Timestamp Everything

Every data structure includes:

capture_time: When the node saw this data
process_time: When the state builder processed it
sequence_number: Monotonic ID for ordering

Principle 3: NULL vs Zero

Missing data is NULL, not zero.

If a metric cannot be calculated:
  Return NULL
  Do not return 0
  Do not interpolate

Strategies must check for NULL before using data.

Principle 4: Precision Over Convenience

Store raw values, not formatted strings.

Price: Store as integer (in minimal units)
Time: Store as nanoseconds since epoch
Percentage: Store as basis points (10000 = 100%)

Let consumers format for display.

---

HOT STATE STORE SCHEMA

This is the single source of truth for real-time market state.

Structure: Versioned Snapshot

Every update creates a new snapshot with incremented version.

Version: Integer, monotonically increasing
Timestamp: Nanoseconds since epoch
Sequence: Node message sequence number

Market State Snapshot

symbol: string
  The trading pair (e.g., "BTC-PERP")

mark_price: int64
  Current mark price in minimal units (e.g., cents)
  Range: > 0
  Staleness: < 1000ms

index_price: int64
  Current index price in minimal units
  Range: > 0
  Staleness: < 1000ms

funding_rate: int64
  Current funding rate in basis points
  Range: any (can be negative)
  Staleness: < 5000ms

open_interest: int64
  Current open interest in contracts
  Range: >= 0
  Staleness: < 1000ms

L2 Orderbook

bid_levels: array of OrderLevel (max 50)
ask_levels: array of OrderLevel (max 50)

OrderLevel:
  price: int64 (minimal units)
  size: int64 (contracts)
  count: int32 (number of orders, if available)

Orderbook must be sorted:
  Bids: descending by price
  Asks: ascending by price

Rolling Aggregates (1-second window)

oi_change_1s: int64
  Change in OI over last second (can be negative)

volume_buy_1s: int64
  Buyer-initiated volume (contracts)

volume_sell_1s: int64
  Seller-initiated volume (contracts)

depth_bid_20bps: int64
  Total bid size within 20bps of mid

depth_ask_20bps: int64
  Total ask size within 20bps of mid

aggressive_buy_count_1s: int32
  Number of aggressive buy trades

aggressive_sell_count_1s: int32
  Number of aggressive sell trades

Rolling Aggregates (5-second window)

oi_change_5s: int64
oi_pct_change_5s: int32 (basis points)
volume_buy_5s: int64
volume_sell_5s: int64
funding_velocity_5s: int64 (basis points per hour)
depth_ratio_5s: int32 (bid/ask ratio, basis points)

Rolling Aggregates (15-minute window)

oi_baseline_15m: int64 (mean OI)
oi_stddev_15m: int64 (standard deviation)
funding_mean_15m: int64 (mean funding rate)
funding_stddev_15m: int64 (standard deviation)
volume_baseline_15m: int64 (mean volume per second)
depth_symmetry_15m: int32 (bid/ask balance score)

Rolling Aggregates (1-hour window)

oi_trend_1h: int32 (slope, basis points per minute)
funding_trend_1h: int32 (slope, basis points per hour)
volatility_1h: int32 (realized vol, basis points)

Derived Metrics

liq_inevitability_score: int32
  Ratio of estimated liq size to available depth
  Range: 0 - 10000 (0 = no risk, 10000 = certain)
  Formula: (estimated_liq_size / depth) * 10000

funding_skew_zscore: int32
  Z-score of current funding vs baseline
  Range: -10000 to +10000 (in basis points)

oi_elevation_zscore: int32
  Z-score of current OI vs baseline
  Range: -10000 to +10000

regime_classification: enum
  Values: SIDEWAYS, EXPANSION, DISABLED
  Based on controller logic

Wallet Activity (if tracking enabled)

active_wallets: array of WalletActivity (max 20)

WalletActivity:
  wallet_id: string (hash or address)
  direction: enum (LONG, SHORT, NEUTRAL)
  size_rank: int32 (1 = largest, etc.)
  entry_time: int64 (nanoseconds)
  is_passive: bool (limit orders vs market)
  behavioral_class: enum (MANIPULATOR, DIRECTIONAL, UNKNOWN)

Staleness Indicators

data_age_ms: int64
  Time since last state update (milliseconds)
  Range: >= 0
  If > 1000ms, strategies should not trade

sequence_gap_detected: bool
  True if sequence numbers have gaps
  Indicates missed messages

Health Flags

node_connected: bool
websocket_active: bool
last_heartbeat_ms: int64
state_builder_healthy: bool

---

EVENT STREAM SCHEMA

Events are emitted when structural changes occur.

Base Event Structure

event_id: string (UUID)
event_type: enum (see below)
timestamp: int64 (nanoseconds)
symbol: string
sequence: int64

Event Types

Event: OI_SPIKE

oi_before: int64
oi_after: int64
change_pct: int32 (basis points)
duration_ms: int64

Trigger condition:
  OI change > threshold in < time_window

Event: OI_COLLAPSE

oi_before: int64
oi_after: int64
change_pct: int32 (basis points, negative)
duration_ms: int64

Trigger condition:
  OI drops > threshold in < time_window

Event: FUNDING_ACCELERATION

funding_rate_before: int64
funding_rate_after: int64
velocity: int64 (basis points per hour)

Trigger condition:
  Funding rate change velocity exceeds threshold

Event: FUNDING_SNAPBACK

funding_peak: int64
funding_current: int64
snapback_pct: int32 (basis points)

Trigger condition:
  Funding reverses sharply after extreme reading

Event: DEPTH_THINNING

side: enum (BID, ASK)
depth_before: int64
depth_after: int64
distance_bps: int32 (distance from mid)

Trigger condition:
  Depth drops > threshold at specific distance

Event: LIQUIDITY_VACUUM

bid_depth_change_pct: int32
ask_depth_change_pct: int32

Trigger condition:
  Both sides thin simultaneously

Event: AGGRESSIVE_FLOW_SURGE

side: enum (BUY, SELL)
volume: int64
trades_count: int32
duration_ms: int64
price_impact_bps: int32

Trigger condition:
  Aggressive volume spike without proportional price move

Event: MANIPULATOR_WALLET_ACTIVATED

wallet_id: string
direction: enum (LONG, SHORT)
size_estimate: int64
behavioral_signature: string

Trigger condition:
  Known manipulator wallet becomes active

Event: MANIPULATOR_WALLET_EXITED

wallet_id: string
hold_time_ms: int64
exit_type: enum (AGGRESSIVE, PASSIVE)

Trigger condition:
  Known manipulator wallet closes position

Event: LIQUIDATION_BAND_APPROACHED

price_level: int64
distance_bps: int32
estimated_liq_size: int64
available_depth: int64

Trigger condition:
  Price within threshold of suspected liq band

Event: REGIME_CHANGE

regime_before: enum
regime_after: enum
trigger_reason: string

Trigger condition:
  Regime classification changes

Event: SETUP_DETECTED

strategy_id: string
setup_type: enum (GEOMETRY, KINEMATICS, CASCADE)
confidence_score: int32 (0-10000)
setup_params: JSON

Trigger condition:
  Strategy detects valid setup

Event: SETUP_INVALIDATED

strategy_id: string
setup_type: enum
invalidation_reason: string

Trigger condition:
  Active setup invalidates

---

COLD STORAGE SCHEMA

All data logged for replay and analysis.

Log Entry Types

Type 1: Raw Node Message

entry_type: "NODE_MESSAGE"
timestamp: int64
sequence: int64
message_type: string (e.g., "orderbook", "trades", "funding")
payload: bytes (raw message)

Type 2: State Snapshot

entry_type: "STATE_SNAPSHOT"
timestamp: int64
sequence: int64
snapshot_version: int64
state: HotStateSnapshot (full structure)

Frequency: Every N seconds or on significant change

Type 3: Event Emission

entry_type: "EVENT"
timestamp: int64
sequence: int64
event: Event (full structure)

Type 4: Strategy Decision

entry_type: "STRATEGY_DECISION"
timestamp: int64
sequence: int64
strategy_id: string
state_before: enum
state_after: enum
decision_type: enum (SCAN, ARM, ENTER, EXIT, INVALIDATE)
inputs: JSON (all metrics used in decision)
outputs: JSON (result of decision)

Type 5: Trade Execution

entry_type: "TRADE_EXECUTION"
timestamp: int64
sequence: int64
strategy_id: string
direction: enum (LONG, SHORT)
entry_price: int64
exit_price: int64
size: int64
stop_price: int64
target_price: int64
hold_time_ms: int64
pnl: int64
exit_reason: string
metrics: JSON (OI, funding, depth at entry/exit)

Storage Format

Format: Newline-delimited JSON (NDJSON)

One log entry per line
Append-only
Gzip compressed

File rotation:

Rotate daily
Keep last N days
Archive older logs

Indexing:

Timestamp index for fast replay
Sequence number index for gap detection

---

PRIMITIVES SCHEMA

Primitives are high-level abstractions that strategies consume.

These are computed by the state builder from raw state.

Primitive: LiquidationBand

price_level: int64
estimated_size: int64 (contracts that would liquidate)
match_score: int32 (0-10000, how certain)
side: enum (LONG_LIQS, SHORT_LIQS)
detection_method: enum (ROUND_NUMBER, FAILED_BREAKOUT, DEPTH_ANOMALY)

Primitive: HunterIntent

is_active: bool
direction: enum (LONG, SHORT, NONE)
match_score: int32 (0-10000)
entry_time: int64
wallet_id: string (optional)

Primitive: RegimeClassification

regime: enum (SIDEWAYS, EXPANSION, DISABLED)
match_score: int32 (0-10000)
duration_in_regime_ms: int64
transition_probability: array of RegimeTransitionProb

RegimeTransitionProb:
  target_regime: enum
  probability: int32 (0-10000)

Primitive: MarketStress

stress_level: int32 (0-10000)
  0 = calm, 10000 = extreme stress

stress_components:
  oi_stress: int32 (deviation from baseline)
  funding_stress: int32 (deviation from baseline)
  liquidity_stress: int32 (depth depletion)
  volatility_stress: int32 (recent price movement)

Primitive: InventoryOverhang

detected: bool
direction: enum (LONG, SHORT, NONE)
estimated_size: int64
distribution_phase: enum (COMPRESSION, DISTRIBUTION, COMPLETE)

Primitive: CascadeExhaustion

exhaustion_detected: bool
exhaustion_match_score: int32 (0-10000)
indicators:
  oi_collapsed: bool
  volume_spiked: bool
  price_extension_stopped: bool
  aggressive_flow_ended: bool

---

INTER-SCHEMA RELATIONSHIPS

Hot State → Events

State builder reads hot state
Compares to previous state
Emits events when thresholds crossed

Events → Primitives

Multiple events combine to create primitives

Example:
  OI_SPIKE + FUNDING_ACCELERATION + DEPTH_THINNING
  → LiquidationBand primitive

Primitives → Strategy Decisions

Strategies consume primitives, not raw state
Primitives abstract complexity

Hot State + Primitives → Cold Storage

Every state update logged
Every primitive update logged
Every strategy decision logged

---

SCHEMA VERSIONING

All schemas are versioned.

Schema identifier format:
  schema_type/version
  Example: "hot_state/v1", "event/v1"

Version increments when:

New fields added
Field types change
Semantics change

Backward compatibility:

New fields: Optional, default to NULL
Removed fields: Deprecated, not removed for N versions
Type changes: New version required

---

VALIDATION RULES

Every data structure must be validated before use.

Hot State Validation

✓ mark_price > 0
✓ open_interest >= 0
✓ data_age_ms < max_staleness
✓ sequence monotonically increasing
✓ bid levels sorted descending
✓ ask levels sorted ascending
✓ No NULL in critical fields (price, OI, funding)

Event Validation

✓ event_id unique
✓ timestamp <= current_time
✓ event_type valid enum value
✓ All required fields present

Primitive Validation

✓ Match scores in range [0, 10000]
✓ Enums valid
✓ Timestamps reasonable

If validation fails:

Log error
Drop invalid data
Do not propagate to strategies

---

PERFORMANCE CONSTRAINTS

Hot State Store

Read latency: < 100 microseconds
Update latency: < 1 millisecond
Memory footprint: < 10 MB per symbol

Event Stream

Emission latency: < 500 microseconds
Delivery latency: < 1 millisecond
Backlog capacity: 10,000 events

Cold Storage

Write latency: < 10 milliseconds (async)
Rotation time: < 1 second
Compression ratio: > 5:1

---

TEST DATA GENERATION

For testing without node:

Mock Hot State

Generate realistic state snapshots
Include noise and jitter
Simulate state transitions

Mock Events

Generate event sequences
Include rare events (liquidation cascades)
Test strategy reactions

Replay Harness

Load saved cold storage
Replay state updates
Verify strategy decisions match

---

SCHEMA MIGRATION STRATEGY

When schemas change:

1. Create new version (v2)
2. Maintain old version (v1) for N days
3. Run both in parallel
4. Validate outputs match
5. Deprecate old version
6. Remove old version after grace period

Never break existing consumers.

---

BOTTOM LINE

Data schemas are the contract between system components.

Every field must be:
  - Typed precisely
  - Validated on read
  - Versioned for evolution
  - Timestamped for replay

Schemas must support:
  - Lock-free reads
  - Deterministic replay
  - Performance constraints
  - Graceful degradation

If schemas are wrong:
  Everything built on them is wrong
