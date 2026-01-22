Below is a production-grade way to serve data from a Hyperliquid non-validator node into a trading system, optimized for latency, determinism, and strategy isolation. This is how you prevent data plumbing from becoming your bottleneck.

I will assume you already run a stable node on Hyperliquid and care about liquidation anticipation + actor behavior, not generic charting.

---

HYPERLIQUID NODE DATA (Exact Fields):

asset_to_oi_szi → OI per asset (real-time)
user_to_state[addr] → Position (s=size, e=entry, l=leverage, M=margin)
users_with_positions → All 66,280 wallets with positions
funding_tracker.asset_to_premiums → Funding per asset
books[asset].halfs → Orderbook (halfs[0]=bids, halfs[1]=asks)
books[asset].last_trade_px → Last price

Primitive Calculations:
- OI Spike: asset_to_oi_szi / baseline_15m
- Funding Velocity: premium_now - premium_15m_ago
- Depth Asymmetry: sum(halfs[0]) / sum(halfs[1])
- Wallet Change: user_to_state[addr].s current vs previous
- Liquidation: wallet disappears from users_with_positions

---

1. First Principle: Separate “Truth” From “Use”

Your node produces ground truth.
Your trading system consumes interpreted state.

Never let strategies talk directly to raw node feeds.

Why:

Raw data is noisy

Formats evolve

Strategies should not block ingestion

You want replayability and determinism

So the architecture must enforce one-way flow.

2. High-Level Architecture (Correct Decomposition)
[ Hyperliquid Node ]
        │
        ▼
[ Ingestion Layer ]
        │
        ▼
[ Normalization / State Builder ]
        │
        ├──► [ Hot State Store ]
        │
        ├──► [ Event Stream ]
        │
        └──► [ Cold Storage / Replay ]
                    │
                    ▼
             [ Trading System ]


Each box has a single responsibility.
This is non-negotiable at scale.

3. Ingestion Layer: “Do Not Think Here”

Purpose:
Consume node data as fast and faithfully as possible.

Design rules

No aggregation

No filtering

No business logic

No blocking calls

Typical inputs

Orderbook diffs / snapshots

Trades

Funding updates

OI updates

Liquidation engine signals (implicit)

Output

Append-only messages with:

Timestamp (node-received)

Sequence number

Raw payload

Think of this as a packet capture, not analytics.

4. Normalization & State Builder (This Is Where Edge Lives)

This layer converts noise into coherent market state.

Responsibilities

Maintain authoritative in-memory state:

Full L2 book

Mark price

OI

Funding

Detect structural events:

OI acceleration

Funding velocity

Depth thinning

Aggression vs absorption

Key rule

This layer produces facts, not opinions.

Example outputs:

“Bid depth < X within Y bps”

“OI dropped Z% in T seconds”

“Aggressive buys failed to move price”

No strategy logic here either.

5. Hot State Store (Latency-Critical)

This is what strategies read synchronously.

Properties

In-memory

Lock-free reads

Single writer

Multiple readers

Typical contents

Latest book snapshot

Rolling aggregates (1s, 5s, 15m)

Precomputed ratios (liq size vs depth)

Wallet activity flags

This is your shared reality.

If this store lags or blocks, you lose money.

6. Event Stream (Asynchronous Alpha Feeds)

Not everything needs polling.

Use an event bus for:

“Liquidation inevitability crossed”

“Manipulator wallet activated”

“OI collapse detected”

“Funding snapback started”

Why this matters

Strategies become event-driven

Lower CPU usage

Cleaner logic

Easier backtesting

You want strategies reacting to state changes, not raw ticks.

7. Cold Storage + Replay (Non-Optional)

If you cannot replay, you cannot improve.

You must store:

Raw node messages

Normalized state transitions

Strategy decisions (inputs + outputs)

Why

Debug false positives

Validate new heuristics

Reproduce rare liquidation cascades

Train classifiers

This is where real edge compounds over time.

8. Strategy Consumption Model (Hard Rule)

Strategies never:

Subscribe directly to the node

Maintain their own market state

Parse raw messages

They:

Read hot state

Subscribe to derived events

Submit intents (orders)

This prevents:

Inconsistent views

Race conditions

Hidden coupling

Strategy interference

9. Latency vs Stability: The Correct Trade-Off

You do not want the lowest possible latency everywhere.

You want:

Ultra-low latency ingestion

Slightly slower but stable state building

Deterministic strategy reads

A fast but inconsistent system is worse than a slightly slower consistent one—especially for liquidation logic, where timing precision > raw speed.

10. Failure Modes You Must Design For

If you ignore these, you will bleed PnL.

Mandatory safeguards

Backpressure handling

Partial state recovery

Snapshot rehydration

Sequence gap detection

Clock skew correction

Strategy circuit breakers

Markets do not pause for your bugs.

11. Mental Model to Keep

Think of your system as:

Node = reality

State builder = physics engine

Strategy = policy

Execution = actuator

Never collapse these layers.

Bottom Line

The correct approach to serving node data is:

One-way flow

Strict separation of concerns

State first, strategy second

Events over polling

Replay as a first-class citizen

Most traders lose not because they lack alpha, but because their data architecture leaks edge under stress.