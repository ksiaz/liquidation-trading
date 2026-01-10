"""
Orderbook Zoning & Compression Module

Converts raw L2 orderbook into normalized liquidity zones.

Zones are defined relative to mid-price:
- Zone A: 0-5 basis points (tight liquidity)
- Zone B: 5-15 basis points (extended buffer)
- Zone C: 15-30 basis points (context only, non-tradable)

INVARIANTS:
- Zones always relative to mid-price
- No per-level logic exposed to strategies
- All levels within zone aggregated
- Deterministic calculations
"""

from .types import ZoneLiquidity, OrderbookZones, ZoneMetrics
from .zone_calculator import ZoneCalculator
from .zone_state import ZoneState

__all__ = [
    "ZoneLiquidity",
    "OrderbookZones",
    "ZoneMetrics",
    "ZoneCalculator",
    "ZoneState",
]
