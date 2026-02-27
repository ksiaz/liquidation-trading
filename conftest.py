"""
Root pytest conftest — applies to ALL test paths (tests/, runtime/*/tests/).

Initializes PG pool and cleans test-contaminated tables after every test
to protect live paper-trade state.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Track whether PG pool is available
_pg_available = False

# Initialize PostgreSQL pool once for all tests
try:
    from runtime.logging.pg_pool import init_pool, _pool
    if _pool is None:
        init_pool()
        from runtime.logging.pg_pool import get_conn, put_conn
        from runtime.logging.pg_schema import ensure_schema
        conn = get_conn()
        ensure_schema(conn)
        put_conn(conn)
    _pg_available = True
except Exception:
    pass  # PG not available — tests that don't need DB will still work


# Tables that tests write to and must be cleaned after each test
_TEST_CONTAMINATED_TABLES = [
    "positions",
]


@pytest.fixture(autouse=True)
def _clean_test_tables_after():
    """Clean tables that tests contaminate, after every test."""
    yield
    if not _pg_available:
        return
    try:
        from runtime.logging.pg_pool import get_conn, put_conn
        conn = get_conn()
        try:
            cur = conn.cursor()
            for table in _TEST_CONTAMINATED_TABLES:
                cur.execute(f"DELETE FROM {table}")
            conn.commit()
        finally:
            put_conn(conn)
    except Exception:
        pass
