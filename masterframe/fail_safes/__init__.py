"""
Fail-Safes & Cooldown Module

System fail-safes and kill-switch logic.

RESPONSIBILITIES:
- Monitor consecutive losses
- Monitor daily drawdown
- Monitor win rate
- Trigger kill-switch on violations
- Enforce manual reset

INVARIANTS:
- Hard kill requires manual reset
- Fail closed (safe = disabled)
"""

from .types import KillSwitchReason, FailSafeConfig, KillSwitchEvent
from .fail_safe_monitor import FailSafeMonitor

__all__ = [
    "KillSwitchReason",
    "FailSafeConfig",
    "KillSwitchEvent",
    "FailSafeMonitor",
]
