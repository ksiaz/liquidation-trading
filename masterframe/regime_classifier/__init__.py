"""
Regime Classifier Module

Implements global regime classification for the Market Regime Masterframe.

Regimes:
- SIDEWAYS: Low volatility, range-bound conditions
- EXPANSION: High volatility, trending/breakout conditions
- DISABLED: Neither regime qualifies or insufficient data

INVARIANTS:
- Regime is a GATE, not a signal
- ALL conditions must be met for regime activation
- NULL metrics → DISABLED
- Regime does NOT generate trades
"""

from .types import RegimeType, RegimeState, RegimeTransition
from .classifier import RegimeClassifier

__all__ = [
    "RegimeType",
    "RegimeState",
    "RegimeTransition",
    "RegimeClassifier",
]
