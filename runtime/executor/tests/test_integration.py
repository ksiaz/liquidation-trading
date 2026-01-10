"""Integration Tests for Execution Controller.

Tests end-to-end flow:
- Mandate emission → Arbitration → State machine → Execution → Logging

Verifies all components work together correctly.
"""

import pytest
from decimal import Decimal

from runtime.executor.controller import ExecutionController
from runtime.arbitration.types import Mandate, MandateType, ActionType
from runtime.position.types import PositionState, Direction


class TestFullPositionLifecycle:
    """Test complete position lifecycle end-to-end."""
    
    def test_entry_to_flat_lifecycle(self):
        """Full lifecycle: FLAT → ENTERING → OPEN → CLOSING → FLAT."""
        controller = ExecutionController()
        
        # Cycle 1: ENTRY mandate → ENTERING state
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0)
        ]
        stats = controller.process_cycle(mandates)
        
        assert stats.mandates_received == 1
        assert stats.actions_executed == 1
        
        position = controller.state_machine.get_position("BTCUSDT")
        assert position.state == PositionState.ENTERING
    
    def test_exit_from_open_to_flat(self):
        """Test EXIT: OPEN → CLOSING → FLAT."""
        controller = ExecutionController()
        
        # Setup: Create OPEN position (simplified)
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        controller.state_machine.transition("BTCUSDT", "SUCCESS", 
                                           quantity=Decimal("1"), 
                                           entry_price=Decimal("50000"))
        
        # Cycle: EXIT mandate
        mandates = [
            Mandate("BTCUSDT", MandateType.EXIT, authority=10.0, timestamp=200.0)
        ]
        stats = controller.process_cycle(mandates)
        
        assert stats.actions_executed == 1
        position = controller.state_machine.get_position("BTCUSDT")
        assert position.state == PositionState.CLOSING


class TestConflictingMandates:
    """Test arbitration resolves conflicts correctly."""
    
    def test_exit_supremacy_over_entry(self):
        """EXIT + ENTRY → EXIT wins."""
        controller = ExecutionController()
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.EXIT, authority=1.0, timestamp=100.0),
        ]
        
        stats = controller.process_cycle(mandates)
        
        # EXIT should win despite lower authority (but fail - no position to exit)
        log = controller.get_execution_log()
        assert len(log) == 1
        assert log[0].action == ActionType.EXIT  # EXIT was chosen by arbitration
        assert not log[0].success  # But failed (invalid action for FLAT state)
        assert "Invalid action" in log[0].error
        
    def test_reduce_over_entry(self):
        """REDUCE + ENTRY → REDUCE wins (hierarchy)."""
        controller = ExecutionController()
        
        # Setup OPEN position
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        controller.state_machine.transition("BTCUSDT", "SUCCESS", 
                                           quantity=Decimal("2"), 
                                           entry_price=Decimal("50000"))
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=10.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0),
        ]
        
        stats = controller.process_cycle(mandates)
        
        # REDUCE should win
        position = controller.state_machine.get_position("BTCUSDT")
        assert position.state == PositionState.REDUCING


class TestStateValidation:
    """Test action validation against state machine."""
    
    def test_entry_rejected_if_position_exists(self):
        """ENTRY rejected if position state != FLAT."""
        controller = ExecutionController()
        
        # Create ENTERING position
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        
        # Try another ENTRY
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0)
        ]
        stats = controller.process_cycle(mandates)
        
        # Should be rejected
        assert stats.actions_rejected == 1
        assert stats.actions_executed == 0
        
        log = controller.get_execution_log()
        assert len(log) == 1
        assert not log[0].success
        assert "Invalid action" in log[0].error
    
    def test_reduce_rejected_if_not_open(self):
        """REDUCE rejected if state != OPEN."""
        controller = ExecutionController()
        
        # Position is FLAT
        mandates = [
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0)
        ]
        stats = controller.process_cycle(mandates)
        
        # Should be rejected
        assert stats.actions_rejected == 1
        log = controller.get_execution_log()
        assert not log[0].success


class TestSymbolIndependence:
    """Test symbols process independently."""
    
    def test_multiple_symbols_independent(self):
        """Different symbols processed independently."""
        controller = ExecutionController()
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
            Mandate("ETHUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
            Mandate("SOLUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
        ]
        
        stats = controller.process_cycle(mandates)
        
        assert stats.symbols_processed == 3
        assert stats.actions_executed == 3
        
        # Each symbol should be in ENTERING
        for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            position = controller.state_machine.get_position(symbol)
            assert position.state == PositionState.ENTERING
    
    def test_one_symbol_error_doesnt_affect_others(self):
        """Error on one symbol doesn't block others."""
        controller = ExecutionController()
        
        # Create OPEN position for BTC
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        controller.state_machine.transition("BTCUSDT", "SUCCESS", 
                                           quantity=Decimal("1"), 
                                           entry_price=Decimal("50000"))
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),  # Invalid
            Mandate("ETHUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),  # Valid
        ]
        
        stats = controller.process_cycle(mandates)
        
        # BTC rejected, ETH should succeed
        assert stats.actions_executed == 1  # ETH
        assert stats.actions_rejected == 1  # BTC
        
        eth_position = controller.state_machine.get_position("ETHUSDT")
        assert eth_position.state == PositionState.ENTERING


class TestRiskConstraints:
    """Test risk constraint enforcement."""
    
    def test_block_prevents_entry(self):
        """BLOCK + ENTRY → NO_ACTION (ENTRY filtered)."""
        controller = ExecutionController()
        
        mandates = [
            Mandate("BTCUSDT", MandateType.BLOCK, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=10.0, timestamp=100.0),
        ]
        
        stats = controller.process_cycle(mandates)
        
        # No action should be executed (BLOCK filtered ENTRY)
        assert stats.actions_executed == 0
        
        position = controller.state_machine.get_position("BTCUSDT")
        assert position.state == PositionState.FLAT  # Unchanged
    
    def test_block_allows_reduce(self):
        """BLOCK + REDUCE → REDUCE executes."""
        controller = ExecutionController()
        
        # Setup OPEN position
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        controller.state_machine.transition("BTCUSDT", "SUCCESS", 
                                           quantity=Decimal("2"), 
                                           entry_price=Decimal("50000"))
        
        mandates = [
            Mandate("BTCUSDT", MandateType.BLOCK, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0),
        ]
        
        stats = controller.process_cycle(mandates)
        
        # REDUCE should execute (not filtered by BLOCK)
        assert stats.actions_executed == 1
        position = controller.state_machine.get_position("BTCUSDT")
        assert position.state == PositionState.REDUCING


class TestLogging:
    """Test execution logging."""
    
    def test_successful_execution_logged(self):
        """Successful execution is logged correctly."""
        controller = ExecutionController()
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0)
        ]
        controller.process_cycle(mandates)
        
        log = controller.get_execution_log()
        assert len(log) == 1
        
        result = log[0]
        assert result.symbol == "BTCUSDT"
        assert result.action == ActionType.ENTRY
        assert result.success
        assert result.state_before == PositionState.FLAT
        assert result.state_after == PositionState.ENTERING
        assert result.error is None
    
    def test_failed_execution_logged(self):
        """Failed execution is logged with error."""
        controller = ExecutionController()
        
        # Setup position in ENTERING
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        
        # Try invalid ENTRY
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=200.0)
        ]
        controller.process_cycle(mandates)
        
        log = controller.get_execution_log()
        assert len(log) == 1
        
        result = log[0]
        assert not result.success
        assert result.error is not None
        assert "Invalid action" in result.error
    
    def test_log_captures_all_fields(self):
        """Log contains all required constitutional fields."""
        controller = ExecutionController()
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0)
        ]
        controller.process_cycle(mandates)
        
        log_dict = controller.get_execution_log()[0].to_log_dict()
        
        # Verify all required fields present
        required_fields = ["symbol", "action", "success", "state_before", 
                          "state_after", "timestamp", "error"]
        for field in required_fields:
            assert field in log_dict


class TestCycleStats:
    """Test cycle statistics tracking."""
    
    def test_cycle_stats_accurate(self):
        """Cycle stats reflect actual execution."""
        controller = ExecutionController()
        
        # Setup one OPEN position
        controller.state_machine.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        controller.state_machine.transition("BTCUSDT", "SUCCESS", 
                                           quantity=Decimal("1"), 
                                           entry_price=Decimal("50000"))
        
        mandates = [
            Mandate("BTCUSDT", MandateType.EXIT, authority=10.0, timestamp=100.0),  # Valid
            Mandate("ETHUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),  # Valid
            Mandate("SOLUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0), # Invalid (no position)
        ]
        
        stats = controller.process_cycle(mandates)
        
        assert stats.mandates_received == 3
        assert stats.symbols_processed == 3
        assert stats.actions_executed == 2  # BTC EXIT, ETH ENTRY
        assert stats.actions_rejected == 1  # SOL REDUCE
    
    def test_empty_cycle(self):
        """Empty mandate set produces zero stats."""
        controller = ExecutionController()
        
        stats = controller.process_cycle([])
        
        assert stats.mandates_received == 0
        assert stats.actions_executed == 0
        assert stats.actions_rejected == 0
        assert stats.symbols_processed == 0
