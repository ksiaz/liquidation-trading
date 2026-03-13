"""
Gravity Zone Observer — passive data collection for zone-to-zone traverse research.

Watches price arrivals at L2 gravity zones, tracks dwell/absorption/outcome,
persists to PG for post-hoc analysis. No trading logic.

Called from regime loop in service.py once per coin per cycle (~200ms).
"""

import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from runtime.liquidations.liquidity_map import LiquidityZone


@dataclass
class ZoneArrivalEvent:
    """One observed price arrival at a gravity zone."""
    event_id: str
    coin: str
    state: str  # "DWELLING", "TRACKING"

    # Zone snapshot
    zone_center: float
    zone_low: float
    zone_high: float
    zone_side: str
    zone_gravity: float
    zone_persistence: float
    zone_size_initial: float

    # Arrival
    arrival_ts: float
    arrival_price: float
    approach_direction: str  # "from_above" or "from_below"
    zone_strength: int = 0      # 0=noise, 1=weak, 2=notable, 3=strong
    zone_gravity_rank: float = 0.0  # percentile rank (0.0-1.0)
    of_imbalance_arrival: float = 0.0
    of_fills_arrival: int = 0

    # Destinations (set at arrival)
    dest_zones_above: str = "[]"  # JSON
    dest_zones_below: str = "[]"  # JSON
    path_gravity_above: float = 0.0
    path_gravity_below: float = 0.0
    cascade_active: bool = False

    # Dwell tracking
    zone_exit_ts: float = 0.0
    exit_price: float = 0.0
    exit_direction: str = ""
    dwell_duration_s: float = 0.0
    size_samples: list = field(default_factory=list)
    size_ratio: float = 0.0
    min_size_ratio: float = 0.0
    last_sample_ts: float = 0.0
    of_imbalance_exit: float = 0.0
    of_fills_exit: int = 0

    # Outcome tracking
    highest_since_exit: float = 0.0
    lowest_since_exit: float = 0.0
    reversal: bool = False
    mfe_30s: float = 0.0
    mfe_60s: float = 0.0
    mfe_120s: float = 0.0
    mae_30s: float = 0.0
    mae_60s: float = 0.0
    mae_120s: float = 0.0
    destination_reached: Optional[str] = None
    destination_gravity: Optional[float] = None
    destination_strength: Optional[int] = None
    destination_time_s: Optional[float] = None
    breached: bool = False

    # Internal
    _brief_exit_ts: float = 0.0  # for 10s re-entry grace


_SIZE_SAMPLE_INTERVAL = 5.0
_REENTRY_GRACE_SEC = 10.0
_OUTCOME_WINDOW_SEC = 120.0


class GravityObserver:
    """Passive observer of price behavior at L2 gravity zones."""

    def __init__(self, min_obs_gravity: float = 5000):
        self._min_gravity = min_obs_gravity
        self._active: Dict[str, Optional[ZoneArrivalEvent]] = {}
        self._last_price: Dict[str, float] = {}
        self._last_zone: Dict[str, Optional[tuple]] = {}  # (center, side) of zone price was in
        self._recent: deque = deque(maxlen=500)
        self._pending_persist: List[ZoneArrivalEvent] = []

    def on_price_update(
        self,
        coin: str,
        price: float,
        timestamp: float,
        liquidity_map,
        orderflow_calc=None,
    ):
        """Called each regime loop cycle. Drives the state machine."""
        prev_price = self._last_price.get(coin)
        self._last_price[coin] = price

        if not liquidity_map.is_warmed_up(coin):
            return

        event = self._active.get(coin)

        if event is None:
            if prev_price is not None:
                self._check_arrival(coin, price, prev_price, timestamp,
                                    liquidity_map, orderflow_calc)
        elif event.state == "DWELLING":
            self._update_dwell(coin, price, timestamp, liquidity_map,
                               orderflow_calc)
        elif event.state == "TRACKING":
            self._update_tracking(coin, price, timestamp, liquidity_map)

    # ── State transitions ────────────────────────────────────────────

    def _check_arrival(self, coin, price, prev_price, ts, liq_map, of_calc):
        """IDLE → DWELLING if price enters a qualifying zone."""
        zones = liq_map.get_zones(coin, min_gravity=self._min_gravity)
        if not zones:
            self._last_zone[coin] = None
            return

        # Find strongest zone price is currently inside
        current_zone = None
        for z in zones:  # sorted by gravity desc
            if z.band_low <= price <= z.band_high:
                current_zone = z
                break

        current_key = (round(current_zone.center_price, 8), current_zone.side) if current_zone else None
        prev_key = self._last_zone.get(coin)
        self._last_zone[coin] = current_key

        # Arrival = entered a zone that's different from last cycle's zone
        if current_zone is None or current_key == prev_key:
            return

        hit_zone = current_zone
        direction = "from_above" if prev_price > hit_zone.center_price else "from_below"

        # Snapshot destination candidates
        above = liq_map.get_zones_above(coin, price, min_gravity=self._min_gravity)
        below = liq_map.get_zones_below(coin, price, min_gravity=self._min_gravity)

        dest_above = json.dumps([
            {"center": round(z.center_price, 6), "gravity": round(z.gravity, 1),
             "distance_bps": round(abs(z.center_price - price) / price * 10000, 1),
             "strength": getattr(z, 'strength', 0)}
            for z in sorted(above, key=lambda x: x.center_price)[:3]
        ])
        dest_below = json.dumps([
            {"center": round(z.center_price, 6), "gravity": round(z.gravity, 1),
             "distance_bps": round(abs(z.center_price - price) / price * 10000, 1),
             "strength": getattr(z, 'strength', 0)}
            for z in sorted(below, key=lambda x: x.center_price, reverse=True)[:3]
        ])

        # Path gravity to nearest destinations
        pg_above = 0.0
        if above:
            nearest_above = min(above, key=lambda z: z.center_price)
            pg_above = liq_map.get_depth_between(coin, price, nearest_above.center_price)
        pg_below = 0.0
        if below:
            nearest_below = max(below, key=lambda z: z.center_price)
            pg_below = liq_map.get_depth_between(coin, nearest_below.center_price, price)

        of_imb = 0.0
        of_fills = 0
        if of_calc:
            of_imb = of_calc.get_imbalance_60s() or 0.0
            of_fills = getattr(of_calc, 'get_fill_count_60s', lambda: 0)()

        event = ZoneArrivalEvent(
            event_id=str(uuid.uuid4())[:12],
            coin=coin,
            state="DWELLING",
            zone_center=hit_zone.center_price,
            zone_low=hit_zone.band_low,
            zone_high=hit_zone.band_high,
            zone_side=hit_zone.side,
            zone_gravity=hit_zone.gravity,
            zone_persistence=hit_zone.persistence,
            zone_size_initial=hit_zone.current_size_usd,
            zone_strength=getattr(hit_zone, 'strength', 0),
            zone_gravity_rank=getattr(hit_zone, 'gravity_rank', 0.0),
            arrival_ts=ts,
            arrival_price=price,
            approach_direction=direction,
            of_imbalance_arrival=of_imb,
            of_fills_arrival=of_fills,
            dest_zones_above=dest_above,
            dest_zones_below=dest_below,
            path_gravity_above=pg_above,
            path_gravity_below=pg_below,
            last_sample_ts=ts,
        )
        event.size_samples.append(hit_zone.current_size_usd)
        self._active[coin] = event

    def _update_dwell(self, coin, price, ts, liq_map, of_calc):
        """Update DWELLING state. Transition to TRACKING on zone exit."""
        event = self._active[coin]
        in_zone = event.zone_low <= price <= event.zone_high

        if in_zone:
            event._brief_exit_ts = 0.0
            # Sample zone size periodically
            if ts - event.last_sample_ts >= _SIZE_SAMPLE_INTERVAL:
                zones = liq_map.get_zones(coin, min_gravity=0)
                current_size = 0.0
                for z in zones:
                    if (abs(z.center_price - event.zone_center) / max(event.zone_center, 1) < 0.001
                            and z.side == event.zone_side):
                        current_size = z.current_size_usd
                        break
                event.size_samples.append(current_size)
                event.last_sample_ts = ts
        else:
            # Price outside zone
            if event._brief_exit_ts == 0.0:
                event._brief_exit_ts = ts

            if ts - event._brief_exit_ts < _REENTRY_GRACE_SEC:
                # Check re-entry
                if event.zone_low <= price <= event.zone_high:
                    event._brief_exit_ts = 0.0
                return

            # Confirmed exit → TRACKING
            event.state = "TRACKING"
            event.zone_exit_ts = event._brief_exit_ts
            event.exit_price = price
            event.dwell_duration_s = event._brief_exit_ts - event.arrival_ts
            event.exit_direction = "upward" if price > event.zone_center else "downward"
            event.highest_since_exit = price
            event.lowest_since_exit = price

            if of_calc:
                event.of_imbalance_exit = of_calc.get_imbalance_60s() or 0.0
                event.of_fills_exit = getattr(of_calc, 'get_fill_count_60s', lambda: 0)()

            if event.size_samples and event.zone_size_initial > 0:
                event.min_size_ratio = min(event.size_samples) / event.zone_size_initial

    def _update_tracking(self, coin, price, ts, liq_map):
        """Update TRACKING state. Compute MFE/MAE. Finalize after 120s."""
        event = self._active[coin]

        event.highest_since_exit = max(event.highest_since_exit, price)
        event.lowest_since_exit = min(event.lowest_since_exit, price)

        elapsed = ts - event.zone_exit_ts
        ep = event.exit_price

        if event.exit_direction == "upward":
            mfe_bps = (event.highest_since_exit - ep) / ep * 10000
            mae_bps = (ep - event.lowest_since_exit) / ep * 10000
        else:
            mfe_bps = (ep - event.lowest_since_exit) / ep * 10000
            mae_bps = (event.highest_since_exit - ep) / ep * 10000

        if elapsed <= 30:
            event.mfe_30s = max(event.mfe_30s, mfe_bps)
            event.mae_30s = max(event.mae_30s, mae_bps)
        if elapsed <= 60:
            event.mfe_60s = max(event.mfe_60s, mfe_bps)
            event.mae_60s = max(event.mae_60s, mae_bps)
        if elapsed <= 120:
            event.mfe_120s = max(event.mfe_120s, mfe_bps)
            event.mae_120s = max(event.mae_120s, mae_bps)

        # Check if destination zone reached
        if event.destination_reached is None:
            zones = liq_map.get_zones(coin, min_gravity=self._min_gravity)
            for z in zones:
                if (abs(z.center_price - event.zone_center) / max(event.zone_center, 1) < 0.001
                        and z.side == event.zone_side):
                    continue  # skip departure zone
                if z.band_low <= price <= z.band_high:
                    event.destination_reached = f"{z.center_price:.6f}"
                    event.destination_gravity = z.gravity
                    event.destination_strength = getattr(z, 'strength', 0)
                    event.destination_time_s = elapsed
                    break

        # Breach: exited in same direction as approach (zone failed to hold)
        if not event.breached:
            if event.approach_direction == "from_above" and event.exit_direction == "downward":
                event.breached = True
            elif event.approach_direction == "from_below" and event.exit_direction == "upward":
                event.breached = True

        if elapsed >= _OUTCOME_WINDOW_SEC:
            self._finalize(coin, event)

    def _finalize(self, coin, event):
        """Move event from active to recent + persist queue."""
        if event.size_samples and event.zone_size_initial > 0:
            event.size_ratio = event.size_samples[-1] / event.zone_size_initial
            if event.min_size_ratio == 0:
                event.min_size_ratio = min(event.size_samples) / event.zone_size_initial

        event.reversal = (
            (event.approach_direction == "from_above" and event.exit_direction == "upward")
            or (event.approach_direction == "from_below" and event.exit_direction == "downward")
        )

        self._recent.append(event)
        self._pending_persist.append(event)
        self._active[coin] = None

    # ── Persistence ──────────────────────────────────────────────────

    def flush_to_db(self):
        """Persist pending events to PG. Called periodically from service.py."""
        if not self._pending_persist:
            return

        from runtime.logging.pg_pool import get_conn, put_conn

        events = list(self._pending_persist)
        self._pending_persist.clear()

        conn = None
        try:
            conn = get_conn()
            cur = conn.cursor()
            for e in events:
                cur.execute("""
                    INSERT INTO gravity_zone_events (
                        event_id, coin, arrival_ts,
                        zone_center, zone_low, zone_high, zone_side,
                        zone_gravity, zone_persistence, zone_size_initial,
                        zone_strength, zone_gravity_rank,
                        arrival_price, approach_direction,
                        of_imbalance_arrival, of_fills_arrival,
                        dest_zones_above, dest_zones_below,
                        path_gravity_above, path_gravity_below,
                        cascade_active,
                        dwell_duration_s, zone_size_samples,
                        size_ratio, min_size_ratio,
                        of_imbalance_exit, of_fills_exit,
                        exit_price, exit_direction, reversal,
                        mfe_30s, mfe_60s, mfe_120s,
                        mae_30s, mae_60s, mae_120s,
                        destination_reached, destination_gravity,
                        destination_strength, destination_time_s,
                        breached, finalized
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1
                    ) ON CONFLICT (event_id) DO NOTHING
                """, (
                    e.event_id, e.coin, e.arrival_ts,
                    e.zone_center, e.zone_low, e.zone_high, e.zone_side,
                    e.zone_gravity, e.zone_persistence, e.zone_size_initial,
                    e.zone_strength, e.zone_gravity_rank,
                    e.arrival_price, e.approach_direction,
                    e.of_imbalance_arrival, e.of_fills_arrival,
                    e.dest_zones_above, e.dest_zones_below,
                    e.path_gravity_above, e.path_gravity_below,
                    1 if e.cascade_active else 0,
                    e.dwell_duration_s, json.dumps(e.size_samples),
                    e.size_ratio, e.min_size_ratio,
                    e.of_imbalance_exit, e.of_fills_exit,
                    e.exit_price, e.exit_direction,
                    1 if e.reversal else 0,
                    e.mfe_30s, e.mfe_60s, e.mfe_120s,
                    e.mae_30s, e.mae_60s, e.mae_120s,
                    e.destination_reached, e.destination_gravity,
                    e.destination_strength, e.destination_time_s,
                    1 if e.breached else 0,
                ))
            conn.commit()
        except Exception as ex:
            print(f"[GRAVITY OBS] DB flush error: {ex}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                put_conn(conn)

    # ── Query API ────────────────────────────────────────────────────

    def get_active_event(self, coin: str) -> Optional[ZoneArrivalEvent]:
        return self._active.get(coin)

    def get_recent_events(self) -> list:
        return list(self._recent)

    def get_pending_count(self) -> int:
        return len(self._pending_persist)
