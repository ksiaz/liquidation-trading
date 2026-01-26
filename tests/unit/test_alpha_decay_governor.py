"""Unit tests for alpha_decay_governor.py."""

import pytest
import time

from runtime.risk.alpha_decay_governor import (
    DecaySeverity,
    GovernorAction,
    TradeOutcome,
    StrategyMetrics,
    DecaySnapshot,
    DecayThresholds,
    StrategyPerformanceTracker,
    DecaySeverityClassifier,
    GovernorDecision,
    AlphaDecayGovernor,
)


class TestDecaySeverity:
    """Tests for DecaySeverity enum."""

    def test_all_severities_defined(self):
        """All severity levels should be defined."""
        assert DecaySeverity.NONE.value == "NONE"
        assert DecaySeverity.LOW.value == "LOW"
        assert DecaySeverity.MEDIUM.value == "MEDIUM"
        assert DecaySeverity.HIGH.value == "HIGH"
        assert DecaySeverity.CRITICAL.value == "CRITICAL"


class TestGovernorAction:
    """Tests for GovernorAction enum."""

    def test_all_actions_defined(self):
        """All governor actions should be defined."""
        assert GovernorAction.NONE.value == "NONE"
        assert GovernorAction.REDUCE_SIZE.value == "REDUCE_SIZE"
        assert GovernorAction.DISABLE_STRATEGY.value == "DISABLE_STRATEGY"
        assert GovernorAction.HALT_ENTRIES.value == "HALT_ENTRIES"
        assert GovernorAction.HALT_ALL.value == "HALT_ALL"


class TestStrategyMetrics:
    """Tests for StrategyMetrics dataclass."""

    def test_win_rate_calculation(self):
        """Should calculate win rate correctly."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 100
        metrics.window_wins = 60
        metrics.window_losses = 40
        assert metrics.win_rate == 0.6

    def test_win_rate_zero_trades(self):
        """Should return 0 for no trades."""
        metrics = StrategyMetrics(strategy_id="test")
        assert metrics.win_rate == 0.0

    def test_profit_factor_calculation(self):
        """Should calculate profit factor correctly."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.gross_profit = 1000.0
        metrics.gross_loss = 500.0
        assert metrics.profit_factor == 2.0

    def test_profit_factor_no_loss(self):
        """Should return inf for no losses."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.gross_profit = 1000.0
        metrics.gross_loss = 0.0
        assert metrics.profit_factor == float('inf')

    def test_profit_factor_no_profit_no_loss(self):
        """Should return 0 for no profit and no loss."""
        metrics = StrategyMetrics(strategy_id="test")
        assert metrics.profit_factor == 0.0

    def test_expectancy_calculation(self):
        """Should calculate expectancy correctly."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 10
        metrics.total_pnl_bps = 100.0
        assert metrics.expectancy == 10.0

    def test_avg_slippage_calculation(self):
        """Should calculate average slippage correctly."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 10
        metrics.total_slippage_bps = 50.0
        assert metrics.avg_slippage_bps == 5.0


class TestTradeOutcome:
    """Tests for TradeOutcome dataclass."""

    def test_outcome_is_frozen(self):
        """TradeOutcome should be immutable."""
        outcome = TradeOutcome(
            ts_ns=1000,
            strategy_id="test",
            symbol="BTC",
            side="buy",
            entry_price=50000.0,
            exit_price=51000.0,
            size=1.0,
            pnl=1000.0,
            pnl_bps=200.0,
            slippage_bps=5.0,
            hold_time_ns=60_000_000_000,
        )
        with pytest.raises(AttributeError):
            outcome.pnl = 500.0


class TestStrategyPerformanceTracker:
    """Tests for StrategyPerformanceTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create fresh tracker for each test."""
        return StrategyPerformanceTracker(window_size=20, baseline_window_size=50)

    def _create_outcome(
        self,
        strategy_id: str,
        pnl: float,
        pnl_bps: float,
        slippage_bps: float = 5.0,
        ts_ns: int = None,
    ) -> TradeOutcome:
        """Helper to create trade outcome."""
        return TradeOutcome(
            ts_ns=ts_ns or int(time.time() * 1_000_000_000),
            strategy_id=strategy_id,
            symbol="BTC",
            side="buy",
            entry_price=50000.0,
            exit_price=50000.0 + pnl,
            size=1.0,
            pnl=pnl,
            pnl_bps=pnl_bps,
            slippage_bps=slippage_bps,
            hold_time_ns=60_000_000_000,
        )

    def test_no_data_returns_none(self, tracker):
        """Should return None with no data."""
        metrics = tracker.get_metrics("nonexistent")
        assert metrics is None

    def test_records_trades(self, tracker):
        """Should record trades correctly."""
        outcome = self._create_outcome("strat1", 100.0, 20.0)
        tracker.record_trade(outcome)

        metrics = tracker.get_metrics("strat1")
        assert metrics is not None
        assert metrics.window_trades == 1

    def test_computes_win_rate(self, tracker):
        """Should compute win rate from trades."""
        # 6 wins, 4 losses = 60% win rate
        for i in range(6):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))
        for i in range(4):
            tracker.record_trade(self._create_outcome("strat1", -50.0, -10.0))

        metrics = tracker.get_metrics("strat1")
        assert metrics.win_rate == 0.6
        assert metrics.window_wins == 6
        assert metrics.window_losses == 4

    def test_computes_pnl(self, tracker):
        """Should compute total PnL correctly."""
        tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))
        tracker.record_trade(self._create_outcome("strat1", -30.0, -6.0))

        metrics = tracker.get_metrics("strat1")
        assert metrics.total_pnl == 70.0
        assert metrics.total_pnl_bps == 14.0

    def test_tracks_multiple_strategies(self, tracker):
        """Should track strategies independently."""
        tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))
        tracker.record_trade(self._create_outcome("strat2", 50.0, 10.0))

        assert tracker.get_trade_count("strat1") == 1
        assert tracker.get_trade_count("strat2") == 1

        ids = tracker.get_strategy_ids()
        assert "strat1" in ids
        assert "strat2" in ids

    def test_window_size_limits(self, tracker):
        """Recent window should be limited."""
        # Add more than window_size trades
        for i in range(30):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))

        # Recent metrics should use last 20 trades
        metrics = tracker.get_metrics("strat1", "recent")
        assert metrics.window_trades == 20


class TestDecaySeverityClassifier:
    """Tests for DecaySeverityClassifier class."""

    @pytest.fixture
    def classifier(self):
        """Create classifier."""
        return DecaySeverityClassifier()

    def test_insufficient_samples(self, classifier):
        """Should return NONE with insufficient samples."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 5  # Below threshold

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.NONE
        assert reason == "insufficient_samples"

    def test_acceptable_performance(self, classifier):
        """Should return NONE for acceptable performance."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 50
        metrics.window_wins = 30
        metrics.window_losses = 20
        metrics.gross_profit = 1000.0
        metrics.gross_loss = 500.0
        metrics.total_pnl_bps = 500.0  # 10 bps per trade - above min threshold
        metrics.total_slippage_bps = 100.0  # 2 bps avg - acceptable

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.NONE
        assert reason == "performance_acceptable"

    def test_critical_low_win_rate(self, classifier):
        """Should return CRITICAL for very low win rate."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 50
        metrics.window_wins = 10  # 20% win rate
        metrics.window_losses = 40
        metrics.gross_profit = 100.0
        metrics.gross_loss = 400.0
        metrics.total_pnl_bps = 0.0

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.CRITICAL
        assert "win_rate" in reason

    def test_critical_negative_expectancy(self, classifier):
        """Should return CRITICAL for negative expectancy."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 50
        metrics.window_wins = 20
        metrics.window_losses = 30
        metrics.gross_profit = 200.0
        metrics.gross_loss = 500.0
        metrics.total_pnl_bps = -100.0  # Negative

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.CRITICAL
        assert "expectancy" in reason

    def test_critical_profit_factor_below_one(self, classifier):
        """Should return CRITICAL for profit factor < 1."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 50
        metrics.window_wins = 25
        metrics.window_losses = 25
        metrics.gross_profit = 400.0
        metrics.gross_loss = 600.0  # PF = 0.67
        metrics.total_pnl_bps = 10.0

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.CRITICAL
        assert "profit_factor" in reason

    def test_critical_high_slippage(self, classifier):
        """Should return CRITICAL for very high slippage."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 50
        metrics.window_wins = 30
        metrics.window_losses = 20
        metrics.gross_profit = 1000.0
        metrics.gross_loss = 500.0
        metrics.total_pnl_bps = 100.0
        metrics.total_slippage_bps = 2000.0  # 40 bps avg

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.CRITICAL
        assert "slippage" in reason

    def test_low_severity_marginal_performance(self, classifier):
        """Should return LOW for marginal performance."""
        metrics = StrategyMetrics(strategy_id="test")
        metrics.window_trades = 50
        metrics.window_wins = 19  # 38% win rate < 40% threshold
        metrics.window_losses = 31
        metrics.gross_profit = 800.0
        metrics.gross_loss = 600.0  # PF = 1.33
        metrics.total_pnl_bps = 100.0
        metrics.total_slippage_bps = 100.0

        severity, reason = classifier.classify(metrics)
        assert severity == DecaySeverity.LOW
        assert "win_rate" in reason

    def test_decay_detection_with_baseline(self, classifier):
        """Should detect decay compared to baseline."""
        # Current: worse than baseline
        current = StrategyMetrics(strategy_id="test")
        current.window_trades = 50
        current.window_wins = 25  # 50%
        current.window_losses = 25
        current.gross_profit = 500.0
        current.gross_loss = 300.0
        current.total_pnl_bps = 200.0
        current.total_slippage_bps = 100.0

        # Baseline: much better
        baseline = StrategyMetrics(strategy_id="test")
        baseline.window_trades = 200
        baseline.window_wins = 140  # 70%
        baseline.window_losses = 60
        baseline.gross_profit = 2000.0
        baseline.gross_loss = 500.0
        baseline.total_pnl_bps = 1000.0
        baseline.total_slippage_bps = 200.0

        severity, reason = classifier.classify(current, baseline)
        # 50% vs 70% = -28.5% change, exceeds 20% threshold
        assert severity in (DecaySeverity.MEDIUM, DecaySeverity.HIGH)
        assert "decay" in reason


class TestAlphaDecayGovernor:
    """Tests for AlphaDecayGovernor class."""

    @pytest.fixture
    def tracker(self):
        """Create performance tracker."""
        return StrategyPerformanceTracker()

    @pytest.fixture
    def classifier(self):
        """Create classifier."""
        return DecaySeverityClassifier()

    @pytest.fixture
    def governor(self, tracker, classifier):
        """Create governor."""
        return AlphaDecayGovernor(tracker, classifier)

    def _create_outcome(
        self,
        strategy_id: str,
        pnl: float,
        pnl_bps: float,
        slippage_bps: float = 5.0,
    ) -> TradeOutcome:
        """Helper to create trade outcome."""
        return TradeOutcome(
            ts_ns=int(time.time() * 1_000_000_000),
            strategy_id=strategy_id,
            symbol="BTC",
            side="buy",
            entry_price=50000.0,
            exit_price=50000.0 + pnl,
            size=1.0,
            pnl=pnl,
            pnl_bps=pnl_bps,
            slippage_bps=slippage_bps,
            hold_time_ns=60_000_000_000,
        )

    def test_no_data_returns_none_action(self, governor):
        """Should return NONE action with no data."""
        decision = governor.evaluate_strategy("unknown")
        assert decision.action == GovernorAction.NONE
        assert decision.severity == DecaySeverity.NONE

    def test_good_performance_allows(self, governor, tracker):
        """Should allow trading with good performance."""
        # Add good trades
        for i in range(20):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))

        decision = governor.evaluate_strategy("strat1")
        assert decision.action == GovernorAction.NONE
        assert decision.size_factor == 1.0

    def test_critical_halts_all(self, governor, tracker):
        """Should halt all for critical decay."""
        # Add terrible trades
        for i in range(20):
            tracker.record_trade(self._create_outcome("strat1", -100.0, -20.0))

        decision = governor.evaluate_strategy("strat1")
        assert decision.severity == DecaySeverity.CRITICAL
        assert decision.action == GovernorAction.HALT_ALL

    def test_is_strategy_enabled(self, governor, tracker):
        """Should track enabled/disabled strategies."""
        for i in range(20):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))

        assert governor.is_strategy_enabled("strat1") is True

    def test_strategy_disabled_after_critical(self, governor, tracker):
        """Should disable strategy after critical decision."""
        for i in range(20):
            tracker.record_trade(self._create_outcome("strat1", -100.0, -20.0))

        governor.evaluate_strategy("strat1")
        # After critical, strategy is halted for cooldown
        assert governor.is_strategy_enabled("strat1") is False

    def test_allows_trading(self, governor):
        """Should report trading allowed status."""
        assert governor.allows_trading() is True

    def test_global_halt_blocks_trading(self, governor, tracker):
        """Global halt should block all trading."""
        # Trigger critical for multiple strategies
        for strat in ["strat1", "strat2"]:
            for i in range(20):
                tracker.record_trade(self._create_outcome(strat, -100.0, -20.0))

        governor.evaluate_all()
        assert governor.allows_trading() is False

    def test_reset_strategy(self, governor, tracker):
        """Should reset individual strategy disabled via MEDIUM severity."""
        # Create metrics that trigger MEDIUM severity (disable strategy, not halt all)
        # MEDIUM = win rate decay from baseline
        # First build up a good baseline
        for i in range(60):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))

        # Now add enough bad trades to decay the recent window below threshold
        # Window size is 100 by default, so we need to swing the metrics
        for i in range(50):
            tracker.record_trade(self._create_outcome("strat1", -50.0, -10.0))

        # Force MEDIUM by manually disabling
        now_ns = int(time.time() * 1_000_000_000)
        governor._disabled_strategies["strat1"] = now_ns

        assert governor.is_strategy_enabled("strat1") is False

        result = governor.reset_strategy("strat1")
        assert result is True
        assert governor.is_strategy_enabled("strat1") is True

    def test_reset_all_requires_confirmation(self, governor, tracker):
        """Should require confirmation to reset all."""
        # Trigger global halt
        for strat in ["strat1", "strat2"]:
            for i in range(20):
                tracker.record_trade(self._create_outcome(strat, -100.0, -20.0))

        governor.evaluate_all()

        # Wrong phrase
        assert governor.reset_all("wrong phrase") is False
        assert governor.allows_trading() is False

        # Correct phrase
        assert governor.reset_all("CONFIRM RESET DECAY GOVERNOR") is True
        assert governor.allows_trading() is True

    def test_get_status(self, governor):
        """Should return status summary."""
        status = governor.get_status()
        assert "allows_trading" in status
        assert "disabled_strategies" in status
        assert "halted_symbols" in status
        assert "global_halt_active" in status

    def test_get_decay_snapshot(self, governor, tracker):
        """Should return decay snapshot."""
        for i in range(20):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))

        snapshot = governor.get_decay_snapshot("strat1")
        assert snapshot is not None
        assert snapshot.strategy_id == "strat1"
        assert snapshot.severity == DecaySeverity.NONE

    def test_get_recent_decisions(self, governor, tracker):
        """Should return recent decisions."""
        for i in range(10):
            tracker.record_trade(self._create_outcome("strat1", 100.0, 20.0))

        governor.evaluate_strategy("strat1")
        decisions = governor.get_recent_decisions()
        assert len(decisions) > 0

    def test_callback_on_action(self, tracker, classifier):
        """Should call callback on non-NONE actions."""
        actions = []

        def callback(decision):
            actions.append(decision)

        governor = AlphaDecayGovernor(tracker, classifier, on_action=callback)

        # Add critical trades
        for i in range(20):
            outcome = TradeOutcome(
                ts_ns=int(time.time() * 1_000_000_000),
                strategy_id="strat1",
                symbol="BTC",
                side="buy",
                entry_price=50000.0,
                exit_price=49000.0,
                size=1.0,
                pnl=-1000.0,
                pnl_bps=-200.0,
                slippage_bps=5.0,
                hold_time_ns=60_000_000_000,
            )
            tracker.record_trade(outcome)

        governor.evaluate_strategy("strat1")
        assert len(actions) > 0


class TestDecaySnapshot:
    """Tests for DecaySnapshot dataclass."""

    def test_snapshot_is_frozen(self):
        """DecaySnapshot should be immutable."""
        snapshot = DecaySnapshot(
            ts_ns=1000,
            strategy_id="test",
            severity=DecaySeverity.LOW,
            reason="test",
            win_rate=0.5,
            expectancy_bps=10.0,
            profit_factor=1.5,
            avg_slippage_bps=5.0,
            sample_count=50,
        )
        with pytest.raises(AttributeError):
            snapshot.severity = DecaySeverity.CRITICAL
