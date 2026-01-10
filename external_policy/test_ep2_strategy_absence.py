"""
Tests for EP-2 Strategy #3: Absence-Driven Structural Proposal

Validates proposal generation logic, determinism, and semantic purity.
"""

import pytest
from external_policy.ep2_strategy_absence import (
    generate_absence_proposal,
    StrategyContext,
    PermissionOutput,
    StrategyProposal
)
from memory.m4_structural_absence import StructuralAbsenceDuration
from memory.m4_structural_persistence import StructuralPersistenceDuration
from memory.m4_zone_geometry import ZonePenetrationDepth


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def strategy_context():
    """Standard strategy context."""
    return StrategyContext(
        context_id="TEST_CONTEXT",
        timestamp=2000.0
    )


@pytest.fixture
def permission_allowed():
    """M6 permission ALLOWED."""
    return PermissionOutput(
        result="ALLOWED",
        mandate_id="M2",
        action_id="A2",
        reason_code="APPROVED",
        timestamp=2000.0
    )


@pytest.fixture
def permission_denied():
    """M6 permission DENIED."""
    return PermissionOutput(
        result="DENIED",
        mandate_id="M2",
        action_id="A2",
        reason_code="REJECTED",
        timestamp=2000.0
    )


@pytest.fixture
def absence_exists():
    """B1.1: Absence exists (partial)."""
    return StructuralAbsenceDuration(
        absence_duration=40.0,
        observation_window=100.0,
        absence_ratio=0.4
    )


@pytest.fixture
def absence_zero():
    """B1.1: Zero absence (full presence)."""
    return StructuralAbsenceDuration(
        absence_duration=0.0,
        observation_window=100.0,
        absence_ratio=0.0
    )


@pytest.fixture
def absence_total():
    """B1.1: Total absence (no presence)."""
    return StructuralAbsenceDuration(
        absence_duration=100.0,
        observation_window=100.0,
        absence_ratio=1.0
    )


@pytest.fixture
def persistence_exists():
    """B2.1: Persistence exists (partial)."""
    return StructuralPersistenceDuration(
        total_persistence_duration=60.0,
        observation_window=100.0,
        persistence_ratio=0.6
    )


@pytest.fixture
def persistence_zero():
    """B2.1: Zero persistence (full absence)."""
    return StructuralPersistenceDuration(
        total_persistence_duration=0.0,
        observation_window=100.0,
        persistence_ratio=0.0
    )


@pytest.fixture
def geometry_exists():
    """A6: Geometry exists (penetration)."""
    return ZonePenetrationDepth(
        zone_id="Z1",
        penetration_depth=5.0
    )


@pytest.fixture
def geometry_zero():
    """A6: No penetration."""
    return ZonePenetrationDepth(
        zone_id="Z1",
        penetration_depth=0.0
    )


# ==============================================================================
# Happy Path Test
# ==============================================================================

def test_happy_path_all_conditions_met(
    absence_exists,
    persistence_exists,
    strategy_context,
    permission_allowed
):
    """Happy Path: Absence and persistence both exist -> proposal emitted."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    
    assert result is not None
    assert result.strategy_id == "EP2-ABSENCE-V1"
    assert result.action_type == "STRUCTURAL_ABSENCE_EVENT"
    assert result.confidence == "STRUCTURAL_PRESENT"
    assert result.justification_ref == "B1.1|B2.1"
    assert result.timestamp == strategy_context.timestamp


def test_happy_path_with_geometry(
    absence_exists,
    persistence_exists,
    geometry_exists,
    strategy_context,
    permission_allowed
):
    """Happy Path: With optional geometry -> enriched justification."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=geometry_exists,
        context=strategy_context
    )
    
    assert result is not None
    assert result.justification_ref == "B1.1|B2.1|A6"


# ==============================================================================
# Rejection Tests - M6 Permission
# ==============================================================================

def test_m6_denied_no_proposal(
    absence_exists,
    persistence_exists,
    strategy_context,
    permission_denied
):
    """M6 DENIED -> no proposal."""
    result = generate_absence_proposal(
        permission=permission_denied,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    assert result is None


# ==============================================================================
# Rejection Tests - Missing Primitives
# ==============================================================================

def test_absence_none_no_proposal(
    persistence_exists,
    strategy_context,
    permission_allowed
):
    """Absence None -> no proposal."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=None,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    assert result is None


def test_persistence_none_no_proposal(
    absence_exists,
    strategy_context,
    permission_allowed
):
    """Persistence None -> no proposal."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=None,
        geometry=None,
        context=strategy_context
    )
    assert result is None


# ==============================================================================
# Rejection Tests - Condition Failures
# ==============================================================================

def test_absence_duration_zero_no_proposal(
    absence_zero,
    persistence_exists,
    strategy_context,
    permission_allowed
):
    """Absence duration == 0 -> no proposal."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_zero,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    assert result is None


def test_persistence_duration_zero_no_proposal(
    absence_exists,
    persistence_zero,
    strategy_context,
    permission_allowed
):
    """Persistence duration == 0 -> no proposal."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_zero,
        geometry=None,
        context=strategy_context
    )
    assert result is None


def test_absence_ratio_one_no_proposal(
    absence_total,
    persistence_zero,
    strategy_context,
    permission_allowed
):
    """Absence ratio == 1.0 -> no proposal."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_total,
        persistence=persistence_zero,
        geometry=None,
        context=strategy_context
    )
    assert result is None


# ==============================================================================
# Optional Geometry Tests
# ==============================================================================

def test_geometry_none_base_justification(
    absence_exists,
    persistence_exists,
    strategy_context,
    permission_allowed
):
    """Geometry None -> base justification B1.1|B2.1."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    
    assert result.justification_ref == "B1.1|B2.1"


def test_geometry_zero_penetration_base_justification(
    absence_exists,
    persistence_exists,
    geometry_zero,
    strategy_context,
    permission_allowed
):
    """Geometry with zero penetration -> base justification."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=geometry_zero,
        context=strategy_context
    )
    
    assert result.justification_ref == "B1.1|B2.1"


# ==============================================================================
# Determinism Test
# ==============================================================================

def test_determinism_identical_inputs(
    absence_exists,
    persistence_exists,
    strategy_context,
    permission_allowed
):
    """Determinism: Identical inputs -> identical output."""
    result1 = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    
    result2 = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    
    assert result1 == result2


# ==============================================================================
# Semantic Purity Test
# ==============================================================================

def test_semantic_purity_no_market_terms():
    """Semantic Purity: Zero forbidden market terms in code."""
    import external_policy.ep2_strategy_absence as ep2_module
    import inspect
    
    source_code = inspect.getsource(ep2_module)
    source_lower = source_code.lower()
    
    # Check for market-specific patterns
    forbidden_patterns = [
        "bullish", "bearish", "momentum", "reversal",
        "strong_", "weak_", "good_", "bad_",
        "buy_", "sell_", "signal", "trade_",
        "profit", "loss", "alpha", "edge",
        "entry_price", "exit_price"
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in source_lower, \
            f"Forbidden market pattern '{pattern}' found in EP-2 Strategy #3 code"


# ==============================================================================
# Immutability Test
# ==============================================================================

def test_proposal_immutability(
    absence_exists,
    persistence_exists,
    strategy_context,
    permission_allowed
):
    """Proposal must be immutable (frozen dataclass)."""
    result = generate_absence_proposal(
        permission=permission_allowed,
        absence=absence_exists,
        persistence=persistence_exists,
        geometry=None,
        context=strategy_context
    )
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        result.strategy_id = "MODIFIED"
