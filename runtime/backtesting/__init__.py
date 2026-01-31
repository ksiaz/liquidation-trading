"""
Backtesting Infrastructure Package.

Provides tools for strategy backtesting and parameter optimization:
- ParameterSweep: Parallelized parameter grid search
- DeterminismChecker: Verify backtest reproducibility
- BacktestEngine: Core backtesting simulation

HLP22 Components.
"""

from .parameter_sweep import (
    ParameterSweep,
    SweepConfig,
    SweepResult,
    ParameterResult,
    OptimizationMetric,
)

from .determinism_checker import (
    DeterminismChecker,
    DeterminismResult,
)

__all__ = [
    # Parameter Sweep
    'ParameterSweep',
    'SweepConfig',
    'SweepResult',
    'ParameterResult',
    'OptimizationMetric',
    # Determinism
    'DeterminismChecker',
    'DeterminismResult',
]
