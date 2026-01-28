"""
Buffered Database Wrapper for Non-Blocking Writes.

Wraps ResearchDatabase to buffer writes and flush periodically,
preventing synchronous SQLite commits from blocking the async event loop.

Performance fix for issue: 0.2 cycles/s caused by per-write commits.
"""

import threading
import time
import queue
from typing import Any, Optional, Callable


class BufferedResearchDatabase:
    """Buffered wrapper around ResearchDatabase.

    Buffers all log_* method calls and flushes them in batches
    on a background thread to avoid blocking the async event loop.

    Properties:
    - Non-blocking: log_* calls return immediately
    - Batched commits: Reduces disk I/O by committing in batches
    - Thread-safe: Uses lock for SQLite access synchronization
    - Graceful shutdown: Flushes pending writes on close
    """

    def __init__(
        self,
        db: Any,  # ResearchDatabase instance
        flush_interval_sec: float = 1.0,
        max_buffer_size: int = 1000,
        enable_high_frequency_logs: bool = False
    ):
        """Initialize buffered wrapper.

        Args:
            db: ResearchDatabase instance to wrap
            flush_interval_sec: How often to flush buffer (seconds)
            max_buffer_size: Maximum buffer size before forced flush
            enable_high_frequency_logs: If False, skip very high frequency logs
                (trades, orderbook updates) to reduce load
        """
        self._db = db
        self._flush_interval = flush_interval_sec
        self._max_buffer_size = max_buffer_size
        self._enable_high_freq = enable_high_frequency_logs

        # Write buffer: list of (method_name, args, kwargs)
        self._buffer = queue.Queue()

        # Thread synchronization lock for SQLite access
        self._db_lock = threading.Lock()

        # Local cycle ID counter (thread-safe)
        # This avoids blocking on database to get lastrowid
        self._cycle_counter = 0
        self._cycle_lock = threading.Lock()

        # Background flush thread
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

        # Stats
        self._writes_buffered = 0
        self._writes_flushed = 0
        self._flushes_count = 0

        # Expose underlying connection for direct access if needed
        self.conn = db.conn

    def _get_next_cycle_id(self) -> int:
        """Get next cycle ID (thread-safe local counter)."""
        with self._cycle_lock:
            self._cycle_counter += 1
            return self._cycle_counter

    def _flush_loop(self):
        """Background thread that periodically flushes the buffer."""
        last_flush = time.time()

        while self._running:
            time.sleep(0.1)  # Check every 100ms

            now = time.time()
            should_flush = (
                now - last_flush >= self._flush_interval or
                self._buffer.qsize() >= self._max_buffer_size
            )

            if should_flush and not self._buffer.empty():
                self._do_flush()
                last_flush = now

        # Final flush on shutdown
        if not self._buffer.empty():
            self._do_flush()

    def _do_flush(self):
        """Flush all buffered writes to database."""
        writes = []

        # Drain the queue
        while True:
            try:
                item = self._buffer.get_nowait()
                writes.append(item)
            except queue.Empty:
                break

        if not writes:
            return

        # Execute writes in batch (single transaction) with lock
        with self._db_lock:
            try:
                for method_name, args, kwargs in writes:
                    method = getattr(self._db, method_name, None)
                    if method:
                        try:
                            # Strip internal tracking kwargs before calling
                            clean_kwargs = {k: v for k, v in kwargs.items()
                                          if not k.startswith('_injected_')}
                            # Call the underlying method
                            method(*args, **clean_kwargs)
                        except Exception as e:
                            # Log but don't fail - some writes may be invalid
                            pass

                # Single commit for entire batch
                self._db.conn.commit()

                self._writes_flushed += len(writes)
                self._flushes_count += 1

            except Exception as e:
                # Database error - log but don't crash
                print(f"Database flush error: {e}")

    def _buffer_write(self, method_name: str, *args, **kwargs):
        """Buffer a write for later flushing."""
        self._buffer.put((method_name, args, kwargs))
        self._writes_buffered += 1

    # =========================================================================
    # High-frequency logs (optional - can be disabled for performance)
    # =========================================================================

    def log_trade_event(self, *args, **kwargs):
        """Buffer trade event (high frequency)."""
        if self._enable_high_freq:
            self._buffer_write('log_trade_event', *args, **kwargs)

    def log_orderbook_event(self, *args, **kwargs):
        """Buffer orderbook event (high frequency)."""
        if self._enable_high_freq:
            self._buffer_write('log_orderbook_event', *args, **kwargs)

    def log_orderbook_depth(self, *args, **kwargs):
        """Buffer orderbook depth (high frequency)."""
        if self._enable_high_freq:
            self._buffer_write('log_orderbook_depth', *args, **kwargs)

    def log_mark_price(self, *args, **kwargs):
        """Buffer mark price (high frequency)."""
        if self._enable_high_freq:
            self._buffer_write('log_mark_price', *args, **kwargs)

    # =========================================================================
    # Medium-frequency logs (always buffered)
    # =========================================================================

    def log_liquidation_event(self, *args, **kwargs):
        """Buffer liquidation event."""
        self._buffer_write('log_liquidation_event', *args, **kwargs)

    def log_ohlc_candle(self, *args, **kwargs):
        """Buffer OHLC candle."""
        self._buffer_write('log_ohlc_candle', *args, **kwargs)

    # =========================================================================
    # Low-frequency logs (buffered with local ID generation)
    # =========================================================================

    def log_cycle(self, *args, **kwargs):
        """Log cycle and return cycle_id (non-blocking).

        Uses local counter for cycle_id instead of database lastrowid
        to avoid blocking on database commit.
        """
        cycle_id = self._get_next_cycle_id()
        # Inject cycle_id into kwargs for the actual database call
        kwargs['_injected_cycle_id'] = cycle_id
        self._buffer_write('log_cycle', *args, **kwargs)
        return cycle_id

    def log_m2_nodes(self, *args, **kwargs):
        """Buffer M2 nodes."""
        self._buffer_write('log_m2_nodes', *args, **kwargs)

    def log_primitive_values(self, *args, **kwargs):
        """Buffer primitive values."""
        self._buffer_write('log_primitive_values', *args, **kwargs)

    def log_mandate(self, *args, **kwargs):
        """Buffer mandate."""
        self._buffer_write('log_mandate', *args, **kwargs)

    def log_policy_outcome(self, *args, **kwargs):
        """Buffer policy outcome."""
        self._buffer_write('log_policy_outcome', *args, **kwargs)

    def log_arbitration_round(self, *args, **kwargs):
        """Buffer arbitration round."""
        self._buffer_write('log_arbitration_round', *args, **kwargs)

    # =========================================================================
    # Pass-through for methods that need immediate execution
    # =========================================================================

    def __getattr__(self, name: str):
        """Pass through any undefined methods to underlying database."""
        attr = getattr(self._db, name)
        if callable(attr) and name.startswith('log_'):
            # Buffer any log_* method we haven't explicitly defined
            def buffered(*args, **kwargs):
                self._buffer_write(name, *args, **kwargs)
            return buffered
        return attr

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def get_stats(self) -> dict:
        """Get buffering statistics."""
        return {
            'writes_buffered': self._writes_buffered,
            'writes_flushed': self._writes_flushed,
            'flushes_count': self._flushes_count,
            'buffer_size': self._buffer.qsize(),
            'high_freq_enabled': self._enable_high_freq,
            'cycle_counter': self._cycle_counter
        }

    def flush(self):
        """Force immediate flush of buffer."""
        self._do_flush()

    def close(self):
        """Stop background thread and flush remaining writes."""
        self._running = False
        self._flush_thread.join(timeout=5.0)
        self._do_flush()  # Final flush
