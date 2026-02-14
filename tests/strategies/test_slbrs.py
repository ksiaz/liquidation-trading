"""
SLBRS Strategy Tests

Verifies SLBRS logic against design spec (OB-SLBRSorderblockstrat.md).

Tests cover:
- State machine: IDLE → FIRST_TEST → REJECTION → RETEST → ENTRY
- Rejection displacement requirement (A3)
- Volume reduction, impact reduction, absorption (A4)
- R:R ≥ 1.5 constraint (A5)
- Invalidation: volatility expansion, adverse orderflow, price acceptance (A6)
- Fail-safes: consecutive losses, winrate, 5-min cooldown (Section 7)
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
    SLBRSState,
    _slbrs_strategy,
)
from runtime.position.types import PositionState


# Mock primitive types
@dataclass
class MockZonePenetration:
    penetration_depth: float


@dataclass
class MockRestingSize:
    bid_size: float
    ask_size: float


@dataclass
class MockOrderConsumption:
    consumed_size: float
    initial_size: float = 500.0
    price_level: float = 50000.0
    timestamp: float = 1000.0


@dataclass
class MockStructuralPersistence:
    total_persistence_duration: float
    timestamp: float = 1000.0


class TestSLBRSStrategy:
    """Test SLBRS strategy logic."""

    def setup_method(self):
        """Reset strategy state before each test."""
        _slbrs_strategy.reset_state("BTCUSDT")
        _slbrs_strategy._sideways_streak["BTCUSDT"] = 0
        _slbrs_strategy._oc_seen["BTCUSDT"] = _slbrs_strategy.MIN_OC_OBSERVATIONS
        _slbrs_strategy._open_symbols.clear()
        _slbrs_strategy._entry_info.clear()
        _slbrs_strategy._position_info.clear()
        _slbrs_strategy._consecutive_losses.clear()
        _slbrs_strategy._trade_results.clear()
        _slbrs_strategy._oc_cache.clear()
        _slbrs_strategy._sp_cache.clear()
        _slbrs_strategy._last_exit_ts.clear()

        self.context = StrategyContext(context_id="test_context", timestamp=1000.0)
        self.permission = PermissionOutput(
            result="ALLOWED", mandate_id="test_mandate",
            action_id="test_action", reason_code="TEST", timestamp=1000.0
        )

        # ATR=200 > 0.3% of 50000=150 ✓
        # vwap_distance=120: R:R = 120/60 = 2.0 ≥ 1.5 ✓
        #   (stop = max(50000*0.0006, 0.30*200) = max(30, 60) = 60)
        self.regime_sideways = RegimeState(
            regime="SIDEWAYS_ACTIVE", vwap_distance=120.0,
            atr_5m=200.0, atr_30m=250.0
        )

    def _warm_sideways_streak(self, symbol="BTCUSDT", cycles=4):
        """Warm up SIDEWAYS streak to pass regime stability gate."""
        for i in range(cycles):
            generate_slbrs_proposal(
                symbol=symbol, regime_state=self.regime_sideways,
                zone_penetration=None, resting_size=None,
                order_consumption=None, structural_persistence=None,
                price=50000.0,
                context=StrategyContext(f"warmup_{i}", 900.0 + i),
                permission=self.permission, position_state=PositionState.FLAT
            )

    def _do_first_test(self, symbol="BTCUSDT", price=50000.0, ts=1000.0):
        """Trigger first test with full data → FIRST_TEST_OBSERVED."""
        generate_slbrs_proposal(
            symbol=symbol, regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=price,
            context=StrategyContext("first_test", ts),
            permission=self.permission, position_state=PositionState.FLAT
        )

    def _do_rejection(self, symbol="BTCUSDT", price=50060.0, ts=1010.0):
        """Simulate price rejection: price bounces up (LONG direction).

        Rejection threshold = max(50000*0.0008, 0.25*200) = max(40, 50) = 50.
        Price 50060 gives displacement=60 > 50 → REJECTION_CONFIRMED.
        """
        generate_slbrs_proposal(
            symbol=symbol, regime_state=self.regime_sideways,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=price,
            context=StrategyContext("rejection", ts),
            permission=self.permission, position_state=PositionState.FLAT
        )

    def _do_retest_entry(self, symbol="BTCUSDT", ts=1020.0):
        """Attempt retest entry with reduced volume/impact.

        First test: consumed=50, impact=25
        Retest: consumed=30 (< 50*0.70=35 ✓), impact=15 (< 25 ✓)
        Absorption: 30/40 = 0.75 ✓
        """
        return generate_slbrs_proposal(
            symbol=symbol, regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=30.0, initial_size=40.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0,
            context=StrategyContext("retest", ts),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )

    def test_regime_gate_disabled_when_not_sideways(self):
        """SLBRS disabled when regime is not SIDEWAYS_ACTIVE."""
        regime_not_sideways = RegimeState(
            regime="EXPANSION_ACTIVE", vwap_distance=200.0,
            atr_5m=80.0, atr_30m=70.0
        )
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=regime_not_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None, order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0, context=self.context,
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None

    def test_regime_change_resets_state_machine(self):
        """Regime change from SIDEWAYS resets FIRST_TEST/REJECTION states."""
        self._warm_sideways_streak()
        self._do_first_test()
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.FIRST_TEST_OBSERVED

        # Regime changes
        regime_expansion = RegimeState(
            regime="EXPANSION_ACTIVE", vwap_distance=200.0,
            atr_5m=80.0, atr_30m=70.0
        )
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=regime_expansion,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=50000.0, context=StrategyContext("regime_change", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.IDLE

    def test_first_test_detection(self):
        """SLBRS detects and records first test with full data."""
        self._warm_sideways_streak()
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0, context=self.context,
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None  # No entry on first test
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.FIRST_TEST_OBSERVED
        ft = _slbrs_strategy._first_test["BTCUSDT"]
        assert ft is not None
        assert ft.direction == "LONG"
        assert ft.test_volume == 50.0
        assert ft.test_price_impact == 25.0

    def test_rejection_required_before_entry(self):
        """Entry requires rejection displacement between first test and retest."""
        self._warm_sideways_streak()
        self._do_first_test()

        # Try retest immediately (no rejection) — should NOT enter
        # State is FIRST_TEST_OBSERVED, not REJECTION_CONFIRMED
        proposal = self._do_retest_entry(ts=1001.0)
        assert proposal is None
        # Still waiting for rejection
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.FIRST_TEST_OBSERVED

    def test_full_flow_first_test_rejection_retest(self):
        """Full flow: first test → rejection → retest entry."""
        self._warm_sideways_streak()
        self._do_first_test()
        self._do_rejection()
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.REJECTION_CONFIRMED

        proposal = self._do_retest_entry()
        assert proposal is not None
        assert proposal.action_type == "ENTRY"
        assert proposal.strategy_id == "EP2-SLBRS-V1"
        assert proposal.direction == "LONG"
        assert proposal.confidence == "RETEST_CONDITIONS_MET"
        assert "BLOCK_REJECTION" in proposal.justification_ref

    def test_volume_reduction_required(self):
        """Retest consumed volume must be < 70% of first test volume."""
        self._warm_sideways_streak()
        self._do_first_test()  # test_volume = 50
        self._do_rejection()

        # Retest with same volume as first test (50 >= 50*0.70=35) → blocked
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=70.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0, context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )
        assert proposal is None

    def test_impact_reduction_required(self):
        """Retest impact must be less than first test impact."""
        self._warm_sideways_streak()
        self._do_first_test()  # test_price_impact = 25
        self._do_rejection()

        # Retest with same impact (25 >= 25) → blocked
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),  # Same as first test
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=30.0, initial_size=40.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0, context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )
        assert proposal is None

    def test_rr_gate(self):
        """Entry blocked when R:R < 1.5."""
        self._warm_sideways_streak()
        self._do_first_test()
        self._do_rejection()

        # Low vwap_distance → poor R:R
        # stop = max(50005*0.0006, 0.30*200) = 60
        # target = vwap_distance = 50 → R:R = 50/60 = 0.83 < 1.5
        low_rr_regime = RegimeState(
            regime="SIDEWAYS_ACTIVE", vwap_distance=50.0,
            atr_5m=200.0, atr_30m=250.0
        )
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=low_rr_regime,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=30.0, initial_size=40.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0, context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )
        assert proposal is None

    def test_invalidation_volatility_expansion(self):
        """A6: EXIT on volatility expansion (ATR ratio ≥ 0.95)."""
        regime_expanding = RegimeState(
            regime="SIDEWAYS_ACTIVE", vwap_distance=60.0,
            atr_5m=80.0, atr_30m=70.0  # Ratio = 1.14 ≥ 0.95
        )
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=regime_expanding,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=50010.0, context=self.context,
            permission=self.permission, position_state=PositionState.OPEN
        )
        assert proposal is not None
        assert proposal.action_type == "EXIT"
        assert "VOLATILITY_EXPANSION" in proposal.justification_ref

    def test_invalidation_no_exit_when_stable(self):
        """No EXIT when volatility is stable (ATR ratio < 0.95)."""
        regime_stable = RegimeState(
            regime="SIDEWAYS_ACTIVE", vwap_distance=60.0,
            atr_5m=60.0, atr_30m=80.0  # Ratio = 0.75 < 0.95
        )
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=regime_stable,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=50010.0, context=self.context,
            permission=self.permission, position_state=PositionState.OPEN
        )
        assert proposal is None

    def test_retest_armed_resets_on_position_open(self):
        """RETEST_ARMED state resets when position becomes OPEN."""
        _slbrs_strategy._state["BTCUSDT"] = SLBRSState.RETEST_ARMED
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=50000.0, context=self.context,
            permission=self.permission, position_state=PositionState.OPEN
        )
        assert proposal is None
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.IDLE

    def test_m6_denied_no_proposal(self):
        """SLBRS respects M6 permission denial."""
        permission_denied = PermissionOutput(
            result="DENIED", mandate_id="test_mandate",
            action_id="test_action", reason_code="M6_DENIED", timestamp=1000.0
        )
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None, order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0, context=self.context,
            permission=permission_denied, position_state=PositionState.FLAT
        )
        assert proposal is None

    def test_cooldown_300s(self):
        """5-minute (300s) cooldown after exit."""
        self._warm_sideways_streak()
        # Set exit timestamp
        _slbrs_strategy._last_exit_ts["BTCUSDT"] = 900.0

        # Try at t=1000 (100s after exit, < 300s) → blocked
        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0, context=self.context,
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None

    def test_consecutive_loss_hard_kill(self):
        """≥2 consecutive losses on symbol blocks entry."""
        self._warm_sideways_streak()
        _slbrs_strategy._consecutive_losses["BTCUSDT"] = 2

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0, context=self.context,
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None

    def test_rejection_timeout(self):
        """State resets to IDLE if no rejection within 60s."""
        self._warm_sideways_streak()
        self._do_first_test(ts=1000.0)
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.FIRST_TEST_OBSERVED

        # 61 seconds later, no rejection
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=50010.0,  # Small move, not enough for rejection
            context=StrategyContext("timeout", 1061.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.IDLE

    def test_block_acceptance_resets_state(self):
        """Price staying beyond block for >10s resets state (block broken)."""
        self._warm_sideways_streak()
        self._do_first_test(ts=1000.0)
        # For LONG, "beyond" = price below block_edge

        # Price drops below block edge
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=49980.0,  # Below block_edge (50000) by 20 > 50000*0.0003=15
            context=StrategyContext("below1", 1002.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.FIRST_TEST_OBSERVED

        # Still below after 11 seconds → accepted through
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime_sideways,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=49980.0,
            context=StrategyContext("below2", 1013.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert _slbrs_strategy._state["BTCUSDT"] == SLBRSState.IDLE

    def test_constitutional_compliance_no_numeric_confidence(self):
        """SLBRS never uses numeric confidence scores."""
        self._warm_sideways_streak()
        self._do_first_test()
        self._do_rejection()
        proposal = self._do_retest_entry()
        assert proposal is not None
        assert isinstance(proposal.confidence, str)
        assert not any(char.isdigit() for char in proposal.confidence if char not in ['V', '1', '2'])


class TestSLBRSPartialDataRejection:
    """Test that SLBRS requires FULL context before entering."""

    def setup_method(self):
        _slbrs_strategy.reset_state("BTCUSDT")
        _slbrs_strategy._sideways_streak["BTCUSDT"] = 0
        _slbrs_strategy._open_symbols.clear()
        _slbrs_strategy._oc_seen["BTCUSDT"] = _slbrs_strategy.MIN_OC_OBSERVATIONS
        _slbrs_strategy._entry_info.clear()
        _slbrs_strategy._position_info.clear()
        _slbrs_strategy._consecutive_losses.clear()
        _slbrs_strategy._trade_results.clear()
        _slbrs_strategy._oc_cache.clear()
        _slbrs_strategy._sp_cache.clear()
        _slbrs_strategy._last_exit_ts.clear()

        self.context = StrategyContext(context_id="partial_test", timestamp=1000.0)
        self.permission = PermissionOutput(
            result="ALLOWED", mandate_id="m", action_id="a",
            reason_code="TEST", timestamp=1000.0
        )
        self.regime = RegimeState(
            regime="SIDEWAYS_ACTIVE", vwap_distance=120.0,
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
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=50.0, initial_size=500.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )

    def _do_rejection(self):
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=None, resting_size=None,
            order_consumption=None, structural_persistence=None,
            price=50060.0,
            context=StrategyContext("rejection", 1010.0),
            permission=self.permission, position_state=PositionState.FLAT
        )

    def test_full_data_entry_succeeds(self):
        """Baseline: entry fires with full data through complete flow."""
        self._warm_streak()
        self._do_first_test()
        self._do_rejection()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=30.0, initial_size=40.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0,
            context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )
        assert proposal is not None, "Entry must fire with full data"
        assert proposal.action_type == "ENTRY"

    def test_no_order_consumption_no_entry(self):
        """Entry must NOT fire without order_consumption at retest."""
        self._warm_streak()
        self._do_first_test()
        self._do_rejection()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0,
            context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.55, orderflow_fill_count=30
        )
        assert proposal is None, "Must NOT enter without absorption evidence"

    def test_no_resting_size_no_entry(self):
        """Entry must NOT fire without resting_size (needed for first test)."""
        self._warm_streak()

        # Try first test without resting_size
        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert _slbrs_strategy._state.get("BTCUSDT") == SLBRSState.IDLE, \
            "First test must NOT be recorded without resting_size"

    def test_only_zone_penetration_no_entry(self):
        """Entry must NOT fire with only 2 of 4 primitives."""
        self._warm_streak()

        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None, order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None, order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0,
            context=StrategyContext("retest", 1050.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert proposal is None

    def test_first_test_requires_resting_size(self):
        """First test requires resting_size to confirm block exists."""
        self._warm_streak()

        generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=25.0),
            resting_size=None,
            order_consumption=None,
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50000.0,
            context=StrategyContext("first_test", 1000.0),
            permission=self.permission, position_state=PositionState.FLAT
        )
        assert _slbrs_strategy._state.get("BTCUSDT") == SLBRSState.IDLE

    def test_sparse_orderflow_blocks_entry(self):
        """Entry blocked when orderflow fill count is too low."""
        self._warm_streak()
        self._do_first_test()
        self._do_rejection()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=30.0, initial_size=40.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0,
            context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.003, orderflow_fill_count=3
        )
        assert proposal is None, "Must NOT enter with sparse orderflow data"

    def test_extreme_orderflow_blocks_entry(self):
        """Entry blocked when orderflow is extreme (< 0.10 or > 0.90)."""
        self._warm_streak()
        self._do_first_test()
        self._do_rejection()

        proposal = generate_slbrs_proposal(
            symbol="BTCUSDT", regime_state=self.regime,
            zone_penetration=MockZonePenetration(penetration_depth=15.0),
            resting_size=MockRestingSize(bid_size=800.0, ask_size=200.0),
            order_consumption=MockOrderConsumption(consumed_size=30.0, initial_size=40.0),
            structural_persistence=MockStructuralPersistence(total_persistence_duration=125.0),
            price=50005.0,
            context=StrategyContext("retest", 1020.0),
            permission=self.permission, position_state=PositionState.FLAT,
            orderflow_imbalance=0.02, orderflow_fill_count=30
        )
        assert proposal is None, "Must NOT enter with extreme orderflow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
