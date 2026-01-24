"""
HLP23 Threshold Discovery.

Systematic threshold optimization from arbitrary numbers to validated decision boundaries.

Methods:
- Grid search optimization
- ROC analysis
- Sensitivity analysis
- Out-of-sample validation

All thresholds are hypotheses until validated.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from enum import Enum, auto
import math


class DiscoveryMethod(Enum):
    """Threshold discovery method used."""
    GRID_SEARCH = auto()
    ROC_ANALYSIS = auto()
    EXPECTED_VALUE = auto()
    DOMAIN_KNOWLEDGE = auto()
    CONSERVATIVE_DEFAULT = auto()


@dataclass(frozen=True)
class ThresholdCandidate:
    """A candidate threshold value with performance metrics."""
    name: str
    value: float
    trades: int
    wins: int
    losses: int
    total_pnl: float
    sharpe_ratio: float

    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if self.trades == 0:
            return 0.0
        return self.wins / self.trades

    @property
    def avg_pnl_per_trade(self) -> float:
        """Average PnL per trade."""
        if self.trades == 0:
            return 0.0
        return self.total_pnl / self.trades

    @property
    def score(self) -> float:
        """Composite score balancing win rate, trade frequency, and Sharpe."""
        if self.trades == 0:
            return 0.0
        # Score = win_rate * sqrt(trades) * sharpe
        # Rewards: high win rate, enough trades, good risk-adjusted return
        return self.win_rate * math.sqrt(self.trades) * max(0, self.sharpe_ratio)


@dataclass(frozen=True)
class OptimizationResult:
    """Result of threshold optimization."""
    threshold_name: str
    optimal_value: float
    method: DiscoveryMethod
    in_sample_performance: ThresholdCandidate
    out_of_sample_performance: Optional[ThresholdCandidate]
    sensitivity: Dict[float, float]  # threshold -> sharpe
    all_candidates: List[ThresholdCandidate]
    degradation_pct: Optional[float]  # OOS degradation
    is_robust: bool  # True if degradation < 20%

    @property
    def status(self) -> str:
        """Human-readable status."""
        if self.out_of_sample_performance is None:
            return "IN_SAMPLE_ONLY"
        if self.is_robust:
            return "VALIDATED"
        return "OVERFITTED"


@dataclass(frozen=True)
class ROCPoint:
    """Single point on ROC curve."""
    threshold: float
    true_positive_rate: float
    false_positive_rate: float

    @property
    def youden_index(self) -> float:
        """Youden's J statistic: TPR - FPR."""
        return self.true_positive_rate - self.false_positive_rate


@dataclass
class GridSearchConfig:
    """Configuration for grid search optimization."""
    min_value: float
    max_value: float
    step: float
    min_trades: int = 20  # Minimum trades for valid result
    train_ratio: float = 0.6  # Ratio for in-sample data

    @property
    def values(self) -> List[float]:
        """Generate all threshold values in grid."""
        result = []
        current = self.min_value
        while current <= self.max_value:
            result.append(round(current, 6))
            current += self.step
        return result


class GridSearchOptimizer:
    """
    Grid search threshold optimizer.

    Tests each threshold value against historical data and selects
    the value that maximizes a scoring function.
    """

    def __init__(self, config: GridSearchConfig):
        """Initialize optimizer with configuration."""
        self._config = config

    def optimize(
        self,
        threshold_name: str,
        evaluate_fn: Callable[[float], ThresholdCandidate],
        events: List[Any],
    ) -> OptimizationResult:
        """
        Run grid search optimization.

        Args:
            threshold_name: Name of threshold being optimized
            evaluate_fn: Function that evaluates a threshold value
                         and returns ThresholdCandidate
            events: List of events to evaluate (for train/test split)

        Returns:
            OptimizationResult with optimal threshold and validation
        """
        # Split events into train/test
        split_idx = int(len(events) * self._config.train_ratio)

        # Evaluate all threshold values on in-sample data
        candidates = []
        for value in self._config.values:
            candidate = evaluate_fn(value)
            candidates.append(candidate)

        # Filter candidates with minimum trades
        valid_candidates = [
            c for c in candidates
            if c.trades >= self._config.min_trades
        ]

        if not valid_candidates:
            # No valid candidates, return best of what we have
            valid_candidates = candidates

        # Find optimal by score
        optimal = max(valid_candidates, key=lambda c: c.score)

        # Run sensitivity analysis (±10% around optimal)
        sensitivity = self._analyze_sensitivity(optimal.value, candidates)

        # Out-of-sample validation would require separate evaluation
        # For now, mark as in-sample only
        return OptimizationResult(
            threshold_name=threshold_name,
            optimal_value=optimal.value,
            method=DiscoveryMethod.GRID_SEARCH,
            in_sample_performance=optimal,
            out_of_sample_performance=None,
            sensitivity=sensitivity,
            all_candidates=candidates,
            degradation_pct=None,
            is_robust=False  # Unknown without OOS test
        )

    def _analyze_sensitivity(
        self,
        optimal_value: float,
        candidates: List[ThresholdCandidate]
    ) -> Dict[float, float]:
        """Analyze how sensitive performance is to threshold changes."""
        sensitivity = {}

        # Find candidates within ±20% of optimal
        lower = optimal_value * 0.8
        upper = optimal_value * 1.2

        for candidate in candidates:
            if lower <= candidate.value <= upper:
                sensitivity[candidate.value] = candidate.sharpe_ratio

        return sensitivity


class ROCAnalyzer:
    """
    ROC (Receiver Operating Characteristic) analysis for threshold selection.

    Finds threshold that maximizes Youden's index (TPR - FPR).
    """

    def analyze(
        self,
        threshold_name: str,
        thresholds: List[float],
        evaluate_fn: Callable[[float], Tuple[float, float]],
    ) -> Tuple[float, List[ROCPoint]]:
        """
        Perform ROC analysis.

        Args:
            threshold_name: Name of threshold
            thresholds: List of threshold values to test
            evaluate_fn: Function that returns (TPR, FPR) for a threshold

        Returns:
            Tuple of (optimal_threshold, roc_curve)
        """
        points = []

        for threshold in thresholds:
            tpr, fpr = evaluate_fn(threshold)
            points.append(ROCPoint(
                threshold=threshold,
                true_positive_rate=tpr,
                false_positive_rate=fpr
            ))

        # Find threshold with maximum Youden's index
        optimal_point = max(points, key=lambda p: p.youden_index)

        return optimal_point.threshold, points


class SensitivityAnalyzer:
    """
    Analyze threshold sensitivity to detect overfitting.

    A robust threshold should have stable performance within ±10% range.
    """

    def __init__(self, tolerance_pct: float = 0.10):
        """
        Initialize analyzer.

        Args:
            tolerance_pct: Acceptable performance degradation (default 10%)
        """
        self._tolerance_pct = tolerance_pct

    def analyze(
        self,
        optimal_value: float,
        sensitivity_map: Dict[float, float]
    ) -> Dict[str, Any]:
        """
        Analyze sensitivity of threshold.

        Args:
            optimal_value: The optimal threshold value
            sensitivity_map: Map of threshold -> sharpe ratio

        Returns:
            Analysis results with robustness assessment
        """
        if optimal_value not in sensitivity_map:
            return {
                'is_robust': False,
                'reason': 'optimal_value_not_in_map',
                'optimal_sharpe': None,
                'min_sharpe': None,
                'max_sharpe': None,
                'degradation_pct': None
            }

        optimal_sharpe = sensitivity_map[optimal_value]

        if optimal_sharpe == 0:
            return {
                'is_robust': False,
                'reason': 'zero_sharpe',
                'optimal_sharpe': optimal_sharpe,
                'min_sharpe': None,
                'max_sharpe': None,
                'degradation_pct': None
            }

        # Find min/max in ±10% range
        lower = optimal_value * 0.9
        upper = optimal_value * 1.1

        nearby_sharpes = [
            sharpe for threshold, sharpe in sensitivity_map.items()
            if lower <= threshold <= upper
        ]

        if not nearby_sharpes:
            return {
                'is_robust': False,
                'reason': 'no_nearby_values',
                'optimal_sharpe': optimal_sharpe,
                'min_sharpe': None,
                'max_sharpe': None,
                'degradation_pct': None
            }

        min_sharpe = min(nearby_sharpes)
        max_sharpe = max(nearby_sharpes)

        # Calculate max degradation
        degradation = (optimal_sharpe - min_sharpe) / optimal_sharpe

        is_robust = degradation <= self._tolerance_pct

        return {
            'is_robust': is_robust,
            'reason': 'robust' if is_robust else 'sensitive',
            'optimal_sharpe': optimal_sharpe,
            'min_sharpe': min_sharpe,
            'max_sharpe': max_sharpe,
            'degradation_pct': degradation * 100
        }


class OutOfSampleValidator:
    """
    Out-of-sample validation for threshold robustness.

    Tests threshold on data not used during optimization.
    """

    def __init__(self, max_degradation_pct: float = 0.20):
        """
        Initialize validator.

        Args:
            max_degradation_pct: Maximum acceptable degradation (default 20%)
        """
        self._max_degradation = max_degradation_pct

    def validate(
        self,
        in_sample: ThresholdCandidate,
        out_of_sample: ThresholdCandidate
    ) -> Dict[str, Any]:
        """
        Validate threshold on out-of-sample data.

        Args:
            in_sample: Performance on training data
            out_of_sample: Performance on test data

        Returns:
            Validation results with robustness assessment
        """
        if in_sample.sharpe_ratio == 0:
            degradation = 1.0 if out_of_sample.sharpe_ratio < 0 else 0.0
        else:
            degradation = (
                (in_sample.sharpe_ratio - out_of_sample.sharpe_ratio)
                / in_sample.sharpe_ratio
            )

        is_robust = degradation <= self._max_degradation

        return {
            'is_robust': is_robust,
            'in_sample_sharpe': in_sample.sharpe_ratio,
            'out_of_sample_sharpe': out_of_sample.sharpe_ratio,
            'degradation_pct': degradation * 100,
            'in_sample_trades': in_sample.trades,
            'out_of_sample_trades': out_of_sample.trades,
            'status': 'VALIDATED' if is_robust else 'OVERFITTED'
        }


class WalkForwardOptimizer:
    """
    Walk-forward optimization for adaptive thresholds.

    Simulates real-world deployment by:
    1. Optimize on window [t0, t1]
    2. Test on window [t1, t2]
    3. Re-optimize on [t1, t2]
    4. Test on [t2, t3]
    5. Repeat
    """

    def __init__(
        self,
        window_size_days: int = 60,
        step_size_days: int = 30
    ):
        """
        Initialize optimizer.

        Args:
            window_size_days: Size of optimization window
            step_size_days: Step between windows
        """
        self._window_size = window_size_days
        self._step_size = step_size_days

    def optimize(
        self,
        threshold_name: str,
        config: GridSearchConfig,
        events_by_day: Dict[int, List[Any]],  # day_offset -> events
        evaluate_fn: Callable[[float, List[Any]], ThresholdCandidate],
    ) -> List[Dict[str, Any]]:
        """
        Run walk-forward optimization.

        Args:
            threshold_name: Name of threshold
            config: Grid search configuration
            events_by_day: Events grouped by day offset
            evaluate_fn: Evaluation function

        Returns:
            List of window results
        """
        results = []

        days = sorted(events_by_day.keys())
        if len(days) < self._window_size + self._step_size:
            return results  # Not enough data

        start_day = days[0]
        end_day = days[-1]

        current_start = start_day

        while current_start + self._window_size + self._step_size <= end_day:
            # Optimization window
            opt_end = current_start + self._window_size

            # Test window
            test_end = opt_end + self._step_size

            # Collect events for each window
            opt_events = []
            test_events = []

            for day, day_events in events_by_day.items():
                if current_start <= day < opt_end:
                    opt_events.extend(day_events)
                elif opt_end <= day < test_end:
                    test_events.extend(day_events)

            # Run grid search on optimization window
            optimizer = GridSearchOptimizer(config)

            # Find best threshold
            best_candidate = None
            best_score = -float('inf')

            for value in config.values:
                candidate = evaluate_fn(value, opt_events)
                if candidate.score > best_score:
                    best_score = candidate.score
                    best_candidate = candidate

            if best_candidate is None:
                current_start += self._step_size
                continue

            # Test on out-of-sample window
            test_candidate = evaluate_fn(best_candidate.value, test_events)

            results.append({
                'window_start': current_start,
                'window_end': opt_end,
                'test_start': opt_end,
                'test_end': test_end,
                'optimal_threshold': best_candidate.value,
                'in_sample_sharpe': best_candidate.sharpe_ratio,
                'out_of_sample_sharpe': test_candidate.sharpe_ratio,
                'in_sample_trades': best_candidate.trades,
                'out_of_sample_trades': test_candidate.trades
            })

            current_start += self._step_size

        return results


def get_conservative_defaults() -> Dict[str, float]:
    """
    Get conservative default thresholds based on domain knowledge.

    These are starting points when no historical data is available.
    All values are hypotheses requiring validation.
    """
    return {
        # OI thresholds
        'oi_spike_threshold': 1.18,  # 18% increase
        'oi_collapse_threshold': 0.85,  # 15% drop
        'oi_stability_threshold': 0.05,  # ±5%

        # Funding thresholds
        'funding_skew_threshold': 0.018,  # 1.8% 8h rate
        'funding_divergence_threshold': 0.0005,  # 5bps Binance-HL spread

        # Depth thresholds
        'depth_asymmetry_threshold': 1.6,  # Bid/Ask ratio

        # Match score thresholds
        'match_score_minimum': 0.75,  # 75% conditions met
        'high_match_score': 0.85,  # High priority

        # Risk thresholds
        'daily_loss_limit': 0.03,  # 3%
        'position_size_limit': 0.05,  # 5% of capital
        'max_aggregate_exposure': 0.10,  # 10%

        # Wave thresholds (from HLP25 validation)
        'wave_count_min': 3,
        'wave_count_max': 5,
        'wave_gap_seconds': 30,

        # Absorption thresholds
        'absorption_ratio_threshold': 0.65,

        # Cascade thresholds
        'cascade_oi_drop_pct': 0.10,  # 10% OI drop
        'cascade_min_liquidations': 2,
    }


def get_phased_thresholds(phase: int) -> Dict[str, float]:
    """
    Get thresholds for phased relaxation strategy.

    Phase 1: Ultra-conservative (days 1-30)
    Phase 2: Conservative (days 31-60)
    Phase 3: Moderate (days 61-90)
    Phase 4: Use optimized thresholds

    Args:
        phase: Phase number (1-4)

    Returns:
        Threshold configuration for phase
    """
    if phase == 1:
        return {
            'oi_spike_threshold': 1.25,
            'funding_skew_threshold': 0.025,
            'match_score_minimum': 0.85,
            'depth_asymmetry_threshold': 1.8,
        }
    elif phase == 2:
        return {
            'oi_spike_threshold': 1.20,
            'funding_skew_threshold': 0.020,
            'match_score_minimum': 0.80,
            'depth_asymmetry_threshold': 1.7,
        }
    elif phase == 3:
        return {
            'oi_spike_threshold': 1.15,
            'funding_skew_threshold': 0.015,
            'match_score_minimum': 0.70,
            'depth_asymmetry_threshold': 1.5,
        }
    else:
        # Phase 4: Return defaults (should be replaced with optimized)
        return get_conservative_defaults()
