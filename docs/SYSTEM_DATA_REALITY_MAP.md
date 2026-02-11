# System Data Reality Map

**Date:** 2026-02-01
**Purpose:** Canonical map of data flows reflecting actual source authority

---

## DATA SOURCE AUTHORITY

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                     │
├─────────────────────────────────┬───────────────────────────────────────┤
│       HYPERLIQUID NODE          │           BINANCE                      │
│       (Protocol-Native)         │           (Exchange-Surface)           │
├─────────────────────────────────┼───────────────────────────────────────┤
│ ✓ Oracle price (authoritative)  │ ✓ Trade price + volume                │
│ ✓ Liquidation (ground truth)    │ ✓ Trade direction (is_buyer_maker)    │
│ ✓ Wallet identity               │ ✓ Liquidation events                  │
│ ✓ Position side (LONG/SHORT)    │ ✓ Order book (20 levels)              │
│ ✓ Liquidation method            │ ✓ Mark price + funding                │
│ ✓ Block ordering                │ ✓ Best bid/ask                        │
├─────────────────────────────────┼───────────────────────────────────────┤
│ ✗ Trades (not emitted)          │ ✗ Wallet identity (private)           │
│ ✗ Order book (not available)    │ ✗ Position side (inferred only)       │
│ ✗ Volume (prices only)          │ ✗ Oracle price (internal)             │
│ ✗ Trade direction               │ ✗ Account state (private)             │
└─────────────────────────────────┴───────────────────────────────────────┘
```

---

## CALCULATOR DATA FLOW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CALCULATORS                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐                                                     │
│  │   BINANCE WS    │                                                     │
│  │   aggTrade      │────┬─────────────────────────────────────────────► │
│  │   forceOrder    │    │                                                │
│  │   depth20       │    │    ┌────────────────┐                         │
│  │   markPrice     │    ├───►│ VWAP Calculator │ [Binance-only]         │
│  └─────────────────┘    │    └────────────────┘                         │
│                         │                                                │
│                         │    ┌────────────────┐                         │
│                         ├───►│ ATR Calculator  │ [Binance-only]         │
│                         │    └────────────────┘                         │
│                         │                                                │
│                         │    ┌────────────────┐                         │
│                         ├───►│ Orderflow Calc  │ [Binance-only]         │
│                         │    └────────────────┘                         │
│                         │                                                │
│  ┌─────────────────┐    │    ┌────────────────┐                         │
│  │   HL NODE       │    └───►│ Liq Z-Score    │ [Multi-source]          │
│  │   gRPC Stream   │────────►│                │ ◄── HL preferred        │
│  │                 │         └────────────────┘                         │
│  │   HL_PRICE      │────────────────────────────────────────────────►   │
│  │   LIQUIDATION   │                                  Primary Price      │
│  └─────────────────┘                                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## REGIME CLASSIFICATION FLOW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    REGIME CLASSIFIER                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUTS (4 required):                                                    │
│                                                                          │
│    ┌────────────────┐                                                    │
│    │ VWAP distance  │◄────── Binance trades (REQUIRED)                  │
│    └────────────────┘                                                    │
│             │                                                            │
│    ┌────────────────┐                                                    │
│    │ ATR 5m / 30m   │◄────── Binance trades (REQUIRED)                  │
│    └────────────────┘                                                    │
│             │                                                            │
│    ┌────────────────┐                                                    │
│    │ Orderflow imb  │◄────── Binance trades (REQUIRED)                  │
│    └────────────────┘                                                    │
│             │                                                            │
│    ┌────────────────┐                                                    │
│    │ Liquidation Z  │◄────── HL or Binance (HL preferred)               │
│    └────────────────┘                                                    │
│             │                                                            │
│             ▼                                                            │
│    ┌────────────────┐                                                    │
│    │ classify_      │──────► SIDEWAYS_ACTIVE                            │
│    │ regime()       │──────► EXPANSION_ACTIVE                           │
│    │                │──────► DISABLED                                    │
│    └────────────────┘                                                    │
│                                                                          │
│  STATUS: Blocked unless Binance WS connected                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## CASCADE SNIPER FLOW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CASCADE SNIPER                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PROXIMITY DATA [HL-native]:                                            │
│    ┌─────────────────┐                                                   │
│    │ PositionState   │◄────── abci_state.rmp (HL ONLY)                  │
│    │ Manager (PSM)   │                                                   │
│    └────────┬────────┘                                                   │
│             │                                                            │
│             ▼                                                            │
│    ┌─────────────────┐                                                   │
│    │ ProximityData   │ positions_at_risk, value_at_risk                 │
│    │                 │ closest_liquidation, dominant_side               │
│    └────────┬────────┘                                                   │
│             │                                                            │
│  LIQUIDATION BURST [Multi-source]:                                      │
│    ┌─────────────────┐                                                   │
│    │ BurstAggregator │◄────── HL (preferred) OR Binance forceOrder      │
│    └────────┬────────┘                                                   │
│             │                                                            │
│  ABSORPTION [Binance-only]:                                             │
│    ┌─────────────────┐                                                   │
│    │ Depth Analysis  │◄────── Binance depth20 (REQUIRED)                │
│    └────────┬────────┘                                                   │
│             │                                                            │
│             ▼                                                            │
│    ┌─────────────────┐                                                   │
│    │ CascadeState    │──────► NONE → PRIMED → TRIGGERED → ABSORBING    │
│    │ Machine         │                                                   │
│    └─────────────────┘                                                   │
│                                                                          │
│  STATUS:                                                                 │
│    - Proximity: Blocked unless PSM active                               │
│    - Burst: Active with HL or Binance                                   │
│    - Absorption: Blocked unless Binance depth connected                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## COMPONENT STATUS LEGEND

| Status | Meaning |
|--------|---------|
| **LIVE** | Data flowing, component active |
| **BLOCKED** | Missing required data source |
| **DEGRADED** | Using fallback, not optimal |
| **INERT** | Component exists but cannot activate |

---

## CURRENT SYSTEM STATE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CURRENT STATE (2026-02-01)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  DATA SOURCES:                                                           │
│    [LIVE]    HL Node gRPC (prices + liquidations streaming)             │
│    [LIVE]    Binance WS (trades + depth + mark price)                   │
│                                                                          │
│  CALCULATORS:                                                            │
│    [LIVE]    VWAP (from Binance trades)                                 │
│    [LIVE]    ATR (from Binance trades, warm-up complete)                │
│    [LIVE]    Orderflow (from Binance trades)                            │
│    [LIVE]    Liq Z-Score (from HL liquidations)                         │
│                                                                          │
│  REGIME CLASSIFIER:                                                      │
│    [LIVE]    All 4 inputs available for Binance-format symbols          │
│    [BLOCKED] HL-format symbols (BTC) lack calculators                   │
│                                                                          │
│  CASCADE SNIPER:                                                         │
│    [BLOCKED] Proximity - PSM not parsing abci_state                     │
│    [LIVE]    Burst - receiving HL liquidations                          │
│    [BLOCKED] Absorption - needs investigation                           │
│                                                                          │
│  OBSERVED:                                                               │
│    "Regime transition: SOLUSDT SIDEWAYS_ACTIVE → DISABLED"              │
│    - Proves calculators ARE producing values                            │
│    - Proves regime IS making decisions                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## SYMBOL FORMAT ISSUE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SYMBOL FORMAT MISMATCH                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  HL Node emits:     BTC, ETH, SOL (no suffix)                           │
│  Binance emits:     BTCUSDT, ETHUSDT, SOLUSDT (with suffix)             │
│                                                                          │
│  Calculator storage: Keyed by Binance format (BTCUSDT)                  │
│  Regime iteration:   Includes both formats                              │
│                                                                          │
│  RESULT:                                                                 │
│    - BTCUSDT: Has calculators, regime works                             │
│    - BTC: No calculators, regime SKIPs                                  │
│                                                                          │
│  THIS IS CORRECT BEHAVIOR:                                              │
│    - HL-format symbols use HL price only                                │
│    - Binance-format symbols use full calculator suite                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## WHAT "NOT WIRED YET" vs "IMPOSSIBLE" MEANS

| Situation | Example | Status |
|-----------|---------|--------|
| **Not wired yet** | Binance WS disconnects temporarily | Reconnection fixes it |
| **Impossible by source** | HL providing trade direction | Architectural limit |
| **Intentionally inactive** | Proximity without PSM | Design decision |

---

## VALID INTEGRATION PATTERN

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CORRECT ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. PRICE AUTHORITY:    HL oracle_price (for liquidation distance)      │
│  2. MARKET REGIME:      Binance (VWAP, ATR, orderflow)                  │
│  3. LIQUIDATION Z:      HL (ground truth) OR Binance (fallback)         │
│  4. POSITION DATA:      HL only (via PSM)                               │
│  5. ORDER BOOK:         Binance only                                    │
│                                                                          │
│  These are DIFFERENT information types, not equivalent sources.         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*This map reflects observed reality. False equivalences have been removed.*
