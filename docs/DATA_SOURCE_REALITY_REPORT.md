# Data Source Reality Report

**Date:** 2026-02-01
**Purpose:** Document what each data source ACTUALLY provides (not assumptions)

---

## 1. HYPERLIQUID NODE (Protocol-Native)

### Event Types Emitted

| Event | Frequency | Source |
|-------|-----------|--------|
| HL_PRICE | Every block (~500ms) | SetGlobalAction in replica_cmds |
| LIQUIDATION | Per fill | node_fills directory |
| SYNC_STATUS | Periodic | Adapter internal |

### HL_PRICE Fields (Observed)

| Field | Type | Semantic Meaning |
|-------|------|------------------|
| `symbol` | string | Asset name (BTC, ETH, SOL) |
| `oracle_price` | float | **Authoritative liquidation trigger price** |
| `mark_price` | float | Mark price for PnL |
| `block_height` | uint64 | Deterministic ordering |
| `timestamp_ns` | int64 | Block consensus time |

### LIQUIDATION Fields (Observed)

| Field | Type | Semantic Meaning |
|-------|------|------------------|
| `symbol` | string | Asset being liquidated |
| `side` | string | **Position side: LONG or SHORT** (unambiguous) |
| `price` | float | Execution price |
| `size` | float | Amount liquidated |
| `liquidated_wallet` | string | **Wallet that was liquidated** |
| `liquidator_wallet` | string | **Wallet that took the fill** |
| `method` | string | **"market" or "backstop"** (execution path) |
| `fill_id` | uint64 | Idempotent deduplication |
| `tx_hash` | string | Blockchain transaction reference |

### What HL Provides That Binance Cannot

| Capability | HL | Binance |
|------------|-------|---------|
| Wallet identity | Yes | No |
| Position side (LONG/SHORT) | Direct | Inferred from order side |
| Liquidation method | Yes (market/backstop) | No |
| Oracle price (trigger) | Yes | No |
| Fill deduplication | fill_id | None |
| Transaction proof | tx_hash | None |
| Block ordering | block_height | Timestamp only |

---

## 2. BINANCE WEBSOCKET (Exchange-Surface)

### Stream Types Subscribed

| Stream | Frequency | Purpose |
|--------|-----------|---------|
| `@aggTrade` | Per trade | Volume, price, direction |
| `@forceOrder` | Per liquidation | Liquidation events |
| `@bookTicker` | Event-driven | Best bid/ask |
| `@depth20@100ms` | 100ms | Order book depth |
| `@markPrice@1s` | 1 second | Official mark price |

### aggTrade Fields (Observed)

| Field | Type | Semantic Meaning |
|-------|------|------------------|
| `p` | float | Trade price |
| `q` | float | Trade volume |
| `m` | bool | is_buyer_maker (taker side inference) |
| `E` | int | Event timestamp (ms) |

### forceOrder Fields (Observed)

| Field | Type | Semantic Meaning |
|-------|------|------------------|
| `s` | string | Symbol (BTCUSDT) |
| `S` | string | Order side (BUY/SELL) - NOT position side |
| `p` | float | Liquidation price |
| `q` | float | Liquidation size |
| `E` | int | Event timestamp (ms) |

### What Binance Will NEVER Provide

| Gap | Why |
|-----|-----|
| Wallet identity | Privacy protection |
| Position side | Only order side exposed |
| Liquidation method | Internal execution detail |
| Oracle price | Exchange internal |
| Margin ratio | Account-level state |
| Entry price | Account-level state |
| Leverage used | Account-level state |

---

## 3. KEY SEMANTIC DIFFERENCES

### Liquidation Side Semantics

**HL Node:**
- `side="LONG"` means a LONG position was liquidated (forced SELL)
- `side="SHORT"` means a SHORT position was liquidated (forced BUY)
- **Unambiguous position context**

**Binance:**
- `S="SELL"` means the liquidation order sold (could be long liquidation)
- `S="BUY"` means the liquidation order bought (could be short liquidation)
- **Requires inference: SELL → long liquidation, BUY → short liquidation**

### Price Authority

**HL Node:**
- `oracle_price` is THE price that triggers liquidations
- Protocol-native, deterministic

**Binance:**
- `mark_price` is Binance's calculated price
- Not the actual liquidation trigger (that's internal)

### Identity

**HL Node:**
- Both sides of liquidation known (liquidated + liquidator)
- Can track whale liquidations, repeat victims, liquidator strategies

**Binance:**
- Anonymous - "a liquidation happened" with no identity
- All liquidations attributed to "the market"

---

## 4. DATA COMPLETENESS MATRIX

| Data Type | HL Node | Binance |
|-----------|---------|---------|
| Trade prices | Via oracle | Yes |
| Trade volume | No | Yes |
| Trade direction | No | Yes (is_buyer_maker) |
| Liquidation events | Yes | Yes |
| Liquidation identity | Yes | No |
| Liquidation method | Yes | No |
| Order book | No | Yes (20 levels) |
| Mark price | Yes | Yes |
| Oracle price | Yes | No |
| Funding rate | No | Yes |
| Historical data | Forward only | Forward only |

---

*This document reflects observed reality, not theoretical capabilities.*
