"""Position Tracker.

Stub module - position tracking is currently in state_machine.py.

This module exists for schema compliance. Actual position tracking
functionality is implemented in PositionStateMachine.

Purpose:
- Track position state across lifecycle
- Coordinate with state machine
- No interpretation of positions

Status: STUB - Functionality in state_machine.py
"""

from typing import Dict, Optional
from .types import Position, PositionState


class PositionTracker:
    """Position tracking stub.

    Actual tracking is in PositionStateMachine.
    This class exists for schema module compliance.
    """

    def __init__(self):
        """Initialize tracker."""
        self._tracked: Dict[str, Position] = {}

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get tracked position for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position if tracked, None otherwise
        """
        return self._tracked.get(symbol)

    def get_state(self, symbol: str) -> PositionState:
        """Get position state for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Current position state (FLAT if not tracked)
        """
        position = self._tracked.get(symbol)
        if position is None:
            return PositionState.FLAT
        return position.state

    def track(self, position: Position) -> None:
        """Begin tracking a position.

        Args:
            position: Position to track
        """
        self._tracked[position.symbol] = position

    def untrack(self, symbol: str) -> None:
        """Stop tracking a position.

        Args:
            symbol: Symbol to untrack
        """
        self._tracked.pop(symbol, None)

    def get_all_tracked(self) -> Dict[str, Position]:
        """Get all tracked positions.

        Returns:
            Dict of symbol -> Position
        """
        return dict(self._tracked)
