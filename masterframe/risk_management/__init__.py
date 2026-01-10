"""
Risk Management Module

Centralized risk management for Market Regime Masterframe.

RESPONSIBILITIES:
- Validate stops/targets (minimum R:R)
- Calculate position size
- Monitor exits
- Enforce one position only
- Log exit reasons

INVARIANTS:
- No scaling, pyramiding, or averaging
- Immediate exit on invalidation
- Structural stops required
"""

from .types import ExitReason, RiskParameters, Position, PositionExit
from .risk_manager import RiskManager

__all__ = [
    "ExitReason",
    "RiskParameters",
    "Position",
    "PositionExit",
    "RiskManager",
]
