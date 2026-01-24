"""
Unit tests for HLP23 Threshold Discovery.

Tests grid search optimization, sensitivity analysis, and threshold storage.
"""

import pytest
from datetime import datetime, timedelta

from analysis.threshold_discovery import (
    DiscoveryMethod,
    ThresholdCandidate,
    OptimizationResult,
    ROCPoint,
    GridSearchConfig,
    GridSearchOptimizer,
    ROCAnalyzer,
    SensitivityAnalyzer,
    OutOfSampleValidator,
    get_conservative_defaults,
    get_phased_thresholds,
)
from analysis.threshold_store import (
    ThresholdStatus,
    ThresholdConfig,
    ThresholdSet,
    create_threshold_config,
    create_conservative_threshold_set,
)


class TestThresholdCandidate:
    """Tests for ThresholdCandidate dataclass."""

    def test_win_rate_calculation(self):
        """Win rate is correctly calculated."""
        candidate = ThresholdCandidate(
            name='test',
            value=1.15,
            trades=100,
            wins=60,
            losses=40,
            total_pnl=1000.0,
            sharpe_ratio=1.5
        )
        assert candidate.win_rate == 0.6

    def test_win_rate_zero_trades(self):
        """Win rate is 0 when no trades."""
        candidate = ThresholdCandidate(
            name='test',
            value=1.15,
            trades=0,
            wins=0,
            losses=0,
            total_pnl=0.0,
            sharpe_ratio=0.0
        )
        assert candidate.win_rate == 0.0

    def test_avg_pnl_calculation(self):
        """Average PnL per trade is correctly calculated."""
        candidate = ThresholdCandidate(
            name='test',
            value=1.15,
            trades=50,
            wins=30,
            losses=20,
            total_pnl=500.0,
            sharpe_ratio=1.2
        )
        assert candidate.avg_pnl_per_trade == 10.0

    def test_score_calculation(self):
        """Score balances win rate, trades, and Sharpe."""
        candidate = ThresholdCandidate(
            name='test',
            value=1.15,
            trades=100,
            wins=60,
            losses=40,
            total_pnl=1000.0,
            sharpe_ratio=1.5
        )
        # Score = win_rate * sqrt(trades) * sharpe
        # 0.6 * 10 * 1.5 = 9.0
        assert candidate.score == 9.0

    def test_score_zero_trades(self):
        """Score is 0 when no trades."""
        candidate = ThresholdCandidate(
            name='test',
            value=1.15,
            trades=0,
            wins=0,
            losses=0,
            total_pnl=0.0,
            sharpe_ratio=0.0
        )
        assert candidate.score == 0.0


class TestGridSearchConfig:
    """Tests for GridSearchConfig."""

    def test_values_generation(self):
        """Values are correctly generated from min/max/step."""
        config = GridSearchConfig(
            min_value=1.10,
            max_value=1.25,
            step=0.05
        )
        values = config.values
        assert len(values) >= 3
        assert abs(values[0] - 1.10) < 1e-6
        assert abs(values[1] - 1.15) < 1e-6
        assert abs(values[2] - 1.20) < 1e-6

    def test_default_min_trades(self):
        """Default minimum trades is 20."""
        config = GridSearchConfig(min_value=1.0, max_value=2.0, step=0.1)
        assert config.min_trades == 20

    def test_default_train_ratio(self):
        """Default train ratio is 0.6."""
        config = GridSearchConfig(min_value=1.0, max_value=2.0, step=0.1)
        assert config.train_ratio == 0.6


class TestGridSearchOptimizer:
    """Tests for GridSearchOptimizer."""

    @pytest.fixture
    def config(self):
        return GridSearchConfig(
            min_value=1.10,
            max_value=1.30,
            step=0.05,
            min_trades=5  # Lower for testing
        )

    @pytest.fixture
    def optimizer(self, config):
        return GridSearchOptimizer(config)

    def test_optimize_selects_best_score(self, optimizer):
        """Optimizer selects candidate with best score."""
        # Mock evaluate function that returns better scores for middle values
        def evaluate_fn(value):
            # Score peaks at 1.20
            distance = abs(value - 1.20)
            win_rate = 0.7 - distance
            return ThresholdCandidate(
                name='test',
                value=value,
                trades=30,
                wins=int(30 * win_rate),
                losses=int(30 * (1 - win_rate)),
                total_pnl=100.0,
                sharpe_ratio=1.5 - distance * 5
            )

        result = optimizer.optimize('test_threshold', evaluate_fn, events=[])

        assert result.threshold_name == 'test_threshold'
        assert result.method == DiscoveryMethod.GRID_SEARCH
        # Should pick 1.20 as optimal
        assert abs(result.optimal_value - 1.20) < 1e-10


class TestROCAnalyzer:
    """Tests for ROCAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return ROCAnalyzer()

    def test_roc_analysis_finds_optimal(self, analyzer):
        """ROC analysis finds threshold with best Youden's index."""
        thresholds = [1.10, 1.15, 1.20, 1.25, 1.30]

        # TPR decreases, FPR decreases as threshold increases
        def evaluate_fn(threshold):
            idx = thresholds.index(threshold)
            tpr = 0.95 - idx * 0.1  # 0.95, 0.85, 0.75, 0.65, 0.55
            fpr = 0.50 - idx * 0.12  # 0.50, 0.38, 0.26, 0.14, 0.02
            return (tpr, fpr)

        optimal, points = analyzer.analyze('test', thresholds, evaluate_fn)

        # Calculate Youden's indices
        # 1.10: 0.95 - 0.50 = 0.45
        # 1.15: 0.85 - 0.38 = 0.47
        # 1.20: 0.75 - 0.26 = 0.49
        # 1.25: 0.65 - 0.14 = 0.51 <- optimal
        # 1.30: 0.55 - 0.02 = 0.53 <- actually best
        assert abs(optimal - 1.30) < 1e-10

    def test_roc_point_youden_index(self):
        """ROCPoint correctly calculates Youden's index."""
        point = ROCPoint(threshold=1.20, true_positive_rate=0.8, false_positive_rate=0.2)
        assert abs(point.youden_index - 0.6) < 1e-10


class TestSensitivityAnalyzer:
    """Tests for SensitivityAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return SensitivityAnalyzer(tolerance_pct=0.10)

    def test_robust_threshold(self, analyzer):
        """Threshold is robust when performance stable within range."""
        # Optimal at 1.20, range is 1.08 to 1.32
        sensitivity_map = {
            1.10: 1.4,
            1.15: 1.45,
            1.18: 1.48,
            1.20: 1.5,  # optimal
            1.22: 1.48,
            1.25: 1.45,
            1.30: 1.4,
        }

        result = analyzer.analyze(1.20, sensitivity_map)

        assert result['is_robust'] is True
        assert result['optimal_sharpe'] == 1.5

    def test_sensitive_threshold(self, analyzer):
        """Threshold is sensitive when performance varies significantly."""
        sensitivity_map = {
            1.08: 0.8,
            1.10: 0.9,
            1.12: 1.0,
            1.15: 1.5,  # optimal - big spike
            1.18: 0.9,
            1.20: 0.7,
        }

        result = analyzer.analyze(1.15, sensitivity_map)

        # Performance drops more than 10% within ±10%
        assert result['is_robust'] is False


class TestOutOfSampleValidator:
    """Tests for OutOfSampleValidator."""

    @pytest.fixture
    def validator(self):
        return OutOfSampleValidator(max_degradation_pct=0.20)

    def test_robust_validation(self, validator):
        """Validation passes when degradation under 20%."""
        in_sample = ThresholdCandidate(
            name='test', value=1.15, trades=50, wins=30, losses=20,
            total_pnl=500.0, sharpe_ratio=1.5
        )
        out_of_sample = ThresholdCandidate(
            name='test', value=1.15, trades=30, wins=17, losses=13,
            total_pnl=250.0, sharpe_ratio=1.3  # 13% degradation
        )

        result = validator.validate(in_sample, out_of_sample)

        assert result['is_robust'] is True
        assert result['status'] == 'VALIDATED'

    def test_overfitted_validation(self, validator):
        """Validation fails when degradation over 20%."""
        in_sample = ThresholdCandidate(
            name='test', value=1.15, trades=50, wins=30, losses=20,
            total_pnl=500.0, sharpe_ratio=1.5
        )
        out_of_sample = ThresholdCandidate(
            name='test', value=1.15, trades=30, wins=15, losses=15,
            total_pnl=100.0, sharpe_ratio=1.0  # 33% degradation
        )

        result = validator.validate(in_sample, out_of_sample)

        assert result['is_robust'] is False
        assert result['status'] == 'OVERFITTED'


class TestThresholdConfig:
    """Tests for ThresholdConfig dataclass."""

    def test_to_dict_and_back(self):
        """Config can be serialized and deserialized."""
        config = ThresholdConfig(
            name='oi_spike_threshold',
            value=1.18,
            method=DiscoveryMethod.GRID_SEARCH,
            date_set='2026-01-24T10:00:00',
            rationale='Optimized on 90 days of data',
            sharpe_ratio=1.5,
            win_rate=0.58,
            trades_per_month=28.0,
            validation_sharpe=1.4,
            validation_degradation_pct=7.0,
            status=ThresholdStatus.VALIDATED,
            is_robust=True,
            next_review_date='2026-02-24T10:00:00'
        )

        data = config.to_dict()
        restored = ThresholdConfig.from_dict(data)

        assert restored.name == config.name
        assert restored.value == config.value
        assert restored.method == config.method
        assert restored.status == config.status
        assert restored.is_robust == config.is_robust


class TestThresholdSet:
    """Tests for ThresholdSet."""

    def test_get_threshold_value(self):
        """Can retrieve threshold value by name."""
        config = ThresholdConfig(
            name='test_threshold',
            value=1.15,
            method=DiscoveryMethod.CONSERVATIVE_DEFAULT,
            date_set='2026-01-24',
            rationale='Test',
            sharpe_ratio=0.0,
            win_rate=0.0,
            trades_per_month=0.0
        )
        threshold_set = ThresholdSet(
            strategy_name='test_strategy',
            thresholds={'test_threshold': config},
            created_at='2026-01-24'
        )

        assert threshold_set.get('test_threshold') == 1.15
        assert threshold_set.get('nonexistent') is None


class TestConservativeDefaults:
    """Tests for conservative default thresholds."""

    def test_get_conservative_defaults(self):
        """Conservative defaults contain expected thresholds."""
        defaults = get_conservative_defaults()

        assert 'oi_spike_threshold' in defaults
        assert 'funding_skew_threshold' in defaults
        assert 'match_score_minimum' in defaults
        assert 'wave_count_min' in defaults
        assert 'wave_count_max' in defaults

    def test_conservative_defaults_values(self):
        """Default values are conservative (higher thresholds)."""
        defaults = get_conservative_defaults()

        # OI spike should be substantial
        assert defaults['oi_spike_threshold'] >= 1.15

        # Match score should require high match
        assert defaults['match_score_minimum'] >= 0.70


class TestPhasedThresholds:
    """Tests for phased threshold relaxation."""

    def test_phase_1_most_conservative(self):
        """Phase 1 has most conservative thresholds."""
        phase1 = get_phased_thresholds(1)
        phase3 = get_phased_thresholds(3)

        # Phase 1 OI threshold should be higher (more conservative)
        assert phase1['oi_spike_threshold'] > phase3['oi_spike_threshold']

        # Phase 1 match score should be higher (more conservative)
        assert phase1['match_score_minimum'] > phase3['match_score_minimum']

    def test_all_phases_return_thresholds(self):
        """All phases return valid threshold dictionaries."""
        for phase in [1, 2, 3, 4]:
            thresholds = get_phased_thresholds(phase)
            assert isinstance(thresholds, dict)
            assert len(thresholds) > 0


class TestCreateThresholdConfig:
    """Tests for create_threshold_config helper."""

    def test_creates_config_with_review_date(self):
        """Config is created with review date in the future."""
        config = create_threshold_config(
            name='test',
            value=1.15,
            method=DiscoveryMethod.GRID_SEARCH,
            rationale='Test rationale',
            review_days=30
        )

        assert config.name == 'test'
        assert config.value == 1.15
        assert config.status == ThresholdStatus.HYPOTHESIS
        assert config.next_review_date is not None

        # Review date should be ~30 days from now
        review_date = datetime.fromisoformat(config.next_review_date)
        now = datetime.now()
        days_diff = (review_date - now).days
        assert 29 <= days_diff <= 31


class TestCreateConservativeThresholdSet:
    """Tests for create_conservative_threshold_set helper."""

    def test_creates_complete_set(self):
        """Creates a complete threshold set with all defaults."""
        threshold_set = create_conservative_threshold_set('test_strategy')

        assert threshold_set.strategy_name == 'test_strategy'
        assert len(threshold_set.thresholds) > 10  # Should have many thresholds

        # All should be marked as hypothesis
        for config in threshold_set.thresholds.values():
            assert config.status == ThresholdStatus.HYPOTHESIS
            assert config.method == DiscoveryMethod.CONSERVATIVE_DEFAULT
