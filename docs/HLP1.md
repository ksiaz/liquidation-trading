NON-VALIDATOR NODE DATA ACCESS

What the Node Provides:

A non-validator Hyperliquid node provides:
- Orderbook state (L2 depth)
- Open interest per asset
- Funding rates and premiums
- Position data for all wallets
- Trade execution data

Data is received before public API dissemination.

---

OBSERVABLE DATA POINTS

1. Orderbook State

Available fields:
- books[asset].halfs[0] = bids (price, size pairs)
- books[asset].halfs[1] = asks (price, size pairs)
- books[asset].last_trade_px = last trade price

Derived observations:
- Depth at each price level
- Bid/ask asymmetry: sum(bids) / sum(asks)
- Depth changes over time

---

2. Open Interest

Available fields:
- asset_to_oi_szi = OI per asset in native units

Derived observations:
- OI change rate: current_oi / baseline_oi (15m window)
- OI direction: increasing or decreasing

---

3. Funding Rate

Available fields:
- funding_tracker.asset_to_premiums = funding premium per asset

Derived observations:
- Funding velocity: premium_now - premium_15m_ago
- Funding direction: positive (longs pay) or negative (shorts pay)

---

4. Position Data

Available fields:
- user_to_state[address] = position data per wallet
  - s = size (positive = long, negative = short)
  - e = entry price
  - l = leverage
  - M = margin
  - f = cumulative funding
- users_with_positions = set of wallets with open positions

Derived observations:
- Position disappearance (wallet exits users_with_positions)
- Position size changes over time
- Leverage distribution across wallets

---

LATENCY CHARACTERISTICS

**HYPOTHESIS (requires measurement):**
Node data may be available before public API data.

To validate:
- Compare node timestamp to public API timestamp for same event
- Measure over statistically significant sample
- Document actual latency advantage in milliseconds

Without measurement, do not assume latency advantage exists.

---

LIQUIDATION MECHANICS (FACTUAL)

How Hyperliquid liquidations work:
1. Position reaches liquidation price
2. Internal liquidation engine executes forced close
3. Position removed from users_with_positions
4. OI decreases by liquidated size

Observable after liquidation:
- Wallet disappears from users_with_positions
- OI drops without corresponding voluntary close
- Price impact from forced market order

Not directly observable:
- Liquidation in progress (only completion is visible)
- Which specific wallet was liquidated
- Liquidation queue order

---

WHAT THIS SYSTEM DOES NOT DO

This system does not:
- Exploit protocol vulnerabilities
- Manipulate oracles
- Attack consensus
- Front-run in illegal ways

This system only:
- Observes publicly available on-chain state
- Acts on observations according to defined rules

---

ENGINEERING CONSTRAINTS

Performance requirements:
- Data ingestion must not block
- State updates must be atomic
- Memory usage must be bounded
- Failures must halt, not degrade

Common failure modes:
- Missed data (network issues)
- State corruption (partial updates)
- Memory exhaustion (unbounded buffers)
- Timing errors (clock skew)

See HLP16 for failure handling specification.
