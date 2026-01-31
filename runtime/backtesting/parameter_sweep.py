"""
HLP22: Parameter Sweep Optimization.

Parallelized parameter grid search for strategy optimization.

Features:
- Grid search across parameter combinations
- Parallel execution for efficiency
- Multiple optimization metrics
- Walk-forward validation support
- Result persistence and analysis

Usage:
    sweep = ParameterSweep(strategy, historical_data)

    config = SweepConfig(
        parameters={
            'oi_spike_threshold': [0.10, 0.15, 0.20],
            'funding_skew_threshold': [0.001, 0.0015, 0.002],
        },
        metric=OptimizationMetric.SHARPE,
    )

    result = await sweep.run(config)
    best = result.best_combination
"""

import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable, Tuple
import statistics


class OptimizationMetric(Enum):
    """Metric to optimize for."""
    SHARPE = auto()           # Sharpe ratio (risk-adjusted return)
    TOTAL_RETURN = auto()     # Total percentage return
    WIN_RATE = auto()         # Percentage of winning trades
    PROFIT_FACTOR = auto()    # Gross profit / gross loss
    MAX_DRAWDOWN = auto()     # Minimize maximum drawdown
    CALMAR = auto()           # Return / max drawdown
    COMPOSITE = auto()        # Weighted combination


@dataclass
class SweepConfig:
    """Configuration for parameter sweep."""

    # Parameters to sweep: {param_name: [values]}
    parameters: Dict[str, List[float]]

    # Optimization target
    metric: OptimizationMetric = OptimizationMetric.SHARPE

    # Composite metric weights (if using COMPOSITE)
    composite_weights: Dict[str, float] = field(default_factory=lambda: {
        'sharpe': 0.4,
        'win_rate': 0.2,
        'profit_factor': 0.2,
        'max_drawdown': 0.2,
    })

    # Execution settings
    n_workers: int = 4
    timeout_per_backtest_sec: float = 300.0

    # Minimum requirements to consider valid
    min_trades: int = 10
    min_win_rate: float = 0.0
    max_drawdown: float = 1.0  # 100%

    @property
    def total_combinations(self) -> int:
        """Total number of parameter combinations."""
        if not self.parameters:
            return 0
        counts = [len(values) for values in self.parameters.values()]
        result = 1
        for c in counts:
            result *= c
        return result


@dataclass
class BacktestMetrics:
    """Metrics from a single backtest run."""
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    calmar_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'max_drawdown': self.max_drawdown,
            'calmar_ratio': self.calmar_ratio,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
        }


@dataclass
class ParameterResult:
    """Result for a single parameter combination."""
    parameters: Dict[str, float]
    metrics: BacktestMetrics
    score: float
    is_valid: bool
    error: Optional[str] = None
    execution_time_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'parameters': self.parameters,
            'metrics': self.metrics.to_dict(),
            'score': self.score,
            'is_valid': self.is_valid,
            'error': self.error,
            'execution_time_sec': self.execution_time_sec,
        }


@dataclass
class SweepResult:
    """Complete result of parameter sweep."""
    config: SweepConfig
    results: List[ParameterResult]
    best_combination: Optional[ParameterResult]
    start_time: datetime
    end_time: datetime
    total_combinations: int
    valid_combinations: int
    failed_combinations: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_sec': (self.end_time - self.start_time).total_seconds(),
            'total_combinations': self.total_combinations,
            'valid_combinations': self.valid_combinations,
            'failed_combinations': self.failed_combinations,
            'best_parameters': self.best_combination.parameters if self.best_combination else None,
            'best_score': self.best_combination.score if self.best_combination else None,
            'best_metrics': self.best_combination.metrics.to_dict() if self.best_combination else None,
        }

    def get_top_n(self, n: int = 10) -> List[ParameterResult]:
        """Get top N results by score."""
        valid = [r for r in self.results if r.is_valid]
        return sorted(valid, key=lambda r: r.score, reverse=True)[:n]

    def get_parameter_sensitivity(self, param_name: str) -> Dict[float, float]:
        """Get average score for each value of a parameter."""
        scores_by_value: Dict[float, List[float]] = {}

        for result in self.results:
            if not result.is_valid:
                continue
            value = result.parameters.get(param_name)
            if value is not None:
                if value not in scores_by_value:
                    scores_by_value[value] = []
                scores_by_value[value].append(result.score)

        return {
            value: statistics.mean(scores)
            for value, scores in scores_by_value.items()
        }


class ParameterSweep:
    """
    Parallelized parameter grid search.

    Runs backtests for all parameter combinations and finds optimal values.
    """

    def __init__(
        self,
        backtest_fn: Callable[..., BacktestMetrics],
        logger: logging.Logger = None,
    ):
        """
        Initialize parameter sweep.

        Args:
            backtest_fn: Function that takes parameters and returns BacktestMetrics.
                        Signature: (params: Dict[str, float]) -> BacktestMetrics
            logger: Logger instance
        """
        self._backtest_fn = backtest_fn
        self._logger = logger or logging.getLogger(__name__)

    async def run(self, config: SweepConfig) -> SweepResult:
        """
        Run parameter sweep.

        Args:
            config: Sweep configuration

        Returns:
            SweepResult with all results and best combination
        """
        start_time = datetime.now()
        self._logger.info(
            f"Starting parameter sweep: {config.total_combinations} combinations"
        )

        # Generate all combinations
        param_names = list(config.parameters.keys())
        param_values = list(config.parameters.values())
        combinations = list(itertools.product(*param_values))

        # Run backtests with limited concurrency
        semaphore = asyncio.Semaphore(config.n_workers)
        results = await asyncio.gather(*[
            self._run_single(
                dict(zip(param_names, combo)),
                config,
                semaphore,
            )
            for combo in combinations
        ])

        # Find best
        valid_results = [r for r in results if r.is_valid]
        best = max(valid_results, key=lambda r: r.score) if valid_results else None

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        self._logger.info(
            f"Sweep complete in {duration:.1f}s: "
            f"{len(valid_results)}/{len(results)} valid"
        )
        if best:
            self._logger.info(f"Best score: {best.score:.4f} with {best.parameters}")

        return SweepResult(
            config=config,
            results=results,
            best_combination=best,
            start_time=start_time,
            end_time=end_time,
            total_combinations=len(results),
            valid_combinations=len(valid_results),
            failed_combinations=len(results) - len(valid_results),
        )

    async def _run_single(
        self,
        parameters: Dict[str, float],
        config: SweepConfig,
        semaphore: asyncio.Semaphore,
    ) -> ParameterResult:
        """Run a single backtest with given parameters."""
        async with semaphore:
            start = datetime.now()
            try:
                # Run backtest (may be sync or async)
                if asyncio.iscoroutinefunction(self._backtest_fn):
                    metrics = await asyncio.wait_for(
                        self._backtest_fn(parameters),
                        timeout=config.timeout_per_backtest_sec,
                    )
                else:
                    metrics = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._backtest_fn(parameters),
                    )

                # Check validity
                is_valid = self._check_validity(metrics, config)

                # Calculate score
                score = self._calculate_score(metrics, config) if is_valid else 0.0

                return ParameterResult(
                    parameters=parameters,
                    metrics=metrics,
                    score=score,
                    is_valid=is_valid,
                    execution_time_sec=(datetime.now() - start).total_seconds(),
                )

            except asyncio.TimeoutError:
                self._logger.warning(f"Timeout for parameters: {parameters}")
                return ParameterResult(
                    parameters=parameters,
                    metrics=BacktestMetrics(),
                    score=0.0,
                    is_valid=False,
                    error="Timeout",
                    execution_time_sec=config.timeout_per_backtest_sec,
                )

            except Exception as e:
                self._logger.error(f"Error for parameters {parameters}: {e}")
                return ParameterResult(
                    parameters=parameters,
                    metrics=BacktestMetrics(),
                    score=0.0,
                    is_valid=False,
                    error=str(e),
                    execution_time_sec=(datetime.now() - start).total_seconds(),
                )

    def _check_validity(self, metrics: BacktestMetrics, config: SweepConfig) -> bool:
        """Check if metrics meet minimum requirements."""
        if metrics.total_trades < config.min_trades:
            return False
        if metrics.win_rate < config.min_win_rate:
            return False
        if metrics.max_drawdown > config.max_drawdown:
            return False
        return True

    def _calculate_score(self, metrics: BacktestMetrics, config: SweepConfig) -> float:
        """Calculate optimization score for metrics."""
        metric = config.metric

        if metric == OptimizationMetric.SHARPE:
            return metrics.sharpe_ratio

        elif metric == OptimizationMetric.TOTAL_RETURN:
            return metrics.total_return

        elif metric == OptimizationMetric.WIN_RATE:
            return metrics.win_rate

        elif metric == OptimizationMetric.PROFIT_FACTOR:
            return metrics.profit_factor

        elif metric == OptimizationMetric.MAX_DRAWDOWN:
            # Lower is better, so negate
            return -metrics.max_drawdown

        elif metric == OptimizationMetric.CALMAR:
            return metrics.calmar_ratio

        elif metric == OptimizationMetric.COMPOSITE:
            return self._calculate_composite_score(metrics, config.composite_weights)

        else:
            return 0.0

    def _calculate_composite_score(
        self,
        metrics: BacktestMetrics,
        weights: Dict[str, float],
    ) -> float:
        """Calculate weighted composite score."""
        # Normalize each metric to roughly 0-1 scale
        normalized = {
            'sharpe': max(-3, min(3, metrics.sharpe_ratio)) / 3,  # Expect -3 to 3
            'win_rate': metrics.win_rate,  # Already 0-1
            'profit_factor': min(3, metrics.profit_factor) / 3,  # Cap at 3
            'max_drawdown': 1 - metrics.max_drawdown,  # Lower is better
        }

        score = 0.0
        total_weight = sum(weights.values())

        for metric_name, weight in weights.items():
            if metric_name in normalized:
                score += (weight / total_weight) * normalized[metric_name]

        return score


def calculate_metrics_from_trades(
    trades: List[Dict[str, Any]],
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """
    Calculate backtest metrics from a list of trades.

    Args:
        trades: List of trade dicts with 'pnl' field
        risk_free_rate: Annual risk-free rate for Sharpe calculation

    Returns:
        BacktestMetrics
    """
    if not trades:
        return BacktestMetrics()

    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_return = sum(pnls)
    win_rate = len(wins) / len(pnls) if pnls else 0

    # Profit factor
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Drawdown
    equity = 0
    peak = 0
    max_dd = 0
    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualized)
    if len(pnls) > 1:
        mean_return = statistics.mean(pnls)
        std_return = statistics.stdev(pnls)
        if std_return > 0:
            sharpe = (mean_return - risk_free_rate/252) / std_return
            sharpe *= (252 ** 0.5)  # Annualize
        else:
            sharpe = 0
    else:
        sharpe = 0

    # Calmar
    calmar = total_return / max_dd if max_dd > 0 else float('inf')

    return BacktestMetrics(
        total_return=total_return,
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        calmar_ratio=calmar,
        total_trades=len(pnls),
        winning_trades=len(wins),
        losing_trades=len(losses),
        avg_win=statistics.mean(wins) if wins else 0,
        avg_loss=statistics.mean(losses) if losses else 0,
        largest_win=max(wins) if wins else 0,
        largest_loss=min(losses) if losses else 0,
    )
