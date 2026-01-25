"""Unit tests for PositionRepository."""

import pytest
import tempfile
import os
from decimal import Decimal

from runtime.position.repository import PositionRepository
from runtime.position.types import Position, PositionState, Direction
from runtime.position.state_machine import PositionStateMachine


class TestPositionRepository:
    """Tests for PositionRepository."""

    def setup_method(self):
        """Create temp database for each test."""
        self.temp_db = tempfile.mkstemp(suffix='.db')[1]
        self.repo = PositionRepository(self.temp_db)

    def teardown_method(self):
        """Cleanup temp database."""
        self.repo.close()
        import gc
        gc.collect()  # Help release any lingering references
        try:
            if os.path.exists(self.temp_db):
                os.remove(self.temp_db)
        except PermissionError:
            pass  # Windows may still hold lock briefly

    def test_save_and_load_position(self):
        """Test saving and loading a single position."""
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.5"),
            entry_price=Decimal("50000.0")
        )

        self.repo.save(position)
        loaded = self.repo.load("BTCUSDT")

        assert loaded is not None
        assert loaded.symbol == "BTCUSDT"
        assert loaded.state == PositionState.OPEN
        assert loaded.direction == Direction.LONG
        assert loaded.quantity == Decimal("1.5")
        assert loaded.entry_price == Decimal("50000.0")

    def test_load_nonexistent_returns_none(self):
        """Test loading nonexistent position returns None."""
        loaded = self.repo.load("NONEXISTENT")
        assert loaded is None

    def test_save_overwrites_existing(self):
        """Test that save updates existing position."""
        # Save initial
        position1 = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        )
        self.repo.save(position1)

        # Save update
        position2 = Position(
            symbol="BTCUSDT",
            state=PositionState.CLOSING,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        )
        self.repo.save(position2)

        loaded = self.repo.load("BTCUSDT")
        assert loaded.state == PositionState.CLOSING

    def test_save_flat_position(self):
        """Test saving a FLAT position."""
        position = Position.create_flat("BTCUSDT")

        self.repo.save(position)
        loaded = self.repo.load("BTCUSDT")

        assert loaded is not None
        assert loaded.state == PositionState.FLAT
        assert loaded.direction is None
        assert loaded.quantity == Decimal("0")
        assert loaded.entry_price is None

    def test_load_all(self):
        """Test loading all positions."""
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("1.0"),
                entry_price=Decimal("50000.0")
            ),
            "ETHUSDT": Position(
                symbol="ETHUSDT",
                state=PositionState.OPEN,
                direction=Direction.SHORT,
                quantity=Decimal("10.0"),
                entry_price=Decimal("3000.0")
            ),
        }

        self.repo.save_all(positions)
        loaded = self.repo.load_all()

        assert len(loaded) == 2
        assert "BTCUSDT" in loaded
        assert "ETHUSDT" in loaded
        assert loaded["ETHUSDT"].direction == Direction.SHORT

    def test_load_open_positions(self):
        """Test loading only OPEN positions."""
        self.repo.save(Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        ))
        self.repo.save(Position(
            symbol="ETHUSDT",
            state=PositionState.FLAT,
            direction=None,
            quantity=Decimal("0"),
            entry_price=None
        ))
        self.repo.save(Position(
            symbol="SOLUSDT",
            state=PositionState.CLOSING,
            direction=Direction.LONG,
            quantity=Decimal("100.0"),
            entry_price=Decimal("150.0")
        ))

        open_positions = self.repo.load_open_positions()

        assert len(open_positions) == 1
        assert "BTCUSDT" in open_positions
        assert "ETHUSDT" not in open_positions
        assert "SOLUSDT" not in open_positions

    def test_load_non_flat_positions(self):
        """Test loading all non-FLAT positions."""
        self.repo.save(Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        ))
        self.repo.save(Position(
            symbol="ETHUSDT",
            state=PositionState.FLAT,
            direction=None,
            quantity=Decimal("0"),
            entry_price=None
        ))
        self.repo.save(Position(
            symbol="SOLUSDT",
            state=PositionState.CLOSING,
            direction=Direction.LONG,
            quantity=Decimal("100.0"),
            entry_price=Decimal("150.0")
        ))

        non_flat = self.repo.load_non_flat_positions()

        assert len(non_flat) == 2
        assert "BTCUSDT" in non_flat
        assert "SOLUSDT" in non_flat
        assert "ETHUSDT" not in non_flat

    def test_delete_position(self):
        """Test deleting a position."""
        self.repo.save(Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        ))

        self.repo.delete("BTCUSDT")
        loaded = self.repo.load("BTCUSDT")

        assert loaded is None

    def test_delete_flat_positions(self):
        """Test deleting all FLAT positions."""
        self.repo.save(Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        ))
        self.repo.save(Position(
            symbol="ETHUSDT",
            state=PositionState.FLAT,
            direction=None,
            quantity=Decimal("0"),
            entry_price=None
        ))
        self.repo.save(Position(
            symbol="SOLUSDT",
            state=PositionState.FLAT,
            direction=None,
            quantity=Decimal("0"),
            entry_price=None
        ))

        deleted = self.repo.delete_flat_positions()

        assert deleted == 2
        assert self.repo.load("BTCUSDT") is not None
        assert self.repo.load("ETHUSDT") is None
        assert self.repo.load("SOLUSDT") is None

    def test_decimal_precision_preserved(self):
        """Test that Decimal precision is preserved through save/load."""
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("0.00123456789"),
            entry_price=Decimal("50000.123456789")
        )

        self.repo.save(position)
        loaded = self.repo.load("BTCUSDT")

        assert loaded.quantity == Decimal("0.00123456789")
        assert loaded.entry_price == Decimal("50000.123456789")


class TestStateMachineWithPersistence:
    """Tests for PositionStateMachine with repository."""

    def setup_method(self):
        """Create temp database for each test."""
        self.temp_db = tempfile.mkstemp(suffix='.db')[1]
        self.repo = PositionRepository(self.temp_db)

    def teardown_method(self):
        """Cleanup temp database."""
        self.repo.close()
        import gc
        gc.collect()  # Help release any lingering references
        try:
            if os.path.exists(self.temp_db):
                os.remove(self.temp_db)
        except PermissionError:
            pass  # Windows may still hold lock briefly

    def test_state_machine_loads_positions_on_init(self):
        """Test that state machine loads existing positions."""
        # Pre-populate database
        self.repo.save(Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000.0")
        ))

        # Create new state machine with same repo
        sm = PositionStateMachine(repository=self.repo)

        # Position should be loaded
        pos = sm.get_position("BTCUSDT")
        assert pos.state == PositionState.OPEN
        assert pos.quantity == Decimal("1.0")

    def test_state_machine_persists_transitions(self):
        """Test that transitions are persisted."""
        sm = PositionStateMachine(repository=self.repo)

        # Perform transitions
        sm.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        sm.transition("BTCUSDT", "SUCCESS",
                      quantity=Decimal("1.0"),
                      entry_price=Decimal("50000.0"))

        # Verify persisted
        loaded = self.repo.load("BTCUSDT")
        assert loaded.state == PositionState.OPEN
        assert loaded.quantity == Decimal("1.0")

    def test_position_survives_restart(self):
        """Test position recovery after simulated restart."""
        # First session: open position
        sm1 = PositionStateMachine(repository=self.repo)
        sm1.transition("BTCUSDT", "ENTRY", direction=Direction.LONG)
        sm1.transition("BTCUSDT", "SUCCESS",
                       quantity=Decimal("2.5"),
                       entry_price=Decimal("45000.0"))

        # Verify position is OPEN
        pos1 = sm1.get_position("BTCUSDT")
        assert pos1.state == PositionState.OPEN

        # Close first repo before simulating restart
        self.repo.close()

        # Simulate restart: create new state machine with same DB
        repo2 = PositionRepository(self.temp_db)
        sm2 = PositionStateMachine(repository=repo2)

        # Position should be recovered
        pos2 = sm2.get_position("BTCUSDT")
        assert pos2.state == PositionState.OPEN
        assert pos2.direction == Direction.LONG
        assert pos2.quantity == Decimal("2.5")
        assert pos2.entry_price == Decimal("45000.0")

        repo2.close()

        # Re-open for teardown consistency
        self.repo = PositionRepository(self.temp_db)

    def test_flat_positions_not_loaded(self):
        """Test that FLAT positions are not loaded on restart."""
        # Pre-populate with FLAT position
        self.repo.save(Position.create_flat("BTCUSDT"))

        # Create state machine
        sm = PositionStateMachine(repository=self.repo)

        # FLAT position should not be in _positions dict
        assert "BTCUSDT" not in sm._positions

        # But get_position should still return FLAT
        pos = sm.get_position("BTCUSDT")
        assert pos.state == PositionState.FLAT


class TestExecutionControllerWithPersistence:
    """Tests for ExecutionController with position persistence."""

    def setup_method(self):
        """Create temp database for each test."""
        self.temp_db = tempfile.mkstemp(suffix='.db')[1]
        self._controllers = []  # Track controllers for cleanup

    def teardown_method(self):
        """Cleanup temp database."""
        # Close all controllers' repositories
        for controller in self._controllers:
            if controller._repository:
                controller._repository.close()
        self._controllers.clear()

        # Now safe to remove file
        import gc
        gc.collect()  # Help release any lingering references
        try:
            if os.path.exists(self.temp_db):
                os.remove(self.temp_db)
        except PermissionError:
            pass  # Windows may still hold lock briefly

    def test_controller_with_persistence(self):
        """Test controller creates repository when db_path provided."""
        from runtime.executor.controller import ExecutionController

        controller = ExecutionController(db_path=self.temp_db)
        self._controllers.append(controller)

        assert controller._repository is not None
        assert controller.state_machine._repository is not None

    def test_controller_without_persistence(self):
        """Test controller works without persistence."""
        from runtime.executor.controller import ExecutionController

        controller = ExecutionController()
        self._controllers.append(controller)

        assert controller._repository is None
        assert controller.state_machine._repository is None

    def test_position_persists_through_controller(self):
        """Test position persists when using controller."""
        from runtime.executor.controller import ExecutionController
        from runtime.arbitration.types import Mandate, MandateType
        from runtime.risk.types import AccountState
        import time

        # First session
        controller1 = ExecutionController(db_path=self.temp_db)
        self._controllers.append(controller1)

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
                direction="LONG",
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        controller1.process_cycle(mandates, account, mark_prices)

        # Verify position opened
        pos1 = controller1.state_machine.get_position("BTCUSDT")
        assert pos1.state == PositionState.OPEN

        # Close first controller before simulating restart
        controller1._repository.close()

        # Simulate restart
        controller2 = ExecutionController(db_path=self.temp_db)
        self._controllers.append(controller2)

        # Position should be recovered
        pos2 = controller2.state_machine.get_position("BTCUSDT")
        assert pos2.state == PositionState.OPEN
        assert pos2.direction == Direction.LONG
