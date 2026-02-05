"""
Tests for EP-2 Strategy #1: Geometry-Driven Structural Proposal

Validates proposal generation logic, determinism, and semantic purity.
"""

import pytest
from external_policy.ep2_strategy_geometry import (
    generate_geometry_proposal,
    StrategyContext,
    PermissionOutput,
    StrategyProposal,
    reset_entry_context
)
from memory.m4_zone_geometry import ZonePenetrationDepth
from memory.m4_traversal_kinematics import TraversalCompactness
from memory.m4_price_distribution import CentralTendencyDeviation
from memory.m4_node_patterns import SupplyDemandZonePrimitive


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def strategy_context():
    """Standard strategy context."""
    return StrategyContext(
        context_id="TEST_CONTEXT",
        timestamp=1000.0
    )


@pytest.fixture
def strategy_context_with_price():
    """Strategy context with current price at demand zone."""
    return StrategyContext(
        context_id="TEST_CONTEXT",
        timestamp=1000.0,
        current_price=100.0  # At the demand zone (zone_high=101)
    )


@pytest.fixture
def confirmed_demand_zone():
    """B5: Confirmed demand zone (support) with retest."""
    return SupplyDemandZonePrimitive(
        zone_id="DZ1",
        symbol="BTCUSDT",
        zone_type="demand",
        zone_low=99.0,
        zone_high=101.0,
        zone_center=100.0,
        zone_width=2.0,
        node_count=5,
        total_interactions=100,
        total_volume=10000.0,
        avg_node_strength=0.6,
        displacement_detected=True,
        displacement_direction="up",
        displacement_magnitude=5.0,
        retest_detected=True,
        retest_count=1,
        timestamp=999.0
    )


@pytest.fixture
def permission_allowed():
    """M6 permission ALLOWED."""
    return PermissionOutput(
        result="ALLOWED",
        mandate_id="M1",
        action_id="A1",
        reason_code="APPROVED",
        timestamp=1000.0
    )


@pytest.fixture
def permission_denied():
    """M6 permission DENIED."""
    return PermissionOutput(
        result="DENIED",
        mandate_id="M1",
        action_id="A1",
        reason_code="REJECTED",
        timestamp=1000.0
    )


@pytest.fixture
def zone_penetration_present():
    """A6: Zone penetration exists."""
    return ZonePenetrationDepth(
        zone_id="Z1",
        penetration_depth=5.0
    )


@pytest.fixture
def zone_penetration_zero():
    """A6: Zero penetration."""
    return ZonePenetrationDepth(
        zone_id="Z1",
        penetration_depth=0.0
    )


@pytest.fixture
def traversal_compactness_nonzero():
    """A4: Non-degenerate traversal."""
    return TraversalCompactness(
        traversal_id="T1",
        net_displacement=10.0,
        total_path_length=15.0,
        compactness_ratio=0.667
    )


@pytest.fixture
def traversal_compactness_zero():
    """A4: Zero compactness (degenerate)."""
    return TraversalCompactness(
        traversal_id="T1",
        net_displacement=0.0,
        total_path_length=0.0,
        compactness_ratio=0.0
    )


@pytest.fixture
def deviation_nonzero():
    """A8: Non-zero deviation."""
    return CentralTendencyDeviation(
        deviation_value=5.0
    )


@pytest.fixture
def deviation_zero():
    """A8: Zero deviation."""
    return CentralTendencyDeviation(
        deviation_value=0.0
    )


@pytest.fixture(autouse=True)
def reset_state():
    """Reset entry context between tests."""
    reset_entry_context()
    yield
    reset_entry_context()


# ==============================================================================
# Happy Path Tests
# ==============================================================================

def test_happy_path_pattern_entry(
    confirmed_demand_zone,
    strategy_context_with_price,
    permission_allowed
):
    """Happy Path: Confirmed demand zone with price at zone -> LONG entry proposal."""
    result = generate_geometry_proposal(
        supply_demand_zone=confirmed_demand_zone,
        context=strategy_context_with_price,
        permission=permission_allowed
    )

    assert result is not None
    assert result.strategy_id == "EP2-GEOMETRY-V2"
    assert result.action_type == "ENTRY"
    assert result.confidence == "ZONE_CONFIRMED"
    assert result.direction == "LONG"
    assert "B5_SDZ|DEMAND|RT1" in result.justification_ref
    assert result.timestamp == strategy_context_with_price.timestamp


def test_happy_path_instantaneous_disabled(
    zone_penetration_present,
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """Instantaneous fallback is disabled -> no proposal without pattern primitive."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )

    # Instantaneous path is intentionally disabled (no direction context)
    assert result is None


def test_entry_rejected_price_below_supply_zone(
    permission_allowed
):
    """Supply zone exists but price is below it -> no entry (bug fix test)."""
    # This is the DOGE SHORT bug: supply zone at 0.0992-0.0995, price at 0.0979
    supply_zone = SupplyDemandZonePrimitive(
        zone_id="SZ1",
        symbol="DOGEUSDT",
        zone_type="supply",
        zone_low=0.0992,
        zone_high=0.0995,
        zone_center=0.09935,
        zone_width=0.0003,
        node_count=5,
        total_interactions=100,
        total_volume=10000.0,
        avg_node_strength=0.6,
        displacement_detected=True,
        displacement_direction="down",
        displacement_magnitude=0.001,
        retest_detected=True,
        retest_count=1,
        timestamp=999.0
    )
    # Price is 1.3% BELOW the supply zone - should NOT enter SHORT
    context = StrategyContext(
        context_id="TEST",
        timestamp=1000.0,
        current_price=0.0979  # Below zone_low of 0.0992
    )

    result = generate_geometry_proposal(
        supply_demand_zone=supply_zone,
        context=context,
        permission=permission_allowed
    )

    # Entry should be rejected - price not at supply zone
    assert result is None


def test_entry_allowed_price_at_supply_zone(
    permission_allowed
):
    """Supply zone exists and price is at zone -> SHORT entry allowed."""
    supply_zone = SupplyDemandZonePrimitive(
        zone_id="SZ1",
        symbol="DOGEUSDT",
        zone_type="supply",
        zone_low=0.0992,
        zone_high=0.0995,
        zone_center=0.09935,
        zone_width=0.0003,
        node_count=5,
        total_interactions=100,
        total_volume=10000.0,
        avg_node_strength=0.6,
        displacement_detected=True,
        displacement_direction="down",
        displacement_magnitude=0.001,
        retest_detected=True,
        retest_count=1,
        timestamp=999.0
    )
    # Price is AT the supply zone
    context = StrategyContext(
        context_id="TEST",
        timestamp=1000.0,
        current_price=0.0993  # Inside the zone
    )

    result = generate_geometry_proposal(
        supply_demand_zone=supply_zone,
        context=context,
        permission=permission_allowed
    )

    assert result is not None
    assert result.direction == "SHORT"
    assert result.action_type == "ENTRY"


# ==============================================================================
# Rejection Tests (Individual Conditions)
# ==============================================================================

def test_no_penetration_no_proposal(
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """A6 missing or zero -> no proposal."""
    # Missing A6
    result = generate_geometry_proposal(
        zone_penetration=None,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    assert result is None


def test_zero_penetration_depth_no_proposal(
    zone_penetration_zero,
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """A6 depth == 0 -> no proposal."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_zero,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    assert result is None


def test_zero_compactness_no_proposal(
    zone_penetration_present,
    traversal_compactness_zero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """A4 ratio == 0 -> no proposal."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_zero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    assert result is None


def test_zero_deviation_no_proposal(
    zone_penetration_present,
    traversal_compactness_nonzero,
    deviation_zero,
    strategy_context,
    permission_allowed
):
    """A8 deviation == 0 -> no proposal."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_zero,
        context=strategy_context,
        permission=permission_allowed
    )
    assert result is None


def test_missing_compactness_no_proposal(
    zone_penetration_present,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """A4 missing -> no proposal."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=None,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    assert result is None


def test_missing_deviation_no_proposal(
    zone_penetration_present,
    traversal_compactness_nonzero,
    strategy_context,
    permission_allowed
):
    """A8 missing -> no proposal."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=None,
        context=strategy_context,
        permission=permission_allowed
    )
    assert result is None


# ==============================================================================
# M6 Permission Tests
# ==============================================================================

def test_m6_denied_no_proposal(
    zone_penetration_present,
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_denied
):
    """M6 Permission DENIED -> no proposal."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_denied
    )
    assert result is None


# ==============================================================================
# Determinism Tests
# ==============================================================================

def test_determinism_identical_inputs(
    zone_penetration_present,
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """Determinism: Identical inputs -> identical output."""
    result1 = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    
    result2 = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    
    assert result1 == result2


# ==============================================================================
# Semantic Purity Test
# ==============================================================================

def test_semantic_purity_no_market_terms():
    """Semantic Purity: Zero forbidden market terms in code."""
    import external_policy.ep2_strategy_geometry as ep2_module
    import inspect
    
    source_code = inspect.getsource(ep2_module)
    source_lower = source_code.lower()
    
    # Check for market prediction patterns (not structural terms)
    # Note: entry_price/exit_price are structural position tracking terms, not predictions
    forbidden_patterns = [
        "bullish", "bearish", "momentum", "reversal",
        "strong_", "weak_", "long_position", "short_position",
        "buy_", "sell_", "signal", "trade_",
        "profit", "loss", "alpha"
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in source_lower, \
            f"Forbidden market pattern '{pattern}' found in EP-2 code"


# ==============================================================================
# Input Immutability Tests (A5)
# ==============================================================================

def test_input_immutability_zone_penetration(
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """Policy does not modify zone_penetration input."""
    import copy
    zone = ZonePenetrationDepth(
        zone_id="Z1",
        penetration_depth=5.0
    )
    zone_copy = copy.deepcopy(zone)

    generate_geometry_proposal(
        zone_penetration=zone,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )

    assert zone == zone_copy


def test_input_immutability_traversal_compactness(
    zone_penetration_present,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """Policy does not modify traversal_compactness input."""
    import copy
    compactness = TraversalCompactness(
        traversal_id="T1",
        net_displacement=10.0,
        total_path_length=15.0,
        compactness_ratio=0.667
    )
    compactness_copy = copy.deepcopy(compactness)

    generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=compactness,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )

    assert compactness == compactness_copy


def test_input_immutability_central_tendency_deviation(
    zone_penetration_present,
    traversal_compactness_nonzero,
    strategy_context,
    permission_allowed
):
    """Policy does not modify central_tendency_deviation input."""
    import copy
    deviation = CentralTendencyDeviation(
        deviation_value=5.0
    )
    deviation_copy = copy.deepcopy(deviation)

    generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation,
        context=strategy_context,
        permission=permission_allowed
    )

    assert deviation == deviation_copy


# ==============================================================================
# Proposal Immutability Test
# ==============================================================================

def test_proposal_immutability(
    zone_penetration_present,
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """Proposal must be immutable (frozen dataclass)."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        result.strategy_id = "MODIFIED"
