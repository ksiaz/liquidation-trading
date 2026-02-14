"""
PostgreSQL Buffered Database — Lockless Write Batching.

Replaces BufferedResearchDatabase. Same external API, but:
- NO _db_lock — PostgreSQL MVCC handles concurrency
- Flush and prune run on SEPARATE pool connections (zero contention)
- Prune no longer blocks writes (was 25-50 min with SQLite)

Uses a connection adapter to reuse existing ResearchDatabase log_* methods
by translating SQLite SQL (? placeholders) to PostgreSQL (%s) on the fly.
"""

import threading
import time
import queue
import json
import sys
from typing import Any, Optional

from runtime.logging.pg_pool import get_conn, put_conn, PgCursorAdapter, PgConnAdapter


class PgBufferedResearchDatabase:
    """PostgreSQL buffered writer. Same API as BufferedResearchDatabase.

    Key difference: NO _db_lock. PostgreSQL MVCC means:
    - _do_flush() uses one pool connection
    - prune_safe() uses a DIFFERENT pool connection
    - read_sql() uses a DIFFERENT pool connection
    - All run concurrently without blocking each other
    """

    def __init__(
        self,
        flush_interval_sec: float = 1.0,
        max_buffer_size: int = 1000,
        enable_high_frequency_logs: bool = False,
    ):
        self._flush_interval = flush_interval_sec
        self._max_buffer_size = max_buffer_size
        self._enable_high_freq = enable_high_frequency_logs

        # Write buffer
        self._buffer = queue.Queue()

        # Local cycle ID counter — initialized from PG MAX(id)
        self._cycle_counter = self._init_cycle_counter()
        self._cycle_lock = threading.Lock()

        # Background flush thread
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

        # Stats
        self._writes_buffered = 0
        self._writes_flushed = 0
        self._flushes_count = 0

        # Compatibility: some code accesses .conn for schema info
        self.conn = None

    @staticmethod
    def _init_cycle_counter() -> int:
        """Read MAX(id) from execution_cycles so counter continues from last ID."""
        try:
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT COALESCE(MAX(id), 0) FROM execution_cycles")
                row = cur.fetchone()
                max_id = row[0] if row else 0
                print(f"[PG-BRD] Cycle counter initialized from MAX(id)={max_id}",
                      flush=True)
                return max_id
            finally:
                put_conn(conn)
        except Exception as e:
            print(f"[PG-BRD] Could not read MAX(id), starting at 0: {e}",
                  file=sys.stderr, flush=True)
            return 0

    def _get_next_cycle_id(self) -> int:
        with self._cycle_lock:
            self._cycle_counter += 1
            return self._cycle_counter

    @staticmethod
    def _make_db_shell(conn):
        """Create a thread-local ResearchDatabase shell bound to a PG connection.

        Each caller (flush thread, passthrough, etc.) gets its OWN shell.
        This prevents the race condition where flush and passthrough
        clobbered each other's self._db.conn.
        """
        from runtime.logging.execution_db import ResearchDatabase
        db = object.__new__(ResearchDatabase)
        db.conn = PgConnAdapter(conn, commit_passthrough=False)
        db.db_path = None
        return db

    def _flush_loop(self):
        last_flush = time.time()
        while self._running:
            time.sleep(0.1)
            now = time.time()
            should_flush = (
                now - last_flush >= self._flush_interval
                or self._buffer.qsize() >= self._max_buffer_size
            )
            if should_flush and not self._buffer.empty():
                self._do_flush()
                last_flush = now

        # Final flush on shutdown
        if not self._buffer.empty():
            self._do_flush()

    def _do_flush(self):
        """Flush buffered writes using a pool connection. NO LOCK."""
        writes = []
        while True:
            try:
                writes.append(self._buffer.get_nowait())
            except queue.Empty:
                break

        if not writes:
            return

        conn = get_conn()
        try:
            # Each flush gets its OWN db shell — no shared state with passthrough
            db_shell = self._make_db_shell(conn)

            errors = 0
            for method_name, args, kwargs in writes:
                try:
                    if method_name == '__raw_sql__':
                        sql, params = args
                        pg_sql = sql.replace('?', '%s')
                        pg_params = PgCursorAdapter._coerce_params(params)
                        if pg_params:
                            conn.cursor().execute(pg_sql, pg_params)
                        else:
                            conn.cursor().execute(pg_sql)
                    else:
                        method = getattr(db_shell, method_name, None)
                        if method:
                            clean_kwargs = {}
                            for k, v in kwargs.items():
                                if k == '_injected_cycle_id':
                                    clean_kwargs['cycle_id'] = v
                                elif not k.startswith('_injected_'):
                                    clean_kwargs[k] = v
                            method(*args, **clean_kwargs)
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        print(f"[PG-BRD] {method_name} error: {e}",
                              file=sys.stderr, flush=True)
                    # Rollback to clear PG error state, then continue
                    try:
                        conn.rollback()
                    except Exception:
                        pass

            conn.commit()
            self._writes_flushed += len(writes) - errors
            self._flushes_count += 1

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[PG-BRD] Flush error: {e}", file=sys.stderr, flush=True)
        finally:
            put_conn(conn)

    def _buffer_write(self, method_name: str, *args, **kwargs):
        self._buffer.put((method_name, args, kwargs))
        self._writes_buffered += 1

    # =========================================================================
    # High-frequency logs (optional)
    # =========================================================================

    def log_trade_event(self, *args, **kwargs):
        if self._enable_high_freq:
            self._buffer_write('log_trade_event', *args, **kwargs)

    def log_orderbook_event(self, *args, **kwargs):
        if self._enable_high_freq:
            self._buffer_write('log_orderbook_event', *args, **kwargs)

    def log_orderbook_depth(self, *args, **kwargs):
        if self._enable_high_freq:
            self._buffer_write('log_orderbook_depth', *args, **kwargs)

    def log_mark_price(self, *args, **kwargs):
        if self._enable_high_freq:
            self._buffer_write('log_mark_price', *args, **kwargs)

    # =========================================================================
    # Medium-frequency logs
    # =========================================================================

    def log_liquidation_event(self, *args, **kwargs):
        self._buffer_write('log_liquidation_event', *args, **kwargs)

    def log_ohlc_candle(self, *args, **kwargs):
        self._buffer_write('log_ohlc_candle', *args, **kwargs)

    # =========================================================================
    # Low-frequency logs
    # =========================================================================

    def log_cycle(self, *args, **kwargs):
        cycle_id = self._get_next_cycle_id()
        kwargs['_injected_cycle_id'] = cycle_id
        self._buffer_write('log_cycle', *args, **kwargs)
        return cycle_id

    def log_m2_nodes(self, *args, **kwargs):
        self._buffer_write('log_m2_nodes', *args, **kwargs)

    def log_primitive_values(self, *args, **kwargs):
        self._buffer_write('log_primitive_values', *args, **kwargs)

    def log_mandate(self, *args, **kwargs):
        self._buffer_write('log_mandate', *args, **kwargs)

    def log_policy_outcome(self, *args, **kwargs):
        self._buffer_write('log_policy_outcome', *args, **kwargs)

    def log_arbitration_round(self, *args, **kwargs):
        self._buffer_write('log_arbitration_round', *args, **kwargs)

    # =========================================================================
    # Raw SQL (ghost trades, rejections, etc.)
    # =========================================================================

    def execute_sql(self, sql: str, params: tuple = ()):
        """Buffer raw SQL. Converts ? to %s automatically."""
        self._buffer.put(('__raw_sql__', (sql, params), {}))
        self._writes_buffered += 1

    def read_sql(self, sql: str, params: tuple = ()):
        """Execute read query on a SEPARATE pool connection. No lock needed."""
        pg_sql = sql.replace('?', '%s')
        conn = get_conn()
        try:
            cur = conn.cursor()
            if params:
                cur.execute(pg_sql, params)
            else:
                cur.execute(pg_sql)
            return cur.fetchall()
        finally:
            put_conn(conn)

    def prune_safe(self, max_age_hours: int = 48) -> int:
        """Prune old data on a SEPARATE pool connection.

        NO LOCK. PostgreSQL MVCC: DELETE doesn't block INSERT.
        No manual VACUUM needed (autovacuum handles it).
        """
        self.flush()

        conn = get_conn()
        try:
            cutoff_ts = time.time() - (max_age_hours * 3600)
            cutoff_ns = int(cutoff_ts * 1_000_000_000)
            total_deleted = 0

            cur = conn.cursor()

            # Tables with 'timestamp' column (float seconds)
            for table in [
                'execution_cycles', 'liquidation_events', 'ohlc_candles',
                'orderbook_events', 'orderbook_depth', 'mark_prices',
                'trade_events', 'policy_outcomes', 'm2_node_events',
                'hl_positions', 'hl_liquidation_proximity', 'hl_cascade_events',
            ]:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE timestamp < %s", (cutoff_ts,))
                    total_deleted += cur.rowcount
                except Exception:
                    conn.rollback()
                    conn.cursor()  # Get fresh cursor after rollback

            # Tables with 'ts_ns' column (nanoseconds)
            for table in [
                'hl_metric_snapshots', 'hl_decay_signals',
                'hl_catastrophe_events', 'hl_recovery_attempts',
                'hl_gating_decisions', 'hl_strategy_performance',
                'hl_governor_decisions', 'hl_capital_governor_decisions',
                'hl_meta_governor_decisions', 'hl_unknown_threat_signals',
            ]:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE ts_ns < %s", (cutoff_ns,))
                    total_deleted += cur.rowcount
                except Exception:
                    conn.rollback()
                    cur = conn.cursor()

            # Tables with 'snapshot_ts' column (nanoseconds)
            for table in [
                'hl_position_snapshots', 'hl_wallet_snapshots',
                'hl_oi_snapshots', 'hl_mark_prices_raw',
                'hl_funding_snapshots', 'binance_funding_snapshots',
                'spot_price_snapshots',
            ]:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE snapshot_ts < %s", (cutoff_ns,))
                    total_deleted += cur.rowcount
                except Exception:
                    conn.rollback()
                    cur = conn.cursor()

            # Tables with other timestamp columns
            for table, col in [
                ('hl_liquidation_events_raw', 'detected_ts'),
                ('hl_poll_cycles', 'cycle_ts'),
                ('hl_wallet_discovery', 'discovery_ts'),
                ('hl_labeled_cascades', 'start_ts'),
                ('hl_validation_results', 'run_ts'),
                ('hl_threshold_optimization_runs', 'run_ts'),
            ]:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE {col} < %s", (cutoff_ns,))
                    total_deleted += cur.rowcount
                except Exception:
                    conn.rollback()
                    cur = conn.cursor()

            # Child tables: delete by old cycle_ids
            try:
                cur.execute(
                    "SELECT id FROM execution_cycles WHERE timestamp < %s",
                    (cutoff_ts,)
                )
                old_ids = [r[0] for r in cur.fetchall()]
                if old_ids:
                    for child in ['m2_nodes', 'primitive_values',
                                  'policy_evaluations', 'mandates',
                                  'arbitration_rounds']:
                        try:
                            cur.execute(
                                f"DELETE FROM {child} WHERE cycle_id = ANY(%s)",
                                (old_ids,)
                            )
                            total_deleted += cur.rowcount
                        except Exception:
                            conn.rollback()
                            cur = conn.cursor()
            except Exception:
                conn.rollback()
                cur = conn.cursor()

            conn.commit()
            print(f"[PG-BRD] Pruned {total_deleted} rows (>{max_age_hours}h old)",
                  flush=True)
            return total_deleted

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[PG-BRD] Prune error: {e}", file=sys.stderr, flush=True)
            return 0
        finally:
            put_conn(conn)

    # =========================================================================
    # Pass-through for non-log methods (reads, etc.)
    # =========================================================================

    def __getattr__(self, name: str):
        """Pass through undefined methods.

        log_* methods → buffer for batch write
        Other callable methods → execute immediately on a pool connection
        """
        if name.startswith('_'):
            raise AttributeError(name)

        if name.startswith('log_'):
            # Buffer any log_* method we haven't explicitly defined
            def buffered(*args, **kwargs):
                self._buffer_write(name, *args, **kwargs)
            return buffered

        # For read/query methods, execute on a temporary pool connection
        # Each call gets its OWN db shell — no shared state with flush thread
        def passthrough(*args, **kwargs):
            conn = get_conn()
            try:
                db_shell = self._make_db_shell(conn)
                method = getattr(db_shell, name)
                result = method(*args, **kwargs)
                conn.commit()
                return result
            finally:
                put_conn(conn)

        return passthrough

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def get_stats(self) -> dict:
        return {
            'writes_buffered': self._writes_buffered,
            'writes_flushed': self._writes_flushed,
            'flushes_count': self._flushes_count,
            'buffer_size': self._buffer.qsize(),
            'high_freq_enabled': self._enable_high_freq,
            'cycle_counter': self._cycle_counter,
        }

    def flush(self):
        """Force immediate flush."""
        self._do_flush()

    def close(self):
        """Stop background thread and flush remaining writes."""
        self._running = False
        self._flush_thread.join(timeout=5.0)
        self._do_flush()
