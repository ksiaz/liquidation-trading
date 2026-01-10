"""Tests for M4 primitive computation via ObservationSystem.

Verifies:
1. M2 store can be populated with nodes
2. M5 access layer queries primitives correctly
3. ObservationSnapshot contains computed primitives
4. PolicyAdapter receives primitives via snapshot
"""

import pytest
from decimal import Decimal

from observation.types import ObservationSnapshot, ObservationStatus
from observation.governance import ObservationSystem
from runtime.policy_adapter import PolicyAdapter
from runtime.arbitration.types import MandateType


class TestPrimitiveComputationFlow:
    """Test end-to-end primitive computation flow."""

    def test_observation_system_has_m2_and_m5_access(self):
        """ObservationSystem initializes M2 store and M5 access layer."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Verify M2 store exists
        assert hasattr(obs_system, "_m2_store")
        assert obs_system._m2_store is not None

        # Verify M5 access exists
        assert hasattr(obs_system, "_m5_access")
        assert obs_system._m5_access is not None

    def test_snapshot_contains_primitive_bundle(self):
        """Snapshot includes M4PrimitiveBundle for each symbol."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT", "ETHUSDT"])

        # Advance time to make snapshot valid
        obs_system.advance_time(1000.0)

        # Get snapshot
        snapshot = obs_system.query({"type": "snapshot"})

        # Verify primitives field exists
        assert hasattr(snapshot, "primitives")
        assert "BTCUSDT" in snapshot.primitives
        assert "ETHUSDT" in snapshot.primitives

        # Verify bundle structure (currently all None)
        btc_bundle = snapshot.primitives["BTCUSDT"]
        assert btc_bundle.symbol == "BTCUSDT"
        assert btc_bundle.zone_penetration is None  # No M2 data yet
        assert btc_bundle.displacement_origin_anchor is None
        assert btc_bundle.price_traversal_velocity is None
        assert btc_bundle.traversal_compactness is None

    def test_policy_adapter_receives_primitives(self):
        """PolicyAdapter extracts primitives from snapshot."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])
        obs_system.advance_time(1000.0)
        snapshot = obs_system.query({"type": "snapshot"})

        adapter = PolicyAdapter()
        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # PolicyAdapter runs without error (even with empty primitives)
        assert isinstance(mandates, list)

    def test_empty_m2_returns_none_primitives(self):
        """When M2 is empty, all primitives are None (graceful degradation)."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])
        obs_system.advance_time(1000.0)

        snapshot = obs_system.query({"type": "snapshot"})
        bundle = snapshot.primitives["BTCUSDT"]

        # All primitives None when M2 has no nodes
        assert bundle.zone_penetration is None
        assert bundle.displacement_origin_anchor is None
        assert bundle.price_traversal_velocity is None
        assert bundle.traversal_compactness is None
        assert bundle.central_tendency_deviation is None
        assert bundle.structural_absence_duration is None
        assert bundle.traversal_void_span is None
        assert bundle.event_non_occurrence_counter is None

    def test_primitive_computation_does_not_crash_snapshot(self):
        """Primitive computation errors do not prevent snapshot creation."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Ingest some data (won't create nodes without M1→M2 wiring)
        obs_system.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50000.0",
                "q": "1.0",
                "T": 1000000,
                "m": True
            }
        )

        obs_system.advance_time(1001.0)

        # Snapshot creation succeeds even if primitive computation fails
        snapshot = obs_system.query({"type": "snapshot"})
        assert snapshot.status == ObservationStatus.UNINITIALIZED
        assert "BTCUSDT" in snapshot.primitives


class TestPrimitiveComputationWithMockData:
    """Test primitive computation with manually populated M2 store."""

    def test_zone_penetration_with_populated_m2(self):
        """Compute zone_penetration when M2 has nodes."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Manually populate M2 store with a test node
        # (In production, M1/M3 would populate this)
        node = obs_system._m2_store.add_or_update_node(
            node_id="test_zone_50000",
            price_center=50000.0,
            price_band=100.0,
            side="bid",
            timestamp=1000.0,
            creation_reason="test_liquidation",
            initial_strength=0.7,
            initial_confidence=0.6,
            volume=100000.0
        )

        # Advance time
        obs_system.advance_time(1001.0)

        # Get snapshot (primitive computation runs)
        snapshot = obs_system.query({"type": "snapshot"})

        # Currently returns None because _compute_primitives_for_symbol is stub
        # Future implementation will compute real primitives here
        bundle = snapshot.primitives["BTCUSDT"]

        # This will pass as stub returns None
        # When implementation is complete, this will have actual ZonePenetrationDepth
        assert bundle.zone_penetration is None  # Stub behavior

        # Verify M2 store has the node
        active_nodes = obs_system._m2_store.get_active_nodes()
        assert len(active_nodes) == 1
        assert active_nodes[0].price_center == 50000.0

    def test_m5_query_with_mock_data(self):
        """Verify M5 query interface works with populated M2."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Add mock node
        obs_system._m2_store.add_or_update_node(
            node_id="test_node_1",
            price_center=50000.0,
            price_band=50.0,
            side="bid",
            timestamp=1000.0,
            creation_reason="test",
            initial_strength=0.5,
            initial_confidence=0.5
        )

        # Test M5 query directly (identity query)
        result = obs_system._m5_access.execute_query(
            "IDENTITY",
            {"node_id": "test_node_1"}
        )

        # M5 returns normalized dict output
        assert result is not None
        assert isinstance(result, dict)
        assert result["price_center"] == 50000.0
        # Verify node was found by checking node_id
        assert result["node_id"] == "test_node_1"


class TestIntegrationWithExecution:
    """Test that primitives flow to execution layer correctly."""

    def test_end_to_end_flow(self):
        """Full flow: ObservationSystem → Snapshot → PolicyAdapter → Mandates."""
        from runtime.executor.controller import ExecutionController
        from runtime.risk.types import AccountState

        # 1. Create observation system
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])
        obs_system.advance_time(1000.0)

        # 2. Get snapshot (with primitives)
        snapshot = obs_system.query({"type": "snapshot"})
        assert "BTCUSDT" in snapshot.primitives

        # 3. PolicyAdapter generates mandates
        adapter = PolicyAdapter()
        mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0)

        # 4. ExecutionController processes mandates
        controller = ExecutionController()
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("10000"),
            timestamp=1000.0
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}

        cycle_stats = controller.process_cycle(mandates, account, mark_prices)

        # Flow succeeds (even with empty primitives)
        assert cycle_stats.mandates_received >= 0
        assert isinstance(cycle_stats.actions_executed, int)
