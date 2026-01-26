"""Live Price View Tool - For debugging and analysis.

Quick access to:
- Current prices
- Recent candles
- Order book snapshot
- Whale order tracking
"""

import requests
import time
from datetime import datetime
from typing import Optional, Dict, List
import json


class LiveView:
    """Live market data viewer."""

    BASE_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self):
        self._price_cache: Dict[str, float] = {}
        self._last_fetch = 0

    def _post(self, payload: dict) -> dict:
        resp = requests.post(self.BASE_URL, json=payload, timeout=10)
        return resp.json()

    def prices(self, coins: Optional[List[str]] = None) -> Dict[str, float]:
        """Get current prices."""
        data = self._post({"type": "allMids"})
        self._price_cache = {k: float(v) for k, v in data.items()}
        self._last_fetch = time.time()

        if coins:
            return {c: self._price_cache.get(c, 0) for c in coins}
        return self._price_cache

    def price(self, coin: str) -> float:
        """Get single coin price."""
        if time.time() - self._last_fetch > 1:
            self.prices()
        return self._price_cache.get(coin, 0)

    def candles(self, coin: str, interval: str = "1m", count: int = 30) -> List[dict]:
        """Get recent candles."""
        end_time = int(time.time() * 1000)

        # Calculate start time based on interval
        interval_ms = {
            "1m": 60000, "5m": 300000, "15m": 900000,
            "1h": 3600000, "4h": 14400000, "1d": 86400000
        }.get(interval, 60000)

        start_time = end_time - (count * interval_ms)

        data = self._post({
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time
            }
        })

        if isinstance(data, list):
            return data
        return []

    def book(self, coin: str, depth: int = 10) -> dict:
        """Get order book."""
        data = self._post({"type": "l2Book", "coin": coin})
        levels = data.get("levels", [[], []])

        bids = levels[0][:depth] if len(levels) > 0 else []
        asks = levels[1][:depth] if len(levels) > 1 else []

        return {
            "bids": [(float(b["px"]), float(b["sz"]), int(b["n"])) for b in bids],
            "asks": [(float(a["px"]), float(a["sz"]), int(a["n"])) for a in asks],
            "spread": float(asks[0]["px"]) - float(bids[0]["px"]) if bids and asks else 0
        }

    def trades(self, coin: str, count: int = 50) -> List[dict]:
        """Get recent trades."""
        data = self._post({
            "type": "recentTrades",
            "coin": coin,
            "count": count
        })
        return data if isinstance(data, list) else []

    def wallet_orders(self, wallet: str, coin: Optional[str] = None) -> List[dict]:
        """Get open orders for wallet."""
        data = self._post({"type": "openOrders", "user": wallet})
        if coin:
            return [o for o in data if o.get("coin") == coin]
        return data

    def wallet_position(self, wallet: str, coin: str) -> Optional[dict]:
        """Get position for wallet/coin."""
        data = self._post({"type": "clearinghouseState", "user": wallet})
        for p in data.get("assetPositions", []):
            if p["position"]["coin"] == coin:
                pos = p["position"]
                return {
                    "side": "SHORT" if float(pos["szi"]) < 0 else "LONG",
                    "size": abs(float(pos["szi"])),
                    "entry": float(pos["entryPx"]),
                    "pnl": float(pos.get("unrealizedPnl", 0))
                }
        return None

    def wallet_fills(self, wallet: str, coin: Optional[str] = None, hours: float = 24) -> List[dict]:
        """Get recent fills for wallet."""
        data = self._post({"type": "userFills", "user": wallet})

        cutoff = (time.time() - hours * 3600) * 1000
        fills = [f for f in data if int(f.get("time", 0)) > cutoff]

        if coin:
            fills = [f for f in fills if f.get("coin") == coin]

        return fills

    # === Display methods ===

    def show_price(self, coin: str):
        """Print current price with context."""
        price = self.price(coin)
        candles = self.candles(coin, "1m", 60)

        if candles:
            highs = [float(c["h"]) for c in candles]
            lows = [float(c["l"]) for c in candles]
            h1_high = max(highs)
            h1_low = min(lows)

            pct_from_high = ((h1_high - price) / h1_high) * 100
            pct_from_low = ((price - h1_low) / h1_low) * 100

            print(f"{coin}: ${price:.6f}")
            print(f"  1H Range: {h1_low:.6f} - {h1_high:.6f}")
            print(f"  From high: -{pct_from_high:.2f}%  From low: +{pct_from_low:.2f}%")
        else:
            print(f"{coin}: ${price:.6f}")

    def show_book(self, coin: str, depth: int = 5):
        """Print order book."""
        book = self.book(coin, depth)
        price = self.price(coin)

        print(f"\n{coin} Order Book (price: {price:.6f})")
        print("-" * 50)

        # Asks (reversed to show highest first)
        for px, sz, n in reversed(book["asks"]):
            pct = ((px - price) / price) * 100
            bar = "█" * min(int(sz / 10000), 20)
            print(f"  ASK {px:.6f} (+{pct:.2f}%) | {sz:>10,.0f} | {bar}")

        print(f"  --- SPREAD: {book['spread']:.6f} ---")

        for px, sz, n in book["bids"]:
            pct = ((price - px) / price) * 100
            bar = "█" * min(int(sz / 10000), 20)
            print(f"  BID {px:.6f} (-{pct:.2f}%) | {sz:>10,.0f} | {bar}")

    def show_candles(self, coin: str, interval: str = "1m", count: int = 15):
        """Print recent candles."""
        candles = self.candles(coin, interval, count)

        print(f"\n{coin} {interval} Candles")
        print("-" * 70)

        for c in candles[-count:]:
            t = datetime.fromtimestamp(c["t"] / 1000).strftime("%H:%M")
            o, h, l, close = float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"])
            v = float(c["v"])

            pct = ((close - o) / o) * 100
            icon = "🟢" if close >= o else "🔴"

            print(f"{t} {icon} O:{o:.5f} H:{h:.5f} L:{l:.5f} C:{close:.5f} | V:{v:>8,.0f} | {pct:+.2f}%")

    def show_whale(self, wallet: str, coin: str):
        """Show whale's position and orders on a coin."""
        pos = self.wallet_position(wallet, coin)
        orders = self.wallet_orders(wallet, coin)
        fills = self.wallet_fills(wallet, coin, hours=2)
        price = self.price(coin)

        print(f"\n=== WHALE {wallet[:10]}... on {coin} ===")
        print(f"Current price: {price:.6f}")
        print()

        if pos:
            pnl_pct = (pos["pnl"] / (pos["size"] * pos["entry"])) * 100 if pos["size"] > 0 else 0
            print(f"Position: {pos['side']} {pos['size']:,.0f} @ {pos['entry']:.6f}")
            print(f"PnL: ${pos['pnl']:+,.0f} ({pnl_pct:+.2f}%)")
        else:
            print("Position: None")

        print(f"\nOpen Orders ({len(orders)}):")
        sells = sorted([o for o in orders if o["side"] == "A"], key=lambda x: float(x["limitPx"]))
        buys = sorted([o for o in orders if o["side"] == "B"], key=lambda x: -float(x["limitPx"]))

        for o in sells[:5]:
            px = float(o["limitPx"])
            sz = float(o["sz"])
            dist = ((px - price) / price) * 100
            print(f"  SELL {sz:>10,.0f} @ {px:.6f} (+{dist:.2f}%)")

        if len(sells) > 5:
            print(f"  ... and {len(sells) - 5} more sells")

        for o in buys[:5]:
            px = float(o["limitPx"])
            sz = float(o["sz"])
            dist = ((price - px) / price) * 100
            print(f"  BUY  {sz:>10,.0f} @ {px:.6f} (-{dist:.2f}%)")

        if len(buys) > 5:
            print(f"  ... and {len(buys) - 5} more buys")

        print(f"\nRecent Fills ({len(fills)}):")
        for f in fills[-10:]:
            ts = datetime.fromtimestamp(int(f["time"]) / 1000).strftime("%H:%M:%S")
            side = "BUY " if f["side"] == "B" else "SELL"
            sz = float(f["sz"])
            px = float(f["px"])
            print(f"  {ts} | {side} {sz:>8,.0f} @ {px:.6f}")


# Quick access instance
view = LiveView()


def quick_look(coin: str, whale: str = None):
    """Quick overview of a coin and optionally a whale."""
    v = LiveView()
    v.show_price(coin)
    v.show_candles(coin, "1m", 10)
    v.show_book(coin, 5)

    if whale:
        v.show_whale(whale, coin)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python live_view.py <COIN> [WHALE_ADDRESS]")
        print("Example: python live_view.py ZETA")
        print("Example: python live_view.py ZETA 0x010461c14e146ac35fe42271bdc1134ee31c703a")
        sys.exit(1)

    coin = sys.argv[1].upper()
    whale = sys.argv[2] if len(sys.argv) > 2 else None

    quick_look(coin, whale)
