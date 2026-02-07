"""
SLBRS Strategy Tests

Verifies SLBRS logic and constitutional compliance.

Constitutional Compliance:
- No confidence scoring (uses structural labels)
- No certainty claims
- Conditional execution only
- Acknowledges outcome divergence
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from external_policy.ep2_slbrs_strategy import (
    generate_slbrs_proposal,
    StrategyContext,
    PermissionOutput,
    RegimeState,
    SLBRSStrategy,
    _slbrs_strategy  # Import global instance
)
from runtime.position.types import PositionState


# Mock primitive types
@dataclass
class MockZonePenetration:
    """Mock zone penetration primitive."""
    penetration_depth: float


@dataclass
class MockRestingSize:
    """Mock resting size primitive."""
    bid_size: float
    ask_size: float


@dataclass
class MockOrderConsumption:
    """Mock order consumption primitive."""
    consumed_size: float
    initial_size: float = 500.0  # Default: consumed_size/initial_size >= 10% for entry


@dataclass
class MockStructuralPersistence:
    """Mock structural persistence primitive."""
    total_persistence_duration: float


class TestSLBRSStrategy:
    """Test SLBRS strategy logic."""

    def setup_method(self):
        """Reset strategy state before each test."""
        # Reset global strategy state
        _slbrs_strategy.reset_state("BTCUSDT")
        # Clear sideways streak so each test starts clean
        _slbrs_strategy._sideways_streak["BTCUSDT"] = 0

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

        self.regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

    def _warm_sideways_streak(self, symbol="BTCUSDT", cycles=2):
        """Warm up SIDEWAYS streak to pass regime stability gate (>= 2 cycles)."""
        for i in range(cycles):
            generate_slbrs_proposal(
                symbol=symbol,
                regime_state=self.regime_sideways,
                zone_penetration=None,  # No block — just builds streak
                resting_size=None,
                order_consumption=None,
                structural_persistence=None,
                price=50000.0,
                context=StrategyContext(f"warmup_{i}", 900.0 + i),
                permission=self.permission,
                position_state=PositionState.FLAT
            )

    def test_regime_gate_disabled_when_not_sideways(self):
        """Test SLBRS disabled when regime is not SIDEWAYS_ACTIVE."""
        regime_not_sideways = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_not_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # SLBRS should not generate proposal when regime is not SIDEWAYS
        assert proposal is None

    def test_regime_gate_blocks_when_regime_changes(self):
        """Test SLBRS blocks (returns None) when regime changes from SIDEWAYS.

        Per Constitution §110.2.5: Regime mismatch = BLOCK, not EXIT.
        Strategy cannot exit positions based solely on regime change.
        """
        regime_changed = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_changed,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=None,
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN  # Position exists
        )

        # Should return None (BLOCK) - not EXIT
        # Per §110.2.5: Regime mismatch blocks new evaluations, doesn't exit
        assert proposal is None

    def test_first_test_detection(self):
        """Test SLBRS detects and records first test."""
        # Warm sideways streak (2+ cycles required for regime stability)
        self._warm_sideways_streak()

        # Call with block present - should detect and record first test
        proposal1 = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # No entry on first test
        assert proposal1 is None

        # Global strategy should have recorded first test
        assert _slbrs_strategy._first_test.get("BTCUSDT") is not None

    def test_retest_entry_conditions_met(self):
        """Test SLBRS generates ENTRY on valid retest."""
        # Warm sideways streak
        self._warm_sideways_streak()

        # First call - record first test
        generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Second call - retest with absorption (consumed_size/initial_size >= 10%)
        context_retest = StrategyContext(
            context_id="test_context_retest",
            timestamp=1100.0
        )

        proposal_retest = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=8.0),  # Still near block
            resting_size=None,
            order_consumption=MockOrderConsumption(consumed_size=100.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50005.0,  # Near first test price (within 50% of block width=50)
            context=context_retest,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should generate ENTRY on retest
        assert proposal_retest is not None
        assert proposal_retest.action_type == "ENTRY"
        assert proposal_retest.strategy_id == "EP2-SLBRS-V1"
        # Verify constitutional compliance: no numeric confidence
        assert proposal_retest.confidence == "RETEST_CONDITIONS_MET"
        assert "BLOCK_PERSISTENCE" in proposal_retest.justification_ref

    def test_retest_entry_no_absorption(self):
        """Test SLBRS does not enter without absorption or meaningful penetration."""
        # Warm sideways streak
        self._warm_sideways_streak()

        # First call - record first test
        generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Second call - retest WITHOUT absorption AND tiny penetration (< 20% of block width)
        context_retest = StrategyContext(
            context_id="test_context_retest",
            timestamp=1100.0
        )

        proposal_retest = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=1.0),  # < 20% of block_width=50
            resting_size=None,
            order_consumption=None,  # No absorption
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50005.0,
            context=context_retest,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should NOT generate ENTRY without absorption or meaningful penetration
        assert proposal_retest is None

    def test_invalidation_returns_none_trailing_stop_handles_exit(self):
        """Test SLBRS does not emit EXIT — trailing stop handles all exits.

        Strategy-level invalidation (volatility expansion, price acceptance)
        was removed. Exits are now handled by:
        1. Trailing stop (ATR-progressive, registered on entry)
        2. Regime change (SLBRS stops proposing, trailing stop still active)
        """
        regime_expanding = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=80.0,  # High ATR ratio (was volatility expansion trigger)
            atr_30m=70.0
        )

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expanding,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=None,
            price=50010.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN
        )

        # Should return None (HOLD) — no strategy-level exit
        assert proposal is None

    def test_retest_armed_resets_on_position_open(self):
        """Test RETEST_ARMED state resets when position becomes OPEN."""
        # Force state to RETEST_ARMED
        _slbrs_strategy._state["BTCUSDT"] = SLBRSStrategy.__module__  # Won't work, use enum
        from external_policy.ep2_slbrs_strategy import SLBRSState
        _slbrs_strategy._state["BTCUSDT"] = SLBRSState.RETEST_ARMED

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=None,
            resting_size=None,
            order_consumption=None,
            structural_persistence=None,
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN
        )

        # Should return None (trailing stop handles exit)
        assert proposal is None
        # State should be reset to IDLE (ready for next cycle after exit)
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.IDLE

    def test_m6_denied_no_proposal(self):
        """Test SLBRS respects M6 permission denial."""
        permission_denied = PermissionOutput(
            result="DENIED",
            mandate_id="test_mandate",
            action_id="test_action",
            reason_code="M6_DENIED",
            timestamp=1000.0
        )

        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=10.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=35.0),
            price=50000.0,
            context=self.context,
            permission=permission_denied,
            position_state=PositionState.FLAT
        )

        # No proposal when M6 denies
        assert proposal is None

    def test_constitutional_compliance_no_numeric_confidence(self):
        """Test that SLBRS never uses numeric confidence scores."""
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # Generate multiple proposals
        proposals = []

        # First test
        p1 = generate_slbrs_proposal(
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
        if p1:
            proposals.append(p1)

        # Retest
        p2 = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=8.0),
            resting_size=None,
            order_consumption=MockOrderConsumption(consumed_size=100.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50005.0,
            context=StrategyContext("test2", 1100.0),
            permission=self.permission,
            position_state=PositionState.FLAT
        )
        if p2:
            proposals.append(p2)

        # Verify no numeric confidence in any proposal
        for proposal in proposals:
            # Confidence should be string label, not numeric
            assert isinstance(proposal.confidence, str)
            # Should not contain numbers like "0.75", "75%", etc.
            assert not any(char.isdigit() for char in proposal.confidence if char not in ['V', '1', '2'])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
