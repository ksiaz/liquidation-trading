"""
EFFCS (Expansion & Forced Flow Continuation Strategy) Module

Momentum continuation strategy for EXPANSION regimes.

Philosophy:
- Trade WITH the flow, never against it
- Impulse move shows commitment
- Shallow pullback = continuation
- Enter on flow resumption

INVARIANTS:
- Active ONLY in EXPANSION regime
- Never fade price direction
- Single entry per impulse
"""

from .types import EFFCSState, ImpulseDirection, Impulse, Pullback, EFFCSSetup
from .state_machine import EFFCSStateMachine

__all__ = [
    "EFFCSState",
    "ImpulseDirection",
    "Impulse",
    "Pullback",
    "EFFCSSetup",
    "EFFCSStateMachine",
]
