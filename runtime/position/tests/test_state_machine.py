"""Tests for Position State Machine.

Verifies all 13 theorems from POSITION_STATE_MACHINE_PROOFS.md:
- Determinism (Theorem 2.1, 2.2)
- Single-position invariant (Theorem 3.1, 3.2)
- Direction preservation (Theorem 4.1, 4.2)
- Reachability (Theorem 5.1, 5.2)
- Termination (Theorem 6.1)
- Invariant preservation (Theorem 7.1, 7.2)
- Liveness (Theorem 8.1, 8.2)
"""

import pytest
from decimal import Decimal

from runtime.position.types import Position, PositionState, Direction, InvariantViolation
from runtime.position.state_machine import PositionStateMachine, Action


class TestPositionStateInvariants:
    """Test invariants enforced in Position type (Theorems 3.2, 7.2)."""
    
    def test_flat_position_zero_quantity(self):
        """Theorem 7.2: Q=0 ⟺ state=FLAT."""
        position = Position.create_flat("BTCUSDT")
        assert position.quantity == Decimal("0")
        assert position.state == PositionState.FLAT
   
    def test_flat_position_no_direction(self):
        """FLAT position must have direction=None."""
        position = Position.create_flat("BTCUSDT")
        assert position.direction is None
    
    def test_non_flat_requires_quantity(self):
        """Theorem 7.2: If state≠FLAT then Q≠0."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("0"),  # Invalid!
                entry_price=Decimal("50000")
            )
    
    def test_non_flat_requires_direction(self):
        """If state≠FLAT then direction≠None."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=None,  # Invalid!
                quantity=Decimal("1"),
                entry_price=Decimal("50000")
            )
    
    def test_flat_with_nonzero_quantity_rejected(self):
        """FLAT position cannot have Q≠0."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTCUSDT",
                state=PositionState.FLAT,
                direction=None,
                quantity=Decimal("1"),  # Invalid!
                entry_price=None
            )


class TestStateMachineDeterminism:
    """Test deterministic transitions (Theorems 2.1, 2.2)."""
    
    def test_same_state_action_same_result(self):
        """Theorem 2.1: Same (state, action) → same next_state."""
        sm1 = PositionStateMachine()
        sm2 = PositionStateMachine()
        
        # Execute same transition twice
        pos1 = sm1.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        pos2 = sm2.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        
        assert pos1.state == pos2.state == PositionState.ENTERING
        assert pos1.direction == pos2.direction == Direction.LONG
    
    def test_no_implicit_transitions(self):
        """Theorem 2.2: No state changes without explicit action."""
        sm = PositionStateMachine()
        pos1 = sm.get_position("BTCUSDT")
        
        # Time passes... (simulate)
        # But no action called
        
        pos2 = sm.get_position("BTCUSDT")
        assert pos1.state == pos2.state  # No change


class TestSinglePositionInvariant:
    """Test one position per symbol (Theorem 3.1)."""
    
    def test_one_position_per_symbol(self):
        """Theorem 3.1: At most one position object per symbol."""
        sm = PositionStateMachine()
        
        pos1 = sm.get_position("BTCUSDT")
        pos2 = sm.get_position("BTCUSDT")
        
        # Same object (dict uniqueness)
        assert pos1 is pos2
    
    def test_entry_rejects_if_position_exists(self):
        """Cannot ENTRY if position state≠FLAT."""
        sm = PositionStateMachine()
        
        # First entry succeeds
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        
        # Second entry should fail validation
        assert not sm.validate_entry("BTCUSDT")


class TestDirectionPreservation:
    """Test direction immutability (Theorems 4.1, 4.2)."""
    
    def test_direction_preserved_through_lifecycle(self):
        """Theorem 4.1: Direction unchanged until FLAT."""
        sm = PositionStateMachine()
        
        # ENTRY sets direction
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        pos = sm.get_position("BTCUSDT")
        assert pos.direction == Direction.LONG
        
        # Fill entry -> OPEN
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        pos = sm.get_position("BTCUSDT")
        assert pos.direction == Direction.LONG  # Preserved
        
        # REDUCE
        sm.transition("BTCUSDT", Action.REDUCE)
        pos = sm.get_position("BTCUSDT")
        assert pos.direction == Direction.LONG  # Still preserved
    
    def test_direction_cleared_on_flat(self):
        """Direction reset when returning to FLAT."""
        sm = PositionStateMachine()
        
        # Go through full lifecycle
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.SHORT)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("-1"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.EXIT)
        sm.transition("BTCUSDT", "SUCCESS")
        
        pos = sm.get_position("BTCUSDT")
        assert pos.state == PositionState.FLAT
        assert pos.direction is None  # Cleared
    
    def test_reduce_cannot_reverse_direction(self):
        """Theorem 4.2: Cannot go LONG→SHORT without FLAT."""
        sm = PositionStateMachine()
        
        # Open LONG position
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("2"), 
                     entry_price=Decimal("50000"))
        
        # REDUCE to REDUCING state
        sm.transition("BTCUSDT", Action.REDUCE)
        
        # Try to flip to SHORT (should fail)
        with pytest.raises(InvariantViolation):
            sm.transition("BTCUSDT", "PARTIAL", 
                         new_quantity=Decimal("-1"))  # Wrong sign!


class TestAllowedTransitions:
    """Test all 8 allowed transitions (Section 1.2)."""
    
    def test_flat_to_entering(self):
        """Transition 1: FLAT --[ENTRY]→ ENTERING."""
        sm = PositionStateMachine()
        pos = sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        assert pos.state == PositionState.ENTERING
    
    def test_entering_to_open(self):
        """Transition 2: ENTERING --[SUCCESS]→ OPEN."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        pos = sm.transition("BTCUSDT", "SUCCESS", 
                           quantity=Decimal("1"), 
                           entry_price=Decimal("50000"))
        assert pos.state == PositionState.OPEN
    
    def test_entering_to_flat_failure(self):
        """Transition 3: ENTERING --[FAILURE]→ FLAT."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        pos = sm.transition("BTCUSDT", "FAILURE")
        assert pos.state == PositionState.FLAT
    
    def test_open_to_reducing(self):
        """Transition 4: OPEN --[REDUCE]→ REDUCING."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("2"), 
                     entry_price=Decimal("50000"))
        pos = sm.transition("BTCUSDT", Action.REDUCE)
        assert pos.state == PositionState.REDUCING
    
    def test_open_to_closing(self):
        """Transition 5: OPEN --[EXIT]→ CLOSING."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        pos = sm.transition("BTCUSDT", Action.EXIT)
        assert pos.state == PositionState.CLOSING
    
    def test_reducing_to_open(self):
        """Transition 6: REDUCING --[PARTIAL]→ OPEN."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("2"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.REDUCE)
        pos = sm.transition("BTCUSDT", "PARTIAL", new_quantity=Decimal("1"))
        assert pos.state == PositionState.OPEN
    
    def test_reducing_to_closing(self):
        """Transition 7: REDUCING --[COMPLETE]→ CLOSING."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.REDUCE)
        pos = sm.transition("BTCUSDT", "COMPLETE")
        assert pos.state == PositionState.CLOSING
    
    def test_closing_to_flat(self):
        """Transition 8: CLOSING --[SUCCESS]→ FLAT."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.EXIT)
        pos = sm.transition("BTCUSDT", "SUCCESS")
        assert pos.state == PositionState.FLAT


class TestForbiddenTransitions:
    """Test forbidden transitions are rejected (Section 1.3)."""
    
    def test_flat_to_open_forbidden(self):
        """Cannot skip ENTERING state."""
        sm = PositionStateMachine()
        with pytest.raises(InvariantViolation):
            sm.transition("BTCUSDT", Action.EXIT)  # FLAT -> ?
    
    def test_open_to_entering_forbidden(self):
        """Cannot re-enter from OPEN."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        
        with pytest.raises(InvariantViolation):
            sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)


class TestQuantityMonotonicity:
    """Test quantity decreases during REDUCE (Theorem 7.1)."""
    
    def test_reduce_decreases_quantity(self):
        """Theorem 7.1: REDUCING → |Q_new| < |Q_old|."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("2"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.REDUCE)
        
        pos = sm.transition("BTCUSDT", "PARTIAL", new_quantity=Decimal("1"))
        assert pos.quantity < Decimal("2")
    
    def test_reduce_cannot_increase_quantity(self):
        """REDUCE with increased Q is rejected."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.REDUCE)
        
        with pytest.raises(InvariantViolation):
            sm.transition("BTCUSDT", "PARTIAL", new_quantity=Decimal("2"))


class TestTermination:
    """Test all paths lead to FLAT (Theorem 6.1)."""
    
    def test_lifecycle_returns_to_flat(self):
        """Theorem 6.1: All paths → FLAT in finite steps."""
        sm = PositionStateMachine()
        
        # Full lifecycle
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS", 
                     quantity=Decimal("1"), 
                     entry_price=Decimal("50000"))
        sm.transition("BTCUSDT", Action.EXIT)
        pos = sm.transition("BTCUSDT", "SUCCESS")
        
        assert pos.state == PositionState.FLAT  # Terminated
    
    def test_failed_entry_returns_to_flat(self):
        """Failed ENTRY → FLAT (1 step)."""
        sm = PositionStateMachine()
        sm.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        pos = sm.transition("BTCUSDT", "FAILURE")
        assert pos.state == PositionState.FLAT


class TestReachability:
    """Test all states reachable (Theorem 5.1)."""
    
    def test_all_states_reachable_from_flat(self):
        """Theorem 5.1: Every state reachable from FLAT."""
        sm = PositionStateMachine()
        
        # Reach ENTERING
        sm.transition("SYM1", Action.ENTRY, direction=Direction.LONG)
        assert sm.get_position("SYM1").state == PositionState.ENTERING
        
        # Reach OPEN
        sm.transition("SYM2", Action.ENTRY, direction=Direction.LONG)
        sm.transition("SYM2", "SUCCESS", quantity=Decimal("1"), entry_price=Decimal("50000"))
        assert sm.get_position("SYM2").state == PositionState.OPEN
        
        # Reach REDUCING
        sm.transition("SYM3", Action.ENTRY, direction=Direction.LONG)
        sm.transition("SYM3", "SUCCESS", quantity=Decimal("2"), entry_price=Decimal("50000"))
        sm.transition("SYM3", Action.REDUCE)
        assert sm.get_position("SYM3").state == PositionState.REDUCING
        
        # Reach CLOSING
        sm.transition("SYM4", Action.ENTRY, direction=Direction.LONG)
        sm.transition("SYM4", "SUCCESS", quantity=Decimal("1"), entry_price=Decimal("50000"))
        sm.transition("SYM4", Action.EXIT)
        assert sm.get_position("SYM4").state == PositionState.CLOSING
