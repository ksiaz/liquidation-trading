"""
Unit tests for HLP17 Capital Management.

Tests position sizing, risk limits, drawdown tracking, and capital manager.
"""

import pytest

from runtime.risk import (
    # Position Sizer
    PositionSizer,
    SizingConfig,
    SizingMethod,
    Regime,
    # Risk Limits
    RiskLimitsChecker,
    RiskLimitsConfig,
    Position,
    LimitViolation,
    # Drawdown
    DrawdownTracker,
    DrawdownConfig,
    DrawdownState,
    # Capital Manager
    CapitalManager,
    CapitalManagerConfig,
    TradeRequest,
    TradeDecision,
)


class TestPositionSizer:
    """Tests for PositionSizer."""

    @pytest.fixture
    def sizer(self):
        """Create sizer with test config."""
        config = SizingConfig(
            risk_per_trade_default=0.01,
            risk_per_trade_max=0.02,
            risk_per_trade_min=0.005,
        )
        return PositionSizer(config)

    def test_fixed_fractional_sizing(self, sizer):
        """Basic fixed fractional sizing calculation."""
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500
        )
        # Risk = 1% of 10000 = 100
        # Stop distance = 500
        # Size = 100 / 500 = 0.2 BTC
        assert abs(result.position_size - 0.2) < 0.001
        assert result.method == SizingMethod.FIXED_FRACTIONAL

    def test_verify_risk_amount(self, sizer):
        """Position size results in correct risk amount."""
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500
        )
        # If stop hits: 0.2 * 500 = 100
        assert abs(result.risk_amount - 100) < 1

    def test_volatility_adjustment_high_vol(self, sizer):
        """High volatility reduces position size."""
        sizer.set_baseline_volatility("BTC", 1000)  # baseline ATR
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500,
            current_volatility=2000,  # 2x baseline
            symbol="BTC"
        )
        # Volatility scalar = 1000/2000 = 0.5
        # Size = 0.2 * 0.5 = 0.1
        assert abs(result.position_size - 0.1) < 0.001

    def test_volatility_adjustment_low_vol(self, sizer):
        """Low volatility increases position size (up to limit)."""
        sizer.set_baseline_volatility("BTC", 1000)
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500,
            current_volatility=500,  # 0.5x baseline
            symbol="BTC"
        )
        # Volatility scalar = 1000/500 = 2.0 (max)
        # Size = 0.2 * 2.0 = 0.4
        assert abs(result.position_size - 0.4) < 0.001

    def test_regime_adjustment(self, sizer):
        """Regime affects position size."""
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500,
            regime=Regime.EXPANSION
        )
        # EXPANSION regime scalar = 0.75
        # Size = 0.2 * 0.75 = 0.15
        assert abs(result.position_size - 0.15) < 0.001

    def test_consecutive_losses_reduce_size(self, sizer):
        """Consecutive losses reduce position size."""
        sizer.record_trade_result(is_win=False)
        sizer.record_trade_result(is_win=False)
        # After 2 losses: risk = 0.75%
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500
        )
        # Size = (10000 * 0.0075) / 500 = 0.15
        assert abs(result.position_size - 0.15) < 0.001

    def test_consecutive_wins_increase_size(self, sizer):
        """Consecutive wins increase position size."""
        for _ in range(3):
            sizer.record_trade_result(is_win=True)
        # After 3 wins: risk = 1.25%
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=49500
        )
        # Size = (10000 * 0.0125) / 500 = 0.25
        assert abs(result.position_size - 0.25) < 0.001

    def test_invalid_capital_returns_zero(self, sizer):
        """Zero capital returns zero size."""
        result = sizer.calculate_size(
            capital=0,
            entry_price=50000,
            stop_price=49500
        )
        assert result.position_size == 0

    def test_invalid_stop_returns_zero(self, sizer):
        """Same entry and stop returns zero size."""
        result = sizer.calculate_size(
            capital=10000,
            entry_price=50000,
            stop_price=50000  # No stop distance
        )
        assert result.position_size == 0


class TestRiskLimitsChecker:
    """Tests for RiskLimitsChecker."""

    @pytest.fixture
    def checker(self):
        """Create checker with test config."""
        config = RiskLimitsConfig(
            max_position_size_pct=0.05,
            max_aggregate_exposure_pct=0.10,
            max_correlated_exposure_pct=0.07,
            max_concurrent_positions=2
        )
        return RiskLimitsChecker(config)

    def test_position_within_limits(self, checker):
        """Position within limits is approved."""
        result = checker.check_new_position(
            symbol="BTC",
            size=0.01,  # $500 at $50000
            entry_price=50000,
            stop_price=49500,
            capital=10000
        )
        assert result.allowed

    def test_position_exceeds_size_limit(self, checker):
        """Position exceeding size limit is rejected."""
        result = checker.check_new_position(
            symbol="BTC",
            size=0.2,  # $10000 at $50000 = 100% of capital
            entry_price=50000,
            stop_price=49500,
            capital=10000
        )
        assert not result.allowed
        assert LimitViolation.POSITION_SIZE_EXCEEDED in result.violations

    def test_aggregate_exposure_limit(self, checker):
        """Aggregate exposure limit is enforced."""
        # Add existing position
        checker.add_position(Position(
            symbol="ETH",
            size=0.5,  # $500 at $1000
            entry_price=1000,
            current_price=1000,
            stop_price=950,
            side="long"
        ))
        # Try to add more
        result = checker.check_new_position(
            symbol="BTC",
            size=0.012,  # $600 at $50000
            entry_price=50000,
            stop_price=49500,
            capital=10000
        )
        # Total would be $1100 = 11% > 10%
        assert not result.allowed
        assert LimitViolation.AGGREGATE_EXPOSURE_EXCEEDED in result.violations

    def test_max_positions_limit(self, checker):
        """Max concurrent positions limit is enforced."""
        checker.add_position(Position(
            symbol="BTC", size=0.001, entry_price=50000,
            current_price=50000, stop_price=49500, side="long"
        ))
        checker.add_position(Position(
            symbol="ETH", size=0.01, entry_price=1000,
            current_price=1000, stop_price=950, side="long"
        ))
        # Try to add third
        result = checker.check_new_position(
            symbol="SOL",
            size=0.1,
            entry_price=100,
            stop_price=95,
            capital=10000
        )
        assert not result.allowed
        assert LimitViolation.MAX_POSITIONS_EXCEEDED in result.violations

    def test_correlated_exposure_limit(self, checker):
        """Correlated exposure limit is enforced."""
        checker.set_correlation("BTC", "ETH", 0.85)
        checker.add_position(Position(
            symbol="BTC", size=0.01, entry_price=50000,
            current_price=50000, stop_price=49500, side="long"
        ))  # $500
        # Try to add correlated asset
        result = checker.check_new_position(
            symbol="ETH",
            size=0.5,  # $500 at $1000
            entry_price=1000,
            stop_price=950,
            capital=10000
        )
        # Correlated exposure = $1000 = 10% > 7%
        assert not result.allowed
        assert LimitViolation.CORRELATED_EXPOSURE_EXCEEDED in result.violations

    def test_adjusted_size_provided(self, checker):
        """Adjusted size is calculated when limits exceeded."""
        result = checker.check_new_position(
            symbol="BTC",
            size=0.2,  # Too large
            entry_price=50000,
            stop_price=49500,
            capital=10000
        )
        assert result.adjusted_size is not None
        assert result.adjusted_size < 0.2

    def test_exposure_summary(self, checker):
        """Exposure summary is calculated correctly."""
        checker.add_position(Position(
            symbol="BTC", size=0.01, entry_price=50000,
            current_price=50000, stop_price=49500, side="long"
        ))
        summary = checker.get_exposure_summary(10000)
        assert summary['position_count'] == 1
        assert abs(summary['total_exposure_usd'] - 500) < 1


class TestDrawdownTracker:
    """Tests for DrawdownTracker."""

    @pytest.fixture
    def tracker(self):
        """Create tracker with test config."""
        config = DrawdownConfig(
            daily_loss_limit_pct=0.03,
            weekly_loss_limit_pct=0.07,
            consecutive_loss_reduced=3,
            consecutive_loss_halt=5,
            max_drawdown_pct=0.25
        )
        return DrawdownTracker(10000, config)

    def test_initial_state_is_normal(self, tracker):
        """Tracker starts in normal state."""
        assert tracker.state == DrawdownState.NORMAL
        assert tracker.is_trading_allowed()

    def test_daily_loss_limit_triggers_cooldown(self, tracker):
        """Hitting daily loss limit triggers cooldown."""
        tracker.record_trade(-350)  # 3.5% loss
        assert tracker.state == DrawdownState.DAILY_COOLDOWN
        assert not tracker.is_trading_allowed()

    def test_weekly_loss_limit_triggers_cooldown(self, tracker):
        """Hitting weekly loss limit triggers cooldown."""
        tracker.record_trade(-250)  # 2.5%
        tracker.reset_daily()
        tracker.record_trade(-250)  # 2.5% more
        tracker.reset_daily()
        tracker.record_trade(-250)  # 7.5% weekly total
        assert tracker.state == DrawdownState.WEEKLY_COOLDOWN

    def test_consecutive_losses_triggers_reduced_risk(self, tracker):
        """Consecutive losses trigger reduced risk mode."""
        for _ in range(3):
            tracker.record_trade(-50)
        assert tracker.state == DrawdownState.REDUCED_RISK
        assert tracker.get_size_multiplier() == 0.5

    def test_recovery_from_reduced_risk(self, tracker):
        """Wins allow recovery from reduced risk."""
        for _ in range(3):
            tracker.record_trade(-50)
        assert tracker.state == DrawdownState.REDUCED_RISK
        # 2 wins to recover
        tracker.record_trade(100)
        tracker.record_trade(100)
        assert tracker.state == DrawdownState.NORMAL

    def test_max_drawdown_triggers_state(self, tracker):
        """Large drawdown triggers max drawdown state."""
        tracker.record_trade(-2600)  # 26% loss
        assert tracker.state == DrawdownState.MAXIMUM_DRAWDOWN
        assert tracker.get_size_multiplier() == 0.25

    def test_reset_daily_clears_cooldown(self, tracker):
        """Resetting daily clears daily cooldown."""
        tracker.record_trade(-350)
        assert tracker.state == DrawdownState.DAILY_COOLDOWN
        tracker.reset_daily()
        assert tracker.state == DrawdownState.NORMAL

    def test_get_summary(self, tracker):
        """Summary provides comprehensive info."""
        tracker.record_trade(100)
        summary = tracker.get_summary()
        assert summary['state'] == 'NORMAL'
        assert summary['current_capital'] == 10100
        assert summary['trading_allowed'] is True


class TestCapitalManager:
    """Tests for CapitalManager integration."""

    @pytest.fixture
    def manager(self):
        """Create manager with test config."""
        return CapitalManager(initial_capital=10000)

    def test_validate_trade_approved(self, manager):
        """Valid trade is approved."""
        request = TradeRequest(
            symbol="BTC",
            entry_price=50000,
            stop_price=49500
        )
        result = manager.validate_trade(request)
        assert result.decision == TradeDecision.APPROVED
        assert result.approved_size > 0

    def test_validate_trade_rejected_disabled_regime(self, manager):
        """Trade rejected in disabled regime."""
        manager.set_regime(Regime.DISABLED)
        request = TradeRequest(
            symbol="BTC",
            entry_price=50000,
            stop_price=49500
        )
        result = manager.validate_trade(request)
        assert result.decision == TradeDecision.REJECTED_RISK_LIMIT

    def test_validate_trade_rejected_drawdown(self, manager):
        """Trade rejected during drawdown cooldown."""
        # Trigger daily limit
        manager.record_trade_result(-400, "BTC")
        request = TradeRequest(
            symbol="ETH",
            entry_price=1000,
            stop_price=950
        )
        result = manager.validate_trade(request)
        assert result.decision == TradeDecision.REJECTED_DRAWDOWN

    def test_validate_trade_invalid_params(self, manager):
        """Trade rejected with invalid parameters."""
        request = TradeRequest(
            symbol="BTC",
            entry_price=0,  # Invalid
            stop_price=49500
        )
        result = manager.validate_trade(request)
        assert result.decision == TradeDecision.REJECTED_INVALID_PARAMS

    def test_record_trade_updates_capital(self, manager):
        """Recording trade updates capital."""
        initial = manager.capital
        manager.record_trade_result(100, "BTC")
        assert manager.capital == initial + 100

    def test_get_status_comprehensive(self, manager):
        """Status provides comprehensive info."""
        status = manager.get_status()
        assert 'capital' in status
        assert 'regime' in status
        assert 'drawdown' in status
        assert 'exposure' in status
        assert 'sizing' in status

    def test_size_multiplier_combines_factors(self, manager):
        """Size multiplier combines regime and drawdown."""
        manager.set_regime(Regime.EXPANSION)  # 0.75x
        assert manager.get_size_multiplier() == 0.75
