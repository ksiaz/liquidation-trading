"""
Unit tests for HLP24-compliant Hyperliquid data store.

Tests:
- Raw data storage (no computed fields)
- Append-only behavior
- Poll cycle management
- Query methods
"""

import os
import tempfile
import pytest
import time

from runtime.logging.execution_db import ResearchDatabase
from runtime.hyperliquid.hl_data_store import HLDataStore, PollCycleStats, now_ns


class TestHLDataStore:
    """Test HLDataStore raw data storage."""

    @pytest.fixture
    def db(self):
        """Create temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        yield db
        db.close()
        os.unlink(path)

    @pytest.fixture
    def store(self, db):
        """Create HLDataStore instance."""
        return HLDataStore(db)

    # =========================================================================
    # Poll Cycle Tests
    # =========================================================================

    def test_start_poll_cycle_returns_id(self, store):
        """Starting a poll cycle returns a valid cycle ID."""
        cycle_id = store.start_poll_cycle("tier1")
        assert cycle_id > 0

    def test_end_poll_cycle_stores_stats(self, store, db):
        """Ending a poll cycle stores statistics."""
        cycle_id = store.start_poll_cycle("tier1")

        stats = PollCycleStats(
            wallets_polled=10,
            positions_found=25,
            liquidations_detected=2,
            api_errors=1,
            duration_ms=150
        )
        store.end_poll_cycle(cycle_id, stats)

        # Verify stored
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_poll_cycles WHERE id = ?", (cycle_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row['wallets_polled'] == 10
        assert row['positions_found'] == 25
        assert row['liquidations_detected'] == 2
        assert row['api_errors'] == 1
        assert row['duration_ms'] == 150

    def test_current_cycle_id_tracks_active_cycle(self, store):
        """current_cycle_id property tracks the active cycle."""
        assert store.current_cycle_id is None

        cycle_id = store.start_poll_cycle("tier2")
        assert store.current_cycle_id == cycle_id

        store.end_poll_cycle(cycle_id, PollCycleStats())
        assert store.current_cycle_id is None

    # =========================================================================
    # Position Snapshot Tests
    # =========================================================================

    def test_store_position_snapshot_returns_id(self, store):
        """Storing a position snapshot returns a row ID."""
        cycle_id = store.start_poll_cycle("tier1")

        snapshot_id = store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xtest123",
            coin="BTC",
            raw_position={
                'szi': '1.5',
                'entryPx': '95000.0',
                'liquidationPx': '90000.0',
                'positionValue': '142500.0',
                'unrealizedPnl': '500.0'
            }
        )

        assert snapshot_id > 0

    def test_store_position_preserves_raw_strings(self, store, db):
        """Position data is stored as raw strings, not computed."""
        cycle_id = store.start_poll_cycle("tier1")

        store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xtest456",
            coin="ETH",
            raw_position={
                'szi': '-2.0',  # Negative = short
                'entryPx': '3500.00',
                'liquidationPx': '3850.00',
                'leverage': {'type': 'isolated', 'value': 10.0}
            }
        )

        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT szi, entry_px, liquidation_px, leverage_type, leverage_value
            FROM hl_position_snapshots
            WHERE wallet_address = ?
        """, ('0xtest456',))
        row = cursor.fetchone()

        # Verify stored as strings exactly
        assert row['szi'] == '-2.0'
        assert row['entry_px'] == '3500.00'
        assert row['liquidation_px'] == '3850.00'
        assert row['leverage_type'] == 'isolated'
        assert row['leverage_value'] == 10.0

    def test_store_position_lowercases_wallet(self, store, db):
        """Wallet addresses are normalized to lowercase."""
        cycle_id = store.start_poll_cycle("tier1")

        store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xABCDEF123456",  # Mixed case
            coin="SOL",
            raw_position={'szi': '100', 'entryPx': '200'}
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT wallet_address FROM hl_position_snapshots")
        row = cursor.fetchone()

        assert row['wallet_address'] == '0xabcdef123456'

    # =========================================================================
    # Wallet Snapshot Tests
    # =========================================================================

    def test_store_wallet_snapshot(self, store, db):
        """Wallet account snapshot is stored correctly."""
        cycle_id = store.start_poll_cycle("tier1")

        store.store_wallet_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet="0xwallet789",
            raw_summary={
                'accountValue': '1000000.00',
                'totalMarginUsed': '250000.00',
                'withdrawable': '750000.00'
            }
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_wallet_snapshots WHERE wallet_address = ?",
                      ('0xwallet789',))
        row = cursor.fetchone()

        assert row['account_value'] == '1000000.00'
        assert row['total_margin_used'] == '250000.00'
        assert row['withdrawable'] == '750000.00'

    # =========================================================================
    # Liquidation Event Tests
    # =========================================================================

    def test_store_liquidation_event(self, store, db):
        """Liquidation event stores last known state."""
        event_id = store.store_liquidation_event(
            detected_ts=now_ns(),
            wallet="0xliquidated",
            coin="BTC",
            last_known_snapshot={
                'szi': '5.0',
                'entryPx': '96000.0',
                'liquidationPx': '91200.0',
                'positionValue': '480000.0',
                'unrealizedPnl': '-24000.0'
            },
            prev_snapshot_id=123
        )

        assert event_id > 0

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_liquidation_events_raw WHERE id = ?", (event_id,))
        row = cursor.fetchone()

        assert row['wallet_address'] == '0xliquidated'
        assert row['coin'] == 'BTC'
        assert row['last_known_szi'] == '5.0'
        assert row['last_known_entry_px'] == '96000.0'
        assert row['prev_snapshot_id'] == 123
        assert row['detection_method'] == 'position_disappearance'

    # =========================================================================
    # OI/Funding/Mark Price Tests
    # =========================================================================

    def test_store_oi_snapshot(self, store, db):
        """OI snapshot stores raw API values."""
        store.store_oi_snapshot(
            snapshot_ts=now_ns(),
            coin="BTC",
            raw_context={
                'openInterest': '15000000000',
                'funding': '0.0001',
                'premium': '-0.0002',
                'dayNtlVlm': '5000000000'
            }
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_oi_snapshots WHERE coin = ?", ('BTC',))
        row = cursor.fetchone()

        assert row['open_interest'] == '15000000000'
        assert row['funding_rate'] == '0.0001'
        assert row['premium'] == '-0.0002'
        assert row['day_ntl_vlm'] == '5000000000'

    def test_store_mark_price(self, store, db):
        """Mark price stores raw string values."""
        store.store_mark_price(
            snapshot_ts=now_ns(),
            coin="ETH",
            mark_px="3456.78",
            oracle_px="3455.50"
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_mark_prices_raw WHERE coin = ?", ('ETH',))
        row = cursor.fetchone()

        assert row['mark_px'] == '3456.78'
        assert row['oracle_px'] == '3455.50'

    def test_store_funding_snapshot(self, store, db):
        """Funding snapshot stores rate and timing."""
        next_funding = now_ns() + 28800 * 1_000_000_000  # 8 hours

        store.store_funding_snapshot(
            snapshot_ts=now_ns(),
            coin="SOL",
            funding_rate="0.00015",
            next_funding_ts=next_funding
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_funding_snapshots WHERE coin = ?", ('SOL',))
        row = cursor.fetchone()

        assert row['funding_rate'] == '0.00015'
        assert row['next_funding_ts'] == next_funding

    # =========================================================================
    # Wallet Discovery Tests
    # =========================================================================

    def test_store_wallet_discovery(self, store, db):
        """Wallet discovery records provenance."""
        store.store_wallet_discovery(
            wallet="0xdiscovered",
            source_type="trade",
            source_coin="BTC",
            source_value=500000.0,
            source_metadata='{"trade_hash": "0xabc123"}'
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_wallet_discovery WHERE wallet_address = ?",
                      ('0xdiscovered',))
        row = cursor.fetchone()

        assert row['source_type'] == 'trade'
        assert row['source_coin'] == 'BTC'
        assert row['source_value'] == 500000.0

    # =========================================================================
    # Tier Management Tests
    # =========================================================================

    def test_set_wallet_tier(self, store, db):
        """Setting wallet tier persists configuration."""
        next_poll = now_ns() + 5 * 1_000_000_000  # 5 seconds

        store.set_wallet_tier("0xtier1wallet", tier=1, next_poll_ts=next_poll)

        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM hl_wallet_polling_config WHERE wallet_address = ?",
                      ('0xtier1wallet',))
        row = cursor.fetchone()

        assert row['tier'] == 1
        assert row['next_poll_ts'] == next_poll

    def test_get_wallets_due_for_poll(self, store):
        """Get wallets due returns wallets past their poll time."""
        now = now_ns()
        past = now - 1_000_000_000  # 1 second ago
        future = now + 60 * 1_000_000_000  # 1 minute from now

        store.set_wallet_tier("0xdue1", tier=1, next_poll_ts=past)
        store.set_wallet_tier("0xdue2", tier=1, next_poll_ts=past)
        store.set_wallet_tier("0xnotdue", tier=1, next_poll_ts=future)

        due = store.get_wallets_due_for_poll(tier=1)

        assert '0xdue1' in due
        assert '0xdue2' in due
        assert '0xnotdue' not in due

    # =========================================================================
    # Query Method Tests
    # =========================================================================

    def test_get_position_history(self, store):
        """Query returns position history in chronological order."""
        cycle_id = store.start_poll_cycle("test")
        base_ts = now_ns()

        # Store multiple snapshots
        for i in range(3):
            store.store_position_snapshot(
                snapshot_ts=base_ts + i * 1_000_000_000,
                poll_cycle_id=cycle_id,
                wallet="0xhistory",
                coin="BTC",
                raw_position={
                    'szi': str(i + 1),
                    'entryPx': '95000'
                }
            )

        history = store.get_position_history(
            wallet="0xhistory",
            coin="BTC",
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )

        assert len(history) == 3
        # Verify chronological order
        assert float(history[0]['szi']) == 1.0
        assert float(history[1]['szi']) == 2.0
        assert float(history[2]['szi']) == 3.0

    def test_get_liquidations_in_window(self, store):
        """Query returns liquidations in time window."""
        base_ts = now_ns()

        # Store liquidations
        store.store_liquidation_event(
            detected_ts=base_ts + 1_000_000_000,
            wallet="0xliq1",
            coin="BTC",
            last_known_snapshot={'szi': '1', 'entryPx': '95000'}
        )
        store.store_liquidation_event(
            detected_ts=base_ts + 2_000_000_000,
            wallet="0xliq2",
            coin="ETH",
            last_known_snapshot={'szi': '10', 'entryPx': '3500'}
        )

        # Query all
        all_liqs = store.get_liquidations_in_window(
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000
        )
        assert len(all_liqs) == 2

        # Query by coin
        btc_liqs = store.get_liquidations_in_window(
            start_ts=base_ts,
            end_ts=base_ts + 10 * 1_000_000_000,
            coin="BTC"
        )
        assert len(btc_liqs) == 1
        assert btc_liqs[0]['coin'] == 'BTC'


class TestHLP24Compliance:
    """Test HLP24 compliance: raw storage, no computed fields."""

    @pytest.fixture
    def db(self):
        """Create temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        yield db
        db.close()
        os.unlink(path)

    @pytest.fixture
    def store(self, db):
        """Create HLDataStore instance."""
        return HLDataStore(db)

    def test_no_computed_fields_in_position_snapshots(self, db):
        """Position snapshots table has no computed columns."""
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(hl_position_snapshots)")
        columns = [row[1] for row in cursor.fetchall()]

        # These would be computed fields - should NOT exist
        forbidden = [
            'side',  # Derived from szi sign
            'position_size',  # Derived from abs(szi)
            'distance_to_liquidation',  # Computed
            'leverage_ratio',  # Computed
            'is_long',  # Derived
            'is_short'  # Derived
        ]

        for field in forbidden:
            assert field not in columns, f"Computed field '{field}' should not exist"

    def test_timestamps_stored_as_received(self, store, db):
        """Timestamps are stored exactly as provided, not modified."""
        exact_ts = 1700000000123456789  # Specific nanosecond timestamp

        cycle_id = store.start_poll_cycle("test")
        store.store_position_snapshot(
            snapshot_ts=exact_ts,
            poll_cycle_id=cycle_id,
            wallet="0xexact",
            coin="BTC",
            raw_position={'szi': '1', 'entryPx': '95000'}
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT snapshot_ts FROM hl_position_snapshots WHERE wallet_address = ?",
                      ('0xexact',))
        row = cursor.fetchone()

        assert row['snapshot_ts'] == exact_ts

    def test_append_only_no_update_method(self, store):
        """HLDataStore has no update methods for raw data tables."""
        # These methods should NOT exist
        forbidden_methods = [
            'update_position_snapshot',
            'delete_position_snapshot',
            'modify_liquidation_event',
            'update_oi_snapshot'
        ]

        for method in forbidden_methods:
            assert not hasattr(store, method), f"Forbidden method '{method}' exists"
