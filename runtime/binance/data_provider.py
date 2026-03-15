"""
Binance Futures WebSocket Data Provider.

Connects to Binance USDS-M Futures WebSocket streams and fires callbacks
matching the existing NodeBridge/HyperliquidClient interface. Drop-in
replacement for the HL data layer — service.py trading logic unchanged.

Streams used:
- aggTrade: taker fills → on_fill(symbol, side, price, size, timestamp)
- forceOrder: liquidations → on_liquidation(symbol, side, price, size, timestamp)
- depth20@100ms: L2 orderbook → on_orderbook(orderbook_dict)
- markPrice@1s: mark prices → on_price(symbol, price, timestamp)
"""

import asyncio
import json
import sys
import time
from typing import Callable, Dict, List, Optional, Set

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


WS_BASE = "wss://fstream.binance.com/stream?streams="


class BinanceDataProvider:
    """Binance Futures WS data provider with NodeBridge-compatible callbacks."""

    def __init__(self, symbols: List[str]):
        self._symbols = symbols
        self._symbol_set: Set[str] = set(symbols)
        self._running = False
        self._ws_tasks: List[asyncio.Task] = []

        # Callbacks (set by caller before start)
        self.on_fill: Optional[Callable] = None
        self.on_liquidation: Optional[Callable] = None
        self.on_orderbook: Optional[Callable] = None
        self.on_price: Optional[Callable] = None
        self.on_fill_extended: Optional[Callable] = None

        # Stats
        self.fills_received = 0
        self.liqs_received = 0
        self.depth_received = 0
        self.prices_received = 0
        self._last_fill_time = 0.0
        self._last_price_time = 0.0

    @property
    def is_connected(self) -> bool:
        """Duck-type compatibility with NodeBridge for DataFreshnessBreaker."""
        return self._running and len(self._ws_tasks) > 0

    def get_metrics(self) -> Dict:
        """Duck-type compatibility with NodeBridge for DataFreshnessBreaker."""
        return {
            'prices_ingested': self.prices_received,
            'fills_ingested': self.fills_received,
            'liquidations_ingested': self.liqs_received,
            'last_price_time': self._last_price_time,
            'last_fill_time': self._last_fill_time,
            'errors': 0,
        }

    def _to_coin(self, symbol: str) -> str:
        """BTCUSDT → BTC"""
        return symbol.removesuffix("USDT")

    def _build_stream_names(self) -> List[str]:
        """Build list of all stream names for WS subscription."""
        streams = []
        for s in self._symbols:
            sl = s.lower()
            streams.append(f"{sl}@aggTrade")
            streams.append(f"{sl}@depth20@100ms")
        streams.append("!forceOrder@arr")
        streams.append("!markPrice@arr@1s")
        return streams

    # ── Message Handlers ──────────────────────────────────────────────

    def _handle_agg_trade(self, msg: Dict):
        """aggTrade → on_fill callback.

        Binance m field: true = buyer is maker → taker sold → side "A"
                         false = seller is maker → taker bought → side "B"
        """
        symbol = msg.get("s", "")
        if symbol not in self._symbol_set:
            return
        if not self.on_fill:
            return

        side = "A" if msg.get("m") else "B"
        price = float(msg["p"])
        size = float(msg["q"])
        timestamp = msg["T"] / 1000.0

        self.fills_received += 1
        self._last_fill_time = time.time()
        coin = self._to_coin(symbol)
        self.on_fill(coin, side, price, size, timestamp)

    def _handle_force_order(self, msg: Dict):
        """forceOrder → on_liquidation callback.

        Binance S field: "SELL" = long position liquidated → side "LONG"
                         "BUY" = short position liquidated → side "SHORT"
        Uses average fill price (ap) not limit price (p).
        """
        order = msg.get("o", {})
        symbol = order.get("s", "")
        if symbol not in self._symbol_set:
            return
        if not self.on_liquidation:
            return

        side = "LONG" if order.get("S") == "SELL" else "SHORT"
        price = float(order.get("ap", order.get("p", "0")))
        size = float(order.get("q", "0"))
        timestamp = order["T"] / 1000.0

        self.liqs_received += 1
        coin = self._to_coin(symbol)
        self.on_liquidation(coin, side, price, size, timestamp)

    def _handle_depth(self, msg: Dict):
        """depth20 → on_orderbook callback.

        Converts Binance format [[price, qty], ...] to HL-compatible
        {coin, bids: [{price, size}], asks: [{price, size}]}.
        """
        symbol = msg.get("s", "")
        if symbol not in self._symbol_set:
            return
        if not self.on_orderbook:
            return

        self.depth_received += 1
        coin = self._to_coin(symbol)

        bids = [{"price": float(b[0]), "size": float(b[1])} for b in msg.get("b", [])]
        asks = [{"price": float(a[0]), "size": float(a[1])} for a in msg.get("a", [])]

        self.on_orderbook({"coin": coin, "bids": bids, "asks": asks})

    def _handle_mark_price(self, msg: Dict):
        """markPriceUpdate → on_price callback."""
        symbol = msg.get("s", "")
        if symbol not in self._symbol_set:
            return
        if not self.on_price:
            return

        self.prices_received += 1
        self._last_price_time = time.time()
        coin = self._to_coin(symbol)
        price = float(msg["p"])
        timestamp = msg["E"] / 1000.0

        self.on_price(coin, price, timestamp)

    def _dispatch(self, msg):
        """Route a parsed message to the appropriate handler."""
        # markPrice@arr sends an array of all mark prices
        if isinstance(msg, list):
            for item in msg:
                if isinstance(item, dict) and item.get("e") == "markPriceUpdate":
                    self._handle_mark_price(item)
            return

        event_type = msg.get("e")
        if event_type == "aggTrade":
            self._handle_agg_trade(msg)
        elif event_type == "forceOrder":
            self._handle_force_order(msg)
        elif event_type == "depthUpdate":
            self._handle_depth(msg)
        elif event_type == "markPriceUpdate":
            self._handle_mark_price(msg)

    # ── WebSocket Connection ──────────────────────────────────────────

    async def _run_ws(self, streams: List[str], name: str):
        """Run a single WS connection with auto-reconnect."""
        url = WS_BASE + "/".join(streams)
        backoff = 1.0

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=60, ping_timeout=30) as ws:
                    print(f"[Binance-{name}] Connected ({len(streams)} streams)", file=sys.stderr)
                    backoff = 1.0

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            envelope = json.loads(raw)
                            data = envelope.get("data", envelope)
                            self._dispatch(data)
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            print(f"[Binance-{name}] Parse error: {e}", file=sys.stderr)

            except Exception as e:
                if not self._running:
                    break
                print(f"[Binance-{name}] Disconnected: {e}, reconnecting in {backoff:.0f}s",
                      file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def start(self):
        """Start WS connections. Call from asyncio event loop."""
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("pip install websockets")

        self._running = True
        all_streams = self._build_stream_names()

        # Split into two connections for cleaner organization
        trade_streams = [s for s in all_streams if "aggTrade" in s or "forceOrder" in s]
        book_streams = [s for s in all_streams if "depth" in s or "markPrice" in s]

        self._ws_tasks = [
            asyncio.create_task(self._run_ws(trade_streams, "trades")),
            asyncio.create_task(self._run_ws(book_streams, "books")),
        ]
        print(f"[Binance] Started: {len(trade_streams)} trade streams, "
              f"{len(book_streams)} book streams", file=sys.stderr)

    async def stop(self):
        """Stop all WS connections."""
        self._running = False
        for task in self._ws_tasks:
            task.cancel()
        if self._ws_tasks:
            await asyncio.gather(*self._ws_tasks, return_exceptions=True)
        self._ws_tasks = []
        print(f"[Binance] Stopped. Received: fills={self.fills_received}, "
              f"liqs={self.liqs_received}, depth={self.depth_received}, "
              f"prices={self.prices_received}", file=sys.stderr)
