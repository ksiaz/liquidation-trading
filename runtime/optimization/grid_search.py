"""
HLP23: Grid Search Optimizer.

Exhaustive parameter search for threshold discovery.

Features:
- Parallel evaluation of parameter combinations
- Multiple optimization metrics (Sharpe, win rate, profit factor)
- Early stopping for poor performers
- Result caching for incremental optimization

Usage:
    optimizer = GridSearchOptimizer(config)

    grid = ParameterGrid(
        param_name='oi.spike_ratio',
        min_value=1.05,
        max_value=1.30,
        step=0.01,
    )

    result = await optimizer.run_grid_search(grid, historical_data)
    print(f"Optimal: {result.optimal_value} (Sharpe: {result.optimal_sharpe})")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum, auto
import numpy as np


class OptimizationMetric(Enum):
    """Metrics for optimization."""
    SHARPE = auto()
    WIN_RATE = auto()
    PROFIT_FACTOR = auto()
    SORTINO = auto()
    CALMAR = auto()
    COMBINED = auto()  # Weighted combination


@dataclass
class ParameterGrid:
    """Definition of parameter search space."""
    param_name: str
    min_value: float
    max_value: float
    step: float
    log_scale: bool = False  # Use logarithmic spacing

    def get_values(self) -> List[float]:
        """Generate list of values to test."""
        if self.log_scale:
            # Logarithmic spacing for parameters like ratios
            log_min = np.log10(self.min_value)
            log_max = np.log10(self.max_value)
            n_steps = int((log_max - log_min) / self.step) + 1
            return list(np.logspace(log_min, log_max, n_steps))
        else:
            # Linear spacing
            return list(np.arange(
                self.min_value,
                self.max_value + self.step / 2,  # Include endpoint
                self.step
            ))


@dataclass
class BacktestResult:
    """Result of backtesting with a specific parameter value."""
    param_value: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    n_trades: int
    total_pnl: float
    avg_trade_pnl: float
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0


@dataclass
class GridSearchConfig:
    """Configuration for grid search."""
    # Optimization target
    metric: OptimizationMetric = OptimizationMetric.SHARPE

    # Combined metric weights (if COMBINED)
    sharpe_weight: float = 0.4
    win_rate_weight: float = 0.2
    profit_factor_weight: float = 0.2
    drawdown_weight: float = 0.2

    # Filtering
    min_trades: int = 30              # Minimum trades for validity
    max_drawdown_limit: float = 0.30  # Skip if drawdown > 30%

    # Early stopping
    early_stop_threshold: float = 0.0  # Stop if metric below this

    # Parallelization
    max_workers: int = 4

    # Caching
    cache_results: bool = True


@dataclass
class GridSearchResult:
    """Result of grid search optimization."""
    param_name: str
    optimal_value: float
    optimal_sharpe: float
    optimal_win_rate: float
    optimal_profit_factor: float
    optimal_n_trades: int

    # All tested values
    all_results: List[BacktestResult] = field(default_factory=list)

    # Metadata
    search_time_sec: float = 0.0
    values_tested: int = 0
    values_valid: int = 0  # Met minimum trade requirement

    def get_top_n(self, n: int = 5, metric: str = 'sharpe_ratio') -> List[BacktestResult]:
        """Get top N results by specified metric."""
        sorted_results = sorted(
            self.all_results,
            key=lambda x: getattr(x, metric),
            reverse=True
        )
        return sorted_results[:n]

    def get_percentile_value(self, percentile: float) -> float:
        """Get parameter value at given percentile of performance."""
        if not self.all_results:
            return self.optimal_value

        sorted_results = sorted(
            self.all_results,
            key=lambda x: x.sharpe_ratio
        )
        idx = int(len(sorted_results) * percentile / 100)
        return sorted_results[idx].param_value


class GridSearchOptimizer:
    """
    Grid search optimizer for threshold discovery.

    Exhaustively tests all parameter values in the grid
    and finds the optimal value based on specified metric.
    """

    def __init__(
        self,
        config: GridSearchConfig = None,
        backtest_fn: Callable = None,
        logger: logging.Logger = None
    ):
        """
        Initialize optimizer.

        Args:
            config: Search configuration
            backtest_fn: Async function (param_name, param_value, data) -> BacktestResult
            logger: Logger instance
        """
        self._config = config or GridSearchConfig()
        self._backtest_fn = backtest_fn
        self._logger = logger or logging.getLogger(__name__)

        # Results cache
        self._cache: Dict[Tuple[str, float], BacktestResult] = {}

    def set_backtest_function(self, fn: Callable):
        """Set the backtest function."""
        self._backtest_fn = fn

    async def run_grid_search(
        self,
        grid: ParameterGrid,
        data: Any,
    ) -> GridSearchResult:
        """
        Run grid search over parameter space.

        Args:
            grid: Parameter grid definition
            data: Historical data for backtesting

        Returns:
            GridSearchResult with optimal value and all results
        """
        if self._backtest_fn is None:
            raise ValueError("Backtest function not set")

        start_time = time.time()
        values = grid.get_values()
        results: List[BacktestResult] = []

        self._logger.info(
            f"Starting grid search for {grid.param_name}: "
            f"{len(values)} values from {grid.min_value} to {grid.max_value}"
        )

        # Run backtests (can be parallelized)
        for i, value in enumerate(values):
            # Check cache
            cache_key = (grid.param_name, value)
            if self._config.cache_results and cache_key in self._cache:
                result = self._cache[cache_key]
            else:
                try:
                    result = await self._backtest_fn(grid.param_name, value, data)
                    if self._config.cache_results:
                        self._cache[cache_key] = result
                except Exception as e:
                    self._logger.warning(f"Backtest failed for {value}: {e}")
                    continue

            results.append(result)

            # Progress logging
            if (i + 1) % 10 == 0:
                self._logger.debug(f"Progress: {i + 1}/{len(values)}")

            # Early stopping check
            if len(results) >= 5:  # Need some samples first
                best_so_far = max(r.sharpe_ratio for r in results)
                if best_so_far < self._config.early_stop_threshold:
                    self._logger.warning(
                        f"Early stopping: best Sharpe {best_so_far:.2f} "
                        f"below threshold {self._config.early_stop_threshold}"
                    )
                    break

        # Filter valid results
        valid_results = [
            r for r in results
            if r.n_trades >= self._config.min_trades
            and r.max_drawdown <= self._config.max_drawdown_limit
        ]

        if not valid_results:
            self._logger.error("No valid results found in grid search")
            return GridSearchResult(
                param_name=grid.param_name,
                optimal_value=grid.min_value,
                optimal_sharpe=0.0,
                optimal_win_rate=0.0,
                optimal_profit_factor=0.0,
                optimal_n_trades=0,
                all_results=results,
                search_time_sec=time.time() - start_time,
                values_tested=len(results),
                values_valid=0,
            )

        # Find optimal based on metric
        optimal = self._find_optimal(valid_results)

        search_time = time.time() - start_time
        self._logger.info(
            f"Grid search complete: optimal {grid.param_name}={optimal.param_value:.4f} "
            f"(Sharpe: {optimal.sharpe_ratio:.2f}, trades: {optimal.n_trades}) "
            f"in {search_time:.1f}s"
        )

        return GridSearchResult(
            param_name=grid.param_name,
            optimal_value=optimal.param_value,
            optimal_sharpe=optimal.sharpe_ratio,
            optimal_win_rate=optimal.win_rate,
            optimal_profit_factor=optimal.profit_factor,
            optimal_n_trades=optimal.n_trades,
            all_results=results,
            search_time_sec=search_time,
            values_tested=len(results),
            values_valid=len(valid_results),
        )

    def _find_optimal(self, results: List[BacktestResult]) -> BacktestResult:
        """Find optimal result based on configured metric."""
        if self._config.metric == OptimizationMetric.SHARPE:
            return max(results, key=lambda r: r.sharpe_ratio)

        elif self._config.metric == OptimizationMetric.WIN_RATE:
            return max(results, key=lambda r: r.win_rate)

        elif self._config.metric == OptimizationMetric.PROFIT_FACTOR:
            return max(results, key=lambda r: r.profit_factor)

        elif self._config.metric == OptimizationMetric.SORTINO:
            return max(results, key=lambda r: r.sortino_ratio)

        elif self._config.metric == OptimizationMetric.CALMAR:
            return max(results, key=lambda r: r.calmar_ratio)

        elif self._config.metric == OptimizationMetric.COMBINED:
            # Normalize metrics and combine
            def score(r: BacktestResult) -> float:
                # Normalize each metric to [0, 1] range
                max_sharpe = max(x.sharpe_ratio for x in results) or 1
                max_pf = max(x.profit_factor for x in results) or 1
                min_dd = min(x.max_drawdown for x in results) or 0.01

                sharpe_norm = r.sharpe_ratio / max_sharpe
                wr_norm = r.win_rate
                pf_norm = r.profit_factor / max_pf
                dd_norm = 1 - (r.max_drawdown / (max(x.max_drawdown for x in results) or 1))

                return (
                    self._config.sharpe_weight * sharpe_norm +
                    self._config.win_rate_weight * wr_norm +
                    self._config.profit_factor_weight * pf_norm +
                    self._config.drawdown_weight * dd_norm
                )

            return max(results, key=score)

        else:
            return max(results, key=lambda r: r.sharpe_ratio)

    async def run_sensitivity_analysis(
        self,
        param_name: str,
        base_value: float,
        data: Any,
        change_pcts: List[float] = None,
    ) -> Dict[str, BacktestResult]:
        """
        Run sensitivity analysis around a value.

        Tests ±10%, ±20% etc. to see how stable the threshold is.

        Args:
            param_name: Parameter to test
            base_value: Base value to test around
            data: Historical data
            change_pcts: List of change percentages to test (default: ±5%, ±10%, ±20%)

        Returns:
            Dict mapping change description to backtest result
        """
        if change_pcts is None:
            change_pcts = [-20, -10, -5, 5, 10, 20]

        results = {}

        # Base case
        base_result = await self._backtest_fn(param_name, base_value, data)
        results['base'] = base_result

        # Test each change
        for pct in change_pcts:
            test_value = base_value * (1 + pct / 100)
            try:
                result = await self._backtest_fn(param_name, test_value, data)
                key = f"{'+' if pct > 0 else ''}{pct}%"
                results[key] = result
            except Exception as e:
                self._logger.warning(f"Sensitivity test failed for {pct}%: {e}")

        return results

    def clear_cache(self):
        """Clear the results cache."""
        self._cache.clear()
