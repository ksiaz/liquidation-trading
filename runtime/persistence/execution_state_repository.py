"""
Execution State Repository - Unified Persistence for Execution State.

P1-P4 Hardenings:
- P1: Stop order lifecycle persistence
- P2: Trailing stop state persistence
- P3: Fill tracker/dedup set persistence
- P4: CLOSING timeout tracker persistence

Constitutional: Stores factual state only, no interpretation.
"""

import sqlite3
import time
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path
from decimal import Decimal
from threading import RLock


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
    Unified SQLite persistence for all execution state.

    Handles:
    - P1: Stop order lifecycle
    - P2: Trailing stop state
    - P3: Fill tracker dedup set
    - P4: CLOSING timeout trackers

    Thread-safe with RLock.
    """

    def __init__(self, db_path: str = "logs/execution_state.db"):
        """Initialize repository.

        Args:
            db_path: Path to SQLite database
        """
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self._lock = RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self._create_schema()

    def _create_schema(self):
        """Create all persistence tables."""
        cursor = self.conn.cursor()

        # P1: Stop order lifecycle table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stop_orders (
                entry_order_id TEXT PRIMARY KEY,
                stop_order_id TEXT,
                state TEXT NOT NULL,
                stop_price REAL NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                placement_attempts INTEGER DEFAULT 0,
                last_error TEXT,
                placed_at_ns INTEGER,
                triggered_at_ns INTEGER,
                filled_at_ns INTEGER,
                fill_price REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # P2: Trailing stop state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trailing_stops (
                entry_order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                current_stop_price REAL NOT NULL,
                initial_stop_price REAL NOT NULL,
                highest_price REAL NOT NULL,
                lowest_price REAL NOT NULL,
                break_even_triggered INTEGER DEFAULT 0,
                updates_count INTEGER DEFAULT 0,
                current_atr REAL,
                config_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # P3: Fill ID deduplication table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_fill_ids (
                fill_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                order_id TEXT NOT NULL,
                processed_at REAL NOT NULL
            )
        """)

        # P4: CLOSING timeout tracker table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS closing_timeouts (
                symbol TEXT PRIMARY KEY,
                entered_closing_at REAL NOT NULL,
                timeout_sec REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        # P7: SharedPositionState snapshots table (for detection state)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_positions (
                id TEXT PRIMARY KEY,
                wallet TEXT NOT NULL,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                notional REAL NOT NULL,
                entry_price REAL NOT NULL,
                liq_price REAL NOT NULL,
                current_price REAL NOT NULL,
                distance_pct REAL NOT NULL,
                leverage REAL NOT NULL,
                danger_level INTEGER DEFAULT 0,
                updated_at REAL NOT NULL,
                opened_at REAL,
                discovered_at REAL NOT NULL
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stop_orders_symbol ON stop_orders(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stop_orders_state ON stop_orders(state)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trailing_stops_symbol ON trailing_stops(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_fills_processed ON seen_fill_ids(processed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracked_positions_wallet ON tracked_positions(wallet)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracked_positions_coin ON tracked_positions(coin)")

        self.conn.commit()

    # =========================================================================
    # P1: Stop Order Lifecycle Persistence
    # =========================================================================

    def save_stop_order(self, stop: PersistedStopOrder) -> None:
        """P1: Save stop order state (upsert)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO stop_orders (
                    entry_order_id, stop_order_id, state, stop_price, symbol, side, size,
                    placement_attempts, last_error, placed_at_ns, triggered_at_ns,
                    filled_at_ns, fill_price, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            self.conn.commit()

    def load_stop_order(self, entry_order_id: str) -> Optional[PersistedStopOrder]:
        """P1: Load stop order by entry order ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM stop_orders WHERE entry_order_id = ?",
                (entry_order_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_stop_order(row)

    def load_active_stop_orders(self) -> Dict[str, PersistedStopOrder]:
        """P1: Load all non-terminal stop orders (for restart recovery).

        Returns stop orders in states: PENDING_PLACEMENT, PLACED, TRIGGERED
        AUDIT-P0-8: Excludes STALE orders (need reconciliation first)
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM stop_orders
                WHERE state IN ('PENDING_PLACEMENT', 'PLACED', 'TRIGGERED')
            """)
            result = {}
            for row in cursor.fetchall():
                stop = self._row_to_stop_order(row)
                result[stop.entry_order_id] = stop
            return result

    def load_unreconciled_stop_orders(self) -> Dict[str, PersistedStopOrder]:
        """AUDIT-P0-8: Load stop orders that need reconciliation before use.

        Returns PLACED orders that should be validated against exchange.
        Call reconcile_stop_orders() after querying exchange state.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM stop_orders
                WHERE state = 'PLACED'
            """)
            result = {}
            for row in cursor.fetchall():
                stop = self._row_to_stop_order(row)
                result[stop.entry_order_id] = stop
            return result

    def delete_stop_order(self, entry_order_id: str) -> None:
        """P1: Delete stop order record."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM stop_orders WHERE entry_order_id = ?",
                (entry_order_id,)
            )
            self.conn.commit()

    def reconcile_stop_orders(
        self,
        exchange_order_ids: Set[str],
        logger=None
    ) -> Dict[str, str]:
        """AUDIT-P0-8: Reconcile persisted stop orders against exchange reality.

        On startup, call this with the set of order IDs that actually exist
        on the exchange. Orders in PLACED state that aren't on exchange will
        be marked as STALE for review.

        Args:
            exchange_order_ids: Set of order IDs currently on exchange
            logger: Optional logger for reconciliation events

        Returns:
            Dict mapping entry_order_id -> action taken ('STALE', 'VALID', etc.)
        """
        import logging
        log = logger or logging.getLogger(__name__)

        with self._lock:
            cursor = self.conn.cursor()

            # Load all PLACED orders
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
                    # Order claims to be PLACED but doesn't exist on exchange
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
                cursor.executemany(
                    """
                    UPDATE stop_orders
                    SET state = 'STALE',
                        last_error = 'P0-8: Not found on exchange during startup reconciliation'
                    WHERE entry_order_id = ?
                    """,
                    [(oid,) for oid in stale_orders]
                )
                self.conn.commit()
                log.info(f"P0-8: Marked {len(stale_orders)} stop orders as STALE")

            return results

    def get_stale_stop_orders(self) -> List[PersistedStopOrder]:
        """AUDIT-P0-8: Get all stop orders marked as STALE for manual review."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM stop_orders
                WHERE state = 'STALE'
            """)
            return [self._row_to_stop_order(row) for row in cursor.fetchall()]

    def clear_stale_stop_order(self, entry_order_id: str, action: str) -> None:
        """AUDIT-P0-8: Clear a STALE order after manual review.

        Args:
            entry_order_id: Order to clear
            action: Action taken (e.g., 'DELETED', 'RESTORED', 'IGNORED')
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE stop_orders
                SET state = 'RECONCILED',
                    last_error = ?
                WHERE entry_order_id = ? AND state = 'STALE'
                """,
                (f"P0-8: Cleared by manual review, action={action}", entry_order_id)
            )
            self.conn.commit()

    def _row_to_stop_order(self, row: sqlite3.Row) -> PersistedStopOrder:
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
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO trailing_stops (
                    entry_order_id, symbol, direction, entry_price, current_stop_price,
                    initial_stop_price, highest_price, lowest_price, break_even_triggered,
                    updates_count, current_atr, config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_order_id) DO UPDATE SET
                    current_stop_price = excluded.current_stop_price,
                    highest_price = excluded.highest_price,
                    lowest_price = excluded.lowest_price,
                    break_even_triggered = excluded.break_even_triggered,
                    updates_count = excluded.updates_count,
                    current_atr = excluded.current_atr,
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
            self.conn.commit()

    def load_trailing_stop(self, entry_order_id: str) -> Optional[PersistedTrailingStop]:
        """P2: Load trailing stop by entry order ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM trailing_stops WHERE entry_order_id = ?",
                (entry_order_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_trailing_stop(row)

    def load_all_trailing_stops(self) -> Dict[str, PersistedTrailingStop]:
        """P2: Load all trailing stops (for restart recovery)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM trailing_stops")
            result = {}
            for row in cursor.fetchall():
                stop = self._row_to_trailing_stop(row)
                result[stop.entry_order_id] = stop
            return result

    def delete_trailing_stop(self, entry_order_id: str) -> None:
        """P2: Delete trailing stop record."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM trailing_stops WHERE entry_order_id = ?",
                (entry_order_id,)
            )
            self.conn.commit()

    def _row_to_trailing_stop(self, row: sqlite3.Row) -> PersistedTrailingStop:
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
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO seen_fill_ids (fill_id, symbol, order_id, processed_at)
                VALUES (?, ?, ?, ?)
            """, (fill_id, symbol, order_id, time.time()))
            self.conn.commit()

    def has_fill_id(self, fill_id: str) -> bool:
        """P3: Check if fill ID was already processed."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM seen_fill_ids WHERE fill_id = ?",
                (fill_id,)
            )
            return cursor.fetchone() is not None

    def load_recent_fill_ids(self, hours: int = 24) -> Set[str]:
        """P3: Load fill IDs from last N hours (for restart recovery)."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT fill_id FROM seen_fill_ids WHERE processed_at > ?",
                (cutoff,)
            )
            return {row['fill_id'] for row in cursor.fetchall()}

    def cleanup_old_fill_ids(self, hours: int = 48) -> int:
        """P3: Delete fill IDs older than N hours."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM seen_fill_ids WHERE processed_at < ?",
                (cutoff,)
            )
            deleted = cursor.rowcount
            self.conn.commit()
            return deleted

    # =========================================================================
    # P4: CLOSING Timeout Persistence
    # =========================================================================

    def save_closing_timeout(self, symbol: str, entered_at: float, timeout_sec: float) -> None:
        """P4: Save CLOSING timeout tracker."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO closing_timeouts (symbol, entered_closing_at, timeout_sec, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    entered_closing_at = excluded.entered_closing_at,
                    timeout_sec = excluded.timeout_sec
            """, (symbol, entered_at, timeout_sec, time.time()))
            self.conn.commit()

    def load_closing_timeout(self, symbol: str) -> Optional[PersistedClosingTimeout]:
        """P4: Load CLOSING timeout for symbol."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM closing_timeouts WHERE symbol = ?",
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

    def load_all_closing_timeouts(self) -> Dict[str, PersistedClosingTimeout]:
        """P4: Load all CLOSING timeouts (for restart recovery)."""
        with self._lock:
            cursor = self.conn.cursor()
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

    def delete_closing_timeout(self, symbol: str) -> None:
        """P4: Delete CLOSING timeout record."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM closing_timeouts WHERE symbol = ?",
                (symbol,)
            )
            self.conn.commit()

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
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO tracked_positions (
                    id, wallet, coin, side, size, notional, entry_price, liq_price,
                    current_price, distance_pct, leverage, danger_level,
                    updated_at, opened_at, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            self.conn.commit()

    def load_tracked_positions(self) -> List[Dict]:
        """P7: Load all tracked positions (for restart recovery)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM tracked_positions")
            return [dict(row) for row in cursor.fetchall()]

    def delete_tracked_position(self, wallet: str, coin: str) -> None:
        """P7: Delete tracked position."""
        pos_id = f"{wallet}:{coin}"
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM tracked_positions WHERE id = ?", (pos_id,))
            self.conn.commit()

    def clear_tracked_positions(self) -> int:
        """P7: Clear all tracked positions."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM tracked_positions")
            deleted = cursor.rowcount
            self.conn.commit()
            return deleted

    # =========================================================================
    # P6: Atomic Transaction Support
    # =========================================================================

    def begin_transaction(self):
        """P6: Begin atomic transaction."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")

    def commit_transaction(self):
        """P6: Commit atomic transaction."""
        with self._lock:
            self.conn.commit()

    def rollback_transaction(self):
        """P6: Rollback atomic transaction."""
        with self._lock:
            self.conn.rollback()

    def atomic(self):
        """P6: Context manager for atomic transactions.

        Usage:
            with repo.atomic():
                repo.save_stop_order(...)
                repo.save_trailing_stop(...)
                repo.save_closing_timeout(...)
            # All changes committed atomically, or all rolled back on error
        """
        return AtomicTransaction(self)

    # =========================================================================
    # Utility
    # =========================================================================

    def close(self):
        """Close database connection."""
        with self._lock:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AtomicTransaction:
    """P6: Context manager for atomic multi-write transactions."""

    def __init__(self, repository: ExecutionStateRepository):
        self._repo = repository
        self._entered = False

    def __enter__(self):
        self._repo.begin_transaction()
        self._entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._entered:
            return False

        if exc_type is not None:
            # Error occurred - rollback
            try:
                self._repo.rollback_transaction()
            except Exception:
                pass  # Best effort rollback
            return False  # Re-raise the exception

        # Success - commit
        try:
            self._repo.commit_transaction()
        except Exception:
            # Commit failed - try to rollback
            try:
                self._repo.rollback_transaction()
            except Exception:
                pass
            raise  # Re-raise commit error

        return False
