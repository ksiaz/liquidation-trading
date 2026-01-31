"""
HLP10: Cascade Strategy (Sniper).

Front-runs liquidation inevitability.

Setup conditions (PRE_ARMED):
- Liquidation bands detected at known price levels
- OI concentrated near those bands
- Funding pressure building

Setup conditions (ARMED):
- Liquidity thinning toward liq bands
- Order book depth dropping
- Aggressive flow increasing

Trigger:
- Initial cascade begins
- Rapid price movement toward liq bands
- Volume spike confirms momentum

Position:
- Enter with cascade direction
- Very short hold (<1 minute typically)
- Hard stop if cascade fails

Named "Cascade" because it profits from the cascading
liquidation waterfall effect.
"""

from .state_machine import (
    CascadeStateMachine,
    CascadeConfig,
    CascadeSetup,
)

__all__ = [
    'CascadeStateMachine',
    'CascadeConfig',
    'CascadeSetup',
]
