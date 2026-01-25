"""
Unit tests for HLP16 Circuit Breakers.

Tests circuit breaker tripping, reset, and specific breaker types.
"""

import pytest
import time
from unittest.mock import MagicMock

from runtime.risk import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerConfig,
    RapidLossBreaker,
    AbnormalPriceBreaker,
    StrategyMalfunctionBreaker,
    ResourceExhaustionBreaker,
)


class TestCircuitBreakerBase:
    """Tests for base CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        """Breaker starts in closed (normal) state."""
        breaker = CircuitBreaker("test")
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.is_closed
        assert not breaker.is_open

    def test_trip_changes_state_to_open(self):
        """Tripping breaker changes state to open."""
        breaker = CircuitBreaker("test")
        breaker.trip("Test reason")
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.is_open
        assert not breaker.is_closed

    def test_trip_records_event(self):
        """Tripping records an event."""
        breaker = CircuitBreaker("test")
        breaker.trip("Test reason", {"key": "value"})
        events = breaker.get_events()
        assert len(events) == 1
        assert events[0].reason == "Test reason"
        assert events[0].details == {"key": "value"}

    def test_double_trip_is_noop(self):
        """Tripping an already-open breaker does nothing."""
        breaker = CircuitBreaker("test")
        breaker.trip("First")
        breaker.trip("Second")
        events = breaker.get_events()
        assert len(events) == 1  # Only first trip recorded

    def test_reset_without_manual_flag_fails_when_required(self):
        """Reset requires manual flag when configured."""
        config = CircuitBreakerConfig(manual_reset_required=True)
        breaker = CircuitBreaker("test", config)
        breaker.trip("Test")
        result = breaker.reset(manual=False)
        assert result is False
        assert breaker.is_open

    def test_reset_with_manual_flag_succeeds(self):
        """Reset succeeds with manual flag."""
        config = CircuitBreakerConfig(manual_reset_required=True)
        breaker = CircuitBreaker("test", config)
        breaker.trip("Test")
        result = breaker.reset(manual=True)
        assert result is True
        assert breaker.is_closed

    def test_check_returns_is_closed(self):
        """Check method returns closed state."""
        breaker = CircuitBreaker("test")
        assert breaker.check() is True
        breaker.trip("Test")
        assert breaker.check() is False


class TestRapidLossBreaker:
    """Tests for RapidLossBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create breaker with test config."""
        config = CircuitBreakerConfig(
            single_trade_loss_pct=0.05,
            session_loss_pct=0.10,
            consecutive_losses=3
        )
        return RapidLossBreaker(config)

    def test_single_trade_loss_trips(self, breaker):
        """Large single trade loss trips breaker."""
        breaker.set_capital(10000)
        breaker.record_trade(-600)  # 6% loss
        assert breaker.is_open

    def test_session_loss_trips(self, breaker):
        """Cumulative session loss trips breaker."""
        breaker.set_capital(10000)
        breaker.record_trade(-400)  # 4%
        breaker.record_trade(-400)  # 4% more = 8%
        assert breaker.is_closed
        breaker.record_trade(-300)  # 3% more = 11% total
        assert breaker.is_open

    def test_consecutive_losses_trips(self, breaker):
        """Consecutive losses trip breaker."""
        breaker.set_capital(10000)
        breaker.record_trade(-50)  # Small loss
        breaker.record_trade(-50)
        assert breaker.is_closed
        breaker.record_trade(-50)  # 3rd consecutive
        assert breaker.is_open

    def test_win_resets_consecutive_counter(self, breaker):
        """A win resets the consecutive loss counter."""
        breaker.set_capital(10000)
        breaker.record_trade(-50)
        breaker.record_trade(-50)
        breaker.record_trade(100)  # Win
        breaker.record_trade(-50)
        breaker.record_trade(-50)
        assert breaker.is_closed  # Counter reset, only 2 consecutive

    def test_reset_session_clears_pnl(self, breaker):
        """Reset session clears PnL tracking."""
        breaker.set_capital(10000)
        breaker.record_trade(-400)
        breaker.reset_session()
        breaker.record_trade(-400)
        assert breaker.is_closed  # Only 4% now, not cumulative


class TestAbnormalPriceBreaker:
    """Tests for AbnormalPriceBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create breaker with test config."""
        config = CircuitBreakerConfig(
            price_move_threshold_pct=0.10,  # 10%
            depth_drop_threshold_pct=0.80,  # 80%
            funding_spike_multiplier=5.0
        )
        return AbnormalPriceBreaker(config)

    def test_rapid_price_move_trips(self, breaker):
        """Rapid price movement trips breaker."""
        ts = int(time.time() * 1_000_000_000)
        breaker.record_price("BTC", 50000, ts)
        breaker.record_price("BTC", 56000, ts + 30_000_000_000)  # 12% in 30s
        assert breaker.is_open

    def test_slow_price_move_ok(self, breaker):
        """Gradual price movement is acceptable."""
        ts = int(time.time() * 1_000_000_000)
        breaker.record_price("BTC", 50000, ts)
        breaker.record_price("BTC", 55000, ts + 120_000_000_000)  # 10% in 2 min
        assert breaker.is_closed

    def test_depth_drop_trips(self, breaker):
        """Large depth drop trips breaker."""
        breaker.check_depth("BTC", 1000, 10000)  # 90% drop
        assert breaker.is_open

    def test_funding_spike_trips(self, breaker):
        """Funding rate spike trips breaker."""
        breaker.check_funding("BTC", 0.001)  # Establish baseline
        breaker.check_funding("BTC", 0.006)  # 6x baseline
        assert breaker.is_open


class TestStrategyMalfunctionBreaker:
    """Tests for StrategyMalfunctionBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create breaker with test config."""
        config = CircuitBreakerConfig(
            win_rate_drop_pct=0.30,
            avg_loss_multiplier=2.0,
            sharpe_threshold=0.0
        )
        breaker = StrategyMalfunctionBreaker(config)
        breaker._window_size = 10  # Smaller window for testing
        return breaker

    def test_win_rate_drop_trips(self, breaker):
        """Significant win rate drop trips breaker."""
        breaker.set_baseline("test_strategy", 0.7)  # 70% baseline
        # Record 10 trades with only 3 wins (30% vs 70% baseline = 57% drop)
        for i in range(7):
            breaker.record_trade("test_strategy", -100)
        for i in range(3):
            breaker.record_trade("test_strategy", 100)
        assert breaker.is_open

    def test_avg_loss_vs_win_trips(self, breaker):
        """Large losses vs wins trips breaker."""
        breaker.set_baseline("test_strategy", 0.5)
        # 5 wins of 100, 5 losses of 300 (avg loss 3x avg win)
        for i in range(5):
            breaker.record_trade("test_strategy", 100)
        for i in range(5):
            breaker.record_trade("test_strategy", -300)
        assert breaker.is_open


class TestResourceExhaustionBreaker:
    """Tests for ResourceExhaustionBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create breaker with test config."""
        config = CircuitBreakerConfig(
            cpu_threshold_pct=90.0,
            memory_threshold_pct=85.0,
            latency_multiplier=5.0
        )
        return ResourceExhaustionBreaker(config)

    def test_high_cpu_trips(self, breaker):
        """Sustained high CPU trips breaker."""
        ts = int(time.time() * 1_000_000_000)
        for i in range(5):
            breaker.record_cpu(95, ts + i * 10_000_000_000)
        assert breaker.is_open

    def test_high_memory_trips(self, breaker):
        """High memory usage trips breaker."""
        breaker.check_memory(90)
        assert breaker.is_open

    def test_high_latency_trips(self, breaker):
        """High latency trips breaker."""
        breaker.set_baseline_latency(10)  # 10ms baseline
        breaker.check_latency(60)  # 6x baseline
        assert breaker.is_open

    def test_normal_resources_ok(self, breaker):
        """Normal resource usage is acceptable."""
        breaker.check_memory(50)
        breaker.set_baseline_latency(10)
        breaker.check_latency(30)  # 3x but under 5x
        assert breaker.is_closed
