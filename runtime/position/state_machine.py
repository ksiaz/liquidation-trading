"""Position State Machine.

Implements deterministic position lifecycle per POSITION_STATE_MACHINE_PROOFS.md.

Enforces:
- 13 proven theorems
- 8 allowed transitions (+ X3-A emergency exit)
- 17 forbidden transitions (rejected)
- Single-position invariant
- Direction preservation
- X6-A: CLOSING state timeout

Hardenings:
- X3-A: Emergency exit from ENTERING/REDUCING states
- X6-A: CLOSING state timeout tracking
- P4: CLOSING timeout persistence across restarts
"""

import time
from decimal import Decimal
from threading import RLock
from typing import Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass

from .types import Position, PositionState, Direction, InvariantViolation

if TYPE_CHECKING:
    from .repository import PositionRepository
    from runtime.persistence import ExecutionStateRepository


# X6-A: Default CLOSING state timeout (30 seconds)
DEFAULT_CLOSING_TIMEOUT_SEC = 30.0


@dataclass
class ClosingStateTracker:
    """X6-A: Tracks CLOSING state entry time for timeout detection."""
    symbol: str
    entered_closing_at: float  # timestamp when entered CLOSING
    timeout_sec: float = DEFAULT_CLOSING_TIMEOUT_SEC


class Action(str):
    """Actions that trigger state transitions."""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"  # X3-A: Emergency exit from any state


class PositionStateMachine:
    """Manages position lifecycle for all symbols.

    Invariants:
    - One position per symbol (dict uniqueness - Theorem 3.1)
    - Deterministic transitions (Theorem 2.1)
    - All paths lead to FLAT (Theorem 6.1)

    Supports optional persistence via PositionRepository.
    """

    # Allowed transitions (Theorem 2.1, Section 1.2)
    # X3-A: Added EMERGENCY_EXIT from ENTERING and REDUCING states
    ALLOWED_TRANSITIONS = {
        (PositionState.FLAT, Action.ENTRY): PositionState.ENTERING,
        (PositionState.ENTERING, "SUCCESS"): PositionState.OPEN,
        (PositionState.ENTERING, "FAILURE"): PositionState.FLAT,
        (PositionState.OPEN, Action.REDUCE): PositionState.REDUCING,
        (PositionState.OPEN, Action.EXIT): PositionState.CLOSING,
        (PositionState.REDUCING, "COMPLETE"): PositionState.CLOSING,
        (PositionState.REDUCING, "PARTIAL"): PositionState.OPEN,
        (PositionState.CLOSING, "SUCCESS"): PositionState.FLAT,
        # X3-A: Emergency exit paths (cancel pending + market close)
        (PositionState.ENTERING, Action.EMERGENCY_EXIT): PositionState.CLOSING,
        (PositionState.REDUCING, Action.EMERGENCY_EXIT): PositionState.CLOSING,
    }

    def __init__(
        self,
        repository: Optional["PositionRepository"] = None,
        closing_timeout_sec: float = DEFAULT_CLOSING_TIMEOUT_SEC,
        execution_state_repository: Optional["ExecutionStateRepository"] = None
    ):
        """Initialize state machine.

        Args:
            repository: Optional persistence layer. If provided, positions
                       are loaded on init and saved on every transition.
            closing_timeout_sec: X6-A timeout for CLOSING state (default 30s)
            execution_state_repository: P4 - Optional persistence for CLOSING timeouts
        """
        # AUDIT-P0-1: Thread safety lock for all state access
        self._lock = RLock()

        self._positions: Dict[str, Position] = {}
        self._repository = repository

        # X6-A: CLOSING state timeout tracking
        self._closing_timeout_sec = closing_timeout_sec
        self._closing_trackers: Dict[str, ClosingStateTracker] = {}

        # P4: Persistence for CLOSING timeouts
        self._exec_state_repo = execution_state_repository

        # Load existing positions if repository provided
        if self._repository:
            self._positions = self._repository.load_non_flat_positions()

        # P4: Load persisted CLOSING timeouts
        if self._exec_state_repo:
            self._load_persisted_closing_timeouts()
    
    def _load_persisted_closing_timeouts(self):
        """P4: Load persisted CLOSING timeouts on startup."""
        if not self._exec_state_repo:
            return

        try:
            persisted = self._exec_state_repo.load_all_closing_timeouts()
            with self._lock:
                for symbol, p in persisted.items():
                    self._closing_trackers[symbol] = ClosingStateTracker(
                        symbol=p.symbol,
                        entered_closing_at=p.entered_closing_at,
                        timeout_sec=p.timeout_sec
                    )
            # Note: imported here to avoid circular imports
            import logging
            logging.getLogger(__name__).info(
                f"P4: Loaded {len(persisted)} CLOSING timeouts from persistence"
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                f"P4: Failed to load persisted CLOSING timeouts: {e}"
            )
            # AUDIT-P0-1: Re-raise to prevent state machine operating with incomplete state
            raise

    def _persist_closing_timeout(self, symbol: str, entered_at: float, timeout_sec: float):
        """P4: Persist CLOSING timeout."""
        if not self._exec_state_repo:
            return

        try:
            self._exec_state_repo.save_closing_timeout(symbol, entered_at, timeout_sec)
        except Exception:
            pass  # Don't fail transitions due to persistence errors

    def _delete_closing_timeout(self, symbol: str):
        """P4: Delete CLOSING timeout from persistence."""
        if not self._exec_state_repo:
            return

        try:
            self._exec_state_repo.delete_closing_timeout(symbol)
        except Exception:
            pass  # Don't fail transitions due to persistence errors

    def get_position(self, symbol: str) -> Position:
        """Get position for symbol (creates FLAT if not exists)."""
        with self._lock:
            if symbol not in self._positions:
                self._positions[symbol] = Position.create_flat(symbol)
            return self._positions[symbol]
    
    def validate_entry(self, symbol: str) -> bool:
        """Validate ENTRY action (Theorem 3.1 - single position invariant).

        Returns:
            True if ENTRY allowed, False otherwise
        """
        with self._lock:
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
        with self._lock:
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
            elif action == Action.EMERGENCY_EXIT:
                # X3-A: Emergency exit from ENTERING or REDUCING
                new_position = self._handle_emergency_exit(current, next_state)
            elif action == "SUCCESS" and current.state == PositionState.CLOSING:
                new_position = Position.create_flat(symbol)
            else:
                raise InvariantViolation(f"Unhandled transition: {transition_key}")

            self._positions[symbol] = new_position

            # X6-A: Track CLOSING state entry time
            if new_position.state == PositionState.CLOSING:
                if symbol not in self._closing_trackers:
                    entered_at = time.time()
                    self._closing_trackers[symbol] = ClosingStateTracker(
                        symbol=symbol,
                        entered_closing_at=entered_at,
                        timeout_sec=self._closing_timeout_sec
                    )
                    # P4: Persist CLOSING timeout
                    self._persist_closing_timeout(symbol, entered_at, self._closing_timeout_sec)
            elif new_position.state == PositionState.FLAT:
                # Clear CLOSING tracker when position closes
                self._closing_trackers.pop(symbol, None)
                # P4: Delete from persistence
                self._delete_closing_timeout(symbol)

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

    def _handle_emergency_exit(self, current: Position, next_state: PositionState) -> Position:
        """X3-A: Handle emergency exit from ENTERING or REDUCING states.

        This is a safety valve for scenarios where:
        - Market crashes during entry order pending
        - Need to abort a reduce operation
        - Risk limits breached while in transitional state

        The caller is responsible for:
        1. Cancelling any pending orders on exchange
        2. Submitting market close order for any filled quantity

        Returns position in CLOSING state (awaiting close confirmation).
        """
        return Position(
            symbol=current.symbol,
            state=next_state,  # CLOSING
            direction=current.direction,
            quantity=current.quantity,  # May be 0 if nothing filled yet
            entry_price=current.entry_price
        )

    def check_closing_timeouts(self) -> Dict[str, float]:
        """X6-A: Check for CLOSING state timeouts.

        Returns:
            Dict of symbol -> seconds in CLOSING state for timed-out positions
        """
        with self._lock:
            now = time.time()
            timed_out = {}

            # AUDIT-P0-1: Copy items to avoid modification during iteration
            trackers_copy = list(self._closing_trackers.items())

        for symbol, tracker in trackers_copy:
            elapsed = now - tracker.entered_closing_at
            if elapsed > tracker.timeout_sec:
                timed_out[symbol] = elapsed

        return timed_out

    def force_close_timeout(self, symbol: str) -> Position:
        """X6-A: Force position to FLAT after CLOSING timeout.

        This is a last resort when exit order never fills.
        WARNING: May result in state desync with exchange!

        The caller MUST:
        1. Cancel any pending exit orders
        2. Verify actual exchange position state
        3. Reconcile if necessary

        Args:
            symbol: Symbol to force close

        Returns:
            New FLAT position

        Raises:
            InvariantViolation: If position not in CLOSING state
        """
        with self._lock:
            current = self.get_position(symbol)

            if current.state != PositionState.CLOSING:
                raise InvariantViolation(
                    f"X6-A: Cannot force close {symbol} - not in CLOSING state "
                    f"(current: {current.state})"
                )

            # Force transition to FLAT
            new_position = Position.create_flat(symbol)
            self._positions[symbol] = new_position

            # Clear timeout tracker
            self._closing_trackers.pop(symbol, None)

            # P4: Delete from persistence
            self._delete_closing_timeout(symbol)

            # Persist if repository configured
            if self._repository:
                self._repository.save(new_position)

            return new_position

    def get_closing_duration(self, symbol: str) -> Optional[float]:
        """X6-A: Get how long position has been in CLOSING state.

        Returns:
            Seconds in CLOSING state, or None if not in CLOSING
        """
        with self._lock:
            tracker = self._closing_trackers.get(symbol)
            if tracker:
                return time.time() - tracker.entered_closing_at
            return None
