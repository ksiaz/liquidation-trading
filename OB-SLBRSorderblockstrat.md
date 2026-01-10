# MARKET REGIME MASTERFRAME
## Dual-Strategy Behavioral Trading System

---

## 0. SYSTEM PURPOSE

This system trades **participant behavior**, not indicators.

It operates two **mutually exclusive strategies** governed by a **single regime classifier**:

1. **SLBRS** — Sideways Liquidity Block Reaction System  
   → exploits absorption, negotiation, and inventory rebalancing

2. **EFFCS** — Expansion & Forced Flow Continuation System  
   → exploits liquidation cascades, stop-runs, and forced participation

At any moment:
- **Only ONE strategy may be active**
- If regime is unclear → **NO TRADE**

---

## 1. REQUIRED DATA INPUTS

### Mandatory Streams
- L2 Orderbook (top 20 levels, 1s snapshots)
- Aggressive trades (buyer/seller initiated)
- Liquidation feed (forced flow)
- OHLCV klines:
  - 1-minute
  - 5-minute

### Derived Metrics
- Session-anchored VWAP
- ATR(1m), ATR(5m), ATR(30m)
- Rolling taker buy/sell volume (10s, 30s)
- Liquidation Z-score (60m baseline)
- Open Interest delta (if available)

---

## 2. GLOBAL ARCHITECTURE

### Master State Machine

DISABLED
SIDEWAYS_ACTIVE
EXPANSION_ACTIVE
COOLDOWN


### Mutual Exclusion Rule (HARD)

IF SIDEWAYS_ACTIVE → EXPANSION_DISABLED
IF EXPANSION_ACTIVE → SIDEWAYS_DISABLED


If neither regime is valid → **DISABLED**

---

## 3. REGIME CLASSIFIER (CORE GATE)

### 3.1 SIDEWAYS REGIME (SLBRS ENABLED)

ALL conditions must be TRUE:

#### VWAP Containment

abs(price − VWAP) ≤ 1.25 × ATR(5m)


#### Volatility Compression

ATR(5m) / ATR(30m) < 0.80


#### Orderflow Balance

abs(taker_buy_30s − taker_sell_30s) / total_volume_30s < 0.18


#### No Forced Flow

liquidation_zscore < 2.0


→ `state = SIDEWAYS_ACTIVE`

---

### 3.2 EXPANSION REGIME (EFFCS ENABLED)

ALL conditions must be TRUE:

#### VWAP Escape

abs(price − VWAP) ≥ 1.5 × ATR(5m)


#### Volatility Expansion

ATR(5m) / ATR(30m) ≥ 1.0


#### Orderflow Dominance

abs(taker_buy_30s − taker_sell_30s) / total_volume_30s ≥ 0.35


#### Forced Participation
At least ONE must be TRUE:

liquidation_zscore ≥ 2.5
OR
open_interest decreases during price expansion


→ `state = EXPANSION_ACTIVE`

---

### 3.3 TRANSITION / UNCLEAR

If neither regime qualifies → state = DISABLED


---

## 4. ORDERBOOK NORMALIZATION (SHARED)

### Price Zoning (Relative to Mid)
| Zone | Distance |
|----|---------|
| Zone A | 0–5 bps |
| Zone B | 5–15 bps |
| Zone C | 15–30 bps |

Zone A & B only are actionable.

---

## 5. STRATEGY A — SLBRS
### Sideways Liquidity Block Reaction System

---

### A1. Liquidity Block Detection

Block exists if ALL are true:

zone_liquidity ≥ 2.5 × rolling_zone_avg
AND persistence ≥ 30s
AND executed_volume > 0
AND cancel_to_trade_ratio < 3.5


Block classification:

ABSORPTION → tradable
CONSUMPTION → ignore
SPOOF → ignore


---

### A2. SLBRS State Machine

SETUP_DETECTED
FIRST_TEST
RETEST_ARMED
IN_POSITION


---

### A3. FIRST TEST (INFORMATION PASS)

Conditions:

price enters block
AND aggressive volume increases
AND price does NOT accept through


Acceptance definition:

price beyond block > 10s
AND aggressive volume continues


Rejection displacement:

abs(price − block_edge) ≥ max(8 bps, 0.25 × ATR(1m))


---

### A4. RETEST ENTRY (ONLY ENTRY)

price_distance_to_block ≤ 30% of block width
AND aggressive_volume < first_test_volume × 0.70
AND price_impact < first_test_price_impact
AND absorption_ratio ≥ 0.65


→ Enter trade

---

### A5. SLBRS RISK

Stop:

block_edge ± max(6 bps, 0.30 × ATR(1m))


Target:

next opposing liquidity block
OR VWAP


Constraint:

R:R ≥ 1.5


---

### A6. SLBRS INVALIDATION

Exit immediately if:

volatility expands
OR orderflow becomes one-sided
OR price accepts through block


---

## 6. STRATEGY B — EFFCS
### Expansion & Forced Flow Continuation System

---

### B1. Core Edge

Exploit:
- Liquidation cascades
- Stop-run continuation
- Liquidity void traversal
- Late participant chasing

Never fade price.

---

### B2. Orderbook Role (Fragility Only)

Required:

price_impact high
AND near-touch liquidity thin
AND replenishment slow


If liquidity refills → no trade.

---

### B3. ENTRY LOGIC

#### Impulse Detection

price displacement ≥ 0.5 × ATR(5m)
AND liquidation spike OR OI contraction


#### Pullback Filter

retracement ≤ 30% of impulse
AND volume decreases


→ Enter continuation

---

### B4. EFFCS RISK

Stop:

below/above pullback low/high
OR 0.5 × ATR(5m)


Target:

liquidity void exhaustion
OR 2.5–4.0 × risk


---

### B5. EFFCS EXIT

Exit if:

liquidations stop accelerating
OR orderbook replenishes
OR volatility contracts


---

## 7. COOLDOWN & FAIL-SAFES

Cooldown:

5 minutes after any exit


Hard Kill:

≥ 2 consecutive losses
OR daily drawdown ≥ MAX_DD


Structural Failure:

winrate last 20 < 35%


---

## 8. LOGGING (MANDATORY)

Per trade:

timestamp
regime_state
strategy_id (SLBRS / EFFCS)
block_zone
block_type
entry_price
stop_price
target_price
MAE
MFE
exit_reason


---

## 9. FINAL INVARIANTS

- One regime at a time
- One strategy at a time
- No trades during transitions
- No discretionary overrides
- No exceptions

---

## 10. EXPECTED BEHAVIOR

| Market Condition | System Response |
|-----------------|----------------|
| Range / Chop | SLBRS active |
| Trend / Cascade | EFFCS active |
| Unclear / News | No trade |

---

## END OF MASTERFRAME