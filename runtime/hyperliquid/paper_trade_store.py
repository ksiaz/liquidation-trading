"""
Paper Trade Persistence Store.

Persists paper trades from LiquidationFadeExecutor to PostgreSQL
so they survive app restarts and can be analyzed.
"""

import time
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

from runtime.logging.pg_pool import get_conn, put_conn


@dataclass
class StoredTrade:
    """Trade record from database."""
    trade_id: str
    coin: str
    entry_price: float
    entry_time: float
    size: float
    liquidated_wallet: str
    liquidation_value: float
    take_profit_price: float
    stop_loss_price: float
    status: str
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None
    highest_price: Optional[float] = None
    breakeven_triggered: bool = False
    original_stop_loss: Optional[float] = None


class PaperTradeStore:
    """PostgreSQL persistence for paper trades."""

    def __init__(self, **kwargs):
        self._logger = logging.getLogger("PaperTradeStore")
        self._logger.info("Paper trade store initialized (PostgreSQL)")

    def save_trade(self, trade) -> str:
        """Save new trade to database."""
        trade_id = str(uuid.uuid4())[:8]

        conn = get_conn()
        try:
            conn.cursor().execute("""
                INSERT INTO paper_trades (
                    trade_id, coin, entry_price, entry_time, size,
                    liquidated_wallet, liquidation_value,
                    take_profit_price, stop_loss_price, status,
                    highest_price, breakeven_triggered, original_stop_loss
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trade_id,
                trade.coin,
                trade.entry_price,
                trade.entry_time,
                trade.size,
                trade.liquidated_wallet,
                trade.liquidation_value,
                trade.take_profit_price,
                trade.stop_loss_price,
                trade.status.value if hasattr(trade.status, 'value') else str(trade.status),
                trade.highest_price,
                1 if trade.breakeven_triggered else 0,
                trade.original_stop_loss
            ))
            conn.commit()
            self._logger.info(f"Saved trade {trade_id}: {trade.coin} @ ${trade.entry_price:.4f}")
        except Exception as e:
            self._logger.error(f"Failed to save trade: {e}")
            conn.rollback()
            raise
        finally:
            put_conn(conn)

        return trade_id

    def update_trade(self, trade_id: str, trade):
        """Update existing trade (status, exit, P&L)."""
        conn = get_conn()
        try:
            conn.cursor().execute("""
                UPDATE paper_trades SET
                    status = %s,
                    exit_price = %s,
                    exit_time = %s,
                    pnl = %s,
                    highest_price = %s,
                    breakeven_triggered = %s,
                    original_stop_loss = %s
                WHERE trade_id = %s
            """, (
                trade.status.value if hasattr(trade.status, 'value') else str(trade.status),
                trade.exit_price,
                trade.exit_time,
                trade.pnl,
                trade.highest_price,
                1 if trade.breakeven_triggered else 0,
                trade.original_stop_loss,
                trade_id
            ))
            conn.commit()

            if trade.pnl is not None:
                self._logger.info(
                    f"Updated trade {trade_id}: {trade.status.value if hasattr(trade.status, 'value') else trade.status} "
                    f"P&L=${trade.pnl:.2f}"
                )
        except Exception as e:
            self._logger.error(f"Failed to update trade {trade_id}: {e}")
            conn.rollback()
        finally:
            put_conn(conn)

    def get_active_trades(self) -> List[StoredTrade]:
        """Load all active (non-closed) trades."""
        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM paper_trades
                WHERE status IN ('PENDING', 'ENTERED', 'pending', 'entered')
                ORDER BY entry_time DESC
            """)

            trades = []
            for row in cur.fetchall():
                trades.append(StoredTrade(
                    trade_id=row['trade_id'],
                    coin=row['coin'],
                    entry_price=row['entry_price'],
                    entry_time=row['entry_time'],
                    size=row['size'],
                    liquidated_wallet=row['liquidated_wallet'],
                    liquidation_value=row['liquidation_value'],
                    take_profit_price=row['take_profit_price'],
                    stop_loss_price=row['stop_loss_price'],
                    status=row['status'],
                    exit_price=row['exit_price'],
                    exit_time=row['exit_time'],
                    pnl=row['pnl'],
                    highest_price=row['highest_price'],
                    breakeven_triggered=bool(row['breakeven_triggered']),
                    original_stop_loss=row['original_stop_loss']
                ))
            return trades
        finally:
            put_conn(conn)

    def get_trade_history(self, limit: int = 100, coin: str = None) -> List[StoredTrade]:
        """Get recent closed trades."""
        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if coin:
                cur.execute("""
                    SELECT * FROM paper_trades
                    WHERE coin = %s AND status NOT IN ('PENDING', 'ENTERED', 'pending', 'entered')
                    ORDER BY exit_time DESC
                    LIMIT %s
                """, (coin, limit))
            else:
                cur.execute("""
                    SELECT * FROM paper_trades
                    WHERE status NOT IN ('PENDING', 'ENTERED', 'pending', 'entered')
                    ORDER BY exit_time DESC
                    LIMIT %s
                """, (limit,))

            trades = []
            for row in cur.fetchall():
                trades.append(StoredTrade(
                    trade_id=row['trade_id'],
                    coin=row['coin'],
                    entry_price=row['entry_price'],
                    entry_time=row['entry_time'],
                    size=row['size'],
                    liquidated_wallet=row['liquidated_wallet'],
                    liquidation_value=row['liquidation_value'],
                    take_profit_price=row['take_profit_price'],
                    stop_loss_price=row['stop_loss_price'],
                    status=row['status'],
                    exit_price=row['exit_price'],
                    exit_time=row['exit_time'],
                    pnl=row['pnl'],
                    highest_price=row['highest_price'],
                    breakeven_triggered=bool(row['breakeven_triggered']),
                    original_stop_loss=row['original_stop_loss']
                ))
            return trades
        finally:
            put_conn(conn)

    def get_daily_stats(self, date: str = None) -> Dict:
        """Get stats for a day (default: today)."""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM paper_trade_stats WHERE date = %s",
                (date,)
            )
            row = cur.fetchone()

            if row:
                return {
                    'date': row['date'],
                    'total_trades': row['total_trades'],
                    'winning_trades': row['winning_trades'],
                    'losing_trades': row['losing_trades'],
                    'total_pnl': row['total_pnl'],
                    'largest_win': row['largest_win'],
                    'largest_loss': row['largest_loss'],
                    'win_rate': row['winning_trades'] / row['total_trades'] * 100 if row['total_trades'] > 0 else 0
                }
            else:
                return {
                    'date': date,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0,
                    'largest_win': 0,
                    'largest_loss': 0,
                    'win_rate': 0
                }
        finally:
            put_conn(conn)

    def update_daily_stats(self, pnl: float):
        """Update daily stats when a trade closes."""
        date = datetime.now().strftime('%Y-%m-%d')
        now = time.time()
        won = pnl > 0

        conn = get_conn()
        try:
            cur = conn.cursor()

            # Get current stats
            cur.execute(
                "SELECT date FROM paper_trade_stats WHERE date = %s",
                (date,)
            )
            row = cur.fetchone()

            if row:
                cur.execute("""
                    UPDATE paper_trade_stats SET
                        total_trades = total_trades + 1,
                        winning_trades = winning_trades + %s,
                        losing_trades = losing_trades + %s,
                        total_pnl = total_pnl + %s,
                        largest_win = GREATEST(largest_win, %s),
                        largest_loss = LEAST(largest_loss, %s),
                        updated_at = %s
                    WHERE date = %s
                """, (
                    1 if won else 0,
                    0 if won else 1,
                    pnl,
                    pnl if won else 0,
                    pnl if not won else 0,
                    now,
                    date
                ))
            else:
                cur.execute("""
                    INSERT INTO paper_trade_stats (
                        date, total_trades, winning_trades, losing_trades,
                        total_pnl, largest_win, largest_loss, updated_at
                    ) VALUES (%s, 1, %s, %s, %s, %s, %s, %s)
                """, (
                    date,
                    1 if won else 0,
                    0 if won else 1,
                    pnl,
                    pnl if won else 0,
                    pnl if not won else 0,
                    now
                ))

            conn.commit()
        finally:
            put_conn(conn)

    def get_all_time_stats(self) -> Dict:
        """Get aggregate stats across all time."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losing_trades,
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COALESCE(MAX(pnl), 0) as largest_win,
                    COALESCE(MIN(pnl), 0) as largest_loss,
                    COALESCE(AVG(pnl), 0) as avg_pnl
                FROM paper_trades
                WHERE pnl IS NOT NULL
            """)

            row = cur.fetchone()

            if row:
                total = row[0] or 0
                wins = row[1] or 0
                return {
                    'total_trades': total,
                    'winning_trades': wins,
                    'losing_trades': row[2] or 0,
                    'total_pnl': row[3] or 0,
                    'largest_win': row[4] or 0,
                    'largest_loss': row[5] or 0,
                    'avg_pnl': row[6] or 0,
                    'win_rate': (wins / total * 100) if total > 0 else 0
                }
            else:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0,
                    'largest_win': 0,
                    'largest_loss': 0,
                    'avg_pnl': 0,
                    'win_rate': 0
                }
        finally:
            put_conn(conn)
