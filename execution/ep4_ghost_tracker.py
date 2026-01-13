"""
Ghost Position Tracker - Account State Management

Tracks simulated positions, account balance, and trade outcomes.
Mechanical state tracking only. No interpretation.

Authority: Ghost Trading Extension v1.0
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime
import json

from execution.ep4_ghost_adapter import (
    GhostExchangeAdapter,
    GhostExecutionResult,
    FillEstimate,
    ExecutionMode
)


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
    entry_cycle_id: Optional[int] = None  # For exits, link to entry
    exit_cycle_id: Optional[int] = None  # For exits
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
        db_conn = None  # Optional database connection for logging
    ):
        """
        Initialize ghost position tracker.

        Args:
            initial_balance: Starting account balance in USD
            position_size_pct: Position size as fraction of account (0.05 = 5%)
            symbols: List of trading symbols to support
            api_key: Optional Binance API key for live data
            db_conn: Optional sqlite3 connection for logging trades
        """
        self._state = GhostAccountState(
            initial_balance=initial_balance,
            current_balance=initial_balance
        )
        self._position_size_pct = position_size_pct
        self._db_conn = db_conn
        self._api_key = api_key

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

        # Trade ID counter
        self._next_trade_id = 1

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
        active_primitives: Optional[List[str]] = None
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

        Returns:
            (success, error_reason, trade_record)
        """
        # Check if position already exists
        if self.has_open_position(symbol):
            return (False, f"Position already exists for {symbol}", None)

        # Get adapter for this symbol
        adapter = self._get_adapter(symbol)

        # Execute ghost order
        order_side = "BUY" if side == "LONG" else "SELL"

        # Capture snapshot to get current price
        snapshot = adapter.capture_snapshot()
        entry_price = snapshot.best_ask if order_side == "BUY" else snapshot.best_bid

        # Calculate quantity if not provided
        if quantity is None:
            quantity = self.get_position_size_quantity(entry_price)

        # Round quantity to exchange filters
        filters = adapter.get_filters()
        quantity = round(quantity / filters['step_size']) * filters['step_size']

        # Execute ghost order
        result = adapter.execute_ghost_order(
            side=order_side,
            order_type="MARKET",
            quantity=quantity
        )

        # Check execution result
        if not result.would_execute:
            reason = result.reject_reason or "Execution failed"
            return (False, reason, None)

        if result.fill_estimate == FillEstimate.NONE:
            return (False, "No fill", None)

        # Generate trade ID
        trade_id = self._generate_trade_id()

        # Serialize active primitives
        primitives_json = json.dumps(active_primitives) if active_primitives else None

        # Calculate spread in BPS
        spread_bps = ((result.best_ask - result.best_bid) / result.best_bid * 10000) if result.best_bid > 0 else None

        # Create position
        position = GhostPosition(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_timestamp=result.timestamp,
            entry_order_id=result.orderbook_snapshot_id,
            entry_trade_id=trade_id,
            entry_cycle_id=cycle_id,
            entry_policy=policy_name,
            entry_primitives=primitives_json
        )

        # Update state
        self._state.open_positions[symbol] = position

        # Create trade record
        trade = GhostTrade(
            trade_id=trade_id,
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            price=entry_price,
            timestamp=result.timestamp,
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
        exit_reason: str = "FULL_EXIT"
    ) -> tuple[bool, Optional[str], Optional[GhostTrade]]:
        """
        Close position (simulated).

        Args:
            symbol: Trading symbol
            quantity: Quantity to close (None = full position)
            cycle_id: Optional execution cycle ID
            exit_reason: Reason for exit (FULL_EXIT, PARTIAL_REDUCE, STOP, MANDATE_EXIT)

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

        # Get adapter for this symbol
        adapter = self._get_adapter(symbol)

        # Execute ghost order (opposite side)
        order_side = "SELL" if position.side == "LONG" else "BUY"

        # Capture snapshot for exit price
        snapshot = adapter.capture_snapshot()
        exit_price = snapshot.best_bid if order_side == "SELL" else snapshot.best_ask

        # Execute ghost order
        result = adapter.execute_ghost_order(
            side=order_side,
            order_type="MARKET",
            quantity=quantity
        )

        # Check execution result
        if not result.would_execute:
            reason = result.reject_reason or "Execution failed"
            return (False, reason, None)

        if result.fill_estimate == FillEstimate.NONE:
            return (False, "No fill", None)

        # Calculate PNL
        if position.side == "LONG":
            pnl = (exit_price - position.entry_price) * quantity
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * quantity

        # Update account balance
        self._state.current_balance += pnl
        self._state.total_realized_pnl += pnl

        # Update win/loss counters
        if pnl > 0:
            self._state.winning_trades += 1
        elif pnl < 0:
            self._state.losing_trades += 1

        # Calculate holding duration
        holding_duration = result.timestamp - position.entry_timestamp if position.entry_timestamp else None

        # Calculate spread in BPS
        spread_bps = ((result.best_ask - result.best_bid) / result.best_bid * 10000) if result.best_bid > 0 else None

        # Is this a partial close?
        is_partial = quantity < position.quantity

        # Create trade record
        trade = GhostTrade(
            trade_id=self._generate_trade_id(),
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            price=exit_price,
            timestamp=result.timestamp,
            position_side=position.side,
            is_entry=False,
            pnl=pnl,
            account_balance_after=self._state.current_balance,
            cycle_id=cycle_id,
            entry_cycle_id=position.entry_cycle_id,
            exit_cycle_id=cycle_id,
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
            # Full close
            del self._state.open_positions[symbol]
        else:
            # Partial close - update position
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

    def _generate_trade_id(self) -> str:
        """Generate sequential trade ID."""
        trade_id = f"GHOST_{self._next_trade_id:06d}"
        self._next_trade_id += 1
        return trade_id

    def _log_trade_to_db(self, trade: GhostTrade) -> None:
        """Log trade to database if connection available."""
        if not self._db_conn:
            return

        try:
            cursor = self._db_conn.cursor()
            cursor.execute('''
                INSERT INTO ghost_trades (
                    trade_id, cycle_id, symbol, side, quantity, price,
                    timestamp, position_side, is_entry, pnl, account_balance_after,
                    entry_cycle_id, exit_cycle_id, winning_policy_name,
                    active_primitives, spread_bps, concurrent_positions,
                    holding_duration_sec, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        except Exception as e:
            # Silently fail - don't break execution if logging fails
            pass

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
