"""Phase D: Stability Integration Tests.

Verifies stability observer integrates correctly with execution path.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase D requirements:
- End-to-end stability monitoring
- Integration with arbitration and execution
- No feedback loops (observation only)
"""

import pytest
import time
from decimal import Decimal
from typing import List, Dict

from runtime.stability_observer import StabilityObserver, StabilityIssue
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.arbitration.types import Mandate, MandateType, Action, ActionType
from runtime.executor.controller import ExecutionController
from runtime.risk.types import RiskConfig, AccountState
from runtime.position.types import PositionState


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def observer():
    """Fresh stability observer."""
    return StabilityObserver(enabled=True)


@pytest.fixture
def arbitrator():
    """Fresh mandate arbitrator."""
    return MandateArbitrator()


@pytest.fixture
def controller():
    """Fresh execution controller with permissive risk config."""
    config = RiskConfig(
        L_max=100.0,  # Very permissive for tests
        L_target=50.0,
        L_symbol_max=50.0
    )
    return ExecutionController(risk_config=config)


@pytest.fixture
def account():
    """Test account state."""
    return AccountState(
        equity=Decimal("100000"),
        margin_available=Decimal("100000"),
        timestamp=time.time()
    )


def create_entry_mandate(
    symbol: str = "BTCUSDT",
    direction: str = "LONG",
    quantity: Decimal = Decimal("0.01"),
    entry_price: Decimal = Decimal("50000"),
    authority: float = 5.0,
    strategy_id: str = "TEST"
) -> Mandate:
    """Create ENTRY mandate with all required fields."""
    return Mandate(
        symbol=symbol,
        type=MandateType.ENTRY,
        authority=authority,
        timestamp=time.time(),
        direction=direction,
        strategy_id=strategy_id,
        quantity=quantity,
        entry_price=entry_price
    )


def create_exit_mandate(
    symbol: str = "BTCUSDT",
    authority: float = 5.0,
    strategy_id: str = "TEST"
) -> Mandate:
    """Create EXIT mandate."""
    return Mandate(
        symbol=symbol,
        type=MandateType.EXIT,
        authority=authority,
        timestamp=time.time(),
        strategy_id=strategy_id
    )


# ==============================================================================
# TASK D.1: Observer + Arbitrator Integration
# ==============================================================================

class TestObserverArbitratorIntegration:
    """Test stability observer integrates with arbitrator."""

    def test_observer_records_mandates_before_arbitration(self, observer, arbitrator):
        """Observer records mandates before arbitration."""
        mandates = [
            create_entry_mandate(symbol="BTCUSDT", direction="LONG"),
            create_entry_mandate(symbol="ETHUSDT", direction="SHORT"),
        ]

        # Record mandates (as would happen in real flow)
        for mandate in mandates:
            observer.record_mandate(mandate)

        # Arbitrate
        actions = arbitrator.arbitrate_all(mandates)

        # Record actions
        for symbol, action in actions.items():
            observer.record_action(action, symbol)

        # Verify observer recorded both
        assert observer._total_mandates == 2
        assert observer._total_actions == 2

    def test_observer_records_arbitration_results(self, observer, arbitrator):
        """Observer correctly records arbitration outcomes."""
        mandates = [
            create_entry_mandate(symbol="BTCUSDT", direction="LONG"),
            create_exit_mandate(symbol="ETHUSDT"),
        ]

        for mandate in mandates:
            observer.record_mandate(mandate)

        actions = arbitrator.arbitrate_all(mandates)
        for symbol, action in actions.items():
            observer.record_action(action, symbol)

        # Verify action distribution
        action_dist = observer.get_action_distribution()
        assert action_dist["ENTRY"] == 1
        assert action_dist["EXIT"] == 1

    def test_exit_supremacy_recorded_correctly(self, observer, arbitrator):
        """EXIT supremacy is reflected in observer records."""
        # ENTRY and EXIT for same symbol - EXIT should win
        mandates = [
            create_entry_mandate(symbol="BTCUSDT", direction="LONG", authority=10.0),
            create_exit_mandate(symbol="BTCUSDT", authority=1.0),  # Lower authority but EXIT wins
        ]

        for mandate in mandates:
            observer.record_mandate(mandate)

        actions = arbitrator.arbitrate_all(mandates)
        for symbol, action in actions.items():
            observer.record_action(action, symbol)

        # Mandate distribution shows both
        mandate_dist = observer.get_mandate_distribution()
        assert mandate_dist["ENTRY"] == 1
        assert mandate_dist["EXIT"] == 1

        # But action shows EXIT won
        action_dist = observer.get_action_distribution()
        assert action_dist.get("ENTRY", 0) == 0
        assert action_dist["EXIT"] == 1


# ==============================================================================
# TASK D.2: Observer + ExecutionController Integration
# ==============================================================================

class TestObserverExecutionIntegration:
    """Test stability observer integrates with execution controller."""

    def test_full_execution_path_observed(self, observer, controller, account):
        """Full execution path is observed correctly."""
        mandates = [
            create_entry_mandate(
                symbol="BTCUSDT",
                direction="LONG",
                quantity=Decimal("0.01"),
                entry_price=Decimal("50000")
            )
        ]
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Record mandates
        for mandate in mandates:
            observer.record_mandate(mandate)

        # Execute
        stats = controller.process_cycle(mandates, account, mark_prices)

        # Record action from arbitration (internal to controller)
        # In real integration, we'd hook into the controller
        # For test, we verify mandates were recorded
        assert observer._total_mandates == 1
        assert stats.mandates_received == 1

    def test_rejected_execution_does_not_affect_observation(self, observer, account):
        """Rejected executions don't corrupt observer state."""
        # Controller with restrictive config (all limits must be <= L_max)
        strict_config = RiskConfig(
            L_max=0.001,
            L_target=0.0005,
            L_symbol_max=0.001
        )  # Very restrictive
        strict_controller = ExecutionController(risk_config=strict_config)

        mandates = [
            create_entry_mandate(
                symbol="BTCUSDT",
                direction="LONG",
                quantity=Decimal("1.0"),  # Large position
                entry_price=Decimal("50000")
            )
        ]
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Record mandate
        observer.record_mandate(mandates[0])

        # Execute (will be rejected by risk)
        stats = strict_controller.process_cycle(mandates, account, mark_prices)

        # Mandate still recorded even though rejected
        assert observer._total_mandates == 1
        assert stats.actions_rejected == 1

        # Observer status unaffected by execution outcome
        status = observer.get_stability_status()
        assert status["total_mandates"] == 1


# ==============================================================================
# TASK D.3: Multi-Symbol Integration
# ==============================================================================

class TestMultiSymbolIntegration:
    """Test stability observation across multiple symbols."""

    def test_multi_symbol_arbitration_observed(self, observer, arbitrator):
        """Multi-symbol arbitration is correctly observed."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        mandates = [
            create_entry_mandate(symbol=s, direction="LONG")
            for s in symbols
        ]

        # Record all
        for mandate in mandates:
            observer.record_mandate(mandate)

        # Arbitrate
        actions = arbitrator.arbitrate_all(mandates)
        for symbol, action in actions.items():
            observer.record_action(action, symbol)

        # Verify per-symbol tracking
        for symbol in symbols:
            status = observer.get_symbol_status(symbol)
            assert status["total_mandates"] == 1
            assert status["status"] == "STABLE"

    def test_multi_symbol_independence_in_observer(self, observer):
        """Symbol independence is maintained in observer."""
        # Create oscillation on BTC only
        observer.OSCILLATION_CYCLE_THRESHOLD = 2

        # BTC oscillation
        for _ in range(3):
            observer.record_mandate(create_exit_mandate(symbol="BTCUSDT"))
            observer.record_mandate(create_entry_mandate(symbol="BTCUSDT"))

        # ETH normal
        observer.record_mandate(create_entry_mandate(symbol="ETHUSDT"))

        # BTC should have issues
        btc_status = observer.get_symbol_status("BTCUSDT")
        assert "OSCILLATION_CYCLES" in btc_status.get("issues", [])

        # ETH should be stable
        eth_status = observer.get_symbol_status("ETHUSDT")
        assert eth_status["status"] == "STABLE"


# ==============================================================================
# TASK D.4: Storm Detection in Real Flow
# ==============================================================================

class TestStormDetectionIntegration:
    """Test storm detection in realistic execution flow."""

    def test_rapid_mandate_burst_detected(self, observer, arbitrator):
        """Rapid mandate burst is detected as storm."""
        observer.STORM_THRESHOLD = 10

        # Simulate rapid burst
        for i in range(15):
            mandate = create_exit_mandate(symbol="BTCUSDT", strategy_id=f"S{i}")
            observer.record_mandate(mandate)

        # Should detect storm
        issues = observer.get_recent_issues()
        storm_issues = [i for i in issues if "STORM" in i["issue"]]
        assert len(storm_issues) > 0

    def test_normal_rate_no_storm(self, observer, arbitrator):
        """Normal mandate rate doesn't trigger storm."""
        observer.STORM_THRESHOLD = 100  # High threshold

        # Normal rate (10 mandates)
        for i in range(10):
            mandate = create_exit_mandate(symbol="BTCUSDT", strategy_id=f"S{i}")
            observer.record_mandate(mandate)

        status = observer.get_stability_status()
        assert status["recent_issues"]["CRITICAL"] == 0


# ==============================================================================
# TASK D.5: Oscillation Detection in Real Flow
# ==============================================================================

class TestOscillationDetectionIntegration:
    """Test oscillation detection in realistic execution flow."""

    def test_entry_exit_oscillation_detected(self, observer, arbitrator, controller, account):
        """ENTRY/EXIT oscillation is detected."""
        observer.OSCILLATION_CYCLE_THRESHOLD = 2
        observer.OSCILLATION_WINDOW_SEC = 1000.0  # Large window for test

        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Simulate oscillation pattern
        for _ in range(3):
            # EXIT (would be rejected since no position, but observer still records)
            exit_mandate = create_exit_mandate(symbol="BTCUSDT")
            observer.record_mandate(exit_mandate)

            # ENTRY
            entry_mandate = create_entry_mandate(symbol="BTCUSDT")
            observer.record_mandate(entry_mandate)

        # Should detect oscillation
        status = observer.get_symbol_status("BTCUSDT")
        assert "OSCILLATION_CYCLES" in status.get("issues", [])

    def test_direction_flip_oscillation_detected(self, observer):
        """Rapid direction flips are detected."""
        observer.OSCILLATION_FLIP_THRESHOLD = 2

        # Flip pattern: LONG → SHORT → LONG
        observer.record_mandate(create_entry_mandate(direction="LONG"))
        observer.record_mandate(create_entry_mandate(direction="SHORT"))
        observer.record_mandate(create_entry_mandate(direction="LONG"))

        status = observer.get_symbol_status("BTCUSDT")
        assert "DIRECTION_FLIPS" in status.get("issues", [])


# ==============================================================================
# TASK D.6: End-to-End Integration
# ==============================================================================

class TestEndToEndIntegration:
    """Full end-to-end integration tests."""

    def test_complete_trading_cycle_observed(self, observer, controller, account):
        """Complete trading cycle: ENTRY → HOLD → EXIT."""
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Step 1: ENTRY
        entry_mandate = create_entry_mandate(
            symbol="BTCUSDT",
            direction="LONG",
            quantity=Decimal("0.01"),
            entry_price=Decimal("50000")
        )
        observer.record_mandate(entry_mandate)
        stats1 = controller.process_cycle([entry_mandate], account, mark_prices)

        # Verify entry
        assert stats1.actions_executed == 1
        pos = controller.state_machine.get_position("BTCUSDT")
        assert pos.state == PositionState.OPEN

        # Step 2: HOLD (no mandate)
        # (nothing to record)

        # Step 3: EXIT
        exit_mandate = create_exit_mandate(symbol="BTCUSDT")
        observer.record_mandate(exit_mandate)
        stats2 = controller.process_cycle([exit_mandate], account, mark_prices)

        # Verify exit
        assert stats2.actions_executed == 1

        # Verify observer recorded complete cycle
        assert observer._total_mandates == 2
        mandate_dist = observer.get_mandate_distribution()
        assert mandate_dist["ENTRY"] == 1
        assert mandate_dist["EXIT"] == 1

    def test_stability_status_through_cycle(self, observer, controller, account):
        """Stability status remains stable through normal cycle."""
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Normal cycle
        entry = create_entry_mandate(symbol="BTCUSDT", quantity=Decimal("0.01"))
        observer.record_mandate(entry)
        controller.process_cycle([entry], account, mark_prices)

        # Check stability
        status = observer.get_stability_status()
        assert status["status"] == "STABLE"

        # Exit
        exit_m = create_exit_mandate(symbol="BTCUSDT")
        observer.record_mandate(exit_m)
        controller.process_cycle([exit_m], account, mark_prices)

        # Still stable
        status = observer.get_stability_status()
        assert status["status"] == "STABLE"


# ==============================================================================
# TASK D.7: No Feedback Verification
# ==============================================================================

class TestNoFeedbackIntegration:
    """Verify observation doesn't affect execution."""

    def test_observer_does_not_block_execution(self, observer, controller, account):
        """Observer recording doesn't block mandate execution."""
        mark_prices = {"BTCUSDT": Decimal("50000")}

        mandate = create_entry_mandate(symbol="BTCUSDT", quantity=Decimal("0.01"))

        # Record in observer
        observer.record_mandate(mandate)

        # Execute - should work regardless of observer
        stats = controller.process_cycle([mandate], account, mark_prices)

        assert stats.actions_executed == 1

    def test_observer_critical_does_not_halt_execution(self, observer, controller, account):
        """Critical stability issues don't halt execution."""
        mark_prices = {"BTCUSDT": Decimal("50000")}

        # Force a CRITICAL issue
        observer._record_issue(
            StabilityIssue.STORM_EXCESSIVE_MANDATES,
            "BTCUSDT",
            "CRITICAL",
            {"test": True}
        )

        # Verify CRITICAL status
        status = observer.get_stability_status()
        assert status["status"] == "CRITICAL"

        # Execution should still work
        mandate = create_entry_mandate(symbol="BTCUSDT", quantity=Decimal("0.01"))
        stats = controller.process_cycle([mandate], account, mark_prices)

        # Execution proceeds (observer is purely observational)
        assert stats.mandates_received == 1

    def test_observer_has_no_execution_control(self, observer):
        """Observer cannot modify execution flow."""
        # Verify no methods that could affect execution
        assert not hasattr(observer, 'block_execution')
        assert not hasattr(observer, 'halt_trading')
        assert not hasattr(observer, 'reject_mandate')
        assert not hasattr(observer, 'modify_action')


# ==============================================================================
# TASK D.8: Comprehensive Summary
# ==============================================================================

class TestComprehensiveSummary:
    """Test comprehensive summary generation."""

    def test_summary_after_realistic_session(self, observer, arbitrator, controller, account):
        """Summary captures realistic trading session."""
        mark_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000"),
        }

        # Simulate session with multiple symbols
        symbols = ["BTCUSDT", "ETHUSDT"]

        for symbol in symbols:
            # Entry
            entry = create_entry_mandate(
                symbol=symbol,
                quantity=Decimal("0.01"),
                entry_price=mark_prices[symbol]
            )
            observer.record_mandate(entry)

        # Arbitrate
        all_mandates = [
            create_entry_mandate(s, quantity=Decimal("0.01"), entry_price=mark_prices[s])
            for s in symbols
        ]
        actions = arbitrator.arbitrate_all(all_mandates)
        for symbol, action in actions.items():
            observer.record_action(action, symbol)

        # Get summary
        summary = observer.summary()

        # Verify comprehensive data
        assert summary["status"] == "STABLE"
        assert summary["total_mandates"] == 2
        assert summary["total_actions"] == 2
        assert len(summary["symbols"]) == 2
        assert "BTCUSDT" in summary["symbols"]
        assert "ETHUSDT" in summary["symbols"]

    def test_summary_includes_all_stability_metrics(self, observer):
        """Summary includes all stability metrics."""
        # Create some data
        observer.record_mandate(create_entry_mandate(direction="LONG"))
        observer.record_action(
            Action(type=ActionType.ENTRY, symbol="BTCUSDT"),
            "BTCUSDT"
        )

        summary = observer.summary()

        # Required fields
        assert "status" in summary
        assert "runtime_sec" in summary
        assert "total_mandates" in summary
        assert "total_actions" in summary
        assert "mandate_rate_per_sec" in summary
        assert "action_rate_per_sec" in summary
        assert "mandate_distribution" in summary
        assert "action_distribution" in summary
        assert "symbols" in summary
        assert "recent_issues" in summary
