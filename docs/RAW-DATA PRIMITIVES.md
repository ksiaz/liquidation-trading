RAW-DATA PRIMITIVES SPECIFICATION

(Constitution-Compliant)

0. Definition and Scope

A Raw-Data Primitive is a deterministic transformation of raw market data into a bounded factual description, without interpretation, prediction, confidence, or intent.

Invariants:

Derived only from raw data streams

Stateless or window-bounded

No semantic labels (bullish, bearish, strong, weak, important)

No aggregation across symbols unless explicitly defined

No dependence on execution state

No mandate logic embedded

Raw-data primitives do not decide actions.
They only exist.

1. Raw Data Sources (Authoritative)

Only the following inputs are permitted:

1.1 Trades
(timestamp, symbol, price, quantity, aggressor_side)

1.2 Liquidations
(timestamp, symbol, price, quantity, side)

1.3 Order Book (L2 or L3)
(timestamp, symbol, price, size, side, event_type)

1.4 Mark / Index Price
(timestamp, symbol, price)


No indicators, no OHLC candles, no VWAP, no funding, no “signals”.

2. Primitive Categories

Raw-data primitives fall into six non-overlapping categories:

Temporal

Price Motion

Volume / Flow

Liquidation

Order-Book Interaction

Historical Memory (Raw-Derived)

Each primitive is defined below.

3. Temporal Primitives
3.1 Time Window

Definition:
A bounded interval [t₀, t₁] with fixed duration Δt.

Fields:

start_time
end_time
duration_ms


Used only to bound observation windows.
No semantic meaning.

4. Price Motion Primitives
4.1 Price Delta

Definition:
Absolute or signed price change over a window.

Δprice = price(t₁) − price(t₀)


Fields:

start_price
end_price
delta
duration

4.2 Price Velocity

Definition:
Rate of price change over time.

velocity = Δprice / Δtime


No classification (fast / slow).

4.3 Directional Continuity

Definition:
Count of consecutive price updates with identical sign of Δprice.

Fields:

count
direction ∈ {+1, −1}


Purely descriptive.

5. Volume & Trade Flow Primitives
5.1 Trade Count

Definition:
Number of trades in a window.

5.2 Volume Sum

Definition:
Sum of traded quantity in a window.

5.3 Aggressor Imbalance

Definition:
Difference between aggressive buys and sells.

imbalance = buy_volume − sell_volume


No inference.

5.4 Trade Burst

Definition:
Trade count exceeds baseline count within Δt.

Fields:

count
window_duration


Baseline must be mechanical, not adaptive.

6. Liquidation Primitives
6.1 Liquidation Count

Definition:
Number of liquidation events in window.

6.2 Liquidation Volume

Definition:
Sum of liquidation quantities.

6.3 Liquidation Cluster

Definition:
Multiple liquidation events within price band ε and time Δt.

Fields:

event_count
price_band
time_span
side


No interpretation of “cascade”.

6.4 Liquidation Density

Definition:
Liquidation volume per unit price movement.

7. Order-Book Interaction Primitives
7.1 Resting Size at Price

Definition:
Total resting quantity at a price level.

7.2 Order Consumption

Definition:
Reduction in resting size at price due to trades.

Fields:

initial_size
consumed_size
remaining_size

7.3 Absorption Event

Definition:
Trades occur at a price without price movement while resting size decreases.

Fields:

price
consumed_size
duration


No “strength” or “support”.

7.4 Refill Event

Definition:
Resting size replenishes after consumption.

8. Historical Memory Primitives (Raw-Derived)

These are not indicators.
They are recorded past raw events.

8.1 Prior Event Region

Definition:
A price interval where a raw event occurred in the past.

Examples:

Past liquidation cluster

Past absorption event

Past trade burst

Fields:

price_low
price_high
event_type
timestamp

8.2 Region Revisit

Definition:
Current price enters a prior event region.

No reaction assumed.

8.3 Event Recurrence

Definition:
Same primitive re-occurs within same region.

9. Composite Raw Primitives (Allowed)

Composite primitives may exist only if all components are raw primitives.

Example:

Absorption + Trade Burst + No Price Movement


Still factual, not interpretive.

10. Explicitly Forbidden Constructs

❌ Trend
❌ Bias
❌ Strength
❌ Weakness
❌ Support / Resistance
❌ Momentum
❌ Reversal
❌ Opportunity
❌ Signal
❌ Setup

If a word implies intent or meaning, it is forbidden.

11. Relationship to Mandates (Boundary)

Raw-data primitives:

Do not emit mandates

Do not evaluate conditions

Do not know position state

Do not know risk

They may be consumed by mandate-emission logic, which is defined elsewhere.

12. Completion Status

This document defines the entire allowed vocabulary of raw-data facts.

Everything else in the system must be built on top of these primitives or not exist.