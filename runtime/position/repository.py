"""Position Repository - Persistence Layer.

Provides save/load functionality for positions.
Enables position recovery across restarts.

Constitutional: Stores factual position state only.
"""

import sqlite3
import time
from decimal import Decimal
from typing import Dict, Optional, List
from pathlib import Path

from .types import Position, PositionState, Direction


class PositionRepository:
    """SQLite-backed position persistence.

    Invariants:
    - One row per symbol (upsert semantics)
    - State machine states stored as strings
    - Decimal values stored as TEXT for precision
    - Thread-safe with check_same_thread=False
    """

    def __init__(self, db_path: str = "logs/positions.db"):
        """Initialize repository with database connection.

        Args:
            db_path: Path to SQLite database file
        """
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self._create_schema()

    def _create_schema(self):
        """Create positions table if not exists."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                direction TEXT,
                quantity TEXT NOT NULL,
                entry_price TEXT,
                updated_at REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index for efficient state queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_state
            ON positions(state)
        """)

        self.conn.commit()

    def save(self, position: Position) -> None:
        """Save position to database (upsert).

        Args:
            position: Position to save
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO positions (symbol, state, direction, quantity, entry_price, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
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

        self.conn.commit()

    def save_all(self, positions: Dict[str, Position]) -> None:
        """Save multiple positions in a single transaction.

        Args:
            positions: Dict of symbol -> Position
        """
        cursor = self.conn.cursor()

        for symbol, position in positions.items():
            cursor.execute("""
                INSERT INTO positions (symbol, state, direction, quantity, entry_price, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
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

        self.conn.commit()

    def load(self, symbol: str) -> Optional[Position]:
        """Load position for symbol.

        Args:
            symbol: Symbol to load

        Returns:
            Position if exists, None otherwise
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT symbol, state, direction, quantity, entry_price
            FROM positions
            WHERE symbol = ?
        """, (symbol,))

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_position(row)

    def load_all(self) -> Dict[str, Position]:
        """Load all positions.

        Returns:
            Dict of symbol -> Position
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT symbol, state, direction, quantity, entry_price
            FROM positions
        """)

        positions = {}
        for row in cursor.fetchall():
            position = self._row_to_position(row)
            positions[position.symbol] = position

        return positions

    def load_open_positions(self) -> Dict[str, Position]:
        """Load only OPEN positions (for restart recovery).

        Returns:
            Dict of symbol -> Position for OPEN positions only
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT symbol, state, direction, quantity, entry_price
            FROM positions
            WHERE state = ?
        """, (PositionState.OPEN.value,))

        positions = {}
        for row in cursor.fetchall():
            position = self._row_to_position(row)
            positions[position.symbol] = position

        return positions

    def load_non_flat_positions(self) -> Dict[str, Position]:
        """Load all non-FLAT positions (includes ENTERING, REDUCING, CLOSING).

        Returns:
            Dict of symbol -> Position for non-FLAT positions
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT symbol, state, direction, quantity, entry_price
            FROM positions
            WHERE state != ?
        """, (PositionState.FLAT.value,))

        positions = {}
        for row in cursor.fetchall():
            position = self._row_to_position(row)
            positions[position.symbol] = position

        return positions

    def delete(self, symbol: str) -> None:
        """Delete position for symbol.

        Args:
            symbol: Symbol to delete
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        self.conn.commit()

    def delete_flat_positions(self) -> int:
        """Delete all FLAT positions (cleanup).

        Returns:
            Number of positions deleted
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM positions WHERE state = ?",
            (PositionState.FLAT.value,)
        )
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def _row_to_position(self, row: sqlite3.Row) -> Position:
        """Convert database row to Position object.

        Args:
            row: SQLite row

        Returns:
            Position object
        """
        # Parse state
        state = PositionState(row['state'])

        # Parse direction (may be None for FLAT)
        direction = None
        if row['direction']:
            direction = Direction(row['direction'])

        # Parse quantity
        quantity = Decimal(row['quantity'])

        # Parse entry_price (may be None)
        entry_price = None
        if row['entry_price']:
            entry_price = Decimal(row['entry_price'])

        return Position(
            symbol=row['symbol'],
            state=state,
            direction=direction,
            quantity=quantity,
            entry_price=entry_price
        )

    def close(self):
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
