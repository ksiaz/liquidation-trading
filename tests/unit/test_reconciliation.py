"""
Unit tests for position reconciliation (HLP18).

Tests:
- Position matching and syncing
- Handling local-only positions (ghost positions)
- Handling exchange-only positions (unknown exposure)
- Size and side mismatch detection
- Emergency stop creation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List

from runtime.executor.reconciliation import (
    PositionReconciler,
    PositionSnapshot,
    ReconciliationResult,
    ReconciliationAction,
)


# =============================================================================
# Mock Implementations
# =============================================================================

class MockExchangeClient:
    """Mock exchange client for testing."""

    def __init__(self):
        self.positions: List[PositionSnapshot] = []
        self.close_position_called: List[str] = []
        self.stop_orders_placed: List[Dict] = []

    async def get_positions(self) -> List[PositionSnapshot]:
        return self.positions

    async def close_position(self, symbol: str, market: bool = True) -> bool:
        self.close_position_called.append(symbol)
        return True

    async def get_open_orders(self, symbol: str) -> List[Dict]:
        return []

    async def place_stop_order(
        self, symbol: str, side: str, size: float, stop_price: float
    ) -> str:
        order = {
            'symbol': symbol,
            'side': side,
            'size': size,
            'stop_price': stop_price,
        }
        self.stop_orders_placed.append(order)
        return f"stop_{symbol}_{len(self.stop_orders_placed)}"


class MockPositionTracker:
    """Mock position tracker for testing."""

    def __init__(self):
        self.positions: Dict[str, PositionSnapshot] = {}

    def get_all_positions(self) -> Dict[str, PositionSnapshot]:
        return self.positions.copy()

    def update_position(self, symbol: str, snapshot: PositionSnapshot):
        self.positions[symbol] = snapshot

    def remove_position(self, symbol: str):
        self.positions.pop(symbol, None)

    def add_position(self, snapshot: PositionSnapshot):
        self.positions[snapshot.symbol] = snapshot


# =============================================================================
# Position Snapshot Tests
# =============================================================================

class TestPositionSnapshot:
    """Tests for PositionSnapshot."""

    def test_snapshot_creation(self):
        """Test creating a position snapshot."""
        snapshot = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="long",
            entry_price=50000,
            unrealized_pnl=100,
        )

        assert snapshot.symbol == "BTC-PERP"
        assert snapshot.size == 0.1
        assert snapshot.side == "long"
        assert snapshot.entry_price == 50000


# =============================================================================
# Reconciliation Tests
# =============================================================================

class TestPositionReconciler:
    """Tests for PositionReconciler."""

    @pytest.fixture
    def exchange(self):
        """Create mock exchange client."""
        return MockExchangeClient()

    @pytest.fixture
    def tracker(self):
        """Create mock position tracker."""
        return MockPositionTracker()

    @pytest.fixture
    def reconciler(self, exchange, tracker):
        """Create reconciler with mocks."""
        return PositionReconciler(
            exchange_client=exchange,
            position_tracker=tracker,
            auto_create_stops=False,  # Disable for most tests
        )

    @pytest.mark.asyncio
    async def test_clean_reconciliation_no_positions(self, reconciler):
        """Test reconciliation with no positions."""
        result = await reconciler.reconcile()

        assert result.is_clean
        assert result.local_positions == 0
        assert result.exchange_positions == 0
        assert len(result.diffs_found) == 0

    @pytest.mark.asyncio
    async def test_clean_reconciliation_matching_positions(
        self, exchange, tracker, reconciler
    ):
        """Test reconciliation with matching positions."""
        # Add same position to both
        pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="long",
            entry_price=50000,
        )
        exchange.positions = [pos]
        tracker.positions = {"BTC-PERP": pos}

        result = await reconciler.reconcile()

        assert result.is_clean
        assert result.positions_matched == 1
        assert len(result.diffs_found) == 0

    @pytest.mark.asyncio
    async def test_local_only_position_removed(self, exchange, tracker, reconciler):
        """Test that local-only positions are removed."""
        # Position only in local tracker
        local_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="long",
            entry_price=50000,
        )
        tracker.positions = {"BTC-PERP": local_pos}
        exchange.positions = []

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.diffs_found) == 1
        assert result.diffs_found[0].diff_type == 'local_only'
        assert result.diffs_found[0].severity == 'critical'

        # Position should be removed from tracker
        assert "BTC-PERP" not in tracker.positions

    @pytest.mark.asyncio
    async def test_exchange_only_position_synced(self, exchange, tracker, reconciler):
        """Test that exchange-only positions are synced to local."""
        # Position only on exchange
        exchange_pos = PositionSnapshot(
            symbol="ETH-PERP",
            size=1.0,
            side="short",
            entry_price=3000,
        )
        exchange.positions = [exchange_pos]
        tracker.positions = {}

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.diffs_found) == 1
        assert result.diffs_found[0].diff_type == 'exchange_only'
        assert result.diffs_found[0].severity == 'warning'
        assert result.positions_synced == 1

        # Position should be added to tracker
        assert "ETH-PERP" in tracker.positions
        assert tracker.positions["ETH-PERP"].size == 1.0

    @pytest.mark.asyncio
    async def test_size_mismatch_corrected(self, exchange, tracker, reconciler):
        """Test that size mismatches are corrected to exchange value."""
        # Same symbol, different sizes
        local_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="long",
            entry_price=50000,
        )
        exchange_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.15,  # Different size
            side="long",
            entry_price=50000,
        )
        tracker.positions = {"BTC-PERP": local_pos}
        exchange.positions = [exchange_pos]

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.diffs_found) == 1
        assert result.diffs_found[0].diff_type == 'size_mismatch'

        # Local should be updated to exchange value
        assert tracker.positions["BTC-PERP"].size == 0.15

    @pytest.mark.asyncio
    async def test_side_mismatch_corrected(self, exchange, tracker, reconciler):
        """Test that side mismatches are corrected."""
        # Same symbol, different sides
        local_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="long",
            entry_price=50000,
        )
        exchange_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="short",  # Different side
            entry_price=50000,
        )
        tracker.positions = {"BTC-PERP": local_pos}
        exchange.positions = [exchange_pos]

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.diffs_found) == 1
        assert result.diffs_found[0].diff_type == 'side_mismatch'
        assert result.diffs_found[0].severity == 'critical'

        # Local should be updated to exchange value
        assert tracker.positions["BTC-PERP"].side == "short"

    @pytest.mark.asyncio
    async def test_size_within_tolerance_is_clean(self, exchange, tracker):
        """Test that small size differences within tolerance are clean."""
        reconciler = PositionReconciler(
            exchange_client=exchange,
            position_tracker=tracker,
            size_tolerance=0.01,  # 1% tolerance
        )

        local_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.100,
            side="long",
            entry_price=50000,
        )
        exchange_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1005,  # 0.5% difference
            side="long",
            entry_price=50000,
        )
        tracker.positions = {"BTC-PERP": local_pos}
        exchange.positions = [exchange_pos]

        result = await reconciler.reconcile()

        assert result.is_clean
        assert len(result.diffs_found) == 0

    @pytest.mark.asyncio
    async def test_multiple_positions(self, exchange, tracker, reconciler):
        """Test reconciliation with multiple positions."""
        # Multiple matching positions
        positions = [
            PositionSnapshot("BTC-PERP", 0.1, "long", 50000),
            PositionSnapshot("ETH-PERP", 1.0, "short", 3000),
            PositionSnapshot("SOL-PERP", 10.0, "long", 100),
        ]
        exchange.positions = positions
        tracker.positions = {p.symbol: p for p in positions}

        result = await reconciler.reconcile()

        assert result.is_clean
        assert result.positions_matched == 3
        assert result.exchange_positions == 3
        assert result.local_positions == 3

    @pytest.mark.asyncio
    async def test_auto_create_stops(self, exchange, tracker):
        """Test automatic stop order creation."""
        reconciler = PositionReconciler(
            exchange_client=exchange,
            position_tracker=tracker,
            auto_create_stops=True,
        )

        # Exchange position without stop
        exchange_pos = PositionSnapshot(
            symbol="BTC-PERP",
            size=0.1,
            side="long",
            entry_price=50000,
            stop_order_active=False,
        )
        exchange.positions = [exchange_pos]
        tracker.positions = {}

        result = await reconciler.reconcile()

        # Should have created stop
        assert len(exchange.stop_orders_placed) == 1
        assert exchange.stop_orders_placed[0]['symbol'] == "BTC-PERP"
        assert "Created emergency stop" in str(result.actions_taken)

    @pytest.mark.asyncio
    async def test_alert_callback_called(self, exchange, tracker, reconciler):
        """Test that alert callbacks are invoked."""
        alerts_received = []

        async def alert_handler(alert_type, symbol, message):
            alerts_received.append((alert_type, symbol, message))

        reconciler.add_alert_callback(alert_handler)

        # Create local-only position (should trigger alert)
        tracker.positions = {
            "BTC-PERP": PositionSnapshot("BTC-PERP", 0.1, "long", 50000)
        }
        exchange.positions = []

        await reconciler.reconcile()

        assert len(alerts_received) == 1
        assert alerts_received[0][0] == "POSITION_MISMATCH_LOCAL_ONLY"
        assert alerts_received[0][1] == "BTC-PERP"

    @pytest.mark.asyncio
    async def test_error_handling(self, tracker):
        """Test handling of exchange errors."""
        # Exchange that throws
        class FailingExchange:
            async def get_positions(self):
                raise Exception("Connection failed")

        reconciler = PositionReconciler(
            exchange_client=FailingExchange(),
            position_tracker=tracker,
        )

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.errors) == 1
        assert "Connection failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_get_status(self, reconciler):
        """Test getting reconciler status."""
        status = reconciler.get_status()

        assert 'last_reconcile' in status
        assert 'consecutive_failures' in status
        assert status['consecutive_failures'] == 0

    @pytest.mark.asyncio
    async def test_consecutive_failures_tracked(self, tracker):
        """Test that consecutive failures are tracked."""
        class FailingExchange:
            async def get_positions(self):
                raise Exception("Failed")

        reconciler = PositionReconciler(
            exchange_client=FailingExchange(),
            position_tracker=tracker,
        )

        await reconciler.reconcile()
        await reconciler.reconcile()
        await reconciler.reconcile()

        status = reconciler.get_status()
        assert status['consecutive_failures'] == 3

    @pytest.mark.asyncio
    async def test_result_to_dict(self, exchange, tracker, reconciler):
        """Test result serialization."""
        tracker.positions = {
            "BTC-PERP": PositionSnapshot("BTC-PERP", 0.1, "long", 50000)
        }
        exchange.positions = []

        result = await reconciler.reconcile()
        data = result.to_dict()

        assert 'timestamp' in data
        assert 'is_clean' in data
        assert 'diffs_found' in data
        assert 'actions_taken' in data


# =============================================================================
# Complex Scenario Tests
# =============================================================================

class TestReconciliationScenarios:
    """Tests for complex reconciliation scenarios."""

    @pytest.mark.asyncio
    async def test_mixed_scenario(self):
        """Test scenario with multiple types of issues."""
        exchange = MockExchangeClient()
        tracker = MockPositionTracker()
        reconciler = PositionReconciler(exchange, tracker)

        # Local positions
        tracker.positions = {
            "BTC-PERP": PositionSnapshot("BTC-PERP", 0.1, "long", 50000),  # Matching
            "ETH-PERP": PositionSnapshot("ETH-PERP", 1.0, "short", 3000),  # Size mismatch
            "SOL-PERP": PositionSnapshot("SOL-PERP", 10.0, "long", 100),  # Local only
        }

        # Exchange positions
        exchange.positions = [
            PositionSnapshot("BTC-PERP", 0.1, "long", 50000),  # Matching
            PositionSnapshot("ETH-PERP", 1.5, "short", 3000),  # Size mismatch
            PositionSnapshot("DOGE-PERP", 1000, "long", 0.1),  # Exchange only
        ]

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.diffs_found) == 3  # Local only, exchange only, size mismatch
        assert result.positions_matched == 2  # BTC and ETH matched (even with size issue)

        # Check corrections
        assert "SOL-PERP" not in tracker.positions  # Removed ghost
        assert "DOGE-PERP" in tracker.positions  # Added unknown
        assert tracker.positions["ETH-PERP"].size == 1.5  # Fixed size

    @pytest.mark.asyncio
    async def test_all_positions_closed_on_exchange(self):
        """Test when all local positions were closed on exchange."""
        exchange = MockExchangeClient()
        tracker = MockPositionTracker()
        reconciler = PositionReconciler(exchange, tracker)

        # Local has positions
        tracker.positions = {
            "BTC-PERP": PositionSnapshot("BTC-PERP", 0.1, "long", 50000),
            "ETH-PERP": PositionSnapshot("ETH-PERP", 1.0, "short", 3000),
        }

        # Exchange is empty
        exchange.positions = []

        result = await reconciler.reconcile()

        assert not result.is_clean
        assert len(result.diffs_found) == 2
        assert all(d.diff_type == 'local_only' for d in result.diffs_found)

        # All should be removed
        assert len(tracker.positions) == 0
