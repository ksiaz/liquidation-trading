"""
Unit tests for Binance Collector Service.

Tests configuration, state management, and statistics tracking.
Does not test actual API calls (those require mocking or integration tests).
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from runtime.binance import (
    BinanceCollector,
    CollectorConfig,
    CollectorStats,
    CollectorState,
    BinanceClient,
    FundingInfo,
    SpotPrice,
)


class TestCollectorConfig:
    """Tests for CollectorConfig."""

    def test_default_symbols(self):
        """Default config includes standard symbols."""
        config = CollectorConfig()
        assert 'BTC' in config.symbols
        assert 'ETH' in config.symbols
        assert len(config.symbols) == 10

    def test_default_intervals(self):
        """Default intervals are reasonable."""
        config = CollectorConfig()
        assert config.funding_poll_interval == 60.0
        assert config.spot_poll_interval == 10.0

    def test_custom_symbols(self):
        """Custom symbols can be specified."""
        config = CollectorConfig(symbols=['BTC', 'ETH'])
        assert config.symbols == ['BTC', 'ETH']

    def test_custom_intervals(self):
        """Custom intervals can be specified."""
        config = CollectorConfig(
            funding_poll_interval=120.0,
            spot_poll_interval=5.0
        )
        assert config.funding_poll_interval == 120.0
        assert config.spot_poll_interval == 5.0


class TestCollectorStats:
    """Tests for CollectorStats."""

    def test_initial_stats(self):
        """Initial stats are all zero."""
        stats = CollectorStats()
        assert stats.funding_polls == 0
        assert stats.spot_polls == 0
        assert stats.funding_records == 0
        assert stats.spot_records == 0
        assert stats.errors == 0

    def test_to_dict(self):
        """Stats can be converted to dictionary."""
        stats = CollectorStats(
            funding_polls=10,
            spot_polls=20,
            funding_records=100,
            spot_records=200,
            errors=2
        )
        d = stats.to_dict()
        assert d['funding_polls'] == 10
        assert d['spot_polls'] == 20
        assert d['funding_records'] == 100
        assert d['spot_records'] == 200
        assert d['errors'] == 2


class TestCollectorState:
    """Tests for CollectorState enum."""

    def test_all_states_exist(self):
        """All expected states exist."""
        assert CollectorState.STOPPED
        assert CollectorState.RUNNING
        assert CollectorState.PAUSED
        assert CollectorState.ERROR


class TestBinanceCollector:
    """Tests for BinanceCollector."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.log_binance_funding_snapshot = MagicMock()
        db.log_spot_price_snapshot = MagicMock()
        return db

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CollectorConfig(
            symbols=['BTC', 'ETH'],
            funding_poll_interval=1.0,
            spot_poll_interval=0.5
        )

    @pytest.fixture
    def collector(self, mock_db, config):
        """Create collector instance."""
        return BinanceCollector(mock_db, config)

    def test_initial_state_is_stopped(self, collector):
        """Collector starts in STOPPED state."""
        assert collector.state == CollectorState.STOPPED

    def test_initial_stats_empty(self, collector):
        """Initial statistics are empty."""
        stats = collector.stats
        assert stats.funding_polls == 0
        assert stats.spot_polls == 0

    def test_get_status(self, collector):
        """Status returns expected structure."""
        status = collector.get_status()

        assert 'state' in status
        assert 'symbols' in status
        assert 'funding_interval' in status
        assert 'spot_interval' in status
        assert 'stats' in status

        assert status['state'] == 'STOPPED'
        assert status['symbols'] == ['BTC', 'ETH']

    def test_start_changes_state(self, collector):
        """Starting collector changes state to RUNNING."""
        collector.start()
        assert collector.state == CollectorState.RUNNING

        # Clean up
        collector.stop()

    def test_stop_changes_state(self, collector):
        """Stopping collector changes state to STOPPED."""
        collector.start()
        collector.stop()
        assert collector.state == CollectorState.STOPPED

    def test_pause_and_resume(self, collector):
        """Collector can be paused and resumed."""
        collector.start()
        assert collector.state == CollectorState.RUNNING

        collector.pause()
        assert collector.state == CollectorState.PAUSED

        collector.resume()
        assert collector.state == CollectorState.RUNNING

        collector.stop()

    def test_double_start_is_safe(self, collector):
        """Starting an already running collector is safe."""
        collector.start()
        collector.start()  # Should not raise
        assert collector.state == CollectorState.RUNNING
        collector.stop()

    def test_double_stop_is_safe(self, collector):
        """Stopping an already stopped collector is safe."""
        collector.stop()  # Already stopped
        collector.stop()  # Should not raise
        assert collector.state == CollectorState.STOPPED


class TestBinanceClient:
    """Tests for BinanceClient."""

    @pytest.fixture
    def client(self):
        """Create client instance."""
        return BinanceClient()

    def test_symbol_mapping(self, client):
        """Symbols are correctly mapped to Binance format."""
        assert client._to_binance_symbol('BTC') == 'BTCUSDT'
        assert client._to_binance_symbol('ETH') == 'ETHUSDT'
        assert client._to_binance_symbol('SOL') == 'SOLUSDT'

    def test_unknown_symbol_mapping(self, client):
        """Unknown symbols get USDT suffix."""
        assert client._to_binance_symbol('UNKNOWN') == 'UNKNOWNUSDT'

    def test_symbol_case_insensitive(self, client):
        """Symbol mapping is case insensitive."""
        assert client._to_binance_symbol('btc') == 'BTCUSDT'
        assert client._to_binance_symbol('Btc') == 'BTCUSDT'


class TestFundingInfo:
    """Tests for FundingInfo dataclass."""

    def test_funding_info_creation(self):
        """FundingInfo can be created with all fields."""
        info = FundingInfo(
            symbol='BTC',
            mark_price=50000.0,
            index_price=50010.0,
            funding_rate=0.0001,
            next_funding_time=1700000000000,
            timestamp=1700000000000000000
        )
        assert info.symbol == 'BTC'
        assert info.funding_rate == 0.0001


class TestSpotPrice:
    """Tests for SpotPrice dataclass."""

    def test_spot_price_creation(self):
        """SpotPrice can be created with all fields."""
        price = SpotPrice(
            symbol='BTC',
            price=50000.0,
            timestamp=1700000000000000000
        )
        assert price.symbol == 'BTC'
        assert price.price == 50000.0
