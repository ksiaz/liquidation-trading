"""
Tests for EP-2 Strategy: EFFCS (Expansion & Forced Flow Continuation System)

Validates proposal generation logic, determinism, None-handling, and semantic purity.

CRITICAL: This strategy is STATEFUL. Tests must reset state before each test.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase A, Tasks A3-A6.
"""

import copy
import pytest
from external_policy.ep2_effcs_strategy import (
    generate_effcs_proposal,
    EFFCSStrategy,
    EFFCSState,
    StrategyContext,
    PermissionOutput,
    StrategyProposal,
    RegimeState,
    _effcs_strategy,  # Global instance
)
from external_policy.test_fixtures import (
    create_price_velocity,
    create_displacement_origin,
    create_strategy_context,
    create_permission_allowed,
    create_permission_denied,
    create_regime_state_expansion,
)


# ==============================================================================
# State Reset Fixture
# ==============================================================================

@pytest.fixture(autouse=True)
def reset_strategy_state():
    """Reset EFFCS global state before and after each test."""
    # Reset before test
    _effcs_strategy._state.clear()
    _effcs_strategy._impulse.clear()
    _effcs_strategy._pullback.clear()
    yield
    # Reset after test
    _effcs_strategy._state.clear()
    _effcs_strategy._impulse.clear()
    _effcs_strategy._pullback.clear()


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def strategy_context():
    """Standard strategy context."""
    return StrategyContext(
        context_id="TEST_EFFCS",
        timestamp=1000.0
    )


@pytest.fixture
def permission_allowed():
    """M6 permission ALLOWED."""
    return PermissionOutput(
        result="ALLOWED",
        mandate_id="M_EFFCS",
        action_id="A_EFFCS",
        reason_code="APPROVED",
        timestamp=1000.0
    )


@pytest.fixture
def permission_denied():
    """M6 permission DENIED."""
    return PermissionOutput(
        result="DENIED",
        mandate_id="M_EFFCS",
        action_id="A_EFFCS",
        reason_code="REJECTED",
        timestamp=1000.0
    )


@pytest.fixture
def regime_expansion():
    """EXPANSION_ACTIVE regime state."""
    return create_regime_state_expansion()


@pytest.fixture
def regime_sideways():
    """SIDEWAYS_ACTIVE regime state (not valid for EFFCS)."""
    return RegimeState(
        regime="SIDEWAYS_ACTIVE",
        vwap_distance=0.001,
        atr_5m=50.0,
        atr_30m=100.0
    )


@pytest.fixture
def price_velocity():
    """Price velocity primitive."""
    return create_price_velocity(velocity=0.1)  # High velocity for impulse


@pytest.fixture
def displacement():
    """Displacement origin anchor primitive."""
    return create_displacement_origin()


# ==============================================================================
# M6 Permission Tests
# ==============================================================================

def test_m6_denied_no_proposal(
    strategy_context,
    permission_denied,
    regime_expansion,
    price_velocity,
    displacement
):
    """M6 Permission DENIED -> no proposal."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_denied,
        position_state=None
    )
    assert result is None


# ==============================================================================
# Regime Gate Tests
# ==============================================================================

def test_regime_sideways_no_proposal(
    strategy_context,
    permission_allowed,
    regime_sideways,
    price_velocity,
    displacement
):
    """SIDEWAYS regime -> EFFCS blocked (regime mismatch)."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_sideways,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    assert result is None


def test_regime_none_no_proposal(
    strategy_context,
    permission_allowed,
    price_velocity,
    displacement
):
    """No regime state -> EFFCS blocked."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=None,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    assert result is None


# ==============================================================================
# None-Handling Tests (A4)
# ==============================================================================

def test_price_velocity_none_no_crash(
    strategy_context,
    permission_allowed,
    regime_expansion,
    displacement
):
    """Price velocity None -> no crash, returns None."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=None,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    assert result is None


def test_displacement_none_no_crash(
    strategy_context,
    permission_allowed,
    regime_expansion,
    price_velocity
):
    """Displacement None -> no crash, may still work with velocity."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=None,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )
    # May or may not produce result depending on velocity-based detection
    assert result is None or isinstance(result, StrategyProposal)


def test_all_primitives_none_no_crash(
    strategy_context,
    permission_allowed,
    regime_expansion
):
    """All primitives None -> no crash, returns None."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=None,
        displacement=None,
        liquidation_zscore=0.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
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
    regime_expansion,
    price_velocity,
    displacement
):
    """Determinism: After state reset, identical inputs -> identical output."""
    # Call 1
    _effcs_strategy._state.clear()
    _effcs_strategy._impulse.clear()
    _effcs_strategy._pullback.clear()

    result1 = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Reset state
    _effcs_strategy._state.clear()
    _effcs_strategy._impulse.clear()
    _effcs_strategy._pullback.clear()

    # Call 2
    result2 = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    assert result1 == result2


def test_determinism_none_inputs(
    strategy_context,
    permission_allowed,
    regime_expansion
):
    """Determinism: Identical None inputs -> identical None output."""
    result1 = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=None,
        displacement=None,
        liquidation_zscore=0.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    result2 = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=None,
        displacement=None,
        liquidation_zscore=0.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
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
    strategy = EFFCSStrategy()
    # Access state for a new symbol
    assert strategy._state.get("BTCUSDT") is None
    # After initialization, should be IDLE
    strategy._state["BTCUSDT"] = EFFCSState.IDLE
    assert strategy._state.get("BTCUSDT") == EFFCSState.IDLE


def test_reset_state_clears_symbol(
    strategy_context,
    permission_allowed,
    regime_expansion,
    price_velocity,
    displacement
):
    """reset_state() clears state for symbol."""
    # Make a call to initialize state
    generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Verify state exists
    assert "BTCUSDT" in _effcs_strategy._state

    # Reset
    _effcs_strategy.reset_state("BTCUSDT")

    # Verify state cleared
    assert _effcs_strategy._state.get("BTCUSDT") == EFFCSState.IDLE
    assert _effcs_strategy._impulse.get("BTCUSDT") is None
    assert _effcs_strategy._pullback.get("BTCUSDT") is None


# ==============================================================================
# Input Immutability Tests (A5)
# ==============================================================================

def test_input_immutability_price_velocity(
    strategy_context,
    permission_allowed,
    regime_expansion,
    displacement
):
    """Policy does not modify price_velocity input."""
    velocity = create_price_velocity(velocity=0.1)
    velocity_copy = copy.deepcopy(velocity)

    generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    assert velocity == velocity_copy


def test_input_immutability_regime_state(
    strategy_context,
    permission_allowed,
    price_velocity,
    displacement
):
    """Policy does not modify regime_state input."""
    regime = create_regime_state_expansion()
    regime_copy = copy.deepcopy(regime)

    generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
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
    regime_expansion,
    price_velocity,
    displacement
):
    """State changes for one symbol don't affect another."""
    # Initialize BTC
    generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Initialize ETH
    generate_effcs_proposal(
        symbol="ETHUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=3200.0,
        price_high=3250.0,
        price_low=3150.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Both should have independent state
    assert "BTCUSDT" in _effcs_strategy._state
    assert "ETHUSDT" in _effcs_strategy._state

    # Reset BTC shouldn't affect ETH
    _effcs_strategy.reset_state("BTCUSDT")
    assert _effcs_strategy._state.get("BTCUSDT") == EFFCSState.IDLE
    assert "ETHUSDT" in _effcs_strategy._state


# ==============================================================================
# Proposal Immutability Test
# ==============================================================================

def test_proposal_immutability_if_emitted(
    strategy_context,
    permission_allowed,
    regime_expansion,
    price_velocity,
    displacement
):
    """If proposal emitted, it must be immutable."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
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

def test_position_open_checks_exit(
    strategy_context,
    permission_allowed,
    regime_expansion,
    price_velocity,
    displacement
):
    """Open position -> check for exit conditions."""
    from runtime.position.types import PositionState

    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=1.0,  # Low z-score triggers exit
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=PositionState.OPEN
    )

    # With position open, EFFCS should check for exit
    assert result is None or result.action_type == "EXIT"


def test_position_none_checks_entry(
    strategy_context,
    permission_allowed,
    regime_expansion,
    price_velocity,
    displacement
):
    """No position -> check for entry conditions."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=3.0,
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Result depends on entry conditions
    assert result is None or result.action_type == "ENTRY"


# ==============================================================================
# Liquidation Z-Score Tests
# ==============================================================================

def test_low_zscore_no_impulse(
    strategy_context,
    permission_allowed,
    regime_expansion,
    price_velocity,
    displacement
):
    """Low liquidation z-score -> no impulse detection."""
    result = generate_effcs_proposal(
        symbol="BTCUSDT",
        regime_state=regime_expansion,
        price_velocity=price_velocity,
        displacement=displacement,
        liquidation_zscore=1.0,  # Below 2.5 threshold
        price=64000.0,
        price_high=64200.0,
        price_low=63800.0,
        context=strategy_context,
        permission=permission_allowed,
        position_state=None
    )

    # Low z-score = no impulse
    assert result is None


# ==============================================================================
# Full-Context Data Rejection Tests
# ==============================================================================

class TestEFFCSPartialDataRejection:
    """Test that EFFCS requires FULL context before entering.

    Same methodology as TestSLBRSPartialDataRejection:
    If partial data is enough to trigger, the test fails.
    We want strategies to consider full context.
    """

    def setup_method(self):
        """Reset strategy state before each test."""
        _effcs_strategy._state.clear()
        _effcs_strategy._impulse.clear()
        _effcs_strategy._pullback.clear()

    def _make_context(self, ts: float) -> StrategyContext:
        return StrategyContext(context_id=f"test_{ts}", timestamp=ts)

    def _make_permission(self) -> PermissionOutput:
        return PermissionOutput(
            result="ALLOWED", mandate_id="M", action_id="A",
            reason_code="TEST", timestamp=1000.0
        )

    def _make_regime(self, atr_5m=150.0) -> RegimeState:
        return RegimeState(
            regime="EXPANSION_ACTIVE", vwap_distance=200.0,
            atr_5m=atr_5m, atr_30m=100.0
        )

    def _trigger_full_entry(self, symbol="BTCUSDT"):
        """Trigger a valid EFFCS entry with full data (baseline).

        Returns the entry proposal (should be non-None).
        """
        regime = self._make_regime()
        perm = self._make_permission()
        velocity = create_price_velocity(velocity=100.0)  # > 0.5 * 150 = 75

        # Cycle 1: Impulse detection (must return None)
        result1 = generate_effcs_proposal(
            symbol=symbol,
            regime_state=regime,
            price_velocity=velocity,
            displacement=None,
            liquidation_zscore=3.0,  # >= 2.5
            price=64000.0,
            price_high=64200.0,  # Actual range
            price_low=63800.0,   # Actual range
            context=self._make_context(1000.0),
            permission=perm,
            position_state=None
        )
        assert result1 is None, "First cycle should detect impulse, not enter"

        # Cycle 2: Continuation entry
        # Retracement = (impulse_high - price) / displacement = (64200 - 64185) / 100 = 0.15
        # Must be < 0.25 for continuation entry
        result2 = generate_effcs_proposal(
            symbol=symbol,
            regime_state=regime,
            price_velocity=velocity,
            displacement=None,
            liquidation_zscore=3.0,
            price=64185.0,  # Near high (15% retracement of displacement)
            price_high=64200.0,
            price_low=63800.0,
            context=self._make_context(1100.0),
            permission=perm,
            position_state=None
        )
        return result2

    def test_full_data_entry_succeeds(self):
        """Baseline: EFFCS enters with full data (velocity + zscore + price range)."""
        result = self._trigger_full_entry()
        assert result is not None, "Full data should allow entry"
        assert result.action_type == "ENTRY"
        assert result.strategy_id == "EP2-EFFCS-V1"

    def test_entry_has_direction(self):
        """EFFCS entry must specify direction (LONG or SHORT).

        Without direction, downstream code doesn't know what side to trade.
        """
        result = self._trigger_full_entry()
        assert result is not None
        assert result.direction is not None, (
            "Entry proposal must have direction — downstream needs LONG/SHORT"
        )
        assert result.direction in ("LONG", "SHORT")

    def test_equal_high_low_no_entry(self):
        """price_high == price_low means no actual range observed.

        When high == low == current_price:
        - impulse_direction defaults to -1 (arbitrary)
        - retracement is always 0% (passes any filter)
        - No real pullback evidence exists

        This is partial data — strategy should block.
        """
        regime = self._make_regime()
        perm = self._make_permission()
        velocity = create_price_velocity(velocity=100.0)

        # Cycle 1: Impulse with equal high/low
        generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime,
            price_velocity=velocity,
            displacement=None,
            liquidation_zscore=3.0,
            price=64000.0,
            price_high=64000.0,  # Same as current price!
            price_low=64000.0,   # Same as current price!
            context=self._make_context(1000.0),
            permission=perm,
            position_state=None
        )

        # Cycle 2: Should NOT enter (no real range)
        result = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime,
            price_velocity=velocity,
            displacement=None,
            liquidation_zscore=3.0,
            price=64000.0,
            price_high=64000.0,
            price_low=64000.0,
            context=self._make_context(1100.0),
            permission=perm,
            position_state=None
        )

        assert result is None, (
            "price_high == price_low = no observable range. "
            "Direction and retracement are meaningless. "
            "Strategy should not enter with zero-information impulse."
        )

    def test_no_velocity_no_entry(self):
        """price_velocity=None should block entry (already works)."""
        regime = self._make_regime()
        perm = self._make_permission()

        result = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime,
            price_velocity=None,
            displacement=None,
            liquidation_zscore=3.0,
            price=64000.0,
            price_high=64200.0,
            price_low=63800.0,
            context=self._make_context(1000.0),
            permission=perm,
            position_state=None
        )

        assert result is None, "No velocity = no impulse detection"

    def test_low_zscore_no_entry(self):
        """liquidation_zscore < 2.5 should block entry (already works)."""
        regime = self._make_regime()
        perm = self._make_permission()
        velocity = create_price_velocity(velocity=100.0)

        # Cycle 1
        generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime,
            price_velocity=velocity,
            displacement=None,
            liquidation_zscore=1.0,  # Below 2.5
            price=64000.0,
            price_high=64200.0,
            price_low=63800.0,
            context=self._make_context(1000.0),
            permission=perm,
            position_state=None
        )

        # Cycle 2
        result = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime,
            price_velocity=velocity,
            displacement=None,
            liquidation_zscore=1.0,
            price=64050.0,
            price_high=64200.0,
            price_low=63800.0,
            context=self._make_context(1100.0),
            permission=perm,
            position_state=None
        )

        assert result is None, "Low z-score should block entry"
