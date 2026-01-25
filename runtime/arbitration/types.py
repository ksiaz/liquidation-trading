"""Mandate Arbitration Types.

Implements mandate and action types per MANDATE_ARBITRATION_PROOFS.md.

Authority Hierarchy (Theorem 2.2):
  EXIT > BLOCK > REDUCE > ENTRY > HOLD
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.position.types import Direction


class MandateType(Enum):
    """Mandate types with authority hierarchy.
    
    Higher enum value = higher priority (Theorem 2.2).
    """
    EXIT = 5      # Highest: Safety (liquidation avoidance)
    BLOCK = 4     # Risk constraint violation
    REDUCE = 3    # Exposure management
    ENTRY = 2     # Opportunity
    HOLD = 1      # No change (lowest)


class ActionType(Enum):
    """Actions that can be executed on a position."""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True)
class Mandate:
    """Mandate emitted by strategy or risk layer.

    Invariants:
    - symbol must be non-empty
    - authority >= 0
    - timestamp >= 0
    """
    symbol: str
    type: MandateType
    authority: float
    timestamp: float
    expiry: Optional[Callable] = None  # Optional expiry condition
    direction: Optional[str] = None  # "LONG" or "SHORT" for ENTRY mandates
    strategy_id: Optional[str] = None  # Which strategy emitted this

    def __post_init__(self):
        """Validate mandate."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.authority < 0:
            raise ValueError(f"authority must be non-negative, got {self.authority}")
        if self.timestamp < 0:
            raise ValueError(f"timestamp must be non-negative, got {self.timestamp}")
        if self.direction is not None and self.direction not in ("LONG", "SHORT"):
            raise ValueError(f"direction must be LONG or SHORT, got {self.direction}")


@dataclass(frozen=True)
class Action:
    """Arbitrated action to execute.

    Exactly one action per symbol per cycle (Theorem 4.1).
    """
    type: ActionType
    symbol: str
    strategy_id: Optional[str] = None  # Which strategy triggered this (for tracing)
    direction: Optional[str] = None  # "LONG" or "SHORT" for ENTRY actions

    @staticmethod
    def from_mandate_type(
        mandate_type: MandateType,
        symbol: str,
        strategy_id: Optional[str] = None,
        direction: Optional[str] = None
    ) -> "Action":
        """Convert mandate type to action type."""
        mapping = {
            MandateType.ENTRY: ActionType.ENTRY,
            MandateType.EXIT: ActionType.EXIT,
            MandateType.REDUCE: ActionType.REDUCE,
            MandateType.HOLD: ActionType.HOLD,
            MandateType.BLOCK: ActionType.NO_ACTION,  # BLOCK is not actionable
        }
        return Action(
            type=mapping[mandate_type],
            symbol=symbol,
            strategy_id=strategy_id,
            direction=direction
        )

    @staticmethod
    def from_mandate(mandate: "Mandate") -> "Action":
        """Create action from mandate, preserving direction."""
        return Action.from_mandate_type(
            mandate_type=mandate.type,
            symbol=mandate.symbol,
            strategy_id=mandate.strategy_id,
            direction=mandate.direction
        )
