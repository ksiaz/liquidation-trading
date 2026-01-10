"""
Tests for EP-2 Strategy #1: Geometry-Driven Structural Proposal

Validates proposal generation logic, determinism, and semantic purity.
"""

import pytest
from external_policy.ep2_strategy_geometry import (
    generate_geometry_proposal,
    StrategyContext,
    PermissionOutput,
    StrategyProposal
)
from memory.m4_zone_geometry import ZonePenetrationDepth
from memory.m4_traversal_kinematics import TraversalCompactness
from memory.m4_price_distribution import CentralTendencyDeviation


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


# ==============================================================================
# Happy Path Tests
# ==============================================================================

def test_happy_path_all_conditions_met(
    zone_penetration_present,
    traversal_compactness_nonzero,
    deviation_nonzero,
    strategy_context,
    permission_allowed
):
    """Happy Path: All three primitives present -> proposal emitted."""
    result = generate_geometry_proposal(
        zone_penetration=zone_penetration_present,
        traversal_compactness=traversal_compactness_nonzero,
        central_tendency_deviation=deviation_nonzero,
        context=strategy_context,
        permission=permission_allowed
    )
    
    assert result is not None
    assert result.strategy_id == "EP2-GEOMETRY-V1"
    assert result.action_type == "STRUCTURAL_GEOMETRY_EVENT"
    assert result.confidence == "STRUCTURAL_PRESENT"
    assert result.justification_ref == "A6|A4|A8"
    assert result.timestamp == strategy_context.timestamp


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
    
    # Check for market-specific patterns
    forbidden_patterns = [
        "bullish", "bearish", "momentum", "reversal",
        "strong_", "weak_", "long_position", "short_position",
        "buy_", "sell_", "signal", "trade_",
        "profit", "loss", "alpha", "edge",
        "entry_price", "exit_price"
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in source_lower, \
            f"Forbidden market pattern '{pattern}' found in EP-2 code"


# ==============================================================================
# Immutability Test
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
