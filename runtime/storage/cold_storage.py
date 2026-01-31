"""
HLP24: Cold Storage.

Append-only raw data storage for historical analysis and backtesting.

Features:
- SQLite-based storage for reliability
- Efficient batch inserts
- Time-range queries
- Integer microseconds for precision
- Compression support for exports

Schema:
- market_snapshots: Periodic market state (OI, funding, prices, depth)
- trades: Individual trade records with liquidation flags
- events: Detected liquidation events with labels

Usage:
    storage = ColdStorage('data/cold_storage.db')

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

import sqlite3
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator
from contextlib import contextmanager
import threading


@dataclass
class StorageConfig:
    """Configuration for cold storage."""
    db_path: str = 'data/cold_storage.db'
    batch_size: int = 1000
    vacuum_interval_hours: int = 24
    enable_wal: bool = True  # Write-ahead logging for performance
    enable_compression: bool = False  # Future: compress on export


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

    Uses SQLite for reliability and simplicity.
    All timestamps stored as microseconds since epoch.
    All prices/sizes stored as integers (scaled by 1e8).
    """

    SCHEMA = {
        'market_snapshots': '''
            CREATE TABLE IF NOT EXISTS market_snapshots (
                ts_us INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                open_interest INTEGER,
                funding_rate INTEGER,
                mark_price INTEGER,
                index_price INTEGER,
                bid_depth_1pct INTEGER,
                ask_depth_1pct INTEGER,
                volume_24h INTEGER,
                PRIMARY KEY (ts_us, symbol)
            )
        ''',
        'trades': '''
            CREATE TABLE IF NOT EXISTS trades (
                ts_us INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                price INTEGER,
                size INTEGER,
                side TEXT,
                is_liquidation INTEGER DEFAULT 0,
                trade_id TEXT
            )
        ''',
        'events': '''
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                ts_start_us INTEGER NOT NULL,
                ts_end_us INTEGER,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT,
                metrics TEXT,
                label TEXT
            )
        ''',
    }

    INDEXES = [
        'CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_ts ON market_snapshots(symbol, ts_us)',
        'CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON trades(symbol, ts_us)',
        'CREATE INDEX IF NOT EXISTS idx_trades_liquidation ON trades(is_liquidation) WHERE is_liquidation = 1',
        'CREATE INDEX IF NOT EXISTS idx_events_symbol_ts ON events(symbol, ts_start_us)',
        'CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)',
    ]

    def __init__(
        self,
        config: StorageConfig = None,
        logger: logging.Logger = None,
    ):
        """
        Initialize cold storage.

        Args:
            config: Storage configuration
            logger: Logger instance
        """
        self._config = config or StorageConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._local = threading.local()

        # Ensure directory exists
        Path(self._config.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._config.db_path)
            if self._config.enable_wal:
                self._local.conn.execute('PRAGMA journal_mode=WAL')
            self._local.conn.execute('PRAGMA synchronous=NORMAL')
        return self._local.conn

    @contextmanager
    def _transaction(self):
        """Context manager for transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        """Initialize database schema."""
        with self._transaction() as conn:
            for table_sql in self.SCHEMA.values():
                conn.execute(table_sql)
            for index_sql in self.INDEXES:
                conn.execute(index_sql)

        self._logger.debug(f"Initialized cold storage at {self._config.db_path}")

    def insert_snapshot(self, snapshot: MarketSnapshot):
        """Insert single market snapshot."""
        with self._transaction() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO market_snapshots
                (ts_us, symbol, open_interest, funding_rate, mark_price,
                 index_price, bid_depth_1pct, ask_depth_1pct, volume_24h)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot.ts_us,
                snapshot.symbol,
                snapshot.open_interest,
                snapshot.funding_rate,
                snapshot.mark_price,
                snapshot.index_price,
                snapshot.bid_depth_1pct,
                snapshot.ask_depth_1pct,
                snapshot.volume_24h,
            ))

    def insert_snapshots_batch(self, snapshots: List[MarketSnapshot]):
        """Insert multiple snapshots efficiently."""
        if not snapshots:
            return

        with self._transaction() as conn:
            conn.executemany('''
                INSERT OR REPLACE INTO market_snapshots
                (ts_us, symbol, open_interest, funding_rate, mark_price,
                 index_price, bid_depth_1pct, ask_depth_1pct, volume_24h)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', [
                (s.ts_us, s.symbol, s.open_interest, s.funding_rate, s.mark_price,
                 s.index_price, s.bid_depth_1pct, s.ask_depth_1pct, s.volume_24h)
                for s in snapshots
            ])

        self._logger.debug(f"Inserted {len(snapshots)} snapshots")

    def insert_trade(self, trade: TradeRecord):
        """Insert single trade record."""
        with self._transaction() as conn:
            conn.execute('''
                INSERT INTO trades
                (ts_us, symbol, price, size, side, is_liquidation, trade_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade.ts_us,
                trade.symbol,
                trade.price,
                trade.size,
                trade.side,
                1 if trade.is_liquidation else 0,
                trade.trade_id,
            ))

    def insert_trades_batch(self, trades: List[TradeRecord]):
        """Insert multiple trades efficiently."""
        if not trades:
            return

        with self._transaction() as conn:
            conn.executemany('''
                INSERT INTO trades
                (ts_us, symbol, price, size, side, is_liquidation, trade_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', [
                (t.ts_us, t.symbol, t.price, t.size, t.side,
                 1 if t.is_liquidation else 0, t.trade_id)
                for t in trades
            ])

        self._logger.debug(f"Inserted {len(trades)} trades")

    def query_snapshots(
        self,
        symbol: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 10000,
    ) -> QueryResult:
        """
        Query market snapshots.

        Args:
            symbol: Filter by symbol (optional)
            start_ts: Start timestamp in microseconds (inclusive)
            end_ts: End timestamp in microseconds (exclusive)
            limit: Maximum rows to return

        Returns:
            QueryResult with list of MarketSnapshot
        """
        import time
        query_start = time.time()

        conditions = []
        params = []

        if symbol:
            conditions.append('symbol = ?')
            params.append(symbol)
        if start_ts is not None:
            conditions.append('ts_us >= ?')
            params.append(start_ts)
        if end_ts is not None:
            conditions.append('ts_us < ?')
            params.append(end_ts)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        conn = self._get_connection()
        cursor = conn.execute(f'''
            SELECT ts_us, symbol, open_interest, funding_rate, mark_price,
                   index_price, bid_depth_1pct, ask_depth_1pct, volume_24h
            FROM market_snapshots
            WHERE {where_clause}
            ORDER BY ts_us ASC
            LIMIT ?
        ''', params + [limit])

        rows = [MarketSnapshot.from_row(row) for row in cursor.fetchall()]
        query_time = (time.time() - query_start) * 1000

        return QueryResult(
            rows=rows,
            count=len(rows),
            start_ts=start_ts,
            end_ts=end_ts,
            query_time_ms=query_time,
        )

    def query_trades(
        self,
        symbol: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        liquidations_only: bool = False,
        limit: int = 10000,
    ) -> QueryResult:
        """
        Query trade records.

        Args:
            symbol: Filter by symbol (optional)
            start_ts: Start timestamp in microseconds
            end_ts: End timestamp in microseconds
            liquidations_only: Only return liquidation trades
            limit: Maximum rows to return

        Returns:
            QueryResult with list of TradeRecord
        """
        import time
        query_start = time.time()

        conditions = []
        params = []

        if symbol:
            conditions.append('symbol = ?')
            params.append(symbol)
        if start_ts is not None:
            conditions.append('ts_us >= ?')
            params.append(start_ts)
        if end_ts is not None:
            conditions.append('ts_us < ?')
            params.append(end_ts)
        if liquidations_only:
            conditions.append('is_liquidation = 1')

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        conn = self._get_connection()
        cursor = conn.execute(f'''
            SELECT ts_us, symbol, price, size, side, is_liquidation, trade_id
            FROM trades
            WHERE {where_clause}
            ORDER BY ts_us ASC
            LIMIT ?
        ''', params + [limit])

        rows = [TradeRecord.from_row(row) for row in cursor.fetchall()]
        query_time = (time.time() - query_start) * 1000

        return QueryResult(
            rows=rows,
            count=len(rows),
            start_ts=start_ts,
            end_ts=end_ts,
            query_time_ms=query_time,
        )

    def get_symbols(self) -> List[str]:
        """Get list of unique symbols in storage."""
        conn = self._get_connection()
        cursor = conn.execute('''
            SELECT DISTINCT symbol FROM market_snapshots
            UNION
            SELECT DISTINCT symbol FROM trades
        ''')
        return [row[0] for row in cursor.fetchall()]

    def get_time_range(self, symbol: Optional[str] = None) -> Optional[tuple]:
        """Get min/max timestamps for data."""
        conn = self._get_connection()

        if symbol:
            cursor = conn.execute('''
                SELECT MIN(ts_us), MAX(ts_us) FROM market_snapshots
                WHERE symbol = ?
            ''', (symbol,))
        else:
            cursor = conn.execute('''
                SELECT MIN(ts_us), MAX(ts_us) FROM market_snapshots
            ''')

        row = cursor.fetchone()
        if row and row[0] is not None:
            return (row[0], row[1])
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        conn = self._get_connection()

        snapshot_count = conn.execute(
            'SELECT COUNT(*) FROM market_snapshots'
        ).fetchone()[0]

        trade_count = conn.execute(
            'SELECT COUNT(*) FROM trades'
        ).fetchone()[0]

        liq_count = conn.execute(
            'SELECT COUNT(*) FROM trades WHERE is_liquidation = 1'
        ).fetchone()[0]

        db_size = Path(self._config.db_path).stat().st_size if \
            Path(self._config.db_path).exists() else 0

        return {
            'snapshot_count': snapshot_count,
            'trade_count': trade_count,
            'liquidation_count': liq_count,
            'db_size_bytes': db_size,
            'db_size_mb': db_size / (1024 * 1024),
            'symbols': self.get_symbols(),
            'time_range': self.get_time_range(),
        }

    def vacuum(self):
        """Optimize database storage."""
        conn = self._get_connection()
        conn.execute('VACUUM')
        self._logger.info("Database vacuumed")

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
