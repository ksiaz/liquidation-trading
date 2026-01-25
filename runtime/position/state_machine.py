"""Position State Machine.

Implements deterministic position lifecycle per POSITION_STATE_MACHINE_PROOFS.md.

Enforces:
- 13 proven theorems
- 8 allowed transitions
- 17 forbidden transitions (rejected)
- Single-position invariant
- Direction preservation
"""

from decimal import Decimal
from typing import Dict, Optional, TYPE_CHECKING

from .types import Position, PositionState, Direction, InvariantViolation

if TYPE_CHECKING:
    from .repository import PositionRepository


class Action(str):
    """Actions that trigger state transitions."""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    HOLD = "HOLD"


class PositionStateMachine:
    """Manages position lifecycle for all symbols.

    Invariants:
    - One position per symbol (dict uniqueness - Theorem 3.1)
    - Deterministic transitions (Theorem 2.1)
    - All paths lead to FLAT (Theorem 6.1)

    Supports optional persistence via PositionRepository.
    """

    # Allowed transitions (Theorem 2.1, Section 1.2)
    ALLOWED_TRANSITIONS = {
        (PositionState.FLAT, Action.ENTRY): PositionState.ENTERING,
        (PositionState.ENTERING, "SUCCESS"): PositionState.OPEN,
        (PositionState.ENTERING, "FAILURE"): PositionState.FLAT,
        (PositionState.OPEN, Action.REDUCE): PositionState.REDUCING,
        (PositionState.OPEN, Action.EXIT): PositionState.CLOSING,
        (PositionState.REDUCING, "COMPLETE"): PositionState.CLOSING,
        (PositionState.REDUCING, "PARTIAL"): PositionState.OPEN,
        (PositionState.CLOSING, "SUCCESS"): PositionState.FLAT,
    }

    def __init__(self, repository: Optional["PositionRepository"] = None):
        """Initialize state machine.

        Args:
            repository: Optional persistence layer. If provided, positions
                       are loaded on init and saved on every transition.
        """
        self._positions: Dict[str, Position] = {}
        self._repository = repository

        # Load existing positions if repository provided
        if self._repository:
            self._positions = self._repository.load_non_flat_positions()
    
    def get_position(self, symbol: str) -> Position:
        """Get position for symbol (creates FLAT if not exists)."""
        if symbol not in self._positions:
            self._positions[symbol] = Position.create_flat(symbol)
        return self._positions[symbol]
    
    def validate_entry(self, symbol: str) -> bool:
        """Validate ENTRY action (Theorem 3.1 - single position invariant).
        
        Returns:
            True if ENTRY allowed, False otherwise
        """
        position = self.get_position(symbol)
        if position.state != PositionState.FLAT:
            return False  # Reject: position already exists
        return True
    
    def validate_direction_preserved(
        self, 
        current_direction: Direction, 
        new_direction: Direction
    ) -> bool:
        """Validate direction unchanged (Theorem 4.1).
        
        Returns:
            True if direction preserved, False if violated
        """
        return current_direction == new_direction
    
    def transition(
        self, 
        symbol: str, 
        action: str, 
        **kwargs
    ) -> Position:
        """Execute state transition (deterministic - Theorem 2.1).
        
        Args:
            symbol: Symbol to transition
            action: Action triggering transition
            kwargs: Additional data (direction, quantity, price)
        
        Returns:
            New position state
            
        Raises:
            InvariantViolation: If transition invalid or invariant violated
        """
        current = self.get_position(symbol)
        transition_key = (current.state, action)
        
        # Validate transition allowed
        if transition_key not in self.ALLOWED_TRANSITIONS:
            raise InvariantViolation(
                f"Invalid transition: {current.state} --[{action}]-> ?"
            )
        
        next_state = self.ALLOWED_TRANSITIONS[transition_key]
        
        # Execute transition with state-specific logic
        if action == Action.ENTRY:
            new_position = self._handle_entry(symbol, next_state, **kwargs)
        elif action == "SUCCESS" and current.state == PositionState.ENTERING:
            new_position = self._handle_entry_success(current, next_state, **kwargs)
        elif action == "FAILURE" and current.state == PositionState.ENTERING:
            new_position = Position.create_flat(symbol)
        elif action == Action.REDUCE:
            new_position = self._handle_reduce(current, next_state, **kwargs)
        elif action == "PARTIAL" and current.state == PositionState.REDUCING:
            new_position = self._handle_reduce_partial(current, next_state, **kwargs)
        elif action == "COMPLETE" and current.state == PositionState.REDUCING:
            new_position = self._handle_reduce_complete(current, next_state)
        elif action == Action.EXIT:
            new_position = self._handle_exit(current, next_state)
        elif action == "SUCCESS" and current.state == PositionState.CLOSING:
            new_position = Position.create_flat(symbol)
        else:
            raise InvariantViolation(f"Unhandled transition: {transition_key}")
        
        self._positions[symbol] = new_position

        # Persist if repository configured
        if self._repository:
            self._repository.save(new_position)

        return new_position
    
    def _handle_entry(self, symbol: str, next_state: PositionState, **kwargs) -> Position:
        """Handle FLAT -> ENTERING transition."""
        direction = kwargs.get("direction")
        if direction is None:
            raise InvariantViolation("ENTRY requires direction")
        
        return Position(
            symbol=symbol,
            state=next_state,
            direction=direction,
            quantity=Decimal("0"),  # Not filled yet
            entry_price=None
        )
    
    def _handle_entry_success(self, current: Position, next_state: PositionState, **kwargs) -> Position:
        """Handle ENTERING -> OPEN transition."""
        quantity = kwargs.get("quantity")
        entry_price = kwargs.get("entry_price")
        
        if quantity is None or entry_price is None:
            raise InvariantViolation("Entry success requires quantity and entry_price")
        
        return Position(
            symbol=current.symbol,
            state=next_state,
            direction=current.direction,  # Preserved (Theorem 4.1)
            quantity=quantity,
            entry_price=entry_price
        )
    
    def _handle_reduce(self, current: Position, next_state: PositionState, **kwargs) -> Position:
        """Handle OPEN -> REDUCING transition."""
        return Position(
            symbol=current.symbol,
            state=next_state,
            direction=current.direction,
            quantity=current.quantity,  # Unchanged until exchange confirms
            entry_price=current.entry_price
        )
    
    def _handle_reduce_partial(self, current: Position, next_state: PositionState, **kwargs) -> Position:
        """Handle REDUCING -> OPEN transition (partial fill).
        
        Enforces:
        - Quantity monotonicity (Theorem 7.1): new_Q < old_Q
        - Direction preservation (Theorem 4.1): sign unchanged
        """
        new_quantity = kwargs.get("new_quantity")
        if new_quantity is None:
            raise InvariantViolation("Partial reduction requires new_quantity")
        
        # Validate quantity decreased (Theorem 7.1)
        if abs(new_quantity) >= abs(current.quantity):
            raise InvariantViolation(
                f"REDUCE must decrease quantity: {current.quantity} -> {new_quantity}"
            )
        
        # Validate direction preserved (sign check - Theorem 4.2)
        if (new_quantity > 0) != (current.quantity > 0):
            raise InvariantViolation(
                f"REDUCE changed direction: {current.quantity} -> {new_quantity}"
            )
        
        return Position(
            symbol=current.symbol,
            state=next_state,
            direction=current.direction,
            quantity=new_quantity,
            entry_price=current.entry_price
        )
    
    def _handle_reduce_complete(self, current: Position, next_state: PositionState) -> Position:
        """Handle REDUCING -> CLOSING transition (Q -> 0)."""
        return Position(
            symbol=current.symbol,
            state=next_state,
            direction=current.direction,
            quantity=Decimal("0"),  # Complete reduction
            entry_price=current.entry_price
        )
    
    def _handle_exit(self, current: Position, next_state: PositionState) -> Position:
        """Handle OPEN -> CLOSING transition."""
        return Position(
            symbol=current.symbol,
            state=next_state,
            direction=current.direction,
            quantity=current.quantity,
            entry_price=current.entry_price
        )
