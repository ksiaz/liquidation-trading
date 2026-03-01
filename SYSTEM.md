# Liquidation Trading System

Last updated: 2026-03-01

## Overview

Paper-trading system that detects liquidation cascades on Hyperliquid perpetual futures and enters counter-trend (fade) positions at exhaustion points. Runs 24/7 as a systemd service. No real orders placed — all execution is ghost-simulated against live L2 orderbooks.

**Exchange**: Hyperliquid (exclusively — no Binance)
**Symbols**: 20 perps (BTC, ETH, SOL, kPEPE, DOGE, AVAX, LINK, HYPE, PENDLE, NEAR, LTC, ADA, AAVE, APT, SEI, BNB, INJ, FARTCOIN, WLD, TON)
**Database**: PostgreSQL (`liquidation_trading` on localhost)
**Account**: Ghost account starting at $1,000, 5% position sizing

---

## Architecture

```
┌─────────────────┐     gRPC      ┌──────────────┐     node files     ┌──────────┐
│  CollectorService│◄────────────► │  hl-adapter   │◄──────────────────│  HL Node  │
│  (service.py)    │    :50051     │  (server.py)  │  fills, prices    │  (visor)  │
└────────┬─────────┘              └──────────────┘                    └──────────┘
         │
         │ asyncio regime loop (200ms/cycle, 20 symbols)
         │
    ┌────┴─────────────────────────────────────────────────┐
    │                                                       │
    ▼                                                       ▼
┌──────────────┐                                    ┌──────────────────┐
│ HyperliquidWS │  allMids, l2Book, trades,         │  Strategy Engine  │
│ (client.py)   │  activeAssetCtx, webData2         │  (cascade_sniper) │
│ + overflow WS │  wss://api.hyperliquid.xyz/ws     │                  │
└──────────────┘                                    └────────┬─────────┘
                                                             │
                                                             ▼
                                                    ┌──────────────────┐
                                                    │  Ghost Tracker    │
                                                    │  (ghost_tracker)  │
                                                    │  → PostgreSQL     │
                                                    └──────────────────┘
```

---

## Data Feeds

### 1. HL Node (gRPC, primary)

| Stream | Source Files | Data | Coverage |
|--------|-------------|------|----------|
| `StreamPrices` | `~/hl/data/replica_cmds/` | Oracle + mark prices | All ~43 perps |
| `StreamFills` | `~/hl/data/node_fills/hourly/` | Taker fills + liquidation metadata | All HL symbols |

Fills drive: liq z-score, burst aggregator, orderflow, VWAP, ATR, capitulation tracker.
Liquidations derived from fills (`is_liquidation` metadata), not a separate reader.

### 2. HL WebSocket (main WS)

| Channel | Data | Coverage |
|---------|------|----------|
| `allMids` | Real-time mid prices | All ~43 coins |
| `trades` | Taker fills | 7 coins (BTC, ETH, SOL, DOGE, XRP, NOT, HYPE) |
| `activeAssetCtx` | OI, funding, volume | 10 majors |
| `l2Book` | L2 orderbook (20 levels) | 10 primary coins |
| `webData2` | Wallet positions | 10 tracked wallets (WS limit) |

### 3. HL WebSocket (L2 overflow)

| Channel | Data | Coverage |
|---------|------|----------|
| `l2Book` | L2 orderbook (20 levels) | 10 overflow coins |

Separate connection — HL caps ~10 l2Book per WS.

**L2 primary**: BTC, ETH, SOL, kPEPE, DOGE, HYPE, ADA, LINK, AVAX, LTC
**L2 overflow**: NEAR, FARTCOIN, AAVE, APT, SEI, BNB, INJ, PENDLE, WLD, TON

### 4. HL REST API

| Endpoint | When | Purpose |
|----------|------|---------|
| `candleSnapshot` | Startup | Seed ATR + VWAP (last 2.5h of 5m candles) |
| `allMids` | Startup | One-shot prices for PnL reconciliation |
| `clearinghouseState` | Polling (~5s) | Wallet positions beyond WS limit |
| `meta` | Ghost adapter init | `szDecimals` per asset for order validation |

### Key distinction

- **gRPC fills** (node) = **real** liquidation detection (burst aggregator, z-score, cascade sniper)
- **WS `activeAssetCtx`** (OI drops) = **proxy** signal for momentum tracker only

---

## Regime Classification

Per-symbol, computed every cycle (~200ms). Three states:

| State | Meaning | Trading |
|-------|---------|---------|
| `SIDEWAYS` | Range-bound, VWAP-contained, low volatility | SLBRS entries (disabled) |
| `EXPANSION` | Breakout, VWAP escape, high volatility + liqs | Cascade entries |
| `DISABLED` | Neither criteria met | No entries |

**Inputs**: VWAP distance, ATR ratio (5m/30m), orderflow imbalance, liq z-score.
**Hysteresis**: Relaxed hold thresholds prevent chatter (e.g., SIDEWAYS entry requires OF dev <0.32, hold allows <0.40).
**Low-fill neutralization**: OF treated as 0.5 when <15 fills in 60s window.
**Debounce**: 50 cycles (~10s) before transition.

---

## Strategy: Cascade Sniper (EP2)

### Cascade State Machine

`NONE` → `PRIMED` → `TRIGGERED` → `ABSORBING` → `EXHAUSTED`

Transitions driven by liquidation burst volume, proximity clustering, and absorption metrics.

### Entry Modes

| Mode | Signal Source | Status |
|------|-------------|--------|
| FAST_PIVOT | Running trade delta zero-cross | Active |
| STRUCTURAL | AbsorptionConfirmationTracker (2-15s) | Active |
| ORGANIC | OrganicFlowDetector (10s, buy ratio >0.70) | Active |
| ORDERBOOK | Static absorption ratio | Active (fallback) |
| ROLLING_FADE | 30s burst / 60m baseline ratio ≥10x | Active |
| EXHAUSTION_FADE | liq_z ≥2.5 override, immediate at TRIGGERED | Active |
| GEOMETRY | Frozen — 10% WR | Disabled |
| SLBRS | 26% WR, net negative PnL | Disabled |

### Entry Gates

1. **Gate A (Warmup)**: ≥15 fills, ≥3 liq events, ≥120s elapsed
2. **Gate B (Trend)**: ret_1m/ret_3m alignment (absorption override at 0.65)
3. **Gate C (Cascade confirmation)**: ≥2 bursts in 60s, 10s refractory
4. **liq_z ≥2.5 override**: Bypasses trend gate, EQ filter, Gate C refractory

### ROLLING_FADE Detection

30s burst window vs 60m baseline. Requirements:
- ≥5 events in burst window
- Burst rate ≥10x baseline rate
- 60% concentration in any 10s sub-window
- Declining exhaustion (second half < first half)
- Adaptive baseline minimum: 50x ratio→5, 20x→10, 10x→20 events

### Excluded Coins

`{XRP, SUI, TRX, ATOM, ARB, OP}` — cascade fading doesn't work on these (0-40% WR in backtests).

---

## Position Management

### Ghost Execution

Simulated against live HL L2 orderbook. `GhostExchangeAdapter` validates order constraints using HL meta API (`szDecimals`). No Binance dependencies.

### Trailing Stops

ATR-progressive two-phase:
- Entry: 2.5× ATR (wide)
- At 2% MFE: tightens to 2.0×
- At 4% MFE: tightens to 1.0×
- Adverse orderflow (<0.38): 0.6× multiplier
- Break-even: triggers at 0.8% profit, locks 0.2%
- Floor: 0.5% minimum distance

### DCA (Dollar Cost Averaging)

Cascade sniper only. Up to 2 adds at 15bp spacing, minimum 15s apart.
Requires ≥3 active liq events in 60s window (cascade quality gate).
Sizing: 25% / 37.5% / 37.5% of initial quantity.

### Gravity TP (Partial Take-Profit)

L2 orderbook gravity zones (persistent liquidity bands). 50% reduce at nearest qualifying zone (30-300bp from entry, gravity ≥10,000). Moves trailing stop to break-even after partial close. Recovers targets for positions surviving restarts.

---

## Infrastructure

### Services (systemd user units)

| Service | Command | Log |
|---------|---------|-----|
| `paper-trade.service` | `.venv-mcp/bin/python -u scripts/run_paper_trade.py` | `paper_trade.log` |
| `hl-adapter.service` | `cd hl-adapter && python -u server.py` | adapter log |

**Paper trade**: `Restart=always`, `RestartSec=10`. Always use `systemctl --user restart paper-trade` — never manual python.

### HL Node

- Managed by `~/hl/start-node.sh` (tmux session "hyperliquid")
- Health check: `bash ~/hl/check-node.sh` (converts UTC→CET, shows age)
- **Never** run raw hl-visor commands while running. **Never** delete `~/hl/hyperliquid_data/`.

### Database

PostgreSQL on localhost. Connection: `liqtrade@localhost:5432/liquidation_trading`.
Pool: min=2, max=10 connections. All writes through `PgBufferedResearchDatabase` (no application locks, MVCC).
Schema: 57 tables, 85 indexes, idempotent `ensure_schema()`.

Key tables: `ghost_positions`, `ghost_trades`, `market_snapshots`, `execution_cycles`, `primitive_values`, `regime_transitions`.

### Market State Snapshots

39-field `MarketSnapshot` per symbol. Triggers: PERIODIC (10s), ENTRY, EXIT, REGIME_CHANGE, CASCADE_TRANSITION, LIQ_SPIKE.
Ring buffer (300 entries/coin, ~60s) + PG persistence (48h periodic, 30d events).

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/run_paper_trade.py` | Entry point, symbol config, startup |
| `runtime/collector/service.py` | Mandate loop, regime classification, entry/exit logic, all callbacks |
| `external_policy/ep2_strategy_cascade_sniper.py` | Strategy logic, cascade state machine, entry modes |
| `runtime/hyperliquid/client.py` | WS connections, L2 subscriptions, message routing |
| `runtime/hyperliquid/collector.py` | Proximity tracking, cascade alerts, wallet polling |
| `runtime/node_client/bridge.py` | gRPC client for HL node adapter |
| `execution/ep4_ghost_tracker.py` | Position tracking, PnL, trade history |
| `execution/ep4_ghost_adapter.py` | Ghost order simulation against L2 book |
| `runtime/regime/classifier.py` | SIDEWAYS/EXPANSION/DISABLED classification |
| `runtime/liquidations/rolling_volume_tracker.py` | ROLLING_FADE burst detection |
| `runtime/liquidations/zscore.py` | Liquidation z-score calculator |
| `runtime/liquidations/burst_aggregator.py` | 10s sliding window burst aggregation |
| `runtime/liquidations/liquidity_map.py` | L2 gravity zones for TP targeting |
| `runtime/market_state/snapshot.py` | MarketSnapshot dataclass |
| `runtime/market_state/emitter.py` | Snapshot emission + persistence |
| `runtime/logging/pg_pool.py` | PostgreSQL connection pool |
| `runtime/logging/pg_schema.py` | Schema definition (57 tables) |
| `runtime/logging/pg_buffered_db.py` | Buffered write layer |
