"""
Integration tests for module contract boundaries.

Verifies that modules communicate correctly and contracts are respected.
These tests do NOT test business logic - they test structural integrity.
"""

import pytest
from decimal import Decimal
from typing import Dict, List, Optional

# Layer 1: Observation types
from observation.types import (
    ObservationSnapshot,
    ObservationStatus,
    SystemCounters,
    M4PrimitiveBundle,
)

# Layer 3: Arbitration types
from runtime.arbitration.types import (
    Mandate,
    MandateType,
    Action,
    ActionType,
)

# Layer 4: Risk and Position types
from runtime.risk.types import (
    RiskConfig,
    AccountState,
    PositionRisk,
    PortfolioRisk,
    ValidationResult,
)
from runtime.position.types import (
    Position,
    PositionState,
    Direction,
    InvariantViolation,
)

# Layer 5: Exchange types
from runtime.exchange.types import (
    OrderRequest,
    OrderResponse,
    OrderStatus,
    OrderType,
    OrderSide,
    OrderFill,
    FillType,
    ReconciliationResult,
    ReconciliationAction,
)

# Layer 5: Executor types
from runtime.executor.types import (
    ExecutionResult,
    CycleStats,
)

# Layer 6: Analytics types
from runtime.analytics.types import (
    TradeRecord,
    TradeOutcome,
    PerformanceSnapshot,
    Alert,
    AlertLevel,
)

# Layer 6: Meta types
from runtime.meta.types import (
    Assumption,
    AssumptionStatus,
    CalibratedParameter,
    ModelHealthStatus,
    SystemRegime,
)


class TestTypeImmutability:
    """Verify that frozen types are truly immutable."""

    def test_observation_snapshot_immutable(self):
        """ObservationSnapshot should be immutable."""
        snapshot = ObservationSnapshot(
            status=ObservationStatus.UNINITIALIZED,
            timestamp=1000.0,
            symbols_active=["BTC"],
            counters=SystemCounters(intervals_processed=0, dropped_events={}),
            promoted_events=None,
            primitives={}
        )

        with pytest.raises(AttributeError):
            snapshot.timestamp = 2000.0

    def test_mandate_immutable(self):
        """Mandate should be immutable."""
        mandate = Mandate(
            symbol="BTC",
            type=MandateType.ENTRY,
            authority=1.0,
            timestamp=1000.0
        )

        with pytest.raises(AttributeError):
            mandate.symbol = "ETH"

    def test_position_immutable(self):
        """Position should be immutable."""
        position = Position(
            symbol="BTC",
            state=PositionState.FLAT,
            direction=None,
            quantity=Decimal("0"),
            entry_price=None
        )

        with pytest.raises(AttributeError):
            position.state = PositionState.OPEN

    def test_execution_result_immutable(self):
        """ExecutionResult should be immutable."""
        result = ExecutionResult(
            symbol="BTC",
            action=ActionType.ENTRY,
            success=True,
            state_before=PositionState.FLAT,
            state_after=PositionState.ENTERING,
            timestamp=1000.0
        )

        with pytest.raises(AttributeError):
            result.success = False


class TestPositionInvariants:
    """Verify position state machine invariants."""

    def test_flat_must_have_zero_quantity(self):
        """FLAT position must have quantity=0."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTC",
                state=PositionState.FLAT,
                direction=None,
                quantity=Decimal("1.0"),
                entry_price=None
            )

    def test_flat_must_have_no_direction(self):
        """FLAT position must have direction=None."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTC",
                state=PositionState.FLAT,
                direction=Direction.LONG,
                quantity=Decimal("0"),
                entry_price=None
            )

    def test_open_must_have_quantity(self):
        """OPEN position must have quantity≠0."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTC",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("0"),
                entry_price=Decimal("50000")
            )

    def test_open_must_have_direction(self):
        """OPEN position must have direction."""
        with pytest.raises(InvariantViolation):
            Position(
                symbol="BTC",
                state=PositionState.OPEN,
                direction=None,
                quantity=Decimal("1.0"),
                entry_price=Decimal("50000")
            )

    def test_valid_flat_position(self):
        """Valid FLAT position should be constructable."""
        position = Position.create_flat("BTC")
        assert position.state == PositionState.FLAT
        assert position.quantity == Decimal("0")
        assert position.direction is None

    def test_valid_open_position(self):
        """Valid OPEN position should be constructable."""
        position = Position(
            symbol="BTC",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.5"),
            entry_price=Decimal("50000")
        )
        assert position.state == PositionState.OPEN


class TestMandateValidation:
    """Verify mandate validation rules."""

    def test_mandate_requires_symbol(self):
        """Mandate must have non-empty symbol."""
        with pytest.raises(ValueError):
            Mandate(
                symbol="",
                type=MandateType.ENTRY,
                authority=1.0,
                timestamp=1000.0
            )

    def test_mandate_requires_positive_authority(self):
        """Mandate authority must be non-negative."""
        with pytest.raises(ValueError):
            Mandate(
                symbol="BTC",
                type=MandateType.ENTRY,
                authority=-1.0,
                timestamp=1000.0
            )

    def test_mandate_requires_positive_timestamp(self):
        """Mandate timestamp must be non-negative."""
        with pytest.raises(ValueError):
            Mandate(
                symbol="BTC",
                type=MandateType.ENTRY,
                authority=1.0,
                timestamp=-1.0
            )


class TestMandateAuthorityHierarchy:
    """Verify mandate authority ordering."""

    def test_exit_highest_authority(self):
        """EXIT has highest authority value."""
        assert MandateType.EXIT.value > MandateType.BLOCK.value
        assert MandateType.EXIT.value > MandateType.REDUCE.value
        assert MandateType.EXIT.value > MandateType.ENTRY.value
        assert MandateType.EXIT.value > MandateType.HOLD.value

    def test_hold_lowest_authority(self):
        """HOLD has lowest authority value."""
        assert MandateType.HOLD.value < MandateType.EXIT.value
        assert MandateType.HOLD.value < MandateType.BLOCK.value
        assert MandateType.HOLD.value < MandateType.REDUCE.value
        assert MandateType.HOLD.value < MandateType.ENTRY.value

    def test_authority_ordering(self):
        """Full authority ordering is correct."""
        # EXIT > BLOCK > REDUCE > ENTRY > HOLD
        assert MandateType.EXIT.value > MandateType.BLOCK.value
        assert MandateType.BLOCK.value > MandateType.REDUCE.value
        assert MandateType.REDUCE.value > MandateType.ENTRY.value
        assert MandateType.ENTRY.value > MandateType.HOLD.value


class TestActionTypeMapping:
    """Verify action type mappings from mandates."""

    def test_mandate_to_action_mapping(self):
        """Mandate types map correctly to action types."""
        mappings = {
            MandateType.ENTRY: ActionType.ENTRY,
            MandateType.EXIT: ActionType.EXIT,
            MandateType.REDUCE: ActionType.REDUCE,
            MandateType.HOLD: ActionType.HOLD,
            MandateType.BLOCK: ActionType.NO_ACTION,
        }

        for mandate_type, expected_action in mappings.items():
            action = Action.from_mandate_type(mandate_type, "BTC")
            assert action.type == expected_action


class TestRiskConfigValidation:
    """Verify risk configuration constraints."""

    def test_default_config_valid(self):
        """Default RiskConfig should be valid."""
        config = RiskConfig()
        config.validate()  # Should not raise

    def test_target_must_not_exceed_max(self):
        """L_target must be <= L_max."""
        config = RiskConfig(L_max=5.0, L_target=10.0)
        with pytest.raises(AssertionError):
            config.validate()

    def test_critical_less_than_safe(self):
        """D_critical must be < D_min_safe."""
        config = RiskConfig(D_critical=0.10, D_min_safe=0.05)
        with pytest.raises(AssertionError):
            config.validate()


class TestAccountStateValidation:
    """Verify account state constraints."""

    def test_equity_must_be_positive(self):
        """Account equity must be positive."""
        with pytest.raises(ValueError):
            AccountState(
                equity=Decimal("0"),
                margin_available=Decimal("100"),
                timestamp=1000.0
            )

    def test_margin_cannot_be_negative(self):
        """Available margin cannot be negative."""
        with pytest.raises(ValueError):
            AccountState(
                equity=Decimal("1000"),
                margin_available=Decimal("-100"),
                timestamp=1000.0
            )


class TestPositionRiskValidation:
    """Verify position risk constraints."""

    def test_prices_must_be_positive(self):
        """Mark and entry prices must be positive."""
        with pytest.raises(ValueError):
            PositionRisk(
                symbol="BTC",
                direction=Direction.LONG,
                quantity=Decimal("1"),
                entry_price=Decimal("50000"),
                mark_price=Decimal("-100"),  # Invalid
                exposure=Decimal("50000"),
                notional=Decimal("50000"),
                unrealized_pnl=Decimal("0"),
                liquidation_price=Decimal("40000"),
                liquidation_distance=0.2
            )

    def test_liquidation_distance_non_negative(self):
        """Liquidation distance cannot be negative."""
        with pytest.raises(ValueError):
            PositionRisk(
                symbol="BTC",
                direction=Direction.LONG,
                quantity=Decimal("1"),
                entry_price=Decimal("50000"),
                mark_price=Decimal("50000"),
                exposure=Decimal("50000"),
                notional=Decimal("50000"),
                unrealized_pnl=Decimal("0"),
                liquidation_price=Decimal("40000"),
                liquidation_distance=-0.1  # Invalid
            )


class TestOrderLifecycleStates:
    """Verify order status transitions."""

    def test_order_status_values(self):
        """All order statuses should be distinct."""
        statuses = list(OrderStatus)
        assert len(statuses) == len(set(s.value for s in statuses))

    def test_terminal_states(self):
        """Verify terminal order states."""
        terminal_states = {
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED
        }
        for status in terminal_states:
            assert status in OrderStatus


class TestReconciliationActions:
    """Verify reconciliation action semantics."""

    def test_reconciliation_actions_distinct(self):
        """All reconciliation actions should be distinct."""
        actions = list(ReconciliationAction)
        assert len(actions) == len(set(a.value for a in actions))

    def test_emergency_close_exists(self):
        """EMERGENCY_CLOSE action should exist for unknown positions."""
        assert ReconciliationAction.EMERGENCY_CLOSE in ReconciliationAction


class TestTradeOutcomeDerivation:
    """Verify trade outcome is derived correctly."""

    def test_open_trade_has_open_outcome(self):
        """Trade without exit should have OPEN outcome."""
        trade = TradeRecord(
            trade_id="test_1",
            symbol="BTC",
            strategy="test",
            direction="LONG",
            entry_time_ns=1000000000,
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
            # No exit details
        )
        assert trade.outcome == TradeOutcome.OPEN

    def test_winning_trade_outcome(self):
        """Trade with positive PnL should have WIN outcome."""
        trade = TradeRecord(
            trade_id="test_2",
            symbol="BTC",
            strategy="test",
            direction="LONG",
            entry_time_ns=1000000000,
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1",
            exit_time_ns=2000000000,
            exit_price=51000.0,
            realized_pnl=1000.0,
            net_pnl=990.0  # Positive
        )
        assert trade.outcome == TradeOutcome.WIN

    def test_losing_trade_outcome(self):
        """Trade with negative PnL should have LOSS outcome."""
        trade = TradeRecord(
            trade_id="test_3",
            symbol="BTC",
            strategy="test",
            direction="LONG",
            entry_time_ns=1000000000,
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1",
            exit_time_ns=2000000000,
            exit_price=49000.0,
            realized_pnl=-1000.0,
            net_pnl=-1010.0  # Negative
        )
        assert trade.outcome == TradeOutcome.LOSS


class TestAlertLevelHierarchy:
    """Verify alert level ordering."""

    def test_emergency_highest(self):
        """EMERGENCY should be highest severity."""
        assert AlertLevel.EMERGENCY.value > AlertLevel.CRITICAL.value

    def test_info_lowest(self):
        """INFO should be lowest severity."""
        assert AlertLevel.INFO.value < AlertLevel.WARNING.value
        assert AlertLevel.INFO.value < AlertLevel.ERROR.value


class TestAssumptionStatusStates:
    """Verify assumption status states."""

    def test_all_states_defined(self):
        """All expected assumption states should exist."""
        expected_states = {'UNTESTED', 'VALID', 'WARNING', 'INVALID', 'EXPIRED'}
        actual_states = {s.name for s in AssumptionStatus}
        assert expected_states == actual_states


class TestSystemRegimeStates:
    """Verify system regime states."""

    def test_all_regimes_defined(self):
        """All expected system regimes should exist."""
        expected_regimes = {
            'UNKNOWN',
            'EDGE_PRESENT',
            'EDGE_DECAYING',
            'EDGE_GONE',
            'REGIME_CHANGE'
        }
        actual_regimes = {r.name for r in SystemRegime}
        assert expected_regimes == actual_regimes


class TestCrossLayerTypeCompatibility:
    """Verify types are compatible across layer boundaries."""

    def test_action_type_in_execution_result(self):
        """ActionType from arbitration should work in ExecutionResult."""
        result = ExecutionResult(
            symbol="BTC",
            action=ActionType.ENTRY,
            success=True,
            state_before=PositionState.FLAT,
            state_after=PositionState.ENTERING,
            timestamp=1000.0
        )
        assert result.action == ActionType.ENTRY

    def test_position_state_in_execution_result(self):
        """PositionState from position layer should work in ExecutionResult."""
        result = ExecutionResult(
            symbol="BTC",
            action=ActionType.EXIT,
            success=True,
            state_before=PositionState.OPEN,
            state_after=PositionState.CLOSING,
            timestamp=1000.0
        )
        assert result.state_before == PositionState.OPEN

    def test_direction_in_position_risk(self):
        """Direction from position types should work in risk types."""
        risk = PositionRisk(
            symbol="BTC",
            direction=Direction.LONG,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            mark_price=Decimal("51000"),
            exposure=Decimal("51000"),
            notional=Decimal("51000"),
            unrealized_pnl=Decimal("1000"),
            liquidation_price=Decimal("40000"),
            liquidation_distance=0.22
        )
        assert risk.direction == Direction.LONG


class TestDataSerializability:
    """Verify types can be serialized for logging/storage."""

    def test_execution_result_to_dict(self):
        """ExecutionResult should serialize to dict."""
        result = ExecutionResult(
            symbol="BTC",
            action=ActionType.ENTRY,
            success=True,
            state_before=PositionState.FLAT,
            state_after=PositionState.ENTERING,
            timestamp=1000.0
        )
        d = result.to_log_dict()
        assert isinstance(d, dict)
        assert d["symbol"] == "BTC"
        assert d["action"] == "ENTRY"

    def test_trade_record_to_dict(self):
        """TradeRecord should serialize to dict."""
        trade = TradeRecord(
            trade_id="test_1",
            symbol="BTC",
            strategy="test",
            direction="LONG",
            entry_time_ns=1000000000,
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
        )
        d = trade.to_dict()
        assert isinstance(d, dict)
        assert d["trade_id"] == "test_1"

    def test_alert_to_dict(self):
        """Alert should serialize to dict."""
        alert = Alert(
            alert_id="alert_1",
            level=AlertLevel.WARNING,
            category="risk",
            message="Test alert"
        )
        d = alert.to_dict()
        assert isinstance(d, dict)
        assert d["level"] == "WARNING"

    def test_assumption_to_dict(self):
        """Assumption should serialize to dict."""
        assumption = Assumption(
            name="test_assumption",
            description="Test",
            category="test"
        )
        d = assumption.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "test_assumption"
