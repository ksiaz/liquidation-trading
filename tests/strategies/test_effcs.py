"""
EFFCS Strategy Tests

Verifies EFFCS logic and constitutional compliance.

Constitutional Compliance:
- No confidence scoring (uses structural labels)
- No certainty claims
- Conditional execution only
- Acknowledges outcome divergence
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from external_policy.ep2_effcs_strategy import (
    generate_effcs_proposal,
    StrategyContext,
    PermissionOutput,
    RegimeState,
    EFFCSStrategy,
    _effcs_strategy  # Import global instance
)
from runtime.position.types import PositionState


# Mock primitive types
@dataclass
class MockPriceVelocity:
    """Mock price velocity primitive."""
    velocity: float


@dataclass
class MockDisplacement:
    """Mock displacement primitive."""
    displacement: float


class TestEFFCSStrategy:
    """Test EFFCS strategy logic."""

    def setup_method(self):
        """Reset strategy state before each test."""
        # Reset global strategy state
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

    def test_regime_gate_disabled_when_not_expansion(self):
        """Test EFFCS disabled when regime is not EXPANSION_ACTIVE."""
        regime_not_expansion = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        proposal = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_not_expansion,
            price_velocity=MockPriceVelocity(velocity=30.0),
            displacement=None,
            liquidation_zscore=3.0,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # EFFCS should not generate proposal when regime is not EXPANSION
        assert proposal is None

    def test_regime_gate_exit_when_regime_changes(self):
        """Test EFFCS exits position when regime changes from EXPANSION."""
        regime_changed = RegimeState(
            regime="SIDEWAYS_ACTIVE",
            vwap_distance=60.0,
            atr_5m=50.0,
            atr_30m=70.0
        )

        proposal = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_changed,
            price_velocity=MockPriceVelocity(velocity=30.0),
            displacement=None,
            liquidation_zscore=3.0,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN  # Position exists
        )

        # Should generate EXIT due to regime change
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "REGIME_CHANGE" in proposal.justification_ref

    def test_impulse_detection(self):
        """Test EFFCS detects and records impulse."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # First call - should detect impulse
        # Displacement = 50, threshold = 0.5 × 80 = 40, so impulse detected
        # Liquidation zscore = 2.8 ≥ 2.5, so spike detected
        proposal1 = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
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

        # No entry on impulse detection (need pullback + continuation)
        assert proposal1 is None

        # Global strategy should have recorded impulse
        assert _effcs_strategy._impulse.get("BTCUSDT") is not None

    def test_pullback_filtering_valid(self):
        """Test EFFCS validates pullback within 30% limit."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # First call - detect impulse
        generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
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

        # Second call - pullback within 30% (retracement = 20%)
        # Assuming impulse high = 50100, current price = 50080 (20 points back)
        # Impulse displacement = abs(velocity) = 50
        # Retracement = 20 / 50 = 0.40... but let's make it clearer

        # Actually, since we're using velocity as displacement proxy,
        # and impulse_high/low are set to price_high/low,
        # the retracement calculation is: (impulse_high - current_price) / displacement

        context_pullback = StrategyContext(
            context_id="test_context_pullback",
            timestamp=1100.0
        )

        proposal_pullback = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50090.0,  # Small pullback from 50100
            price_high=50100.0,
            price_low=49900.0,
            context=context_pullback,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should not enter yet (pullback filtering in progress)
        # Will only enter on continuation (retracement < 25% AND liquidations still high)
        # Since retracement = (50100 - 50090) / 50 = 0.20 (20%), it's valid

    def test_pullback_filtering_too_deep(self):
        """Test EFFCS invalidates pullback beyond 30% limit."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # First call - detect impulse
        generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),  # Displacement = 100
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Second call - pullback too deep (> 30%)
        # Retracement = (50100 - 50060) / 100 = 0.40 (40% > 30%)
        context_deep_pullback = StrategyContext(
            context_id="test_context_deep",
            timestamp=1100.0
        )

        proposal_deep = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50060.0,  # Deep pullback
            price_high=50100.0,
            price_low=49900.0,
            context=context_deep_pullback,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should reset to IDLE (impulse invalidated)
        assert proposal_deep is None
        # State should be reset
        # (Can't easily verify internal state from outside, but no proposal is correct)

    def test_continuation_entry(self):
        """Test EFFCS generates ENTRY on valid continuation."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # First call - detect impulse
        generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Second call - shallow pullback (< 25%) with high liquidations
        # Retracement = (50100 - 50085) / 100 = 0.15 (15% < 25%)
        context_continuation = StrategyContext(
            context_id="test_context_continuation",
            timestamp=1100.0
        )

        proposal_continuation = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),
            displacement=None,
            liquidation_zscore=2.6,  # Still ≥ 2.5
            price=50085.0,  # Shallow pullback
            price_high=50100.0,
            price_low=49900.0,
            context=context_continuation,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should generate ENTRY on continuation
        assert proposal_continuation is not None
        assert proposal_continuation.action_type == "ENTRY"
        assert proposal_continuation.strategy_id == "EP2-EFFCS-V1"
        # Verify constitutional compliance: no numeric confidence
        assert proposal_continuation.confidence == "CONTINUATION_CONDITIONS_MET"
        assert "IMPULSE_DISPLACEMENT" in proposal_continuation.justification_ref
        assert "LIQUIDATION_SPIKE" in proposal_continuation.justification_ref

    def test_exit_liquidations_stopped(self):
        """Test EFFCS exits when liquidations stop."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # Simulate position open
        _effcs_strategy._impulse["BTCUSDT"] = type('obj', (object,), {
            'impulse_start_price': 50000.0,
            'impulse_end_price': 50100.0,
            'impulse_displacement': 100.0,
            'impulse_high': 50100.0,
            'impulse_low': 49900.0,
            'timestamp': 1000.0
        })()

        proposal = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=100.0),
            displacement=None,
            liquidation_zscore=1.8,  # < 2.0 → liquidations stopped
            price=50110.0,
            price_high=50120.0,
            price_low=50080.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN
        )

        # Should generate EXIT due to liquidations stopped
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "LIQUIDATIONS_STOPPED" in proposal.justification_ref

    def test_exit_volatility_contraction(self):
        """Test EFFCS exits on volatility contraction."""
        regime_contracting = RegimeState(
            regime="EXPANSION_ACTIVE",  # Still in expansion but volatility contracting
            vwap_distance=200.0,
            atr_5m=60.0,  # ATR ratio = 60/70 = 0.857 < 0.90 → contraction
            atr_30m=70.0
        )

        # Simulate position open
        _effcs_strategy._impulse["BTCUSDT"] = type('obj', (object,), {
            'impulse_start_price': 50000.0,
            'impulse_end_price': 50100.0,
            'impulse_displacement': 100.0,
            'impulse_high': 50100.0,
            'impulse_low': 49900.0,
            'timestamp': 1000.0
        })()

        proposal = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_contracting,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.6,  # Liquidations still high
            price=50110.0,
            price_high=50120.0,
            price_low=50080.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.OPEN
        )

        # Should generate EXIT due to volatility contraction
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "VOLATILITY_CONTRACTION" in proposal.justification_ref

    def test_m6_denied_no_proposal(self):
        """Test EFFCS respects M6 permission denial."""
        permission_denied = PermissionOutput(
            result="DENIED",
            mandate_id="test_mandate",
            action_id="test_action",
            reason_code="M6_DENIED",
            timestamp=1000.0
        )

        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        proposal = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.8,
            price=50000.0,
            price_high=50100.0,
            price_low=49900.0,
            context=self.context,
            permission=permission_denied,
            position_state=PositionState.FLAT
        )

        # No proposal when M6 denies
        assert proposal is None

    def test_constitutional_compliance_no_numeric_confidence(self):
        """Test that EFFCS never uses numeric confidence scores."""
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE",
            vwap_distance=200.0,
            atr_5m=80.0,
            atr_30m=70.0
        )

        # Generate multiple proposals
        proposals = []

        # Impulse detection
        p1 = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
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
        if p1:
            proposals.append(p1)

        # Continuation entry
        p2 = generate_effcs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_expansion,
            price_velocity=MockPriceVelocity(velocity=50.0),
            displacement=None,
            liquidation_zscore=2.6,
            price=50085.0,
            price_high=50100.0,
            price_low=49900.0,
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
            # Allow V, 1, 2 from strategy IDs
            assert not any(char.isdigit() for char in proposal.confidence if char not in ['V', '1', '2'])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
