"""
Market State Emitter

Builds MarketSnapshot from calculator outputs and raw input counters,
maintains per-coin ring buffers, and persists downsampled + event snapshots to PG.

Thread safety: runs entirely on asyncio loop (same thread as regime loop).
Ring buffer reads are O(1) deque operations.
Persistence is batched: _persist() buffers, flush() commits all at once.
"""

import logging
import time
from collections import deque
from typing import Optional, Dict, List

from runtime.market_state.snapshot import MarketSnapshot, SnapshotTrigger

_log = logging.getLogger("MarketStateEmitter")


class MarketStateEmitter:
    """Builds, buffers, and persists market snapshots."""

    RING_SIZE = 300          # ~60s at 5Hz
    DOWNSAMPLE_SEC = 10.0    # Persist periodic snapshots every 10s per coin

    def __init__(self, buffered_db):
        self._db = buffered_db
        # Per-coin ring buffers
        self._rings: Dict[str, deque] = {}
        # Per-coin last periodic persist timestamp
        self._last_persist_ts: Dict[str, float] = {}
        # Per-coin previous snapshot (for event detection)
        self._prev: Dict[str, MarketSnapshot] = {}
        # Batch persistence buffer — flushed once per regime cycle
        self._persist_buffer: List[MarketSnapshot] = []

    def emit(
        self,
        symbol: str,
        trigger: str,
        timestamp: float,
        price: float,
        *,
        # Derived values (passed from regime loop — already computed)
        vwap: Optional[float] = None,
        vwap_distance: Optional[float] = None,
        vwap_z: Optional[float] = None,
        atr_5m: Optional[float] = None,
        atr_30m: Optional[float] = None,
        orderflow_ratio: Optional[float] = None,
        orderflow_fill_count: Optional[int] = None,
        orderflow_neutralized: bool = False,
        liq_z: Optional[float] = None,
        rolling_liq_volume: Optional[float] = None,
        rolling_liq_z: Optional[float] = None,
        regime: Optional[str] = None,
        cascade_state: Optional[str] = None,
        proximity_count: Optional[int] = None,
        proximity_usd_at_risk: Optional[float] = None,
        closest_liq_pct: Optional[float] = None,
        bid_depth_2pct: Optional[float] = None,
        ask_depth_2pct: Optional[float] = None,
        absorption_ratio_longs: Optional[float] = None,
        absorption_ratio_shorts: Optional[float] = None,
        cap_confidence: Optional[float] = None,
        has_position: bool = False,
        position_side: Optional[str] = None,
        # Raw input counters
        feed_age_ms: Optional[int] = None,
        raw_of_fills_60s: Optional[int] = None,
        raw_liq_events_baseline: Optional[int] = None,
        raw_liq_rate_1m: Optional[float] = None,
        raw_burst_count: Optional[int] = None,
        raw_burst_volume: Optional[float] = None,
        raw_rolling_history_count: Optional[int] = None,
        raw_rolling_warmed_up: bool = False,
        raw_l2_age_ms: Optional[int] = None,
        raw_cap_fills: Optional[int] = None,
    ) -> MarketSnapshot:
        """Build snapshot, append to ring buffer, buffer for persistence if due."""

        snap = MarketSnapshot(
            timestamp=timestamp,
            symbol=symbol,
            trigger=trigger,
            price=price,
            vwap=vwap,
            vwap_distance=vwap_distance,
            vwap_z=vwap_z,
            atr_5m=atr_5m,
            atr_30m=atr_30m,
            atr_ratio=(atr_5m / atr_30m) if (atr_5m is not None and atr_30m) else None,
            atr_5m_pct=(atr_5m / price * 100) if (atr_5m is not None and price) else None,
            orderflow_ratio=orderflow_ratio,
            orderflow_fill_count=orderflow_fill_count,
            orderflow_neutralized=orderflow_neutralized,
            liq_z=liq_z,
            rolling_liq_volume=rolling_liq_volume,
            rolling_liq_z=rolling_liq_z,
            regime=regime,
            cascade_state=cascade_state,
            proximity_count=proximity_count,
            proximity_usd_at_risk=proximity_usd_at_risk,
            closest_liq_pct=closest_liq_pct,
            bid_depth_2pct=bid_depth_2pct,
            ask_depth_2pct=ask_depth_2pct,
            absorption_ratio_longs=absorption_ratio_longs,
            absorption_ratio_shorts=absorption_ratio_shorts,
            cap_confidence=cap_confidence,
            has_position=has_position,
            position_side=position_side,
            feed_age_ms=feed_age_ms,
            raw_of_fills_60s=raw_of_fills_60s,
            raw_liq_events_baseline=raw_liq_events_baseline,
            raw_liq_rate_1m=raw_liq_rate_1m,
            raw_burst_count=raw_burst_count,
            raw_burst_volume=raw_burst_volume,
            raw_rolling_history_count=raw_rolling_history_count,
            raw_rolling_warmed_up=raw_rolling_warmed_up,
            raw_l2_age_ms=raw_l2_age_ms,
            raw_cap_fills=raw_cap_fills,
        )

        # Always append to ring buffer
        if symbol not in self._rings:
            self._rings[symbol] = deque(maxlen=self.RING_SIZE)
        self._rings[symbol].append(snap)

        # Detect implicit event triggers from state changes
        prev = self._prev.get(symbol)
        if prev is not None and trigger == SnapshotTrigger.PERIODIC.value:
            # Regime change
            if prev.regime and snap.regime and prev.regime != snap.regime:
                snap = MarketSnapshot(**{
                    **snap.to_dict(),
                    'trigger': SnapshotTrigger.REGIME_CHANGE.value,
                })
                self._persist(snap)
                self._prev[symbol] = snap
                return snap

            # Cascade transition
            if prev.cascade_state and snap.cascade_state and prev.cascade_state != snap.cascade_state:
                snap = MarketSnapshot(**{
                    **snap.to_dict(),
                    'trigger': SnapshotTrigger.CASCADE_TRANSITION.value,
                })
                self._persist(snap)
                self._prev[symbol] = snap
                return snap

            # Liq spike: classical z-score OR rolling z-score crossing threshold
            liq_z_crossed = (
                snap.liq_z is not None and snap.liq_z >= 2.0
                and (prev.liq_z is None or prev.liq_z < 2.0)
            )
            rolling_z_crossed = (
                snap.rolling_liq_z is not None and snap.rolling_liq_z >= 2.0
                and (prev.rolling_liq_z is None or prev.rolling_liq_z < 2.0)
            )
            if liq_z_crossed or rolling_z_crossed:
                snap = MarketSnapshot(**{
                    **snap.to_dict(),
                    'trigger': SnapshotTrigger.LIQ_SPIKE.value,
                })
                self._persist(snap)
                self._prev[symbol] = snap
                return snap

        self._prev[symbol] = snap

        # Persist logic: always persist events, downsample periodic
        if trigger != SnapshotTrigger.PERIODIC.value:
            self._persist(snap)
        else:
            last = self._last_persist_ts.get(symbol, 0)
            if timestamp - last >= self.DOWNSAMPLE_SEC:
                self._persist(snap)
                self._last_persist_ts[symbol] = timestamp

        return snap

    def _persist(self, snap: MarketSnapshot):
        """Buffer snapshot for batch persistence (flushed by flush())."""
        self._persist_buffer.append(snap)

    def flush(self):
        """Flush buffered snapshots to PG in one transaction.

        Called once per regime cycle from service.py, after all symbols emitted.
        Single conn + commit for the whole batch (~2-3 rows typically).
        """
        if not self._persist_buffer:
            return
        batch = self._persist_buffer
        self._persist_buffer = []
        try:
            from runtime.logging.pg_pool import get_conn, put_conn
            conn = get_conn()
            try:
                cur = conn.cursor()
                sql = MarketSnapshot.pg_insert_sql()
                for snap in batch:
                    cur.execute(sql, snap.to_pg_row())
                conn.commit()
            finally:
                put_conn(conn)
        except Exception as e:
            _log.warning(f"Batch persist error ({len(batch)} rows): {e}")

    # ── Ring buffer reads ──

    def get_current(self, symbol: str) -> Optional[MarketSnapshot]:
        """Latest snapshot for a symbol."""
        ring = self._rings.get(symbol)
        if ring:
            return ring[-1]
        return None

    def get_history(self, symbol: str, seconds: float) -> List[MarketSnapshot]:
        """Ring buffer slice for last N seconds."""
        ring = self._rings.get(symbol)
        if not ring:
            return []
        now = time.time()
        cutoff = now - seconds
        return [s for s in ring if s.timestamp >= cutoff]

    def get_all_current(self) -> Dict[str, MarketSnapshot]:
        """Latest snapshot per coin."""
        result = {}
        for symbol, ring in self._rings.items():
            if ring:
                result[symbol] = ring[-1]
        return result
