"""Unit tests for PerformanceTracker."""

import pytest
import math

from runtime.analytics.performance_tracker import PerformanceTracker, PerformanceConfig
from runtime.analytics.types import TradeRecord, TradeOutcome


def create_trade(
    pnl: float,
    fees: float = 0.0,
    strategy: str = "test",
    direction: str = "LONG",
    entry_price: float = 50000.0,
    stop_price: float = None
) -> TradeRecord:
    """Create a test trade record."""
    import time
    now = int(time.time() * 1_000_000_000)

    trade = TradeRecord(
        trade_id=f"trade_{now}",
        symbol="BTC-PERP",
        strategy=strategy,
        direction=direction,
        entry_time_ns=now,
        entry_price=entry_price,
        entry_size=1.0,
        entry_order_id="order_1",
        exit_time_ns=now + 1_000_000_000,  # 1 second later
        exit_price=entry_price + pnl if direction == "LONG" else entry_price - pnl,
        exit_reason="TARGET" if pnl > 0 else "STOP",
        stop_price=stop_price,
        realized_pnl=pnl,
        fees=fees,
        net_pnl=pnl - fees
    )
    return trade


class TestPerformanceTracker:
    """Tests for PerformanceTracker."""

    def test_init_defaults(self):
        """Test tracker initialization."""
        tracker = PerformanceTracker()
        assert tracker._initial_capital == 10000.0
        assert tracker._current_capital == 10000.0
        assert len(tracker._trades) == 0

    def test_init_custom_capital(self):
        """Test tracker with custom initial capital."""
        tracker = PerformanceTracker(initial_capital=50000.0)
        assert tracker._initial_capital == 50000.0
        assert tracker._current_capital == 50000.0

    def test_record_trade_updates_capital(self):
        """Test that recording trades updates capital."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        trade = create_trade(pnl=500.0, fees=10.0)
        tracker.record_trade(trade)

        assert tracker._current_capital == 10490.0  # 10000 + (500 - 10)

    def test_record_trade_ignores_open(self):
        """Test that open trades are ignored."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        open_trade = TradeRecord(
            trade_id="trade_1",
            symbol="BTC-PERP",
            strategy="test",
            direction="LONG",
            entry_time_ns=1000000000,
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
            # No exit details = OPEN
        )
        tracker.record_trade(open_trade)

        assert tracker._current_capital == 10000.0
        assert len(tracker._trades) == 0

    def test_win_rate_calculation(self):
        """Test win rate calculation."""
        tracker = PerformanceTracker()

        # 6 wins, 4 losses = 60% win rate
        for i in range(10):
            pnl = 100.0 if i < 6 else -100.0
            tracker.record_trade(create_trade(pnl=pnl))

        assert tracker.get_win_rate() == 0.6

    def test_win_rate_no_trades(self):
        """Test win rate with no trades."""
        tracker = PerformanceTracker()
        assert tracker.get_win_rate() == 0.0

    def test_rolling_win_rate(self):
        """Test rolling win rate."""
        tracker = PerformanceTracker()

        # 10 losses then 10 wins
        for i in range(20):
            pnl = -100.0 if i < 10 else 100.0
            tracker.record_trade(create_trade(pnl=pnl))

        # Overall: 50% (10/20)
        assert tracker.get_win_rate() == 0.5

        # Rolling 20: 50% (last 20 trades)
        assert tracker.get_rolling_win_rate(20) == 0.5

        # Rolling 10: 100% (last 10 are all wins)
        assert tracker.get_rolling_win_rate(10) == 1.0

    def test_peak_tracking(self):
        """Test peak capital tracking."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        # Win
        tracker.record_trade(create_trade(pnl=500.0))
        assert tracker._peak_capital == 10500.0

        # Loss - peak unchanged
        tracker.record_trade(create_trade(pnl=-300.0))
        assert tracker._peak_capital == 10500.0

        # Bigger win
        tracker.record_trade(create_trade(pnl=1000.0))
        assert tracker._peak_capital == 11200.0

    def test_current_drawdown(self):
        """Test current drawdown calculation."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        # Win to set peak
        tracker.record_trade(create_trade(pnl=2000.0))
        assert tracker._peak_capital == 12000.0

        # Lose 1200 = 10% drawdown from peak
        tracker.record_trade(create_trade(pnl=-1200.0))

        drawdown = tracker._calculate_current_drawdown()
        assert abs(drawdown - 0.1) < 0.001  # ~10%

    def test_max_drawdown(self):
        """Test max drawdown calculation."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        # Series: +2000, -1500, +1000, -2500
        # Capital: 12000, 10500, 11500, 9000
        # DD from peaks: 0, 12.5%, 0, 21.7%
        tracker.record_trade(create_trade(pnl=2000.0))
        tracker.record_trade(create_trade(pnl=-1500.0))
        tracker.record_trade(create_trade(pnl=1000.0))
        tracker.record_trade(create_trade(pnl=-2500.0))

        max_dd = tracker._calculate_max_drawdown()
        # Peak was 12000, dropped to 9000 = 25% drawdown
        assert abs(max_dd - 0.25) < 0.001

    def test_get_snapshot(self):
        """Test performance snapshot."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        # Create mixed results
        for i in range(10):
            pnl = 200.0 if i % 2 == 0 else -100.0
            tracker.record_trade(create_trade(pnl=pnl, fees=5.0))

        snapshot = tracker.get_snapshot()

        assert snapshot.total_trades == 10
        assert snapshot.winning_trades == 5
        assert snapshot.losing_trades == 5
        assert snapshot.win_rate == 0.5
        assert snapshot.total_pnl == 500.0  # 5*200 - 5*100
        assert snapshot.total_fees == 50.0
        assert snapshot.avg_win == pytest.approx((200.0 - 5.0))  # Per winning trade
        assert snapshot.avg_loss == pytest.approx((-100.0 - 5.0))

    def test_profit_factor(self):
        """Test profit factor calculation."""
        tracker = PerformanceTracker()

        # 5 wins of $200, 5 losses of $100
        for i in range(10):
            pnl = 200.0 if i % 2 == 0 else -100.0
            tracker.record_trade(create_trade(pnl=pnl))

        snapshot = tracker.get_snapshot()
        # Profit factor = total_wins / |total_losses| = 1000 / 500 = 2.0
        assert snapshot.profit_factor == 2.0

    def test_expectancy(self):
        """Test expectancy calculation."""
        tracker = PerformanceTracker()

        # 60% win rate, avg win 200, avg loss -100
        for i in range(10):
            pnl = 200.0 if i < 6 else -100.0
            tracker.record_trade(create_trade(pnl=pnl))

        expectancy = tracker.get_expectancy()
        # E = 0.6 * 200 + 0.4 * (-100) = 120 - 40 = 80
        assert abs(expectancy - 80.0) < 0.01

    def test_total_return(self):
        """Test total return percentage."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        tracker.record_trade(create_trade(pnl=2000.0))

        # 20% return
        assert tracker.get_total_return() == 0.2

    def test_strategy_breakdown(self):
        """Test per-strategy tracking."""
        tracker = PerformanceTracker()

        # 3 wins for strat_a, 1 loss for strat_b
        for strategy, pnl in [("strat_a", 100), ("strat_a", 150), ("strat_a", 200), ("strat_b", -100)]:
            tracker.record_trade(create_trade(pnl=pnl, strategy=strategy))

        snapshot = tracker.get_snapshot()

        assert "strat_a" in snapshot.by_strategy
        assert snapshot.by_strategy["strat_a"]["trades"] == 3
        assert snapshot.by_strategy["strat_a"]["wins"] == 3
        assert snapshot.by_strategy["strat_a"]["win_rate"] == 1.0

        assert "strat_b" in snapshot.by_strategy
        assert snapshot.by_strategy["strat_b"]["trades"] == 1
        assert snapshot.by_strategy["strat_b"]["wins"] == 0
        assert snapshot.by_strategy["strat_b"]["win_rate"] == 0.0

    def test_get_strategy_stats(self):
        """Test getting specific strategy stats."""
        tracker = PerformanceTracker()

        tracker.record_trade(create_trade(pnl=100, strategy="momentum"))
        tracker.record_trade(create_trade(pnl=200, strategy="momentum"))

        stats = tracker.get_strategy_stats("momentum")
        assert stats is not None
        assert stats['trades'] == 2
        assert stats['wins'] == 2
        assert stats['pnl'] == 300.0

        assert tracker.get_strategy_stats("nonexistent") is None

    def test_sharpe_ratio_insufficient_data(self):
        """Test Sharpe ratio with insufficient data."""
        tracker = PerformanceTracker()

        # Need at least 5 days of returns
        for i in range(3):
            tracker.record_daily_return(0.01)

        sharpe = tracker._calculate_sharpe(30)
        assert sharpe == 0.0

    def test_sharpe_ratio_calculation(self):
        """Test Sharpe ratio calculation."""
        tracker = PerformanceTracker()

        # Varying returns to get meaningful Sharpe
        for i in range(30):
            ret = 0.01 if i % 2 == 0 else 0.02
            tracker.record_daily_return(ret)

        sharpe = tracker._calculate_sharpe(30)
        # Should be positive with consistent gains
        assert sharpe > 0

        # Test with more variance (some losses)
        tracker._daily_returns.clear()
        for i in range(30):
            ret = 0.02 if i % 3 == 0 else -0.01
            tracker.record_daily_return(ret)

        sharpe2 = tracker._calculate_sharpe(30)
        # Should still compute (might be lower due to losses)
        assert isinstance(sharpe2, float)

    def test_period_pnl_tracking(self):
        """Test daily/weekly/monthly PnL tracking."""
        tracker = PerformanceTracker()

        tracker.record_trade(create_trade(pnl=100))
        tracker.record_trade(create_trade(pnl=200))

        snapshot = tracker.get_snapshot()
        assert snapshot.daily_pnl == 300.0
        assert snapshot.weekly_pnl == 300.0
        assert snapshot.monthly_pnl == 300.0

    def test_reset_daily(self):
        """Test daily reset."""
        tracker = PerformanceTracker(initial_capital=10000.0)

        tracker.record_trade(create_trade(pnl=500))
        tracker.reset_daily()

        # Daily PnL reset, but weekly/monthly preserved
        assert tracker._daily_pnl == 0.0
        # A return was recorded
        assert len(tracker._daily_returns) == 1

    def test_check_thresholds_healthy(self):
        """Test threshold checking with good performance."""
        config = PerformanceConfig(
            win_rate_warning=0.50,
            win_rate_critical=0.40
        )
        tracker = PerformanceTracker(config=config)

        # Good win rate
        for i in range(20):
            pnl = 100 if i < 12 else -100  # 60% win rate
            tracker.record_trade(create_trade(pnl=pnl))

        issues = tracker.check_thresholds()
        assert 'win_rate' not in issues

    def test_check_thresholds_warning(self):
        """Test threshold checking with warning conditions."""
        config = PerformanceConfig(
            win_rate_warning=0.50,
            win_rate_critical=0.40
        )
        tracker = PerformanceTracker(config=config)

        # Poor win rate: 45%
        for i in range(20):
            pnl = 100 if i < 9 else -100
            tracker.record_trade(create_trade(pnl=pnl))

        issues = tracker.check_thresholds()
        assert issues.get('win_rate') == 'WARNING'

    def test_check_thresholds_critical(self):
        """Test threshold checking with critical conditions."""
        config = PerformanceConfig(
            win_rate_warning=0.50,
            win_rate_critical=0.40
        )
        tracker = PerformanceTracker(config=config)

        # Very poor win rate: 35%
        for i in range(20):
            pnl = 100 if i < 7 else -100
            tracker.record_trade(create_trade(pnl=pnl))

        issues = tracker.check_thresholds()
        assert issues.get('win_rate') == 'CRITICAL'

    def test_win_loss_ratio(self):
        """Test win/loss ratio calculation."""
        tracker = PerformanceTracker()

        # Avg win: 200, Avg loss: 100
        for i in range(10):
            pnl = 200 if i < 5 else -100
            tracker.record_trade(create_trade(pnl=pnl))

        snapshot = tracker.get_snapshot()
        # Win/loss ratio = |avg_win / avg_loss| = 200 / 100 = 2.0
        assert snapshot.win_loss_ratio == 2.0

    def test_hold_time_tracking(self):
        """Test average hold time calculation."""
        tracker = PerformanceTracker()

        # All trades have 1 second hold time (from create_trade)
        for _ in range(5):
            tracker.record_trade(create_trade(pnl=100))

        snapshot = tracker.get_snapshot()
        assert snapshot.avg_hold_time_ms == 1000.0  # 1 second in ms

    def test_breakeven_trades(self):
        """Test breakeven trade handling."""
        tracker = PerformanceTracker()

        # Create breakeven trade (0 pnl)
        tracker.record_trade(create_trade(pnl=0))
        tracker.record_trade(create_trade(pnl=100))
        tracker.record_trade(create_trade(pnl=-100))

        snapshot = tracker.get_snapshot()
        assert snapshot.breakeven_trades == 1
        assert snapshot.winning_trades == 1
        assert snapshot.losing_trades == 1

    def test_largest_win_loss(self):
        """Test largest win/loss tracking."""
        tracker = PerformanceTracker()

        tracker.record_trade(create_trade(pnl=100))
        tracker.record_trade(create_trade(pnl=500))
        tracker.record_trade(create_trade(pnl=-200))
        tracker.record_trade(create_trade(pnl=-50))

        snapshot = tracker.get_snapshot()
        assert snapshot.largest_win == 500.0
        assert snapshot.largest_loss == -200.0
