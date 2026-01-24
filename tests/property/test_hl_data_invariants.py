"""
Property-based tests for HLP24 data invariants.

Verifies constitutional compliance:
- Append-only behavior (no updates or deletes)
- Raw data preservation (strings stored exactly)
- No computed fields in storage
- Timestamp precision preserved
"""

import os
import tempfile
import pytest
import time
import random
import string

from runtime.logging.execution_db import ResearchDatabase
from runtime.hyperliquid.hl_data_store import HLDataStore, PollCycleStats, now_ns


class TestAppendOnlyInvariants:
    """Verify append-only behavior - no updates or deletes allowed."""

    @pytest.fixture
    def store(self):
        """Create temporary data store."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        yield store
        db.close()
        os.unlink(path)

    def test_no_update_methods_exist(self, store):
        """HLDataStore has no update methods for raw data."""
        forbidden_methods = [
            'update_position_snapshot',
            'update_wallet_snapshot',
            'update_liquidation_event',
            'update_oi_snapshot',
            'update_mark_price',
            'update_funding_snapshot',
            'modify_position',
            'edit_snapshot',
        ]

        for method in forbidden_methods:
            assert not hasattr(store, method), f"Forbidden method '{method}' exists"

    def test_no_delete_methods_exist(self, store):
        """HLDataStore has no delete methods for raw data."""
        forbidden_methods = [
            'delete_position_snapshot',
            'delete_wallet_snapshot',
            'delete_liquidation_event',
            'delete_oi_snapshot',
            'delete_poll_cycle',
            'remove_position',
            'clear_snapshots',
        ]

        for method in forbidden_methods:
            assert not hasattr(store, method), f"Forbidden method '{method}' exists"

    def test_store_returns_new_id_each_time(self, store):
        """Each store operation returns a unique, increasing ID."""
        cycle_id = store.start_poll_cycle("test")

        ids = []
        for i in range(10):
            snapshot_id = store.store_position_snapshot(
                snapshot_ts=now_ns(),
                poll_cycle_id=cycle_id,
                wallet=f"0xwallet{i}",
                coin="BTC",
                raw_position={'szi': str(i), 'entryPx': '95000'}
            )
            ids.append(snapshot_id)

        # All IDs unique
        assert len(set(ids)) == len(ids)

        # IDs are increasing
        assert ids == sorted(ids)

    def test_duplicate_data_creates_new_row(self, store):
        """Storing identical data creates new row, not update."""
        cycle_id = store.start_poll_cycle("test")

        raw_position = {'szi': '1.0', 'entryPx': '95000'}

        # Store same data twice
        id1 = store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xduplicate",
            coin="BTC",
            raw_position=raw_position
        )

        id2 = store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xduplicate",
            coin="BTC",
            raw_position=raw_position
        )

        # Different IDs = different rows
        assert id1 != id2

        # Verify both rows exist
        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM hl_position_snapshots WHERE wallet_address = ?",
            ("0xduplicate",)
        )
        assert cursor.fetchone()[0] == 2


class TestRawDataPreservation:
    """Verify raw data is stored exactly as received."""

    @pytest.fixture
    def db_and_store(self):
        """Create temporary database and data store."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        yield db, store
        db.close()
        os.unlink(path)

    def test_string_values_preserved_exactly(self, db_and_store):
        """String values stored exactly as provided."""
        db, store = db_and_store

        cycle_id = store.start_poll_cycle("test")

        # Various string formats
        test_values = [
            "1.0",
            "1.00000000",
            "-0.5",
            "95000.12345678",
            "0.00000001",
        ]

        for i, val in enumerate(test_values):
            store.store_position_snapshot(
                snapshot_ts=now_ns(),
                poll_cycle_id=cycle_id,
                wallet=f"0xtest{i}",
                coin="BTC",
                raw_position={'szi': val, 'entryPx': '1'}
            )

        # Verify each is stored exactly
        cursor = db.conn.cursor()
        for i, expected in enumerate(test_values):
            cursor.execute(
                "SELECT szi FROM hl_position_snapshots WHERE wallet_address = ?",
                (f"0xtest{i}",)
            )
            actual = cursor.fetchone()[0]
            assert actual == expected, f"Expected '{expected}', got '{actual}'"

    def test_negative_values_preserved(self, db_and_store):
        """Negative values (shorts) preserved exactly."""
        db, store = db_and_store

        cycle_id = store.start_poll_cycle("test")
        store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xshort",
            coin="ETH",
            raw_position={'szi': '-5.0', 'entryPx': '3500'}
        )

        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT szi FROM hl_position_snapshots WHERE wallet_address = ?",
            ("0xshort",)
        )
        assert cursor.fetchone()[0] == '-5.0'

    def test_wallet_address_normalized(self, db_and_store):
        """Wallet addresses normalized to lowercase."""
        db, store = db_and_store

        cycle_id = store.start_poll_cycle("test")
        store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xABCDEF123456",  # Mixed case
            coin="BTC",
            raw_position={'szi': '1', 'entryPx': '95000'}
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT wallet_address FROM hl_position_snapshots")
        assert cursor.fetchone()[0] == "0xabcdef123456"


class TestTimestampPrecision:
    """Verify timestamp precision is preserved."""

    @pytest.fixture
    def db_and_store(self):
        """Create temporary database and data store."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        yield db, store
        db.close()
        os.unlink(path)

    def test_nanosecond_timestamp_preserved(self, db_and_store):
        """Nanosecond timestamps stored exactly."""
        db, store = db_and_store

        # Specific nanosecond timestamp
        exact_ts = 1700000000123456789

        cycle_id = store.start_poll_cycle("test")
        store.store_position_snapshot(
            snapshot_ts=exact_ts,
            poll_cycle_id=cycle_id,
            wallet="0xprecision",
            coin="BTC",
            raw_position={'szi': '1', 'entryPx': '95000'}
        )

        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT snapshot_ts FROM hl_position_snapshots WHERE wallet_address = ?",
            ("0xprecision",)
        )
        stored_ts = cursor.fetchone()[0]

        assert stored_ts == exact_ts

    def test_timestamps_orderable(self, db_and_store):
        """Timestamps maintain ordering when queried."""
        db, store = db_and_store

        cycle_id = store.start_poll_cycle("test")
        base_ts = now_ns()

        # Store in random order
        offsets = [3, 1, 4, 1, 5, 9, 2, 6]
        for offset in offsets:
            store.store_position_snapshot(
                snapshot_ts=base_ts + offset * 1_000_000_000,
                poll_cycle_id=cycle_id,
                wallet="0xorder_test",
                coin="BTC",
                raw_position={'szi': str(offset), 'entryPx': '95000'}
            )

        # Query ordered by timestamp
        history = store.get_position_history(
            wallet="0xorder_test",
            coin="BTC",
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )

        # Should be in chronological order
        timestamps = [h['snapshot_ts'] for h in history]
        assert timestamps == sorted(timestamps)


class TestNoComputedFields:
    """Verify no computed fields in storage layer."""

    @pytest.fixture
    def db(self):
        """Create temporary database."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        yield db
        db.close()
        os.unlink(path)

    def test_position_snapshots_no_derived_columns(self, db):
        """Position snapshots table has no derived columns."""
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(hl_position_snapshots)")
        columns = [row[1] for row in cursor.fetchall()]

        # These would be computed/derived fields
        forbidden = [
            'side',  # Derived from szi sign
            'is_long',
            'is_short',
            'position_size',  # Derived from abs(szi)
            'abs_size',
            'distance_to_liquidation',
            'distance_pct',
            'liquidation_distance',
            'risk_score',
            'health_factor',
            'leverage_ratio',  # Computed from margin/value
        ]

        for field in forbidden:
            assert field not in columns, f"Computed field '{field}' should not exist"

    def test_liquidation_events_no_derived_columns(self, db):
        """Liquidation events table has no derived columns."""
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(hl_liquidation_events_raw)")
        columns = [row[1] for row in cursor.fetchall()]

        forbidden = [
            'side',
            'liquidation_type',  # full/partial - derived
            'loss_amount',  # Computed
            'impact_score',
        ]

        for field in forbidden:
            assert field not in columns, f"Computed field '{field}' should not exist"

    def test_oi_snapshots_no_derived_columns(self, db):
        """OI snapshots table has no derived columns."""
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(hl_oi_snapshots)")
        columns = [row[1] for row in cursor.fetchall()]

        forbidden = [
            'oi_change',  # Derived from diff
            'oi_change_pct',
            'funding_direction',  # Derived from sign
            'is_positive_funding',
        ]

        for field in forbidden:
            assert field not in columns, f"Computed field '{field}' should not exist"


class TestQueryMethodPurity:
    """Verify query methods don't modify data."""

    @pytest.fixture
    def store(self):
        """Create populated data store."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)

        # Populate with test data
        cycle_id = store.start_poll_cycle("test")
        base_ts = now_ns()

        for i in range(5):
            store.store_position_snapshot(
                snapshot_ts=base_ts + i * 1_000_000_000,
                poll_cycle_id=cycle_id,
                wallet="0xquery_test",
                coin="BTC",
                raw_position={'szi': str(i), 'entryPx': '95000'}
            )

        store.end_poll_cycle(cycle_id, PollCycleStats())

        yield store, base_ts
        db.close()
        os.unlink(path)

    def test_get_position_history_is_readonly(self, store):
        """get_position_history doesn't modify data."""
        store, base_ts = store

        # Query twice
        result1 = store.get_position_history(
            wallet="0xquery_test",
            coin="BTC",
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )

        result2 = store.get_position_history(
            wallet="0xquery_test",
            coin="BTC",
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )

        # Same results
        assert len(result1) == len(result2)
        for r1, r2 in zip(result1, result2):
            assert r1['snapshot_ts'] == r2['snapshot_ts']
            assert r1['szi'] == r2['szi']

    def test_queries_return_copies(self, store):
        """Query results are copies, modifying them doesn't affect storage."""
        store, base_ts = store

        # Get history
        history = store.get_position_history(
            wallet="0xquery_test",
            coin="BTC",
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )

        # Modify result
        if history:
            history[0]['szi'] = 'MODIFIED'

        # Query again
        history2 = store.get_position_history(
            wallet="0xquery_test",
            coin="BTC",
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )

        # Should not be modified
        if history2:
            assert history2[0]['szi'] != 'MODIFIED'
