"""
Regime Mutual Exclusion Integration Tests

Verifies that SLBRS and EFFCS strategies enforce hard mutual exclusion.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VII (Regime Mutual Exclusion)
- Only one strategy can be active at a time
- Regime transitions force exits
"""

import pytest
from dataclasses import dataclass

from external_policy.ep2_slbrs_strategy import (
    generate_slbrs_proposal as slbrs_proposal,
    StrategyContext,
    PermissionOutput,
    RegimeState,
    _slbrs_strategy
)
from external_policy.ep2_effcs_strategy import (
    generate_effcs_proposal as effcs_proposal,
    _effcs_strategy
)
from runtime.position.types import PositionState


# Mock primitives
@dataclass
class MockZonePenetration:
    """Mock zone penetration primitive."""
    penetration_depth: float


@dataclass
class MockStructuralPersistence:
    """Mock structural persistence primitive."""
    total_persistence_duration: float


@dataclass
class MockOrderConsumption:
    """Mock order consumption primitive."""
    consumed_size: float


@dataclass
class MockPriceVelocity:
    """Mock price velocity primitive."""
    velocity: float


class TestRegimeMutualExclusion:
    """Test regime mutual exclusion between SLBRS and EFFCS."""

    def setup_method(self):
        """Reset strategy states before each test."""
        _slbrs_strategy.reset_state("BTCUSDT")
        _effcs_strategy.reset_state("BTCUSDT")

        self.context = StrategyContext(
            context_id="test_context",
            timestamp=1000.0
        )
        self.permission = PermissionOutput(
            result="ALLOWED",
            mandate_id="test_mandate",
            action_id="test_action",
            reason_code="TEST",
            timestamp=1000.0
        )

    def test_slbrs_disabled_in_expansion_regime(self):
        """Test SLBRS does not generate proposals in EXPANSION regime."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # SLBRS should not generate proposal (regime gate)
        proposal_slbrs = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        assert proposal_slbrs is None

    def test_effcs_disabled_in_sideways_regime(self):
        """Test EFFCS does not generate proposals in SIDEWAYS regime."""
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # EFFCS should not generate proposal (regime gate)
        proposal_effcs = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        assert proposal_effcs is None

    def test_both_strategies_disabled_when_regime_disabled(self):
        """Test both strategies disabled when regime is DISABLED."""
        regime_disabled = RegimeState(
            regime="DISABLED",
            vwap_distance=100.0,
            atr_5m=65.0,
            atr_30m=70.0
        )

        # Neither strategy should generate proposals
        proposal_slbrs = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_disabled,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        proposal_effcs = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_disabled,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        assert proposal_slbrs is None
        assert proposal_effcs is None

    def test_slbrs_exits_on_regime_transition_to_expansion(self):
        """Test SLBRS exits position when regime transitions to EXPANSION."""
        # Simulate SLBRS has open position
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # Regime transitions to EXPANSION
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # SLBRS should generate EXIT on regime change
        proposal_slbrs = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            zone_penetration=None,
            resting_size=None,
            order_consumption=None,
            structural_persistence=None,
            price=50100.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN  # Position exists
        )

        assert proposal_slbrs is not None
        assert proposal_slbrs.action_type == "EXIT"
        assert "REGIME_CHANGE" in proposal_slbrs.justification_ref

    def test_effcs_exits_on_regime_transition_to_sideways(self):
        """Test EFFCS exits position when regime transitions to SIDEWAYS."""
        # Simulate EFFCS has open position
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # Regime transitions to SIDEWAYS
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # EFFCS should generate EXIT on regime change
        proposal_effcs = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            price_velocity=None,
            displacement=None,
            liquidation_zscore=1.5,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN  # Position exists
        )

        assert proposal_effcs is not None
        assert proposal_effcs.action_type == "EXIT"
        assert "REGIME_CHANGE" in proposal_effcs.justification_ref

    def test_slbrs_can_enter_after_effcs_exits(self):
        """
        Test SLBRS can enter after EFFCS exits on regime transition.

        Scenario:
        1. EXPANSION regime: EFFCS active
        2. Regime transitions to SIDEWAYS
        3. EFFCS exits
        4. SLBRS can now evaluate and enter
        """
        # Step 1: EXPANSION regime
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # SLBRS should not evaluate
        proposal_slbrs_expansion = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )
        assert proposal_slbrs_expansion is None

        # Step 2: Regime transitions to SIDEWAYS
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # Step 3: Simulate EFFCS exit (position now FLAT)

        # Step 4: SLBRS can now evaluate
        # First test detection
        proposal_first_test = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=StrategyContext("test1", 1100.0),
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # No entry on first test, but SLBRS evaluates (regime gate passed)
        assert proposal_first_test is None

        # Retest with absorption
        proposal_retest = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=8.0),
            resting_size=None,
            order_consumption=MockOrderConsumption(consumed_size=100.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50005.0,
            context=StrategyContext("test2", 1200.0),
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # SLBRS can enter now
        assert proposal_retest is not None
        assert proposal_retest.action_type == "ENTRY"
        assert proposal_retest.strategy_id == "EP2-SLBRS-V1"

    def test_effcs_can_enter_after_slbrs_exits(self):
        """
        Test EFFCS can enter after SLBRS exits on regime transition.

        Scenario:
        1. SIDEWAYS regime: SLBRS active
        2. Regime transitions to EXPANSION
        3. SLBRS exits
        4. EFFCS can now evaluate and enter
        """
        # Step 1: SIDEWAYS regime
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # EFFCS should not evaluate
        proposal_effcs_sideways = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )
        assert proposal_effcs_sideways is None

        # Step 2: Regime transitions to EXPANSION
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # Step 3: Simulate SLBRS exit (position now FLAT)

        # Step 4: EFFCS can now evaluate
        # Impulse detection
        # velocity = 100, threshold = 0.5 × 80 = 40, so 100 > 40 (impulse detected)
        proposal_impulse = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=StrategyContext("test1", 1100.0),
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # No entry on impulse, but EFFCS evaluates (regime gate passed)
        assert proposal_impulse is None

        # Continuation entry
        # Retracement = (50100 - 50085) / 100 = 0.15 (15% < 25%)
        proposal_continuation = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),
            displacement=None,
            liquidation_zscore=2.6,
            price=50085.0,
            price_high=50100.0,
            price_low=49900.0,
            context=StrategyContext("test2", 1200.0),
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # EFFCS can enter now
        assert proposal_continuation is not None
        assert proposal_continuation.action_type == "ENTRY"
        assert proposal_continuation.strategy_id == "EP2-EFFCS-V1"

    def test_hard_mutual_exclusion_at_regime_boundary(self):
        """
        Test that regime classification is deterministic and exclusive.

        A regime cannot be both SIDEWAYS and EXPANSION simultaneously.
        If regime metrics are ambiguous, classifier returns DISABLED.
        """
        # Test case: Regime at exact boundary conditions
        # (In reality, classifier would resolve to one or DISABLED, never both)

        # This test verifies that if we call both strategies with the same regime,
        # only one can be active (enforced by regime gate in strategies)

        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # Call both strategies with SIDEWAYS regime
        proposal_slbrs = slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        proposal_effcs = effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # SLBRS can evaluate (first test detection)
        # EFFCS cannot evaluate (regime gate blocks)
        assert proposal_effcs is None
        # SLBRS may or may not generate proposal (depends on primitives)
        # but EFFCS must be None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
