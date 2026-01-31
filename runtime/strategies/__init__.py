"""
HLP10: Strategy State Machines Package.

Provides deterministic state machine implementations for each strategy:
- Geometry (Failed Hunt): Trade failed liquidation hunts in sideways regime
- Kinematics (Post-Liq Inventory): Trade range expansion after OI collapse
- Cascade (Sniper): Front-run liquidation inevitability

Each strategy follows a strict state machine pattern:
DISABLED -> SCANNING -> [PRE_ARMED] -> ARMED -> ENTERED -> EXITED -> COOLDOWN

State transitions are:
- Deterministic: Same inputs produce same outputs
- Atomic: No partial transitions
- Logged: Every transition is recorded
- Validated: Invalid transitions are rejected
"""

from .base import (
    StrategyState,
    StrategyStateMachine,
    StrategyConfig,
    StrategySetup,
    Mandate,
    MandateType,
)

__all__ = [
    'StrategyState',
    'StrategyStateMachine',
    'StrategyConfig',
    'StrategySetup',
    'Mandate',
    'MandateType',
]
