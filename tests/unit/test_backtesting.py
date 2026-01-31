"""
Unit tests for backtesting infrastructure (HLP22).

Tests:
- Parameter sweep configuration and execution
- Metrics calculation
- Determinism verification
"""

import pytest
from datetime import datetime
import asyncio
from typing import Dict, List, Any

from runtime.backtesting.parameter_sweep import (
    ParameterSweep,
    SweepConfig,
    SweepResult,
    ParameterResult,
    BacktestMetrics,
    OptimizationMetric,
    calculate_metrics_from_trades,
)
from runtime.backtesting.determinism_checker import (
    DeterminismChecker,
    DeterminismResult,
    TradeRecord,
    RunResult,
)


# =============================================================================
# Sweep Configuration Tests
# =============================================================================

class TestSweepConfig:
    """Tests for SweepConfig."""

    def test_basic_config(self):
        """Test creating basic sweep config."""
        config = SweepConfig(
            parameters={
                'threshold': [0.1, 0.15, 0.2],
                'multiplier': [1.0, 1.5],
            },
        )

        assert len(config.parameters) == 2
        assert config.metric == OptimizationMetric.SHARPE

    def test_total_combinations(self):
        """Test combination count calculation."""
        config = SweepConfig(
            parameters={
                'a': [1, 2, 3],       # 3 values
                'b': [10, 20],        # 2 values
                'c': [0.1, 0.2, 0.3], # 3 values
            },
        )

        assert config.total_combinations == 3 * 2 * 3  # 18

    def test_empty_parameters(self):
        """Test empty parameters."""
        config = SweepConfig(parameters={})
        assert config.total_combinations == 0

    def test_single_parameter(self):
        """Test single parameter sweep."""
        config = SweepConfig(
            parameters={'x': [1, 2, 3, 4, 5]},
        )
        assert config.total_combinations == 5


# =============================================================================
# Backtest Metrics Tests
# =============================================================================

class TestBacktestMetrics:
    """Tests for BacktestMetrics."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        metrics = BacktestMetrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            win_rate=0.6,
            max_drawdown=0.08,
        )

        assert metrics.total_return == 0.15
        assert metrics.sharpe_ratio == 1.5
        assert metrics.win_rate == 0.6

    def test_to_dict(self):
        """Test serialization."""
        metrics = BacktestMetrics(
            total_return=0.10,
            sharpe_ratio=2.0,
        )

        data = metrics.to_dict()
        assert 'total_return' in data
        assert 'sharpe_ratio' in data


class TestCalculateMetricsFromTrades:
    """Tests for calculate_metrics_from_trades function."""

    def test_empty_trades(self):
        """Test with no trades."""
        metrics = calculate_metrics_from_trades([])
        assert metrics.total_trades == 0
        assert metrics.total_return == 0

    def test_all_winners(self):
        """Test with all winning trades."""
        trades = [
            {'pnl': 100},
            {'pnl': 150},
            {'pnl': 200},
        ]
        metrics = calculate_metrics_from_trades(trades)

        assert metrics.total_trades == 3
        assert metrics.winning_trades == 3
        assert metrics.losing_trades == 0
        assert metrics.win_rate == 1.0
        assert metrics.total_return == 450

    def test_all_losers(self):
        """Test with all losing trades."""
        trades = [
            {'pnl': -100},
            {'pnl': -50},
        ]
        metrics = calculate_metrics_from_trades(trades)

        assert metrics.total_trades == 2
        assert metrics.winning_trades == 0
        assert metrics.losing_trades == 2
        assert metrics.win_rate == 0.0

    def test_mixed_trades(self):
        """Test with mixed results."""
        trades = [
            {'pnl': 100},
            {'pnl': -50},
            {'pnl': 75},
            {'pnl': -25},
        ]
        metrics = calculate_metrics_from_trades(trades)

        assert metrics.total_trades == 4
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 2
        assert metrics.win_rate == 0.5
        assert metrics.total_return == 100
        assert metrics.profit_factor == 175 / 75  # 2.33...

    def test_drawdown_calculation(self):
        """Test max drawdown calculation."""
        # Equity: 100, 50, 150, 100
        # Peak:   100, 100, 150, 150
        # DD:     0%, 50%, 0%, 33%
        trades = [
            {'pnl': 100},
            {'pnl': -50},
            {'pnl': 100},
            {'pnl': -50},
        ]
        metrics = calculate_metrics_from_trades(trades)

        assert metrics.max_drawdown == 0.5  # 50% drawdown

    def test_avg_win_loss(self):
        """Test average win/loss calculation."""
        trades = [
            {'pnl': 100},
            {'pnl': 200},
            {'pnl': -50},
            {'pnl': -100},
        ]
        metrics = calculate_metrics_from_trades(trades)

        assert metrics.avg_win == 150  # (100 + 200) / 2
        assert metrics.avg_loss == -75  # (-50 + -100) / 2


# =============================================================================
# Parameter Sweep Tests
# =============================================================================

class TestParameterSweep:
    """Tests for ParameterSweep."""

    @pytest.fixture
    def simple_backtest(self):
        """Simple backtest function for testing."""
        def backtest(params: Dict[str, float]) -> BacktestMetrics:
            # Sharpe increases with threshold
            threshold = params.get('threshold', 0.1)
            return BacktestMetrics(
                total_return=threshold * 100,
                sharpe_ratio=threshold * 10,  # Higher threshold = higher sharpe
                win_rate=0.5 + threshold,
                max_drawdown=0.1,
                total_trades=20,
            )
        return backtest

    @pytest.mark.asyncio
    async def test_basic_sweep(self, simple_backtest):
        """Test basic parameter sweep."""
        sweep = ParameterSweep(simple_backtest)

        config = SweepConfig(
            parameters={'threshold': [0.1, 0.15, 0.2]},
            min_trades=5,
        )

        result = await sweep.run(config)

        assert result.total_combinations == 3
        assert result.valid_combinations == 3
        assert result.best_combination is not None
        assert result.best_combination.parameters['threshold'] == 0.2  # Highest sharpe

    @pytest.mark.asyncio
    async def test_multi_param_sweep(self, simple_backtest):
        """Test sweep with multiple parameters."""
        def multi_backtest(params: Dict[str, float]) -> BacktestMetrics:
            t = params.get('threshold', 0.1)
            m = params.get('multiplier', 1.0)
            return BacktestMetrics(
                sharpe_ratio=t * m,
                total_trades=20,
            )

        sweep = ParameterSweep(multi_backtest)

        config = SweepConfig(
            parameters={
                'threshold': [0.1, 0.2],
                'multiplier': [1.0, 2.0],
            },
            min_trades=5,
        )

        result = await sweep.run(config)

        assert result.total_combinations == 4
        assert result.best_combination.parameters == {
            'threshold': 0.2,
            'multiplier': 2.0,
        }

    @pytest.mark.asyncio
    async def test_invalid_results_filtered(self):
        """Test that invalid results are filtered."""
        def low_trades_backtest(params: Dict[str, float]) -> BacktestMetrics:
            return BacktestMetrics(
                sharpe_ratio=2.0,
                total_trades=5,  # Below minimum
            )

        sweep = ParameterSweep(low_trades_backtest)

        config = SweepConfig(
            parameters={'x': [1, 2, 3]},
            min_trades=10,  # Require 10 trades
        )

        result = await sweep.run(config)

        assert result.total_combinations == 3
        assert result.valid_combinations == 0
        assert result.best_combination is None

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test handling of backtest errors."""
        call_count = [0]

        def error_backtest(params: Dict[str, float]) -> BacktestMetrics:
            call_count[0] += 1
            if params.get('x') == 2:
                raise ValueError("Simulated error")
            return BacktestMetrics(sharpe_ratio=1.0, total_trades=20)

        sweep = ParameterSweep(error_backtest)

        config = SweepConfig(
            parameters={'x': [1, 2, 3]},
            min_trades=5,
        )

        result = await sweep.run(config)

        assert result.total_combinations == 3
        assert result.valid_combinations == 2
        assert result.failed_combinations == 1

    @pytest.mark.asyncio
    async def test_different_metrics(self):
        """Test optimization with different metrics."""
        def backtest(params: Dict[str, float]) -> BacktestMetrics:
            x = params.get('x', 1)
            return BacktestMetrics(
                total_return=x * 0.1,
                sharpe_ratio=x * 0.5,
                win_rate=0.5 + x * 0.1,
                max_drawdown=x * 0.02,
                total_trades=20,
            )

        sweep = ParameterSweep(backtest)

        # Optimize for win rate
        config = SweepConfig(
            parameters={'x': [1, 2, 3]},
            metric=OptimizationMetric.WIN_RATE,
            min_trades=5,
        )

        result = await sweep.run(config)
        assert result.best_combination.parameters['x'] == 3  # Highest win rate

    @pytest.mark.asyncio
    async def test_async_backtest(self):
        """Test with async backtest function."""
        async def async_backtest(params: Dict[str, float]) -> BacktestMetrics:
            await asyncio.sleep(0.01)  # Simulate async work
            return BacktestMetrics(
                sharpe_ratio=params.get('x', 1),
                total_trades=20,
            )

        sweep = ParameterSweep(async_backtest)

        config = SweepConfig(
            parameters={'x': [1, 2]},
            min_trades=5,
        )

        result = await sweep.run(config)
        assert result.valid_combinations == 2

    def test_get_top_n(self, simple_backtest):
        """Test getting top N results."""
        # Create mock result
        results = [
            ParameterResult(
                parameters={'x': i},
                metrics=BacktestMetrics(sharpe_ratio=i, total_trades=20),
                score=float(i),
                is_valid=True,
            )
            for i in range(10)
        ]

        sweep_result = SweepResult(
            config=SweepConfig(parameters={'x': list(range(10))}),
            results=results,
            best_combination=results[-1],
            start_time=datetime.now(),
            end_time=datetime.now(),
            total_combinations=10,
            valid_combinations=10,
            failed_combinations=0,
        )

        top3 = sweep_result.get_top_n(3)
        assert len(top3) == 3
        assert top3[0].parameters['x'] == 9  # Highest
        assert top3[1].parameters['x'] == 8
        assert top3[2].parameters['x'] == 7

    def test_parameter_sensitivity(self, simple_backtest):
        """Test parameter sensitivity analysis."""
        results = []
        for x in [1, 1, 2, 2, 3, 3]:
            results.append(ParameterResult(
                parameters={'x': x},
                metrics=BacktestMetrics(),
                score=float(x),  # Score = x
                is_valid=True,
            ))

        sweep_result = SweepResult(
            config=SweepConfig(parameters={'x': [1, 2, 3]}),
            results=results,
            best_combination=results[-1],
            start_time=datetime.now(),
            end_time=datetime.now(),
            total_combinations=6,
            valid_combinations=6,
            failed_combinations=0,
        )

        sensitivity = sweep_result.get_parameter_sensitivity('x')
        assert sensitivity[1] == 1.0  # avg of two 1s
        assert sensitivity[2] == 2.0
        assert sensitivity[3] == 3.0


# =============================================================================
# Determinism Checker Tests
# =============================================================================

class TestTradeRecord:
    """Tests for TradeRecord."""

    def test_record_creation(self):
        """Test creating trade record."""
        record = TradeRecord(
            index=0,
            timestamp="2024-01-01T12:00:00",
            symbol="BTC-PERP",
            side="long",
            size=0.1,
            entry_price=50000,
            exit_price=51000,
            pnl=100,
        )

        assert record.symbol == "BTC-PERP"
        assert record.pnl == 100

    def test_identical_records_same_hash(self):
        """Test identical records produce same hash."""
        record1 = TradeRecord(0, "t", "BTC", "long", 0.1, 100, 110, 10)
        record2 = TradeRecord(0, "t", "BTC", "long", 0.1, 100, 110, 10)

        assert record1.to_hash() == record2.to_hash()

    def test_different_records_different_hash(self):
        """Test different records produce different hash."""
        record1 = TradeRecord(0, "t", "BTC", "long", 0.1, 100, 110, 10)
        record2 = TradeRecord(0, "t", "BTC", "long", 0.2, 100, 110, 10)  # Different size

        assert record1.to_hash() != record2.to_hash()


class TestRunResult:
    """Tests for RunResult."""

    def test_from_trades(self):
        """Test creating from trade data."""
        trades = [
            {'symbol': 'BTC', 'side': 'long', 'size': 0.1, 'entry_price': 100, 'exit_price': 110, 'pnl': 10},
            {'symbol': 'ETH', 'side': 'short', 'size': 1.0, 'entry_price': 50, 'exit_price': 45, 'pnl': 5},
        ]

        result = RunResult.from_trades(0, trades, 1.5)

        assert result.run_id == 0
        assert result.trade_count == 2
        assert result.final_pnl == 15
        assert result.execution_time_sec == 1.5

    def test_empty_trades(self):
        """Test with empty trades."""
        result = RunResult.from_trades(0, [], 0.1)

        assert result.trade_count == 0
        assert result.final_pnl == 0


class TestDeterminismChecker:
    """Tests for DeterminismChecker."""

    @pytest.fixture
    def deterministic_backtest(self):
        """Backtest that always returns same results."""
        def backtest(params: Dict[str, float]) -> List[Dict[str, Any]]:
            x = params.get('x', 1)
            return [
                {'symbol': 'BTC', 'side': 'long', 'size': x, 'entry_price': 100, 'exit_price': 110, 'pnl': 10 * x},
                {'symbol': 'ETH', 'side': 'short', 'size': x, 'entry_price': 50, 'exit_price': 45, 'pnl': 5 * x},
            ]
        return backtest

    @pytest.fixture
    def nondeterministic_backtest(self):
        """Backtest that returns different results each time."""
        import random
        def backtest(params: Dict[str, float]) -> List[Dict[str, Any]]:
            return [
                {'symbol': 'BTC', 'side': 'long', 'size': random.random(), 'entry_price': 100, 'exit_price': 110, 'pnl': random.random()},
            ]
        return backtest

    @pytest.mark.asyncio
    async def test_deterministic_passes(self, deterministic_backtest):
        """Test deterministic backtest passes check."""
        checker = DeterminismChecker(deterministic_backtest)

        result = await checker.verify({'x': 1.0}, n_runs=3)

        assert result.is_deterministic
        assert len(result.divergences) == 0
        assert result.first_divergence_index is None

    @pytest.mark.asyncio
    async def test_nondeterministic_fails(self, nondeterministic_backtest):
        """Test non-deterministic backtest fails check."""
        checker = DeterminismChecker(nondeterministic_backtest)

        result = await checker.verify({'x': 1.0}, n_runs=3)

        assert not result.is_deterministic
        assert len(result.divergences) > 0

    @pytest.mark.asyncio
    async def test_async_backtest(self):
        """Test with async backtest function."""
        async def async_backtest(params: Dict[str, float]) -> List[Dict[str, Any]]:
            await asyncio.sleep(0.01)
            return [
                {'symbol': 'BTC', 'side': 'long', 'size': 0.1, 'entry_price': 100, 'exit_price': 110, 'pnl': 10},
            ]

        checker = DeterminismChecker(async_backtest)
        result = await checker.verify({'x': 1.0}, n_runs=2)

        assert result.is_deterministic

    @pytest.mark.asyncio
    async def test_min_runs_required(self, deterministic_backtest):
        """Test minimum runs requirement."""
        checker = DeterminismChecker(deterministic_backtest)

        with pytest.raises(ValueError, match="at least 2 runs"):
            await checker.verify({'x': 1.0}, n_runs=1)

    @pytest.mark.asyncio
    async def test_result_serialization(self, deterministic_backtest):
        """Test result to_dict."""
        checker = DeterminismChecker(deterministic_backtest)
        result = await checker.verify({'x': 1.0}, n_runs=2)

        data = result.to_dict()
        assert 'is_deterministic' in data
        assert 'n_runs' in data
        assert 'trade_counts' in data

    @pytest.mark.asyncio
    async def test_trade_count_divergence(self):
        """Test detection of trade count divergence."""
        call_count = [0]

        def varying_backtest(params: Dict[str, float]) -> List[Dict[str, Any]]:
            call_count[0] += 1
            # Return different number of trades each time
            return [
                {'symbol': 'BTC', 'side': 'long', 'size': 0.1, 'entry_price': 100, 'exit_price': 110, 'pnl': 10}
            ] * call_count[0]

        checker = DeterminismChecker(varying_backtest)
        result = await checker.verify({'x': 1.0}, n_runs=3)

        assert not result.is_deterministic
        # Should detect trade count difference
        count_divergence = [d for d in result.divergences if d.field == 'trade_count']
        assert len(count_divergence) > 0
