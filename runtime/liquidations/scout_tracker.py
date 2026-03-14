"""
Scout Position Tracker — lightweight in-memory tracker for fast wick-catching entries.

Scout positions are the first half of a two-tier cascade fade:
- Enters immediately when spike detected (no fuel gate)
- Tight trailing stop (30bp SL, 15bp activation, 10bp trail)
- Exits on L2 zone health degradation (zone consumed, dwell timeout, breach)
- No DCA, no gravity TP, no restart recovery

Zone health exit rules (from gravity_zone_events data analysis, 33k events):
- Zone held (size_ratio > 0.5) + dwell < 15s = 98.9% reversal — let it run
- Zone eaten (size_ratio < 0.5) + dwell > 10s = 57% coin flip — exit
- Dwell > 30s regardless = zone being absorbed — exit
- Price breaches zone boundary = zone failed — exit
"""

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class ZoneSnapshot:
    """L2 zone state at scout entry time."""
    center_price: float
    band_low: float
    band_high: float
    initial_size_usd: float
    gravity: float
    side: str  # "bid" or "ask"


@dataclass
class ScoutPosition:
    """Lightweight position for wick-catching."""
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    entry_ts: float
    zone: ZoneSnapshot
    trade_id: str = ""
    zone_arrival_ts: float = 0.0

    def pnl(self, exit_price: float) -> float:
        if self.side == "LONG":
            return (exit_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - exit_price) * self.quantity


# Zone health thresholds (calibrated from 33k gravity_zone_events)
ZONE_EATEN_RATIO = 0.5       # Zone consumed if current_size < 50% of initial
ZONE_EATEN_MIN_DWELL = 10.0  # Only exit if eaten AND dwell > 10s
ZONE_MAX_DWELL = 30.0        # Exit regardless after 30s at zone


class ScoutTracker:
    """In-memory tracker for scout positions.

    One scout per symbol. No persistence (scouts are short-lived).
    """

    def __init__(self):
        self._positions: Dict[str, ScoutPosition] = {}
        self._trade_counter: int = 0

    def open_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        timestamp: float,
        zone: ZoneSnapshot,
    ) -> Optional[ScoutPosition]:
        """Open a scout position. Returns None if one already exists for symbol."""
        if symbol in self._positions:
            return None

        self._trade_counter += 1
        pos = ScoutPosition(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_ts=timestamp,
            zone=zone,
            trade_id=f"SCOUT_{self._trade_counter:06d}",
            zone_arrival_ts=timestamp,
        )
        self._positions[symbol] = pos
        return pos

    def has_open(self, symbol: str) -> bool:
        return symbol in self._positions

    def get_position(self, symbol: str) -> Optional[ScoutPosition]:
        return self._positions.get(symbol)

    def get_all_open(self) -> Dict[str, ScoutPosition]:
        return dict(self._positions)

    def close_position(
        self, symbol: str, exit_price: float, exit_reason: str
    ) -> Optional[float]:
        """Close scout position. Returns PnL in USD or None if no position."""
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return None
        pnl = pos.pnl(exit_price)
        hold_s = time.time() - pos.entry_ts
        print(f"SCOUT_EXIT: {symbol} {pos.side} {exit_reason} "
              f"entry=${pos.entry_price:,.2f} exit=${exit_price:,.2f} "
              f"PnL=${pnl:+.4f} hold={hold_s:.1f}s")
        return pnl

    def check_zone_health(
        self,
        symbol: str,
        current_zone_size_usd: float,
        current_price: float,
        timestamp: float,
    ) -> Tuple[bool, str]:
        """Check if scout should exit based on zone health.

        Returns (should_exit, reason).

        Rules (from gravity_zone_events analysis):
        1. Zone breach: price outside zone boundary -> exit immediately
        2. Zone eaten + dwell > 10s: size_ratio < 0.5 -> exit (57% reversal = coin flip)
        3. Max dwell > 30s: zone being absorbed -> exit regardless
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return False, ""

        zone = pos.zone
        dwell = timestamp - pos.zone_arrival_ts

        # Rule 1: zone breach
        if pos.side == "LONG" and current_price < zone.band_low:
            return True, f"ZONE_BREACH: price ${current_price:,.2f} < zone low ${zone.band_low:,.2f}"
        if pos.side == "SHORT" and current_price > zone.band_high:
            return True, f"ZONE_BREACH: price ${current_price:,.2f} > zone high ${zone.band_high:,.2f}"

        # Rule 3: max dwell (check before eaten)
        if dwell > ZONE_MAX_DWELL:
            size_ratio = current_zone_size_usd / zone.initial_size_usd if zone.initial_size_usd > 0 else 0
            return True, f"MAX_DWELL: {dwell:.0f}s at zone (size_ratio={size_ratio:.0%})"

        # Rule 2: zone eaten + lingering
        if zone.initial_size_usd > 0:
            size_ratio = current_zone_size_usd / zone.initial_size_usd
            if size_ratio < ZONE_EATEN_RATIO and dwell > ZONE_EATEN_MIN_DWELL:
                return True, f"ZONE_EATEN: size_ratio={size_ratio:.0%} dwell={dwell:.0f}s"

        return False, ""
