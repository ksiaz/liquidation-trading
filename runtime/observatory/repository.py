"""
Observatory Repository - Read-Only Database Access.

CONSTITUTIONAL CONSTRAINT: All methods are SELECT-only.
No INSERT, UPDATE, DELETE operations permitted.

PostgreSQL backend: Uses shared connection pool.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

from runtime.logging.pg_pool import get_conn, put_conn


class ObservatoryRepository:
    """Read-only repository for observatory data access.

    Provides SELECT-only access to the shared PostgreSQL database.
    """

    def __init__(self, execution_db: str = None):
        """Initialize repository.

        Args:
            execution_db: Ignored (kept for API compatibility). Uses PG pool.
        """
        pass

    def _safe_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute query with error handling.

        Returns empty list if table or column doesn't exist.
        Converts ? placeholders to %s for PG compatibility.
        """
        pg_query = query.replace('?', '%s')
        conn = get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(pg_query, params)
            return [dict(r) for r in cur.fetchall()]
        except psycopg2.Error as e:
            error_msg = str(e)
            if 'does not exist' in error_msg:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return []
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            put_conn(conn)

    # =========================================
    # Execution Cycles
    # =========================================

    def get_recent_cycles(self, limit: int = 100) -> List[Dict]:
        """Get recent execution cycles."""
        return self._safe_query('''
            SELECT * FROM execution_cycles
            ORDER BY timestamp DESC LIMIT %s
        ''', (limit,))

    def get_cycle(self, cycle_id: int) -> Optional[Dict]:
        """Get single execution cycle by ID."""
        results = self._safe_query(
            'SELECT * FROM execution_cycles WHERE id = %s',
            (cycle_id,)
        )
        return results[0] if results else None

    # =========================================
    # Mandates
    # =========================================

    def get_mandates(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
        mandate_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get mandate history with optional filters."""
        query = 'SELECT * FROM mandates WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND symbol = %s'
            params.append(symbol)
        if since:
            query += ' AND timestamp >= %s'
            params.append(since.timestamp())
        if mandate_type:
            query += ' AND mandate_type = %s'
            params.append(mandate_type)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    def get_mandate(self, mandate_id: int) -> Optional[Dict]:
        """Get single mandate by ID."""
        results = self._safe_query(
            'SELECT * FROM mandates WHERE id = %s',
            (mandate_id,)
        )
        return results[0] if results else None

    def count_mandates_by_type(self, hours: int = 24) -> Dict[str, int]:
        """Count mandates by type in time window."""
        since = datetime.now() - timedelta(hours=hours)
        results = self._safe_query('''
            SELECT mandate_type, COUNT(*) as count
            FROM mandates
            WHERE timestamp >= %s
            GROUP BY mandate_type
        ''', (since.timestamp(),))
        return {r['mandate_type']: r['count'] for r in results}

    # =========================================
    # Arbitration Rounds
    # =========================================

    def get_arbitration_rounds(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get arbitration round history."""
        query = 'SELECT * FROM arbitration_rounds WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND symbol = %s'
            params.append(symbol)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    # =========================================
    # M2 Nodes (Zones)
    # =========================================

    def get_active_zones(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get active M2 supply/demand zones."""
        query = '''
            SELECT * FROM m2_nodes
            WHERE invalidated_at IS NULL
        '''
        params: List[Any] = []

        if symbol:
            query += ' AND symbol = %s'
            params.append(symbol)

        query += ' ORDER BY created_at DESC'

        return self._safe_query(query, tuple(params))

    def get_zone_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get zone history including invalidated zones."""
        query = 'SELECT * FROM m2_nodes WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND symbol = %s'
            params.append(symbol)

        query += ' ORDER BY created_at DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    # =========================================
    # Positions
    # =========================================

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get current positions from hl_positions."""
        query = 'SELECT * FROM hl_positions WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND coin = %s'
            params.append(symbol)

        query += ' ORDER BY timestamp DESC'

        return self._safe_query(query, tuple(params))

    def get_position_proximity(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get liquidation proximity records."""
        query = 'SELECT * FROM hl_liquidation_proximity WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND coin = %s'
            params.append(symbol)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    # =========================================
    # Liquidations
    # =========================================

    def get_liquidations(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
        side: Optional[str] = None,
        limit: int = 500
    ) -> List[Dict]:
        """Get liquidation events."""
        query = 'SELECT * FROM liquidation_events WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND symbol = %s'
            params.append(symbol)
        if since:
            query += ' AND timestamp >= %s'
            params.append(since.timestamp())
        if side:
            query += ' AND side = %s'
            params.append(side)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    def get_cascade_events(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get cascade liquidation events."""
        query = 'SELECT * FROM hl_cascade_events WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND coin = %s'
            params.append(symbol)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    # =========================================
    # Market Data
    # =========================================

    def get_candles(
        self,
        symbol: str,
        since: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """Get OHLC candle data."""
        query = 'SELECT * FROM ohlc_candles WHERE symbol = %s'
        params: List[Any] = [symbol]

        if since:
            query += ' AND timestamp >= %s'
            params.append(since.timestamp())

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    def get_mark_prices(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get mark price snapshots."""
        query = 'SELECT * FROM mark_prices WHERE 1=1'
        params: List[Any] = []

        if symbol:
            query += ' AND symbol = %s'
            params.append(symbol)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    # =========================================
    # System State
    # =========================================

    def get_catastrophe_events(self, limit: int = 100) -> List[Dict]:
        """Get system catastrophe events."""
        return self._safe_query('''
            SELECT * FROM hl_catastrophe_events
            ORDER BY ts_ns DESC LIMIT %s
        ''', (limit,))

    def get_gating_decisions(self, limit: int = 100) -> List[Dict]:
        """Get execution gating decisions."""
        return self._safe_query('''
            SELECT * FROM hl_gating_decisions
            ORDER BY ts_ns DESC LIMIT %s
        ''', (limit,))

    def get_kill_switch_state(self) -> Optional[Dict]:
        """Get current kill switch state."""
        results = self._safe_query(
            'SELECT * FROM hl_kill_switch_state WHERE id = 1'
        )
        return results[0] if results else None

    # =========================================
    # Statistics
    # =========================================

    def get_table_counts(self) -> Dict[str, int]:
        """Get row counts for main tables."""
        tables = [
            'execution_cycles', 'mandates', 'arbitration_rounds',
            'm2_nodes', 'liquidation_events', 'hl_positions'
        ]
        counts = {}
        for table in tables:
            try:
                results = self._safe_query(f'SELECT COUNT(*) as cnt FROM {table}')
                counts[table] = results[0]['cnt'] if results else 0
            except Exception:
                counts[table] = 0
        return counts

    # =========================================
    # Ghost Trades (Paper Trading)
    # =========================================

    def get_ghost_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get ghost trades (paper trades)."""
        query = '''
            SELECT id, trade_id, cycle_id, symbol, side, quantity, price,
                   timestamp, position_side, is_entry, pnl, account_balance_after,
                   winning_policy_name, holding_duration_sec, exit_reason, created_at
            FROM ghost_trades
        '''
        params = []

        if symbol:
            query += ' WHERE symbol = %s'
            params.append(symbol)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        return self._safe_query(query, tuple(params))

    def get_ghost_summary(self) -> Dict:
        """Get ghost trading summary statistics."""
        trades = self._safe_query('''
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_entry = 1 THEN 1 ELSE 0 END) as total_entries,
                SUM(CASE WHEN is_entry = 0 THEN 1 ELSE 0 END) as total_exits,
                SUM(CASE WHEN pnl IS NOT NULL THEN pnl ELSE 0 END) as total_realized_pnl,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                MAX(account_balance_after) as current_balance
            FROM ghost_trades
        ''')

        if not trades or not trades[0]:
            return {
                'total_trades': 0,
                'total_entries': 0,
                'total_exits': 0,
                'total_realized_pnl': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate_pct': 0.0,
                'current_balance': 1000.0
            }

        row = trades[0]
        total_exits = row['total_exits'] or 0
        winning = row['winning_trades'] or 0

        return {
            'total_trades': row['total_trades'] or 0,
            'total_entries': row['total_entries'] or 0,
            'total_exits': total_exits,
            'total_realized_pnl': row['total_realized_pnl'] or 0.0,
            'winning_trades': winning,
            'losing_trades': row['losing_trades'] or 0,
            'win_rate_pct': (winning / total_exits * 100) if total_exits > 0 else 0.0,
            'current_balance': row['current_balance'] or 1000.0
        }
