"""
Pytest configuration file.

Adds project root to Python path for imports.
Initializes PostgreSQL connection pool for DB-dependent tests.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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
except Exception:
    pass  # PG not available — tests that don't need DB will still work
