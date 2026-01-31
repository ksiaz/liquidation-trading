"""
Unit tests for data storage (HLP24).

Tests:
- Cold storage insert and query
- Event labeling
"""

import pytest
import tempfile
import os
from pathlib import Path

from runtime.storage.cold_storage import (
    ColdStorage,
    StorageConfig,
    MarketSnapshot,
    TradeRecord,
    QueryResult,
)
from runtime.labeling.event_labeler import (
    EventLabeler,
    LabeledEvent,
    LabelConfig,
    EventLabel,
    SnapshotData,
)


# =============================================================================
# Cold Storage Tests
# =============================================================================

class TestStorageConfig:
    """Tests for StorageConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = StorageConfig()
        assert config.batch_size == 1000
        assert config.enable_wal is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = StorageConfig(
            db_path='custom/path.db',
            batch_size=500,
        )
        assert config.db_path == 'custom/path.db'
        assert config.batch_size == 500


class TestMarketSnapshot:
    """Tests for MarketSnapshot."""

    def test_snapshot_creation(self):
        """Test creating snapshot."""
        snap = MarketSnapshot(
            ts_us=1000000,
            symbol='BTC-PERP',
            open_interest=1000000,
            funding_rate=100,
            mark_price=5000000000000,
        )
        assert snap.symbol == 'BTC-PERP'
        assert snap.ts_us == 1000000

    def test_to_dict(self):
        """Test serialization."""
        snap = MarketSnapshot(
            ts_us=1000000,
            symbol='BTC-PERP',
            open_interest=1000000,
            funding_rate=100,
            mark_price=5000000000000,
        )
        data = snap.to_dict()
        assert 'ts_us' in data
        assert 'symbol' in data

    def test_from_row(self):
        """Test creating from database row."""
        row = (1000000, 'BTC-PERP', 1000000, 100, 5000000000000, 5000000000000, 100, 100, 50000)
        snap = MarketSnapshot.from_row(row)
        assert snap.ts_us == 1000000
        assert snap.symbol == 'BTC-PERP'


class TestTradeRecord:
    """Tests for TradeRecord."""

    def test_trade_creation(self):
        """Test creating trade record."""
        trade = TradeRecord(
            ts_us=1000000,
            symbol='BTC-PERP',
            price=5000000000000,
            size=10000000,
            side='buy',
            is_liquidation=True,
        )
        assert trade.symbol == 'BTC-PERP'
        assert trade.is_liquidation is True


class TestColdStorage:
    """Tests for ColdStorage."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create temporary storage."""
        db_path = str(tmp_path / 'test.db')
        config = StorageConfig(db_path=db_path)
        storage = ColdStorage(config)
        yield storage
        storage.close()

    def test_init_creates_tables(self, storage):
        """Test initialization creates tables."""
        stats = storage.get_stats()
        assert stats['snapshot_count'] == 0
        assert stats['trade_count'] == 0

    def test_insert_snapshot(self, storage):
        """Test inserting single snapshot."""
        snap = MarketSnapshot(
            ts_us=1000000,
            symbol='BTC-PERP',
            open_interest=1000000,
            funding_rate=100,
            mark_price=5000000000000,
        )
        storage.insert_snapshot(snap)

        stats = storage.get_stats()
        assert stats['snapshot_count'] == 1

    def test_insert_snapshots_batch(self, storage):
        """Test batch insert."""
        snapshots = [
            MarketSnapshot(ts_us=i * 1000000, symbol='BTC-PERP', open_interest=1000000,
                          funding_rate=100, mark_price=5000000000000)
            for i in range(100)
        ]
        storage.insert_snapshots_batch(snapshots)

        stats = storage.get_stats()
        assert stats['snapshot_count'] == 100

    def test_insert_trade(self, storage):
        """Test inserting single trade."""
        trade = TradeRecord(
            ts_us=1000000,
            symbol='BTC-PERP',
            price=5000000000000,
            size=10000000,
            side='buy',
            is_liquidation=True,
        )
        storage.insert_trade(trade)

        stats = storage.get_stats()
        assert stats['trade_count'] == 1
        assert stats['liquidation_count'] == 1

    def test_insert_trades_batch(self, storage):
        """Test batch trade insert."""
        trades = [
            TradeRecord(ts_us=i * 1000000, symbol='BTC-PERP', price=5000000000000,
                       size=10000000, side='buy', is_liquidation=(i % 10 == 0))
            for i in range(100)
        ]
        storage.insert_trades_batch(trades)

        stats = storage.get_stats()
        assert stats['trade_count'] == 100
        assert stats['liquidation_count'] == 10

    def test_query_snapshots(self, storage):
        """Test querying snapshots."""
        # Insert test data
        for i in range(10):
            storage.insert_snapshot(MarketSnapshot(
                ts_us=i * 1000000,
                symbol='BTC-PERP',
                open_interest=1000000 + i,
                funding_rate=100,
                mark_price=5000000000000,
            ))

        # Query all
        result = storage.query_snapshots()
        assert result.count == 10

        # Query with time range
        result = storage.query_snapshots(start_ts=3000000, end_ts=7000000)
        assert result.count == 4  # 3, 4, 5, 6

        # Query with symbol filter
        result = storage.query_snapshots(symbol='ETH-PERP')
        assert result.count == 0

    def test_query_trades(self, storage):
        """Test querying trades."""
        # Insert test data
        for i in range(20):
            storage.insert_trade(TradeRecord(
                ts_us=i * 1000000,
                symbol='BTC-PERP',
                price=5000000000000,
                size=10000000,
                side='buy',
                is_liquidation=(i % 5 == 0),
            ))

        # Query all
        result = storage.query_trades()
        assert result.count == 20

        # Query liquidations only
        result = storage.query_trades(liquidations_only=True)
        assert result.count == 4  # 0, 5, 10, 15

    def test_get_symbols(self, storage):
        """Test getting unique symbols."""
        for symbol in ['BTC-PERP', 'ETH-PERP', 'SOL-PERP']:
            storage.insert_snapshot(MarketSnapshot(
                ts_us=1000000,
                symbol=symbol,
                open_interest=1000000,
                funding_rate=100,
                mark_price=5000000000000,
            ))

        symbols = storage.get_symbols()
        assert len(symbols) == 3
        assert 'BTC-PERP' in symbols

    def test_get_time_range(self, storage):
        """Test getting time range."""
        for i in range(10, 20):
            storage.insert_snapshot(MarketSnapshot(
                ts_us=i * 1000000,
                symbol='BTC-PERP',
                open_interest=1000000,
                funding_rate=100,
                mark_price=5000000000000,
            ))

        time_range = storage.get_time_range()
        assert time_range == (10000000, 19000000)

    def test_upsert_snapshot(self, storage):
        """Test that duplicate timestamps are updated."""
        snap1 = MarketSnapshot(
            ts_us=1000000,
            symbol='BTC-PERP',
            open_interest=1000000,
            funding_rate=100,
            mark_price=5000000000000,
        )
        snap2 = MarketSnapshot(
            ts_us=1000000,  # Same timestamp
            symbol='BTC-PERP',
            open_interest=2000000,  # Different OI
            funding_rate=100,
            mark_price=5000000000000,
        )

        storage.insert_snapshot(snap1)
        storage.insert_snapshot(snap2)

        result = storage.query_snapshots()
        assert result.count == 1
        assert result.rows[0].open_interest == 2000000


# =============================================================================
# Event Labeler Tests
# =============================================================================

class TestLabelConfig:
    """Tests for LabelConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = LabelConfig()
        assert config.cascade_oi_drop_pct == 0.15
        assert config.cascade_window_sec == 60


class TestEventLabeler:
    """Tests for EventLabeler."""

    @pytest.fixture
    def labeler(self):
        """Create labeler with default config."""
        return EventLabeler()

    def test_label_cascades_empty(self, labeler):
        """Test with empty data."""
        events = labeler.label_cascades([])
        assert len(events) == 0

    def test_label_cascades_single_symbol(self, labeler):
        """Test cascade detection on single symbol."""
        # Create cascade scenario: OI drops 20% in 30 seconds with skewed funding
        snapshots = []
        base_ts = 1000000000000

        # Initial state with high OI and skewed funding
        for i in range(10):
            oi = 1000000 - (i * 25000)  # OI drops 2.5% per step
            snapshots.append(SnapshotData(
                ts_us=base_ts + (i * 3000000),  # 3 seconds apart
                symbol='BTC-PERP',
                open_interest=oi,
                funding_rate=0.02,  # 2% funding (skewed)
                mark_price=50000,
            ))

        events = labeler.label_cascades(snapshots)

        # Should detect cascade (22.5% drop over 27 seconds)
        assert len(events) >= 1
        assert events[0].event_type == EventLabel.CASCADE
        assert events[0].metrics['oi_drop_pct'] >= 0.15

    def test_label_cascades_no_funding_skew(self, labeler):
        """Test that cascade without funding skew is not labeled."""
        snapshots = []
        base_ts = 1000000000000

        for i in range(10):
            oi = 1000000 - (i * 25000)
            snapshots.append(SnapshotData(
                ts_us=base_ts + (i * 3000000),
                symbol='BTC-PERP',
                open_interest=oi,
                funding_rate=0.001,  # Low funding (not skewed)
                mark_price=50000,
            ))

        events = labeler.label_cascades(snapshots)
        assert len(events) == 0

    def test_label_cascades_multiple_symbols(self, labeler):
        """Test cascade detection across multiple symbols."""
        snapshots = []
        base_ts = 1000000000000

        for symbol in ['BTC-PERP', 'ETH-PERP']:
            for i in range(10):
                oi = 1000000 - (i * 25000)
                snapshots.append(SnapshotData(
                    ts_us=base_ts + (i * 3000000),
                    symbol=symbol,
                    open_interest=oi,
                    funding_rate=0.02,
                    mark_price=50000,
                ))

        events = labeler.label_cascades(snapshots)

        # Should detect cascade for both symbols
        symbols = [e.symbol for e in events]
        assert 'BTC-PERP' in symbols
        assert 'ETH-PERP' in symbols

    def test_label_hunt_failures(self, labeler):
        """Test hunt failure detection."""
        snapshots = []
        base_ts = 1000000000000

        # OI spike followed by price rejection
        # Initial state
        snapshots.append(SnapshotData(
            ts_us=base_ts,
            symbol='BTC-PERP',
            open_interest=1000000,
            funding_rate=0.02,  # Longs paying
            mark_price=50000,
        ))

        # OI spike (hunting longs)
        for i in range(1, 5):
            snapshots.append(SnapshotData(
                ts_us=base_ts + (i * 30000000),  # 30 sec apart
                symbol='BTC-PERP',
                open_interest=1000000 + (i * 30000),  # OI increasing
                funding_rate=0.02,
                mark_price=50000 - (i * 300),  # Price dropping
            ))

        # Price rejection (bounces back)
        for i in range(5, 10):
            snapshots.append(SnapshotData(
                ts_us=base_ts + (i * 30000000),
                symbol='BTC-PERP',
                open_interest=1100000,
                funding_rate=0.02,
                mark_price=48800 + ((i - 5) * 500),  # Price recovering
            ))

        events = labeler.label_hunt_failures(snapshots)

        # Should detect hunt failure
        assert len(events) >= 1
        assert events[0].event_type == EventLabel.HUNT_FAILED

    def test_label_squeezes(self, labeler):
        """Test squeeze detection."""
        snapshots = []
        base_ts = 1000000000000

        # Short squeeze: positive funding (longs pay), OI drops, price rises
        for i in range(10):
            oi = 1000000 - (i * 15000)  # OI dropping
            price = 50000 + (i * 350)   # Price rising
            snapshots.append(SnapshotData(
                ts_us=base_ts + (i * 10000000),  # 10 sec apart
                symbol='BTC-PERP',
                open_interest=oi,
                funding_rate=0.02,  # Positive funding
                mark_price=price,
            ))

        events = labeler.label_squeezes(snapshots)

        # Should detect squeeze
        assert len(events) >= 1
        assert events[0].event_type == EventLabel.SQUEEZE
        assert events[0].metrics['squeeze_type'] == 'short'

    def test_label_all(self, labeler):
        """Test labeling all event types."""
        # Create mixed scenario
        snapshots = []
        base_ts = 1000000000000

        for i in range(20):
            oi = 1000000 - (i * 20000)
            snapshots.append(SnapshotData(
                ts_us=base_ts + (i * 3000000),
                symbol='BTC-PERP',
                open_interest=oi,
                funding_rate=0.02,
                mark_price=50000 + (i * 200),
            ))

        result = labeler.label_all(snapshots)

        assert EventLabel.CASCADE in result
        assert EventLabel.HUNT_FAILED in result
        assert EventLabel.SQUEEZE in result

    def test_labeled_event_serialization(self, labeler):
        """Test LabeledEvent to_dict."""
        event = LabeledEvent(
            event_id='test_1',
            event_type=EventLabel.CASCADE,
            symbol='BTC-PERP',
            start_ts=1000000,
            end_ts=2000000,
            metrics={'oi_drop_pct': 0.15},
        )

        data = event.to_dict()
        assert data['event_type'] == 'cascade'
        assert 'metrics' in data

    def test_get_stats(self, labeler):
        """Test getting labeling statistics."""
        events = {
            EventLabel.CASCADE: [
                LabeledEvent('1', EventLabel.CASCADE, 'BTC-PERP', 1000, 2000, {}),
                LabeledEvent('2', EventLabel.CASCADE, 'ETH-PERP', 1000, 2000, {}),
            ],
            EventLabel.HUNT_FAILED: [
                LabeledEvent('3', EventLabel.HUNT_FAILED, 'BTC-PERP', 1000, 2000, {}),
            ],
            EventLabel.SQUEEZE: [],
        }

        stats = labeler.get_stats(events)

        assert stats['total_events'] == 3
        assert stats['by_type']['cascade'] == 2
        assert stats['by_type']['hunt_failed'] == 1
        assert 'BTC-PERP' in stats['symbols']
