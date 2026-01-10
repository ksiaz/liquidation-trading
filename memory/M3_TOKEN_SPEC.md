# M3 Evidence Token Specification

## Complete Token Set

| Token | Trigger Condition (Factual) | Source | Notes |
|:------|:---------------------------|:-------|:------|
| **OB_APPEAR** | Orderbook level appears within node's price band | Orderbook | Level was not present, now is present |
| **OB_PERSIST** | Orderbook level remains present for ≥N seconds | Orderbook | Level existed at t-N and still exists at t |
| **OB_VANISH** | Orderbook level disappears from node's price band | Orderbook | Level was present, now is not present |
| **TRADE_EXEC** | Trade executed at node's price | Trade | Any trade execution within price band |
| **TRADE_VOLUME_HIGH** | Trade volume exceeds threshold | Trade | Single trade volume > configured threshold |
| **LIQ_OCCUR** | Liquidation occurred within proximity | Liquidation | Liquidation within configured bps of node |
| **LIQ_CASCADE** | Multiple liquidations within short time window | Liquidation | ≥N liquidations within T seconds |
| **PRICE_TOUCH** | Price enters node's price band | Price | Price moved into band from outside |
| **PRICE_EXIT** | Price leaves node's price band | Price | Price moved out of band |
| **PRICE_DWELL** | Price remains in band for ≥N seconds | Price | Price stayed within band continuously |

---

## Token Definitions (Detailed)

### Orderbook Tokens

**OB_APPEAR**
- **Trigger:** L2 orderbook data shows liquidity appeared at price level within node's band
- **Factual condition:** `orderbook[price_level] exists AND orderbook_previous[price_level] did not exist`
- **NOT interpretive:** Does not imply "support building" or "buyers entering"

**OB_PERSIST**
- **Trigger:** L2 orderbook data shows liquidity remained present for threshold duration
- **Factual condition:** `orderbook[price_level] exists continuously for ≥persistence_seconds`
- **NOT interpretive:** Does not imply "strong level" or "absorption"

**OB_VANISH**
- **Trigger:** L2 orderbook data shows liquidity disappeared from price level
- **Factual condition:** `orderbook[price_level] existed AND orderbook_current[price_level] does not exist`
- **NOT interpretive:** Does not imply "broken" or "swept"

### Trade Tokens

**TRADE_EXEC**
- **Trigger:** Trade executed at price within node's band
- **Factual condition:** `trade.price within [node.price_center - band, node.price_center + band]`
- **NOT interpretive:** Does not imply direction or aggression

**TRADE_VOLUME_HIGH**
- **Trigger:** Single trade volume exceeds configured threshold (e.g., $50k)
- **Factual condition:** `trade.price * trade.quantity > volume_threshold`
- **NOT interpretive:** Does not imply "important" or "institutional"

### Liquidation Tokens

**LIQ_OCCUR**
- **Trigger:** Liquidation event occurred within proximity to node price
- **Factual condition:** `abs(liquidation.price - node.price_center) / current_price < proximity_bps`
- **NOT interpretive:** Does not imply "stop hunt" or "cascade trigger"

**LIQ_CASCADE**
- **Trigger:** Multiple liquidations (≥N) occurred within short time window (≤T seconds)
- **Factual condition:** `count(liquidations within [t-T, t]) >= cascade_threshold`
- **NOT interpretive:** Does not imply "forced selling" or "panic"

### Price Tokens

**PRICE_TOUCH**
- **Trigger:** Market price moved into node's price band from outside
- **Factual condition:** `price_previous outside band AND price_current inside band`
- **NOT interpretive:** Does not imply "test" or "probe"

**PRICE_EXIT**
- **Trigger:** Market price moved out of node's price band
- **Factual condition:** `price_previous inside band AND price_current outside band`
- **NOT interpretive:** Does not imply "rejection" or "breakthrough"

**PRICE_DWELL**
- **Trigger:** Market price remained within node's band for threshold duration
- **Factual condition:** `price stayed within band continuously for ≥dwell_seconds`
- **NOT interpretive:** Does not imply "consolidation" or "accumulation"

---

## Rejected Token Candidates

The following tokens were **intentionally excluded** because they introduce interpretation:

| Rejected Token | Reason for Rejection |
|:---------------|:--------------------|
| ~~TRADE_BUY~~ | Implies directional bias (buyer aggression) |
| ~~TRADE_SELL~~ | Implies directional bias (seller aggression) |
| ~~LIQ_LONG~~ | Implies directional bias (forced long exit) |
| ~~LIQ_SHORT~~ | Implies directional bias (forced short exit) |
| ~~REJECT_UP~~ | Implies outcome (price was rejected upward) |
| ~~REJECT_DOWN~~ | Implies outcome (price was rejected downward) |
| ~~BREAKOUT~~ | Implies interpretation (price broke through) |
| ~~DEFEND~~ | Implies intentionality (level was defended) |
| ~~ABSORPTION~~ | Implies interpretation (orders absorbed volume) |
| ~~SWEEP~~ | Implies aggressive action (liquidity swept) |

**Why rejected:**
- These tokens encode **semantic meaning** rather than **factual events**
- They suggest **outcomes** rather than **observations**
- They imply **directionality** or **bias**

---

## Why This Token Set Is Closed

### 1. Completeness

This token set covers **all observable evidence types** in the current M2 system:
- Orderbook state changes (appear, persist, vanish)
- Trade execution events (exec, high volume)
- Liquidation events (occur, cascade)
- Price movement relative to node (touch, exit, dwell)

**No additional evidence types exist** in the data pipeline that aren't captured.

### 2. Atomicity

Each token represents a **single, indivisible event**:
- Not compound: No token combines multiple observations
- Not derived: No token is computed from other tokens
- Not temporal: No token requires sequence context (that's what motifs are for)

### 3. Mutual Exclusivity

Tokens can occur **simultaneously** but never **conflict**:
- `TRADE_EXEC` and `TRADE_VOLUME_HIGH` can both fire for the same trade
- `OB_APPEAR` and `PRICE_TOUCH` can both fire in the same update
- No token negates or contradicts another

### 4. Observation-Only Boundary

Every token is **purely observational**:
- Trigger conditions are factual comparisons (existence, threshold, duration)
- No token requires interpretation of intent
- No token predicts future events
- No token suggests actions

### 5. Neutrality Principle

Every token is **semantically neutral**:
- No directional implication (up/down, bullish/bearish)
- No outcome implication (success/failure, strong/weak)
- No action implication (defend/attack, absorb/sweep)

**Examples of neutrality:**
- `OB_VANISH` not ~~`OB_BROKEN`~~ (broken implies failure)
- `TRADE_EXEC` not ~~`TRADE_BUY`~~ (buy implies direction)
- `LIQ_OCCUR` not ~~`STOP_HUNT`~~ (hunt implies intentionality)

### 6. Bounded Scope

This token set is **intentionally limited** to:
- Events **observable in real-time data**
- Events **verifiable from historical data**
- Events **deterministically detectable**

**Excluded from scope:**
- Market microstructure (spoofing, layering) - requires interpretation
- Order flow toxicity - requires statistical modeling
- Participant intent - not observable
- Future outcomes - not factual

---

## Token Set Closure Proof

**Closure condition:** No new evidence type can be added without either:
1. Being a **subset** of existing tokens (redundant)
2. Being a **combination** of existing tokens (use motifs instead)
3. Introducing **interpretation** (prohibited)

**Proof by exhaustion:**

**Orderbook domain:**
- State: appear, persist, vanish ✓
- All possible orderbook state transitions covered

**Trade domain:**
- Occurrence: execution ✓
- Magnitude: high volume ✓
- All factual trade properties covered

**Liquidation domain:**
- Single event: occur ✓
- Multiple events: cascade ✓
- All liquidation patterns covered

**Price domain:**
- Entry: touch ✓
- Exit: exit ✓
- Persistence: dwell ✓
- All price-node relationships covered

**Therefore:** Token set is complete and closed.

---

## Configuration Parameters (Factual Thresholds)

These thresholds define token triggers but do **NOT** imply importance:

| Parameter | Default | Purpose |
|:----------|:--------|:--------|
| `persistence_seconds` | 30 | OB_PERSIST trigger threshold |
| `volume_threshold_usd` | 50000 | TRADE_VOLUME_HIGH trigger threshold |
| `proximity_bps` | 10 | LIQ_OCCUR proximity threshold |
| `cascade_count` | 3 | LIQ_CASCADE minimum liquidations |
| `cascade_window_sec` | 5 | LIQ_CASCADE time window |
| `dwell_seconds` | 60 | PRICE_DWELL trigger threshold |

**Critical:** These are **detection thresholds**, NOT **importance scores**.

---

## Summary

**Total tokens:** 10  
**Orderbook:** 3 (appear, persist, vanish)  
**Trade:** 2 (exec, volume_high)  
**Liquidation:** 2 (occur, cascade)  
**Price:** 3 (touch, exit, dwell)

**Guarantee:** This set is:
- ✅ Complete (covers all observable evidence)
- ✅ Closed (no additions possible without violating principles)
- ✅ Atomic (single events only)
- ✅ Neutral (no interpretation)
- ✅ Observational (factual triggers only)

**Awaiting PASS to proceed.**
