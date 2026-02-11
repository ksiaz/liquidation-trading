"""
HLP24: Cold Storage.

Append-only raw data storage for historical analysis and backtesting.

Features:
- PostgreSQL-based storage for reliability
- Efficient batch inserts
- Time-range queries
- Integer microseconds for precision

Schema:
- cold_market_snapshots: Periodic market state (OI, funding, prices, depth)
- cold_trades: Individual trade records with liquidation flags
- cold_events: Detected liquidation events with labels

Usage:
    storage = ColdStorage()

    # Store market data
    snapshot = MarketSnapshot(
        ts_us=int(time.time() * 1_000_000),
        symbol='BTC-PERP',
        open_interest=1_000_000,
        funding_rate=0.0001,
        mark_price=50000_00000000,  # 8 decimal places
    )
    storage.insert_snapshot(snapshot)

    # Query historical data
    snapshots = storage.query_snapshots(
        symbol='BTC-PERP',
        start_ts=start_us,
        end_ts=end_us,
    )
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

from runtime.logging.pg_pool import get_conn, put_conn


@dataclass
class StorageConfig:
    """Configuration for cold storage."""
    batch_size: int = 1000


@dataclass
class MarketSnapshot:
    """Market state snapshot for storage."""
    ts_us: int                      # Timestamp in microseconds
    symbol: str                     # Trading symbol
    open_interest: int              # OI in base units (scaled)
    funding_rate: int               # Funding rate (scaled by 1e8)
    mark_price: int                 # Mark price (scaled by 1e8)
    index_price: int = 0            # Index price (scaled by 1e8)
    bid_depth_1pct: int = 0         # Bid depth within 1% (scaled)
    ask_depth_1pct: int = 0         # Ask depth within 1% (scaled)
    volume_24h: int = 0             # 24h volume (scaled)

    @classmethod
    def from_row(cls, row: tuple) -> 'MarketSnapshot':
        """Create from database row."""
        return cls(
            ts_us=row[0],
            symbol=row[1],
            open_interest=row[2],
            funding_rate=row[3],
            mark_price=row[4],
            index_price=row[5] if len(row) > 5 else 0,
            bid_depth_1pct=row[6] if len(row) > 6 else 0,
            ask_depth_1pct=row[7] if len(row) > 7 else 0,
            volume_24h=row[8] if len(row) > 8 else 0,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ts_us': self.ts_us,
            'symbol': self.symbol,
            'open_interest': self.open_interest,
            'funding_rate': self.funding_rate,
            'mark_price': self.mark_price,
            'index_price': self.index_price,
            'bid_depth_1pct': self.bid_depth_1pct,
            'ask_depth_1pct': self.ask_depth_1pct,
            'volume_24h': self.volume_24h,
        }


@dataclass
class TradeRecord:
    """Individual trade record for storage."""
    ts_us: int                      # Timestamp in microseconds
    symbol: str                     # Trading symbol
    price: int                      # Price (scaled by 1e8)
    size: int                       # Size (scaled by 1e8)
    side: str                       # 'buy' or 'sell'
    is_liquidation: bool = False   # Whether this was a liquidation
    trade_id: str = ''              # Exchange trade ID

    @classmethod
    def from_row(cls, row: tuple) -> 'TradeRecord':
        """Create from database row."""
        return cls(
            ts_us=row[0],
            symbol=row[1],
            price=row[2],
            size=row[3],
            side=row[4],
            is_liquidation=bool(row[5]) if len(row) > 5 else False,
            trade_id=row[6] if len(row) > 6 else '',
        )


@dataclass
class QueryResult:
    """Result of a query with metadata."""
    rows: List[Any]
    count: int
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    query_time_ms: float = 0.0


class ColdStorage:
    """
    Append-only cold storage for market data.

    Uses PostgreSQL for reliability and concurrency.
    All timestamps stored as microseconds since epoch.
    All prices/sizes stored as integers (scaled by 1e8).
    """

    def __init__(
        self,
        config: StorageConfig = None,
        logger: logging.Logger = None,
        **kwargs,
    ):
        self._config = config or StorageConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._logger.debug("Initialized cold storage (PostgreSQL)")

    @contextmanager
    def _transaction(self):
        """Context manager for transactions."""
        conn = get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            put_conn(conn)
            raise
        else:
            put_conn(conn)

    def insert_snapshot(self, snapshot: MarketSnapshot):
        """Insert single market snapshot."""
        with self._transaction() as conn:
            conn.cursor().execute('''
                INSERT INTO cold_market_snapshots
                (ts_us, symbol, open_interest, funding_rate, mark_price,
                 index_price, bid_depth_1pct, ask_depth_1pct, volume_24h)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ts_us, symbol) DO UPDATE SET
                    open_interest = EXCLUDED.open_interest,
                    funding_rate = EXCLUDED.funding_rate,
                    mark_price = EXCLUDED.mark_price,
                    index_price = EXCLUDED.index_price,
                    bid_depth_1pct = EXCLUDED.bid_depth_1pct,
                    ask_depth_1pct = EXCLUDED.ask_depth_1pct,
                    volume_24h = EXCLUDED.volume_24h
            ''', (
                snapshot.ts_us, snapshot.symbol, snapshot.open_interest,
                snapshot.funding_rate, snapshot.mark_price, snapshot.index_price,
                snapshot.bid_depth_1pct, snapshot.ask_depth_1pct, snapshot.volume_24h,
            ))

    def insert_snapshots_batch(self, snapshots: List[MarketSnapshot]):
        """Insert multiple snapshots efficiently."""
        if not snapshots:
            return

        with self._transaction() as conn:
            cur = conn.cursor()
            for s in snapshots:
                cur.execute('''
                    INSERT INTO cold_market_snapshots
                    (ts_us, symbol, open_interest, funding_rate, mark_price,
                     index_price, bid_depth_1pct, ask_depth_1pct, volume_24h)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ts_us, symbol) DO UPDATE SET
                        open_interest = EXCLUDED.open_interest,
                        funding_rate = EXCLUDED.funding_rate,
                        mark_price = EXCLUDED.mark_price,
                        index_price = EXCLUDED.index_price,
                        bid_depth_1pct = EXCLUDED.bid_depth_1pct,
                        ask_depth_1pct = EXCLUDED.ask_depth_1pct,
                        volume_24h = EXCLUDED.volume_24h
                ''', (
                    s.ts_us, s.symbol, s.open_interest, s.funding_rate, s.mark_price,
                    s.index_price, s.bid_depth_1pct, s.ask_depth_1pct, s.volume_24h,
                ))

        self._logger.debug(f"Inserted {len(snapshots)} snapshots")

    def insert_trade(self, trade: TradeRecord):
        """Insert single trade record."""
        with self._transaction() as conn:
            conn.cursor().execute('''
                INSERT INTO cold_trades
                (ts_us, symbol, price, size, side, is_liquidation, trade_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                trade.ts_us, trade.symbol, trade.price, trade.size,
                trade.side, 1 if trade.is_liquidation else 0, trade.trade_id,
            ))

    def insert_trades_batch(self, trades: List[TradeRecord]):
        """Insert multiple trades efficiently."""
        if not trades:
            return

        with self._transaction() as conn:
            cur = conn.cursor()
            for t in trades:
                cur.execute('''
                    INSERT INTO cold_trades
                    (ts_us, symbol, price, size, side, is_liquidation, trade_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    t.ts_us, t.symbol, t.price, t.size, t.side,
                    1 if t.is_liquidation else 0, t.trade_id,
                ))

        self._logger.debug(f"Inserted {len(trades)} trades")

    def query_snapshots(
        self,
        symbol: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 10000,
    ) -> QueryResult:
        """Query market snapshots."""
        import time
        query_start = time.time()

        conditions = []
        params = []

        if symbol:
            conditions.append('symbol = %s')
            params.append(symbol)
        if start_ts is not None:
            conditions.append('ts_us >= %s')
            params.append(start_ts)
        if end_ts is not None:
            conditions.append('ts_us < %s')
            params.append(end_ts)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(f'''
                SELECT ts_us, symbol, open_interest, funding_rate, mark_price,
                       index_price, bid_depth_1pct, ask_depth_1pct, volume_24h
                FROM cold_market_snapshots
                WHERE {where_clause}
                ORDER BY ts_us ASC
                LIMIT %s
            ''', params + [limit])

            rows = [MarketSnapshot.from_row(row) for row in cur.fetchall()]
            query_time = (time.time() - query_start) * 1000

            return QueryResult(
                rows=rows,
                count=len(rows),
                start_ts=start_ts,
                end_ts=end_ts,
                query_time_ms=query_time,
            )
        finally:
            put_conn(conn)

    def query_trades(
        self,
        symbol: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        liquidations_only: bool = False,
        limit: int = 10000,
    ) -> QueryResult:
        """Query trade records."""
        import time
        query_start = time.time()

        conditions = []
        params = []

        if symbol:
            conditions.append('symbol = %s')
            params.append(symbol)
        if start_ts is not None:
            conditions.append('ts_us >= %s')
            params.append(start_ts)
        if end_ts is not None:
            conditions.append('ts_us < %s')
            params.append(end_ts)
        if liquidations_only:
            conditions.append('is_liquidation = 1')

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(f'''
                SELECT ts_us, symbol, price, size, side, is_liquidation, trade_id
                FROM cold_trades
                WHERE {where_clause}
                ORDER BY ts_us ASC
                LIMIT %s
            ''', params + [limit])

            rows = [TradeRecord.from_row(row) for row in cur.fetchall()]
            query_time = (time.time() - query_start) * 1000

            return QueryResult(
                rows=rows,
                count=len(rows),
                start_ts=start_ts,
                end_ts=end_ts,
                query_time_ms=query_time,
            )
        finally:
            put_conn(conn)

    def get_symbols(self) -> List[str]:
        """Get list of unique symbols in storage."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute('''
                SELECT DISTINCT symbol FROM cold_market_snapshots
                UNION
                SELECT DISTINCT symbol FROM cold_trades
            ''')
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_time_range(self, symbol: Optional[str] = None) -> Optional[tuple]:
        """Get min/max timestamps for data."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            if symbol:
                cur.execute('''
                    SELECT MIN(ts_us), MAX(ts_us) FROM cold_market_snapshots
                    WHERE symbol = %s
                ''', (symbol,))
            else:
                cur.execute('''
                    SELECT MIN(ts_us), MAX(ts_us) FROM cold_market_snapshots
                ''')

            row = cur.fetchone()
            if row and row[0] is not None:
                return (row[0], row[1])
            return None
        finally:
            put_conn(conn)

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        conn = get_conn()
        try:
            cur = conn.cursor()

            cur.execute('SELECT COUNT(*) FROM cold_market_snapshots')
            snapshot_count = cur.fetchone()[0]

            cur.execute('SELECT COUNT(*) FROM cold_trades')
            trade_count = cur.fetchone()[0]

            cur.execute('SELECT COUNT(*) FROM cold_trades WHERE is_liquidation = 1')
            liq_count = cur.fetchone()[0]

            return {
                'snapshot_count': snapshot_count,
                'trade_count': trade_count,
                'liquidation_count': liq_count,
                'symbols': self.get_symbols(),
                'time_range': self.get_time_range(),
            }
        finally:
            put_conn(conn)

    def close(self):
        """No-op — pool manages connections."""
        pass
