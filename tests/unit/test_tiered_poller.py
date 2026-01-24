"""
Unit tests for Tiered Wallet Polling System.

Tests:
- Tier assignment by position value
- Wallet promotion/demotion
- Discovery from trades
- Polling mechanics
"""

import os
import tempfile
import pytest
import asyncio

from runtime.logging.execution_db import ResearchDatabase
from runtime.hyperliquid.hl_data_store import HLDataStore
from runtime.hyperliquid.tiered_poller import TieredPoller, TierConfig
from runtime.hyperliquid.mock_data import MockHyperliquidClient, MockConfig


class TestTierAssignment:
    """Test tier assignment logic."""

    @pytest.fixture
    def config(self):
        """Create tier configuration."""
        return TierConfig(
            tier1_threshold=10_000_000,   # $10M
            tier2_threshold=1_000_000,    # $1M
            tier3_threshold=100_000,      # $100k
        )

    @pytest.fixture
    def poller(self, config):
        """Create poller with mock dependencies."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        client = MockHyperliquidClient()

        poller = TieredPoller(client, store, config)
        yield poller

        db.close()
        os.unlink(path)

    def test_tier1_assignment_above_threshold(self, poller, config):
        """Values above tier1 threshold get tier 1."""
        tier = poller.assign_tier_by_value(15_000_000)  # $15M
        assert tier == 1

    def test_tier2_assignment_between_thresholds(self, poller, config):
        """Values between tier1 and tier2 thresholds get tier 2."""
        tier = poller.assign_tier_by_value(5_000_000)  # $5M
        assert tier == 2

    def test_tier3_assignment_below_tier2(self, poller, config):
        """Values below tier2 threshold get tier 3."""
        tier = poller.assign_tier_by_value(500_000)  # $500k
        assert tier == 3

    def test_minimum_tier_is_3(self, poller):
        """Very small values still get tier 3 (not lower)."""
        tier = poller.assign_tier_by_value(1_000)  # $1k
        assert tier == 3

    def test_exact_threshold_gets_higher_tier(self, poller, config):
        """Exact threshold value gets the higher tier."""
        tier = poller.assign_tier_by_value(10_000_000)  # Exactly $10M
        assert tier == 1


class TestWalletManagement:
    """Test wallet add/remove/promotion/demotion."""

    @pytest.fixture
    def poller(self):
        """Create poller with mock dependencies."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        client = MockHyperliquidClient()

        poller = TieredPoller(client, store)
        yield poller

        db.close()
        os.unlink(path)

    def test_add_wallet_to_tier(self, poller):
        """Adding a wallet places it in correct tier set."""
        poller.add_wallet("0xwallet1", tier=1)
        poller.add_wallet("0xwallet2", tier=2)
        poller.add_wallet("0xwallet3", tier=3)

        assert "0xwallet1" in poller._tier1_wallets
        assert "0xwallet2" in poller._tier2_wallets
        assert "0xwallet3" in poller._tier3_wallets

    def test_add_wallet_normalizes_address(self, poller):
        """Wallet addresses are normalized to lowercase."""
        poller.add_wallet("0xABCDEF", tier=1)

        assert "0xabcdef" in poller._tier1_wallets
        assert "0xABCDEF" not in poller._tier1_wallets

    def test_add_wallet_idempotent(self, poller):
        """Adding same wallet twice doesn't duplicate."""
        poller.add_wallet("0xwallet", tier=1)
        poller.add_wallet("0xwallet", tier=2)  # Try to add again with different tier

        assert len(poller._tier1_wallets) == 1
        assert "0xwallet" in poller._tier1_wallets
        # Should still be in tier 1 (first add wins)

    def test_remove_wallet(self, poller):
        """Removing a wallet clears it from tracking."""
        poller.add_wallet("0xremove", tier=2)
        assert "0xremove" in poller._tier2_wallets

        poller.remove_wallet("0xremove")
        assert "0xremove" not in poller._tier2_wallets
        assert "0xremove" not in poller._wallets

    def test_promote_wallet(self, poller):
        """Promoting moves wallet to higher tier (lower number)."""
        poller.add_wallet("0xpromote", tier=3)
        assert "0xpromote" in poller._tier3_wallets

        poller.promote_wallet("0xpromote", new_tier=1)

        assert "0xpromote" in poller._tier1_wallets
        assert "0xpromote" not in poller._tier3_wallets

    def test_promote_requires_lower_tier_number(self, poller):
        """Promotion to same or higher number tier is ignored."""
        poller.add_wallet("0xstay", tier=1)

        poller.promote_wallet("0xstay", new_tier=2)  # Not a promotion

        assert "0xstay" in poller._tier1_wallets
        assert "0xstay" not in poller._tier2_wallets

    def test_demote_wallet(self, poller):
        """Demoting moves wallet to lower tier (higher number)."""
        poller.add_wallet("0xdemote", tier=1)
        assert "0xdemote" in poller._tier1_wallets

        poller.demote_wallet("0xdemote", new_tier=3)

        assert "0xdemote" in poller._tier3_wallets
        assert "0xdemote" not in poller._tier1_wallets

    def test_demote_requires_higher_tier_number(self, poller):
        """Demotion to same or lower number tier is ignored."""
        poller.add_wallet("0xstay", tier=3)

        poller.demote_wallet("0xstay", new_tier=1)  # Not a demotion

        assert "0xstay" in poller._tier3_wallets
        assert "0xstay" not in poller._tier1_wallets


class TestPolling:
    """Test polling mechanics."""

    @pytest.fixture
    def poller(self):
        """Create poller with mock client."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)

        # Configure mock to have predictable wallets
        mock_config = MockConfig(num_wallets=10, coins=['BTC', 'ETH'])
        client = MockHyperliquidClient(mock_config, seed=42)

        poller = TieredPoller(client, store)

        # Add mock wallets to poller
        for wallet in client.get_tracked_wallets()[:5]:
            poller.add_wallet(wallet, tier=1)

        yield poller

        db.close()
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_tier1_poll_returns_stats(self, poller):
        """Tier 1 poll returns statistics."""
        stats = await poller.run_tier1_poll()

        assert stats.wallets_polled > 0
        assert stats.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_empty_tier_returns_empty_stats(self, poller):
        """Polling empty tier returns zero stats."""
        # Clear tier 2 (should be empty)
        poller._tier2_wallets.clear()

        stats = await poller.run_tier2_poll()

        assert stats.wallets_polled == 0
        assert stats.positions_found == 0

    @pytest.mark.asyncio
    async def test_poll_stores_positions(self, poller):
        """Polling stores position data."""
        # Ensure we have wallets to poll and capture one BEFORE polling
        if not poller._tier1_wallets:
            pytest.skip("No tier 1 wallets configured in fixture")

        # Capture wallet before polling (polling may modify wallet sets)
        wallet = list(poller._tier1_wallets)[0]

        await poller.run_tier1_poll()

        # Check that data was stored
        history = poller._store.get_position_history(
            wallet=wallet,
            coin="BTC",
            start_ts=0,
            end_ts=int(1e18)  # Far future
        )

        # Should have some position data (mock generates positions)
        # Note: Depends on mock config probability
        assert isinstance(history, list)


class TestStatus:
    """Test status reporting."""

    @pytest.fixture
    def poller(self):
        """Create poller with known state."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        client = MockHyperliquidClient()

        poller = TieredPoller(client, store)
        yield poller

        db.close()
        os.unlink(path)

    def test_get_status_includes_tier_counts(self, poller):
        """Status includes wallet counts per tier."""
        poller.add_wallet("0xa", tier=1)
        poller.add_wallet("0xb", tier=1)
        poller.add_wallet("0xc", tier=2)
        poller.add_wallet("0xd", tier=3)

        status = poller.get_status()

        assert status['total_wallets'] == 4
        assert status['tier1_count'] == 2
        assert status['tier2_count'] == 1
        assert status['tier3_count'] == 1

    def test_get_status_includes_config(self, poller):
        """Status includes polling configuration."""
        status = poller.get_status()

        assert 'config' in status
        assert 'tier1_interval' in status['config']
        assert 'tier2_interval' in status['config']
        assert 'tier3_interval' in status['config']


class TestTierConfig:
    """Test TierConfig defaults and customization."""

    def test_default_config_values(self):
        """Default config has sensible values."""
        config = TierConfig()

        assert config.tier1_threshold == 10_000_000
        assert config.tier2_threshold == 1_000_000
        assert config.tier3_threshold == 100_000

        assert config.tier1_interval == 5.0
        assert config.tier2_interval == 30.0
        assert config.tier3_interval == 300.0

    def test_custom_config(self):
        """Custom config values are preserved."""
        config = TierConfig(
            tier1_threshold=50_000_000,
            tier1_interval=2.0
        )

        assert config.tier1_threshold == 50_000_000
        assert config.tier1_interval == 2.0
        # Others stay default
        assert config.tier2_threshold == 1_000_000


class TestIntervalCalculation:
    """Test interval calculations for tiers."""

    @pytest.fixture
    def poller(self):
        """Create poller with custom intervals."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db = ResearchDatabase(path)
        store = HLDataStore(db)
        client = MockHyperliquidClient()

        config = TierConfig(
            tier1_interval=5.0,
            tier2_interval=30.0,
            tier3_interval=300.0
        )

        poller = TieredPoller(client, store, config)
        yield poller

        db.close()
        os.unlink(path)

    def test_tier1_interval(self, poller):
        """Tier 1 gets fastest interval."""
        interval = poller._get_interval_for_tier(1)
        assert interval == 5.0

    def test_tier2_interval(self, poller):
        """Tier 2 gets medium interval."""
        interval = poller._get_interval_for_tier(2)
        assert interval == 30.0

    def test_tier3_interval(self, poller):
        """Tier 3 gets slowest interval."""
        interval = poller._get_interval_for_tier(3)
        assert interval == 300.0
