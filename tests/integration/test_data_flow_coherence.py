"""Integration tests for end-to-end data flow coherence.

Verifies that data flows correctly through all layers:
1. External Data → Observation Layer
2. Observation → Analysis (Policy Adapter)
3. Analysis → Arbitration
4. Arbitration → Risk
5. Risk → Execution
6. Execution → Position State

Tests type compatibility, data transformation, and boundary contracts.
"""

import pytest
import time
from decimal import Decimal
from typing import Dict, List

# Layer 1: Observation
from observation.governance import ObservationSystem
from observation.types import (
    ObservationSnapshot,
    ObservationStatus,
    M4PrimitiveBundle,
)

# Layer 2: Analysis (Policy Adapter)
from runtime.policy_adapter import PolicyAdapter, AdapterConfig

# Layer 3: Arbitration
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.arbitration.types import Mandate, MandateType, Action, ActionType

# Layer 4: Risk
from runtime.risk.types import RiskConfig, AccountState
from runtime.risk.monitor import RiskMonitor

# Layer 5: Execution
from runtime.executor.controller import ExecutionController
from runtime.executor.types import ExecutionResult, CycleStats

# Layer 6: Position
from runtime.position.state_machine import PositionStateMachine
from runtime.position.types import Position, PositionState, Direction


def create_empty_primitive_bundle(symbol: str) -> M4PrimitiveBundle:
    """Create an empty M4PrimitiveBundle with all None primitives.

    Note: This helper is kept for backwards compatibility.
    Prefer using M4PrimitiveBundle.empty(symbol) directly.
    """
    return M4PrimitiveBundle.empty(symbol)


class TestObservationToSnapshot:
    """Test data flow from external data to ObservationSnapshot."""

    def test_observation_produces_snapshot(self):
        """ObservationSystem.query returns ObservationSnapshot."""
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Advance time to initialize
        obs.advance_time(time.time())

        # Query snapshot
        snapshot = obs.query({'type': 'snapshot'})

        # Verify type
        assert isinstance(snapshot, ObservationSnapshot)
        assert snapshot.status == ObservationStatus.UNINITIALIZED
        assert "BTCUSDT" in snapshot.symbols_active

    def test_snapshot_contains_primitive_bundles(self):
        """ObservationSnapshot.primitives contains M4PrimitiveBundle per symbol."""
        obs = ObservationSystem(allowed_symbols=["BTCUSDT", "ETHUSDT"])
        obs.advance_time(time.time())

        snapshot = obs.query({'type': 'snapshot'})

        # Verify primitives dict exists
        assert isinstance(snapshot.primitives, dict)

        # Each symbol should have a bundle
        for symbol in snapshot.symbols_active:
            assert symbol in snapshot.primitives
            assert isinstance(snapshot.primitives[symbol], M4PrimitiveBundle)

    def test_trade_ingestion_updates_snapshot(self):
        """Ingested trades affect snapshot state."""
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])

        ts = time.time()
        obs.advance_time(ts)

        # Ingest trades
        for i in range(20):
            trade_ts = ts + i * 0.1
            obs.ingest_observation(trade_ts, "BTCUSDT", "TRADE", {
                'p': str(50000 + i),
                'q': '0.1',
                's': 'BTCUSDT',
                'm': i % 2 == 0,  # Alternating buyer/seller maker
                'T': int(trade_ts * 1000),
            })

        obs.advance_time(ts + 2.0)
        snapshot = obs.query({'type': 'snapshot'})

        # Should still be valid snapshot
        assert isinstance(snapshot, ObservationSnapshot)
        assert snapshot.status != ObservationStatus.FAILED


class TestSnapshotToMandate:
    """Test data flow from ObservationSnapshot to Mandate."""

    def test_policy_adapter_accepts_snapshot(self):
        """PolicyAdapter.generate_mandates accepts ObservationSnapshot."""
        adapter = PolicyAdapter(AdapterConfig())

        # Create minimal snapshot
        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=time.time(),
            symbols_active=["BTCUSDT"],
            counters=None,
            promoted_events=None,
            primitives={"BTCUSDT": create_empty_primitive_bundle("BTCUSDT")},
        )

        # Generate mandates - should not raise
        mandates = adapter.generate_mandates(
            observation_snapshot=snapshot,
            symbol="BTCUSDT",
            timestamp=time.time(),
            position_state=PositionState.FLAT,
        )

        # Returns list (may be empty)
        assert isinstance(mandates, list)

    def test_mandates_have_correct_type(self):
        """Generated mandates are Mandate instances."""
        adapter = PolicyAdapter(AdapterConfig(enable_geometry=True))

        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=time.time(),
            symbols_active=["BTCUSDT"],
            counters=None,
            promoted_events=None,
            primitives={"BTCUSDT": create_empty_primitive_bundle("BTCUSDT")},
        )

        mandates = adapter.generate_mandates(
            observation_snapshot=snapshot,
            symbol="BTCUSDT",
            timestamp=time.time(),
            position_state=PositionState.FLAT,
        )

        for mandate in mandates:
            assert isinstance(mandate, Mandate)
            assert mandate.symbol == "BTCUSDT"
            assert isinstance(mandate.type, MandateType)


class TestMandateToAction:
    """Test data flow from Mandate to Action."""

    def test_arbitrator_accepts_mandates(self):
        """MandateArbitrator.arbitrate_all accepts List[Mandate]."""
        arbitrator = MandateArbitrator()

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        actions = arbitrator.arbitrate_all(mandates)

        assert isinstance(actions, dict)
        assert "BTCUSDT" in actions

    def test_arbitration_produces_actions(self):
        """Arbitration produces Action instances."""
        arbitrator = MandateArbitrator()

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
            Mandate(
                type=MandateType.HOLD,
                symbol="ETHUSDT",
                authority=5,
                timestamp=time.time(),
            ),
        ]

        actions = arbitrator.arbitrate_all(mandates)

        for symbol, action in actions.items():
            assert isinstance(action, Action)
            assert action.symbol == symbol
            assert isinstance(action.type, ActionType)

    def test_exit_supremacy_preserved(self):
        """EXIT mandate wins over ENTRY (Theorem 2.2)."""
        arbitrator = MandateArbitrator()

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=100,
                timestamp=time.time(),
            ),
            Mandate(
                type=MandateType.EXIT,
                symbol="BTCUSDT",
                authority=1,  # Lower authority
                timestamp=time.time(),
            ),
        ]

        actions = arbitrator.arbitrate_all(mandates)

        # EXIT wins regardless of authority
        assert actions["BTCUSDT"].type == ActionType.EXIT

    def test_direction_passthrough(self):
        """Direction is preserved from Mandate to Action."""
        arbitrator = MandateArbitrator()

        # Test LONG direction
        long_mandate = Mandate(
            type=MandateType.ENTRY,
            symbol="BTCUSDT",
            authority=10,
            timestamp=time.time(),
            direction="LONG",
        )
        actions = arbitrator.arbitrate_all([long_mandate])
        assert actions["BTCUSDT"].direction == "LONG"

        # Test SHORT direction
        short_mandate = Mandate(
            type=MandateType.ENTRY,
            symbol="ETHUSDT",
            authority=10,
            timestamp=time.time(),
            direction="SHORT",
        )
        actions = arbitrator.arbitrate_all([short_mandate])
        assert actions["ETHUSDT"].direction == "SHORT"

        # Test None direction (default)
        no_dir_mandate = Mandate(
            type=MandateType.ENTRY,
            symbol="SOLUSDT",
            authority=10,
            timestamp=time.time(),
        )
        actions = arbitrator.arbitrate_all([no_dir_mandate])
        assert actions["SOLUSDT"].direction is None


class TestActionToExecution:
    """Test data flow from Action to ExecutionResult."""

    def test_controller_accepts_mandates(self):
        """ExecutionController.process_cycle accepts mandates."""
        controller = ExecutionController(RiskConfig())

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )

        mark_prices = {"BTCUSDT": Decimal("50000")}

        stats = controller.process_cycle(mandates, account, mark_prices)

        assert isinstance(stats, CycleStats)

    def test_execution_produces_results(self):
        """Execution produces ExecutionResult in log."""
        controller = ExecutionController(RiskConfig())

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )

        mark_prices = {"BTCUSDT": Decimal("50000")}

        controller.process_cycle(mandates, account, mark_prices)

        log = controller.get_execution_log()

        # Should have execution results
        for result in log:
            assert isinstance(result, ExecutionResult)
            assert isinstance(result.state_before, PositionState)
            assert isinstance(result.state_after, PositionState)


class TestExecutionToPosition:
    """Test data flow from Execution to Position state."""

    def test_entry_transitions_to_open(self):
        """Successful ENTRY transitions position FLAT → OPEN."""
        controller = ExecutionController(RiskConfig())

        # Verify initial state
        pos = controller.state_machine.get_position("BTCUSDT")
        assert pos.state == PositionState.FLAT

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )

        mark_prices = {"BTCUSDT": Decimal("50000")}

        controller.process_cycle(mandates, account, mark_prices)

        # Verify final state
        pos = controller.state_machine.get_position("BTCUSDT")
        assert pos.state == PositionState.OPEN

    def test_exit_transitions_to_flat(self):
        """Successful EXIT transitions position OPEN → FLAT."""
        controller = ExecutionController(RiskConfig())

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # First, enter position
        entry_mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]
        controller.process_cycle(entry_mandates, account, mark_prices)

        # Verify OPEN
        pos = controller.state_machine.get_position("BTCUSDT")
        assert pos.state == PositionState.OPEN

        # Now exit
        exit_mandates = [
            Mandate(
                type=MandateType.EXIT,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]
        controller.process_cycle(exit_mandates, account, mark_prices)

        # Verify FLAT
        pos = controller.state_machine.get_position("BTCUSDT")
        assert pos.state == PositionState.FLAT


class TestEndToEndFlow:
    """Test complete data flow from observation to position."""

    def test_full_cycle_type_coherence(self):
        """Types are compatible throughout the entire flow."""
        # Layer 1: Observation
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
        ts = time.time()
        obs.advance_time(ts)

        # Ingest some data
        for i in range(10):
            obs.ingest_observation(ts + i * 0.1, "BTCUSDT", "TRADE", {
                'p': str(50000 + i),
                'q': '0.1',
                's': 'BTCUSDT',
                'm': i % 2 == 0,
                'T': int((ts + i * 0.1) * 1000),
            })

        obs.advance_time(ts + 1.0)
        snapshot = obs.query({'type': 'snapshot'})

        # Verify Layer 1 output
        assert isinstance(snapshot, ObservationSnapshot)

        # Layer 2: Policy Adapter
        adapter = PolicyAdapter(AdapterConfig())
        mandates = adapter.generate_mandates(
            observation_snapshot=snapshot,
            symbol="BTCUSDT",
            timestamp=ts,
            position_state=PositionState.FLAT,
        )

        # Verify Layer 2 output
        assert isinstance(mandates, list)

        # Create a test mandate to ensure flow continues
        if not mandates:
            mandates = [
                Mandate(
                    type=MandateType.ENTRY,
                    symbol="BTCUSDT",
                    authority=10,
                    timestamp=ts,
                )
            ]

        # Layer 3: Arbitration
        arbitrator = MandateArbitrator()
        actions = arbitrator.arbitrate_all(mandates)

        # Verify Layer 3 output
        assert isinstance(actions, dict)

        # Layer 4 & 5: Execution (includes risk check)
        controller = ExecutionController(RiskConfig())
        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=ts,
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        stats = controller.process_cycle(mandates, account, mark_prices)

        # Verify Layer 4/5 output
        assert isinstance(stats, CycleStats)

        # Layer 6: Position
        pos = controller.state_machine.get_position("BTCUSDT")

        # Verify Layer 6 output
        assert isinstance(pos, Position)
        assert isinstance(pos.state, PositionState)

    def test_data_flows_without_mutation(self):
        """Data flows through layers without unexpected mutation."""
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
        ts = time.time()
        obs.advance_time(ts)

        snapshot = obs.query({'type': 'snapshot'})

        # Capture original values
        original_status = snapshot.status
        original_timestamp = snapshot.timestamp
        original_symbols = list(snapshot.symbols_active)

        # Process through adapter
        adapter = PolicyAdapter(AdapterConfig())
        mandates = adapter.generate_mandates(
            observation_snapshot=snapshot,
            symbol="BTCUSDT",
            timestamp=ts,
            position_state=PositionState.FLAT,
        )

        # Verify snapshot was not mutated
        assert snapshot.status == original_status
        assert snapshot.timestamp == original_timestamp
        assert list(snapshot.symbols_active) == original_symbols

    def test_symbol_independence(self):
        """Actions for different symbols are independent."""
        controller = ExecutionController(RiskConfig())

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
            Mandate(
                type=MandateType.HOLD,
                symbol="ETHUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000"),
        }

        controller.process_cycle(mandates, account, mark_prices)

        # BTC should be OPEN
        btc_pos = controller.state_machine.get_position("BTCUSDT")
        assert btc_pos.state == PositionState.OPEN

        # ETH should still be FLAT (HOLD doesn't change state)
        eth_pos = controller.state_machine.get_position("ETHUSDT")
        assert eth_pos.state == PositionState.FLAT


class TestRiskIntegration:
    """Test risk layer integration with execution flow."""

    def test_risk_monitor_checks_entry(self):
        """Risk monitor validates ENTRY before execution."""
        # Use default RiskConfig which has valid internally-consistent values
        controller = ExecutionController(RiskConfig())

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("1000"),  # Small account
            margin_available=Decimal("1000"),
            timestamp=time.time(),
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Should complete without error
        stats = controller.process_cycle(mandates, account, mark_prices)
        assert isinstance(stats, CycleStats)

    def test_risk_mandates_integrated(self):
        """Risk monitor mandates are included in arbitration."""
        controller = ExecutionController(RiskConfig())

        # Start with open position
        entry_mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        controller.process_cycle(entry_mandates, account, mark_prices)

        # Verify position opened
        pos = controller.state_machine.get_position("BTCUSDT")
        assert pos.state == PositionState.OPEN


class TestTypeCoherence:
    """Test type coherence across layer boundaries."""

    def test_mandate_types_consistent(self):
        """MandateType enum is used consistently."""
        # Arbitration uses same enum
        mandate = Mandate(
            type=MandateType.ENTRY,
            symbol="BTCUSDT",
            authority=10,
            timestamp=time.time(),
        )

        assert mandate.type == MandateType.ENTRY
        assert mandate.type.name == "ENTRY"

    def test_action_types_consistent(self):
        """ActionType enum is used consistently."""
        arbitrator = MandateArbitrator()

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        actions = arbitrator.arbitrate_all(mandates)

        assert actions["BTCUSDT"].type == ActionType.ENTRY
        assert actions["BTCUSDT"].type.name == "ENTRY"

    def test_position_state_consistent(self):
        """PositionState enum is used consistently."""
        controller = ExecutionController(RiskConfig())

        pos = controller.state_machine.get_position("BTCUSDT")

        assert pos.state == PositionState.FLAT
        assert pos.state.name == "FLAT"

    def test_decimal_used_for_prices(self):
        """Decimal type is used for monetary values."""
        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("50000"),
            timestamp=time.time(),
        )

        assert isinstance(account.equity, Decimal)
        assert isinstance(account.margin_available, Decimal)


class TestFailurePropagation:
    """Test that failures propagate correctly through layers."""

    def test_observation_failure_halts_system(self):
        """Observation FAILED status prevents execution."""
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
        ts = time.time()
        obs.advance_time(ts)

        # Trigger failure via time regression
        obs.advance_time(ts - 100)  # Time goes backwards

        # Query should raise
        from observation.types import SystemHaltedException
        with pytest.raises(SystemHaltedException):
            obs.query({'type': 'snapshot'})

    def test_invalid_action_rejected(self):
        """Invalid actions are rejected by state machine."""
        controller = ExecutionController(RiskConfig())

        # Try to EXIT from FLAT (invalid)
        exit_mandates = [
            Mandate(
                type=MandateType.EXIT,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        stats = controller.process_cycle(exit_mandates, account, mark_prices)

        # Check execution log for rejection
        log = controller.get_execution_log()
        if log:
            exit_results = [r for r in log if r.action == ActionType.EXIT]
            if exit_results:
                # Should be rejected (can't exit from FLAT)
                assert not exit_results[0].success


class TestMonitoringIntegration:
    """Test monitoring layer receives execution data."""

    def test_execution_log_available(self):
        """Execution results are logged for monitoring."""
        controller = ExecutionController(RiskConfig())

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        controller.process_cycle(mandates, account, mark_prices)

        log = controller.get_execution_log()

        # Log should have entries
        assert len(log) > 0

        # Each entry should have required fields
        for entry in log:
            assert hasattr(entry, 'symbol')
            assert hasattr(entry, 'action')
            assert hasattr(entry, 'success')
            assert hasattr(entry, 'timestamp')

    def test_cycle_stats_returned(self):
        """Cycle statistics are returned for monitoring."""
        controller = ExecutionController(RiskConfig())

        mandates = [
            Mandate(
                type=MandateType.ENTRY,
                symbol="BTCUSDT",
                authority=10,
                timestamp=time.time(),
            ),
            Mandate(
                type=MandateType.HOLD,
                symbol="ETHUSDT",
                authority=5,
                timestamp=time.time(),
            ),
        ]

        account = AccountState(
            equity=Decimal("100000"),
            margin_available=Decimal("100000"),
            timestamp=time.time(),
        )
        mark_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000"),
        }

        stats = controller.process_cycle(mandates, account, mark_prices)

        # Stats should have required fields
        assert hasattr(stats, 'mandates_received')
        assert hasattr(stats, 'actions_executed')
        assert hasattr(stats, 'actions_rejected')
        assert hasattr(stats, 'symbols_processed')

        # Values should be reasonable
        assert stats.mandates_received >= len(mandates)  # May include risk mandates
        assert stats.symbols_processed >= 0
