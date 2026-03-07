"""
Trade-Based Volume Profile

Aggregates taker fills into 10bp price bands over a 30-min rolling window.
Where fills cluster = real support/resistance. Unlike L2 orderbook data,
trades are confirmed transactions — no spoofing, no flickering.

Used by trailing stop manager to detect adverse trade volume near position price.
LONG + heavy sell volume above = resistance. SHORT + heavy buy volume below = support.

Thread safety: add_fill() and all queries called from asyncio event loop only.
trim_windows() also from asyncio. No daemon thread access.
"""

import time
from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Dict, Deque, List, Optional, Tuple


@dataclass(slots=True)
class TradeZone:
    """A price band with accumulated trade volume."""
    center_price: float
    band_low: float
    band_high: float
    side: str                # "buy" or "sell"
    total_volume_usd: float
    fill_count: int


@dataclass(slots=True)
class _Fill:
    """Internal fill record."""
    timestamp: float
    side: str       # "buy" or "sell"
    price: float
    size_usd: float


class TradeVolumeMap:
    """Volume profile from actual fills.

    Aggregates taker fills into adaptive price bands (10bp width).
    Rolling 30-min window. Queries return zones sorted by volume.
    """

    BAND_WIDTH_BPS = 10       # 10bp price bands
    HISTORY_WINDOW = 1800     # 30 min rolling window
    ZONE_CACHE_TTL = 5.0      # Recompute zones every 5s
    MIN_FILLS_WARMUP = 100    # Need 100 fills for meaningful data

    def __init__(self):
        self._fills: Dict[str, Deque[_Fill]] = {}
        self._zone_cache: Dict[str, Tuple[float, List[TradeZone]]] = {}

    def add_fill(
        self,
        coin: str,
        side: str,        # "buy" or "sell"
        price: float,
        size_usd: float,
        timestamp: float,
    ):
        """Record a taker fill. Called from fill drain loop (asyncio thread)."""
        if coin not in self._fills:
            self._fills[coin] = deque()
        self._fills[coin].append(_Fill(
            timestamp=timestamp, side=side, price=price, size_usd=size_usd
        ))
        # Invalidate zone cache on new fill
        self._zone_cache.pop(coin, None)

    def _compute_zones(self, coin: str, timestamp: float) -> List[TradeZone]:
        """Aggregate fills into price bands within the rolling window."""
        fill_deque = self._fills.get(coin)
        if not fill_deque:
            return []

        cutoff = timestamp - self.HISTORY_WINDOW

        # Accumulate per-band: (band_idx, side) → [total_usd, count]
        bands: Dict[Tuple[int, str], List[float]] = defaultdict(lambda: [0.0, 0])

        # Need a reference price for band width calculation
        # Use latest fill price
        latest_price = fill_deque[-1].price
        if latest_price <= 0:
            return []
        band_width = latest_price * self.BAND_WIDTH_BPS / 10_000

        for fill in fill_deque:
            if fill.timestamp < cutoff:
                continue
            band_idx = int(fill.price / band_width)
            key = (band_idx, fill.side)
            bands[key][0] += fill.size_usd
            bands[key][1] += 1

        zones = []
        for (band_idx, side), (total_usd, count) in bands.items():
            center = (band_idx + 0.5) * band_width
            zones.append(TradeZone(
                center_price=center,
                band_low=band_idx * band_width,
                band_high=(band_idx + 1) * band_width,
                side=side,
                total_volume_usd=total_usd,
                fill_count=int(count),
            ))

        zones.sort(key=lambda z: z.total_volume_usd, reverse=True)
        return zones

    def _get_zones_cached(self, coin: str) -> List[TradeZone]:
        """Get zones with TTL cache."""
        now = time.time()
        cached = self._zone_cache.get(coin)
        if cached is not None:
            cache_ts, zones = cached
            if now - cache_ts < self.ZONE_CACHE_TTL:
                return zones

        zones = self._compute_zones(coin, now)
        self._zone_cache[coin] = (now, zones)
        return zones

    def get_adverse_volume(
        self,
        coin: str,
        price: float,
        direction: str,
        range_bps: int = 30,
    ) -> float:
        """Total adverse trade volume within range_bps of price.

        LONG position → sell volume above price (resistance).
        SHORT position → buy volume below price (support pushing against us).

        Returns total USD volume.
        """
        zones = self._get_zones_cached(coin)
        if not zones:
            return 0.0

        price_range = price * range_bps / 10_000
        total = 0.0

        if direction == "LONG":
            for z in zones:
                if z.side == "sell" and z.center_price >= price and z.center_price <= price + price_range:
                    total += z.total_volume_usd
        else:  # SHORT
            for z in zones:
                if z.side == "buy" and z.center_price <= price and z.center_price >= price - price_range:
                    total += z.total_volume_usd

        return total

    def is_warmed_up(self, coin: str) -> bool:
        """True when enough fills recorded for meaningful data."""
        fill_deque = self._fills.get(coin)
        if not fill_deque:
            return False
        return len(fill_deque) >= self.MIN_FILLS_WARMUP

    def trim_windows(self, timestamp: float):
        """Remove fills older than HISTORY_WINDOW. Call periodically."""
        cutoff = timestamp - self.HISTORY_WINDOW
        for coin, fill_deque in self._fills.items():
            while fill_deque and fill_deque[0].timestamp < cutoff:
                fill_deque.popleft()
        # Clear zone cache for coins with no fills
        for coin in list(self._zone_cache):
            if coin not in self._fills or not self._fills[coin]:
                self._zone_cache.pop(coin, None)
