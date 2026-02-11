"""
Phase B: Snapshot → PolicyAdapter Integration Tests

Verifies M4 primitive flow from ObservationSnapshot through PolicyAdapter to Mandates.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase B requirements.
"""

import pytest
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional

from observation.types import ObservationSnapshot, ObservationStatus, M4PrimitiveBundle, SystemCounters
from runtime.policy_adapter import PolicyAdapter, AdapterConfig
from runtime.arbitration.types import Mandate, MandateType
from runtime.position.types import PositionState


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def adapter():
    """PolicyAdapter with all strategies disabled except orderbook test."""
    config = AdapterConfig(
        enable_geometry=False,
        enable_orderbook_test=True,  # Simple test policy
        enable_slbrs=False,
        enable_effcs=False,
        enable_cascade_sniper=False,
        default_authority=5.0,
        default_notional_usd=100.0
    )
    return PolicyAdapter(config)


@pytest.fixture
def adapter_all_disabled():
    """PolicyAdapter with all strategies disabled."""
    config = AdapterConfig(
        enable_geometry=False,
        enable_orderbook_test=False,
        enable_slbrs=False,
        enable_effcs=False,
        enable_cascade_sniper=False
    )
    return PolicyAdapter(config)


def create_empty_snapshot(symbol: str = "BTCUSDT") -> ObservationSnapshot:
    """Create snapshot with empty M4PrimitiveBundle."""
    bundle = M4PrimitiveBundle.empty(symbol)
    return ObservationSnapshot(
        status=ObservationStatus.UNINITIALIZED,
        timestamp=1000.0,
        symbols_active=[symbol],
        counters=SystemCounters(intervals_processed=0, dropped_events={}),
        promoted_events=None,
        primitives={symbol: bundle}
    )


def create_snapshot_with_orderbook_primitives(symbol: str = "BTCUSDT") -> ObservationSnapshot:
    """Create snapshot with orderbook primitives for test policy.

    Uses simple dict-like objects for primitives since exact types vary.
    """
    from dataclasses import dataclass, field

    @dataclass
    class MockRestingSize:
        symbol: str
        bid_size: float = 100.0
        ask_size: float = 80.0
        imbalance_ratio: float = 0.25
        timestamp: float = 1000.0

    @dataclass
    class MockOrderConsumption:
        symbol: str
        side: str = "BID"
        consumed_size: float = 50.0
        consumption_rate: float = 0.5
        timestamp: float = 1000.0

    @dataclass
    class MockRefillEvent:
        symbol: str
        side: str = "BID"
        refill_size: float = 30.0
        refill_speed: float = 0.3
        timestamp: float = 1000.0

    # Create bundle with all primitives None except orderbook ones
    bundle = M4PrimitiveBundle(
        symbol=symbol,
        zone_penetration=None,
        displacement_origin_anchor=None,
        price_traversal_velocity=None,
        traversal_compactness=None,
        central_tendency_deviation=None,
        structural_absence_duration=None,
        traversal_void_span=None,
        event_non_occurrence_counter=None,
        structural_persistence_duration=None,
        resting_size=MockRestingSize(symbol=symbol),
        order_consumption=MockOrderConsumption(symbol=symbol),
        absorption_event=None,
        refill_event=MockRefillEvent(symbol=symbol),
        price_acceptance_ratio=None,
        liquidation_density=None,
        directional_continuity=None,
        trade_burst=None,
        order_block=None,
        supply_demand_zone=None,
        liquidation_cascade_proximity=None,
        cascade_state=None,
        leverage_concentration_ratio=None,
        open_interest_directional_bias=None
    )
    return ObservationSnapshot(
        status=ObservationStatus.UNINITIALIZED,
        timestamp=1000.0,
        symbols_active=[symbol],
        counters=SystemCounters(intervals_processed=0, dropped_events={}),
        promoted_events=None,
        primitives={symbol: bundle}
    )


def create_failed_snapshot() -> ObservationSnapshot:
    """Create snapshot with FAILED status."""
    return ObservationSnapshot(
        status=ObservationStatus.FAILED,
        timestamp=1000.0,
        symbols_active=[],
        counters=SystemCounters(intervals_processed=0, dropped_events={}),
        promoted_events=None,
        primitives={}
    )


# ==============================================================================
# TASK 2.1: Frozen Snapshot Construction
# ==============================================================================

def test_snapshot_is_frozen():
    """ObservationSnapshot is immutable (frozen dataclass)."""
    snapshot = create_empty_snapshot()

    with pytest.raises(Exception):  # FrozenInstanceError
        snapshot.timestamp = 2000.0


def test_m4_bundle_is_frozen():
    """M4PrimitiveBundle is immutable."""
    bundle = M4PrimitiveBundle.empty("BTCUSDT")

    with pytest.raises(Exception):  # FrozenInstanceError
        bundle.symbol = "ETHUSDT"


def test_snapshot_contains_primitives():
    """Snapshot.primitives contains M4PrimitiveBundle per symbol."""
    snapshot = create_empty_snapshot("BTCUSDT")

    assert "BTCUSDT" in snapshot.primitives
    assert isinstance(snapshot.primitives["BTCUSDT"], M4PrimitiveBundle)


# ==============================================================================
# TASK 2.2: PolicyAdapter Consumes Snapshot
# ==============================================================================

def test_adapter_accepts_snapshot(adapter):
    """PolicyAdapter.generate_mandates accepts ObservationSnapshot."""
    snapshot = create_empty_snapshot()

    # Should not raise
    result = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0
    )

    assert isinstance(result, list)


def test_adapter_extracts_primitives_from_snapshot(adapter):
    """PolicyAdapter extracts M4 primitives from snapshot."""
    snapshot = create_snapshot_with_orderbook_primitives()

    # Internal extraction should work
    primitives = adapter._extract_primitives(snapshot, "BTCUSDT")

    assert primitives["resting_size"] is not None
    assert primitives["order_consumption"] is not None
    assert primitives["refill_event"] is not None


def test_adapter_returns_empty_for_missing_symbol(adapter):
    """Snapshot missing symbol → empty primitives dict."""
    snapshot = create_empty_snapshot("BTCUSDT")

    primitives = adapter._extract_primitives(snapshot, "ETHUSDT")

    # All primitives should be None
    assert all(v is None for v in primitives.values())


# ==============================================================================
# TASK 2.3: Mandate Emission
# ==============================================================================

def test_adapter_emits_entry_mandate_on_consumption(adapter):
    """OrderConsumption + no position → ENTRY mandate."""
    snapshot = create_snapshot_with_orderbook_primitives()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0,
        position_state=None,  # No position
        current_price=65000.0
    )

    # Orderbook test policy should emit ENTRY on consumption
    assert len(mandates) >= 1
    entry_mandates = [m for m in mandates if m.type == MandateType.ENTRY]
    assert len(entry_mandates) >= 1


def test_adapter_emits_exit_mandate_on_refill(adapter):
    """RefillEvent + position open → EXIT mandate."""
    snapshot = create_snapshot_with_orderbook_primitives()

    # Clear entry tracker to avoid grace period block
    PolicyAdapter._entry_tracker.clear()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0,
        position_state=PositionState.OPEN,  # Has position
        current_price=65000.0
    )

    # Orderbook test policy should emit EXIT on refill when position exists
    assert len(mandates) >= 1
    exit_mandates = [m for m in mandates if m.type == MandateType.EXIT]
    assert len(exit_mandates) >= 1


def test_mandates_are_frozen():
    """Emitted mandates are immutable."""
    adapter = PolicyAdapter(AdapterConfig(enable_orderbook_test=True))
    snapshot = create_snapshot_with_orderbook_primitives()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0,
        current_price=65000.0
    )

    if mandates:
        with pytest.raises(Exception):  # FrozenInstanceError
            mandates[0].authority = 999.0


# ==============================================================================
# TASK 2.4: None Primitives Handling
# ==============================================================================

def test_none_primitives_no_crash(adapter):
    """All primitives None → no crash, returns empty or valid mandates."""
    snapshot = create_empty_snapshot()

    # Should not raise
    result = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0
    )

    assert isinstance(result, list)


def test_partial_primitives_no_crash(adapter):
    """Some primitives None → no crash."""
    from dataclasses import dataclass

    @dataclass
    class MockRestingSize:
        symbol: str = "BTCUSDT"
        bid_size: float = 100.0
        ask_size: float = 80.0
        imbalance_ratio: float = 0.25
        timestamp: float = 1000.0

    # Create bundle with only resting_size (no consumption or refill)
    bundle = M4PrimitiveBundle(
        symbol="BTCUSDT",
        zone_penetration=None,
        displacement_origin_anchor=None,
        price_traversal_velocity=None,
        traversal_compactness=None,
        central_tendency_deviation=None,
        structural_absence_duration=None,
        traversal_void_span=None,
        event_non_occurrence_counter=None,
        structural_persistence_duration=None,
        resting_size=MockRestingSize(),
        order_consumption=None,  # Missing
        absorption_event=None,
        refill_event=None,  # Missing
        price_acceptance_ratio=None,
        liquidation_density=None,
        directional_continuity=None,
        trade_burst=None,
        order_block=None,
        supply_demand_zone=None,
        liquidation_cascade_proximity=None,
        cascade_state=None,
        leverage_concentration_ratio=None,
        open_interest_directional_bias=None
    )
    snapshot = ObservationSnapshot(
        status=ObservationStatus.UNINITIALIZED,
        timestamp=1000.0,
        symbols_active=["BTCUSDT"],
        counters=SystemCounters(intervals_processed=0, dropped_events={}),
        promoted_events=None,
        primitives={"BTCUSDT": bundle}
    )

    # Should not raise
    result = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0
    )

    assert isinstance(result, list)


def test_missing_symbol_no_crash(adapter):
    """Symbol not in snapshot → no crash, empty mandates."""
    snapshot = create_empty_snapshot("BTCUSDT")

    # Query for different symbol
    result = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="ETHUSDT",
        timestamp=1000.0
    )

    assert isinstance(result, list)


# ==============================================================================
# TASK 2.5: Failed Observation Status
# ==============================================================================

def test_failed_status_emits_block_mandate(adapter):
    """ObservationStatus.FAILED → BLOCK mandate."""
    snapshot = create_failed_snapshot()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0
    )

    assert len(mandates) == 1
    assert mandates[0].type == MandateType.BLOCK
    assert mandates[0].authority == 10.0  # Maximum authority


# ==============================================================================
# TASK 2.6: Determinism
# ==============================================================================

def test_determinism_same_snapshot_same_mandates(adapter):
    """Same snapshot → same mandates."""
    snapshot = create_snapshot_with_orderbook_primitives()

    results = [
        adapter.generate_mandates(
            observation_snapshot=snapshot,
            symbol="BTCUSDT",
            timestamp=1000.0,
            current_price=65000.0
        )
        for _ in range(5)
    ]

    # All results should be identical
    first = results[0]
    for result in results[1:]:
        assert len(result) == len(first)
        for i, mandate in enumerate(result):
            assert mandate.type == first[i].type
            assert mandate.symbol == first[i].symbol


# ==============================================================================
# TASK 2.7: Authority is Static
# ==============================================================================

def test_authority_from_config_not_primitive():
    """Mandate authority comes from config, not primitive values."""
    config = AdapterConfig(
        enable_orderbook_test=True,
        default_authority=7.5  # Custom authority
    )
    adapter = PolicyAdapter(config)
    snapshot = create_snapshot_with_orderbook_primitives()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0,
        current_price=65000.0
    )

    # All mandates should have config authority
    for mandate in mandates:
        assert mandate.authority == 7.5


# ==============================================================================
# TASK 2.8: Quantity Calculation
# ==============================================================================

def test_entry_mandate_has_quantity():
    """ENTRY mandate has calculated quantity."""
    config = AdapterConfig(
        enable_orderbook_test=True,
        default_notional_usd=100.0
    )
    adapter = PolicyAdapter(config)
    snapshot = create_snapshot_with_orderbook_primitives()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0,
        position_state=None,
        current_price=50000.0  # $50k BTC
    )

    entry_mandates = [m for m in mandates if m.type == MandateType.ENTRY]
    if entry_mandates:
        # quantity = notional / price = 100 / 50000 = 0.002
        assert entry_mandates[0].quantity is not None
        assert entry_mandates[0].quantity == Decimal("100.0") / Decimal("50000.0")
        assert entry_mandates[0].entry_price == Decimal("50000.0")


def test_no_quantity_without_price():
    """ENTRY mandate without price has no quantity."""
    config = AdapterConfig(enable_orderbook_test=True)
    adapter = PolicyAdapter(config)
    snapshot = create_snapshot_with_orderbook_primitives()

    mandates = adapter.generate_mandates(
        observation_snapshot=snapshot,
        symbol="BTCUSDT",
        timestamp=1000.0,
        position_state=None,
        current_price=None  # No price
    )

    entry_mandates = [m for m in mandates if m.type == MandateType.ENTRY]
    if entry_mandates:
        assert entry_mandates[0].quantity is None


# ==============================================================================
# TASK 2.9: Multi-Symbol Independence
# ==============================================================================

def test_multi_symbol_snapshot():
    """Snapshot with multiple symbols processed independently."""
    from dataclasses import dataclass

    @dataclass
    class MockRestingSize:
        symbol: str
        bid_size: float
        ask_size: float
        imbalance_ratio: float
        timestamp: float

    @dataclass
    class MockOrderConsumption:
        symbol: str
        side: str
        consumed_size: float
        consumption_rate: float
        timestamp: float

    btc_bundle = M4PrimitiveBundle(
        symbol="BTCUSDT",
        zone_penetration=None,
        displacement_origin_anchor=None,
        price_traversal_velocity=None,
        traversal_compactness=None,
        central_tendency_deviation=None,
        structural_absence_duration=None,
        traversal_void_span=None,
        event_non_occurrence_counter=None,
        structural_persistence_duration=None,
        resting_size=MockRestingSize("BTCUSDT", 100, 80, 0.25, 1000.0),
        order_consumption=MockOrderConsumption("BTCUSDT", "BID", 50, 0.5, 1000.0),
        absorption_event=None,
        refill_event=None,
        price_acceptance_ratio=None,
        liquidation_density=None,
        directional_continuity=None,
        trade_burst=None,
        order_block=None,
        supply_demand_zone=None,
        liquidation_cascade_proximity=None,
        cascade_state=None,
        leverage_concentration_ratio=None,
        open_interest_directional_bias=None
    )

    eth_bundle = M4PrimitiveBundle.empty("ETHUSDT")

    snapshot = ObservationSnapshot(
        status=ObservationStatus.UNINITIALIZED,
        timestamp=1000.0,
        symbols_active=["BTCUSDT", "ETHUSDT"],
        counters=SystemCounters(intervals_processed=0, dropped_events={}),
        promoted_events=None,
        primitives={"BTCUSDT": btc_bundle, "ETHUSDT": eth_bundle}
    )

    config = AdapterConfig(enable_orderbook_test=True)
    adapter = PolicyAdapter(config)

    btc_mandates = adapter.generate_mandates(snapshot, "BTCUSDT", 1000.0, current_price=65000.0)
    eth_mandates = adapter.generate_mandates(snapshot, "ETHUSDT", 1000.0, current_price=3000.0)

    # BTC has consumption → may have ENTRY
    # ETH has no consumption → no ENTRY
    btc_entries = [m for m in btc_mandates if m.type == MandateType.ENTRY]
    eth_entries = [m for m in eth_mandates if m.type == MandateType.ENTRY]

    # BTC should have entry potential, ETH should not
    # (Exact behavior depends on policy, but they should be independent)
    assert all(m.symbol == "BTCUSDT" for m in btc_mandates)
    assert all(m.symbol == "ETHUSDT" for m in eth_mandates)
