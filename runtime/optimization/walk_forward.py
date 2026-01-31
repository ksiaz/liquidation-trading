"""
HLP23: Walk-Forward Validation.

Out-of-sample validation for threshold discovery.

Walk-forward process:
1. Split data into multiple folds (train/test)
2. Optimize on training set
3. Validate on test set (out-of-sample)
4. Measure degradation from train to test
5. Accept if degradation < threshold (typically 20%)

Features:
- Multiple fold validation (like k-fold cross-validation)
- Expanding window option (accumulate training data)
- Anchored vs rolling windows
- Degradation analysis across folds

Usage:
    validator = WalkForwardValidator(config)

    result = validator.validate(
        threshold_name='oi.spike_ratio',
        threshold_value=1.15,
        data=historical_data,
    )

    if result.passed:
        print(f"Validated! OOS Sharpe: {result.oos_sharpe}")
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime
from enum import Enum, auto
import numpy as np


class WindowType(Enum):
    """Type of walk-forward window."""
    ROLLING = auto()    # Fixed-size training window that rolls forward
    EXPANDING = auto()  # Training window expands over time
    ANCHORED = auto()   # Training always starts from same point


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""
    # Data split
    train_pct: float = 0.6           # 60% training
    n_folds: int = 5                 # Number of validation folds
    window_type: WindowType = WindowType.ROLLING

    # Validation criteria
    max_degradation: float = 0.20    # Max 20% Sharpe degradation
    min_oos_sharpe: float = 0.5      # Minimum OOS Sharpe
    min_oos_trades: int = 20         # Minimum trades in OOS period

    # Robustness checks
    require_profitable_folds: float = 0.6  # 60% of folds must be profitable
    require_positive_oos: bool = True       # OOS Sharpe must be > 0


@dataclass
class FoldResult:
    """Result of a single validation fold."""
    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    # Training metrics
    train_sharpe: float
    train_win_rate: float
    train_n_trades: int

    # Test (OOS) metrics
    test_sharpe: float
    test_win_rate: float
    test_n_trades: int
    test_total_pnl: float

    @property
    def degradation(self) -> float:
        """Calculate Sharpe degradation from train to test."""
        if self.train_sharpe <= 0:
            return 1.0
        return (self.train_sharpe - self.test_sharpe) / self.train_sharpe

    @property
    def is_profitable(self) -> bool:
        """Check if test period was profitable."""
        return self.test_total_pnl > 0


@dataclass
class WalkForwardResult:
    """Result of complete walk-forward validation."""
    threshold_name: str
    threshold_value: float
    passed: bool

    # Aggregate metrics
    avg_train_sharpe: float
    avg_test_sharpe: float
    avg_degradation: float

    # Per-fold results
    fold_results: List[FoldResult] = field(default_factory=list)

    # Robustness
    profitable_folds: int = 0
    total_folds: int = 0

    # Validation details
    failure_reasons: List[str] = field(default_factory=list)

    @property
    def oos_sharpe(self) -> float:
        """Alias for avg_test_sharpe (out-of-sample)."""
        return self.avg_test_sharpe

    @property
    def profitable_fold_ratio(self) -> float:
        """Ratio of profitable folds."""
        if self.total_folds == 0:
            return 0.0
        return self.profitable_folds / self.total_folds


class WalkForwardValidator:
    """
    Walk-forward validator for threshold discovery.

    Validates that a threshold performs well out-of-sample
    by testing across multiple time periods.
    """

    def __init__(
        self,
        config: WalkForwardConfig = None,
        backtest_fn: Callable = None,
        logger: logging.Logger = None
    ):
        """
        Initialize validator.

        Args:
            config: Validation configuration
            backtest_fn: Async function (param_name, param_value, data, start, end) -> FoldMetrics
            logger: Logger instance
        """
        self._config = config or WalkForwardConfig()
        self._backtest_fn = backtest_fn
        self._logger = logger or logging.getLogger(__name__)

    def set_backtest_function(self, fn: Callable):
        """Set the backtest function."""
        self._backtest_fn = fn

    async def validate(
        self,
        threshold_name: str,
        threshold_value: float,
        data: Any,
        data_range: Tuple[datetime, datetime] = None,
    ) -> WalkForwardResult:
        """
        Validate threshold with walk-forward analysis.

        Args:
            threshold_name: Name of threshold being validated
            threshold_value: Value to validate
            data: Historical data
            data_range: Optional (start, end) datetime tuple

        Returns:
            WalkForwardResult with validation outcome
        """
        if self._backtest_fn is None:
            raise ValueError("Backtest function not set")

        self._logger.info(
            f"Starting walk-forward validation for {threshold_name}={threshold_value}"
        )

        # Generate fold boundaries
        folds = self._generate_folds(data, data_range)

        fold_results: List[FoldResult] = []
        failure_reasons: List[str] = []

        # Run each fold
        for i, (train_start, train_end, test_start, test_end) in enumerate(folds):
            try:
                # Backtest on training period
                train_metrics = await self._backtest_fn(
                    threshold_name, threshold_value, data, train_start, train_end
                )

                # Backtest on test period
                test_metrics = await self._backtest_fn(
                    threshold_name, threshold_value, data, test_start, test_end
                )

                fold_result = FoldResult(
                    fold_index=i,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_sharpe=train_metrics.get('sharpe', 0),
                    train_win_rate=train_metrics.get('win_rate', 0),
                    train_n_trades=train_metrics.get('n_trades', 0),
                    test_sharpe=test_metrics.get('sharpe', 0),
                    test_win_rate=test_metrics.get('win_rate', 0),
                    test_n_trades=test_metrics.get('n_trades', 0),
                    test_total_pnl=test_metrics.get('total_pnl', 0),
                )

                fold_results.append(fold_result)

                self._logger.debug(
                    f"Fold {i}: train_sharpe={fold_result.train_sharpe:.2f}, "
                    f"test_sharpe={fold_result.test_sharpe:.2f}, "
                    f"degradation={fold_result.degradation:.1%}"
                )

            except Exception as e:
                self._logger.warning(f"Fold {i} failed: {e}")
                failure_reasons.append(f"Fold {i} error: {str(e)}")

        if not fold_results:
            return WalkForwardResult(
                threshold_name=threshold_name,
                threshold_value=threshold_value,
                passed=False,
                avg_train_sharpe=0,
                avg_test_sharpe=0,
                avg_degradation=1.0,
                fold_results=[],
                failure_reasons=["All folds failed"],
            )

        # Calculate aggregate metrics
        avg_train_sharpe = np.mean([f.train_sharpe for f in fold_results])
        avg_test_sharpe = np.mean([f.test_sharpe for f in fold_results])
        avg_degradation = np.mean([f.degradation for f in fold_results])
        profitable_folds = sum(1 for f in fold_results if f.is_profitable)

        # Check validation criteria
        passed = True

        # Check degradation
        if avg_degradation > self._config.max_degradation:
            passed = False
            failure_reasons.append(
                f"Degradation {avg_degradation:.1%} > {self._config.max_degradation:.1%}"
            )

        # Check OOS Sharpe
        if avg_test_sharpe < self._config.min_oos_sharpe:
            passed = False
            failure_reasons.append(
                f"OOS Sharpe {avg_test_sharpe:.2f} < {self._config.min_oos_sharpe:.2f}"
            )

        # Check positive OOS
        if self._config.require_positive_oos and avg_test_sharpe <= 0:
            passed = False
            failure_reasons.append("OOS Sharpe not positive")

        # Check profitable folds ratio
        profitable_ratio = profitable_folds / len(fold_results)
        if profitable_ratio < self._config.require_profitable_folds:
            passed = False
            failure_reasons.append(
                f"Profitable folds {profitable_ratio:.1%} < "
                f"{self._config.require_profitable_folds:.1%}"
            )

        # Check minimum OOS trades across folds
        total_oos_trades = sum(f.test_n_trades for f in fold_results)
        if total_oos_trades < self._config.min_oos_trades * len(fold_results):
            passed = False
            failure_reasons.append(
                f"Insufficient OOS trades: {total_oos_trades}"
            )

        result = WalkForwardResult(
            threshold_name=threshold_name,
            threshold_value=threshold_value,
            passed=passed,
            avg_train_sharpe=avg_train_sharpe,
            avg_test_sharpe=avg_test_sharpe,
            avg_degradation=avg_degradation,
            fold_results=fold_results,
            profitable_folds=profitable_folds,
            total_folds=len(fold_results),
            failure_reasons=failure_reasons,
        )

        if passed:
            self._logger.info(
                f"Walk-forward PASSED: OOS Sharpe={avg_test_sharpe:.2f}, "
                f"degradation={avg_degradation:.1%}"
            )
        else:
            self._logger.warning(
                f"Walk-forward FAILED: {', '.join(failure_reasons)}"
            )

        return result

    def _generate_folds(
        self,
        data: Any,
        data_range: Tuple[datetime, datetime] = None
    ) -> List[Tuple[datetime, datetime, datetime, datetime]]:
        """
        Generate train/test fold boundaries.

        Returns list of (train_start, train_end, test_start, test_end) tuples.
        """
        # If data has timestamp info, extract range
        if data_range:
            start, end = data_range
        elif hasattr(data, 'index') and len(data) > 0:
            # Pandas DataFrame with datetime index
            start = data.index.min()
            end = data.index.max()
        elif hasattr(data, 'timestamps') and len(data.timestamps) > 0:
            start = min(data.timestamps)
            end = max(data.timestamps)
        else:
            # Default: assume 90 days of data
            end = datetime.now()
            start = datetime(end.year, end.month - 3, end.day)

        total_duration = (end - start).total_seconds()

        folds = []

        if self._config.window_type == WindowType.ROLLING:
            # Fixed-size windows that roll forward
            fold_size = total_duration / (self._config.n_folds + self._config.train_pct)
            train_size = fold_size * self._config.train_pct / (1 - self._config.train_pct)
            test_size = fold_size

            for i in range(self._config.n_folds):
                train_start = datetime.fromtimestamp(
                    start.timestamp() + i * test_size
                )
                train_end = datetime.fromtimestamp(
                    train_start.timestamp() + train_size
                )
                test_start = train_end
                test_end = datetime.fromtimestamp(
                    test_start.timestamp() + test_size
                )

                if test_end.timestamp() <= end.timestamp():
                    folds.append((train_start, train_end, test_start, test_end))

        elif self._config.window_type == WindowType.EXPANDING:
            # Training window expands, test window stays same size
            test_size = total_duration * (1 - self._config.train_pct) / self._config.n_folds

            for i in range(self._config.n_folds):
                train_start = start
                train_end = datetime.fromtimestamp(
                    start.timestamp() + total_duration * self._config.train_pct + i * test_size
                )
                test_start = train_end
                test_end = datetime.fromtimestamp(
                    test_start.timestamp() + test_size
                )

                if test_end.timestamp() <= end.timestamp():
                    folds.append((train_start, train_end, test_start, test_end))

        elif self._config.window_type == WindowType.ANCHORED:
            # Training always starts from beginning
            train_size = total_duration * self._config.train_pct
            test_size = (total_duration - train_size) / self._config.n_folds

            train_end = datetime.fromtimestamp(start.timestamp() + train_size)

            for i in range(self._config.n_folds):
                test_start = datetime.fromtimestamp(
                    train_end.timestamp() + i * test_size
                )
                test_end = datetime.fromtimestamp(
                    test_start.timestamp() + test_size
                )

                if test_end.timestamp() <= end.timestamp():
                    folds.append((start, train_end, test_start, test_end))

        return folds

    async def validate_multiple(
        self,
        threshold_name: str,
        values: List[float],
        data: Any,
    ) -> Dict[float, WalkForwardResult]:
        """
        Validate multiple threshold values.

        Useful for comparing grid search candidates.

        Args:
            threshold_name: Name of threshold
            values: List of values to validate
            data: Historical data

        Returns:
            Dict mapping value to validation result
        """
        results = {}

        for value in values:
            result = await self.validate(threshold_name, value, data)
            results[value] = result

            self._logger.info(
                f"{threshold_name}={value}: "
                f"{'PASSED' if result.passed else 'FAILED'} "
                f"(OOS Sharpe: {result.oos_sharpe:.2f})"
            )

        return results

    def get_best_validated(
        self,
        results: Dict[float, WalkForwardResult]
    ) -> Optional[Tuple[float, WalkForwardResult]]:
        """
        Get best validated threshold from results.

        Args:
            results: Dict from validate_multiple

        Returns:
            (value, result) tuple for best validated threshold, or None
        """
        validated = {
            v: r for v, r in results.items()
            if r.passed
        }

        if not validated:
            return None

        # Sort by OOS Sharpe
        best_value = max(validated.keys(), key=lambda v: validated[v].oos_sharpe)
        return (best_value, validated[best_value])
