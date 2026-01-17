"""
Regime Classification Module

Provides deterministic market regime classification for strategy mutual exclusion.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VII (Regime Mutual Exclusion)
"""

from .types import RegimeState, RegimeMetrics
from .classifier import classify_regime

__all__ = [
    'RegimeState',
    'RegimeMetrics',
    'classify_regime'
]
