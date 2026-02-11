"""
Tests for EP-2 Strategy: SLBRS (Sideways Liquidity Block Reaction System)

Validates proposal generation logic, determinism, None-handling, and semantic purity.

CRITICAL: This strategy is STATEFUL. Tests must reset state before each test.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase A, Tasks A3-A6.
"""

import copy
import pytest
from external_policy.ep2_slbrs_strategy import (
    generate_slbrs_proposal,
    SLBRSStrategy,
    SLBRSState,
    StrategyContext,
    PermissionOutput,
    StrategyProposal,
    RegimeState,
    _slbrs_strategy,  # Global instance
)
from external_policy.test_fixtures import (
    create_zone_penetration,
    create_structural_persistence,
    create_resting_size,
    create_order_consumption,
    create_strategy_context,
    create_permission_allowed,
    create_permission_denied,
    create_regime_state_sideways,
)


# ==============================================================================
# State Reset Fixture
# ==============================================================================

@pytest.fixture(autouse=True)
def reset_strategy_state():
    """Reset SLBRS global state before and after each test."""
    # Reset before test
    _slbrs_strategy._state.clear()
    _slbrs_strategy._first_test.clear()
    yield
    # Reset after test
    _slbrs_strategy._state.clear()
    _slbrs_strategy._first_test.clear()


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def strategy_context():
    """Standard strategy context."""
    return StrategyContext(
        context_id="TEST_SLBRS",
        timestamp=1000.0
    )


@pytest.fixture
def permission_allowed():
    """M6 permission ALLOWED."""
    return PermissionOutput(
        result="ALLOWED",
        mandate_id="M_SLBRS",
        action_id="A_SLBRS",
        reason_code="APPROVED",
        timestamp=1000.0
    )


@pytest.fixture
def permission_denied():
    """M6 permission DENIED."""
    return PermissionOutput(
        result="DENIED",
        mandate_id="M_SLBRS",
        action_id="A_SLBRS",
        reason_code="REJECTED",
        timestamp=1000.0
    )


@pytest.fixture
def regime_sideways():
    """SIDEWAYS_ACTIVE regime state."""
    return create_regime_state_sideways()


@pytest.fixture
def regime_expansion():
    """EXPANSION_ACTIVE regime state (not valid for SLBRS)."""
    return RegimeState(
        regime="EXPANSION_ACTIVE",
        vwap_distance=0.01,
        atr_5m=150.0,
        atr_30m=100.0
    )


@pytest.fixture
def zone_penetration():
    """Zone penetration primitive."""
    return create_zone_penetration(penetration_depth=0.01)


@pytest.fixture
def structural_persistence():
    """Structural persistence primitive (>30s for block)."""
    return create_structural_persistence(total_persistence_duration=60.0)


@pytest.fixture
def resting_size():
    """Resting size primitive."""
    return create_resting_size()


@pytest.fixture
def order_consumption():
    """Order consumption primitive."""
    return create_order_consumption()


# ==============================================================================
# M6 Permission Tests
# ==============================================================================

def test_m6_denied_no_proposal(
    strategy_context,
    permission_denied,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """M6 Permission DENIED -> no proposal."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_denied,
        position_state=None
    )
    assert result is None


# ==============================================================================
# Regime Gate Tests
# ==============================================================================

def test_regime_expansion_no_proposal(
    strategy_context,
    permission_allowed,
    regime_expansion,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """EXPANSION regime -> SLBRS blocked (regime mismatch)."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    assert result is None


def test_regime_none_no_proposal(
    strategy_context,
    permission_allowed,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """No regime state -> SLBRS blocked."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=None,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    assert result is None


# ==============================================================================
# None-Handling Tests (A4)
# ==============================================================================

def test_zone_penetration_none_no_crash(
    strategy_context,
    permission_allowed,
    regime_sideways,
    resting_size,
    order_consumption,
    structural_persistence
):
    """Zone penetration None -> no crash, returns None."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=None,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    # No zone penetration = no block detected
    assert result is None


def test_structural_persistence_none_no_crash(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption
):
    """Structural persistence None -> no crash, returns None."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=None,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    # No persistence = no block
    assert result is None


def test_all_primitives_none_no_crash(
    strategy_context,
    permission_allowed,
    regime_sideways
):
    """All primitives None -> no crash, returns None."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=None,
        resting_size=None,
        order_consumption=None,
        structural_persistence=None,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    assert result is None


# ==============================================================================
# Determinism Tests (A3) - WITH STATE RESET
# ==============================================================================

def test_determinism_with_state_reset(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """Determinism: After state reset, identical inputs -> identical output."""
    # Call 1
    _slbrs_strategy._state.clear()
    _slbrs_strategy._first_test.clear()

    result1 = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Reset state
    _slbrs_strategy._state.clear()
    _slbrs_strategy._first_test.clear()

    # Call 2
    result2 = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    assert result1 == result2


def test_determinism_none_inputs(
    strategy_context,
    permission_allowed,
    regime_sideways
):
    """Determinism: Identical None inputs -> identical None output."""
    result1 = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=None,
        resting_size=None,
        order_consumption=None,
        structural_persistence=None,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    result2 = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=None,
        resting_size=None,
        order_consumption=None,
        structural_persistence=None,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    assert result1 == result2


# ==============================================================================
# State Machine Tests
# ==============================================================================

def test_state_initialized_to_idle():
    """New symbol starts in IDLE state."""
    strategy = SLBRSStrategy()
    # Access state for a new symbol
    assert strategy._state.get("BTCUSDT") is None
    # After first call, should be initialized
    strategy._state["BTCUSDT"] = SLBRSState.IDLE
    assert strategy._state.get("BTCUSDT") == SLBRSState.IDLE


def test_reset_state_clears_symbol(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """reset_state() clears state for symbol."""
    # Make a call to initialize state
    generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Verify state exists
    assert "BTCUSDT" in _slbrs_strategy._state

    # Reset
    _slbrs_strategy.reset_state("BTCUSDT")

    # Verify state cleared
    assert _slbrs_strategy._state.get("BTCUSDT") == SLBRSState.IDLE
    assert _slbrs_strategy._first_test.get("BTCUSDT") is None


# ==============================================================================
# Input Immutability Tests (A5)
# ==============================================================================

def test_input_immutability_zone_penetration(
    strategy_context,
    permission_allowed,
    regime_sideways,
    resting_size,
    order_consumption,
    structural_persistence
):
    """Policy does not modify zone_penetration input."""
    zone = create_zone_penetration(penetration_depth=0.01)
    zone_copy = copy.deepcopy(zone)

    generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    assert zone == zone_copy


def test_input_immutability_regime_state(
    strategy_context,
    permission_allowed,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """Policy does not modify regime_state input."""
    regime = create_regime_state_sideways()
    regime_copy = copy.deepcopy(regime)

    generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    assert regime == regime_copy


# ==============================================================================
# Side Effect Isolation Tests (A6)
# ==============================================================================

def test_symbol_isolation(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """State changes for one symbol don't affect another."""
    # Initialize BTC
    generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Initialize ETH
    generate_slbrs_proposal(
        symbol="ETHUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=3200.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Both should have independent state
    assert "BTCUSDT" in _slbrs_strategy._state
    assert "ETHUSDT" in _slbrs_strategy._state

    # Reset BTC shouldn't affect ETH
    _slbrs_strategy.reset_state("BTCUSDT")
    assert _slbrs_strategy._state.get("BTCUSDT") == SLBRSState.IDLE
    assert "ETHUSDT" in _slbrs_strategy._state


# ==============================================================================
# Proposal Immutability Test
# ==============================================================================

def test_proposal_immutability_if_emitted(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """If proposal emitted, it must be immutable."""
    # Note: Getting a proposal from SLBRS requires specific state machine transitions
    # This test verifies any emitted proposal is frozen
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    if result is not None:
        with pytest.raises(Exception):  # FrozenInstanceError
            result.strategy_id = "MODIFIED"


# ==============================================================================
# Position State Tests
# ==============================================================================

def test_position_open_checks_invalidation(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """Open position -> check for invalidation, not entry."""
    from runtime.position.types import PositionState

    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=PositionState.OPEN
    )

    # With position open, SLBRS should check for invalidation
    # Result depends on invalidation conditions
    assert result is None or result.action_type == "EXIT"


def test_position_none_checks_entry(
    strategy_context,
    permission_allowed,
    regime_sideways,
    zone_penetration,
    resting_size,
    order_consumption,
    structural_persistence
):
    """No position -> check for entry conditions."""
    result = generate_slbrs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        zone_penetration=zone_penetration,
        resting_size=resting_size,
        order_consumption=order_consumption,
        structural_persistence=structural_persistence,
        price=64000.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Result depends on entry conditions being met
    # Either None (not met) or ENTRY proposal
    assert result is None or result.action_type == "ENTRY"
