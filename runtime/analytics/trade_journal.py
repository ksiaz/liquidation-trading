"""
HLP19: Trade Journal.

Records all trades with full details for analysis and debugging.

Every trade logged:
- Entry details (time, price, size, slippage)
- Exit details (time, price, reason, slippage)
- PnL breakdown
- Context (event, regime, strategy)
"""

import time
import logging
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from threading import RLock
from pathlib import Path

from .types import TradeRecord, TradeOutcome, DailyStats


@dataclass
class JournalConfig:
    """Configuration for trade journal."""
    # Storage
    persist_to_file: bool = True
    journal_dir: str = "logs/trades"
    max_memory_trades: int = 1000  # Keep in memory

    # Archiving
    archive_closed_trades: bool = True
    archive_after_days: int = 7


class TradeJournal:
    """
    Records and manages trade history.

    Provides:
    - Trade recording with full details
    - Trade lookup and filtering
    - Daily/weekly/monthly aggregation
    - Export capabilities
    """

    def __init__(
        self,
        config: JournalConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or JournalConfig()
        self._logger = logger or logging.getLogger(__name__)

        # In-memory storage
        self._trades: Dict[str, TradeRecord] = {}
        self._open_trades: Dict[str, TradeRecord] = {}
        self._closed_trades: List[TradeRecord] = []

        # Daily stats cache
        self._daily_stats: Dict[str, DailyStats] = {}

        # Trade counter for ID generation
        self._trade_counter = 0

        # Callbacks
        self._on_trade_open: Optional[Callable[[TradeRecord], None]] = None
        self._on_trade_close: Optional[Callable[[TradeRecord], None]] = None

        self._lock = RLock()

        # Ensure directory exists
        if self._config.persist_to_file:
            Path(self._config.journal_dir).mkdir(parents=True, exist_ok=True)

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        self._trade_counter += 1
        ts = int(time.time() * 1000)
        return f"trade_{ts}_{self._trade_counter}"

    def open_trade(
        self,
        symbol: str,
        strategy: str,
        direction: str,
        entry_price: float,
        entry_size: float,
        entry_order_id: str,
        stop_price: float = None,
        target_price: float = None,
        entry_slippage_bps: float = 0.0,
        event_id: str = None,
        regime: str = None,
        notes: str = ""
    ) -> TradeRecord:
        """
        Record a new trade entry.

        Args:
            symbol: Trading pair
            strategy: Strategy name
            direction: LONG or SHORT
            entry_price: Fill price
            entry_size: Position size
            entry_order_id: Exchange order ID
            stop_price: Stop loss price
            target_price: Take profit price
            entry_slippage_bps: Entry slippage in basis points
            event_id: Associated event ID
            regime: Market regime at entry
            notes: Additional notes

        Returns:
            TradeRecord for the new trade
        """
        with self._lock:
            trade_id = self._generate_trade_id()

            trade = TradeRecord(
                trade_id=trade_id,
                symbol=symbol,
                strategy=strategy,
                direction=direction,
                entry_time_ns=self._now_ns(),
                entry_price=entry_price,
                entry_size=entry_size,
                entry_order_id=entry_order_id,
                entry_slippage_bps=entry_slippage_bps,
                stop_price=stop_price,
                target_price=target_price,
                event_id=event_id,
                regime=regime,
                notes=notes
            )

            self._trades[trade_id] = trade
            self._open_trades[trade_id] = trade

            self._logger.info(
                f"TRADE OPEN: {trade_id} {direction} {symbol} "
                f"{entry_size} @ {entry_price} (strategy: {strategy})"
            )

            if self._on_trade_open:
                self._on_trade_open(trade)

            return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        exit_order_id: str = None,
        exit_slippage_bps: float = 0.0,
        fees: float = 0.0,
        notes: str = ""
    ) -> Optional[TradeRecord]:
        """
        Record trade exit.

        Args:
            trade_id: Trade to close
            exit_price: Exit fill price
            exit_reason: TARGET, STOP, MANUAL, TIMEOUT, etc.
            exit_order_id: Exchange order ID
            exit_slippage_bps: Exit slippage in basis points
            fees: Total fees for the trade
            notes: Additional notes

        Returns:
            Updated TradeRecord or None if not found
        """
        with self._lock:
            if trade_id not in self._trades:
                self._logger.warning(f"Trade not found: {trade_id}")
                return None

            trade = self._trades[trade_id]
            if trade.exit_time_ns is not None:
                self._logger.warning(f"Trade already closed: {trade_id}")
                return trade

            # Update exit details
            trade.exit_time_ns = self._now_ns()
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason
            trade.exit_order_id = exit_order_id
            trade.exit_slippage_bps = exit_slippage_bps
            trade.fees = fees

            # Calculate PnL
            if trade.direction == "LONG":
                trade.realized_pnl = (exit_price - trade.entry_price) * trade.entry_size
            else:
                trade.realized_pnl = (trade.entry_price - exit_price) * trade.entry_size

            trade.net_pnl = trade.realized_pnl - fees

            if notes:
                trade.notes = f"{trade.notes} | {notes}" if trade.notes else notes

            # Move from open to closed
            self._open_trades.pop(trade_id, None)
            self._closed_trades.append(trade)

            # Update daily stats
            self._update_daily_stats(trade)

            # Trim memory if needed
            self._trim_memory()

            self._logger.info(
                f"TRADE CLOSE: {trade_id} {trade.direction} {trade.symbol} "
                f"@ {exit_price} ({exit_reason}) PnL: {trade.net_pnl:.2f}"
            )

            if self._on_trade_close:
                self._on_trade_close(trade)

            # Persist to file
            if self._config.persist_to_file:
                self._persist_trade(trade)

            return trade

    def update_stop(self, trade_id: str, new_stop_price: float, stop_order_id: str = None):
        """Update stop price for an open trade."""
        with self._lock:
            if trade_id not in self._open_trades:
                return
            trade = self._open_trades[trade_id]
            trade.stop_price = new_stop_price
            if stop_order_id:
                trade.stop_order_id = stop_order_id

    def update_target(self, trade_id: str, new_target_price: float, target_order_id: str = None):
        """Update target price for an open trade."""
        with self._lock:
            if trade_id not in self._open_trades:
                return
            trade = self._open_trades[trade_id]
            trade.target_price = new_target_price
            if target_order_id:
                trade.target_order_id = target_order_id

    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Get a specific trade by ID."""
        with self._lock:
            return self._trades.get(trade_id)

    def get_open_trades(self) -> List[TradeRecord]:
        """Get all open trades."""
        with self._lock:
            return list(self._open_trades.values())

    def get_open_trade_for_symbol(self, symbol: str) -> Optional[TradeRecord]:
        """Get open trade for a specific symbol."""
        with self._lock:
            for trade in self._open_trades.values():
                if trade.symbol == symbol:
                    return trade
            return None

    def get_closed_trades(self, limit: int = 100) -> List[TradeRecord]:
        """Get recent closed trades."""
        with self._lock:
            return list(self._closed_trades[-limit:])

    def get_trades_by_strategy(self, strategy: str, limit: int = 100) -> List[TradeRecord]:
        """Get trades for a specific strategy."""
        with self._lock:
            matching = [
                t for t in self._closed_trades
                if t.strategy == strategy
            ]
            return matching[-limit:]

    def get_trades_by_symbol(self, symbol: str, limit: int = 100) -> List[TradeRecord]:
        """Get trades for a specific symbol."""
        with self._lock:
            matching = [
                t for t in self._closed_trades
                if t.symbol == symbol
            ]
            return matching[-limit:]

    def get_trades_since(self, since_ns: int) -> List[TradeRecord]:
        """Get trades since a specific timestamp."""
        with self._lock:
            return [
                t for t in self._closed_trades
                if t.entry_time_ns >= since_ns
            ]

    def get_today_trades(self) -> List[TradeRecord]:
        """Get today's trades."""
        today_start = self._get_day_start_ns()
        return self.get_trades_since(today_start)

    def _get_day_start_ns(self, offset_days: int = 0) -> int:
        """Get start of day in nanoseconds."""
        import datetime
        today = datetime.date.today() - datetime.timedelta(days=offset_days)
        start = datetime.datetime.combine(today, datetime.time.min)
        return int(start.timestamp() * 1_000_000_000)

    def _update_daily_stats(self, trade: TradeRecord):
        """Update daily statistics."""
        import datetime
        date_str = datetime.datetime.fromtimestamp(
            trade.entry_time_ns / 1_000_000_000
        ).strftime('%Y-%m-%d')

        if date_str not in self._daily_stats:
            self._daily_stats[date_str] = DailyStats(date=date_str)

        stats = self._daily_stats[date_str]
        stats.trades += 1
        stats.pnl += trade.realized_pnl
        stats.fees += trade.fees
        stats.net_pnl += trade.net_pnl

        if trade.outcome == TradeOutcome.WIN:
            stats.wins += 1
            stats.largest_win = max(stats.largest_win, trade.net_pnl)
        elif trade.outcome == TradeOutcome.LOSS:
            stats.losses += 1
            stats.largest_loss = min(stats.largest_loss, trade.net_pnl)

        if stats.trades > 0:
            stats.win_rate = stats.wins / stats.trades

    def get_daily_stats(self, date_str: str = None) -> Optional[DailyStats]:
        """Get daily statistics."""
        if date_str is None:
            import datetime
            date_str = datetime.date.today().strftime('%Y-%m-%d')
        with self._lock:
            return self._daily_stats.get(date_str)

    def get_summary(self) -> Dict:
        """Get trade journal summary."""
        with self._lock:
            closed = self._closed_trades
            wins = [t for t in closed if t.outcome == TradeOutcome.WIN]
            losses = [t for t in closed if t.outcome == TradeOutcome.LOSS]

            total_pnl = sum(t.net_pnl for t in closed)
            total_wins = sum(t.net_pnl for t in wins)
            total_losses = sum(t.net_pnl for t in losses)

            return {
                'total_trades': len(closed),
                'open_trades': len(self._open_trades),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': len(wins) / len(closed) if closed else 0,
                'total_pnl': total_pnl,
                'avg_win': total_wins / len(wins) if wins else 0,
                'avg_loss': total_losses / len(losses) if losses else 0,
                'profit_factor': abs(total_wins / total_losses) if total_losses else float('inf'),
                'largest_win': max((t.net_pnl for t in wins), default=0),
                'largest_loss': min((t.net_pnl for t in losses), default=0),
            }

    def _trim_memory(self):
        """Trim in-memory storage if needed."""
        max_trades = self._config.max_memory_trades
        if len(self._closed_trades) > max_trades:
            # Keep most recent
            self._closed_trades = self._closed_trades[-max_trades:]

    def _persist_trade(self, trade: TradeRecord):
        """Persist trade to file."""
        import datetime
        date_str = datetime.datetime.fromtimestamp(
            trade.entry_time_ns / 1_000_000_000
        ).strftime('%Y-%m-%d')

        filepath = Path(self._config.journal_dir) / f"trades_{date_str}.jsonl"

        try:
            with open(filepath, 'a') as f:
                f.write(json.dumps(trade.to_dict()) + '\n')
        except Exception as e:
            self._logger.error(f"Failed to persist trade: {e}")

    def load_from_file(self, date_str: str) -> List[TradeRecord]:
        """Load trades from file for a specific date."""
        filepath = Path(self._config.journal_dir) / f"trades_{date_str}.jsonl"

        if not filepath.exists():
            return []

        trades = []
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    data = json.loads(line.strip())
                    trade = self._dict_to_trade(data)
                    trades.append(trade)
        except Exception as e:
            self._logger.error(f"Failed to load trades: {e}")

        return trades

    def _dict_to_trade(self, data: Dict) -> TradeRecord:
        """Convert dictionary back to TradeRecord."""
        return TradeRecord(
            trade_id=data['trade_id'],
            symbol=data['symbol'],
            strategy=data['strategy'],
            direction=data['direction'],
            entry_time_ns=data['entry_time_ns'],
            entry_price=data['entry_price'],
            entry_size=data['entry_size'],
            entry_order_id=data['entry_order_id'],
            entry_slippage_bps=data.get('entry_slippage_bps', 0),
            exit_time_ns=data.get('exit_time_ns'),
            exit_price=data.get('exit_price'),
            exit_reason=data.get('exit_reason'),
            exit_order_id=data.get('exit_order_id'),
            exit_slippage_bps=data.get('exit_slippage_bps', 0),
            stop_price=data.get('stop_price'),
            target_price=data.get('target_price'),
            realized_pnl=data.get('realized_pnl', 0),
            fees=data.get('fees', 0),
            net_pnl=data.get('net_pnl', 0),
            event_id=data.get('event_id'),
            regime=data.get('regime'),
            notes=data.get('notes', ''),
        )

    def set_trade_open_callback(self, callback: Callable[[TradeRecord], None]):
        """Set callback for trade open events."""
        self._on_trade_open = callback

    def set_trade_close_callback(self, callback: Callable[[TradeRecord], None]):
        """Set callback for trade close events."""
        self._on_trade_close = callback
