"""
Ghost Position Tracker - Account State Management

Tracks simulated positions, account balance, and trade outcomes.
Mechanical state tracking only. No interpretation.

Authority: Ghost Trading Extension v1.0

Persistence: Open positions are persisted to sqlite DB and restored on startup.
This enables external queries for P&L and state reconciliation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime
import json
import sqlite3
import os

from execution.ep4_ghost_adapter import (
    GhostExchangeAdapter,
    GhostExecutionResult,
    FillEstimate,
    ExecutionMode,
    NormalizedOrderbook
)

# Structured diagnostics for silent paths
from runtime.diagnostics import diag, ReasonCode


# ==============================================================================
# Position Persistence
# ==============================================================================

DEFAULT_DB_PATH = "/tmp/ghost_trades.db"


def _init_position_table(conn: sqlite3.Connection) -> None:
    """Create ghost_positions table if not exists. Migrates old schema if needed."""
    # Check if table exists with old UNIQUE(symbol, status) ON CONFLICT REPLACE constraint
    # SQLite can't ALTER TABLE DROP CONSTRAINT, so we recreate the table
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ghost_positions'"
    ).fetchone()
    if row and "ON CONFLICT REPLACE" in (row[0] or ""):
        print("[GHOST] Migrating ghost_positions: removing ON CONFLICT REPLACE constraint", flush=True)
        conn.execute("ALTER TABLE ghost_positions RENAME TO ghost_positions_old")
        conn.execute("""
            CREATE TABLE ghost_positions (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                entry_price REAL NOT NULL,
                entry_time REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                entry_reason TEXT,
                strategy_id TEXT,
                exit_price REAL,
                exit_time REAL,
                pnl REAL,
                zone_context TEXT
            )
        """)
        conn.execute("""
            INSERT INTO ghost_positions
            SELECT trade_id, symbol, side, qty, entry_price, entry_time,
                   status, entry_reason, strategy_id, exit_price, exit_time, pnl, zone_context
            FROM ghost_positions_old
        """)
        conn.execute("DROP TABLE ghost_positions_old")
        print("[GHOST] Migration complete: ghost_positions recreated without UNIQUE constraint", flush=True)
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ghost_positions (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                entry_price REAL NOT NULL,
                entry_time REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                entry_reason TEXT,
                strategy_id TEXT,
                exit_price REAL,
                exit_time REAL,
                pnl REAL,
                zone_context TEXT
            )
        """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_ghost_positions_status ON ghost_positions(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ghost_positions_symbol ON ghost_positions(symbol)")

    # Migration: add zone_context column if missing (for existing DBs)
    try:
        conn.execute("ALTER TABLE ghost_positions ADD COLUMN zone_context TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()


def _load_open_positions(conn: sqlite3.Connection) -> Dict[str, dict]:
    """Load all OPEN positions from DB. Returns dict keyed by symbol."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM ghost_positions WHERE status = 'OPEN'"
    ).fetchall()
    return {row['symbol']: dict(row) for row in rows}


def _insert_position(conn: sqlite3.Connection, pos: dict) -> None:
    """Insert new position with status=OPEN."""
    conn.execute("""
        INSERT INTO ghost_positions (trade_id, symbol, side, qty, entry_price, entry_time, status, entry_reason, strategy_id, zone_context)
        VALUES (:trade_id, :symbol, :side, :qty, :entry_price, :entry_time, 'OPEN', :entry_reason, :strategy_id, :zone_context)
    """, pos)
    conn.commit()


def _update_position_closed(conn: sqlite3.Connection, symbol: str, exit_price: float, exit_time: float, pnl: float) -> None:
    """Update position to CLOSED with exit data."""
    conn.execute("""
        UPDATE ghost_positions
        SET status = 'CLOSED', exit_price = ?, exit_time = ?, pnl = ?
        WHERE symbol = ? AND status = 'OPEN'
    """, (exit_price, exit_time, pnl, symbol))
    conn.commit()


# ==============================================================================
# Position State Types
# ==============================================================================

@dataclass(frozen=True)
class GhostPosition:
    """
    Represents a simulated open position.
    State snapshot only.
    """
    symbol: str
    side: str  # LONG / SHORT
    quantity: float
    entry_price: float
    entry_timestamp: float
    entry_order_id: str
    entry_trade_id: str  # Link to entry trade
    entry_cycle_id: Optional[int] = None  # Cycle when opened
    entry_policy: Optional[str] = None  # Policy that triggered entry
    entry_primitives: Optional[str] = None  # Active primitives at entry


@dataclass(frozen=True)
class GhostTrade:
    """
    Record of completed trade.
    Historical fact only.
    """
    trade_id: str
    symbol: str
    side: str  # BUY / SELL
    quantity: float
    price: float
    timestamp: float
    position_side: str  # LONG / SHORT
    is_entry: bool  # True = open, False = close
    pnl: Optional[float]  # None for entries, float for exits
    account_balance_after: float

    # Enhanced context fields
    cycle_id: Optional[int] = None
    entry_cycle_id: Optional[int] = None  # For exits, link to entry cycle
    exit_cycle_id: Optional[int] = None  # For exits
    entry_trade_id: Optional[str] = None  # For exits: trade_id of the entry row (deterministic linkage)
    winning_policy: Optional[str] = None
    active_primitives: Optional[str] = None  # JSON array
    spread_bps: Optional[float] = None
    concurrent_positions: Optional[int] = None
    holding_duration_sec: Optional[float] = None
    exit_reason: Optional[str] = None


# ==============================================================================
# Account State
# ==============================================================================

@dataclass
class GhostAccountState:
    """
    Simulated account state.
    Mutable container for tracking.
    """
    initial_balance: float
    current_balance: float
    open_positions: Dict[str, GhostPosition] = field(default_factory=dict)
    trade_history: List[GhostTrade] = field(default_factory=list)
    total_realized_pnl: float = 0.0
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


# ==============================================================================
# Ghost Position Tracker
# ==============================================================================

class GhostPositionTracker:
    """
    Tracks simulated positions and account state.

    Maintains:
    - Account balance
    - Open positions
    - Trade history
    - PNL calculations

    Does NOT interpret market conditions or predict outcomes.
    """

    def __init__(
        self,
        *,
        initial_balance: float = 1000.0,
        position_size_pct: float = 0.05,  # 5%
        symbols: List[str] = None,  # Support multiple symbols
        api_key: Optional[str] = None,
        db_conn = None,  # Optional database connection for logging trades
        db_path: str = DEFAULT_DB_PATH  # Path to position persistence DB
    ):
        """
        Initialize ghost position tracker.

        Args:
            initial_balance: Starting account balance in USD
            position_size_pct: Position size as fraction of account (0.05 = 5%)
            symbols: List of trading symbols to support
            api_key: Optional Binance API key for live data
            db_conn: Optional sqlite3 connection for logging trades
            db_path: Path to sqlite DB for position persistence (default: /tmp/ghost_trades.db)
        """
        self._state = GhostAccountState(
            initial_balance=initial_balance,
            current_balance=initial_balance
        )
        self._position_size_pct = position_size_pct
        self._db_conn = db_conn
        self._api_key = api_key
        self._db_path = db_path

        # Position persistence connection (separate from trade logging)
        self._pos_conn: Optional[sqlite3.Connection] = None
        self._init_persistence()

        # Ghost adapters per symbol (created on-demand)
        self._adapters: Dict[str, GhostExchangeAdapter] = {}

        # Pre-create adapters for known symbols
        if symbols:
            for symbol in symbols:
                self._adapters[symbol] = GhostExchangeAdapter(
                    symbol=symbol,
                    api_key=api_key,
                    execution_mode=ExecutionMode.GHOST_LIVE
                )

        # Trade ID counter - load from DB if positions exist
        self._next_trade_id = self._get_next_trade_id()

    def _init_persistence(self) -> None:
        """Initialize position persistence DB and restore state."""
        try:
            self._pos_conn = sqlite3.connect(self._db_path, check_same_thread=False)
            _init_position_table(self._pos_conn)

            # Load existing OPEN positions
            saved_positions = _load_open_positions(self._pos_conn)
            persisted_contexts = {}

            for symbol, row in saved_positions.items():
                # Reconstruct GhostPosition from DB row
                position = GhostPosition(
                    symbol=row['symbol'],
                    side=row['side'],
                    quantity=row['qty'],
                    entry_price=row['entry_price'],
                    entry_timestamp=row['entry_time'],
                    entry_order_id="",  # Not persisted
                    entry_trade_id=row['trade_id'],
                    entry_policy=row.get('strategy_id'),
                    entry_primitives=None
                )
                self._state.open_positions[symbol] = position

                # Collect zone context for geometry restoration
                zone_ctx_json = row.get('zone_context')
                if zone_ctx_json:
                    try:
                        persisted_contexts[symbol] = json.loads(zone_ctx_json)
                    except json.JSONDecodeError:
                        pass

            if saved_positions:
                print(f"[GHOST] Restored {len(saved_positions)} open positions from DB", flush=True)

                # Restore geometry strategy zone contexts for proper exit detection
                # NOTE: Geometry stores context by BASE symbol (BTC), DB stores by FULL symbol (BTCUSDT)
                if persisted_contexts:
                    try:
                        from external_policy.ep2_strategy_geometry import restore_entry_context_from_positions

                        # Helper to normalize symbol
                        def to_base(s: str) -> str:
                            return s.replace('USDT', '').replace('USD', '')

                        # Convert positions list to base symbols for geometry
                        positions_list = [
                            {
                                "symbol": to_base(sym),
                                "direction": "LONG" if row['side'] == "LONG" else "SHORT",
                                "entry_price": row['entry_price'],
                                "state": "OPEN"
                            }
                            for sym, row in saved_positions.items()
                        ]

                        # Convert persisted_contexts keys to base symbols
                        base_contexts = {to_base(k): v for k, v in persisted_contexts.items()}

                        restore_entry_context_from_positions(positions_list, base_contexts)
                        print(f"[GHOST] Restored zone contexts for {len(persisted_contexts)} positions", flush=True)
                    except Exception as e:
                        print(f"[GHOST] Zone context restoration failed: {e}", flush=True)

        except Exception as e:
            print(f"[GHOST] Position persistence init failed: {e}", flush=True)
            self._pos_conn = None

    def _get_next_trade_id(self) -> int:
        """Get next trade ID from DB or start at 1."""
        if not self._pos_conn:
            return 1
        try:
            row = self._pos_conn.execute(
                "SELECT MAX(CAST(SUBSTR(trade_id, 7) AS INTEGER)) FROM ghost_positions"
            ).fetchone()
            if row[0] is not None:
                return row[0] + 1
        except:
            pass
        return 1

    def _normalize_to_base_symbol(self, symbol: str) -> str:
        """Normalize symbol to base format (BTCUSDT -> BTC).

        Geometry strategy stores context keyed by base symbol (from HL primitives),
        but ghost tracker uses full Binance symbols. This ensures lookup works.
        """
        return symbol.replace('USDT', '').replace('USD', '')

    def _persist_open_position(self, position: GhostPosition, strategy_id: Optional[str] = None) -> None:
        """Persist new position to DB with status=OPEN, including zone context."""
        if not self._pos_conn:
            return
        try:
            # Get zone context from geometry strategy for proper exit detection on restart
            # Normalize symbol: geometry stores by base symbol (BTC), we use full symbol (BTCUSDT)
            zone_context_json = None
            try:
                from external_policy.ep2_strategy_geometry import get_entry_context_for_persistence
                base_symbol = self._normalize_to_base_symbol(position.symbol)
                zone_ctx = get_entry_context_for_persistence(base_symbol)
                if zone_ctx:
                    zone_context_json = json.dumps(zone_ctx)
            except Exception:
                pass  # Geometry module may not be available

            _insert_position(self._pos_conn, {
                'trade_id': position.entry_trade_id,
                'symbol': position.symbol,
                'side': position.side,
                'qty': position.quantity,
                'entry_price': position.entry_price,
                'entry_time': position.entry_timestamp,
                'entry_reason': position.entry_policy,
                'strategy_id': strategy_id or position.entry_policy,
                'zone_context': zone_context_json,
            })
        except Exception as e:
            print(f"[GHOST] Failed to persist position: {e}", flush=True)

    def _persist_position_closed(self, symbol: str, exit_price: float, exit_time: float, pnl: float) -> None:
        """Update position in DB to status=CLOSED with exit data."""
        if not self._pos_conn:
            return
        try:
            _update_position_closed(self._pos_conn, symbol, exit_price, exit_time, pnl)
        except Exception as e:
            print(f"[GHOST] Failed to update closed position: {e}", flush=True)

    def _get_adapter(self, symbol: str) -> GhostExchangeAdapter:
        """Get or create adapter for symbol."""
        if symbol not in self._adapters:
            self._adapters[symbol] = GhostExchangeAdapter(
                symbol=symbol,
                api_key=self._api_key,
                execution_mode=ExecutionMode.GHOST_LIVE
            )
        return self._adapters[symbol]

    def get_position_size_usd(self) -> float:
        """
        Calculate position size in USD based on current balance.

        Returns:
            Position size in USD
        """
        return self._state.current_balance * self._position_size_pct

    def get_position_size_quantity(self, price: float) -> float:
        """
        Calculate position size in quantity at given price.

        Args:
            price: Current market price

        Returns:
            Position quantity
        """
        size_usd = self.get_position_size_usd()
        return size_usd / price

    def has_open_position(self, symbol: str) -> bool:
        """Check if position exists for symbol."""
        return symbol in self._state.open_positions

    def get_open_position(self, symbol: str) -> Optional[GhostPosition]:
        """Get open position for symbol or None."""
        return self._state.open_positions.get(symbol)

    def calculate_unrealized_pnl(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Calculate unrealized PNL for open position.

        Args:
            symbol: Position symbol
            current_price: Current market price

        Returns:
            Unrealized PNL in USD or None if no position
        """
        position = self.get_open_position(symbol)
        if not position:
            return None

        # Calculate PNL based on position side
        if position.side == "LONG":
            pnl = (current_price - position.entry_price) * position.quantity
        else:  # SHORT
            pnl = (position.entry_price - current_price) * position.quantity

        return pnl

    def open_position(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Optional[float] = None,
        cycle_id: Optional[int] = None,
        policy_name: Optional[str] = None,
        active_primitives: Optional[List[str]] = None,
        orderbook: Optional[NormalizedOrderbook] = None,
        entry_price: Optional[float] = None,
        timestamp: Optional[float] = None
    ) -> tuple[bool, Optional[str], Optional[GhostTrade]]:
        """
        Open new position (simulated).

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            quantity: Position quantity (None = auto-calculate from position size %)
            cycle_id: Optional execution cycle ID
            policy_name: Optional policy that triggered entry
            active_primitives: Optional list of active primitive names
            orderbook: Optional normalized orderbook (from HL or other source).
                      If provided, uses this for price/spread instead of Binance.
            entry_price: Optional externally-determined entry price.
                        When provided with quantity, skips adapter execution.
            timestamp: Optional entry timestamp (used with entry_price).

        Returns:
            (success, error_reason, trade_record)
        """
        # Close existing position on same symbol before opening new one
        # Prevents orphaned entries from ON CONFLICT REPLACE or state desync
        if self.has_open_position(symbol):
            existing = self.get_open_position(symbol)
            if existing:
                print(f"[GHOST] Closing existing {symbol} {existing.side} position before new open", flush=True)
                self.close_position(
                    symbol=symbol,
                    exit_reason="REPLACED_BY_NEW_ENTRY",
                    exit_price=existing.entry_price,  # Flat PnL
                    timestamp=timestamp or __import__('time').time()
                )

        order_side = "BUY" if side == "LONG" else "SELL"
        spread_bps = None

        if entry_price is not None and quantity is not None:
            # External fill from controller — skip adapter execution
            fill_price = entry_price
            fill_timestamp = timestamp or time.time()
        else:
            # Original adapter path — fetch price and execute ghost order
            adapter = self._get_adapter(symbol)

            snapshot = adapter.capture_snapshot(orderbook=orderbook)
            fill_price = snapshot.best_ask if order_side == "BUY" else snapshot.best_bid

            if quantity is None:
                quantity = self.get_position_size_quantity(fill_price)

            filters = adapter.get_filters()
            quantity = round(quantity / filters['step_size']) * filters['step_size']

            result = adapter.execute_ghost_order(
                side=order_side,
                order_type="MARKET",
                quantity=quantity,
                orderbook=orderbook
            )

            if not result.would_execute:
                reason = result.reject_reason or "Execution failed"
                return (False, reason, None)

            if result.fill_estimate == FillEstimate.NONE:
                return (False, "No fill", None)

            fill_timestamp = result.timestamp
            if result.best_bid > 0:
                spread_bps = ((result.best_ask - result.best_bid) / result.best_bid * 10000)

        # Generate trade ID
        trade_id = self._generate_trade_id()

        # Serialize active primitives
        primitives_json = json.dumps(active_primitives) if active_primitives else None

        # Create position
        position = GhostPosition(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            entry_timestamp=fill_timestamp,
            entry_order_id="external" if entry_price is not None else result.orderbook_snapshot_id,
            entry_trade_id=trade_id,
            entry_cycle_id=cycle_id,
            entry_policy=policy_name,
            entry_primitives=primitives_json
        )

        # Update state
        self._state.open_positions[symbol] = position

        # Persist position to DB
        self._persist_open_position(position, policy_name)

        # Create trade record
        trade = GhostTrade(
            trade_id=trade_id,
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            price=fill_price,
            timestamp=fill_timestamp,
            position_side=side,
            is_entry=True,
            pnl=None,
            account_balance_after=self._state.current_balance,
            cycle_id=cycle_id,
            entry_cycle_id=cycle_id,
            winning_policy=policy_name,
            active_primitives=primitives_json,
            spread_bps=spread_bps,
            concurrent_positions=len(self._state.open_positions)
        )

        self._state.trade_history.append(trade)
        self._state.trade_count += 1

        # Log to database if connected
        self._log_trade_to_db(trade)

        return (True, None, trade)

    def close_position(
        self,
        *,
        symbol: str,
        quantity: Optional[float] = None,
        cycle_id: Optional[int] = None,
        exit_reason: str = "FULL_EXIT",
        orderbook: Optional[NormalizedOrderbook] = None,
        exit_price: Optional[float] = None,
        timestamp: Optional[float] = None
    ) -> tuple[bool, Optional[str], Optional[GhostTrade]]:
        """
        Close position (simulated).

        Args:
            symbol: Trading symbol
            quantity: Quantity to close (None = full position)
            cycle_id: Optional execution cycle ID
            exit_reason: Reason for exit (FULL_EXIT, PARTIAL_REDUCE, STOP, MANDATE_EXIT)
            orderbook: Optional normalized orderbook (from HL or other source).
                      If provided, uses this for price/spread instead of Binance.
            exit_price: Optional exit price (from trailing stop trigger).
                       If provided, skips adapter snapshot + ghost order.
            timestamp: Optional exit timestamp. Defaults to current time.

        Returns:
            (success, error_reason, trade_record)
        """
        # Check position exists
        position = self.get_open_position(symbol)
        if not position:
            return (False, f"No position exists for {symbol}", None)

        # Default to full position close
        if quantity is None:
            quantity = position.quantity

        # Validate quantity
        if quantity > position.quantity:
            return (False, f"Quantity {quantity} exceeds position size {position.quantity}", None)

        # Execute ghost order (opposite side)
        order_side = "SELL" if position.side == "LONG" else "BUY"

        spread_bps = None
        if exit_price is not None:
            # External fill (trailing stop trigger) — use provided price directly
            fill_price = exit_price
            fill_timestamp = timestamp or time.time()
        else:
            # Original adapter path — simulate ghost order execution
            adapter = self._get_adapter(symbol)

            # Capture snapshot for exit price (uses HL orderbook if provided)
            snapshot = adapter.capture_snapshot(orderbook=orderbook)
            fill_price = snapshot.best_bid if order_side == "SELL" else snapshot.best_ask

            # Execute ghost order (uses HL orderbook if provided)
            result = adapter.execute_ghost_order(
                side=order_side,
                order_type="MARKET",
                quantity=quantity,
                orderbook=orderbook
            )

            # Check execution result
            if not result.would_execute:
                reason = result.reject_reason or "Execution failed"
                return (False, reason, None)

            if result.fill_estimate == FillEstimate.NONE:
                return (False, "No fill", None)

            fill_timestamp = result.timestamp
            if result.best_bid > 0:
                spread_bps = ((result.best_ask - result.best_bid) / result.best_bid * 10000)

        # Calculate PNL
        if position.side == "LONG":
            pnl = (fill_price - position.entry_price) * quantity
        else:  # SHORT
            pnl = (position.entry_price - fill_price) * quantity

        # Update account balance
        self._state.current_balance += pnl
        self._state.total_realized_pnl += pnl

        # Update win/loss counters
        if pnl > 0:
            self._state.winning_trades += 1
        elif pnl < 0:
            self._state.losing_trades += 1

        # Calculate holding duration
        holding_duration = fill_timestamp - position.entry_timestamp if position.entry_timestamp else None

        # Is this a partial close?
        is_partial = quantity < position.quantity

        # Create trade record with deterministic entry linkage
        trade = GhostTrade(
            trade_id=self._generate_trade_id(),
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            price=fill_price,
            timestamp=fill_timestamp,
            position_side=position.side,
            is_entry=False,
            pnl=pnl,
            account_balance_after=self._state.current_balance,
            cycle_id=cycle_id,
            entry_cycle_id=position.entry_cycle_id,
            exit_cycle_id=cycle_id,
            entry_trade_id=position.entry_trade_id,  # Links exit to entry row
            winning_policy=position.entry_policy,
            active_primitives=position.entry_primitives,
            spread_bps=spread_bps,
            concurrent_positions=len(self._state.open_positions),
            holding_duration_sec=holding_duration,
            exit_reason=exit_reason if not is_partial else "PARTIAL_REDUCE"
        )

        self._state.trade_history.append(trade)
        self._state.trade_count += 1

        # Log to database if connected
        self._log_trade_to_db(trade)

        # Remove or reduce position
        if quantity >= position.quantity:
            # Full close - persist to DB as CLOSED
            self._persist_position_closed(symbol, fill_price, fill_timestamp, pnl)
            del self._state.open_positions[symbol]
        else:
            # Partial close - update position (keep as OPEN in DB, qty not updated for simplicity)
            updated_position = GhostPosition(
                symbol=position.symbol,
                side=position.side,
                quantity=position.quantity - quantity,
                entry_price=position.entry_price,
                entry_timestamp=position.entry_timestamp,
                entry_order_id=position.entry_order_id,
                entry_trade_id=position.entry_trade_id,
                entry_cycle_id=position.entry_cycle_id,
                entry_policy=position.entry_policy,
                entry_primitives=position.entry_primitives
            )
            self._state.open_positions[symbol] = updated_position

        return (True, None, trade)

    def get_account_summary(self) -> Dict:
        """
        Get account summary statistics.

        Returns:
            Dict with account metrics
        """
        # Calculate total unrealized PNL
        total_unrealized = 0.0
        for symbol, position in self._state.open_positions.items():
            try:
                adapter = self._get_adapter(symbol)
                snapshot = adapter.capture_snapshot()
                current_price = (snapshot.best_bid + snapshot.best_ask) / 2
                unrealized = self.calculate_unrealized_pnl(symbol, current_price)
                if unrealized is not None:
                    total_unrealized += unrealized
            except:
                # Skip if can't get price for this symbol
                pass

        # Calculate total equity
        total_equity = self._state.current_balance + total_unrealized

        # Win rate
        total_closed_trades = self._state.winning_trades + self._state.losing_trades
        win_rate = (self._state.winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0.0

        # Return on initial balance
        roi = ((total_equity - self._state.initial_balance) / self._state.initial_balance * 100)

        return {
            "initial_balance": self._state.initial_balance,
            "current_balance": self._state.current_balance,
            "total_unrealized_pnl": total_unrealized,
            "total_equity": total_equity,
            "total_realized_pnl": self._state.total_realized_pnl,
            "roi_pct": roi,
            "total_trades": self._state.trade_count,
            "winning_trades": self._state.winning_trades,
            "losing_trades": self._state.losing_trades,
            "win_rate_pct": win_rate,
            "open_positions_count": len(self._state.open_positions)
        }

    def get_trade_history(self) -> List[GhostTrade]:
        """Get full trade history."""
        return self._state.trade_history.copy()

    def get_open_positions(self) -> Dict[str, GhostPosition]:
        """Get all open positions."""
        return self._state.open_positions.copy()

    def get_positions_with_pnl(self, price_getter=None) -> List[Dict]:
        """
        Get open positions with computed unrealized P&L.

        External P&L is computed on read from current mark price.
        Does not persist per-tick values.

        Args:
            price_getter: Optional callable(symbol) -> float for current price.
                          If None, uses adapter to get live price.

        Returns:
            List of dicts with position data + unrealized_pnl field
        """
        results = []
        for symbol, pos in self._state.open_positions.items():
            # Get current price
            current_price = None
            if price_getter:
                try:
                    current_price = price_getter(symbol)
                except:
                    pass

            if current_price is None:
                try:
                    adapter = self._get_adapter(symbol)
                    snapshot = adapter.capture_snapshot()
                    current_price = (snapshot.best_bid + snapshot.best_ask) / 2
                except:
                    current_price = pos.entry_price  # Fallback

            # Compute unrealized P&L
            if pos.side == "LONG":
                unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
            else:
                unrealized_pnl = (pos.entry_price - current_price) * pos.quantity

            pnl_pct = (unrealized_pnl / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price > 0 else 0

            results.append({
                'trade_id': pos.entry_trade_id,
                'symbol': symbol,
                'side': pos.side,
                'qty': pos.quantity,
                'entry_price': pos.entry_price,
                'entry_time': pos.entry_timestamp,
                'current_price': current_price,
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_pct': pnl_pct,
                'strategy_id': pos.entry_policy,
            })

        return results

    @staticmethod
    def query_positions_from_db(db_path: str = DEFAULT_DB_PATH, status: str = None) -> List[Dict]:
        """
        Query positions directly from DB without creating tracker instance.

        For external tools that need position state without running the tracker.

        Args:
            db_path: Path to ghost trades DB
            status: Filter by status ('OPEN', 'CLOSED', or None for all)

        Returns:
            List of position dicts from DB
        """
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM ghost_positions WHERE status = ? ORDER BY entry_time DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ghost_positions ORDER BY entry_time DESC"
                ).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            return []

    def _generate_trade_id(self) -> str:
        """Generate sequential trade ID."""
        trade_id = f"GHOST_{self._next_trade_id:06d}"
        self._next_trade_id += 1
        return trade_id

    def _log_trade_to_db(self, trade: GhostTrade) -> None:
        """Log trade to database if connection available."""
        if not self._db_conn:
            # DIAGNOSTIC: No DB connection - trade not persisted
            diag.record_skip(
                component="GhostTracker",
                function="_log_trade_to_db",
                reason_code=ReasonCode.GT_NO_DB_CONNECTION,
                symbol=trade.symbol,
                context={"trade_id": trade.trade_id}
            )
            return

        import time as _time

        max_attempts = 4
        retry_delays = [0.1, 0.5, 1.0]

        for attempt in range(max_attempts):
            try:
                cursor = self._db_conn.cursor()
                cursor.execute('''
                    INSERT INTO ghost_trades (
                        trade_id, cycle_id, symbol, side, quantity, price,
                        timestamp, position_side, is_entry, pnl, account_balance_after,
                        entry_cycle_id, exit_cycle_id, entry_trade_id, winning_policy_name,
                        active_primitives, spread_bps, concurrent_positions,
                        holding_duration_sec, exit_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade.trade_id,
                    trade.cycle_id,
                    trade.symbol,
                    trade.side,
                    trade.quantity,
                    trade.price,
                    trade.timestamp,
                    trade.position_side,
                    trade.is_entry,
                    trade.pnl,
                    trade.account_balance_after,
                    trade.entry_cycle_id,
                    trade.exit_cycle_id,
                    trade.entry_trade_id,
                    trade.winning_policy,
                    trade.active_primitives,
                    trade.spread_bps,
                    trade.concurrent_positions,
                    trade.holding_duration_sec,
                    trade.exit_reason
                ))

                # Update policy_outcomes with ghost trade results (only for exits)
                if not trade.is_entry and trade.entry_cycle_id is not None:
                    # Find policy_outcome for the entry cycle and update with exit data
                    cursor.execute('''
                        UPDATE policy_outcomes
                        SET ghost_trade_id = ?,
                            realized_pnl = ?,
                            holding_duration_sec = ?,
                            exit_reason = ?
                        WHERE cycle_id = ?
                          AND symbol = ?
                          AND executed_action = 'ENTRY'
                          AND ghost_trade_id IS NULL
                        LIMIT 1
                    ''', (
                        int(trade.trade_id.split('_')[1]),  # Extract numeric ID from GHOST_000123
                        trade.pnl,
                        trade.holding_duration_sec,
                        trade.exit_reason,
                        trade.entry_cycle_id,
                        trade.symbol
                    ))

                self._db_conn.commit()
                return  # Success
            except Exception as e:
                is_locked = "database is locked" in str(e).lower()
                if is_locked and attempt < max_attempts - 1:
                    delay = retry_delays[attempt]
                    print(f"[GHOST] DB locked writing {trade.trade_id}, retry {attempt + 1}/{len(retry_delays)} in {delay}s", flush=True)
                    _time.sleep(delay)
                    continue

                # Final failure or non-lock error
                print(f"[GHOST] Failed to log trade to DB: {e}", flush=True)
                diag.record_skip(
                    component="GhostTracker",
                    function="_log_trade_to_db",
                    reason_code=ReasonCode.GT_DB_WRITE_FAILED,
                    symbol=trade.symbol,
                    context={"trade_id": trade.trade_id, "error": str(e), "attempts": attempt + 1}
                )
                return  # Give up

    def log_rejection(
        self,
        *,
        cycle_id: int,
        timestamp: float,
        symbol: str,
        attempted_action: str,
        attempted_side: Optional[str],
        rejection_reason: str,
        mandate_id: Optional[int] = None,
        policy_name: Optional[str] = None,
        current_price: Optional[float] = None,
        spread_bps: Optional[float] = None,
        triggering_primitives: Optional[List[str]] = None
    ) -> None:
        """Log rejected trade attempt to database.

        Args:
            cycle_id: Execution cycle ID
            timestamp: Rejection timestamp
            symbol: Trading symbol
            attempted_action: ENTRY, EXIT, or REDUCE
            attempted_side: LONG or SHORT (if applicable)
            rejection_reason: Why the trade was rejected
            mandate_id: Optional mandate ID that triggered attempt
            policy_name: Optional policy that generated mandate
            current_price: Optional market price at rejection
            spread_bps: Optional spread in basis points
            triggering_primitives: Optional list of active primitives
        """
        if not self._db_conn:
            return

        try:
            cursor = self._db_conn.cursor()

            primitives_json = json.dumps(triggering_primitives) if triggering_primitives else None

            cursor.execute('''
                INSERT INTO ghost_trade_rejections (
                    cycle_id, timestamp, symbol, attempted_action, attempted_side,
                    rejection_reason, mandate_id, policy_name,
                    account_balance, account_equity, open_positions_count,
                    current_price, spread_bps, triggering_primitives
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                cycle_id,
                timestamp,
                symbol,
                attempted_action,
                attempted_side,
                rejection_reason,
                mandate_id,
                policy_name,
                self._state.current_balance,
                self.get_account_summary()['total_equity'],
                len(self._state.open_positions),
                current_price,
                spread_bps,
                primitives_json
            ))
            self._db_conn.commit()
        except Exception as e:
            # Silently fail - don't break execution if logging fails
            pass

    def print_summary(self) -> None:
        """Print formatted account summary."""
        summary = self.get_account_summary()

        print("\n" + "="*60)
        print("GHOST TRADING ACCOUNT SUMMARY")
        print("="*60)
        print(f"Initial Balance:      ${summary['initial_balance']:,.2f}")
        print(f"Current Balance:      ${summary['current_balance']:,.2f}")
        print(f"Unrealized PNL:       ${summary['total_unrealized_pnl']:+,.2f}")
        print(f"Total Equity:         ${summary['total_equity']:,.2f}")
        print(f"Realized PNL:         ${summary['total_realized_pnl']:+,.2f}")
        print(f"ROI:                  {summary['roi_pct']:+.2f}%")
        print("-"*60)
        print(f"Total Trades:         {summary['total_trades']}")
        print(f"Winning Trades:       {summary['winning_trades']}")
        print(f"Losing Trades:        {summary['losing_trades']}")
        print(f"Win Rate:             {summary['win_rate_pct']:.1f}%")
        print(f"Open Positions:       {summary['open_positions_count']}")
        print("="*60 + "\n")

    def print_trade_history(self) -> None:
        """Print formatted trade history."""
        if not self._state.trade_history:
            print("\nNo trades executed yet.\n")
            return

        print("\n" + "="*80)
        print("TRADE HISTORY")
        print("="*80)
        print(f"{'ID':<12} {'Symbol':<8} {'Side':<6} {'Type':<6} {'Qty':<10} {'Price':<12} {'PNL':<12} {'Balance':<12}")
        print("-"*80)

        for trade in self._state.trade_history:
            trade_type = "ENTRY" if trade.is_entry else "EXIT"
            pnl_str = f"${trade.pnl:+,.2f}" if trade.pnl is not None else "-"

            print(
                f"{trade.trade_id:<12} "
                f"{trade.symbol:<8} "
                f"{trade.side:<6} "
                f"{trade_type:<6} "
                f"{trade.quantity:<10.4f} "
                f"${trade.price:<11,.2f} "
                f"{pnl_str:<12} "
                f"${trade.account_balance_after:,.2f}"
            )

        print("="*80 + "\n")
