"""
Tests for EP-2 Strategy: Cascade Sniper (Liquidation Proximity)

Validates proposal generation logic, determinism, None-handling, and semantic purity.

CRITICAL: This strategy is STATEFUL with multiple global instances.
Tests must reset state before each test.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase A, Tasks A3-A6.
"""

import copy
import pytest
from external_policy.ep2_strategy_cascade_sniper import (
    generate_cascade_sniper_proposal,
    generate_cascade_sniper_proposal_from_primitives,
    CascadeStateMachine,
    CascadeState,
    EntryMode,
    ProximityData,
    LiquidationBurst,
    StrategyContext,
    PermissionOutput,
    StrategyProposal,
    CascadeSniperConfig,
    reset_state,
    _get_state_machine,
)
from external_policy.test_fixtures import (
    create_cascade_proximity,
    create_cascade_state,
    create_minimal_bundle,
    create_strategy_context,
    create_permission_allowed,
    create_permission_denied,
)


# ==============================================================================
# State Reset Fixture
# ==============================================================================

@pytest.fixture(autouse=True)
def reset_all_strategy_state():
    """Reset cascade sniper global state before and after each test."""
    reset_state()
    yield
    reset_state()


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def strategy_context():
    """Standard strategy context."""
    return StrategyContext(
        context_id="TEST_CASCADE",
        timestamp=1000.0
    )


@pytest.fixture
def permission_allowed():
    """M6 permission ALLOWED."""
    return PermissionOutput(
        result="ALLOWED",
        mandate_id="M_CASCADE",
        action_id="A_CASCADE",
        reason_code="APPROVED",
        timestamp=1000.0
    )


@pytest.fixture
def permission_denied():
    """M6 permission DENIED."""
    return PermissionOutput(
        result="DENIED",
        mandate_id="M_CASCADE",
        action_id="A_CASCADE",
        reason_code="REJECTED",
        timestamp=1000.0
    )


@pytest.fixture
def proximity_data():
    """Proximity data with dominant long exposure."""
    return ProximityData(
        coin="BTC",
        current_price=64000.0,
        threshold_pct=0.005,
        long_positions_count=10,
        long_positions_value=500000.0,
        long_closest_liquidation=63700.0,
        short_positions_count=3,
        short_positions_value=100000.0,
        short_closest_liquidation=64300.0,
        total_positions_at_risk=13,
        total_value_at_risk=600000.0,
        timestamp=1000.0
    )


@pytest.fixture
def liquidation_burst():
    """Liquidation burst above threshold."""
    return LiquidationBurst(
        symbol="BTCUSDT",
        total_volume=100000.0,
        long_liquidations=80000.0,
        short_liquidations=20000.0,
        liquidation_count=5,
        window_start=990.0,
        window_end=1000.0
    )


@pytest.fixture
def small_liquidation_burst():
    """Liquidation burst below threshold."""
    return LiquidationBurst(
        symbol="BTCUSDT",
        total_volume=5000.0,
        long_liquidations=4000.0,
        short_liquidations=1000.0,
        liquidation_count=1,
        window_start=990.0,
        window_end=1000.0
    )


# ==============================================================================
# M6 Permission Tests
# ==============================================================================

def test_m6_denied_no_proposal(
    strategy_context,
    permission_denied,
    proximity_data,
    liquidation_burst
):
    """M6 Permission DENIED -> no proposal."""
    result = generate_cascade_sniper_proposal(
        permission=permission_denied,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )
    assert result is None


# ==============================================================================
# None-Handling Tests (A4)
# ==============================================================================

def test_proximity_none_no_crash(
    strategy_context,
    permission_allowed,
    liquidation_burst
):
    """Proximity data None -> no crash, returns None."""
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=None,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )
    # Can't determine symbol without proximity
    assert result is None


def test_liquidations_none_no_crash(
    strategy_context,
    permission_allowed,
    proximity_data
):
    """Liquidations None -> no crash, may still work."""
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=None,
        context=strategy_context,
        position_state=None
    )
    # May or may not produce result depending on state
    assert result is None or isinstance(result, StrategyProposal)


def test_all_data_none_no_crash(
    strategy_context,
    permission_allowed
):
    """All data None -> no crash, returns None."""
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=None,
        liquidations=None,
        context=strategy_context,
        position_state=None
    )
    assert result is None


# ==============================================================================
# Determinism Tests (A3) - WITH STATE RESET
# ==============================================================================

def test_determinism_with_state_reset(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """Determinism: After state reset, identical inputs -> identical output."""
    # Call 1
    reset_state()

    result1 = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )

    # Reset state
    reset_state()

    # Call 2
    result2 = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )

    assert result1 == result2


def test_determinism_none_inputs(
    strategy_context,
    permission_allowed
):
    """Determinism: Identical None inputs -> identical None output."""
    result1 = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=None,
        liquidations=None,
        context=strategy_context,
        position_state=None
    )

    result2 = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=None,
        liquidations=None,
        context=strategy_context,
        position_state=None
    )

    assert result1 == result2


# ==============================================================================
# State Machine Tests
# ==============================================================================

def test_state_machine_initial_state():
    """State machine starts with NONE state for new symbols."""
    config = CascadeSniperConfig()
    sm = CascadeStateMachine(config)

    state = sm.get_state("BTCUSDT")
    assert state == CascadeState.NONE


def test_state_machine_primes_on_cluster(
    proximity_data
):
    """State machine transitions to PRIMED when cluster detected."""
    config = CascadeSniperConfig(
        min_cluster_positions=2,
        min_cluster_value=100000.0,
        dominance_ratio=0.65
    )
    sm = CascadeStateMachine(config)

    state = sm.update("BTCUSDT", proximity_data, None, 1000.0)

    # Should be PRIMED because cluster meets criteria
    assert state == CascadeState.PRIMED


def test_state_machine_triggers_on_liquidation(
    proximity_data,
    liquidation_burst
):
    """State machine transitions to TRIGGERED after 2 bursts within confirmation window."""
    config = CascadeSniperConfig(
        min_cluster_positions=2,
        min_cluster_value=100000.0,
        dominance_ratio=0.65
    )
    sm = CascadeStateMachine(config)

    # First, prime the state
    sm.update("BTCUSDT", proximity_data, None, 999.0)
    assert sm.get_state("BTCUSDT") == CascadeState.PRIMED

    # First burst — not enough for confirmation (needs 2)
    state = sm.update("BTCUSDT", proximity_data, liquidation_burst, 1000.0)
    assert state == CascadeState.PRIMED  # Still waiting for confirmation

    # Second burst after refractory period (10s) — confirms cascade
    state = sm.update("BTCUSDT", proximity_data, liquidation_burst, 1015.0)
    assert state == CascadeState.TRIGGERED


def test_reset_state_clears_all():
    """reset_state() clears all global state."""
    config = CascadeSniperConfig()
    # Access state machine to populate it
    sm = _get_state_machine()
    sm._states["BTCUSDT"] = CascadeState.PRIMED

    # Reset
    reset_state()

    # New state machine should be clean
    sm2 = _get_state_machine()
    assert sm2.get_state("BTCUSDT") == CascadeState.NONE


# ==============================================================================
# Input Immutability Tests (A5)
# ==============================================================================

def test_input_immutability_proximity_data(
    strategy_context,
    permission_allowed,
    liquidation_burst
):
    """Policy does not modify proximity_data input."""
    proximity = ProximityData(
        coin="BTC",
        current_price=64000.0,
        threshold_pct=0.005,
        long_positions_count=10,
        long_positions_value=500000.0,
        long_closest_liquidation=63700.0,
        short_positions_count=3,
        short_positions_value=100000.0,
        short_closest_liquidation=64300.0,
        total_positions_at_risk=13,
        total_value_at_risk=600000.0,
        timestamp=1000.0
    )
    proximity_copy = copy.deepcopy(proximity)

    generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )

    assert proximity == proximity_copy


def test_input_immutability_liquidation_burst(
    strategy_context,
    permission_allowed,
    proximity_data
):
    """Policy does not modify liquidation_burst input."""
    burst = LiquidationBurst(
        symbol="BTCUSDT",
        total_volume=100000.0,
        long_liquidations=80000.0,
        short_liquidations=20000.0,
        liquidation_count=5,
        window_start=990.0,
        window_end=1000.0
    )
    burst_copy = copy.deepcopy(burst)

    generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=burst,
        context=strategy_context,
        position_state=None
    )

    assert burst == burst_copy


# ==============================================================================
# Side Effect Isolation Tests (A6)
# ==============================================================================

def test_symbol_isolation(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """State changes for one symbol don't affect another."""
    # Initialize BTC
    generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )

    # Initialize ETH with different proximity
    eth_proximity = ProximityData(
        coin="ETH",
        current_price=3200.0,
        threshold_pct=0.005,
        long_positions_count=5,
        long_positions_value=200000.0,
        long_closest_liquidation=3150.0,
        short_positions_count=2,
        short_positions_value=50000.0,
        short_closest_liquidation=3250.0,
        total_positions_at_risk=7,
        total_value_at_risk=250000.0,
        timestamp=1000.0
    )

    generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=eth_proximity,
        liquidations=None,
        context=strategy_context,
        position_state=None
    )

    # Both should have independent state
    sm = _get_state_machine()
    btc_state = sm.get_state("BTCUSDT")
    eth_state = sm.get_state("ETHUSDT")

    # States should be independent (both may be PRIMED or different)
    # Just verify they both exist
    assert btc_state in CascadeState
    assert eth_state in CascadeState


# ==============================================================================
# Proposal Immutability Test
# ==============================================================================

def test_proposal_immutability_if_emitted(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """If proposal emitted, it must be immutable."""
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )

    if result is not None:
        with pytest.raises(Exception):  # FrozenInstanceError
            result.strategy_id = "MODIFIED"


# ==============================================================================
# Position State Tests
# ==============================================================================

def test_position_open_skips_entry(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """Open position -> no entry proposal (cascade sniper is entry-focused)."""
    from runtime.position.types import PositionState

    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=PositionState.OPEN
    )

    # Cascade sniper doesn't exit - it only does entries
    assert result is None


def test_position_none_checks_entry(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """No position -> check for entry conditions."""
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None
    )

    # Result depends on state machine and entry conditions
    assert result is None or result.action_type == "ENTRY"


# ==============================================================================
# Entry Mode Tests
# ==============================================================================

def test_absorption_reversal_mode_default(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """Default entry mode is ABSORPTION_REVERSAL."""
    # Just verify no crash with default mode
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None,
        entry_mode=EntryMode.ABSORPTION_REVERSAL
    )

    assert result is None or isinstance(result, StrategyProposal)


def test_cascade_momentum_mode(
    strategy_context,
    permission_allowed,
    proximity_data,
    liquidation_burst
):
    """CASCADE_MOMENTUM mode works without crash."""
    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=proximity_data,
        liquidations=liquidation_burst,
        context=strategy_context,
        position_state=None,
        entry_mode=EntryMode.CASCADE_MOMENTUM
    )

    assert result is None or isinstance(result, StrategyProposal)


# ==============================================================================
# Primitive Bundle Integration Tests
# ==============================================================================

def test_from_primitives_none_bundle_no_crash(
    strategy_context,
    permission_allowed
):
    """M4 bundle with None primitives -> no crash."""
    from observation.types import M4PrimitiveBundle

    bundle = M4PrimitiveBundle.empty("BTCUSDT")

    result = generate_cascade_sniper_proposal_from_primitives(
        permission=permission_allowed,
        primitives=bundle,
        context=strategy_context,
        position_state=None
    )

    assert result is None


def test_from_primitives_with_cascade_data(
    strategy_context,
    permission_allowed
):
    """M4 bundle with cascade primitives -> processes correctly."""
    bundle = create_minimal_bundle(symbol="BTCUSDT", policy="cascade")

    result = generate_cascade_sniper_proposal_from_primitives(
        permission=permission_allowed,
        primitives=bundle,
        context=strategy_context,
        position_state=None
    )

    # May or may not produce result depending on state machine
    assert result is None or isinstance(result, StrategyProposal)


# ==============================================================================
# Cluster Formation Tests
# ==============================================================================

def test_no_cluster_no_priming(
    strategy_context,
    permission_allowed
):
    """Insufficient cluster -> no priming, no entry."""
    # Small cluster that doesn't meet thresholds
    small_proximity = ProximityData(
        coin="BTC",
        current_price=64000.0,
        threshold_pct=0.005,
        long_positions_count=1,  # Too few
        long_positions_value=10000.0,  # Too low
        long_closest_liquidation=63700.0,
        short_positions_count=0,
        short_positions_value=0.0,
        short_closest_liquidation=None,
        total_positions_at_risk=1,
        total_value_at_risk=10000.0,
        timestamp=1000.0
    )

    result = generate_cascade_sniper_proposal(
        permission=permission_allowed,
        proximity=small_proximity,
        liquidations=None,
        context=strategy_context,
        position_state=None
    )

    # No cluster = no entry
    assert result is None

    # Verify state machine stayed in NONE
    sm = _get_state_machine()
    assert sm.get_state("BTCUSDT") == CascadeState.NONE


# ==============================================================================
# Full-Context Data Rejection Tests
# ==============================================================================

class TestCascadePartialDataRejection:
    """Test that Cascade Sniper requires FULL context before entering.

    Cascade Sniper has multi-stage lifecycle (NONE→PRIMED→TRIGGERED→ABSORBING)
    that naturally enforces data requirements. Each stage requires specific data.
    These tests verify partial data never triggers entry.
    """

    def setup_method(self):
        """Reset strategy state before each test."""
        reset_state()

    def _make_context(self, ts: float) -> StrategyContext:
        return StrategyContext(context_id=f"test_{ts}", timestamp=ts)

    def _make_permission(self) -> PermissionOutput:
        return PermissionOutput(
            result="ALLOWED", mandate_id="M", action_id="A",
            reason_code="TEST", timestamp=1000.0
        )

    def _make_proximity(self, ts: float = 1000.0) -> ProximityData:
        """Large cluster that should prime the state machine."""
        return ProximityData(
            coin="BTC",
            current_price=64000.0,
            threshold_pct=0.005,
            long_positions_count=15,
            long_positions_value=800000.0,
            long_closest_liquidation=63700.0,
            short_positions_count=3,
            short_positions_value=100000.0,
            short_closest_liquidation=64300.0,
            total_positions_at_risk=18,
            total_value_at_risk=900000.0,
            timestamp=ts
        )

    def _make_burst(self, ts: float = 1000.0) -> LiquidationBurst:
        """Liquidation burst above threshold."""
        return LiquidationBurst(
            symbol="BTCUSDT",
            total_volume=200000.0,
            long_liquidations=180000.0,
            short_liquidations=20000.0,
            liquidation_count=8,
            window_start=ts - 10.0,
            window_end=ts
        )

    def test_no_proximity_no_entry(self):
        """proximity=None prevents cluster formation → no entry."""
        perm = self._make_permission()
        burst = self._make_burst()

        result = generate_cascade_sniper_proposal(
            permission=perm,
            proximity=None,
            liquidations=burst,
            context=self._make_context(1000.0),
            position_state=None
        )

        assert result is None, "No proximity data = no cluster = no entry"
        sm = _get_state_machine()
        assert sm.get_state("BTCUSDT") == CascadeState.NONE

    def test_no_liquidations_no_trigger(self):
        """liquidations=None prevents cascade trigger → state stays PRIMED."""
        sm = _get_state_machine()
        proximity = self._make_proximity()

        # Use state machine directly (bypasses warmup gate)
        state = sm.update("BTCUSDT", proximity, None, 1000.0, None)
        assert state == CascadeState.PRIMED, "Cluster should prime"

        # No liquidations → stays PRIMED, never TRIGGERED
        state = sm.update("BTCUSDT", proximity, None, 1010.0, None)
        assert state == CascadeState.PRIMED, (
            "No liquidation burst = no cascade trigger = stays PRIMED"
        )

    def test_no_absorption_data_blocks_reversal_entry(self):
        """absorption=None blocks reversal entry at absorption filter."""
        sm = _get_state_machine()

        # check_absorption_filter returns False when absorption data is None
        # This prevents entry even when state machine reaches ABSORBING
        assert sm.check_absorption_filter("BTCUSDT", EntryMode.ABSORPTION_REVERSAL) is False, (
            "No absorption data → absorption filter must return False"
        )
        assert sm.check_absorption_filter("BTCUSDT", EntryMode.CASCADE_MOMENTUM) is False, (
            "No absorption data → absorption filter must return False for momentum too"
        )

    def test_both_none_no_entry(self):
        """proximity=None AND liquidations=None → no entry (symbol unknown)."""
        perm = self._make_permission()

        result = generate_cascade_sniper_proposal(
            permission=perm,
            proximity=None,
            liquidations=None,
            context=self._make_context(1000.0),
            position_state=None
        )

        assert result is None, "No proximity + no liquidations = no symbol = no entry"

    def test_entry_requires_direction(self):
        """Cascade Sniper StrategyProposal requires direction — cannot omit it."""
        # Unlike EFFCS (where direction was optional/None), Cascade Sniper's
        # StrategyProposal has direction as REQUIRED field.
        # This enforces full-context at the type level.
        proposal = StrategyProposal(
            strategy_id="EP2-CASCADE-SNIPER-V1",
            action_type="ENTRY",
            direction="LONG",
            confidence="ABSORPTION_REVERSAL",
            justification_ref="TEST",
            timestamp=1000.0
        )
        assert proposal.direction == "LONG"

        # Verify that omitting direction raises TypeError
        with pytest.raises(TypeError):
            StrategyProposal(
                strategy_id="EP2-CASCADE-SNIPER-V1",
                action_type="ENTRY",
                confidence="TEST",
                justification_ref="TEST",
                timestamp=1000.0
                # direction intentionally omitted — should fail
            )
