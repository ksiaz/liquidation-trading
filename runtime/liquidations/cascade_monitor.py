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
    last_z_above_active_ts: float  # last time z >= 1.0
    prev_z: float           # for z_velocity
    prev_ts: float
    # VWAP overextension tracking
    prev_vwap_atr: float = 0.0     # previous vwap/atr ratio for velocity
    peak_vwap_atr: float = 0.0     # max overextension seen
    peak_vwap_atr_ts: float = 0.0  # when overextension peaked
    vwap_peaked: bool = False       # has overextension started declining?
    buffer: List[dict] = field(default_factory=list)


class CascadeLifecycleMonitor:
    """Passive cascade lifecycle recorder."""

    _Z_ACTIVE = 8.0         # z threshold to start recording (burst rate 8x baseline)
    _Z_DONE = 3.0           # z threshold to end recording
    _FADING_RATIO = 0.5     # z < peak * ratio → FADING
    _TIMEOUT_SEC = 120      # end cascade if z hasn't been >= _Z_ACTIVE for this long

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
        vwap_z: float = None,
        atr_5m: float = None,
        atr_30m: float = None,
        orderflow: float = None,
        burst_volume: float = None,
        liq_side: str = None,
        wall_consec_rev: int = None,
        wall_is_ob: bool = None,
        wall_gravity: float = None,
        bid_depth_ratio: float = None,
        rolling_tracker=None,
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
                    last_z_above_active_ts=ts,
                    prev_z=0,
                    prev_ts=ts - 0.2,
                )
                self._states[symbol] = state
                self._append_snapshot(symbol, state, liq_z, price, ts,
                    vwap_distance, vwap_z, atr_5m, atr_30m, orderflow,
                    burst_volume, liq_side, wall_consec_rev,
                    wall_is_ob, wall_gravity, bid_depth_ratio,
                    rolling_tracker)
            return

        # Update peak
        if liq_z > state.peak_z:
            state.peak_z = liq_z
            state.peak_ts = ts

        # Track last time z was above threshold
        if liq_z >= self._Z_ACTIVE:
            state.last_z_above_active_ts = ts

        # Phase transitions
        done = False
        if liq_z < self._Z_DONE:
            done = True
        elif ts - state.last_z_above_active_ts > self._TIMEOUT_SEC:
            done = True

        if done:
            # → DONE: queue for delayed flush (need 5min of future price data for shadow PnL)
            self._pending_flush.append({
                'buffer': state.buffer,
                'done_ts': ts,
                'symbol': symbol,
            })
            del self._states[symbol]
            return

        if state.phase == "ACTIVE" and liq_z < state.peak_z * self._FADING_RATIO:
            state.phase = "FADING"

        # Record snapshot
        self._append_snapshot(symbol, state, liq_z, price, ts,
            vwap_distance, atr_5m, atr_30m, orderflow,
            burst_volume, liq_side, wall_consec_rev,
            wall_is_ob, wall_gravity, bid_depth_ratio,
            rolling_tracker)

        state.prev_z = liq_z
        state.prev_ts = ts
        state.last_z = liq_z

    def _append_snapshot(self, symbol, state, liq_z, price, ts,
                         vwap_distance, vwap_z, atr_5m, atr_30m, orderflow,
                         burst_volume, liq_side, wall_consec_rev,
                         wall_is_ob, wall_gravity, bid_depth_ratio,
                         rolling_tracker=None):
        dt = ts - state.prev_ts if ts > state.prev_ts else 0.2
        # Compute short-window liq rate (5s) for real-time cascade dynamics.
        # get_current_z uses 30s window → stays flat during cascade.
        # 5s rate captures actual rise/peak/fall within the cascade.
        _liq_rate_5s = 0
        if rolling_tracker:
            # Use time.time() not ts — liq events are stamped with time.time()
            # Use 10s window — events are sparse, 5s catches nothing
            _liq_rate_5s = rolling_tracker.get_event_count_in_window(
                symbol, time.time(), window_sec=10.0)
        z_velocity = (liq_z - state.prev_z) / dt if dt > 0 else 0

        # VWAP overextension velocity and peak detection
        _vwap_atr = abs(vwap_distance / atr_30m) if atr_30m and atr_30m > 0 and vwap_distance is not None else 0
        _vwap_atr_velocity = (_vwap_atr - state.prev_vwap_atr) / dt if dt > 0 else 0
        if _vwap_atr > state.peak_vwap_atr:
            state.peak_vwap_atr = _vwap_atr
            state.peak_vwap_atr_ts = ts
            state.vwap_peaked = False
        elif _vwap_atr < state.peak_vwap_atr * 0.9 and not state.vwap_peaked:
            # Overextension dropped 10% from peak — spike is reversing
            state.vwap_peaked = True
        state.prev_vwap_atr = _vwap_atr
        _time_since_vwap_peak = ts - state.peak_vwap_atr_ts if state.peak_vwap_atr_ts > 0 else 0

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
            "vwap_z": round(vwap_z, 2) if vwap_z is not None else None,
            "vwap_atr": round(_vwap_atr, 3),
            "vwap_atr_velocity": round(_vwap_atr_velocity, 3),
            "peak_vwap_atr": round(state.peak_vwap_atr, 3),
            "time_since_vwap_peak": round(_time_since_vwap_peak, 1),
            "vwap_peaked": state.vwap_peaked,
            "atr_5m": atr_5m,
            "atr_30m": atr_30m,
            "orderflow": orderflow,
            "burst_volume": burst_volume,
            "liq_rate_5s": _liq_rate_5s,
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

    _SHADOW_DELAY_SEC = 330  # Wait 5.5min after cascade ends before backfilling
                              # (5min shadow window + 30s buffer for price data arrival)

    def backfill_shadow_pnl(self, symbol: str, price_history: list):
        """Backfill shadow MFE/MAE for pending buffers that are old enough.

        Only processes buffers where 5.5 minutes have passed since cascade end,
        ensuring we have full 1m/2m/5m price data for shadow PnL.

        price_history: list of (ts, price) sorted by ts.
        """
        now = time.time()
        for pending in self._pending_flush:
            if pending.get('_backfilled'):
                continue
            if pending['symbol'] != symbol:
                continue
            if now - pending['done_ts'] < self._SHADOW_DELAY_SEC:
                continue  # Not old enough yet

            buffer = pending['buffer']
            if not buffer:
                pending['_backfilled'] = True
                continue

            # Determine fade direction from cascade price movement
            first = buffer[0]
            last = buffer[-1]
            if last["price"] < first["price_at_start"]:
                fade_dir = "LONG"
            else:
                fade_dir = "SHORT"

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

            pending['_backfilled'] = True

    def flush_to_db(self):
        """Batch insert backfilled buffers to PG. Only flushes after shadow PnL is computed."""
        ready = [p for p in self._pending_flush if p.get('_backfilled')]
        if not ready:
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
                    "vwap_distance", "vwap_z",
                    "vwap_atr", "vwap_atr_velocity", "peak_vwap_atr",
                    "time_since_vwap_peak", "vwap_peaked",
                    "atr_5m", "atr_30m",
                    "orderflow", "burst_volume", "liq_rate_5s", "liq_side",
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
                for pending in ready:
                    for snap in pending['buffer']:
                        rows.append(tuple(snap.get(c) for c in cols))

                if rows:
                    cur.executemany(sql, rows)
                    conn.commit()
                    print(f"[CASCADE MON] Flushed {len(rows)} snapshots "
                          f"from {len(ready)} cascades")

                # Remove flushed from pending
                self._pending_flush = [p for p in self._pending_flush if not p.get('_backfilled')]
            finally:
                put_conn(conn)
        except Exception as e:
            print(f"[CASCADE MON] Flush error: {e}")
