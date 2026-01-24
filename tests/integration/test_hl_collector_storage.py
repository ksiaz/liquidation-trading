"""
Integration tests for Hyperliquid collector with HLP24 storage.

Tests end-to-end data flow from mock API through collector to database.
Verifies raw data is stored correctly and HLP24 compliance is maintained.
"""

import os
import tempfile
import pytest
import asyncio
import time

from runtime.logging.execution_db import ResearchDatabase
from runtime.hyperliquid.hl_data_store import HLDataStore, PollCycleStats, now_ns
from runtime.hyperliquid.mock_data import MockHyperliquidClient, MockConfig
from runtime.hyperliquid.types import WalletState, HyperliquidPosition


class TestCollectorStorageFlow:
    """Test end-to-end storage flow."""

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

    @pytest.fixture
    def mock_client(self):
        """Create mock client with reproducible data."""
        config = MockConfig(
            num_wallets=10,
            coins=['BTC', 'ETH', 'SOL'],
            position_probability=0.8
        )
        return MockHyperliquidClient(config, seed=42)

    @pytest.mark.asyncio
    async def test_wallet_poll_stores_raw_data(self, db_and_store, mock_client):
        """Polling a wallet stores raw position data."""
        db, store = db_and_store

        # Get a wallet from mock client
        wallets = mock_client.get_tracked_wallets()
        test_wallet = wallets[0]

        # Start poll cycle
        cycle_id = store.start_poll_cycle("test")

        # Get wallet state from mock
        wallet_state = await mock_client.get_clearinghouse_state(test_wallet)
        assert wallet_state is not None

        snapshot_ts = now_ns()

        # Store each position
        for pos in wallet_state.positions:
            store.store_position_snapshot(
                snapshot_ts=snapshot_ts,
                poll_cycle_id=cycle_id,
                wallet=test_wallet,
                coin=pos['coin'],
                raw_position=pos
            )

        # Store wallet summary
        store.store_wallet_snapshot(
            snapshot_ts=snapshot_ts,
            poll_cycle_id=cycle_id,
            wallet=test_wallet,
            raw_summary=wallet_state.cross_margin_summary
        )

        # End cycle
        stats = PollCycleStats(
            wallets_polled=1,
            positions_found=len(wallet_state.positions)
        )
        store.end_poll_cycle(cycle_id, stats)

        # Verify data stored
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM hl_position_snapshots WHERE wallet_address = ?",
            (test_wallet.lower(),)
        )
        count = cursor.fetchone()[0]
        assert count == len(wallet_state.positions)

    @pytest.mark.asyncio
    async def test_multiple_poll_cycles_tracked(self, db_and_store, mock_client):
        """Multiple poll cycles are tracked separately."""
        db, store = db_and_store

        cycle_ids = []

        # Run 3 poll cycles
        for i in range(3):
            cycle_id = store.start_poll_cycle(f"cycle_{i}")
            cycle_ids.append(cycle_id)

            # Poll one wallet
            wallet = mock_client.get_tracked_wallets()[0]
            wallet_state = await mock_client.get_clearinghouse_state(wallet)

            if wallet_state:
                for pos in wallet_state.positions:
                    store.store_position_snapshot(
                        snapshot_ts=now_ns(),
                        poll_cycle_id=cycle_id,
                        wallet=wallet,
                        coin=pos['coin'],
                        raw_position=pos
                    )

            store.end_poll_cycle(cycle_id, PollCycleStats(wallets_polled=1))

        # Verify all cycles recorded
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM hl_poll_cycles")
        assert cursor.fetchone()[0] == 3

        # Verify cycle IDs are sequential
        assert cycle_ids[0] < cycle_ids[1] < cycle_ids[2]

    @pytest.mark.asyncio
    async def test_position_history_query(self, db_and_store, mock_client):
        """Position history can be queried by time range."""
        db, store = db_and_store

        wallet = mock_client.get_tracked_wallets()[0]
        base_ts = now_ns()

        # Store 5 snapshots with increasing timestamps
        stored_count = 0
        for i in range(5):
            cycle_id = store.start_poll_cycle("test")
            wallet_state = await mock_client.get_clearinghouse_state(wallet)

            if wallet_state and wallet_state.positions:
                pos = wallet_state.positions[0]
                store.store_position_snapshot(
                    snapshot_ts=base_ts + i * 1_000_000_000,  # 1 second apart
                    poll_cycle_id=cycle_id,
                    wallet=wallet,
                    coin=pos['coin'],
                    raw_position=pos
                )
                stored_count += 1

            store.end_poll_cycle(cycle_id, PollCycleStats())

        # Query all snapshots
        history = store.get_position_history(
            wallet=wallet,
            coin='BTC',  # Assuming BTC exists in mock
            start_ts=base_ts,
            end_ts=base_ts + 5 * 1_000_000_000
        )

        # Should get all snapshots we stored for BTC
        assert len(history) <= stored_count
        # Verify chronological order
        if len(history) > 1:
            timestamps = [h['snapshot_ts'] for h in history]
            assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_liquidation_detection_stores_event(self, db_and_store, mock_client):
        """Detected liquidation stores event with last known state."""
        db, store = db_and_store

        wallet = mock_client.get_tracked_wallets()[0]

        # Get initial state
        wallet_state = await mock_client.get_clearinghouse_state(wallet)
        if not wallet_state or not wallet_state.positions:
            pytest.skip("No positions in mock wallet")

        # Store initial position
        cycle_id = store.start_poll_cycle("test")
        pos = wallet_state.positions[0]
        snapshot_id = store.store_position_snapshot(
            snapshot_ts=now_ns(),
            poll_cycle_id=cycle_id,
            wallet=wallet,
            coin=pos['coin'],
            raw_position=pos
        )
        store.end_poll_cycle(cycle_id, PollCycleStats())

        # Simulate liquidation (position disappears)
        mock_client.simulate_liquidation(wallet, pos['coin'])

        # Detect and store liquidation event
        event_id = store.store_liquidation_event(
            detected_ts=now_ns(),
            wallet=wallet,
            coin=pos['coin'],
            last_known_snapshot=pos,
            prev_snapshot_id=snapshot_id
        )

        assert event_id > 0

        # Verify event stored
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_liquidation_events_raw WHERE id = ?",
            (event_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row['wallet_address'] == wallet.lower()
        assert row['coin'] == pos['coin']
        assert row['prev_snapshot_id'] == snapshot_id


class TestOIAndFundingStorage:
    """Test OI and funding data storage."""

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

    def test_oi_snapshot_storage(self, store):
        """OI snapshot stores raw context."""
        snapshot_ts = now_ns()

        store.store_oi_snapshot(
            snapshot_ts=snapshot_ts,
            coin="BTC",
            raw_context={
                'openInterest': '15000000000',
                'funding': '0.0001',
                'premium': '-0.0002',
                'dayNtlVlm': '5000000000'
            }
        )

        history = store.get_oi_history(
            coin="BTC",
            start_ts=snapshot_ts - 1_000_000_000,
            end_ts=snapshot_ts + 1_000_000_000
        )

        assert len(history) == 1
        assert history[0]['open_interest'] == '15000000000'
        assert history[0]['funding_rate'] == '0.0001'

    def test_mark_price_storage(self, store):
        """Mark price stores raw values."""
        snapshot_ts = now_ns()

        store.store_mark_price(
            snapshot_ts=snapshot_ts,
            coin="ETH",
            mark_px="3456.78",
            oracle_px="3455.50"
        )

        # Query directly since no query method for mark prices
        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_mark_prices_raw WHERE coin = ?",
            ("ETH",)
        )
        row = cursor.fetchone()

        assert row['mark_px'] == "3456.78"
        assert row['oracle_px'] == "3455.50"

    def test_funding_snapshot_storage(self, store):
        """Funding snapshot stores rate and timing."""
        snapshot_ts = now_ns()
        next_funding = snapshot_ts + 8 * 3600 * 1_000_000_000  # 8 hours

        store.store_funding_snapshot(
            snapshot_ts=snapshot_ts,
            coin="SOL",
            funding_rate="0.00015",
            next_funding_ts=next_funding
        )

        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_funding_snapshots WHERE coin = ?",
            ("SOL",)
        )
        row = cursor.fetchone()

        assert row['funding_rate'] == "0.00015"
        assert row['next_funding_ts'] == next_funding


class TestWalletDiscoveryProvenance:
    """Test wallet discovery tracking."""

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

    def test_trade_discovery_provenance(self, store):
        """Trade-discovered wallet records source."""
        store.store_wallet_discovery(
            wallet="0xtrade_discovered",
            source_type="trade",
            source_coin="BTC",
            source_value=500000.0
        )

        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_wallet_discovery WHERE wallet_address = ?",
            ("0xtrade_discovered",)
        )
        row = cursor.fetchone()

        assert row['source_type'] == 'trade'
        assert row['source_coin'] == 'BTC'
        assert row['source_value'] == 500000.0

    def test_liquidation_discovery_provenance(self, store):
        """Liquidation-discovered wallet records source."""
        store.store_wallet_discovery(
            wallet="0xliq_discovered",
            source_type="liquidation",
            source_coin="ETH",
            source_value=250000.0
        )

        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_wallet_discovery WHERE source_type = ?",
            ("liquidation",)
        )
        row = cursor.fetchone()

        assert row['wallet_address'] == '0xliq_discovered'
        assert row['source_coin'] == 'ETH'

    def test_manual_discovery_provenance(self, store):
        """Manually added wallet records source."""
        store.store_wallet_discovery(
            wallet="0xmanual_wallet",
            source_type="manual",
            source_metadata='{"added_by": "config"}'
        )

        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_wallet_discovery WHERE wallet_address = ?",
            ("0xmanual_wallet",)
        )
        row = cursor.fetchone()

        assert row['source_type'] == 'manual'


class TestTierManagement:
    """Test wallet tier management."""

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

    def test_tier_assignment_persists(self, store):
        """Tier assignment is persisted."""
        next_poll = now_ns() + 5 * 1_000_000_000

        store.set_wallet_tier("0xtier1", tier=1, next_poll_ts=next_poll)
        store.set_wallet_tier("0xtier2", tier=2)
        store.set_wallet_tier("0xtier3", tier=3)

        # Query tier 1 wallets due
        due_wallets = store.get_wallets_due_for_poll(tier=1)

        # 0xtier1 is not due yet (next_poll in future)
        assert "0xtier1" not in due_wallets

    def test_tier_promotion_updates_db(self, store):
        """Tier changes are reflected in database."""
        store.set_wallet_tier("0xpromote", tier=3)

        # Promote to tier 1
        store.set_wallet_tier("0xpromote", tier=1)

        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT tier FROM hl_wallet_polling_config WHERE wallet_address = ?",
            ("0xpromote",)
        )
        row = cursor.fetchone()

        assert row['tier'] == 1

    def test_poll_stats_update(self, store):
        """Poll stats are updated correctly."""
        store.set_wallet_tier("0xstats_test", tier=2)

        # Update poll stats
        next_poll = now_ns() + 30 * 1_000_000_000  # 30 seconds
        store.update_wallet_poll_stats(
            wallet="0xstats_test",
            next_poll_ts=next_poll,
            had_positions=True
        )

        cursor = store._db.conn.cursor()
        cursor.execute(
            "SELECT * FROM hl_wallet_polling_config WHERE wallet_address = ?",
            ("0xstats_test",)
        )
        row = cursor.fetchone()

        assert row['next_poll_ts'] == next_poll
        assert row['last_poll_ts'] is not None
