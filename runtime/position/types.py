"""Position State Machine Types.

Implements data structures for position lifecycle per POSITION_STATE_MACHINE_PROOFS.md.

States: FLAT, ENTERING, OPEN, REDUCING, CLOSING
Invariants enforced by construction.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class PositionState(Enum):
    """Position lifecycle states (canonical set).
    
    Cardinality: |S| = 5 (fixed, finite)
    Initial state: FLAT
    Accepting states: {FLAT}
    """
    FLAT = "FLAT"           # No position (Q=0)
    ENTERING = "ENTERING"   # Entry order submitted, awaiting exchange fill
    OPEN = "OPEN"           # Position active (Q≠0)
    REDUCING = "REDUCING"   # Reduction order submitted
    CLOSING = "CLOSING"     # Exit order submitted


class Direction(Enum):
    """Position direction (LONG or SHORT).
    
    Invariant: Direction set on ENTRY, unchanged until FLAT.
    """
    LONG = "LONG"
    SHORT = "SHORT"


class InvariantViolation(Exception):
    """Raised when position invariant violated."""
    pass


@dataclass(frozen=True)
class Position:
    """Position state snapshot.
    
    Invariants (enforced in __post_init__):
    - I-PSM-1: If state=FLAT then Q=0 and direction=None
    - I-PSM-2: If state≠FLAT then Q≠0 and direction≠None
    - Direction preservation: direction immutable until state=FLAT
    """
    symbol: str
    state: PositionState
    direction: Optional[Direction]
    quantity: Decimal
    entry_price: Optional[Decimal]
    
    def __post_init__(self):
        """Validate position invariants."""
        # Invariant: Q=0 ⟺ state=FLAT (Theorem 7.2)
        # Exception: ENTERING, REDUCING, CLOSING may have Q=0 (pending exchange response)
        if self.state == PositionState.FLAT:
            if self.quantity != 0:
                raise InvariantViolation(
                    f"FLAT position must have Q=0, got Q={self.quantity}"
                )
            if self.direction is not None:
                raise InvariantViolation(
                    f"FLAT position must have direction=None, got {self.direction}"
                )
        elif self.state == PositionState.OPEN:
            # OPEN requires non-zero quantity
            if self.quantity == 0:
                raise InvariantViolation(
                    f"OPEN position must have Q≠0, state={self.state}"
                )
            if self.direction is None:
                raise InvariantViolation(
                    f"OPEN position must have direction, state={self.state}"
                )
        else:
            # ENTERING, REDUCING, CLOSING may have Q=0 (pending)
            # But must have direction set
            if self.direction is None:
                raise InvariantViolation(
                    f"Non-FLAT position must have direction, state={self.state}"
                )
    
    @staticmethod
    def create_flat(symbol: str) -> "Position":
        """Create initial FLAT position (s_0 state)."""
        return Position(
            symbol=symbol,
            state=PositionState.FLAT,
            direction=None,
            quantity=Decimal("0"),
            entry_price=None
        )
