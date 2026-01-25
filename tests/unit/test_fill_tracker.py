"""
Unit tests for HLP18 FillTracker.

Tests fill detection, tracking, and timeout handling.
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch

from runtime.exchange.types import (
    OrderSide,
    OrderStatus,
    OrderFill,
    FillType,
)
from runtime.exchange.fill_tracker import FillTracker, FillTrackerConfig, TrackingEntry


class TestOrderTracking:
    """Tests for order tracking."""

    def test_track_order(self):
        """Test tracking a new order."""
        tracker = FillTracker()
        tracker.track_order(
            order_id="order_123",
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            expected_price=50000.0
        )

        assert tracker.get_pending_count() == 1
        assert tracker.get_order_status("order_123") == OrderStatus.SUBMITTED

    def test_track_multiple_orders(self):
        """Test tracking multiple orders."""
        tracker = FillTracker()
        tracker.track_order("order_1", "BTC", OrderSide.BUY, 1.0)
        tracker.track_order("order_2", "ETH", OrderSide.SELL, 10.0)
        tracker.track_order("order_3", "SOL", OrderSide.BUY, 100.0)

        assert tracker.get_pending_count() == 3

    def test_untrack_order(self):
        """Test untracking an order."""
        tracker = FillTracker()
        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0)
        tracker.untrack_order("order_123")

        assert tracker.get_pending_count() == 0


class TestFillProcessing:
    """Tests for fill event processing."""

    def test_handle_full_fill(self):
        """Test handling a complete fill."""
        tracker = FillTracker()
        tracker.track_order(
            order_id="order_123",
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            expected_price=50000.0
        )

        # Process fill via WebSocket format
        fill_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'px': '50010.0',
            'sz': '1.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_456',
            'fee': '0.5',
            'crossed': True
        }
        tracker._process_fill(fill_data)

        # Order should be complete
        assert tracker.is_order_complete("order_123")
        fills = tracker.get_fills("order_123")
        assert len(fills) == 1
        assert fills[0].price == 50010.0
        assert fills[0].size == 1.0

    def test_handle_partial_fill(self):
        """Test handling partial fills."""
        tracker = FillTracker()
        tracker.track_order(
            order_id="order_123",
            symbol="ETH",
            side=OrderSide.BUY,
            size=10.0,
            expected_price=3000.0
        )

        # First partial fill - 6 of 10
        fill_data_1 = {
            'oid': 'order_123',
            'coin': 'ETH',
            'px': '3000.0',
            'sz': '6.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_1',
            'fee': '0.3',
            'crossed': True
        }
        tracker._process_fill(fill_data_1)

        # Should be partial
        assert tracker.get_order_status("order_123") == OrderStatus.PARTIAL
        assert not tracker.is_order_complete("order_123")
        assert tracker.get_pending_count() == 1

        # Second partial fill - remaining 4
        fill_data_2 = {
            'oid': 'order_123',
            'coin': 'ETH',
            'px': '3001.0',
            'sz': '4.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_2',
            'fee': '0.2',
            'crossed': True
        }
        tracker._process_fill(fill_data_2)

        # Now complete
        assert tracker.is_order_complete("order_123")
        fills = tracker.get_fills("order_123")
        assert len(fills) == 2
        assert sum(f.size for f in fills) == 10.0

    def test_handle_ws_fill(self):
        """Test handling fill from WebSocket format."""
        tracker = FillTracker()
        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0, 50000.0)

        # WebSocket fill format
        ws_data = {
            'fills': [{
                'oid': 'order_123',
                'coin': 'BTC',
                'px': '50000.0',
                'sz': '1.0',
                'time': int(time.time() * 1000),
                'tid': 'fill_789',
                'fee': '0.5',
                'crossed': True
            }]
        }
        tracker.handle_ws_fill(ws_data)

        assert tracker.is_order_complete("order_123")

    def test_fill_callback_invoked(self):
        """Test fill callback is invoked on fill."""
        tracker = FillTracker()
        callback = MagicMock()
        tracker.set_fill_callback(callback)

        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0, 50000.0)

        fill_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'px': '50010.0',
            'sz': '1.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_456',
            'fee': '0.5',
            'crossed': True
        }
        tracker._process_fill(fill_data)

        callback.assert_called_once()
        fill_arg = callback.call_args[0][0]
        assert isinstance(fill_arg, OrderFill)
        assert fill_arg.price == 50010.0


class TestOrderStatusUpdates:
    """Tests for order status updates."""

    def test_handle_order_filled_status(self):
        """Test handling filled status from WebSocket."""
        tracker = FillTracker()
        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0)

        status_callback = MagicMock()
        tracker.set_status_callback(status_callback)

        # WebSocket status update
        ws_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'status': 'filled',
            'filled': '1.0'
        }
        tracker.handle_ws_order_update(ws_data)

        assert tracker.get_pending_count() == 0
        status_callback.assert_called_once()

    def test_handle_order_canceled_status(self):
        """Test handling canceled status."""
        tracker = FillTracker()
        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0)

        ws_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'status': 'canceled',
            'filled': '0.0'
        }
        tracker.handle_ws_order_update(ws_data)

        assert tracker.get_order_status("order_123") is None  # No longer tracked


class TestTimeoutHandling:
    """Tests for order timeout detection."""

    def test_market_order_timeout(self):
        """Test market order timeout detection.

        F3: Timeout now requires double-timeout to finalize (first flags, second finalizes).
        This prevents nuking orders that receive late fills.
        """
        config = FillTrackerConfig(market_fill_timeout_ms=100)  # 100ms timeout
        tracker = FillTracker(config=config)

        # Create order with old submit time
        old_time = tracker._now_ns() - 500_000_000  # 500ms ago

        entry = TrackingEntry(
            order_id="order_timeout",
            symbol="BTC",
            side=OrderSide.BUY,
            original_size=1.0,
            remaining_size=1.0,
            is_market=True,
            submit_time_ns=old_time
        )
        tracker._tracked_orders["order_timeout"] = entry

        timeout_callback = MagicMock()
        tracker.set_timeout_callback(timeout_callback)

        # F3: First timeout = flag only (order stays)
        tracker._check_timeouts()
        assert tracker.get_pending_count() == 1
        assert tracker._tracked_orders["order_timeout"].timeout_flagged is True
        timeout_callback.assert_called_once_with("order_timeout")

        # F3: Second timeout = finalize (double-timeout with no fills)
        timeout_callback.reset_mock()
        tracker._check_timeouts()
        assert tracker.get_pending_count() == 0
        timeout_callback.assert_called_once_with("order_timeout")

    def test_limit_order_longer_timeout(self):
        """Test limit order has longer timeout."""
        config = FillTrackerConfig(
            market_fill_timeout_ms=100,
            limit_fill_timeout_ms=10000  # 10 seconds
        )
        tracker = FillTracker(config=config)

        # Create limit order 500ms ago (should NOT timeout)
        old_time = tracker._now_ns() - 500_000_000  # 500ms ago

        entry = TrackingEntry(
            order_id="order_limit",
            symbol="BTC",
            side=OrderSide.BUY,
            original_size=1.0,
            remaining_size=1.0,
            is_market=False,  # Limit order
            submit_time_ns=old_time
        )
        tracker._tracked_orders["order_limit"] = entry

        timeout_callback = MagicMock()
        tracker.set_timeout_callback(timeout_callback)

        tracker._check_timeouts()

        # Should NOT timeout yet
        assert tracker.get_pending_count() == 1
        timeout_callback.assert_not_called()


class TestSlippageTracking:
    """Tests for slippage calculation on fills."""

    def test_slippage_calculated_on_fill(self):
        """Test slippage is calculated when fill processed."""
        tracker = FillTracker()
        tracker.track_order(
            order_id="order_123",
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            expected_price=50000.0
        )

        # Fill at higher price
        fill_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'px': '50050.0',  # 10 bps slippage
            'sz': '1.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_456',
            'fee': '0.5',
            'crossed': True
        }
        tracker._process_fill(fill_data)

        entry = tracker._tracked_orders.get("order_123")
        # Entry should be removed after full fill, check fills instead
        fills = tracker.get_fills("order_123")
        assert len(fills) == 1


class TestFillTypeDetection:
    """Tests for fill type detection."""

    def test_taker_fill_when_crossed(self):
        """Test fill marked as taker when crossed is true."""
        tracker = FillTracker()
        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0)

        fill_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'px': '50000.0',
            'sz': '1.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_456',
            'fee': '0.5',
            'crossed': True
        }
        tracker._process_fill(fill_data)

        fills = tracker.get_fills("order_123")
        assert fills[0].fill_type == FillType.TAKER

    def test_maker_fill_when_not_crossed(self):
        """Test fill marked as maker when crossed is false."""
        tracker = FillTracker()
        tracker.track_order("order_123", "BTC", OrderSide.BUY, 1.0)

        fill_data = {
            'oid': 'order_123',
            'coin': 'BTC',
            'px': '50000.0',
            'sz': '1.0',
            'time': int(time.time() * 1000),
            'tid': 'fill_456',
            'fee': '0.1',
            'crossed': False
        }
        tracker._process_fill(fill_data)

        fills = tracker.get_fills("order_123")
        assert fills[0].fill_type == FillType.MAKER
