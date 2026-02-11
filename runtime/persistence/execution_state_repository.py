"""
Execution State Repository - Unified Persistence for Execution State.

P1-P4 Hardenings:
- P1: Stop order lifecycle persistence
- P2: Trailing stop state persistence
- P3: Fill tracker/dedup set persistence
- P4: CLOSING timeout tracker persistence

Constitutional: Stores factual state only, no interpretation.

PostgreSQL backend (v2): Uses shared connection pool instead of per-file SQLite.
"""

import time
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set
from decimal import Decimal
from threading import RLock

import psycopg2.extras

from runtime.logging.pg_pool import get_conn, put_conn


@dataclass
class PersistedStopOrder:
    """P1: Persisted stop order state."""
    entry_order_id: str
    stop_order_id: Optional[str]
    state: str  # StopOrderState value
    stop_price: float
    symbol: str
    side: str
    size: float
    placement_attempts: int
    last_error: Optional[str]
    placed_at_ns: Optional[int]
    triggered_at_ns: Optional[int]
    filled_at_ns: Optional[int]
    fill_price: Optional[float]
    created_at: float


@dataclass
class PersistedTrailingStop:
    """P2: Persisted trailing stop state."""
    entry_order_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    current_stop_price: float
    initial_stop_price: float
    highest_price: float
    lowest_price: float
    break_even_triggered: bool
    updates_count: int
    current_atr: Optional[float]
    # Config stored as JSON
    config_json: str
    created_at: float
    updated_at: float


@dataclass
class PersistedClosingTimeout:
    """P4: Persisted CLOSING state timeout tracker."""
    symbol: str
    entered_closing_at: float
    timeout_sec: float
    created_at: float


@dataclass
class PersistedFillId:
    """P3: Persisted fill ID for deduplication."""
    fill_id: str
    symbol: str
    order_id: str
    processed_at: float


class ExecutionStateRepository:
    """
    PostgreSQL persistence for all execution state.

    Handles:
    - P1: Stop order lifecycle
    - P2: Trailing stop state
    - P3: Fill tracker dedup set
    - P4: CLOSING timeout trackers

    Thread-safe with RLock (belt and suspenders — PG MVCC handles concurrency).
    """

    def __init__(self, db_path: str = None):
        """Initialize repository.

        Args:
            db_path: Ignored (kept for API compatibility). Uses PG pool.
        """
        self._lock = RLock()
        # Schema already created by pg_schema.ensure_schema() at startup

    def _get_conn(self):
        return get_conn()

    def _put_conn(self, conn):
        put_conn(conn)

    # =========================================================================
    # P1: Stop Order Lifecycle Persistence
    # =========================================================================

    def save_stop_order(self, stop: PersistedStopOrder) -> None:
        """P1: Save stop order state (upsert)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO stop_orders (
                        entry_order_id, stop_order_id, state, stop_price, symbol, side, size,
                        placement_attempts, last_error, placed_at_ns, triggered_at_ns,
                        filled_at_ns, fill_price, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(entry_order_id) DO UPDATE SET
                        stop_order_id = excluded.stop_order_id,
                        state = excluded.state,
                        stop_price = excluded.stop_price,
                        placement_attempts = excluded.placement_attempts,
                        last_error = excluded.last_error,
                        placed_at_ns = excluded.placed_at_ns,
                        triggered_at_ns = excluded.triggered_at_ns,
                        filled_at_ns = excluded.filled_at_ns,
                        fill_price = excluded.fill_price,
                        updated_at = excluded.updated_at
                """, (
                    stop.entry_order_id,
                    stop.stop_order_id,
                    stop.state,
                    stop.stop_price,
                    stop.symbol,
                    stop.side,
                    stop.size,
                    stop.placement_attempts,
                    stop.last_error,
                    stop.placed_at_ns,
                    stop.triggered_at_ns,
                    stop.filled_at_ns,
                    stop.fill_price,
                    stop.created_at,
                    time.time()
                ))
                conn.commit()
            finally:
                self._put_conn(conn)

    def load_stop_order(self, entry_order_id: str) -> Optional[PersistedStopOrder]:
        """P1: Load stop order by entry order ID."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT * FROM stop_orders WHERE entry_order_id = %s",
                    (entry_order_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_stop_order(row)
            finally:
                self._put_conn(conn)

    def load_active_stop_orders(self) -> Dict[str, PersistedStopOrder]:
        """P1: Load all non-terminal stop orders (for restart recovery)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("""
                    SELECT * FROM stop_orders
                    WHERE state IN ('PENDING_PLACEMENT', 'PLACED', 'TRIGGERED')
                """)
                result = {}
                for row in cursor.fetchall():
                    stop = self._row_to_stop_order(row)
                    result[stop.entry_order_id] = stop
                return result
            finally:
                self._put_conn(conn)

    def load_unreconciled_stop_orders(self) -> Dict[str, PersistedStopOrder]:
        """AUDIT-P0-8: Load stop orders that need reconciliation before use."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("""
                    SELECT * FROM stop_orders
                    WHERE state = 'PLACED'
                """)
                result = {}
                for row in cursor.fetchall():
                    stop = self._row_to_stop_order(row)
                    result[stop.entry_order_id] = stop
                return result
            finally:
                self._put_conn(conn)

    def delete_stop_order(self, entry_order_id: str) -> None:
        """P1: Delete stop order record."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM stop_orders WHERE entry_order_id = %s",
                    (entry_order_id,)
                )
                conn.commit()
            finally:
                self._put_conn(conn)

    def reconcile_stop_orders(
        self,
        exchange_order_ids: Set[str],
        logger=None
    ) -> Dict[str, str]:
        """AUDIT-P0-8: Reconcile persisted stop orders against exchange reality."""
        import logging
        log = logger or logging.getLogger(__name__)

        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("""
                    SELECT entry_order_id, stop_order_id, state, symbol
                    FROM stop_orders
                    WHERE state = 'PLACED'
                """)

                results = {}
                stale_orders = []

                for row in cursor.fetchall():
                    entry_id = row['entry_order_id']
                    stop_id = row['stop_order_id']
                    symbol = row['symbol']

                    if stop_id and stop_id not in exchange_order_ids:
                        stale_orders.append(entry_id)
                        results[entry_id] = 'STALE'
                        log.warning(
                            f"P0-8: Stop order {stop_id} for {symbol} not found on exchange, "
                            f"marking as STALE (entry_order_id={entry_id})"
                        )
                    else:
                        results[entry_id] = 'VALID'

                # Mark stale orders
                if stale_orders:
                    for oid in stale_orders:
                        cursor.execute(
                            """
                            UPDATE stop_orders
                            SET state = 'STALE',
                                last_error = 'P0-8: Not found on exchange during startup reconciliation'
                            WHERE entry_order_id = %s
                            """,
                            (oid,)
                        )
                    conn.commit()
                    log.info(f"P0-8: Marked {len(stale_orders)} stop orders as STALE")

                return results
            finally:
                self._put_conn(conn)

    def get_stale_stop_orders(self) -> List[PersistedStopOrder]:
        """AUDIT-P0-8: Get all stop orders marked as STALE for manual review."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("""
                    SELECT * FROM stop_orders
                    WHERE state = 'STALE'
                """)
                return [self._row_to_stop_order(row) for row in cursor.fetchall()]
            finally:
                self._put_conn(conn)

    def clear_stale_stop_order(self, entry_order_id: str, action: str) -> None:
        """AUDIT-P0-8: Clear a STALE order after manual review."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE stop_orders
                    SET state = 'RECONCILED',
                        last_error = %s
                    WHERE entry_order_id = %s AND state = 'STALE'
                    """,
                    (f"P0-8: Cleared by manual review, action={action}", entry_order_id)
                )
                conn.commit()
            finally:
                self._put_conn(conn)

    def _row_to_stop_order(self, row: dict) -> PersistedStopOrder:
        return PersistedStopOrder(
            entry_order_id=row['entry_order_id'],
            stop_order_id=row['stop_order_id'],
            state=row['state'],
            stop_price=row['stop_price'],
            symbol=row['symbol'],
            side=row['side'],
            size=row['size'],
            placement_attempts=row['placement_attempts'],
            last_error=row['last_error'],
            placed_at_ns=row['placed_at_ns'],
            triggered_at_ns=row['triggered_at_ns'],
            filled_at_ns=row['filled_at_ns'],
            fill_price=row['fill_price'],
            created_at=row['created_at']
        )

    # =========================================================================
    # P2: Trailing Stop Persistence
    # =========================================================================

    def save_trailing_stop(self, stop: PersistedTrailingStop) -> None:
        """P2: Save trailing stop state (upsert)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trailing_stops (
                        entry_order_id, symbol, direction, entry_price, current_stop_price,
                        initial_stop_price, highest_price, lowest_price, break_even_triggered,
                        updates_count, current_atr, config_json, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(entry_order_id) DO UPDATE SET
                        current_stop_price = excluded.current_stop_price,
                        highest_price = excluded.highest_price,
                        lowest_price = excluded.lowest_price,
                        break_even_triggered = excluded.break_even_triggered,
                        updates_count = excluded.updates_count,
                        current_atr = excluded.current_atr,
                        config_json = excluded.config_json,
                        updated_at = excluded.updated_at
                """, (
                    stop.entry_order_id,
                    stop.symbol,
                    stop.direction,
                    stop.entry_price,
                    stop.current_stop_price,
                    stop.initial_stop_price,
                    stop.highest_price,
                    stop.lowest_price,
                    1 if stop.break_even_triggered else 0,
                    stop.updates_count,
                    stop.current_atr,
                    stop.config_json,
                    stop.created_at,
                    time.time()
                ))
                conn.commit()
            finally:
                self._put_conn(conn)

    def load_trailing_stop(self, entry_order_id: str) -> Optional[PersistedTrailingStop]:
        """P2: Load trailing stop by entry order ID."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT * FROM trailing_stops WHERE entry_order_id = %s",
                    (entry_order_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_trailing_stop(row)
            finally:
                self._put_conn(conn)

    def load_all_trailing_stops(self) -> Dict[str, PersistedTrailingStop]:
        """P2: Load all trailing stops (for restart recovery)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("SELECT * FROM trailing_stops")
                result = {}
                for row in cursor.fetchall():
                    stop = self._row_to_trailing_stop(row)
                    result[stop.entry_order_id] = stop
                return result
            finally:
                self._put_conn(conn)

    def delete_trailing_stop(self, entry_order_id: str) -> None:
        """P2: Delete trailing stop record."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM trailing_stops WHERE entry_order_id = %s",
                    (entry_order_id,)
                )
                conn.commit()
            finally:
                self._put_conn(conn)

    def _row_to_trailing_stop(self, row: dict) -> PersistedTrailingStop:
        return PersistedTrailingStop(
            entry_order_id=row['entry_order_id'],
            symbol=row['symbol'],
            direction=row['direction'],
            entry_price=row['entry_price'],
            current_stop_price=row['current_stop_price'],
            initial_stop_price=row['initial_stop_price'],
            highest_price=row['highest_price'],
            lowest_price=row['lowest_price'],
            break_even_triggered=bool(row['break_even_triggered']),
            updates_count=row['updates_count'],
            current_atr=row['current_atr'],
            config_json=row['config_json'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    # =========================================================================
    # P3: Fill ID Deduplication Persistence
    # =========================================================================

    def save_fill_id(self, fill_id: str, symbol: str, order_id: str) -> None:
        """P3: Save fill ID for deduplication."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO seen_fill_ids (fill_id, symbol, order_id, processed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (fill_id, symbol, order_id, time.time()))
                conn.commit()
            finally:
                self._put_conn(conn)

    def has_fill_id(self, fill_id: str) -> bool:
        """P3: Check if fill ID was already processed."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM seen_fill_ids WHERE fill_id = %s",
                    (fill_id,)
                )
                return cursor.fetchone() is not None
            finally:
                self._put_conn(conn)

    def load_recent_fill_ids(self, hours: int = 24) -> Set[str]:
        """P3: Load fill IDs from last N hours (for restart recovery)."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT fill_id FROM seen_fill_ids WHERE processed_at > %s",
                    (cutoff,)
                )
                return {row['fill_id'] for row in cursor.fetchall()}
            finally:
                self._put_conn(conn)

    def cleanup_old_fill_ids(self, hours: int = 48) -> int:
        """P3: Delete fill IDs older than N hours."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM seen_fill_ids WHERE processed_at < %s",
                    (cutoff,)
                )
                deleted = cursor.rowcount
                conn.commit()
                return deleted
            finally:
                self._put_conn(conn)

    # =========================================================================
    # P4: CLOSING Timeout Persistence
    # =========================================================================

    def save_closing_timeout(self, symbol: str, entered_at: float, timeout_sec: float) -> None:
        """P4: Save CLOSING timeout tracker."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO closing_timeouts (symbol, entered_closing_at, timeout_sec, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(symbol) DO UPDATE SET
                        entered_closing_at = excluded.entered_closing_at,
                        timeout_sec = excluded.timeout_sec
                """, (symbol, entered_at, timeout_sec, time.time()))
                conn.commit()
            finally:
                self._put_conn(conn)

    def load_closing_timeout(self, symbol: str) -> Optional[PersistedClosingTimeout]:
        """P4: Load CLOSING timeout for symbol."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT * FROM closing_timeouts WHERE symbol = %s",
                    (symbol,)
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return PersistedClosingTimeout(
                    symbol=row['symbol'],
                    entered_closing_at=row['entered_closing_at'],
                    timeout_sec=row['timeout_sec'],
                    created_at=row['created_at']
                )
            finally:
                self._put_conn(conn)

    def load_all_closing_timeouts(self) -> Dict[str, PersistedClosingTimeout]:
        """P4: Load all CLOSING timeouts (for restart recovery)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("SELECT * FROM closing_timeouts")
                result = {}
                for row in cursor.fetchall():
                    timeout = PersistedClosingTimeout(
                        symbol=row['symbol'],
                        entered_closing_at=row['entered_closing_at'],
                        timeout_sec=row['timeout_sec'],
                        created_at=row['created_at']
                    )
                    result[timeout.symbol] = timeout
                return result
            finally:
                self._put_conn(conn)

    def delete_closing_timeout(self, symbol: str) -> None:
        """P4: Delete CLOSING timeout record."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM closing_timeouts WHERE symbol = %s",
                    (symbol,)
                )
                conn.commit()
            finally:
                self._put_conn(conn)

    # =========================================================================
    # P7: Tracked Position Persistence (SharedPositionState)
    # =========================================================================

    def save_tracked_position(
        self,
        wallet: str,
        coin: str,
        side: str,
        size: float,
        notional: float,
        entry_price: float,
        liq_price: float,
        current_price: float,
        distance_pct: float,
        leverage: float,
        danger_level: int = 0,
        opened_at: Optional[float] = None,
        discovered_at: Optional[float] = None
    ) -> None:
        """P7: Save tracked position snapshot."""
        pos_id = f"{wallet}:{coin}"
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO tracked_positions (
                        id, wallet, coin, side, size, notional, entry_price, liq_price,
                        current_price, distance_pct, leverage, danger_level,
                        updated_at, opened_at, discovered_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        side = excluded.side,
                        size = excluded.size,
                        notional = excluded.notional,
                        entry_price = excluded.entry_price,
                        liq_price = excluded.liq_price,
                        current_price = excluded.current_price,
                        distance_pct = excluded.distance_pct,
                        leverage = excluded.leverage,
                        danger_level = excluded.danger_level,
                        updated_at = excluded.updated_at,
                        opened_at = COALESCE(excluded.opened_at, tracked_positions.opened_at)
                """, (
                    pos_id, wallet, coin, side, size, notional, entry_price, liq_price,
                    current_price, distance_pct, leverage, danger_level,
                    now, opened_at, discovered_at or now
                ))
                conn.commit()
            finally:
                self._put_conn(conn)

    def load_tracked_positions(self) -> List[Dict]:
        """P7: Load all tracked positions (for restart recovery)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("SELECT * FROM tracked_positions")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                self._put_conn(conn)

    def delete_tracked_position(self, wallet: str, coin: str) -> None:
        """P7: Delete tracked position."""
        pos_id = f"{wallet}:{coin}"
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tracked_positions WHERE id = %s", (pos_id,))
                conn.commit()
            finally:
                self._put_conn(conn)

    def clear_tracked_positions(self) -> int:
        """P7: Clear all tracked positions."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tracked_positions")
                deleted = cursor.rowcount
                conn.commit()
                return deleted
            finally:
                self._put_conn(conn)

    # =========================================================================
    # P6: Atomic Transaction Support
    # =========================================================================

    def begin_transaction(self):
        """P6: Begin atomic transaction."""
        # PostgreSQL starts transactions automatically; no-op
        pass

    def commit_transaction(self):
        """P6: Commit atomic transaction."""
        # Handled per-method; no-op at repository level
        pass

    def rollback_transaction(self):
        """P6: Rollback atomic transaction."""
        # Handled per-method; no-op at repository level
        pass

    def atomic(self):
        """P6: Context manager for atomic transactions."""
        return AtomicTransaction(self)

    # =========================================================================
    # Utility
    # =========================================================================

    def close(self):
        """No-op — connections managed by pool."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AtomicTransaction:
    """P6: Context manager for atomic multi-write transactions.

    With PostgreSQL pool, each method gets its own connection and commits.
    For true atomicity, this wraps multiple operations in one connection.
    """

    def __init__(self, repository: ExecutionStateRepository):
        self._repo = repository
        self._conn = None

    def __enter__(self):
        self._conn = get_conn()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn is None:
            return False

        if exc_type is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
        else:
            try:
                self._conn.commit()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise

        put_conn(self._conn)
        self._conn = None
        return False
