# Component Activation Decisions

**Date:** 2026-02-01
**Purpose:** Truthful decisions about which components are valid, blocked, or source-specific

---

## DECISION CATEGORIES

| Category | Definition |
|----------|------------|
| **HL-native** | Works only with HL data; Binance irrelevant |
| **Binance-only** | Requires Binance; HL cannot provide needed data |
| **Multi-source** | Explicitly uses both with asymmetric roles |
| **Dormant** | Must remain inactive until new data exists |

---

## 1. VWAP CALCULATOR

**Decision: Binance-only**

| Aspect | Status |
|--------|--------|
| Data requirement | Trade price + volume |
| HL capability | Does not emit trades |
| Binance capability | Fully provides aggTrade stream |
| Current state | Active when Binance connected |

**Rationale:** VWAP requires volume-weighted price accumulation from individual trades. HL node provides oracle prices without associated trade volume. This is architecturally impossible to change.

---

## 2. ATR CALCULATOR

**Decision: Binance-only**

| Aspect | Status |
|--------|--------|
| Data requirement | OHLC from trades |
| HL capability | Price only, no volume/direction |
| Binance capability | Full trade data, kline API for warm-up |
| Current state | Active with historical warm-up |

**Rationale:** True Range requires high/low from price movement with volume context. HL's block-level oracle prices lack intra-block volatility data. Binance REST API provides historical klines for warm-up.

---

## 3. ORDERFLOW IMBALANCE CALCULATOR

**Decision: Binance-only**

| Aspect | Status |
|--------|--------|
| Data requirement | Trade direction (is_buyer_maker) |
| HL capability | No trade direction data |
| Binance capability | Fully provides aggTrade with maker flag |
| Current state | Active when Binance connected |

**Rationale:** Orderflow requires knowing who initiated each trade (taker buy vs taker sell). HL node does not emit regular trades, only liquidations which have different semantics.

---

## 4. LIQUIDATION Z-SCORE CALCULATOR

**Decision: Multi-source (prefer HL)**

| Aspect | Status |
|--------|--------|
| Data requirement | Liquidation volume + timestamp |
| HL capability | Ground truth liquidations with full metadata |
| Binance capability | Exchange-reported liquidations |
| Current state | Can use either; HL preferred for accuracy |

**Source roles:**
- **HL (primary):** Protocol-native liquidations with wallet identity, method, exact timing
- **Binance (fallback):** Exchange-aggregated liquidations when HL unavailable

**Rationale:** Both provide liquidation volume sufficient for Z-score. HL is preferred because it's the protocol source of truth. Binance may aggregate or delay liquidation reports.

---

## 5. REGIME CLASSIFIER

**Decision: Binance-required with HL price assist**

| Aspect | Status |
|--------|--------|
| Inputs required | VWAP, ATR, orderflow, liq_z |
| HL capability | Price + liq_z only (1/4) |
| Binance capability | All four metrics |
| Current state | Requires Binance for 3/4 metrics |

**Source roles:**
- **Binance (required):** VWAP, ATR, orderflow calculators
- **HL (assist):** Oracle price as primary price source, liquidation z-score
- **Combined:** Price from HL, calculators from Binance

**Rationale:** The regime classifier was designed around Binance data semantics (trade volume, direction, aggregation). HL data is fundamentally different (protocol state, not market microstructure). Using HL price as the reference while Binance provides market regime indicators is the valid integration pattern.

---

## 6. CASCADE SNIPER - PROXIMITY

**Decision: HL-native**

| Aspect | Status |
|--------|--------|
| Data requirement | Position data (wallets, liquidation prices) |
| HL capability | Via PositionStateManager (abci_state) |
| Binance capability | Impossible (account-level privacy) |
| Current state | Requires HL PositionStateManager |

**Rationale:** Position proximity requires knowing which wallets have positions near liquidation. This is protocol-level data that only exists in HL's abci_state. Binance architecturally cannot provide this.

**Dependency:** Requires PositionStateManager to be active and parsing abci_state.rmp

---

## 7. CASCADE SNIPER - LIQUIDATION BURST

**Decision: Multi-source (prefer HL)**

| Aspect | Status |
|--------|--------|
| Data requirement | Liquidation events with side/volume |
| HL capability | Full metadata (wallet, method, side) |
| Binance capability | Basic events (price, size, order side) |
| Current state | Can use either |

**Source roles:**
- **HL (preferred):** Direct position side, wallet identity for cascade tracking
- **Binance (fallback):** Inferred side from order direction

**Rationale:** Cascade detection benefits from knowing which wallets are being liquidated (to track cascade propagation). HL provides this; Binance cannot.

---

## 8. CASCADE SNIPER - ABSORPTION

**Decision: Binance-only**

| Aspect | Status |
|--------|--------|
| Data requirement | Order book depth, trade flow |
| HL capability | No order book data |
| Binance capability | Full L2 depth + trade flow |
| Current state | Requires Binance depth stream |

**Rationale:** Absorption analysis requires order book depth to compare against liquidation volume. HL node does not provide order book data.

---

## SUMMARY TABLE

| Component | Decision | Active When |
|-----------|----------|-------------|
| VWAP | Binance-only | Binance WS connected |
| ATR | Binance-only | Binance WS + warm-up complete |
| Orderflow | Binance-only | Binance WS connected |
| Liq Z-Score | Multi-source | HL or Binance connected |
| Regime Classifier | Binance-required | All 4 calculators ready |
| Proximity | HL-native | PSM parsing abci_state |
| Liq Burst | Multi-source | HL or Binance connected |
| Absorption | Binance-only | Binance depth stream |

---

## DORMANT COMPONENTS

| Component | Reason | Required Data |
|-----------|--------|---------------|
| None identified | - | - |

All components have valid data paths. The question is not "dormant" but "which source."

---

## BLOCKING CONDITIONS

| Component | Blocked When |
|-----------|--------------|
| VWAP | Binance WS disconnected |
| ATR | Binance WS disconnected OR warm-up incomplete |
| Orderflow | Binance WS disconnected |
| Regime | Any of (VWAP, ATR, Orderflow) blocked |
| Proximity | PSM not initialized OR abci_state unavailable |
| Absorption | Binance depth stream disconnected |

---

*These decisions reflect architectural reality, not preferences.*
