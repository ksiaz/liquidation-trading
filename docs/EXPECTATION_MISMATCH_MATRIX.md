# Expectation Mismatch Matrix

**Date:** 2026-02-01
**Purpose:** Compare system beliefs against data source reality

---

## LEGEND

- **Fully satisfied** = Source provides exactly what system expects
- **Partially satisfied** = Source provides related but not equivalent data
- **Impossible** = Source architecturally cannot provide this
- **N/A** = Not applicable to this source

---

## 1. VWAP CALCULATOR

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| Trade price events | N/A (no trades) | **Fully satisfied** |
| Trade volume | N/A | **Fully satisfied** |
| Trade timestamp | N/A | **Fully satisfied** |
| Continuous trade stream | N/A | **Fully satisfied** |

**Verdict:** VWAP is **Binance-only**. HL does not emit trade events.

---

## 2. ATR CALCULATOR

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| OHLC candles (5m, 30m) | N/A | **Fully satisfied** (from trades) |
| Historical klines for warm-up | N/A | **Fully satisfied** (REST API) |
| Trade-to-candle aggregation | N/A | **Fully satisfied** |

**Verdict:** ATR is **Binance-only**. HL provides prices but not trade volume for true range.

---

## 3. ORDERFLOW IMBALANCE CALCULATOR

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| Trade direction (is_buyer_maker) | N/A | **Fully satisfied** |
| Trade volume | N/A | **Fully satisfied** |
| Continuous trade stream | N/A | **Fully satisfied** |

**Verdict:** Orderflow is **Binance-only**. HL has no trade direction data.

---

## 4. LIQUIDATION Z-SCORE CALCULATOR

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| Liquidation quantity | **Fully satisfied** | **Fully satisfied** |
| Liquidation timestamp | **Fully satisfied** | **Fully satisfied** |
| Continuous liquidation stream | **Fully satisfied** | **Fully satisfied** |

**Verdict:** Z-Score can use **either source**. Both provide liquidation volume.

**Semantic difference:**
- HL: Protocol-native liquidations (ground truth)
- Binance: Exchange-reported liquidations (may differ in timing/aggregation)

---

## 5. REGIME CLASSIFIER

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| VWAP distance | **Impossible** | **Fully satisfied** |
| ATR 5m/30m | **Impossible** | **Fully satisfied** |
| Orderflow imbalance | **Impossible** | **Fully satisfied** |
| Liquidation Z-score | **Fully satisfied** | **Fully satisfied** |
| Current price | **Fully satisfied** (oracle) | **Fully satisfied** (mark) |

**Verdict:** Regime classifier **requires Binance** for 3 of 4 metrics. HL provides only price and liquidation z-score.

---

## 6. CASCADE SNIPER (PROXIMITY DATA)

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| Positions at risk (count) | **Partially satisfied** (via PSM) | **Impossible** |
| Position value at risk | **Partially satisfied** (via PSM) | **Impossible** |
| Closest liquidation price | **Partially satisfied** (via PSM) | **Impossible** |
| Wallet identity | **Fully satisfied** | **Impossible** |
| Position side (LONG/SHORT) | **Fully satisfied** | **Impossible** |

**Verdict:** Proximity data is **HL-only**. Binance cannot provide account-level position data.

---

## 7. CASCADE SNIPER (LIQUIDATION BURST)

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| Liquidation volume | **Fully satisfied** | **Fully satisfied** |
| Side (long/short) | **Fully satisfied** (direct) | **Partially satisfied** (inferred) |
| Event count | **Fully satisfied** | **Fully satisfied** |
| Wallet identity | **Fully satisfied** | **Impossible** |

**Verdict:** Liquidation burst can use **either source**, but HL provides richer data.

---

## 8. CASCADE SNIPER (ABSORPTION)

| System Expectation | HL Node | Binance |
|-------------------|---------|---------|
| Order book depth | **Impossible** | **Fully satisfied** |
| Organic flow detection | **Impossible** (no trades) | **Fully satisfied** |

**Verdict:** Absorption analysis is **Binance-only**. HL has no order book.

---

## SUMMARY MATRIX

| Component | HL Node | Binance | Verdict |
|-----------|---------|---------|---------|
| VWAP | Impossible | Fully | **Binance-only** |
| ATR | Impossible | Fully | **Binance-only** |
| Orderflow | Impossible | Fully | **Binance-only** |
| Liq Z-Score | Fully | Fully | **Either** (prefer HL) |
| Regime Classifier | Partial (1/4) | Fully (4/4) | **Binance-required** |
| Proximity Data | Partial | Impossible | **HL-only** |
| Liquidation Burst | Fully | Partial | **Either** (prefer HL) |
| Absorption | Impossible | Fully | **Binance-only** |

---

## INVALID EXPECTATIONS IDENTIFIED

1. **"HL can replace Binance for regime classification"** - FALSE
   - HL provides only price and liquidation data
   - VWAP, ATR, orderflow require trade volume/direction from Binance

2. **"Binance can provide position proximity"** - FALSE
   - Position-level data is account-private
   - Only HL node (via abci_state) has this

3. **"Sources are interchangeable"** - FALSE
   - They provide fundamentally different information types
   - Protocol-native vs exchange-surface data

4. **"Liquidation Z-score semantics are identical"** - PARTIALLY FALSE
   - Both provide liquidation volume
   - But HL is protocol ground truth, Binance is exchange-reported
   - Timing and aggregation may differ

---

*This matrix documents reality, not aspirations.*
