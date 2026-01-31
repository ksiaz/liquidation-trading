"""
HLP10: Kinematics Strategy (Post-Liq Inventory).

Trades range expansion after OI collapse.

Setup conditions:
- Recent OI collapse (>5% in <1 hour)
- Price has stabilized (<1% range for >10 minutes)
- Volume remains elevated
- Order book depth is refilling

Trigger:
- Range expansion breakout detected
- Volume confirms direction

Position:
- Enter in direction of breakout
- Hold for range expansion (typically 5-15 minutes)
- Trail stop as range expands

Named "Kinematics" because it trades the motion patterns
after liquidation events clear out overlevered positions.
"""

from .state_machine import (
    KinematicsStateMachine,
    KinematicsConfig,
    KinematicsSetup,
)

__all__ = [
    'KinematicsStateMachine',
    'KinematicsConfig',
    'KinematicsSetup',
]
