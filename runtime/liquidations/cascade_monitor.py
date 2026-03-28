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
