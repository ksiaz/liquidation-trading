# Cascade Lifecycle Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Passively record every cascade lifecycle at ~200ms resolution with shadow entry PnL, to find the optimal entry point in the z-curve.

**Architecture:** A `CascadeLifecycleMonitor` class tracks per-coin cascade state (QUIET→ACTIVE→FADING→DONE), buffers snapshots in memory during active cascades, backfills shadow MFE/MAE from price history when the cascade ends, and batch-inserts to PG.

**Tech Stack:** Python, PostgreSQL, existing rolling_volume_tracker / liquidity_map / gravity_observer infrastructure.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `runtime/liquidations/cascade_monitor.py` | Create | CascadeLifecycleMonitor class + state machine |
| `runtime/logging/pg_schema.py` | Modify | Add cascade_lifecycle table |
| `runtime/collector/service.py` | Modify | Wire monitor into regime loop + trade linkage |
| `runtime/tests/test_cascade_monitor.py` | Create | Unit tests |
| `scripts/analyze_cascades.py` | Create | Analysis script |

---

### Task 1: PG Schema — cascade_lifecycle table

**Files:**
- Modify: `runtime/logging/pg_schema.py` (before `conn.commit()` at line 1480)

- [ ] **Step 1: Add table creation SQL**

Insert before the final `conn.commit()` at line 1480 in `ensure_schema()`:

```python
    # ── Cascade Lifecycle Monitor (research data collection) ─────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cascade_lifecycle (
            id              BIGSERIAL PRIMARY KEY,
            cascade_id      TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            ts              DOUBLE PRECISION NOT NULL,
            phase           TEXT NOT NULL,
            liq_z           DOUBLE PRECISION,
            peak_z          DOUBLE PRECISION,
            time_since_peak DOUBLE PRECISION,
            z_velocity      DOUBLE PRECISION,
            price           DOUBLE PRECISION,
            price_at_start  DOUBLE PRECISION,
            move_from_start DOUBLE PRECISION,
            vwap_distance   DOUBLE PRECISION,
            atr_5m          DOUBLE PRECISION,
            atr_30m         DOUBLE PRECISION,
            orderflow       DOUBLE PRECISION,
            burst_volume    DOUBLE PRECISION,
            liq_side        TEXT,
            wall_consec_rev SMALLINT,
            wall_is_ob      SMALLINT,
            wall_gravity    DOUBLE PRECISION,
            bid_depth_ratio DOUBLE PRECISION,
            n_coins_active  SMALLINT,
            fade_direction  TEXT,
            shadow_mfe_1m   DOUBLE PRECISION,
            shadow_mfe_2m   DOUBLE PRECISION,
            shadow_mfe_5m   DOUBLE PRECISION,
            shadow_mae_1m   DOUBLE PRECISION,
            shadow_mae_2m   DOUBLE PRECISION,
            shadow_mae_5m   DOUBLE PRECISION,
            trade_id        TEXT
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_lifecycle_cascade_id
        ON cascade_lifecycle(cascade_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_lifecycle_symbol_ts
        ON cascade_lifecycle(symbol, ts)
    """)
```

- [ ] **Step 2: Verify schema creates cleanly**

Run: `python -c "from runtime.logging.pg_schema import ensure_schema; from runtime.logging.pg_pool import init_pool, get_conn, put_conn; init_pool(); c = get_conn(); ensure_schema(c); put_conn(c); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add runtime/logging/pg_schema.py
git commit -m "feat: add cascade_lifecycle table for cascade monitor"
```

---

### Task 2: CascadeLifecycleMonitor — Core Class

**Files:**
- Create: `runtime/liquidations/cascade_monitor.py`
- Test: `runtime/tests/test_cascade_monitor.py`

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_cascade_monitor.py
import pytest
from runtime.liquidations.cascade_monitor import CascadeLifecycleMonitor

class TestCascadeMonitor:
    def test_quiet_no_snapshots(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=0.5, price=70000, ts=1000)
        assert mon.get_phase("BTC") == "QUIET"
        assert mon.get_buffer_size("BTC") == 0

    def test_active_on_z_above_1(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=2.0, price=70000, ts=1000)
        assert mon.get_phase("BTC") == "ACTIVE"
        assert mon.get_buffer_size("BTC") == 1

    def test_tracks_peak_z(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=2.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=5.0, price=69900, ts=1001)
        mon.update("BTC", liq_z=3.0, price=69950, ts=1002)
        state = mon._states["BTC"]
        assert state.peak_z == 5.0
        assert mon.get_buffer_size("BTC") == 3

    def test_fading_when_z_drops_below_half_peak(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=4.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=8.0, price=69800, ts=1001)  # peak
        mon.update("BTC", liq_z=3.0, price=69850, ts=1002)  # < 8*0.5=4 → FADING
        assert mon.get_phase("BTC") == "FADING"

    def test_done_when_z_below_half(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=3.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=0.3, price=69950, ts=1001)  # < 0.5 → DONE
        assert mon.get_phase("BTC") == "QUIET"  # DONE → QUIET immediately

    def test_done_on_timeout(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=3.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=0.8, price=69950, ts=1000 + 121)  # > 120s timeout
        assert mon.get_phase("BTC") == "QUIET"

    def test_snapshot_fields(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=3.0, price=70000, ts=1000,
                   vwap_distance=0.5, atr_5m=100, atr_30m=300,
                   orderflow=0.35, burst_volume=50000, liq_side="LONG")
        buf = mon._states["BTC"].buffer
        snap = buf[0]
        assert snap["liq_z"] == 3.0
        assert snap["price"] == 70000
        assert snap["price_at_start"] == 70000
        assert snap["orderflow"] == 0.35

    def test_n_coins_active(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=3.0, price=70000, ts=1000)
        mon.update("ETH", liq_z=2.0, price=2000, ts=1000)
        mon.update("SOL", liq_z=0.5, price=90, ts=1000)  # quiet
        # BTC snapshot should see 1 other active (ETH), SOL is quiet
        btc_snap = mon._states["BTC"].buffer[-1]
        assert btc_snap["n_coins_active"] == 1

    def test_z_velocity(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=2.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=4.0, price=69900, ts=1001)
        snap = mon._states["BTC"].buffer[-1]
        assert snap["z_velocity"] == pytest.approx(2.0, abs=0.1)  # (4-2) / 1s

    def test_get_active_cascade_id(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=3.0, price=70000, ts=1000)
        cid = mon.get_active_cascade_id("BTC")
        assert cid is not None
        assert mon.get_active_cascade_id("ETH") is None

    def test_flush_returns_buffer(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=3.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=5.0, price=69800, ts=1001)
        mon.update("BTC", liq_z=0.3, price=69850, ts=1002)  # → DONE
        # After DONE, buffer should be in pending_flush
        assert len(mon._pending_flush) > 0
```

- [ ] **Step 2: Run tests — verify fail**

Run: `pytest runtime/tests/test_cascade_monitor.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement CascadeLifecycleMonitor**

```python
# runtime/liquidations/cascade_monitor.py
"""
Cascade Lifecycle Monitor — passive recorder of cascade z-curve dynamics.

Tracks the FULL lifecycle: QUIET → ACTIVE → FADING → DONE
Records every ~200ms snapshot with context (price, OF, L2, multi-coin).
Backfills shadow MFE/MAE from price history when cascade ends.
Persists to PG cascade_lifecycle table for post-hoc analysis.

Spec: docs/superpowers/specs/2026-03-28-cascade-lifecycle-monitor-design.md
"""

import uuid
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class _CascadeState:
    """Per-coin active cascade state."""
    cascade_id: str
    phase: str              # ACTIVE, FADING
    start_ts: float
    start_price: float
    peak_z: float
    peak_ts: float
    last_z: float
    last_z_above_1_ts: float  # last time z >= 1.0
    prev_z: float           # for z_velocity
    prev_ts: float
    buffer: List[dict] = field(default_factory=list)


class CascadeLifecycleMonitor:
    """Passive cascade lifecycle recorder."""

    _Z_ACTIVE = 1.0         # z threshold to start recording
    _Z_DONE = 0.5           # z threshold to end recording
    _FADING_RATIO = 0.5     # z < peak * ratio → FADING
    _TIMEOUT_SEC = 120      # end cascade if z hasn't been >= 1.0 for this long

    def __init__(self):
        self._states: Dict[str, _CascadeState] = {}
        self._pending_flush: List[List[dict]] = []

    def update(
        self,
        symbol: str,
        liq_z: float,
        price: float,
        ts: float,
        vwap_distance: float = None,
        atr_5m: float = None,
        atr_30m: float = None,
        orderflow: float = None,
        burst_volume: float = None,
        liq_side: str = None,
        wall_consec_rev: int = None,
        wall_is_ob: bool = None,
        wall_gravity: float = None,
        bid_depth_ratio: float = None,
    ):
        """Called every regime cycle (~200ms) per coin."""
        state = self._states.get(symbol)

        if state is None:
            # QUIET state
            if liq_z >= self._Z_ACTIVE:
                # → ACTIVE
                state = _CascadeState(
                    cascade_id=str(uuid.uuid4())[:12],
                    phase="ACTIVE",
                    start_ts=ts,
                    start_price=price,
                    peak_z=liq_z,
                    peak_ts=ts,
                    last_z=liq_z,
                    last_z_above_1_ts=ts,
                    prev_z=0,
                    prev_ts=ts - 0.2,
                )
                self._states[symbol] = state
                self._append_snapshot(symbol, state, liq_z, price, ts,
                    vwap_distance, atr_5m, atr_30m, orderflow,
                    burst_volume, liq_side, wall_consec_rev,
                    wall_is_ob, wall_gravity, bid_depth_ratio)
            return

        # Update peak
        if liq_z > state.peak_z:
            state.peak_z = liq_z
            state.peak_ts = ts

        # Track last time z was above threshold
        if liq_z >= self._Z_ACTIVE:
            state.last_z_above_1_ts = ts

        # Phase transitions
        done = False
        if liq_z < self._Z_DONE:
            done = True
        elif ts - state.last_z_above_1_ts > self._TIMEOUT_SEC:
            done = True

        if done:
            # → DONE: finalize and queue for flush
            self._pending_flush.append(state.buffer)
            del self._states[symbol]
            return

        if state.phase == "ACTIVE" and liq_z < state.peak_z * self._FADING_RATIO:
            state.phase = "FADING"

        # Record snapshot
        self._append_snapshot(symbol, state, liq_z, price, ts,
            vwap_distance, atr_5m, atr_30m, orderflow,
            burst_volume, liq_side, wall_consec_rev,
            wall_is_ob, wall_gravity, bid_depth_ratio)

        state.prev_z = liq_z
        state.prev_ts = ts
        state.last_z = liq_z

    def _append_snapshot(self, symbol, state, liq_z, price, ts,
                         vwap_distance, atr_5m, atr_30m, orderflow,
                         burst_volume, liq_side, wall_consec_rev,
                         wall_is_ob, wall_gravity, bid_depth_ratio):
        dt = ts - state.prev_ts if ts > state.prev_ts else 0.2
        z_velocity = (liq_z - state.prev_z) / dt if dt > 0 else 0

        # Count other coins in ACTIVE/FADING
        n_active = sum(1 for s, st in self._states.items()
                       if s != symbol and st.phase in ("ACTIVE", "FADING"))

        move_bps = (price - state.start_price) / state.start_price * 10000 if state.start_price else 0

        state.buffer.append({
            "cascade_id": state.cascade_id,
            "symbol": symbol,
            "ts": ts,
            "phase": state.phase,
            "liq_z": liq_z,
            "peak_z": state.peak_z,
            "time_since_peak": ts - state.peak_ts,
            "z_velocity": round(z_velocity, 3),
            "price": price,
            "price_at_start": state.start_price,
            "move_from_start": round(move_bps, 2),
            "vwap_distance": vwap_distance,
            "atr_5m": atr_5m,
            "atr_30m": atr_30m,
            "orderflow": orderflow,
            "burst_volume": burst_volume,
            "liq_side": liq_side,
            "wall_consec_rev": wall_consec_rev,
            "wall_is_ob": 1 if wall_is_ob else 0 if wall_is_ob is not None else None,
            "wall_gravity": wall_gravity,
            "bid_depth_ratio": bid_depth_ratio,
            "n_coins_active": n_active,
            "fade_direction": None,  # backfilled
            "shadow_mfe_1m": None,
            "shadow_mfe_2m": None,
            "shadow_mfe_5m": None,
            "shadow_mae_1m": None,
            "shadow_mae_2m": None,
            "shadow_mae_5m": None,
            "trade_id": None,
        })

    def get_phase(self, symbol: str) -> str:
        state = self._states.get(symbol)
        return state.phase if state else "QUIET"

    def get_buffer_size(self, symbol: str) -> int:
        state = self._states.get(symbol)
        return len(state.buffer) if state else 0

    def get_active_cascade_id(self, symbol: str) -> Optional[str]:
        state = self._states.get(symbol)
        return state.cascade_id if state else None

    def backfill_shadow_pnl(self, price_history: list):
        """Backfill shadow MFE/MAE for all pending flush buffers.

        price_history: list of (ts, price) sorted by ts.
        Call this before flush_to_db().
        """
        for buffer in self._pending_flush:
            if not buffer:
                continue
            # Determine fade direction from cascade price movement
            first = buffer[0]
            last = buffer[-1]
            if last["price"] < first["price_at_start"]:
                fade_dir = "LONG"  # price fell → fade = buy dip
            else:
                fade_dir = "SHORT"  # price rose → fade = sell top

            for snap in buffer:
                snap["fade_direction"] = fade_dir
                snap_ts = snap["ts"]
                snap_price = snap["price"]

                for window_sec, mfe_key, mae_key in [
                    (60, "shadow_mfe_1m", "shadow_mae_1m"),
                    (120, "shadow_mfe_2m", "shadow_mae_2m"),
                    (300, "shadow_mfe_5m", "shadow_mae_5m"),
                ]:
                    future = [p for t, p in price_history
                              if snap_ts < t <= snap_ts + window_sec]
                    if not future:
                        continue
                    if fade_dir == "LONG":
                        mfe = max((p - snap_price) / snap_price * 10000
                                  for p in future)
                        mae = max((snap_price - p) / snap_price * 10000
                                  for p in future)
                    else:
                        mfe = max((snap_price - p) / snap_price * 10000
                                  for p in future)
                        mae = max((p - snap_price) / snap_price * 10000
                                  for p in future)
                    snap[mfe_key] = round(max(0, mfe), 2)
                    snap[mae_key] = round(max(0, mae), 2)

    def flush_to_db(self):
        """Batch insert all pending buffers to PG. Call periodically."""
        if not self._pending_flush:
            return
        try:
            from runtime.logging.pg_pool import get_conn, put_conn
            conn = get_conn()
            try:
                cur = conn.cursor()
                cols = [
                    "cascade_id", "symbol", "ts", "phase",
                    "liq_z", "peak_z", "time_since_peak", "z_velocity",
                    "price", "price_at_start", "move_from_start",
                    "vwap_distance", "atr_5m", "atr_30m",
                    "orderflow", "burst_volume", "liq_side",
                    "wall_consec_rev", "wall_is_ob", "wall_gravity",
                    "bid_depth_ratio", "n_coins_active",
                    "fade_direction",
                    "shadow_mfe_1m", "shadow_mfe_2m", "shadow_mfe_5m",
                    "shadow_mae_1m", "shadow_mae_2m", "shadow_mae_5m",
                    "trade_id",
                ]
                placeholders = ", ".join(["%s"] * len(cols))
                sql = f"INSERT INTO cascade_lifecycle ({', '.join(cols)}) VALUES ({placeholders})"

                rows = []
                for buffer in self._pending_flush:
                    for snap in buffer:
                        rows.append(tuple(snap.get(c) for c in cols))

                if rows:
                    cur.executemany(sql, rows)
                    conn.commit()
                    print(f"[CASCADE MON] Flushed {len(rows)} snapshots "
                          f"from {len(self._pending_flush)} cascades")

                self._pending_flush.clear()
            finally:
                put_conn(conn)
        except Exception as e:
            print(f"[CASCADE MON] Flush error: {e}")
```

- [ ] **Step 4: Run tests — verify pass**

Run: `pytest runtime/tests/test_cascade_monitor.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/liquidations/cascade_monitor.py runtime/tests/test_cascade_monitor.py
git commit -m "feat: add CascadeLifecycleMonitor for cascade z-curve research"
```

---

### Task 3: Wire Monitor into Service

**Files:**
- Modify: `runtime/collector/service.py`

- [ ] **Step 1: Initialize monitor in `__init__`**

Near other monitor inits (~line 362):

```python
from runtime.liquidations.cascade_monitor import CascadeLifecycleMonitor
self._cascade_monitor = CascadeLifecycleMonitor()
```

- [ ] **Step 2: Call update in regime loop**

After the `check_for_signal` call (~line 1597), add:

```python
                    # Cascade lifecycle monitor — passive research data collection
                    _clm_z = self._rolling_volume_tracker.get_current_z(symbol, timestamp)
                    _clm_price = current_price or self._get_live_price(symbol)
                    _clm_wall = self._gravity_observer.get_wall_status(
                        symbol.replace("USDT", ""),
                        liquidity_map=self._liquidity_map,
                        price=_clm_price)
                    _clm_side = self._rolling_volume_tracker.get_burst_dominant_side(
                        symbol, timestamp)
                    # Bid/ask depth ratio from liquidity map
                    _clm_bid_ratio = None
                    _clm_coin = symbol.replace("USDT", "")
                    if _clm_price and self._liquidity_map.is_warmed_up(_clm_coin):
                        _bid_grav = self._liquidity_map.get_depth_between(
                            _clm_coin, _clm_price * 0.995, _clm_price)
                        _ask_grav = self._liquidity_map.get_depth_between(
                            _clm_coin, _clm_price, _clm_price * 1.005)
                        if _ask_grav > 0:
                            _clm_bid_ratio = round(_bid_grav / _ask_grav, 3)
                    # Burst volume
                    _clm_burst_vol = 0
                    _lb = self._liquidation_burst_aggregator.get_burst(symbol, timestamp)
                    if _lb:
                        _clm_burst_vol = _lb.total_volume
                    self._cascade_monitor.update(
                        symbol=symbol, liq_z=_clm_z, price=_clm_price, ts=timestamp,
                        vwap_distance=regime_metrics.vwap_distance if regime_metrics else None,
                        atr_5m=regime_metrics.atr_5m if regime_metrics else None,
                        atr_30m=regime_metrics.atr_30m if regime_metrics else None,
                        orderflow=regime_metrics.orderflow_imbalance if regime_metrics else None,
                        burst_volume=_clm_burst_vol,
                        liq_side=_clm_side,
                        wall_consec_rev=_clm_wall.consecutive_reversals if _clm_wall else None,
                        wall_is_ob=_clm_wall.is_ob if _clm_wall else None,
                        wall_gravity=_clm_wall.total_gravity if _clm_wall else None,
                        bid_depth_ratio=_clm_bid_ratio,
                    )
```

- [ ] **Step 3: Add periodic flush**

In the regime loop's periodic section (where gravity observer flushes, ~line 1437 area), add:

```python
                    # Backfill shadow PnL and flush cascade monitor
                    _ph = self._price_history.get(symbol)
                    if _ph:
                        self._cascade_monitor.backfill_shadow_pnl(list(_ph))
                    self._cascade_monitor.flush_to_db()
```

- [ ] **Step 4: Add trade linkage at entry**

Where ghost positions are opened (~line 2290), after the `open_position` call succeeds:

```python
                        # Link cascade to trade
                        _cascade_id = self._cascade_monitor.get_active_cascade_id(result.symbol)
                        if _cascade_id and _ctx:
                            _ctx["cascade_id"] = _cascade_id
```

- [ ] **Step 5: Verify compilation and restart**

Run: `python -c "import runtime.collector.service; print('OK')"`
Then: `systemctl --user restart paper-trade.service`
Verify: `tail -20 paper_trade.log` — no errors, look for `[CASCADE MON]` on first cascade

- [ ] **Step 6: Commit**

```bash
git add runtime/collector/service.py
git commit -m "feat: wire CascadeLifecycleMonitor into regime loop"
```

---

### Task 4: Analysis Script

**Files:**
- Create: `scripts/analyze_cascades.py`

- [ ] **Step 1: Create analysis script**

```python
#!/usr/bin/env python3
"""
Analyze cascade lifecycle data from PG.

Usage:
    python scripts/analyze_cascades.py                # all data
    python scripts/analyze_cascades.py --hours 24     # last 24h
    python scripts/analyze_cascades.py --cascade ID   # specific cascade
"""

import argparse
import psycopg2
import time
from collections import defaultdict
from datetime import datetime


def get_conn():
    return psycopg2.connect(
        dbname="liquidation_trading", user="liqtrade",
        password="liqtrade", host="localhost"
    )


def analyze(hours=None, cascade_id=None):
    conn = get_conn()
    cur = conn.cursor()

    where = "WHERE 1=1"
    params = []
    if hours:
        where += " AND ts > %s"
        params.append(time.time() - hours * 3600)
    if cascade_id:
        where += " AND cascade_id = %s"
        params.append(cascade_id)

    # 1. Cascade summary
    cur.execute(f"""
        SELECT cascade_id, symbol, min(ts), max(ts), max(peak_z),
               count(*), min(price_at_start),
               avg(shadow_mfe_5m), avg(shadow_mae_5m)
        FROM cascade_lifecycle {where}
        GROUP BY cascade_id, symbol
        ORDER BY min(ts) DESC
    """, params)

    cascades = cur.fetchall()
    print(f"{'='*80}")
    print(f"Cascade Lifecycle Analysis — {len(cascades)} cascades")
    print(f"{'='*80}\n")

    if not cascades:
        print("No data yet. Wait for cascades to occur.")
        conn.close()
        return

    print(f"{'Time':>14s}  {'Symbol':>10s}  {'PeakZ':>6s}  {'Snaps':>5s}  "
          f"{'Duration':>8s}  {'MFE5m':>7s}  {'MAE5m':>7s}  {'Edge':>7s}")

    for c in cascades[:30]:
        cid, sym, start, end, peak, snaps, start_px, mfe, mae = c
        t = datetime.fromtimestamp(start).strftime('%m-%d %H:%M')
        dur = f"{end - start:.0f}s"
        mfe_s = f"{mfe:+.1f}bp" if mfe is not None else "?"
        mae_s = f"{mae:.1f}bp" if mae is not None else "?"
        edge = f"{(mfe or 0) - (mae or 0):+.1f}bp"
        print(f"{t:>14s}  {sym:>10s}  {peak:>6.1f}  {snaps:>5d}  "
              f"{dur:>8s}  {mfe_s:>7s}  {mae_s:>7s}  {edge:>7s}")

    # 2. Optimal entry point: at what z-level and time-since-peak is MFE maximized?
    cur.execute(f"""
        SELECT
            CASE WHEN liq_z >= 5 THEN '5+'
                 WHEN liq_z >= 3 THEN '3-5'
                 WHEN liq_z >= 2 THEN '2-3'
                 WHEN liq_z >= 1 THEN '1-2'
                 ELSE '<1' END as z_bucket,
            count(*),
            avg(shadow_mfe_5m),
            avg(shadow_mae_5m),
            avg(shadow_mfe_5m) - avg(shadow_mae_5m) as edge
        FROM cascade_lifecycle {where}
          AND shadow_mfe_5m IS NOT NULL
        GROUP BY z_bucket
        ORDER BY edge DESC
    """, params)

    print(f"\n{'─'*40}")
    print(f"Shadow PnL by Z-Level at Entry:")
    print(f"{'Z Bucket':>10s}  {'N':>6s}  {'MFE5m':>7s}  {'MAE5m':>7s}  {'Edge':>7s}")
    for r in cur.fetchall():
        print(f"{r[0]:>10s}  {r[1]:>6d}  {r[2]:>+6.1f}bp  {r[3]:>6.1f}bp  {r[4]:>+6.1f}bp")

    # 3. Optimal entry by time since peak
    cur.execute(f"""
        SELECT
            CASE WHEN time_since_peak < 5 THEN '0-5s'
                 WHEN time_since_peak < 15 THEN '5-15s'
                 WHEN time_since_peak < 30 THEN '15-30s'
                 WHEN time_since_peak < 60 THEN '30-60s'
                 ELSE '60s+' END as delay_bucket,
            count(*),
            avg(shadow_mfe_5m),
            avg(shadow_mae_5m),
            avg(shadow_mfe_5m) - avg(shadow_mae_5m) as edge
        FROM cascade_lifecycle {where}
          AND shadow_mfe_5m IS NOT NULL AND time_since_peak >= 0
        GROUP BY delay_bucket
        ORDER BY edge DESC
    """, params)

    print(f"\n{'─'*40}")
    print(f"Shadow PnL by Time Since Peak Z:")
    print(f"{'Delay':>10s}  {'N':>6s}  {'MFE5m':>7s}  {'MAE5m':>7s}  {'Edge':>7s}")
    for r in cur.fetchall():
        print(f"{r[0]:>10s}  {r[1]:>6d}  {r[2]:>+6.1f}bp  {r[3]:>6.1f}bp  {r[4]:>+6.1f}bp")

    # 4. Multi-coin context
    cur.execute(f"""
        SELECT
            CASE WHEN n_coins_active = 0 THEN 'isolated'
                 WHEN n_coins_active <= 2 THEN '1-2 coins'
                 ELSE '3+ coins' END as multi,
            count(*),
            avg(shadow_mfe_5m) - avg(shadow_mae_5m) as edge
        FROM cascade_lifecycle {where}
          AND shadow_mfe_5m IS NOT NULL
        GROUP BY multi
        ORDER BY edge DESC
    """, params)

    print(f"\n{'─'*40}")
    print(f"Shadow PnL by Multi-Coin Context:")
    print(f"{'Context':>12s}  {'N':>6s}  {'Edge':>7s}")
    for r in cur.fetchall():
        print(f"{r[0]:>12s}  {r[1]:>6d}  {r[2]:>+6.1f}bp")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, help="Look back N hours")
    parser.add_argument("--cascade", type=str, help="Specific cascade ID")
    args = parser.parse_args()
    analyze(hours=args.hours, cascade_id=args.cascade)
```

- [ ] **Step 2: Test script runs**

Run: `python scripts/analyze_cascades.py`
Expected: "No data yet" (table is empty until cascades occur)

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_cascades.py
git commit -m "feat: add cascade lifecycle analysis script"
```

---

## Execution Notes

**Task dependencies:**
- Task 1 (schema) must come first
- Tasks 2 and 4 are independent of each other
- Task 3 depends on Tasks 1 and 2

**Expected data volume:**
- ~200ms per snapshot × ~30s average cascade = ~150 snapshots per cascade
- ~50-100 cascades/day across 20 coins = 7,500-15,000 rows/day
- PG handles this trivially

**Verification after deployment:**
- Wait for a liq burst (or check next morning)
- Run: `python scripts/analyze_cascades.py --hours 12`
- Should see cascades with z-curves, shadow PnL data
