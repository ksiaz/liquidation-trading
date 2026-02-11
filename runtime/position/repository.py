"""Position Repository - Persistence Layer.

Provides save/load functionality for positions.
Enables position recovery across restarts.

Constitutional: Stores factual position state only.

Extended (v2): Also stores strategy_id and entry_context for restart recovery.

PostgreSQL backend (v3): Uses shared connection pool instead of per-file SQLite.
"""

import json
import time
from decimal import Decimal
from typing import Dict, Optional, List, Any

import psycopg2.extras

from runtime.logging.pg_pool import get_conn, put_conn
from .types import Position, PositionState, Direction


class PositionRepository:
    """PostgreSQL-backed position persistence.

    Invariants:
    - One row per symbol (upsert semantics)
    - State machine states stored as strings
    - Decimal values stored as TEXT for precision
    """

    def __init__(self, db_path: str = None):
        """Initialize repository.

        Args:
            db_path: Ignored (kept for API compatibility). Uses PG pool.
        """
        # Schema already created by pg_schema.ensure_schema() at startup
        pass

    def _get_conn(self):
        """Borrow a PG pool connection."""
        return get_conn()

    def _put_conn(self, conn):
        """Return connection to pool."""
        put_conn(conn)

    def save(self, position: Position, strategy_id: Optional[str] = None,
             entry_context: Optional[Dict[str, Any]] = None) -> None:
        """Save position to database (upsert)."""
        context_json = json.dumps(entry_context) if entry_context else None

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions (symbol, state, direction, quantity, entry_price, updated_at, strategy_id, entry_context)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(symbol) DO UPDATE SET
                    state = excluded.state,
                    direction = excluded.direction,
                    quantity = excluded.quantity,
                    entry_price = excluded.entry_price,
                    updated_at = excluded.updated_at,
                    strategy_id = COALESCE(excluded.strategy_id, positions.strategy_id),
                    entry_context = COALESCE(excluded.entry_context, positions.entry_context)
            """, (
                position.symbol,
                position.state.value,
                position.direction.value if position.direction else None,
                str(position.quantity),
                str(position.entry_price) if position.entry_price else None,
                time.time(),
                strategy_id,
                context_json
            ))
            conn.commit()
        finally:
            self._put_conn(conn)

    def save_all(self, positions: Dict[str, Position]) -> None:
        """Save multiple positions in a single transaction."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            for symbol, position in positions.items():
                cursor.execute("""
                    INSERT INTO positions (symbol, state, direction, quantity, entry_price, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(symbol) DO UPDATE SET
                        state = excluded.state,
                        direction = excluded.direction,
                        quantity = excluded.quantity,
                        entry_price = excluded.entry_price,
                        updated_at = excluded.updated_at
                """, (
                    position.symbol,
                    position.state.value,
                    position.direction.value if position.direction else None,
                    str(position.quantity),
                    str(position.entry_price) if position.entry_price else None,
                    time.time()
                ))
            conn.commit()
        finally:
            self._put_conn(conn)

    def load(self, symbol: str) -> Optional[Position]:
        """Load position for symbol."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT symbol, state, direction, quantity, entry_price
                FROM positions
                WHERE symbol = %s
            """, (symbol,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_position(row)
        finally:
            self._put_conn(conn)

    def load_all(self) -> Dict[str, Position]:
        """Load all positions."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT symbol, state, direction, quantity, entry_price
                FROM positions
            """)
            positions = {}
            for row in cursor.fetchall():
                position = self._row_to_position(row)
                positions[position.symbol] = position
            return positions
        finally:
            self._put_conn(conn)

    def load_open_positions(self) -> Dict[str, Position]:
        """Load only OPEN positions (for restart recovery)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT symbol, state, direction, quantity, entry_price
                FROM positions
                WHERE state = %s
            """, (PositionState.OPEN.value,))
            positions = {}
            for row in cursor.fetchall():
                position = self._row_to_position(row)
                positions[position.symbol] = position
            return positions
        finally:
            self._put_conn(conn)

    def load_non_flat_positions(self) -> Dict[str, Position]:
        """Load all non-FLAT positions (includes ENTERING, REDUCING, CLOSING)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT symbol, state, direction, quantity, entry_price
                FROM positions
                WHERE state != %s
            """, (PositionState.FLAT.value,))
            positions = {}
            for row in cursor.fetchall():
                position = self._row_to_position(row)
                positions[position.symbol] = position
            return positions
        finally:
            self._put_conn(conn)

    def delete(self, symbol: str) -> None:
        """Delete position for symbol."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions WHERE symbol = %s", (symbol,))
            conn.commit()
        finally:
            self._put_conn(conn)

    def delete_flat_positions(self) -> int:
        """Delete all FLAT positions (cleanup)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM positions WHERE state = %s",
                (PositionState.FLAT.value,)
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            self._put_conn(conn)

    def get_entry_context(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get entry context for a position."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT entry_context FROM positions WHERE symbol = %s",
                (symbol,)
            )
            row = cursor.fetchone()
            if row and row['entry_context']:
                try:
                    return json.loads(row['entry_context'])
                except json.JSONDecodeError:
                    return None
            return None
        finally:
            self._put_conn(conn)

    def get_strategy_id(self, symbol: str) -> Optional[str]:
        """Get strategy ID for a position."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT strategy_id FROM positions WHERE symbol = %s",
                (symbol,)
            )
            row = cursor.fetchone()
            return row['strategy_id'] if row else None
        finally:
            self._put_conn(conn)

    def clear_entry_context(self, symbol: str) -> None:
        """Clear entry context when position is closed."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE positions SET strategy_id = NULL, entry_context = NULL WHERE symbol = %s",
                (symbol,)
            )
            conn.commit()
        finally:
            self._put_conn(conn)

    def _row_to_position(self, row: dict) -> Position:
        """Convert database row to Position object."""
        # Parse state - handle legacy EXITED as FLAT
        raw_state = row['state']
        was_exited = raw_state == 'EXITED'
        if was_exited:
            raw_state = 'FLAT'
        state = PositionState(raw_state)

        # Parse direction (may be None for FLAT)
        direction = None
        if row['direction'] and not was_exited:
            direction = Direction(row['direction'])

        # Parse quantity (FLAT must have Q=0)
        quantity = Decimal(0) if was_exited else Decimal(row['quantity'])

        # Parse entry_price (may be None)
        entry_price = None
        if row['entry_price'] and not was_exited:
            entry_price = Decimal(row['entry_price'])

        return Position(
            symbol=row['symbol'],
            state=state,
            direction=direction,
            quantity=quantity,
            entry_price=entry_price
        )

    def close(self):
        """No-op — connections managed by pool."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
