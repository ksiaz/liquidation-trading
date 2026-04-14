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
    # Pulse tracking
    last_pulse_number: int = 0     # last observed pulse count
    # Depth tracking
    start_bid_depth_ratio: float = 0.0  # bid_depth_ratio at cascade start
    buffer: List[dict] = field(default_factory=list)


class CascadeLifecycleMonitor:
    """Passive cascade lifecycle recorder."""

    _Z_ACTIVE = 8.0         # z threshold to start recording (burst rate 8x baseline)
    _Z_DONE = 3.0           # z threshold to end recording
    _FADING_RATIO = 0.5     # z < peak * ratio → FADING
    _TIMEOUT_SEC = 120      # end cascade if z hasn't been >= _Z_ACTIVE for this long
    _MAX_DURATION_SEC = 300  # 5min max — no cascade lasts forever

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
        mtf_vwap_tracker=None,
    ):
        """Called every regime cycle (~200ms) per coin."""
        state = self._states.get(symbol)

        if state is None:
            # QUIET state
            if liq_z >= self._Z_ACTIVE:
                # → ACTIVE
                print(f"[CASCADE MON] {symbol}: QUIET→ACTIVE z={liq_z:.1f} price=${price:,.2f}")
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
                    start_bid_depth_ratio=bid_depth_ratio if bid_depth_ratio is not None else 0.0,
                )
                self._states[symbol] = state
                self._append_snapshot(symbol, state, liq_z, price, ts,
                    vwap_distance, vwap_z, atr_5m, atr_30m, orderflow,
                    burst_volume, liq_side, wall_consec_rev,
                    wall_is_ob, wall_gravity, bid_depth_ratio,
                    rolling_tracker, mtf_vwap_tracker)
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
        elif ts - state.start_ts > self._MAX_DURATION_SEC:
            done = True  # Max duration — prevents infinite ACTIVE when z stays elevated

        if done:
            # → DONE: queue for delayed flush (need 5min of future price data for shadow PnL)
            print(f"[CASCADE MON] {symbol}: →DONE z={liq_z:.1f} snaps={len(state.buffer)} "
                  f"peak_z={state.peak_z:.0f} pending_flush={len(self._pending_flush)}")
            self._pending_flush.append({
                'buffer': state.buffer,
                'done_ts': ts,
                'symbol': symbol,
            })
            del self._states[symbol]
            # Cap pending to prevent memory leak — drop oldest unbackfilled
            if len(self._pending_flush) > self._MAX_PENDING_FLUSH:
                self._pending_flush = self._pending_flush[-self._MAX_PENDING_FLUSH:]
            return

        if state.phase == "ACTIVE" and liq_z < state.peak_z * self._FADING_RATIO:
            state.phase = "FADING"

        # Cap buffer size (200ms × 300s = 1500 max snapshots)
        if len(state.buffer) > 1500:
            done = True

        # Record snapshot
        self._append_snapshot(symbol, state, liq_z, price, ts,
            vwap_distance, vwap_z, atr_5m, atr_30m, orderflow,
            burst_volume, liq_side, wall_consec_rev,
            wall_is_ob, wall_gravity, bid_depth_ratio,
            rolling_tracker, mtf_vwap_tracker)

        state.prev_z = liq_z
        state.prev_ts = ts
        state.last_z = liq_z

    def _append_snapshot(self, symbol, state, liq_z, price, ts,
                         vwap_distance, vwap_z, atr_5m, atr_30m, orderflow,
                         burst_volume, liq_side, wall_consec_rev,
                         wall_is_ob, wall_gravity, bid_depth_ratio,
                         rolling_tracker=None, mtf_vwap_tracker=None):
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

        # Pulse-level stats from rolling tracker
        _pulse_stats = {'time_since_last_liq': 999.0, 'pulse_number': 0,
                        'pulse_liq_count': 0, 'cumulative_liq_usd': 0.0}
        if rolling_tracker:
            _pulse_stats = rolling_tracker.get_pulse_stats(
                symbol, time.time(), state.start_ts)

        # Multi-TF VWAP
        _mtf = {'vwap_5m_atr': None, 'vwap_15m_atr': None, 'vwap_30m_atr': None}
        if mtf_vwap_tracker and atr_30m and atr_30m > 0:
            _mtf = mtf_vwap_tracker.get_multi_tf_vwap(symbol, price, atr_30m)

        # Depth change since cascade start
        _depth_change = None
        if bid_depth_ratio is not None and state.start_bid_depth_ratio > 0:
            _depth_change = round(bid_depth_ratio - state.start_bid_depth_ratio, 4)

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
            "vwap_peaked": 1 if state.vwap_peaked else 0,
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
            "time_since_last_liq": _pulse_stats['time_since_last_liq'],
            "pulse_number": _pulse_stats['pulse_number'],
            "pulse_liq_count": _pulse_stats['pulse_liq_count'],
            "cumulative_liq_usd": _pulse_stats['cumulative_liq_usd'],
            "depth_change": _depth_change,
            "vwap_5m_atr": _mtf.get('vwap_5m_atr'),
            "vwap_15m_atr": _mtf.get('vwap_15m_atr'),
            "vwap_30m_atr": _mtf.get('vwap_30m_atr'),
            "fade_direction": None,  # backfilled
            "shadow_mfe_1m": None,
            "shadow_mfe_2m": None,
            "shadow_mfe_5m": None,
            "shadow_mfe_10m": None,
            "shadow_mfe_15m": None,
            "shadow_mae_1m": None,
            "shadow_mae_2m": None,
            "shadow_mae_5m": None,
            "shadow_mae_10m": None,
            "shadow_mae_15m": None,
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

    _SHADOW_DELAY_SEC = 960  # Wait 16min after cascade ends before backfilling
                              # (15min shadow window + 60s buffer for price data arrival)
    _MAX_PENDING_FLUSH = 50  # Cap pending buffers — drop oldest if exceeded

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
                    (600, "shadow_mfe_10m", "shadow_mae_10m"),
                    (900, "shadow_mfe_15m", "shadow_mae_15m"),
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
                    "time_since_last_liq", "pulse_number",
                    "pulse_liq_count", "cumulative_liq_usd", "depth_change",
                    "vwap_5m_atr", "vwap_15m_atr", "vwap_30m_atr",
                    "fade_direction",
                    "shadow_mfe_1m", "shadow_mfe_2m", "shadow_mfe_5m",
                    "shadow_mfe_10m", "shadow_mfe_15m",
                    "shadow_mae_1m", "shadow_mae_2m", "shadow_mae_5m",
                    "shadow_mae_10m", "shadow_mae_15m",
                    "trade_id",
                ]
                placeholders = ", ".join(["%s"] * len(cols))
                sql = f"INSERT INTO cascade_lifecycle ({', '.join(cols)}) VALUES ({placeholders})"

                rows = []
                for pending in ready:
                    for snap in pending['buffer']:
                        # Sanitize: convert non-primitives to None
                        row = []
                        for c in cols:
                            v = snap.get(c)
                            if v is not None and not isinstance(v, (int, float, str)):
                                v = int(v) if isinstance(v, bool) else None
                            row.append(v)
                        rows.append(tuple(row))

                if rows:
                    flushed = 0
                    for row in rows:
                        try:
                            cur.execute(sql, row)
                            flushed += 1
                        except Exception as row_err:
                            conn.rollback()
                            # Find the bad value
                            for i, (c, v) in enumerate(zip(cols, row)):
                                print(f"[CASCADE MON] col={c} type={type(v).__name__} val={v!r}"[:120])
                            print(f"[CASCADE MON] Row error: {row_err}")
                            break
                    if flushed > 0:
                        conn.commit()
                        print(f"[CASCADE MON] Flushed {flushed}/{len(rows)} snapshots "
                              f"from {len(ready)} cascades")

                # Remove flushed from pending
                self._pending_flush = [p for p in self._pending_flush if not p.get('_backfilled')]
            finally:
                put_conn(conn)
        except Exception as e:
            print(f"[CASCADE MON] Flush error: {e}")
            # Debug: print first row types
            if rows:
                first = rows[0]
                for i, (c, v) in enumerate(zip(cols, first)):
                    if v is not None and isinstance(v, str) and c not in ('cascade_id', 'symbol', 'phase', 'liq_side', 'fade_direction', 'trade_id'):
                        print(f"[CASCADE MON] STRING in numeric col: {c}={v!r}")
