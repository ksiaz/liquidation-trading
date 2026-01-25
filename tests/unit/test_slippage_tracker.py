"""
Unit tests for HLP18 SlippageTracker.

Tests slippage estimation and tracking.
"""

import pytest
from unittest.mock import MagicMock

from runtime.exchange.types import (
    OrderSide,
    SlippageEstimate,
    OrderFill,
    FillType,
)
from runtime.exchange.slippage_tracker import (
    SlippageTracker,
    SlippageConfig,
    SlippageRecord,
)


class TestSlippageEstimation:
    """Tests for pre-trade slippage estimation."""

    def test_estimate_with_no_orderbook(self):
        """Test estimation returns historical estimate when no orderbook."""
        tracker = SlippageTracker()

        estimate = tracker.estimate_slippage(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            max_slippage_pct=0.5
        )

        assert isinstance(estimate, SlippageEstimate)
        assert estimate.symbol == "BTC"
        assert "historical" in estimate.reason.lower() or estimate.reason == ""

    def test_estimate_with_orderbook(self):
        """Test estimation uses orderbook depth."""
        tracker = SlippageTracker()

        # Add orderbook data
        orderbook = {
            'mid_price': 50000.0,
            'bids': [
                {'price': 49990.0, 'size': 1.0, 'cumulative': 50000.0},
                {'price': 49980.0, 'size': 2.0, 'cumulative': 150000.0},
            ],
            'asks': [
                {'price': 50010.0, 'size': 1.0, 'cumulative': 50010.0},
                {'price': 50020.0, 'size': 2.0, 'cumulative': 150060.0},
            ]
        }
        tracker.update_orderbook("BTC", orderbook)

        estimate = tracker.estimate_slippage(
            symbol="BTC",
            side=OrderSide.BUY,
            size=0.5,
            max_slippage_pct=0.5
        )

        assert estimate.mid_price == 50000.0
        assert estimate.estimated_fill_price > 0
        assert estimate.is_acceptable

    def test_estimate_buy_walks_asks(self):
        """Test buy order walks through asks."""
        tracker = SlippageTracker()

        orderbook = {
            'mid_price': 100.0,
            'bids': [],
            'asks': [
                {'price': 100.5, 'size': 1.0, 'cumulative': 100.5},
                {'price': 101.0, 'size': 1.0, 'cumulative': 201.5},
            ]
        }
        tracker.update_orderbook("TEST", orderbook)

        # Buy 2 units - should fill at average of 100.5 and 101.0
        estimate = tracker.estimate_slippage(
            symbol="TEST",
            side=OrderSide.BUY,
            size=2.0,
            max_slippage_pct=2.0
        )

        expected_avg = (100.5 + 101.0) / 2
        assert abs(estimate.estimated_fill_price - expected_avg) < 0.1
        assert estimate.depth_levels_consumed == 2

    def test_estimate_sell_walks_bids(self):
        """Test sell order walks through bids."""
        tracker = SlippageTracker()

        orderbook = {
            'mid_price': 100.0,
            'bids': [
                {'price': 99.5, 'size': 1.0, 'cumulative': 99.5},
                {'price': 99.0, 'size': 1.0, 'cumulative': 198.5},
            ],
            'asks': []
        }
        tracker.update_orderbook("TEST", orderbook)

        # Sell 2 units - should fill at average of 99.5 and 99.0
        estimate = tracker.estimate_slippage(
            symbol="TEST",
            side=OrderSide.SELL,
            size=2.0,
            max_slippage_pct=2.0
        )

        expected_avg = (99.5 + 99.0) / 2
        assert abs(estimate.estimated_fill_price - expected_avg) < 0.1

    def test_estimate_unacceptable_slippage(self):
        """Test estimation flags unacceptable slippage."""
        tracker = SlippageTracker()

        # Thin orderbook with wide spread
        orderbook = {
            'mid_price': 100.0,
            'bids': [],
            'asks': [
                {'price': 102.0, 'size': 0.5, 'cumulative': 51.0},  # 2% away
                {'price': 105.0, 'size': 1.0, 'cumulative': 156.0},  # 5% away
            ]
        }
        tracker.update_orderbook("TEST", orderbook)

        estimate = tracker.estimate_slippage(
            symbol="TEST",
            side=OrderSide.BUY,
            size=1.0,
            max_slippage_pct=0.5  # Only allow 0.5%
        )

        assert not estimate.is_acceptable
        assert "exceeds" in estimate.reason.lower()


class TestSlippageRecording:
    """Tests for post-trade slippage recording."""

    def test_record_fill_positive_slippage(self):
        """Test recording fill with positive slippage (unfavorable buy)."""
        tracker = SlippageTracker()

        record = tracker.record_fill(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            expected_price=50000.0,
            fill_price=50050.0  # 10 bps worse
        )

        assert record.slippage_pct == pytest.approx(0.1, rel=0.01)  # 0.1%
        assert record.slippage_bps == pytest.approx(10.0, rel=0.01)
        assert record.slippage_cost == pytest.approx(50.0, rel=0.01)

    def test_record_fill_negative_slippage(self):
        """Test recording fill with negative slippage (favorable)."""
        tracker = SlippageTracker()

        record = tracker.record_fill(
            symbol="BTC",
            side=OrderSide.BUY,
            size=1.0,
            expected_price=50000.0,
            fill_price=49950.0  # 10 bps better
        )

        assert record.slippage_pct == pytest.approx(-0.1, rel=0.01)  # -0.1%
        assert record.slippage_bps == pytest.approx(-10.0, rel=0.01)

    def test_record_sell_slippage(self):
        """Test slippage calculation for sell orders."""
        tracker = SlippageTracker()

        # Sell at worse price = positive slippage
        record = tracker.record_fill(
            symbol="ETH",
            side=OrderSide.SELL,
            size=10.0,
            expected_price=3000.0,
            fill_price=2997.0  # 10 bps worse for sell
        )

        assert record.slippage_pct == pytest.approx(0.1, rel=0.01)  # 0.1%

    def test_record_from_order_fill(self):
        """Test recording from OrderFill object."""
        tracker = SlippageTracker()

        fill = OrderFill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTC",
            side=OrderSide.BUY,
            price=50100.0,
            size=0.5,
            fill_type=FillType.TAKER,
            fee=1.0,
            timestamp_ns=0
        )

        record = tracker.record_from_order_fill(fill, expected_price=50000.0)

        assert record.symbol == "BTC"
        assert record.fill_price == 50100.0
        assert record.size == 0.5


class TestStatistics:
    """Tests for slippage statistics."""

    def test_statistics_empty(self):
        """Test statistics with no fills."""
        tracker = SlippageTracker()

        stats = tracker.get_statistics()
        assert stats['total_fills'] == 0
        assert stats['avg_slippage_bps'] == 0

    def test_statistics_calculated(self):
        """Test statistics are calculated correctly."""
        tracker = SlippageTracker()

        # Record several fills
        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50025.0)  # 5 bps
        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)  # 10 bps
        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50075.0)  # 15 bps

        stats = tracker.get_statistics("BTC")
        assert stats['total_fills'] == 3
        assert stats['avg_slippage_bps'] == pytest.approx(10.0, rel=0.1)
        assert stats['max_slippage_bps'] == pytest.approx(15.0, rel=0.1)
        assert stats['min_slippage_bps'] == pytest.approx(5.0, rel=0.1)

    def test_statistics_by_side(self):
        """Test statistics broken down by side."""
        tracker = SlippageTracker()

        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)  # 10 bps
        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)  # 10 bps
        tracker.record_fill("BTC", OrderSide.SELL, 1.0, 50000.0, 49975.0)  # 5 bps

        stats = tracker.get_statistics("BTC")
        assert stats['by_side']['buy']['count'] == 2
        assert stats['by_side']['sell']['count'] == 1

    def test_statistics_symbol_filter(self):
        """Test statistics can be filtered by symbol."""
        tracker = SlippageTracker()

        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)
        tracker.record_fill("ETH", OrderSide.BUY, 10.0, 3000.0, 3003.0)

        btc_stats = tracker.get_statistics("BTC")
        assert btc_stats['total_fills'] == 1

        all_stats = tracker.get_statistics()
        assert all_stats['total_fills'] == 2


class TestSlippageThresholds:
    """Tests for slippage threshold checking."""

    def test_check_acceptable_normal(self):
        """Test check with normal thresholds."""
        config = SlippageConfig(default_max_slippage_pct=0.5)
        tracker = SlippageTracker(config=config)

        # Add orderbook with minimal slippage
        orderbook = {
            'mid_price': 100.0,
            'bids': [],
            'asks': [
                {'price': 100.1, 'size': 10.0, 'cumulative': 1001.0},
            ]
        }
        tracker.update_orderbook("TEST", orderbook)

        is_acceptable, estimate = tracker.check_acceptable(
            symbol="TEST",
            side=OrderSide.BUY,
            size=1.0
        )

        assert is_acceptable

    def test_check_acceptable_cascade_mode(self):
        """Test check with cascade mode (higher tolerance)."""
        config = SlippageConfig(
            default_max_slippage_pct=0.2,
            cascade_max_slippage_pct=1.0
        )
        tracker = SlippageTracker(config=config)

        # Add orderbook with moderate slippage
        orderbook = {
            'mid_price': 100.0,
            'bids': [],
            'asks': [
                {'price': 100.5, 'size': 10.0, 'cumulative': 1005.0},  # 0.5% slippage
            ]
        }
        tracker.update_orderbook("TEST", orderbook)

        # Normal mode would reject
        is_acceptable_normal, _ = tracker.check_acceptable(
            symbol="TEST",
            side=OrderSide.BUY,
            size=1.0,
            is_cascade=False
        )

        # Cascade mode accepts higher slippage
        is_acceptable_cascade, _ = tracker.check_acceptable(
            symbol="TEST",
            side=OrderSide.BUY,
            size=1.0,
            is_cascade=True
        )

        # With 0.5% slippage and 0.2% normal threshold, normal should reject
        # With 1.0% cascade threshold, cascade should accept
        assert not is_acceptable_normal
        assert is_acceptable_cascade


class TestHistoryManagement:
    """Tests for slippage history management."""

    def test_get_recent_slippage(self):
        """Test getting recent slippage records."""
        tracker = SlippageTracker()

        for i in range(5):
            tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50000.0 + i * 10)

        recent = tracker.get_recent_slippage("BTC", count=3)
        assert len(recent) == 3

    def test_history_limited(self):
        """Test history is limited to configured window."""
        config = SlippageConfig(history_window=10)
        tracker = SlippageTracker(config=config)

        # Add more than window size
        for i in range(20):
            tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50000.0 + i)

        recent = tracker.get_recent_slippage("BTC", count=100)
        assert len(recent) <= 10

    def test_reset_statistics(self):
        """Test resetting statistics."""
        tracker = SlippageTracker()

        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)
        assert tracker.get_total_fill_count() == 1

        tracker.reset_statistics()
        assert tracker.get_total_fill_count() == 0
        assert tracker.get_total_slippage_cost() == 0.0


class TestTotalTracking:
    """Tests for total cost tracking."""

    def test_total_slippage_cost(self):
        """Test total slippage cost accumulation."""
        tracker = SlippageTracker()

        # Fill 1: $50 slippage cost
        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)

        # Fill 2: $30 slippage cost
        tracker.record_fill("ETH", OrderSide.BUY, 10.0, 3000.0, 3003.0)

        total = tracker.get_total_slippage_cost()
        assert total == pytest.approx(80.0, rel=0.01)

    def test_total_fill_count(self):
        """Test total fill count."""
        tracker = SlippageTracker()

        tracker.record_fill("BTC", OrderSide.BUY, 1.0, 50000.0, 50050.0)
        tracker.record_fill("BTC", OrderSide.SELL, 1.0, 50000.0, 49950.0)
        tracker.record_fill("ETH", OrderSide.BUY, 10.0, 3000.0, 3003.0)

        assert tracker.get_total_fill_count() == 3
