"""
Master Controller Module

Orchestrates the entire Market Regime Masterframe system.

RESPONSIBILITIES:
- Classify regime each update
- Enforce mutual exclusion (SLBRS ⊕ EFFCS)
- Route data to active strategy only
- Enforce cooldowns

INVARIANTS:
- SLBRS and EFFCS never active simultaneously
- Strategies disabled when regime = DISABLED
- Cooldown blocks all evaluations
"""

from .master_controller import MasterController

__all__ = [
    "MasterController",
]
