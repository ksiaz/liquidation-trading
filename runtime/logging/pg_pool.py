"""
PostgreSQL Connection Pool.

Provides a thread-safe connection pool for all database access.
Replaces per-file SQLite connections with a shared PostgreSQL pool.
"""

import os
import psycopg2
import psycopg2.pool
import psycopg2.extras
from typing import Optional


# Module-level pool singleton
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def init_pool(
    host: str = None,
    port: int = None,
    dbname: str = None,
    user: str = None,
    password: str = None,
    minconn: int = 2,
    maxconn: int = 10,
):
    """Initialize the connection pool. Call once at startup.

    Reads from env vars if parameters not provided:
        PG_HOST (default: localhost)
        PG_PORT (default: 5432)
        PG_DB   (default: liquidation_trading)
        PG_USER (default: liqtrade)
        PG_PASS (default: liqtrade)
    """
    global _pool
    if _pool is not None:
        return  # Already initialized

    host = host or os.environ.get('PG_HOST', 'localhost')
    port = port or int(os.environ.get('PG_PORT', '5432'))
    dbname = dbname or os.environ.get('PG_DB', 'liquidation_trading')
    user = user or os.environ.get('PG_USER', 'liqtrade')
    password = password or os.environ.get('PG_PASS', 'liqtrade')

    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=minconn,
        maxconn=maxconn,
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )
    print(f"[PG] Pool initialized: {user}@{host}:{port}/{dbname} "
          f"(min={minconn}, max={maxconn})", flush=True)


def get_conn():
    """Borrow a connection from the pool.

    IMPORTANT: Always return with put_conn() when done.
    """
    if _pool is None:
        raise RuntimeError("[PG] Pool not initialized. Call init_pool() first.")
    conn = _pool.getconn()
    # Ensure autocommit is OFF (we manage transactions explicitly)
    conn.autocommit = False
    return conn


def put_conn(conn):
    """Return a connection to the pool."""
    if _pool is None:
        return
    try:
        # Reset any in-progress transaction
        conn.rollback()
    except Exception:
        pass
    _pool.putconn(conn)


def close_pool():
    """Close all connections and shut down the pool."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        print("[PG] Pool closed.", flush=True)


# =========================================================================
# SQL Adapters: translate SQLite-style SQL to PostgreSQL
# =========================================================================

class PgCursorAdapter:
    """Wraps psycopg2 cursor to accept SQLite-style SQL (? placeholders)."""

    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self.lastrowid = None

    def execute(self, sql, params=None):
        pg_sql = self._translate(sql)
        pg_params = self._coerce_params(params or ())
        self._cur.execute(pg_sql, pg_params)
        return self

    @staticmethod
    def _coerce_params(params):
        """Convert Python booleans to integers for SMALLINT columns."""
        if isinstance(params, (list, tuple)):
            return tuple(int(p) if isinstance(p, bool) else p for p in params)
        return params

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount

    @staticmethod
    def _translate(sql):
        """Convert SQLite SQL to PostgreSQL."""
        s = sql.replace('?', '%s')
        if 'INSERT OR IGNORE' in s:
            s = s.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
            s = s.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
        return s


class PgConnAdapter:
    """Wraps psycopg2 connection to look like sqlite3 connection.

    Used to feed PG connections into ResearchDatabase log_* methods
    that expect self.conn to be sqlite3-style.

    Args:
        pg_conn: Real psycopg2 connection
        commit_passthrough: If True, commit() calls real PG commit.
                           If False, commit() is a no-op (for BRD flush path).
    """

    def __init__(self, pg_conn, commit_passthrough=True):
        self._conn = pg_conn
        self._commit_passthrough = commit_passthrough
        self.row_factory = None  # Compatibility

    def cursor(self):
        return PgCursorAdapter(
            self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        )

    def commit(self):
        if self._commit_passthrough:
            self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur
