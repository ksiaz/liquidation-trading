"""
Fail-Safe Type Definitions

Data structures for fail-safe monitoring.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class KillSwitchReason(Enum):
    """
    Reasons for kill-switch activation.
    
    All triggers result in hard kill.
    """
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    DAILY_DRAWDOWN = "DAILY_DRAWDOWN"
    LOW_WIN_RATE = "LOW_WIN_RATE"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class FailSafeConfig:
    """
    Fail-safe configuration.
    
    INVARIANT: Immutable configuration.
    """
    max_consecutive_losses: int = 2
    max_daily_drawdown_pct: float = 5.0  # 5%
    min_win_rate_pct: float = 35.0  # 35%
    win_rate_sample_size: int = 20
    cooldown_seconds: float = 300.0  # 5 minutes


@dataclass
class KillSwitchEvent:
    """
    Kill-switch activation record.
    
    Logged for analysis.
    """
    reason: KillSwitchReason
    timestamp: float
    details: str
    
    def get_summary(self) -> str:
        """Get human-readable summary."""
        return f"KILL SWITCH: {self.reason.value} - {self.details}"
