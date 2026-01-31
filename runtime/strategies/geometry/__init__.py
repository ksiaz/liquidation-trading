"""
HLP10: Geometry Strategy (Failed Hunt).

Trades failed liquidation hunts in sideways regime.

Setup conditions:
- Elevated OI (z-score > 2.0)
- Funding skewed (indicating directional bias)
- Depth asymmetry (order imbalance)
- Price near liquidation bands
- Aggressive order flow detected
- Passive cancellations increasing

Trigger:
- OI drops >5% in <10 seconds
- Order flow flips direction
- Indicates failed hunt, reversal likely

Position:
- Enter opposite to failed hunt direction
- Quick scalp (typically <1 minute hold)
- Stop above/below recent swing
"""

from .state_machine import (
    GeometryStateMachine,
    GeometryConfig,
    GeometrySetup,
)

__all__ = [
    'GeometryStateMachine',
    'GeometryConfig',
    'GeometrySetup',
]
