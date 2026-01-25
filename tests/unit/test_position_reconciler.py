"""
Unit tests for HLP18 PositionReconciler.

Tests position synchronization and discrepancy handling.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from runtime.exchange.types import (
    OrderSide,
    ReconciliationAction,
    ReconciliationResult,
)
from runtime.exchange.position_reconciler import (
    PositionReconciler,
    ReconcilerConfig,
    LocalPosition
)


class TestLocalPositionManagement:
    """Tests for local position management."""

    def test_set_local_position(self):
        """Test setting a local position."""
        reconciler = PositionReconciler()
        reconciler.set_local_position(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            entry_price=50000.0,
            stop_order_id="stop_123"
        )

        pos = reconciler.get_local_position("BTC")
        assert pos is not None
        assert pos.symbol == "BTC"
        assert pos.side == OrderSide.BUY
        assert pos.size == 1.0
        assert pos.entry_price == 50000.0
        assert pos.stop_order_id == "stop_123"

    def test_clear_local_position(self):
        """Test clearing a local position."""
        reconciler = PositionReconciler()
        reconciler.set_local_position("BTC", OrderSide.BUY, 1.0, 50000.0)
        reconciler.clear_local_position("BTC")

        pos = reconciler.get_local_position("BTC")
        assert pos is None

    def test_get_all_local_positions(self):
        """Test getting all local positions."""
        reconciler = PositionReconciler()
        reconciler.set_local_position("BTC", OrderSide.BUY, 1.0, 50000.0)
        reconciler.set_local_position("ETH", OrderSide.SELL, 10.0, 3000.0)

        positions = reconciler.get_all_local_positions()
        assert len(positions) == 2
        assert "BTC" in positions
        assert "ETH" in positions


class TestPositionMatching:
    """Tests for position comparison logic."""

    def test_positions_match_same_side_same_size(self):
        """Test positions match when same side and size."""
        reconciler = PositionReconciler()
        local = LocalPosition(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            entry_price=50000.0
        )
        exchange = {
            'symbol': 'BTC',
            'size': 1.0,  # Positive = long
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        assert reconciler._positions_match(local, exchange)

    def test_positions_mismatch_different_side(self):
        """Test positions don't match with different sides."""
        reconciler = PositionReconciler()
        local = LocalPosition(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            entry_price=50000.0
        )
        exchange = {
            'symbol': 'BTC',
            'size': -1.0,  # Negative = short
            'side': OrderSide.SELL,
            'entry_price': 50000.0
        }

        assert not reconciler._positions_match(local, exchange)

    def test_positions_mismatch_different_size(self):
        """Test positions don't match with significant size difference."""
        config = ReconcilerConfig(size_tolerance_pct=0.01)  # 1% tolerance
        reconciler = PositionReconciler(config=config)

        local = LocalPosition(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            entry_price=50000.0
        )
        exchange = {
            'symbol': 'BTC',
            'size': 0.9,  # 10% difference
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        assert not reconciler._positions_match(local, exchange)

    def test_positions_match_within_tolerance(self):
        """Test positions match when within size tolerance."""
        config = ReconcilerConfig(size_tolerance_pct=0.05)  # 5% tolerance
        reconciler = PositionReconciler(config=config)

        local = LocalPosition(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            entry_price=50000.0
        )
        exchange = {
            'symbol': 'BTC',
            'size': 0.98,  # 2% difference, within tolerance
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        assert reconciler._positions_match(local, exchange)


class TestDiscrepancyHandling:
    """Tests for discrepancy handling."""

    def test_handle_unknown_position(self):
        """Test handling unknown position on exchange."""
        reconciler = PositionReconciler()

        callback = MagicMock()
        reconciler.set_discrepancy_callback(callback)

        exchange_pos = {
            'symbol': 'BTC',
            'size': 1.0,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        result = reconciler._handle_unknown_position("BTC", exchange_pos)

        assert result.symbol == "BTC"
        assert result.action == ReconciliationAction.EMERGENCY_CLOSE
        assert result.expected_size == 0
        assert result.actual_size == 1.0
        callback.assert_called_once()

    def test_handle_missing_position(self):
        """Test handling position missing from exchange."""
        reconciler = PositionReconciler()
        reconciler.set_local_position("BTC", OrderSide.BUY, 1.0, 50000.0)

        callback = MagicMock()
        reconciler.set_discrepancy_callback(callback)

        local_pos = reconciler.get_local_position("BTC")
        result = reconciler._handle_missing_position("BTC", local_pos)

        assert result.symbol == "BTC"
        assert result.action == ReconciliationAction.RESET_STATE
        assert result.expected_size == 1.0
        assert result.actual_size == 0

        # Local position should be cleared
        assert reconciler.get_local_position("BTC") is None
        callback.assert_called_once()

    def test_handle_size_mismatch(self):
        """Test handling size mismatch."""
        reconciler = PositionReconciler()
        reconciler.set_local_position("BTC", OrderSide.BUY, 1.0, 50000.0)

        callback = MagicMock()
        reconciler.set_discrepancy_callback(callback)

        local_pos = reconciler.get_local_position("BTC")
        exchange_pos = {
            'symbol': 'BTC',
            'size': 0.8,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        result = reconciler._handle_size_mismatch("BTC", local_pos, exchange_pos)

        assert result.symbol == "BTC"
        assert result.action == ReconciliationAction.SYNC_LOCAL
        assert result.expected_size == 1.0
        assert result.actual_size == 0.8

        # Local position should be updated
        updated_pos = reconciler.get_local_position("BTC")
        assert updated_pos.size == 0.8
        callback.assert_called_once()

    def test_handle_size_mismatch_with_stop(self):
        """Test size mismatch with stop order triggers adjust action."""
        reconciler = PositionReconciler()
        reconciler.set_local_position(
            "BTC", OrderSide.BUY, 1.0, 50000.0,
            stop_order_id="stop_123"
        )

        local_pos = reconciler.get_local_position("BTC")
        exchange_pos = {
            'symbol': 'BTC',
            'size': 0.8,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        result = reconciler._handle_size_mismatch("BTC", local_pos, exchange_pos)

        # Should flag for stop adjustment
        assert result.action == ReconciliationAction.ADJUST_STOP


class TestEmergencyClose:
    """Tests for emergency close functionality."""

    def test_emergency_close_callback(self):
        """Test emergency close callback is invoked."""
        reconciler = PositionReconciler()

        emergency_callback = MagicMock()
        reconciler.set_emergency_close_callback(emergency_callback)

        exchange_pos = {
            'symbol': 'BTC',
            'size': 1.5,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        reconciler._handle_unknown_position("BTC", exchange_pos)

        emergency_callback.assert_called_once_with("BTC", 1.5)

    def test_emergency_close_disabled(self):
        """Test emergency close can be disabled."""
        config = ReconcilerConfig(emergency_close=False)
        reconciler = PositionReconciler(config=config)

        emergency_callback = MagicMock()
        reconciler.set_emergency_close_callback(emergency_callback)

        exchange_pos = {
            'symbol': 'BTC',
            'size': 1.5,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }

        reconciler._handle_unknown_position("BTC", exchange_pos)

        # Callback should not be invoked when disabled
        emergency_callback.assert_not_called()


class TestReconciliationResults:
    """Tests for reconciliation result tracking."""

    def test_results_stored(self):
        """Test reconciliation results are stored."""
        reconciler = PositionReconciler()

        exchange_pos = {
            'symbol': 'BTC',
            'size': 1.0,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }
        result = reconciler._handle_unknown_position("BTC", exchange_pos)
        # Manually add to results (simulate reconcile method)
        reconciler._results.append(result)

        results = reconciler.get_results()
        assert len(results) == 1
        assert results[0].symbol == "BTC"

    def test_mismatch_count(self):
        """Test mismatch count is tracked."""
        reconciler = PositionReconciler()

        # Add some results
        exchange_pos = {
            'symbol': 'BTC',
            'size': 1.0,
            'side': OrderSide.BUY,
            'entry_price': 50000.0
        }
        result1 = reconciler._handle_unknown_position("BTC", exchange_pos)
        result2 = reconciler._handle_unknown_position("ETH", exchange_pos)
        # Manually add to results (simulate reconcile method)
        reconciler._results.append(result1)
        reconciler._results.append(result2)

        assert reconciler.get_mismatch_count() == 2

    def test_results_limited(self):
        """Test results are limited to prevent memory growth."""
        reconciler = PositionReconciler()

        # Add many results
        for i in range(150):
            exchange_pos = {
                'symbol': f'COIN{i}',
                'size': 1.0,
                'side': OrderSide.BUY,
                'entry_price': 100.0
            }
            result = reconciler._handle_unknown_position(f"COIN{i}", exchange_pos)
            reconciler._results.append(result)

        # Should be trimmed to 100
        assert len(reconciler.get_results()) <= 100
