# Gravity Zone Observer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a passive observer that logs every price arrival at an L2 gravity zone, tracks absorption/dwell/outcome, and persists to PG for post-hoc analysis of the "gravity traverse" thesis.

**Architecture:** New `GravityObserver` class in `runtime/liquidations/gravity_observer.py` with a per-coin state machine (IDLE→DWELLING→TRACKING). Called from the regime loop in `service.py`. Persists to a new `gravity_zone_events` PG table. Zero interaction with trading logic.

**Tech Stack:** Python, psycopg2 (via pg_pool), dataclasses, json for array serialization.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `runtime/liquidations/gravity_observer.py` | Observer class: state machine, zone arrival detection, outcome tracking, PG persistence |
| Modify | `runtime/logging/pg_schema.py:1410-1412` | Add `gravity_zone_events` table DDL |
| Modify | `runtime/collector/service.py:334,1488` | Instantiate observer, call from regime loop |
| Create | `runtime/tests/test_gravity_observer.py` | Unit tests for state machine and zone matching |

---

## Chunk 1: Core Observer

### Task 1: PG Table Schema

**Files:**
- Modify: `runtime/logging/pg_schema.py:1406-1412`

- [ ] **Step 1: Add gravity_zone_events table DDL**

Insert before the final `conn.commit()` in `ensure_schema()`. Add after the `idx_ghost_trades_trade_id_unique` block (line 1409):

```python
    # ── Gravity Zone Observer (research data collection) ─────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gravity_zone_events (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT NOT NULL,
            coin TEXT NOT NULL,
            arrival_ts DOUBLE PRECISION NOT NULL,

            -- Zone snapshot at arrival
            zone_center DOUBLE PRECISION NOT NULL,
            zone_low DOUBLE PRECISION NOT NULL,
            zone_high DOUBLE PRECISION NOT NULL,
            zone_side TEXT NOT NULL,
            zone_gravity DOUBLE PRECISION NOT NULL,
            zone_persistence DOUBLE PRECISION NOT NULL,
            zone_size_initial DOUBLE PRECISION NOT NULL,

            -- Arrival context
            arrival_price DOUBLE PRECISION NOT NULL,
            approach_direction TEXT NOT NULL,
            of_imbalance_arrival DOUBLE PRECISION,
            of_fills_arrival INTEGER,

            -- Destination candidates (JSON arrays)
            dest_zones_above TEXT,
            dest_zones_below TEXT,
            path_gravity_above DOUBLE PRECISION,
            path_gravity_below DOUBLE PRECISION,
            cascade_active SMALLINT DEFAULT 0,

            -- Dwell phase (updated at finalization)
            dwell_duration_s DOUBLE PRECISION,
            zone_size_samples TEXT,
            size_ratio DOUBLE PRECISION,
            min_size_ratio DOUBLE PRECISION,
            of_imbalance_exit DOUBLE PRECISION,
            of_fills_exit INTEGER,

            -- Outcome (updated at finalization)
            exit_price DOUBLE PRECISION,
            exit_direction TEXT,
            reversal SMALLINT,
            mfe_30s DOUBLE PRECISION,
            mfe_60s DOUBLE PRECISION,
            mfe_120s DOUBLE PRECISION,
            mae_30s DOUBLE PRECISION,
            mae_60s DOUBLE PRECISION,
            mae_120s DOUBLE PRECISION,
            destination_reached TEXT,
            destination_gravity DOUBLE PRECISION,
            destination_time_s DOUBLE PRECISION,
            breached SMALLINT,

            finalized SMALLINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_gravity_zone_events_coin_ts
        ON gravity_zone_events(coin, arrival_ts)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_gravity_zone_events_event_id
        ON gravity_zone_events(event_id)
    """)
```

- [ ] **Step 2: Verify schema applies cleanly**

Run:
```bash
cd /home/ksiaz/liquidation-trading && python3 -c "
from runtime.logging.pg_pool import init_pool, get_conn, put_conn
from runtime.logging.pg_schema import ensure_schema
init_pool()
conn = get_conn()
ensure_schema(conn)
put_conn(conn)
print('OK')
"
```
Expected: `OK` with no errors.

- [ ] **Step 3: Commit**

```bash
git add runtime/logging/pg_schema.py
git commit -m "feat(gravity-observer): add gravity_zone_events PG table"
```

---

### Task 2: Observer Core — Data Model and State Machine

**Files:**
- Create: `runtime/liquidations/gravity_observer.py`
- Create: `runtime/tests/test_gravity_observer.py`

- [ ] **Step 1: Write test for zone arrival detection**

Create `runtime/tests/test_gravity_observer.py`:

```python
"""Tests for GravityObserver zone arrival detection and state machine."""
import pytest
from unittest.mock import MagicMock
from runtime.liquidations.gravity_observer import GravityObserver
from runtime.liquidations.liquidity_map import LiquidityZone


def _make_zone(center, side="bid", gravity=10000, persistence=0.8,
               current_size=50000):
    """Helper to create a LiquidityZone for testing."""
    band_w = center * 10 / 10000  # 10bp band
    return LiquidityZone(
        center_price=center,
        band_low=center - band_w / 2,
        band_high=center + band_w / 2,
        side=side,
        gravity=gravity,
        persistence=persistence,
        avg_size_usd=gravity / max(persistence, 0.01),
        max_size_usd=gravity / max(persistence, 0.01) * 1.5,
        samples_seen=int(persistence * 100),
        total_samples=100,
        current_size_usd=current_size,
    )


def _mock_liq_map(zones):
    """Create a mock LiquidityMap returning given zones."""
    m = MagicMock()
    m.get_zones.return_value = zones
    m.is_warmed_up.return_value = True

    def _zones_above(coin, price, min_gravity=0):
        return sorted(
            [z for z in zones if z.side == "ask" and z.center_price > price
             and z.gravity >= min_gravity],
            key=lambda z: z.gravity, reverse=True
        )

    def _zones_below(coin, price, min_gravity=0):
        return sorted(
            [z for z in zones if z.side == "bid" and z.center_price < price
             and z.gravity >= min_gravity],
            key=lambda z: z.gravity, reverse=True
        )

    m.get_zones_above.side_effect = _zones_above
    m.get_zones_below.side_effect = _zones_below
    m.get_depth_between.return_value = 5000.0
    return m


def _mock_of_calc(imbalance=0.5, fills=20):
    m = MagicMock()
    m.get_imbalance_60s.return_value = imbalance
    m.get_fill_count_60s.return_value = fills
    return m


class TestZoneArrival:
    """Test IDLE → DWELLING transition."""

    def test_no_arrival_when_price_outside_zones(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        # Price far from zone
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        assert obs.get_active_event("BTC") is None

    def test_arrival_when_price_enters_zone(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        # Price above zone first
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        # Price enters zone band
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)

        event = obs.get_active_event("BTC")
        assert event is not None
        assert event.state == "DWELLING"
        assert event.approach_direction == "from_above"

    def test_no_arrival_below_min_gravity(self):
        obs = GravityObserver(min_obs_gravity=20000)
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        assert obs.get_active_event("BTC") is None

    def test_picks_strongest_zone_when_overlapping(self):
        obs = GravityObserver()
        weak = _make_zone(70000, side="bid", gravity=5000)
        strong = _make_zone(70003, side="bid", gravity=50000)
        lm = _mock_liq_map([weak, strong])
        of = _mock_of_calc()

        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70002, 1001.0, lm, of)

        event = obs.get_active_event("BTC")
        assert event is not None
        assert event.zone_gravity == 50000


class TestDwellToTracking:
    """Test DWELLING → TRACKING transition."""

    def test_exits_to_tracking_when_price_leaves_zone(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        # Enter zone from above
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        assert obs.get_active_event("BTC").state == "DWELLING"

        # Leave zone upward (reversal)
        obs.on_price_update("BTC", 71000, 1010.0, lm, of)
        event = obs.get_active_event("BTC")
        assert event.state == "TRACKING"
        assert event.exit_direction == "upward"
        assert event.dwell_duration_s == pytest.approx(9.0, abs=0.1)

    def test_reentry_within_10s_continues_dwell(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        # Brief exit
        obs.on_price_update("BTC", 71000, 1005.0, lm, of)
        # Re-enter within 10s
        obs.on_price_update("BTC", 70000, 1008.0, lm, of)

        event = obs.get_active_event("BTC")
        assert event.state == "DWELLING"


class TestOutcomeTracking:
    """Test TRACKING → finalized."""

    def test_finalized_after_120s(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        obs.on_price_update("BTC", 70100, 1005.0, lm, of)  # exit zone
        # 121s later
        obs.on_price_update("BTC", 70200, 1005.0 + 121, lm, of)

        assert obs.get_active_event("BTC") is None
        assert len(obs.get_recent_events()) == 1

    def test_mfe_mae_tracked(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        ask_zone = _make_zone(70200, side="ask", gravity=15000)
        lm = _mock_liq_map([zone, ask_zone])
        of = _mock_of_calc()

        # Approach from above, bounce up
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        obs.on_price_update("BTC", 70100, 1003.0, lm, of)  # exit upward @ 70100

        # Track outcome: price goes to 70300 (favorable) then back to 70050
        obs.on_price_update("BTC", 70300, 1010.0, lm, of)
        obs.on_price_update("BTC", 70050, 1040.0, lm, of)

        event = obs.get_active_event("BTC")
        assert event is not None
        # MFE should reflect 70300 vs exit 70100 = +200/70100*10000 ≈ +28.5bp
        assert event.highest_since_exit == 70300
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ksiaz/liquidation-trading && python3 -m pytest runtime/tests/test_gravity_observer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'runtime.liquidations.gravity_observer'`

- [ ] **Step 3: Write gravity_observer.py — data model and state machine**

Create `runtime/liquidations/gravity_observer.py`:

```python
"""
Gravity Zone Observer — passive data collection for zone-to-zone traverse research.

Watches price arrivals at L2 gravity zones, tracks dwell/absorption/outcome,
persists to PG for post-hoc analysis. No trading logic.

Called from regime loop in service.py once per coin per cycle (~200ms).
"""

import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from runtime.liquidations.liquidity_map import LiquidityMap, LiquidityZone


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
    last_sample_ts: float = 0.0
    of_imbalance_exit: float = 0.0
    of_fills_exit: int = 0

    # Outcome tracking
    highest_since_exit: float = 0.0
    lowest_since_exit: float = 0.0
    mfe_30s: float = 0.0
    mfe_60s: float = 0.0
    mfe_120s: float = 0.0
    mae_30s: float = 0.0
    mae_60s: float = 0.0
    mae_120s: float = 0.0
    destination_reached: Optional[str] = None
    destination_gravity: Optional[float] = None
    destination_time_s: Optional[float] = None
    breached: bool = False

    # Internal
    _brief_exit_ts: float = 0.0  # for 10s re-entry grace


# ── Size sampling interval (match LiquidityMap) ─────────────────────
_SIZE_SAMPLE_INTERVAL = 5.0
_REENTRY_GRACE_SEC = 10.0
_OUTCOME_WINDOW_SEC = 120.0


class GravityObserver:
    """Passive observer of price behavior at L2 gravity zones."""

    def __init__(self, min_obs_gravity: float = 5000):
        self._min_gravity = min_obs_gravity
        self._active: Dict[str, Optional[ZoneArrivalEvent]] = {}
        self._last_price: Dict[str, float] = {}
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
            # IDLE — check for new zone arrival
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
            return

        # Find strongest zone that price is inside
        hit_zone = None
        for z in zones:  # already sorted by gravity desc
            if z.band_low <= price <= z.band_high:
                # Was price outside this zone last cycle?
                if not (z.band_low <= prev_price <= z.band_high):
                    hit_zone = z
                    break

        if hit_zone is None:
            return

        direction = "from_above" if prev_price > hit_zone.band_high else "from_below"

        # Snapshot destination candidates
        above = liq_map.get_zones_above(coin, price, min_gravity=self._min_gravity)
        below = liq_map.get_zones_below(coin, price, min_gravity=self._min_gravity)

        dest_above = json.dumps([
            {"center": round(z.center_price, 6), "gravity": round(z.gravity, 1),
             "distance_bps": round(abs(z.center_price - price) / price * 10000, 1)}
            for z in sorted(above, key=lambda x: x.center_price)[:3]
        ])
        dest_below = json.dumps([
            {"center": round(z.center_price, 6), "gravity": round(z.gravity, 1),
             "distance_bps": round(abs(z.center_price - price) / price * 10000, 1)}
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
                return  # grace period — might re-enter

            # Confirmed exit → TRACKING
            event.state = "TRACKING"
            event.zone_exit_ts = event._brief_exit_ts
            event.exit_price = price
            event.dwell_duration_s = event._brief_exit_ts - event.arrival_ts
            event.exit_direction = "upward" if price > event.zone_center else "downward"
            event.highest_since_exit = price
            event.lowest_since_exit = price

            # Snapshot orderflow at exit
            if of_calc:
                event.of_imbalance_exit = of_calc.get_imbalance_60s() or 0.0
                event.of_fills_exit = getattr(of_calc, 'get_fill_count_60s', lambda: 0)()

            # Compute size ratio
            if event.size_samples and event.zone_size_initial > 0:
                event.min_size_ratio = min(event.size_samples) / event.zone_size_initial

    def _update_tracking(self, coin, price, ts, liq_map):
        """Update TRACKING state. Compute MFE/MAE. Finalize after 120s."""
        event = self._active[coin]

        # Update extremes
        event.highest_since_exit = max(event.highest_since_exit, price)
        event.lowest_since_exit = min(event.lowest_since_exit, price)

        elapsed = ts - event.zone_exit_ts
        ep = event.exit_price

        # Compute MFE/MAE based on exit direction (favorable = direction of exit)
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
                if z.center_price == event.zone_center and z.side == event.zone_side:
                    continue  # skip departure zone
                if z.band_low <= price <= z.band_high:
                    event.destination_reached = f"{z.center_price:.6f}"
                    event.destination_gravity = z.gravity
                    event.destination_time_s = elapsed
                    break

        # Check breach: price went through zone and continued
        if not event.breached:
            if event.approach_direction == "from_above" and event.exit_direction == "downward":
                event.breached = True
            elif event.approach_direction == "from_below" and event.exit_direction == "upward":
                event.breached = True

        # Finalize after 120s
        if elapsed >= _OUTCOME_WINDOW_SEC:
            self._finalize(coin, event)

        # Also finalize if price arrives at a new zone (starts new event)
        # This is handled by: finalize current → set active to None → next
        # cycle _check_arrival fires for the new zone

    def _finalize(self, coin, event):
        """Move event from active to recent + persist queue."""
        # Compute final size ratio
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
                        destination_reached, destination_gravity, destination_time_s,
                        breached, finalized
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, 1
                    ) ON CONFLICT (event_id) DO NOTHING
                """, (
                    e.event_id, e.coin, e.arrival_ts,
                    e.zone_center, e.zone_low, e.zone_high, e.zone_side,
                    e.zone_gravity, e.zone_persistence, e.zone_size_initial,
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
                    e.destination_reached, e.destination_gravity, e.destination_time_s,
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

    # ── Query API (for tests and monitoring) ─────────────────────────

    def get_active_event(self, coin: str) -> Optional[ZoneArrivalEvent]:
        return self._active.get(coin)

    def get_recent_events(self) -> list:
        return list(self._recent)

    def get_pending_count(self) -> int:
        return len(self._pending_persist)
```

- [ ] **Step 4: Run tests**

Run: `cd /home/ksiaz/liquidation-trading && python3 -m pytest runtime/tests/test_gravity_observer.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add runtime/liquidations/gravity_observer.py runtime/tests/test_gravity_observer.py
git commit -m "feat(gravity-observer): core observer with state machine and tests"
```

---

### Task 3: MFE/MAE Window Tests

**Files:**
- Modify: `runtime/tests/test_gravity_observer.py`

- [ ] **Step 1: Add MFE/MAE window boundary tests**

Append to `test_gravity_observer.py`:

```python
class TestMfeMaeWindows:
    """Verify MFE/MAE computed correctly per time window."""

    def _setup_tracking_event(self):
        """Helper: create observer with event in TRACKING state."""
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        obs.on_price_update("BTC", 71000, 1000.0, lm, of)  # prev price
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)  # enter zone
        obs.on_price_update("BTC", 70100, 1012.0, lm, of)  # exit zone (after grace)
        return obs, lm, of

    def test_mfe_30s_window(self):
        obs, lm, _ = self._setup_tracking_event()
        event = obs.get_active_event("BTC")
        exit_ts = event.zone_exit_ts

        # Big move within 30s
        obs.on_price_update("BTC", 70500, exit_ts + 20, lm, None)
        event = obs.get_active_event("BTC")
        assert event.mfe_30s > 0

        # After 30s window, mfe_30s should not increase further
        old_mfe_30 = event.mfe_30s
        obs.on_price_update("BTC", 71000, exit_ts + 40, lm, None)
        event = obs.get_active_event("BTC")
        assert event.mfe_30s == old_mfe_30  # frozen
        assert event.mfe_60s > old_mfe_30   # still updating

    def test_reversal_flag(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        # Enter from above, exit upward = reversal
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        obs.on_price_update("BTC", 70200, 1012.0, lm, of)

        # Finalize
        obs.on_price_update("BTC", 70300, 1012.0 + 121, lm, of)

        events = obs.get_recent_events()
        assert len(events) == 1
        assert events[0].reversal is True

    def test_breach_flag(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()

        # Enter from above, exit downward = breach
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        obs.on_price_update("BTC", 69800, 1012.0, lm, of)

        # Finalize
        obs.on_price_update("BTC", 69700, 1012.0 + 121, lm, of)

        events = obs.get_recent_events()
        assert len(events) == 1
        assert events[0].breached is True
        assert events[0].reversal is False
```

- [ ] **Step 2: Run tests**

Run: `cd /home/ksiaz/liquidation-trading && python3 -m pytest runtime/tests/test_gravity_observer.py -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add runtime/tests/test_gravity_observer.py
git commit -m "test(gravity-observer): add MFE/MAE window and reversal/breach tests"
```

---

## Chunk 2: Service Integration

### Task 4: Wire into service.py

**Files:**
- Modify: `runtime/collector/service.py:334,1488`

- [ ] **Step 1: Add import and instantiation**

In `service.py`, add import near line 48 (next to LiquidityMap import):

```python
from runtime.liquidations.gravity_observer import GravityObserver
```

Add instantiation near line 334 (next to `self._liquidity_map = LiquidityMap()`):

```python
        self._gravity_observer = GravityObserver()
```

- [ ] **Step 2: Add observer call in regime loop**

After line 1488 (`self._check_gravity_tp_targets(symbol, price)`), add:

```python
                    # Gravity zone observer — passive data collection
                    self._gravity_observer.on_price_update(
                        hl_symbol, price, timestamp,
                        self._liquidity_map,
                        self._orderflow_calculators.get(symbol),
                    )
```

- [ ] **Step 3: Add periodic flush**

Find the cleanup/periodic section of the regime loop (after the per-symbol loop). Add the flush call. Look for the data freshness gate section (~line 1496):

```python
            # Flush gravity observer events to DB (low frequency, after all symbols processed)
            self._gravity_observer.flush_to_db()
```

- [ ] **Step 4: Add cascade_active tagging**

In the observer call (step 2), pass cascade status. Change the call to:

```python
                    # Gravity zone observer — passive data collection
                    _grav_obs_event = self._gravity_observer.get_active_event(hl_symbol)
                    if _grav_obs_event and not _grav_obs_event.cascade_active:
                        _grav_obs_event.cascade_active = bool(
                            self.ghost_tracker.get_open_position(symbol)
                        )
                    self._gravity_observer.on_price_update(
                        hl_symbol, price, timestamp,
                        self._liquidity_map,
                        self._orderflow_calculators.get(symbol),
                    )
```

- [ ] **Step 5: Verify service starts cleanly**

Run:
```bash
cd /home/ksiaz/liquidation-trading && python3 -c "
from runtime.collector.service import CollectorService
print('Import OK')
"
```
Expected: `Import OK`

- [ ] **Step 6: Commit**

```bash
git add runtime/collector/service.py
git commit -m "feat(gravity-observer): wire into regime loop for passive data collection"
```

---

### Task 5: Deploy and Verify

- [ ] **Step 1: Restart paper trade service**

```bash
systemctl --user restart paper-trade.service
```

- [ ] **Step 2: Verify observer is running (after ~5 min warmup)**

```bash
python3 -c "
import psycopg2
conn = psycopg2.connect(dbname='liquidation_trading', user='liqtrade', password='liqtrade', host='localhost')
cur = conn.cursor()
cur.execute('SELECT COUNT(*), COUNT(DISTINCT coin) FROM gravity_zone_events')
count, coins = cur.fetchone()
print(f'Events: {count}, Coins: {coins}')
cur.execute('SELECT coin, COUNT(*) FROM gravity_zone_events GROUP BY coin ORDER BY count DESC LIMIT 10')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')
conn.close()
"
```
Expected: Events increasing over time, multiple coins represented.

- [ ] **Step 3: Check service logs for errors**

```bash
tail -50 /home/ksiaz/liquidation-trading/paper_trade.log | grep -i "gravity\|error"
```
Expected: No errors related to gravity observer.

- [ ] **Step 4: Commit any fixes if needed**
