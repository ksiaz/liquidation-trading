"""
Real-time macro wall tracker.

Aggregates individual zone reversal/breach events into macro walls.
Tracks consecutive reversals, OB absorption, and prior visits
to detect high-confidence structural levels.

Research: memory/gravity_wall_research.md
Gold filter: OB + prior held + last3=3 → 100% reversal (N=88, 11 days)
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class WallStatus:
    """Current state of macro wall at a price level."""
    coin: str
    center: float
    side: str
    consecutive_reversals: int
    total_zones: int
    total_gravity: float
    is_ob: bool
    absorbed_zones: int
    prior_reversals: int
    gold_signal: bool
    last_event_ts: float
    wall_band_low: float = 0.0
    wall_band_high: float = 0.0
    next_wall_center: Optional[float] = None
    next_wall_distance_bp: Optional[float] = None


_WALL_BAND_BP = 25
_WALL_TIME_WINDOW = 900
_PRIOR_VISIT_WINDOW = 14400
_PRIOR_VISIT_BAND_BP = 50
_WALL_STALE_SEC = 900
_OB_DEEP_THRESHOLD = 0.50
_OB_ABSORBED_THRESHOLD = 0.30


@dataclass
class _ZoneEvent:
    center: float
    gravity: float
    reversal: bool
    breached: bool
    absorbed: bool
    deep_absorbed: bool
    timestamp: float


@dataclass
class _WallState:
    coin: str
    side: str
    events: List[_ZoneEvent] = field(default_factory=list)
    first_ts: float = 0.0
    last_ts: float = 0.0


class WallTracker:
    def __init__(self):
        self._current_wall: Dict[str, _WallState] = {}
        self._wall_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=200)
        )

    def on_zone_finalized(self, coin, zone_center, zone_side, reversal,
                          breached, min_size_ratio, gravity, timestamp):
        absorbed = (1 - min_size_ratio) >= _OB_ABSORBED_THRESHOLD
        deep_absorbed = (1 - min_size_ratio) >= _OB_DEEP_THRESHOLD
        event = _ZoneEvent(center=zone_center, gravity=gravity,
                           reversal=reversal, breached=breached,
                           absorbed=absorbed, deep_absorbed=deep_absorbed,
                           timestamp=timestamp)
        wall = self._current_wall.get(coin)
        if wall and wall.events:
            last = wall.events[-1]
            price_gap = abs(zone_center - last.center) / last.center * 10000 if last.center > 0 else 999
            time_gap = timestamp - wall.last_ts
            if price_gap <= _WALL_BAND_BP and time_gap <= _WALL_TIME_WINDOW:
                wall.events.append(event)
                wall.last_ts = timestamp
                return
            self._archive_wall(wall)
        self._current_wall[coin] = _WallState(
            coin=coin, side=zone_side, events=[event],
            first_ts=timestamp, last_ts=timestamp)

    def get_wall_status(self, coin, now=None, liquidity_map=None,
                        current_price=None):
        wall = self._current_wall.get(coin)
        if not wall or not wall.events:
            return None
        if now is None:
            now = wall.last_ts
        if now - wall.last_ts > _WALL_STALE_SEC:
            self._archive_wall(wall)
            self._current_wall.pop(coin, None)
            return None
        events = wall.events
        total_gravity = sum(e.gravity for e in events)
        centers = [e.center for e in events]
        grav_center = sum(e.center * e.gravity for e in events) / max(total_gravity, 1)
        consec = 0
        for e in reversed(events):
            if e.reversal:
                consec += 1
            else:
                break
        absorbed_count = sum(1 for e in events if e.absorbed)
        has_deep = any(e.deep_absorbed for e in events)
        is_ob = has_deep or absorbed_count >= 2
        prior_rev = self._count_prior_reversals(coin, grav_center, wall.first_ts)
        gold = is_ob and prior_rev >= 1 and consec >= 3
        status = WallStatus(
            coin=coin, center=grav_center, side=wall.side,
            consecutive_reversals=consec, total_zones=len(events),
            total_gravity=total_gravity, is_ob=is_ob,
            absorbed_zones=absorbed_count, prior_reversals=prior_rev,
            gold_signal=gold, last_event_ts=wall.last_ts,
            wall_band_low=min(centers), wall_band_high=max(centers))
        if liquidity_map and current_price and consec >= 3:
            if wall.side == "bid":
                next_zones = liquidity_map.get_zones_above(coin, current_price, min_gravity=50000)
            else:
                next_zones = liquidity_map.get_zones_below(coin, current_price, min_gravity=50000)
            next_zones_sorted = sorted(next_zones, key=lambda z: abs(z.center_price - current_price))
            for z in next_zones_sorted:
                dist = abs(z.center_price - current_price) / current_price * 10000
                if dist >= 10:
                    status.next_wall_center = z.center_price
                    status.next_wall_distance_bp = dist
                    break
        return status

    def _count_prior_reversals(self, coin, center, before_ts):
        count = 0
        cutoff = before_ts - _PRIOR_VISIT_WINDOW
        for hist_wall in self._wall_history.get(coin, []):
            if hist_wall['ts'] < cutoff:
                continue
            if hist_wall['ts'] >= before_ts:
                continue
            price_gap = abs(hist_wall['center'] - center) / center * 10000 if center > 0 else 999
            if price_gap <= _PRIOR_VISIT_BAND_BP:
                count += hist_wall['reversals']
        return count

    def _archive_wall(self, wall):
        if not wall.events:
            return
        total_grav = sum(e.gravity for e in wall.events)
        center = sum(e.center * e.gravity for e in wall.events) / max(total_grav, 1)
        reversals = sum(1 for e in wall.events if e.reversal)
        self._wall_history[wall.coin].append({
            'center': center, 'ts': wall.last_ts,
            'reversals': reversals, 'gravity': total_grav})
