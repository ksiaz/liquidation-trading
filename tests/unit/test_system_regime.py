"""Unit tests for SystemRegimeDetector."""

import pytest
import time

from runtime.meta.system_regime import (
    SystemRegimeDetector,
    RegimeConfig,
)
from runtime.meta.types import SystemRegime


class TestSystemRegimeDetector:
    """Tests for SystemRegimeDetector."""

    def test_init_defaults(self):
        """Test detector initialization."""
        detector = SystemRegimeDetector()
        assert detector._current_regime == SystemRegime.UNKNOWN
        assert len(detector._trades) == 0

    def test_init_custom_config(self):
        """Test detector with custom config."""
        config = RegimeConfig(
            expected_win_rate=0.60,
            expected_profit_factor=2.0
        )
        detector = SystemRegimeDetector(config=config)
        assert detector._config.expected_win_rate == 0.60

    def test_record_trade(self):
        """Test recording trades."""
        detector = SystemRegimeDetector()

        detector.record_trade(won=True, pnl=100.0)
        detector.record_trade(won=False, pnl=-50.0)

        assert len(detector._trades) == 2

    def test_get_regime_insufficient_data(self):
        """Test regime detection with insufficient data."""
        config = RegimeConfig(min_trades_for_assessment=20)
        detector = SystemRegimeDetector(config=config)

        # Only 5 trades
        for _ in range(5):
            detector.record_trade(won=True, pnl=100.0)

        regime = detector.get_regime()
        assert regime == SystemRegime.UNKNOWN

    def test_get_regime_edge_present(self):
        """Test detecting edge present."""
        config = RegimeConfig(
            min_trades_for_assessment=10,
            assessment_window_trades=20,
            expected_win_rate=0.55,
            win_rate_std=0.08,
            edge_present_zscore=-1.0
        )
        detector = SystemRegimeDetector(config=config)

        # 70% win rate - clearly above expectations
        for i in range(30):
            won = i % 10 < 7  # 70% wins
            pnl = 100.0 if won else -50.0
            detector.record_trade(won=won, pnl=pnl)

        regime = detector.get_regime()
        assert regime == SystemRegime.EDGE_PRESENT

    def test_get_regime_edge_decaying(self):
        """Test detecting edge decaying."""
        config = RegimeConfig(
            min_trades_for_assessment=10,
            assessment_window_trades=20,
            expected_win_rate=0.55,
            win_rate_std=0.08,
            edge_present_zscore=-1.0,
            edge_decaying_zscore=-2.0
        )
        detector = SystemRegimeDetector(config=config)

        # 40% win rate - below expectations
        for i in range(30):
            won = i % 10 < 4  # 40% wins
            pnl = 100.0 if won else -50.0
            detector.record_trade(won=won, pnl=pnl)

        regime = detector.get_regime()
        assert regime in (SystemRegime.EDGE_DECAYING, SystemRegime.REGIME_CHANGE)

    def test_get_regime_edge_gone(self):
        """Test detecting edge gone."""
        config = RegimeConfig(
            min_trades_for_assessment=10,
            assessment_window_trades=20,
            expected_win_rate=0.55,
            win_rate_std=0.08,
            edge_gone_zscore=-3.0
        )
        detector = SystemRegimeDetector(config=config)

        # 25% win rate - way below expectations
        for i in range(30):
            won = i % 4 == 0  # 25% wins
            pnl = 100.0 if won else -50.0
            detector.record_trade(won=won, pnl=pnl)

        regime = detector.get_regime()
        assert regime == SystemRegime.EDGE_GONE

    def test_regime_confirmation(self):
        """Test regime change requires confirmation."""
        config = RegimeConfig(
            min_trades_for_assessment=10,
            assessment_window_trades=20,
            expected_win_rate=0.55,
            win_rate_std=0.08
        )
        detector = SystemRegimeDetector(config=config)

        # Start with good performance
        for i in range(20):
            detector.record_trade(won=True, pnl=100.0)

        regime1 = detector.get_regime()
        assert regime1 == SystemRegime.EDGE_PRESENT

        # Now bad performance
        for i in range(20):
            detector.record_trade(won=False, pnl=-50.0)

        # May need multiple checks to confirm regime change
        for _ in range(5):
            detector.get_regime()

        # Eventually should detect decay or edge gone
        regime2 = detector._current_regime
        assert regime2 != SystemRegime.EDGE_PRESENT

    def test_get_current_metrics(self):
        """Test getting current metrics."""
        config = RegimeConfig(min_trades_for_assessment=10)
        detector = SystemRegimeDetector(config=config)

        for i in range(20):
            detector.record_trade(won=i % 2 == 0, pnl=100.0 if i % 2 == 0 else -50.0)

        detector.get_regime()

        metrics = detector.get_current_metrics()

        assert metrics is not None
        assert metrics.observed_win_rate == 0.5
        assert metrics.trade_count == 20

    def test_get_regime_info(self):
        """Test getting regime info."""
        config = RegimeConfig(min_trades_for_assessment=10)
        detector = SystemRegimeDetector(config=config)

        for i in range(20):
            detector.record_trade(won=True, pnl=100.0)

        detector.get_regime()

        info = detector.get_regime_info()

        assert 'regime' in info
        assert 'confidence' in info
        assert 'trade_count' in info

    def test_get_summary(self):
        """Test getting detector summary."""
        config = RegimeConfig(min_trades_for_assessment=10)
        detector = SystemRegimeDetector(config=config)

        for i in range(20):
            detector.record_trade(won=True, pnl=100.0)

        detector.get_regime()

        summary = detector.get_summary()

        assert 'regime' in summary
        assert 'metrics' in summary
        assert 'total_trades' in summary

    def test_should_halt(self):
        """Test halt recommendation."""
        detector = SystemRegimeDetector()

        detector._current_regime = SystemRegime.EDGE_GONE
        assert detector.should_halt() is True

        detector._current_regime = SystemRegime.EDGE_PRESENT
        assert detector.should_halt() is False

    def test_should_reduce_exposure(self):
        """Test exposure reduction recommendation."""
        detector = SystemRegimeDetector()

        detector._current_regime = SystemRegime.EDGE_DECAYING
        assert detector.should_reduce_exposure() is True

        detector._current_regime = SystemRegime.REGIME_CHANGE
        assert detector.should_reduce_exposure() is True

        detector._current_regime = SystemRegime.EDGE_PRESENT
        assert detector.should_reduce_exposure() is False

    def test_reset(self):
        """Test resetting detector."""
        config = RegimeConfig(min_trades_for_assessment=10)
        detector = SystemRegimeDetector(config=config)

        for i in range(20):
            detector.record_trade(won=True, pnl=100.0)

        detector.get_regime()
        detector.reset()

        assert len(detector._trades) == 0
        assert detector._current_regime == SystemRegime.UNKNOWN
        assert detector._regime_confidence == 0.0

    def test_set_expectations(self):
        """Test setting expectations."""
        detector = SystemRegimeDetector()

        detector.set_expectations(
            expected_win_rate=0.60,
            expected_profit_factor=2.0,
            win_rate_std=0.10
        )

        assert detector._config.expected_win_rate == 0.60
        assert detector._config.expected_profit_factor == 2.0
        assert detector._config.win_rate_std == 0.10

    def test_decay_slope_calculation(self):
        """Test edge decay slope calculation."""
        detector = SystemRegimeDetector()

        # Simulate declining win rates
        declining_rates = [0.65, 0.62, 0.58, 0.55, 0.52, 0.48, 0.45]
        for rate in declining_rates:
            detector._rolling_win_rates.append(rate)

        slope = detector._calculate_decay_slope()

        # Should be negative (declining)
        assert slope < 0

    def test_decay_slope_insufficient_data(self):
        """Test decay slope with insufficient data."""
        detector = SystemRegimeDetector()

        # Only 2 data points
        detector._rolling_win_rates.append(0.55)
        detector._rolling_win_rates.append(0.50)

        slope = detector._calculate_decay_slope()
        assert slope == 0.0  # Not enough data

    def test_metrics_history(self):
        """Test metrics history accumulation."""
        config = RegimeConfig(min_trades_for_assessment=10)
        detector = SystemRegimeDetector(config=config)

        for i in range(20):
            detector.record_trade(won=True, pnl=100.0)

        # Multiple regime checks
        for _ in range(3):
            detector.get_regime()

        assert len(detector._metrics_history) == 3


class TestRegimeConfig:
    """Tests for RegimeConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        config = RegimeConfig()

        assert config.expected_win_rate == 0.55
        assert config.expected_profit_factor == 1.5
        assert config.min_trades_for_assessment == 20

    def test_custom_values(self):
        """Test custom configuration."""
        config = RegimeConfig(
            expected_win_rate=0.60,
            edge_gone_zscore=-4.0
        )

        assert config.expected_win_rate == 0.60
        assert config.edge_gone_zscore == -4.0


class TestEdgeMetrics:
    """Tests for EdgeMetrics dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from runtime.meta.types import EdgeMetrics

        metrics = EdgeMetrics(
            timestamp_ns=1000,
            expected_win_rate=0.55,
            observed_win_rate=0.60,
            win_rate_zscore=0.625,
            expected_profit_factor=1.5,
            observed_profit_factor=1.8,
            information_ratio=0.5,
            edge_decay_rate=-0.001,
            trade_count=50,
            period_days=7
        )

        d = metrics.to_dict()

        assert d['expected_win_rate'] == 0.55
        assert d['observed_win_rate'] == 0.60
        assert d['trade_count'] == 50
