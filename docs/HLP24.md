DATA STORAGE & LABELING STRATEGY
Store Raw, Label Later, Preserve Optionality

---

CORE PRINCIPLE

Your hypothesis about what matters WILL change.

Today: "Cascades are OI drops >15%"
Tomorrow: "Actually 12% drops matter too"

If you only stored data matching today's definition, tomorrow's insight is lost.

Store raw facts. Derive labels later. Storage is cheap. Hindsight is expensive.

---

PART 1: WHY NOT LABEL BEFORE STORING

Labeling Before Storage (Wrong):

Day 1:  Define "cascade" as OI drop >15%
Day 1:  Only store events matching this definition
Day 30: Discover 12% drops also tradeable
Day 30: That data is gone forever

You made an irreversible decision with incomplete information.

Storing Raw, Labeling Later (Correct):

Day 1:  Store all OI snapshots (no filtering)
Day 30: Discover 12% drops matter
Day 30: Query historical data
Day 30: Relabel everything with new definition
Day 30: Full dataset available for backtesting

You preserved optionality.

---

PART 2: WHAT IS "RAW" DATA

Raw data = observable facts without interpretation.

Store This (Raw Facts):

timestamp: int64 (nanoseconds)
symbol: string
open_interest: int64
funding_rate: int64 (basis points)
mark_price: int64 (price in cents or smallest unit)
index_price: int64
bid_depth_1pct: int64 (USD value within 1% of mid)
ask_depth_1pct: int64
trades: array of {price, size, side, timestamp}
liquidations: array of {price, size, side, timestamp}

Do NOT Store This (Derived/Labeled):

regime: "CASCADE"              # Your interpretation
cascade_detected: true         # Your label
oi_spike_score: 0.85          # Your computation
is_tradeable: true            # Your judgment

Derived values are computed from raw data.
If your computation is wrong, fix the code.
If raw data is missing, you're stuck.

---

PART 3: STORAGE ARCHITECTURE

Two-Layer Architecture:

Layer 1: Cold Storage (Immutable Raw Data)

Purpose: Preserve all facts for future analysis
Content: Raw market data, no labels
Mutability: Append-only, never modify
Retention: Forever (or as long as useful)
Access: Batch queries, backtesting, research

Layer 2: Hot State (Ephemeral Derived State)

Purpose: Real-time trading decisions
Content: Computed labels, regime classification
Mutability: Constantly updated, never persisted
Retention: Current moment only
Access: Strategy evaluation, execution


Data Flow:

┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  WebSocket  │ ──► │  Cold Storage   │ ──► │  Batch Labeling │
│  Raw Stream │     │  (append-only)  │     │  (run anytime)  │
└─────────────┘     └─────────────────┘     └─────────────────┘
       │
       ▼
┌─────────────────┐
│    Hot State    │  ← Derived labels for trading
│   (ephemeral)   │    Computed from raw, not stored
└─────────────────┘

---

PART 4: STORAGE SCHEMA

Recommended Tables:

Table: market_snapshots

CREATE TABLE market_snapshots (
    ts              INTEGER NOT NULL,  -- nanoseconds
    symbol          TEXT NOT NULL,
    open_interest   INTEGER,
    funding_rate    INTEGER,           -- basis points
    mark_price      INTEGER,
    index_price     INTEGER,
    bid_depth_1pct  INTEGER,
    ask_depth_1pct  INTEGER,
    PRIMARY KEY (ts, symbol)
);

Table: trades

CREATE TABLE trades (
    ts          INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    price       INTEGER,
    size        INTEGER,
    side        TEXT,                  -- 'buy' or 'sell'
    is_liquidation BOOLEAN DEFAULT FALSE
);

Table: orderbook_snapshots (if storing full book)

CREATE TABLE orderbook_snapshots (
    ts          INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT,                  -- 'bid' or 'ask'
    price       INTEGER,
    size        INTEGER
);

Index Recommendations:

CREATE INDEX idx_snapshots_symbol_ts ON market_snapshots(symbol, ts);
CREATE INDEX idx_trades_symbol_ts ON trades(symbol, ts);

---

PART 5: LABELING PROCESS

Labels are derived, not stored with raw data.

Step 1: Define Event Mechanically

No human judgment. Pure conditions.

def is_cascade_event(window: List[Snapshot]) -> bool:
    """
    Mechanical definition of cascade.
    This is YOUR HYPOTHESIS about what constitutes a cascade.
    """
    first = window[0]
    last = window[-1]

    oi_change = (last.open_interest - first.open_interest) / first.open_interest
    duration_sec = (last.ts - first.ts) / 1e9

    return (
        oi_change < -0.15 and          # OI dropped >15%
        duration_sec < 60 and          # Within 60 seconds
        abs(first.funding_rate) > 100  # Funding was skewed (>1%)
    )

Step 2: Run Labeling Over Historical Data

Batch job, not real-time.

def label_historical_data(start_ts: int, end_ts: int) -> List[LabeledEvent]:
    events = []

    for symbol in SYMBOLS:
        snapshots = query_snapshots(symbol, start_ts, end_ts)

        # Sliding window
        for i in range(len(snapshots) - 60):
            window = snapshots[i:i+60]  # 60-second window

            if is_cascade_event(window):
                events.append(LabeledEvent(
                    ts=window[0].ts,
                    symbol=symbol,
                    event_type="CASCADE",
                    oi_drop=calculate_oi_drop(window),
                    outcome=calculate_outcome(window[-1].ts)  # What happened next
                ))

    return events

Step 3: Calculate Outcomes

Self-labeling based on what actually happened.

def calculate_outcome(event_ts: int, symbol: str) -> Outcome:
    """
    What happened in the 5 minutes after the event?
    This is ground truth for validating your strategy.
    """
    future_snapshots = query_snapshots(
        symbol,
        event_ts,
        event_ts + 5 * 60 * 1e9  # 5 minutes
    )

    entry_price = future_snapshots[0].mark_price
    prices = [s.mark_price for s in future_snapshots]

    max_up = max(prices) / entry_price - 1
    max_down = min(prices) / entry_price - 1

    return Outcome(
        reversal=max_up > 0.01,        # Bounced >1%
        continuation=max_down < -0.02,  # Kept dumping >2%
        max_favorable=max_up,
        max_adverse=max_down
    )

---

PART 6: CHANGING YOUR DEFINITIONS

This is why you store raw data.

Scenario: Threshold Was Wrong

Original: OI drop >15% = cascade
Problem:  Missing good trades at 12% drops
Fix:      Change threshold in labeling code
Result:   Relabel all historical data with new definition
          Run backtest
          Compare results
          No data loss

Scenario: New Pattern Discovered

Original: Only tracking OI drops
Discovery: Funding velocity matters too
Fix:       Add funding_velocity to labeling logic
Result:    Raw data has funding_rate at every timestamp
           Calculate velocity = (funding[t] - funding[t-1]) / dt
           Add to event definition
           Relabel historical data
           Test hypothesis

Scenario: Definition Was Completely Wrong

Original: Thought OI drops mattered
Reality:  Depth asymmetry is the real indicator
Fix:      Write new labeling function using depth data
Result:   Raw data has bid_depth and ask_depth
          New labels based on depth ratio
          Old OI-based labels discarded
          Start fresh with new hypothesis

---

PART 7: HOT STATE FOR TRADING

While raw data goes to cold storage, trading needs real-time derived state.

Hot State Structure:

@dataclass
class HotState:
    # Raw (from latest snapshot)
    ts: int
    symbol: str
    mark_price: int
    open_interest: int
    funding_rate: int

    # Derived (computed, not stored)
    oi_change_60s: float
    funding_velocity: float
    depth_asymmetry: float
    regime: str                # "QUIET", "BUILDING", "CASCADE", etc.

    # Event tracking (ephemeral)
    active_events: List[Event]

Hot State Rules:

1. Computed fresh each tick from raw data
2. Never persisted (recompute on restart)
3. Used only for real-time decisions
4. If computation is wrong, fix code and it's immediately correct
5. Separate from cold storage entirely

---

PART 8: STORAGE COST REALITY

Storing raw data is cheap.

Calculation:

1 snapshot per symbol per 100ms
50 symbols
= 500 snapshots/second
= 43.2M snapshots/day

Each snapshot: ~100 bytes
= 4.3 GB/day uncompressed
= ~500 MB/day compressed (10:1 typical for time series)
= 15 GB/month
= 180 GB/year

Cloud Storage Costs:

S3 Standard:     $0.023/GB/month = $4/month
S3 Glacier:      $0.004/GB/month = $0.70/month (for old data)
Local SSD:       Negligible if you have the space

For $50/year, you preserve complete optionality.
One good trade pays for decades of storage.

---

PART 9: WHAT TO FILTER (Exceptions)

Some filtering before storage is acceptable.

OK to Filter:

1. WebSocket heartbeats (no information)
2. Duplicate messages (same data, different delivery)
3. Symbols you'll never trade (if storage constrained)
4. Sub-millisecond duplicates (same tick, multiple messages)

NOT OK to Filter:

1. "Uninteresting" periods (quiet markets still matter)
2. Events below your threshold (threshold may change)
3. Symbols outside your current focus (focus may change)
4. Data that "looks wrong" (might be real, investigate later)

Rule of Thumb:

If filtering is LOSSY (can't recover original): Don't filter
If filtering is DEDUPLICATION (same info, fewer bytes): OK

---

PART 10: IMPLEMENTATION CHECKLIST

[ ] Set up cold storage (SQLite, Parquet, or time-series DB)
[ ] Define raw schema (no derived fields)
[ ] Build ingestion pipeline (WebSocket → storage)
[ ] Verify data completeness (no gaps)
[ ] Build labeling pipeline (batch job)
[ ] Define event types mechanically (code, not prose)
[ ] Add outcome calculation (what happened after)
[ ] Build relabeling capability (change definition, rerun)
[ ] Separate hot state computation from storage
[ ] Estimate storage costs, set retention policy

---

PART 11: COMMON MISTAKES

Mistake 1: Storing Only "Interesting" Events

"I'll just store cascade events to save space"

Problem: You don't know what's interesting yet.
         Your definition of interesting will change.
         You need non-events to calculate baseline/normal.

Fix: Store everything. Filter at query time, not storage time.

Mistake 2: Storing Derived Labels as Ground Truth

"I'll store regime='CASCADE' in the raw table"

Problem: Your regime classification may be wrong.
         Now your raw data is polluted with bad labels.
         Can't tell raw facts from interpretations.

Fix: Raw tables have only raw data.
     Labels in separate tables or computed on demand.

Mistake 3: Modifying Historical Data

"I found a bug, let me fix the old data"

Problem: Now you don't know what your system actually saw.
         Can't reproduce past behavior.
         Debugging becomes impossible.

Fix: Append-only storage. Never modify.
     If data was wrong, add correction record, don't edit.

Mistake 4: Skipping "Boring" Periods

"Nothing happened overnight, I'll skip storing that"

Problem: "Nothing happened" is valuable information.
         You need baseline to detect anomalies.
         Quiet periods may have subtle precursor patterns.

Fix: Store 24/7. Compress quiet periods if needed, but keep them.

---

BOTTOM LINE

Store raw facts. Label later.

Your definition of "interesting" will change.
Your thresholds will change.
Your understanding will evolve.

Raw data preserves optionality.
Labels are ephemeral hypotheses.

Storage is cheap. Hindsight is expensive.

When in doubt, store more, not less.
You can always delete later. You can never recover what you didn't store.
