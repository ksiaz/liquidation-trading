"""
Derived Metrics Module

Computes all required metrics from synchronized data:
- Session-anchored VWAP
- ATR (1m, 5m, 30m)
- Rolling taker buy/sell volumes (10s, 30s)
- Liquidation Z-score (60m baseline)
- Open Interest delta

INVARIANTS:
- Fixed rolling window sizes (no adaptive sizing)
- Returns NULL until windows fully initialized
- No lookahead bias
- Deterministic calculations
- No statistical fitting
"""

from .types import DerivedMetrics
from .metrics_engine import MetricsEngine

__all__ = [
    "DerivedMetrics",
    "MetricsEngine",
]
