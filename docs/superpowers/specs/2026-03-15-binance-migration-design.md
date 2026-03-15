# Binance Data Layer Migration

## Goal
Replace Hyperliquid node + adapter + WS data layer with Binance Futures WebSocket streams. Keep all trading logic unchanged.

## Why
- HL has insufficient liquidity — altcoin cascades produce zero liquidation events on HL
- HL node lag causes periodic data blackouts (1h+ gaps observed)
- Wallet transparency (HL's advantage) is not used operationally
- Binance has 100x more fills, native liquidation stream, deeper L2 books

## Architecture

```
Before:  HL Node files → hl-adapter (gRPC:50051) → NodeBridge → service.py
         HL WS (allMids, l2Book)                  → HyperliquidClient → service.py

After:   Binance WS (combined streams) → BinanceDataProvider → service.py
```

Single new file: `runtime/binance/data_provider.py`

## Binance WS Connections

Two connections, 42 streams total (limit: 1024/connection):

**Connection 1 — Trades + Liquidations (21 streams):**
- `!forceOrder@arr` (all liquidations, 1/sec/symbol)
- 20× `<symbol>@aggTrade` (taker fills, 100ms aggregation)

**Connection 2 — Orderbook + Prices (21 streams):**
- 20× `<symbol>@depth20@100ms` (top 20 L2 levels)
- `!markPrice@arr@1s` (mark prices for all symbols)

Base URL: `wss://fstream.binance.com/stream?streams=<stream1>/<stream2>/...`

## Coin List (Top 20 by sustained volume)

```python
BINANCE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "BNBUSDT", "TRUMPUSDT", "TAOUSDT", "SUIUSDT", "ADAUSDT",
    "LINKUSDT", "AVAXUSDT", "PEPEUSDT", "LTCUSDT", "DOTUSDT",
    "APTUSDT", "NEARUSDT", "AAVEUSDT", "HYPEUSDT", "ZECUSDT",
]
```

## Callback Mapping

| Binance Stream | Transform | Existing Callback |
|---|---|---|
| `aggTrade` | m=true→side="A", m=false→side="B" | `_handle_hl_fill(symbol, side, price, size, ts)` |
| `forceOrder` | S="SELL"→"LONG", S="BUY"→"SHORT" | `_handle_hl_liquidation(symbol, side, price, size, ts)` |
| `depth20@100ms` | Reformat to {coin, bids:[{px,sz}], asks:[{px,sz}]} | `_handle_hl_orderbook(orderbook_dict)` |
| `markPrice@1s` | Extract price | `_handle_hl_price(symbol, price, ts)` |
| `aggTrade` (extended) | Wrap as FillEvent stub (closedPnl=0) | `_handle_hl_fill_extended(event)` |

Symbol transform: `"BTCUSDT"` → callback gets `"BTC"` (strip "USDT").

## Known Limitations

- **forceOrder is lossy**: 1 liquidation per symbol per second max. Acceptable — even sampled, Binance produces more signal than HL's complete stream.
- **No capitulation data**: aggTrade lacks `closedPnl`, `startPosition`. CapitulationTracker becomes inoperative. Not blocking — it wasn't gating entries.
- **No wallet data**: Position tracker, wallet registry, proximity scanner go unfed. Not blocking — not used operationally.

## Changes in service.py

1. Replace `NodeBridge` + `HyperliquidClient` init with `BinanceDataProvider`
2. Update `TOP_10_SYMBOLS` to new 20-coin list
3. Remove HL-specific startup (adapter health check, node bridge connect)
4. Remove L2 WS coin split logic (no longer needed — single combined stream)

## Unchanged

- Cascade sniper (4-layer detection)
- DCA system
- Trailing stop manager
- Gravity TP (static + dynamic)
- Regime classifier
- All calculators (VWAP, ATR, orderflow, z-score, burst aggregator)
- LiquidityMap
- GravityObserver
- Ghost trade system
- PostgreSQL persistence

## Error Handling

- Auto-reconnect on WS disconnect (exponential backoff: 1s, 2s, 4s, max 30s)
- 24h connection rotation (Binance forces disconnect)
- Ping/pong keepalive (Binance pings every 3 min, pong within 10 min)
- Feed freshness: reuse existing `_calculator_last_activity` tracking

## BinanceDataProvider Interface

```python
class BinanceDataProvider:
    def __init__(self, symbols: List[str]):
        """Connect to Binance Futures WS streams."""

    def set_callbacks(
        self,
        on_fill: Callable,           # (symbol, side, price, size, timestamp)
        on_liquidation: Callable,    # (symbol, side, price, size, timestamp)
        on_orderbook: Callable,      # (orderbook_dict)
        on_price: Callable,          # (symbol, price, timestamp)
        on_fill_extended: Callable,  # (FillEvent)
    ): ...

    async def start(self): ...
    async def stop(self): ...
```
