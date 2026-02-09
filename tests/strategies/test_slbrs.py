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
        # Pre-warm OC observation counter (tests assume converged data)
        _slbrs_strategy._oc_seen["BTCUSDT"] = _slbrs_strategy.MIN_OC_OBSERVATIONS

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
            atr_5m=200.0,  # Must be >= 0.3% of price (50000*0.003=150)
            atr_30m=250.0
        )

    def _warm_sideways_streak(self, symbol="BTCUSDT", cycles=4):
        """Warm up SIDEWAYS streak to pass regime stability gate (>= 4 cycles)."""
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
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
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
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
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
        """Test SLBRS detects and records first test with full data."""
        # Warm sideways streak
        self._warm_sideways_streak()

        # Call with block present + orderbook depth - should detect and record first test
        proposal1 = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
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
        """Test SLBRS generates ENTRY on valid retest with full data."""
        # Warm sideways streak
        self._warm_sideways_streak()

        # First call - record first test (full data)
        generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Second call - retest with absorption (consumed_size/initial_size >= 15%)
        context_retest = StrategyContext(
            context_id="test_context_retest",
            timestamp=1100.0
        )

        proposal_retest = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,  # Near first test price (within 30% of block width=50)
            context=context_retest,
            permission=self.permission,
            position_state=PositionState.FLAT,
            orderflow_imbalance=0.55,  # Confirming LONG (bid dominant)
            orderflow_fill_count=30  # Sufficient fills for reliable data
        )

        # Should generate ENTRY on retest
        assert proposal_retest is not None
        assert proposal_retest.action_type == "ENTRY"
        assert proposal_retest.strategy_id == "EP2-SLBRS-V1"
        # Verify constitutional compliance: no numeric confidence
        assert proposal_retest.confidence == "RETEST_CONDITIONS_MET"
        assert "BLOCK_PERSISTENCE" in proposal_retest.justification_ref

    def test_retest_entry_no_absorption(self):
        """Test SLBRS does not enter without order_consumption."""
        # Warm sideways streak
        self._warm_sideways_streak()

        # First call - record first test (full data)
        generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Second call - retest WITHOUT order_consumption
        context_retest = StrategyContext(
            context_id="test_context_retest",
            timestamp=1100.0
        )

        proposal_retest = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=None,  # No absorption evidence
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=context_retest,
            permission=self.permission,
            position_state=PositionState.FLAT
        )

        # Should NOT generate ENTRY without absorption evidence
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
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
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
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
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
            atr_5m=200.0,
            atr_30m=250.0
        )

        # Generate multiple proposals
        proposals = []

        # First test (full data)
        p1 = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50000.0,
            context=self.context,
            permission=self.permission,
            position_state=PositionState.FLAT
        )
        if p1:
            proposals.append(p1)

        # Retest (full data)
        p2 = generate_slbrs_proposal(
            symbol="BTCUSDT",
            regime_state=regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("test2", 1100.0),
            permission=self.permission,
            position_state=PositionState.FLAT,
            orderflow_imbalance=0.55,
            orderflow_fill_count=30
        )
        if p2:
            proposals.append(p2)

        # Verify no numeric confidence in any proposal
        for proposal in proposals:
            # Confidence should be string label, not numeric
            assert isinstance(proposal.confidence, str)
            # Should not contain numbers like "0.75", "75%", etc.
            assert not any(char.isdigit() for char in proposal.confidence if char not in ['V', '1', '2'])


class TestSLBRSPartialDataRejection:
    """
    Test that SLBRS requires FULL context before entering.

    The strategy thesis is: detect liquidity block, observe absorption on first test,
    confirm absorption on retest, enter with orderbook-derived direction.

    If any critical primitive is None, the strategy must NOT enter.
    Partial data = no trade. This is the core invariant.
    """

    def setup_method(self):
        _slbrs_strategy.reset_state("BTCUSDT")
        _slbrs_strategy._sideways_streak["BTCUSDT"] = 0
        _slbrs_strategy._open_symbols.clear()
        _slbrs_strategy._oc_seen["BTCUSDT"] = _slbrs_strategy.MIN_OC_OBSERVATIONS

        self.context = StrategyContext(context_id="partial_test", timestamp=1000.0)
        self.permission = PermissionOutput(
            result="ALLOWED", mandate_id="m", action_id="a",
            reason_code="TEST", timestamp=1000.0
        )
        self.regime = RegimeState(
            regime="SIDEWAYS_ACTIVE", vwap_distance=60.0,
            atr_5m=200.0, atr_30m=250.0
        )

    def _warm_streak(self, cycles=4):
        for i in range(cycles):
            generate_slbrs_proposal(
                symbol="BTCUSDT", regime_state=self.regime,
                zone_penetration=None, resting_size=None,
                order_consumption=None, structural_persistence=None,
                price=50000.0,
                context=StrategyContext(f"w{i}", 900.0 + i),
                permission=self.permission, position_state=PositionState.FLAT
            )

    def _do_first_test(self):
        """Trigger first test with full data."""
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )

    def test_full_data_entry_succeeds(self):
        """Baseline: entry fires when ALL primitives are present."""
        self._warm_streak()
        self._do_first_test()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )
        assert proposal is not None, "Entry must fire with full data"
        assert proposal.action_type == "ENTRY"

    def test_no_order_consumption_no_entry(self):
        """Entry must NOT fire without order_consumption (absorption evidence).

        zone_penetration is NOT absorption. It measures price movement depth,
        which is the opposite of what absorption means. Deep penetration = zone failed.
        """
        self._warm_streak()
        self._do_first_test()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=None,  # NO absorption data
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None, "Must NOT enter without absorption evidence (order_consumption)"

    def test_no_resting_size_no_entry(self):
        """Entry must NOT fire without resting_size (block nature/direction).

        Without orderbook depth, we don't know if there's a real liquidity block
        or which direction to trade. 'price vs block_edge' is not a direction signal.
        """
        self._warm_streak()
        self._do_first_test()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,  # NO orderbook depth
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None, "Must NOT enter without orderbook depth (resting_size)"

    def test_only_zone_penetration_no_entry(self):
        """Entry must NOT fire with only zone_penetration + persistence.

        This is the minimum-data scenario: only 2 of 4 primitives present.
        Strategy should refuse to trade on such thin evidence.
        """
        self._warm_streak()

        # First test with minimal data
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )

        # Retest with minimal data
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None, "Must NOT enter with only zone_penetration (no absorption, no orderbook)"

    def test_first_test_requires_resting_size(self):
        """First test detection should require resting_size to confirm block exists.

        Without orderbook depth, we can't know if there's a real liquidity block.
        'structural_persistence > 60s' alone doesn't mean there are resting orders.
        """
        self._warm_streak()

        # Try first test without resting_size
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,  # Can't confirm block
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )

        # Should NOT have recorded a first test
        from external_policy.ep2_slbrs_strategy import SLBRSState
        assert _slbrs_strategy._state.get("BTCUSDT") == SLBRSState.IDLE, \
            "First test must NOT be recorded without resting_size confirming block"

    def test_sparse_orderflow_blocks_entry(self):
        """Entry must NOT fire when orderflow fill count is too low.

        With sparse HL fills, extreme orderflow ratios (0.003, 0.997) are noise.
        Require minimum 10 fills in the window for reliable data.
        """
        self._warm_streak()
        self._do_first_test()

        # Retest with extreme orderflow from sparse data
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.003,  # Extreme ratio from 2-3 fills
            orderflow_fill_count=3  # Too few fills
        )
        assert proposal is None, "Must NOT enter with sparse orderflow data (<25 fills)"

    def test_extreme_orderflow_blocks_entry(self):
        """Entry must NOT fire when orderflow is extreme (< 0.05 or > 0.95).

        Even with sufficient fills, near-total one-sidedness is unreliable.
        """
        self._warm_streak()
        self._do_first_test()

        # Retest with extreme orderflow despite sufficient fills
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=400.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=65.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.02,  # Near-zero buy ratio
            orderflow_fill_count=30  # Sufficient fills but extreme ratio
        )
        assert proposal is None, "Must NOT enter with extreme orderflow (<0.05)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
