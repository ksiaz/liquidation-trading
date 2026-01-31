"""
Unit tests for threshold configuration and discovery.

Tests:
- ThresholdConfig defaults and validation tracking
- ThresholdDocumentation provenance
- ThresholdRegistry operations
- GridSearchOptimizer parameter testing
- WalkForwardValidator out-of-sample validation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import numpy as np

from runtime.config.thresholds import (
    ThresholdConfig,
    OIThresholds,
    FundingThresholds,
    DepthThresholds,
    ConfidenceThresholds,
    TimingThresholds,
)
from runtime.config.threshold_docs import (
    ThresholdDocumentation,
    ThresholdRegistry,
    DiscoveryMethod,
    ValidationStatus,
    PerformanceMetrics,
    SensitivityResult,
)
from runtime.optimization.grid_search import (
    GridSearchOptimizer,
    GridSearchConfig,
    GridSearchResult,
    ParameterGrid,
    BacktestResult,
    OptimizationMetric,
)
from runtime.optimization.walk_forward import (
    WalkForwardValidator,
    WalkForwardConfig,
    WalkForwardResult,
    FoldResult,
    WindowType,
)


# =============================================================================
# ThresholdConfig Tests
# =============================================================================

class TestThresholdConfig:
    """Tests for ThresholdConfig."""

    def test_default_values(self):
        """Verify conservative default values."""
        config = ThresholdConfig()

        # OI defaults
        assert config.oi.spike_ratio == 1.15
        assert config.oi.collapse_ratio == 0.85
        assert config.oi.elevation_zscore == 2.0

        # Funding defaults
        assert config.funding.skew_threshold == 0.0015
        assert config.funding.extreme_skew == 0.005

        # Depth defaults
        assert config.depth.asymmetry_ratio == 1.5
        assert config.depth.thinning_pct == 0.50

        # Confidence defaults
        assert config.confidence.minimum_match_score == 0.70
        assert config.confidence.high_confidence_score == 0.85

        # Timing defaults
        assert config.timing.armed_timeout_sec == 120
        assert config.timing.cooldown_sec == 300

    def test_validation_tracking(self):
        """Test threshold validation status tracking."""
        config = ThresholdConfig()

        # Initially nothing is validated
        assert not config.is_validated('oi.spike_ratio')
        assert 'oi.spike_ratio' in config.get_unvalidated()

        # Mark as validated
        config.mark_validated('oi.spike_ratio')
        assert config.is_validated('oi.spike_ratio')
        assert 'oi.spike_ratio' not in config.get_unvalidated()

        # Validation date recorded
        assert config.get_validation_date('oi.spike_ratio') is not None

    def test_get_threshold_value(self):
        """Test getting threshold by path."""
        config = ThresholdConfig()

        assert config.get_threshold_value('oi.spike_ratio') == 1.15
        assert config.get_threshold_value('funding.skew_threshold') == 0.0015
        assert config.get_threshold_value('invalid.path') is None
        assert config.get_threshold_value('single') is None

    def test_set_threshold_value(self):
        """Test setting threshold by path."""
        config = ThresholdConfig()

        assert config.set_threshold_value('oi.spike_ratio', 1.20)
        assert config.oi.spike_ratio == 1.20

        assert not config.set_threshold_value('invalid.path', 1.0)
        assert not config.set_threshold_value('oi.nonexistent', 1.0)

    def test_to_dict_from_dict(self):
        """Test serialization round-trip."""
        config = ThresholdConfig()
        config.oi.spike_ratio = 1.25
        config.mark_validated('oi.spike_ratio')

        data = config.to_dict()
        restored = ThresholdConfig.from_dict(data)

        assert restored.oi.spike_ratio == 1.25
        assert restored.is_validated('oi.spike_ratio')

    def test_all_threshold_names(self):
        """Test that all threshold names are tracked."""
        config = ThresholdConfig()
        all_names = config._get_all_threshold_names()

        # Check some expected names exist
        assert 'oi.spike_ratio' in all_names
        assert 'oi.collapse_ratio' in all_names
        assert 'funding.skew_threshold' in all_names
        assert 'depth.asymmetry_ratio' in all_names
        assert 'confidence.minimum_match_score' in all_names
        assert 'timing.cooldown_sec' in all_names


# =============================================================================
# ThresholdDocumentation Tests
# =============================================================================

class TestThresholdDocumentation:
    """Tests for ThresholdDocumentation."""

    def test_documentation_creation(self):
        """Test creating threshold documentation."""
        doc = ThresholdDocumentation(
            name='oi.spike_ratio',
            value=1.15,
            discovery_date=datetime(2024, 1, 15),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime(2023, 6, 1), datetime(2023, 12, 31)),
            performance=PerformanceMetrics(
                sharpe_ratio=1.5,
                win_rate=0.55,
                n_trades=150,
            ),
            rationale="15% spike captures 80% of cascades",
        )

        assert doc.name == 'oi.spike_ratio'
        assert doc.value == 1.15
        assert doc.discovery_method == DiscoveryMethod.GRID_SEARCH

    def test_needs_review(self):
        """Test review date checking."""
        # Past review date
        doc = ThresholdDocumentation(
            name='test',
            value=1.0,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.MANUAL,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
            next_review_date=datetime.now() - timedelta(days=1),
        )
        assert doc.needs_review()

        # Future review date
        doc.next_review_date = datetime.now() + timedelta(days=30)
        assert not doc.needs_review()

        # No review date
        doc.next_review_date = None
        assert doc.needs_review()

    def test_oos_degradation(self):
        """Test out-of-sample degradation calculation."""
        doc = ThresholdDocumentation(
            name='test',
            value=1.0,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(sharpe_ratio=2.0),
            oos_validation=PerformanceMetrics(sharpe_ratio=1.6),
        )

        degradation = doc.get_oos_degradation()
        assert degradation == pytest.approx(0.2)  # 20% degradation

    def test_sensitivity_stability(self):
        """Test sensitivity stability check."""
        doc = ThresholdDocumentation(
            name='test',
            value=1.0,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
            sensitivity={
                '+10%': SensitivityResult(
                    threshold_name='test',
                    base_value=1.0,
                    test_value=1.1,
                    change_pct=10.0,
                    sharpe_change_pct=-5.0,
                    win_rate_change_pct=-3.0,
                    is_stable=True,
                ),
                '-10%': SensitivityResult(
                    threshold_name='test',
                    base_value=1.0,
                    test_value=0.9,
                    change_pct=-10.0,
                    sharpe_change_pct=-8.0,
                    win_rate_change_pct=-4.0,
                    is_stable=True,
                ),
            },
        )

        assert doc.is_sensitivity_stable()

        # Add unstable result
        doc.sensitivity['+20%'] = SensitivityResult(
            threshold_name='test',
            base_value=1.0,
            test_value=1.2,
            change_pct=20.0,
            sharpe_change_pct=-25.0,
            win_rate_change_pct=-15.0,
            is_stable=False,
        )
        assert not doc.is_sensitivity_stable()

    def test_to_dict(self):
        """Test serialization."""
        doc = ThresholdDocumentation(
            name='test',
            value=1.15,
            discovery_date=datetime(2024, 1, 1),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime(2023, 6, 1), datetime(2023, 12, 31)),
            performance=PerformanceMetrics(sharpe_ratio=1.5, win_rate=0.55),
            status=ValidationStatus.VALIDATED,
        )

        data = doc.to_dict()
        assert data['name'] == 'test'
        assert data['value'] == 1.15
        assert data['discovery_method'] == 'GRID_SEARCH'
        assert data['status'] == 'VALIDATED'


# =============================================================================
# ThresholdRegistry Tests
# =============================================================================

class TestThresholdRegistry:
    """Tests for ThresholdRegistry."""

    def test_register_and_get(self):
        """Test registering and retrieving thresholds."""
        registry = ThresholdRegistry()

        doc = ThresholdDocumentation(
            name='oi.spike_ratio',
            value=1.15,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
            status=ValidationStatus.VALIDATED,
        )

        registry.register(doc)

        retrieved = registry.get('oi.spike_ratio')
        assert retrieved is not None
        assert retrieved.value == 1.15

        assert registry.get_value('oi.spike_ratio') == 1.15
        assert registry.is_validated('oi.spike_ratio')

    def test_update_tracking(self):
        """Test that updates are tracked in history."""
        registry = ThresholdRegistry()

        doc1 = ThresholdDocumentation(
            name='test',
            value=1.0,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.MANUAL,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
        )
        registry.register(doc1)

        doc2 = ThresholdDocumentation(
            name='test',
            value=1.5,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
        )
        registry.register(doc2)

        history = registry.get_history('test')
        assert len(history) == 2
        assert history[0]['action'] == 'register'
        assert history[1]['action'] == 'update'

    def test_get_unvalidated(self):
        """Test finding unvalidated thresholds."""
        registry = ThresholdRegistry()

        validated = ThresholdDocumentation(
            name='validated',
            value=1.0,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
            status=ValidationStatus.VALIDATED,
        )
        unvalidated = ThresholdDocumentation(
            name='unvalidated',
            value=1.0,
            discovery_date=datetime.now(),
            discovery_method=DiscoveryMethod.MANUAL,
            training_period=(datetime.now(), datetime.now()),
            performance=PerformanceMetrics(),
            status=ValidationStatus.UNVALIDATED,
        )

        registry.register(validated)
        registry.register(unvalidated)

        unvalidated_list = registry.get_unvalidated()
        assert 'unvalidated' in unvalidated_list
        assert 'validated' not in unvalidated_list

    def test_get_by_method(self):
        """Test filtering by discovery method."""
        registry = ThresholdRegistry()

        for name, method in [
            ('grid1', DiscoveryMethod.GRID_SEARCH),
            ('grid2', DiscoveryMethod.GRID_SEARCH),
            ('manual1', DiscoveryMethod.MANUAL),
        ]:
            doc = ThresholdDocumentation(
                name=name,
                value=1.0,
                discovery_date=datetime.now(),
                discovery_method=method,
                training_period=(datetime.now(), datetime.now()),
                performance=PerformanceMetrics(),
            )
            registry.register(doc)

        grid_thresholds = registry.get_by_method(DiscoveryMethod.GRID_SEARCH)
        assert len(grid_thresholds) == 2
        assert 'grid1' in grid_thresholds
        assert 'grid2' in grid_thresholds

    def test_summary(self):
        """Test registry summary."""
        registry = ThresholdRegistry()

        for i, status in enumerate([
            ValidationStatus.VALIDATED,
            ValidationStatus.VALIDATED,
            ValidationStatus.UNVALIDATED,
        ]):
            doc = ThresholdDocumentation(
                name=f'test{i}',
                value=1.0,
                discovery_date=datetime.now(),
                discovery_method=DiscoveryMethod.GRID_SEARCH,
                training_period=(datetime.now(), datetime.now()),
                performance=PerformanceMetrics(),
                status=status,
            )
            registry.register(doc)

        summary = registry.get_summary()
        assert summary['total_thresholds'] == 3
        assert summary['validated'] == 2
        assert summary['unvalidated'] == 1


# =============================================================================
# ParameterGrid Tests
# =============================================================================

class TestParameterGrid:
    """Tests for ParameterGrid."""

    def test_linear_grid(self):
        """Test linear parameter grid generation."""
        grid = ParameterGrid(
            param_name='oi.spike_ratio',
            min_value=1.10,
            max_value=1.20,
            step=0.02,
        )

        values = grid.get_values()
        expected = [1.10, 1.12, 1.14, 1.16, 1.18, 1.20]

        assert len(values) == len(expected)
        for v, e in zip(values, expected):
            assert v == pytest.approx(e, abs=0.001)

    def test_log_scale_grid(self):
        """Test logarithmic parameter grid generation."""
        grid = ParameterGrid(
            param_name='test',
            min_value=1.0,
            max_value=100.0,
            step=0.5,  # log10 step
            log_scale=True,
        )

        values = grid.get_values()
        # Should span from 1 to 100 in log space
        assert values[0] == pytest.approx(1.0, rel=0.1)
        assert values[-1] == pytest.approx(100.0, rel=0.1)


# =============================================================================
# GridSearchOptimizer Tests
# =============================================================================

class TestGridSearchOptimizer:
    """Tests for GridSearchOptimizer."""

    @pytest.fixture
    def mock_backtest_fn(self):
        """Create mock backtest function."""
        async def backtest(param_name, value, data):
            # Simulate: optimal at 1.15, degrades away from it
            distance = abs(value - 1.15)
            sharpe = 2.0 - distance * 10
            return BacktestResult(
                param_value=value,
                sharpe_ratio=max(0, sharpe),
                win_rate=0.55 - distance,
                profit_factor=1.5 - distance * 5,
                max_drawdown=0.10 + distance,
                n_trades=100,
                total_pnl=1000 - distance * 5000,
                avg_trade_pnl=10,
            )
        return backtest

    @pytest.mark.asyncio
    async def test_grid_search_finds_optimal(self, mock_backtest_fn):
        """Test grid search finds optimal value."""
        optimizer = GridSearchOptimizer(
            config=GridSearchConfig(min_trades=10),
            backtest_fn=mock_backtest_fn,
        )

        grid = ParameterGrid(
            param_name='oi.spike_ratio',
            min_value=1.10,
            max_value=1.20,
            step=0.01,
        )

        result = await optimizer.run_grid_search(grid, data=None)

        # Should find 1.15 as optimal
        assert result.optimal_value == pytest.approx(1.15, abs=0.01)
        assert result.optimal_sharpe > 0
        assert result.values_tested > 0
        assert result.values_valid > 0

    @pytest.mark.asyncio
    async def test_grid_search_with_cache(self, mock_backtest_fn):
        """Test result caching."""
        optimizer = GridSearchOptimizer(
            config=GridSearchConfig(cache_results=True, min_trades=10),
            backtest_fn=mock_backtest_fn,
        )

        grid = ParameterGrid(
            param_name='test',
            min_value=1.10,
            max_value=1.12,
            step=0.01,
        )

        # First run
        await optimizer.run_grid_search(grid, data=None)

        # Second run should use cache
        result2 = await optimizer.run_grid_search(grid, data=None)
        assert result2.values_tested > 0

        # Clear cache
        optimizer.clear_cache()

    @pytest.mark.asyncio
    async def test_combined_metric_optimization(self):
        """Test optimization with combined metric."""
        async def backtest(param_name, value, data):
            return BacktestResult(
                param_value=value,
                sharpe_ratio=1.5,
                win_rate=0.60,
                profit_factor=1.8,
                max_drawdown=0.15,
                n_trades=50,
                total_pnl=500,
                avg_trade_pnl=10,
            )

        optimizer = GridSearchOptimizer(
            config=GridSearchConfig(
                metric=OptimizationMetric.COMBINED,
                sharpe_weight=0.4,
                win_rate_weight=0.3,
                profit_factor_weight=0.2,
                drawdown_weight=0.1,
                min_trades=10,
            ),
            backtest_fn=backtest,
        )

        grid = ParameterGrid(
            param_name='test',
            min_value=1.0,
            max_value=1.1,
            step=0.05,
        )

        result = await optimizer.run_grid_search(grid, data=None)
        assert result.optimal_value is not None

    @pytest.mark.asyncio
    async def test_sensitivity_analysis(self, mock_backtest_fn):
        """Test sensitivity analysis around optimal."""
        optimizer = GridSearchOptimizer(
            backtest_fn=mock_backtest_fn,
        )

        results = await optimizer.run_sensitivity_analysis(
            param_name='test',
            base_value=1.15,
            data=None,
            change_pcts=[-10, -5, 5, 10],
        )

        assert 'base' in results
        assert '-10%' in results
        assert '+10%' in results

    def test_get_top_n_results(self, mock_backtest_fn):
        """Test getting top N results."""
        result = GridSearchResult(
            param_name='test',
            optimal_value=1.15,
            optimal_sharpe=2.0,
            optimal_win_rate=0.55,
            optimal_profit_factor=1.5,
            optimal_n_trades=100,
            all_results=[
                BacktestResult(1.10, 1.5, 0.50, 1.3, 0.12, 80, 800, 10),
                BacktestResult(1.15, 2.0, 0.55, 1.5, 0.10, 100, 1000, 10),
                BacktestResult(1.20, 1.0, 0.45, 1.2, 0.15, 60, 600, 10),
            ],
        )

        top2 = result.get_top_n(2)
        assert len(top2) == 2
        assert top2[0].sharpe_ratio == 2.0
        assert top2[1].sharpe_ratio == 1.5


# =============================================================================
# WalkForwardValidator Tests
# =============================================================================

class TestWalkForwardValidator:
    """Tests for WalkForwardValidator."""

    @pytest.fixture
    def mock_backtest_fn(self):
        """Create mock backtest function for walk-forward."""
        async def backtest(param_name, value, data, start, end):
            # Simulate consistent performance
            return {
                'sharpe': 1.5,
                'win_rate': 0.55,
                'n_trades': 30,
                'total_pnl': 500,
            }
        return backtest

    @pytest.mark.asyncio
    async def test_validation_passes(self, mock_backtest_fn):
        """Test validation passes with good metrics."""
        validator = WalkForwardValidator(
            config=WalkForwardConfig(
                n_folds=3,
                max_degradation=0.30,
                min_oos_sharpe=0.5,
                min_oos_trades=10,
            ),
            backtest_fn=mock_backtest_fn,
        )

        # Create mock data with timestamps
        class MockData:
            def __init__(self):
                self.timestamps = [
                    datetime.now() - timedelta(days=90),
                    datetime.now(),
                ]

        result = await validator.validate(
            threshold_name='oi.spike_ratio',
            threshold_value=1.15,
            data=MockData(),
        )

        assert result.passed
        assert result.avg_test_sharpe > 0
        assert result.oos_sharpe == result.avg_test_sharpe
        assert len(result.fold_results) > 0

    @pytest.mark.asyncio
    async def test_validation_fails_low_sharpe(self):
        """Test validation fails with low OOS Sharpe."""
        async def low_sharpe_backtest(param_name, value, data, start, end):
            return {
                'sharpe': 0.2,  # Below minimum
                'win_rate': 0.45,
                'n_trades': 30,
                'total_pnl': 100,
            }

        validator = WalkForwardValidator(
            config=WalkForwardConfig(
                n_folds=2,
                min_oos_sharpe=0.5,
                min_oos_trades=10,
            ),
            backtest_fn=low_sharpe_backtest,
        )

        class MockData:
            timestamps = [datetime.now() - timedelta(days=60), datetime.now()]

        result = await validator.validate(
            threshold_name='test',
            threshold_value=1.0,
            data=MockData(),
        )

        assert not result.passed
        assert any('OOS Sharpe' in r for r in result.failure_reasons)

    @pytest.mark.asyncio
    async def test_validation_fails_high_degradation(self):
        """Test validation fails with high degradation."""
        call_count = [0]

        async def degrading_backtest(param_name, value, data, start, end):
            call_count[0] += 1
            # Training has high sharpe, test has low
            is_training = call_count[0] % 2 == 1
            return {
                'sharpe': 2.0 if is_training else 0.5,  # 75% degradation
                'win_rate': 0.55,
                'n_trades': 30,
                'total_pnl': 500 if is_training else 100,
            }

        validator = WalkForwardValidator(
            config=WalkForwardConfig(
                n_folds=2,
                max_degradation=0.20,  # 20% max allowed
                min_oos_sharpe=0.3,
                min_oos_trades=10,
            ),
            backtest_fn=degrading_backtest,
        )

        class MockData:
            timestamps = [datetime.now() - timedelta(days=60), datetime.now()]

        result = await validator.validate(
            threshold_name='test',
            threshold_value=1.0,
            data=MockData(),
        )

        assert not result.passed
        assert any('Degradation' in r for r in result.failure_reasons)

    @pytest.mark.asyncio
    async def test_validate_multiple(self, mock_backtest_fn):
        """Test validating multiple threshold values."""
        validator = WalkForwardValidator(
            config=WalkForwardConfig(n_folds=2, min_oos_trades=10),
            backtest_fn=mock_backtest_fn,
        )

        class MockData:
            timestamps = [datetime.now() - timedelta(days=60), datetime.now()]

        results = await validator.validate_multiple(
            threshold_name='test',
            values=[1.10, 1.15, 1.20],
            data=MockData(),
        )

        assert len(results) == 3
        assert 1.10 in results
        assert 1.15 in results
        assert 1.20 in results

    @pytest.mark.asyncio
    async def test_get_best_validated(self, mock_backtest_fn):
        """Test finding best validated threshold."""
        validator = WalkForwardValidator(
            config=WalkForwardConfig(n_folds=2, min_oos_trades=10),
            backtest_fn=mock_backtest_fn,
        )

        # Create results dict
        results = {
            1.10: WalkForwardResult(
                threshold_name='test',
                threshold_value=1.10,
                passed=True,
                avg_train_sharpe=1.5,
                avg_test_sharpe=1.3,
                avg_degradation=0.13,
            ),
            1.15: WalkForwardResult(
                threshold_name='test',
                threshold_value=1.15,
                passed=True,
                avg_train_sharpe=2.0,
                avg_test_sharpe=1.8,  # Best OOS
                avg_degradation=0.10,
            ),
            1.20: WalkForwardResult(
                threshold_name='test',
                threshold_value=1.20,
                passed=False,  # Failed validation
                avg_train_sharpe=1.0,
                avg_test_sharpe=0.5,
                avg_degradation=0.50,
            ),
        }

        best = validator.get_best_validated(results)
        assert best is not None
        assert best[0] == 1.15
        assert best[1].oos_sharpe == 1.8


class TestFoldResult:
    """Tests for FoldResult."""

    def test_degradation_calculation(self):
        """Test Sharpe degradation calculation."""
        fold = FoldResult(
            fold_index=0,
            train_start=datetime.now(),
            train_end=datetime.now(),
            test_start=datetime.now(),
            test_end=datetime.now(),
            train_sharpe=2.0,
            train_win_rate=0.55,
            train_n_trades=50,
            test_sharpe=1.6,
            test_win_rate=0.52,
            test_n_trades=20,
            test_total_pnl=300,
        )

        assert fold.degradation == pytest.approx(0.2)  # 20% degradation
        assert fold.is_profitable

    def test_degradation_with_negative_train(self):
        """Test degradation when training Sharpe is negative."""
        fold = FoldResult(
            fold_index=0,
            train_start=datetime.now(),
            train_end=datetime.now(),
            test_start=datetime.now(),
            test_end=datetime.now(),
            train_sharpe=-0.5,  # Negative
            train_win_rate=0.45,
            train_n_trades=50,
            test_sharpe=0.5,
            test_win_rate=0.50,
            test_n_trades=20,
            test_total_pnl=100,
        )

        assert fold.degradation == 1.0  # Max degradation

    def test_is_profitable(self):
        """Test profitability check."""
        profitable = FoldResult(
            fold_index=0,
            train_start=datetime.now(),
            train_end=datetime.now(),
            test_start=datetime.now(),
            test_end=datetime.now(),
            train_sharpe=1.0,
            train_win_rate=0.50,
            train_n_trades=50,
            test_sharpe=1.0,
            test_win_rate=0.50,
            test_n_trades=20,
            test_total_pnl=100,
        )
        assert profitable.is_profitable

        unprofitable = FoldResult(
            fold_index=0,
            train_start=datetime.now(),
            train_end=datetime.now(),
            test_start=datetime.now(),
            test_end=datetime.now(),
            train_sharpe=1.0,
            train_win_rate=0.50,
            train_n_trades=50,
            test_sharpe=-0.5,
            test_win_rate=0.40,
            test_n_trades=20,
            test_total_pnl=-100,  # Negative
        )
        assert not unprofitable.is_profitable


class TestWindowTypes:
    """Tests for walk-forward window types."""

    def test_rolling_window_generation(self):
        """Test rolling window fold generation."""
        validator = WalkForwardValidator(
            config=WalkForwardConfig(
                n_folds=3,
                train_pct=0.6,
                window_type=WindowType.ROLLING,
            ),
        )

        class MockData:
            timestamps = [
                datetime(2024, 1, 1),
                datetime(2024, 4, 1),
            ]

        folds = validator._generate_folds(MockData(), None)

        # Should generate multiple folds with rolling windows
        assert len(folds) > 0
        for train_start, train_end, test_start, test_end in folds:
            assert train_start < train_end
            assert train_end <= test_start
            assert test_start < test_end

    def test_expanding_window_generation(self):
        """Test expanding window fold generation."""
        validator = WalkForwardValidator(
            config=WalkForwardConfig(
                n_folds=3,
                train_pct=0.6,
                window_type=WindowType.EXPANDING,
            ),
        )

        data_range = (datetime(2024, 1, 1), datetime(2024, 6, 1))
        folds = validator._generate_folds(None, data_range)

        # All folds should start from same point (expanding)
        if folds:
            first_train_start = folds[0][0]
            for train_start, _, _, _ in folds:
                assert train_start == first_train_start

    def test_anchored_window_generation(self):
        """Test anchored window fold generation."""
        validator = WalkForwardValidator(
            config=WalkForwardConfig(
                n_folds=3,
                train_pct=0.6,
                window_type=WindowType.ANCHORED,
            ),
        )

        data_range = (datetime(2024, 1, 1), datetime(2024, 6, 1))
        folds = validator._generate_folds(None, data_range)

        # All folds should have same training period
        if folds:
            first_train = (folds[0][0], folds[0][1])
            for train_start, train_end, _, _ in folds:
                assert train_start == first_train[0]
                assert train_end == first_train[1]
