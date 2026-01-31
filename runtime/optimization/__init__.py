"""
HLP23: Optimization Package.

Provides threshold discovery and validation tools:
- Grid search for exhaustive parameter optimization
- Walk-forward validation for out-of-sample testing
- ROC analysis for binary classification thresholds

Workflow:
1. Grid search to find optimal threshold candidates
2. Walk-forward to validate out-of-sample performance
3. Sensitivity analysis to ensure stability
4. Document with full provenance
"""

from .grid_search import (
    GridSearchConfig,
    GridSearchOptimizer,
    GridSearchResult,
    ParameterGrid,
)
from .walk_forward import (
    WalkForwardConfig,
    WalkForwardValidator,
    WalkForwardResult,
    FoldResult,
)

__all__ = [
    # Grid search
    'GridSearchConfig',
    'GridSearchOptimizer',
    'GridSearchResult',
    'ParameterGrid',
    # Walk forward
    'WalkForwardConfig',
    'WalkForwardValidator',
    'WalkForwardResult',
    'FoldResult',
]
