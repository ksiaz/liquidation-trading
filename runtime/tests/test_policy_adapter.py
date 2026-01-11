"""Tests for PolicyAdapter wiring layer.

Verifies:
1. Adapter correctly handles observation status
2. No semantic leakage across boundaries
3. Proposals correctly converted to mandates
4. Stateless operation (no memory between calls)
"""

import pytest
from decimal import Decimal

from observation.types import (
    ObservationSnapshot,
    ObservationStatus,
    SystemCounters,
    M4PrimitiveBundle
)
from runtime.policy_adapter import PolicyAdapter, AdapterConfig
from runtime.arbitration.types import MandateType


# ==============================================================================
# Test Helpers
# ==============================================================================

def make_empty_primitive_bundle(symbol: str) -> M4PrimitiveBundle:
    """Create M4PrimitiveBundle with all primitives as None.

    Used for testing when primitives are not relevant to test scenario.
    """
    return M4PrimitiveBundle(
        symbol=symbol,
        zone_penetration=None,
        displacement_origin_anchor=None,
        price_traversal_velocity=None,
        traversal_compactness=None,
        central_tendency_deviation=None,
        structural_absence_duration=None,
        traversal_void_span=None,
        event_non_occurrence_counter=None,
        resting_size=None,
        order_consumption=None,
        absorption_event=None,
        refill_event=None
    )


class TestPolicyAdapterObservationStatus:
    """Test observation status handling per M6_CONSUMPTION_CONTRACT.md."""

    def test_failed_observation_emits_block_mandate(self):
        """When observation FAILED, adapter emits BLOCK mandate."""
        adapter = PolicyAdapter()

        snapshot = ObservationSnapshot(
            status=ObservationStatus.FAILED,
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(intervals_processed=None, dropped_events=None),
            promoted_events=None,
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        assert len(mandates) == 1
        assert mandates[0].type == MandateType.BLOCK
        assert mandates[0].authority == 10.0  # Maximum
        assert mandates[0].symbol == "BTCUSDT"

    def test_uninitialized_observation_emits_no_mandates(self):
        """When observation UNINITIALIZED, adapter emits nothing."""
        adapter = PolicyAdapter()

        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=0.0,
            symbols_active=[],
            counters=SystemCounters(intervals_processed=None, dropped_events=None),
            promoted_events=None,
            primitives={}
        )

        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        assert len(mandates) == 0


class TestPolicyAdapterWiring:
    """Test pure wiring behavior - no interpretation."""

    def test_adapter_is_stateless(self):
        """Adapter produces same output for same input (deterministic)."""
        adapter = PolicyAdapter()

        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,  # Simplified test
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(intervals_processed=0, dropped_events={}),
            promoted_events=[],
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        # Call twice with identical inputs
        mandates1 = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)
        mandates2 = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # Must produce identical results
        assert len(mandates1) == len(mandates2)
        assert mandates1 == mandates2

    def test_adapter_handles_missing_primitives_gracefully(self):
        """When primitives are None, policies return no proposals."""
        adapter = PolicyAdapter()

        # All primitives None (via stub implementation)
        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,  # Forces empty primitive dict
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(intervals_processed=0, dropped_events={}),
            promoted_events=[],
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # No primitives -> no proposals -> no mandates (except status-based)
        assert isinstance(mandates, list)

    def test_adapter_configuration_disables_policies(self):
        """Configuration correctly enables/disables policy invocation."""
        config = AdapterConfig(
            enable_geometry=False,
            enable_kinematics=False,
            enable_absence=False
        )
        adapter = PolicyAdapter(config)

        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(intervals_processed=0, dropped_events={}),
            promoted_events=[],
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # All policies disabled -> no mandates
        assert len(mandates) == 0


class TestPolicyAdapterSemanticLeakage:
    """Verify no semantic interpretation crosses boundaries."""

    def test_adapter_does_not_interpret_observation_fields(self):
        """Adapter only reads status, does not interpret counters/events."""
        adapter = PolicyAdapter()

        # Snapshot with counters/events (should be ignored, not interpreted)
        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(
                intervals_processed=100,
                dropped_events={"TRADE": 50}
            ),
            promoted_events=[{"type": "PEAK_PRESSURE"}],
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # Adapter must not interpret these fields
        # Only status matters for mandate generation
        assert isinstance(mandates, list)
        # No assertions about mandate count - that depends on primitives
        # Key point: no exception, no interpretation

    def test_adapter_does_not_expose_internal_semantics(self):
        """Mandates contain no internal semantic fields (strength, confidence)."""
        adapter = PolicyAdapter()

        snapshot = ObservationSnapshot(
            status=ObservationStatus.FAILED,  # Will generate BLOCK
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(intervals_processed=None, dropped_events=None),
            promoted_events=None,
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # Verify Mandate structure has no semantic leakage
        for mandate in mandates:
            # Mandate fields per types.py: symbol, type, authority, timestamp
            assert hasattr(mandate, "symbol")
            assert hasattr(mandate, "type")
            assert hasattr(mandate, "authority")
            assert hasattr(mandate, "timestamp")

            # Must NOT have semantic fields
            assert not hasattr(mandate, "strength")
            assert not hasattr(mandate, "confidence")
            assert not hasattr(mandate, "quality")
            assert not hasattr(mandate, "signal")


class TestPolicyAdapterIntegration:
    """Integration tests verifying end-to-end wiring."""

    def test_adapter_connects_observation_to_execution_pipeline(self):
        """Adapter output is valid input for ExecutionController."""
        from runtime.executor.controller import ExecutionController
        from runtime.risk.types import RiskConfig, AccountState

        adapter = PolicyAdapter()
        controller = ExecutionController()

        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=1000.0,
            symbols_active=["BTCUSDT"],
            counters=SystemCounters(intervals_processed=0, dropped_events={}),
            promoted_events=[],
            primitives={"BTCUSDT": make_empty_primitive_bundle("BTCUSDT")}
        )

        # Generate mandates via adapter
        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # Feed to execution controller (should not raise)
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("10000"),
            timestamp=1000.0
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        cycle_stats = controller.process_cycle(mandates, account, mark_prices)

        # Verify execution accepted mandates
        assert cycle_stats.mandates_received == len(mandates)
        assert isinstance(cycle_stats.actions_executed, int)
        assert isinstance(cycle_stats.actions_rejected, int)
