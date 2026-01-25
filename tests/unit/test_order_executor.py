"""
Unit tests for HLP18 OrderExecutor.

Tests order construction, validation, and lifecycle management.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from runtime.exchange.types import (
    OrderType,
    OrderSide,
    OrderStatus,
    OrderRequest,
    OrderResponse,
    OrderFill,
    FillType,
)
from runtime.exchange.order_executor import OrderExecutor, ExecutorConfig


class TestOrderExecutorValidation:
    """Tests for order validation."""

    def test_validate_missing_symbol(self):
        """Test validation fails for missing symbol."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=1.0
        )
        error = executor._validate_request(request)
        assert error == "Symbol required"

    def test_validate_zero_size(self):
        """Test validation fails for zero size."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=0
        )
        error = executor._validate_request(request)
        assert error == "Size must be positive"

    def test_validate_negative_size(self):
        """Test validation fails for negative size."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=-1.0
        )
        error = executor._validate_request(request)
        assert error == "Size must be positive"

    def test_validate_limit_without_price(self):
        """Test validation fails for limit order without price."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=1.0,
            price=None
        )
        error = executor._validate_request(request)
        assert "Price required" in error

    def test_validate_stop_without_stop_price(self):
        """Test validation fails for stop order without stop price."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            size=1.0,
            stop_price=None
        )
        error = executor._validate_request(request)
        assert "Stop price required" in error

    def test_validate_valid_market_order(self):
        """Test validation passes for valid market order."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=1.0
        )
        error = executor._validate_request(request)
        assert error is None

    def test_validate_valid_limit_order(self):
        """Test validation passes for valid limit order."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=1.0,
            price=50000.0
        )
        error = executor._validate_request(request)
        assert error is None

    def test_validate_valid_stop_order(self):
        """Test validation passes for valid stop market order."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            size=1.0,
            stop_price=45000.0
        )
        error = executor._validate_request(request)
        assert error is None


class TestOrderPayloadConstruction:
    """Tests for order payload building."""

    def test_build_market_order_payload(self):
        """Test market order payload structure."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=1.5,  # Use size >= 1 for 4 decimal formatting
            expected_price=50000.0
        )
        payload = executor._build_order_payload(request)

        assert "action" in payload
        assert payload["action"]["type"] == "order"
        assert len(payload["action"]["orders"]) == 1

        order = payload["action"]["orders"][0]
        assert order["a"] == 0  # BTC index
        assert order["b"] is True  # Buy
        # P1: BTC has szDecimals=5, so 5 decimal places
        assert order["s"] == "1.50000"
        assert order["r"] is False  # Not reduce only

    def test_build_limit_order_payload(self):
        """Test limit order payload structure."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="ETH",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            size=10.0,
            price=3000.0
        )
        payload = executor._build_order_payload(request)

        order = payload["action"]["orders"][0]
        assert order["a"] == 1  # ETH index
        assert order["b"] is False  # Sell
        assert order["p"] == "3000.0"
        assert order["t"]["limit"]["tif"] == "Gtc"

    def test_build_post_only_order_payload(self):
        """Test post-only order uses ALO."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.POST_ONLY,
            size=1.0,
            price=49000.0
        )
        payload = executor._build_order_payload(request)

        order = payload["action"]["orders"][0]
        assert order["t"]["limit"]["tif"] == "Alo"

    def test_build_stop_market_order_payload(self):
        """Test stop market order payload structure."""
        executor = OrderExecutor()
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            size=0.5,
            stop_price=45000.0,
            expected_price=50000.0,
            reduce_only=True
        )
        payload = executor._build_order_payload(request)

        order = payload["action"]["orders"][0]
        assert order["r"] is True  # Reduce only
        assert "trigger" in order["t"]
        assert order["t"]["trigger"]["isMarket"] is True
        # P1: 5 significant figures, 45000 has 5 digits, no decimals needed
        assert order["t"]["trigger"]["triggerPx"] == "45000"


class TestOrderLifecycle:
    """Tests for order lifecycle management."""

    def test_pending_order_tracking(self):
        """Test pending orders are tracked."""
        executor = OrderExecutor()

        # Simulate successful submission
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=1.0
        )

        # Manually add to pending (simulating successful submit)
        order_id = "test_order_123"
        executor._pending_orders[order_id] = request
        executor._order_updates[order_id] = MagicMock(status=OrderStatus.SUBMITTED)

        pending = executor.get_pending_orders()
        assert order_id in pending

    def test_fill_handling(self):
        """Test fill handling updates order state."""
        executor = OrderExecutor()

        order_id = "test_order_456"
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=1.0,
            expected_price=50000.0
        )

        # Setup tracking
        from runtime.exchange.types import OrderUpdate
        executor._pending_orders[order_id] = request
        executor._order_submission_times[order_id] = executor._now_ns()
        executor._order_updates[order_id] = OrderUpdate(
            order_id=order_id,
            client_order_id=request.client_order_id,
            symbol="BTC",
            status=OrderStatus.SUBMITTED,
            remaining_size=1.0
        )

        # Process fill
        fill = OrderFill(
            order_id=order_id,
            fill_id="fill_789",
            symbol="BTC",
            side=OrderSide.BUY,
            price=50010.0,
            size=1.0,
            fill_type=FillType.TAKER,
            fee=1.0,
            timestamp_ns=executor._now_ns()
        )

        executor.handle_fill(fill)

        # Check state updated
        update = executor._order_updates[order_id]
        assert update.status == OrderStatus.FILLED
        assert update.filled_size == 1.0
        assert len(update.fills) == 1

    def test_partial_fill_handling(self):
        """Test partial fill keeps order open."""
        executor = OrderExecutor()

        order_id = "test_order_partial"
        request = OrderRequest(
            symbol="ETH",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=10.0,
            price=3000.0
        )

        from runtime.exchange.types import OrderUpdate
        executor._pending_orders[order_id] = request
        executor._order_submission_times[order_id] = executor._now_ns()
        executor._order_updates[order_id] = OrderUpdate(
            order_id=order_id,
            client_order_id=request.client_order_id,
            symbol="ETH",
            status=OrderStatus.SUBMITTED,
            remaining_size=10.0
        )

        # First fill - 6 of 10
        fill = OrderFill(
            order_id=order_id,
            fill_id="fill_1",
            symbol="ETH",
            side=OrderSide.BUY,
            price=3000.0,
            size=6.0,
            fill_type=FillType.MAKER,
            fee=0.5,
            timestamp_ns=executor._now_ns()
        )

        executor.handle_fill(fill)

        update = executor._order_updates[order_id]
        assert update.status == OrderStatus.PARTIAL
        assert update.filled_size == 6.0
        assert update.remaining_size == 4.0

    def test_timeout_detection(self):
        """Test timeout detection for stale orders."""
        config = ExecutorConfig(market_order_timeout_ms=100)  # 100ms timeout
        executor = OrderExecutor(config=config)

        order_id = "test_order_timeout"
        request = OrderRequest(
            symbol="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=1.0
        )

        from runtime.exchange.types import OrderUpdate
        # Submit time 500ms ago (should timeout)
        submit_time = executor._now_ns() - 500_000_000  # 500ms ago
        executor._pending_orders[order_id] = request
        executor._order_submission_times[order_id] = submit_time
        executor._order_updates[order_id] = OrderUpdate(
            order_id=order_id,
            client_order_id=request.client_order_id,
            symbol="BTC",
            status=OrderStatus.SUBMITTED,
            remaining_size=1.0
        )

        timed_out = executor.check_timeouts()
        assert order_id in timed_out


class TestExecutionMetrics:
    """Tests for execution metrics tracking."""

    def test_metrics_add_successful_order(self):
        """Test metrics track successful orders."""
        executor = OrderExecutor()
        executor._metrics.add_order(success=True)

        metrics = executor.get_metrics()
        assert metrics.total_orders == 1
        assert metrics.successful_orders == 1
        assert metrics.rejected_orders == 0

    def test_metrics_add_rejected_order(self):
        """Test metrics track rejected orders."""
        executor = OrderExecutor()
        executor._metrics.add_order(success=False, rejected=True)

        metrics = executor.get_metrics()
        assert metrics.total_orders == 1
        assert metrics.successful_orders == 0
        assert metrics.rejected_orders == 1

    def test_metrics_add_fill(self):
        """Test metrics track fills with slippage."""
        executor = OrderExecutor()
        executor._metrics.add_fill(slippage_bps=5.0, latency_ms=1.5)
        executor._metrics.add_fill(slippage_bps=10.0, latency_ms=2.0)

        metrics = executor.get_metrics()
        assert metrics.total_fills == 2
        assert metrics.avg_slippage_bps == 7.5
        assert metrics.max_slippage_bps == 10.0


class TestAssetIndexMapping:
    """Tests for asset index mapping."""

    def test_btc_index(self):
        """Test BTC maps to index 0."""
        executor = OrderExecutor()
        assert executor._get_asset_index("BTC") == 0

    def test_eth_index(self):
        """Test ETH maps to index 1."""
        executor = OrderExecutor()
        assert executor._get_asset_index("ETH") == 1

    def test_sol_index(self):
        """Test SOL maps to index 2."""
        executor = OrderExecutor()
        assert executor._get_asset_index("SOL") == 2

    def test_unknown_asset_defaults_zero(self):
        """Test unknown asset defaults to 0."""
        executor = OrderExecutor()
        assert executor._get_asset_index("UNKNOWN") == 0


class TestPriceFormatting:
    """Tests for price formatting.

    P1: Updated for 5 significant figure formatting.
    """

    def test_format_large_price(self):
        """Test large price (>= 10000) uses 0 decimals."""
        executor = OrderExecutor()
        # >= 10000: 0 decimals (5 significant figures in whole part)
        assert executor._format_price(50123.456) == "50123"

    def test_format_medium_price(self):
        """Test medium price (100-1000) uses 2 decimals."""
        executor = OrderExecutor()
        # >= 100: 2 decimals
        assert executor._format_price(123.456) == "123.46"

    def test_format_small_price(self):
        """Test small price uses 5 decimals."""
        executor = OrderExecutor()
        # >= 0.1: 5 decimals (5 significant figures)
        assert executor._format_price(0.123456789) == "0.12346"

    def test_format_very_small_price(self):
        """Test very small price (< 0.1) uses 6 decimals."""
        executor = OrderExecutor()
        # < 0.1: 6 decimals
        assert executor._format_price(0.0123456789) == "0.012346"

    def test_format_zero_price(self):
        """Test zero price returns '0'."""
        executor = OrderExecutor()
        assert executor._format_price(0) == "0"
