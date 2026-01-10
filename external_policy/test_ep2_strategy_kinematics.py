"""
Tests for EP-2 Strategy #2: Kinematics-Driven Structural Proposal

Validates proposal generation logic, determinism, and semantic purity.
"""

import pytest
from external_policy.ep2_strategy_kinematics import (
    generate_kinematics_proposal,
    StrategyContext,
    PermissionOutput,
    StrategyProposal
)
from memory.m4_traversal_kinematics import PriceTraversalVelocity, TraversalCompactness
from memory.m4_price_distribution import PriceAcceptanceRatio


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
def velocity_nonzero():
    """A3: Non-zero velocity."""
    return PriceTraversalVelocity(
        traversal_id="T1",
        price_delta=10.0,
        time_delta=5.0,
        velocity=2.0
    )


@pytest.fixture
def velocity_zero():
    """A3: Zero velocity."""
    return PriceTraversalVelocity(
        traversal_id="T1",
        price_delta=0.0,
        time_delta=5.0,
        velocity=0.0
    )


@pytest.fixture
def compactness_nonzero():
    """A4: Non-degenerate compactness."""
    return TraversalCompactness(
        traversal_id="T1",
        net_displacement=15.0,
        total_path_length=20.0,
        compactness_ratio=0.75
    )


@pytest.fixture
def compactness_zero():
    """A4: Zero compactness (degenerate)."""
    return TraversalCompactness(
        traversal_id="T1",
        net_displacement=0.0,
        total_path_length=0.0,
        compactness_ratio=0.0
    )


@pytest.fixture
def acceptance_nonzero():
    """A5: Non-zero acceptance ratio."""
    return PriceAcceptanceRatio(
        accepted_range=8.0,
        rejected_range=2.0,
        acceptance_ratio=0.8
    )


@pytest.fixture
def acceptance_zero():
    """A5: Zero acceptance ratio (doji)."""
    return PriceAcceptanceRatio(
        accepted_range=0.0,
        rejected_range=10.0,
        acceptance_ratio=0.0
    )


# ==============================================================================
# Happy Path Test
# ==============================================================================

def test_happy_path_all_conditions_met(
    velocity_nonzero,
    compactness_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """Happy Path: All three primitives valid -> proposal emitted."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    
    assert result is not None
    assert result.strategy_id == "EP2-KINEMATICS-V1"
    assert result.action_type == "STRUCTURAL_KINEMATIC_EVENT"
    assert result.confidence == "STRUCTURAL_PRESENT"
    assert result.justification_ref == "A3|A4|A5"
    assert result.timestamp == strategy_context.timestamp


# ==============================================================================
# Missing Primitive Tests
# ==============================================================================

def test_a3_missing_no_proposal(
    compactness_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """A3 missing -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=None,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    assert result is None


def test_a4_missing_no_proposal(
    velocity_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """A4 missing -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=None,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    assert result is None


def test_a5_missing_no_proposal(
    velocity_nonzero,
    compactness_nonzero,
    strategy_context,
    permission_allowed
):
    """A5 missing -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=None,
        permission=permission_allowed,
        context=strategy_context
    )
    assert result is None


# ==============================================================================
# Zero Value Tests
# ==============================================================================

def test_velocity_zero_no_proposal(
    velocity_zero,
    compactness_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """velocity == 0 -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=velocity_zero,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    assert result is None


def test_compactness_ratio_zero_no_proposal(
    velocity_nonzero,
    compactness_zero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """compactness_ratio == 0 -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_zero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    assert result is None


def test_acceptance_ratio_zero_no_proposal(
    velocity_nonzero,
    compactness_nonzero,
    acceptance_zero,
    strategy_context,
    permission_allowed
):
    """acceptance_ratio == 0 -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=acceptance_zero,
        permission=permission_allowed,
        context=strategy_context
    )
    assert result is None


# ==============================================================================
# M6 Permission Test
# ==============================================================================

def test_m6_denied_no_proposal(
    velocity_nonzero,
    compactness_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_denied
):
    """M6 DENIED -> no proposal."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_denied,
        context=strategy_context
    )
    assert result is None


# ==============================================================================
# Determinism Test
# ==============================================================================

def test_determinism_identical_inputs(
    velocity_nonzero,
    compactness_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """Determinism: Identical inputs -> identical output."""
    result1 = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    
    result2 = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    
    assert result1 == result2


# ==============================================================================
# Semantic Purity Test
# ==============================================================================

def test_semantic_purity_no_market_terms():
    """Semantic Purity: Zero forbidden market terms in code."""
    import external_policy.ep2_strategy_kinematics as ep2_module
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
            f"Forbidden market pattern '{pattern}' found in EP-2 Strategy #2 code"


# ==============================================================================
# Immutability Test
# ==============================================================================

def test_proposal_immutability(
    velocity_nonzero,
    compactness_nonzero,
    acceptance_nonzero,
    strategy_context,
    permission_allowed
):
    """Proposal must be immutable (frozen dataclass)."""
    result = generate_kinematics_proposal(
        velocity=velocity_nonzero,
        compactness=compactness_nonzero,
        acceptance=acceptance_nonzero,
        permission=permission_allowed,
        context=strategy_context
    )
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        result.strategy_id = "MODIFIED"
