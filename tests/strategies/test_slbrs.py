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

    def test_regime_gate_exit_when_regime_changes(self):
        """Test SLBRS exits position when regime changes from SIDEWAYS."""
        # First, establish position in SIDEWAYS regime would require
        # simulating entry first, but for this test we can directly test
        # the exit logic when regime changes

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

        # Should generate EXIT due to regime change
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "REGIME_CHANGE" in proposal.justification_ref

    def test_first_test_detection(self):
        """Test SLBRS detects and records first test."""
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # First call - should detect block and record first test
        proposal1 = generate_slbrs_proposal(
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

        # No entry on first test
        assert proposal1 is None

        # Global strategy should have recorded first test
        assert _slbrs_strategy._first_test.get("BTCUSDT") is not None

    def test_retest_entry_conditions_met(self):
        """Test SLBRS generates ENTRY on valid retest."""
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # First call - record first test
        generate_slbrs_proposal(
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

        # Second call - retest with absorption
        context_retest = StrategyContext(
            context_id="test_context_retest",
            timestamp=1100.0
        )

        proposal_retest = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=8.0),  # Still near block
            resting_size=None,
            order_consumption=MockOrderConsumption(consumed_size=100.0),  # Absorption present
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50005.0,  # Near first test price (within 30% of block width)
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
        """Test SLBRS does not enter without absorption."""
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # First call - record first test
        generate_slbrs_proposal(
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

        # Second call - retest WITHOUT absorption
        context_retest = StrategyContext(
            context_id="test_context_retest",
            timestamp=1100.0
        )

        proposal_retest = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=8.0),
            resting_size=None,
            order_consumption=None,  # No absorption
            structural_persistence=MockStructuralPersistence(total_persistence_duration=40.0),
            price=50005.0,
            context=context_retest,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should NOT generate ENTRY without absorption
        assert proposal_retest is None

    def test_invalidation_volatility_expansion(self):
        """Test SLBRS exits on volatility expansion."""
        regime_expanding = RegimeState(
            regime="SIDEWAYS_ACTIVE",  # Still in sideways but volatility expanding
            vwap_distance=60.0,
            atr_5m=80.0,  # ATR ratio = 80/70 = 1.14 ≥ 1.0 → expansion
            atr_30m=70.0
        )

        # Simulate position open
        _slbrs_strategy._first_test["BTCUSDT"] = type('obj', (object,), {
            'block_edge': 50000.0,
            'block_width': 20.0,
            'test_volume': 1000.0,
            'test_price_impact': 10.0,
            'timestamp': 1000.0
        })()

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

        # Should generate EXIT due to volatility expansion
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "VOLATILITY_EXPANSION" in proposal.justification_ref

    def test_invalidation_price_acceptance(self):
        """Test SLBRS exits when price accepts through block."""
        regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        # Simulate position open with first test
        _slbrs_strategy._first_test["BTCUSDT"] = type('obj', (object,), {
            'block_edge': 50000.0,
            'block_width': 20.0,
            'test_volume': 1000.0,
            'test_price_impact': 10.0,
            'timestamp': 1000.0
        })()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),  # Beyond block width (20.0)
            resting_size=None,
            order_consumption=None,
            structural_persistence=None,
            price=50030.0,  # Price moved significantly beyond block
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN
        )

        # Should generate EXIT due to price acceptance
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "PRICE_ACCEPTANCE" in proposal.justification_ref

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
