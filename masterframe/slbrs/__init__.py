"""
SLBRS (Sideways Liquidity Block Retest Strategy) Module

Detects and classifies liquidity blocks from orderbook zones.

Block Types:
- ABSORPTION: High execution, low price impact (tradable)
- CONSUMPTION: High execution, price accepts through (non-tradable)
- SPOOF: Low execution or high cancellations (non-tradable)

INVARIANTS:
- Only ABSORPTION blocks are tradable
- ALL 4 qualification conditions must be met
- Blocks invalidated on price acceptance
"""

from .types import BlockType, LiquidityBlock
from .state_machine import SLBRSStateMachine, SLBRSState, TradeSetup, Position
from .block_detector import BlockDetector
from .block_tracker import BlockTracker

__all__ = [
    "BlockType",
    "LiquidityBlock",
    "SLBRSStateMachine",
    "SLBRSState",
    "TradeSetup",
    "Position",
    "BlockDetector",
    "BlockTracker",
]
