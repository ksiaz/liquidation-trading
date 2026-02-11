"""Phase C: Stability Observer Tests.

Verifies the stability observation infrastructure for live market monitoring.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase C requirements:
- No mandate storms
- No oscillations
- No deadlocks
- No state corruption
"""

import pytest
import time
from decimal import Decimal
from unittest.mock import patch

from runtime.stability_observer import (
    StabilityObserver,
    StabilityIssue,
    StabilityEvent,
    MandateRecord,
    ActionRecord,
    SymbolStats
)
from runtime.arbitration.types import Mandate, MandateType, Action, ActionType


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def observer():
    """Fresh stability observer instance."""
    return StabilityObserver(enabled=True)


def create_mandate(
    symbol: str = "BTCUSDT",
    mandate_type: MandateType = MandateType.ENTRY,
    authority: float = 5.0,
    direction: str = None,
    strategy_id: str = None
) -> Mandate:
    """Factory for test mandates."""
    return Mandate(
        symbol=symbol,
        type=mandate_type,
        authority=authority,
        timestamp=time.time(),
        direction=direction,
        strategy_id=strategy_id
    )


def create_action(
    symbol: str = "BTCUSDT",
    action_type: ActionType = ActionType.ENTRY,
    strategy_id: str = None
) -> Action:
    """Factory for test actions."""
    return Action(
        type=action_type,
        symbol=symbol,
        strategy_id=strategy_id
    )


# ==============================================================================
# TASK C.1: Basic Observation
# ==============================================================================

class TestBasicObservation:
    """Test basic mandate and action recording."""

    def test_record_mandate_increments_count(self, observer):
        """Recording mandate increments total count."""
        assert observer._total_mandates == 0

        observer.record_mandate(create_mandate(direction="LONG"))

        assert observer._total_mandates == 1

    def test_record_mandate_updates_symbol_stats(self, observer):
        """Recording mandate updates symbol statistics."""
        mandate = create_mandate(symbol="ETHUSDT", direction="LONG")

        observer.record_mandate(mandate)

        stats = observer._symbol_stats["ETHUSDT"]
        assert stats.total_mandates == 1
        assert stats.by_type["ENTRY"] == 1

    def test_record_action_increments_count(self, observer):
        """Recording action increments total count."""
        assert observer._total_actions == 0

        observer.record_action(create_action(), "BTCUSDT")

        assert observer._total_actions == 1

    def test_disabled_observer_does_nothing(self):
        """Disabled observer records nothing."""
        observer = StabilityObserver(enabled=False)

        observer.record_mandate(create_mandate(direction="LONG"))
        observer.record_action(create_action(), "BTCUSDT")

        assert observer._total_mandates == 0
        assert observer._total_actions == 0

    def test_mandate_type_distribution(self, observer):
        """Mandate types are tracked in distribution."""
        observer.record_mandate(create_mandate(mandate_type=MandateType.ENTRY))
        observer.record_mandate(create_mandate(mandate_type=MandateType.ENTRY))
        observer.record_mandate(create_mandate(mandate_type=MandateType.EXIT))
        observer.record_mandate(create_mandate(mandate_type=MandateType.BLOCK))

        dist = observer.get_mandate_distribution()

        assert dist["ENTRY"] == 2
        assert dist["EXIT"] == 1
        assert dist["BLOCK"] == 1


# ==============================================================================
# TASK C.2: Storm Detection
# ==============================================================================

class TestStormDetection:
    """Test mandate storm detection."""

    def test_no_storm_under_threshold(self, observer):
        """No storm flagged when under threshold."""
        # Record below threshold (use EXIT to avoid direction warnings)
        for _ in range(10):
            observer.record_mandate(create_mandate(mandate_type=MandateType.EXIT))

        status = observer.get_stability_status()
        assert status["status"] == "STABLE"
        assert status["recent_issues"]["CRITICAL"] == 0

    def test_storm_detected_over_threshold(self, observer):
        """Storm detected when over threshold."""
        # Override threshold for test
        observer.STORM_THRESHOLD = 10

        # Record over threshold (use EXIT to avoid direction warnings)
        for _ in range(15):
            observer.record_mandate(create_mandate(mandate_type=MandateType.EXIT))

        # Should have storm issues
        issues = observer.get_recent_issues()
        storm_issues = [i for i in issues if i["issue"] == "STORM_EXCESSIVE_MANDATES"]
        assert len(storm_issues) > 0

    def test_storm_severity_is_critical(self, observer):
        """Storm issues have CRITICAL severity."""
        observer.STORM_THRESHOLD = 5

        # Use EXIT to avoid direction warnings
        for _ in range(10):
            observer.record_mandate(create_mandate(mandate_type=MandateType.EXIT))

        issues = observer.get_recent_issues()
        storm_issues = [i for i in issues if i["issue"] == "STORM_EXCESSIVE_MANDATES"]

        for issue in storm_issues:
            assert issue["severity"] == "CRITICAL"


# ==============================================================================
# TASK C.3: Oscillation Detection
# ==============================================================================

class TestOscillationDetection:
    """Test ENTRY/EXIT oscillation detection."""

    def test_no_oscillation_normal_trading(self, observer):
        """No oscillation flagged for normal trading patterns."""
        # Normal sequence: ENTRY, wait, EXIT
        observer.record_mandate(create_mandate(mandate_type=MandateType.ENTRY))

        status = observer.get_symbol_status("BTCUSDT")
        assert "OSCILLATION_CYCLES" not in status.get("issues", [])

    def test_oscillation_detected_rapid_cycles(self, observer):
        """Oscillation detected on rapid ENTRY/EXIT cycles."""
        observer.OSCILLATION_CYCLE_THRESHOLD = 2
        observer.OSCILLATION_WINDOW_SEC = 1000.0  # Large window for test

        # Rapid cycles
        for _ in range(3):
            observer.record_mandate(create_mandate(
                mandate_type=MandateType.EXIT,
                direction="LONG"
            ))
            observer.record_mandate(create_mandate(
                mandate_type=MandateType.ENTRY,
                direction="LONG"
            ))

        status = observer.get_symbol_status("BTCUSDT")
        assert "OSCILLATION_CYCLES" in status.get("issues", [])

    def test_direction_flip_detected(self, observer):
        """Direction flips detected."""
        observer.OSCILLATION_FLIP_THRESHOLD = 2

        # LONG → SHORT → LONG → SHORT
        observer.record_mandate(create_mandate(
            mandate_type=MandateType.ENTRY,
            direction="LONG"
        ))
        observer.record_mandate(create_mandate(
            mandate_type=MandateType.ENTRY,
            direction="SHORT"
        ))
        observer.record_mandate(create_mandate(
            mandate_type=MandateType.ENTRY,
            direction="LONG"
        ))

        status = observer.get_symbol_status("BTCUSDT")
        assert "DIRECTION_FLIPS" in status.get("issues", [])

    def test_oscillation_reset_clears_counters(self, observer):
        """Reset clears oscillation counters."""
        observer.OSCILLATION_CYCLE_THRESHOLD = 2

        # Create oscillation state
        for _ in range(3):
            observer.record_mandate(create_mandate(mandate_type=MandateType.EXIT))
            observer.record_mandate(create_mandate(mandate_type=MandateType.ENTRY))

        # Reset
        observer.reset_symbol("BTCUSDT")

        status = observer.get_symbol_status("BTCUSDT")
        assert status["entry_exit_cycles"] == 0
        assert status["direction_flips"] == 0


# ==============================================================================
# TASK C.4: Deadlock Detection
# ==============================================================================

class TestDeadlockDetection:
    """Test deadlock detection (no mandates)."""

    def test_no_deadlock_recent_mandate(self, observer):
        """No deadlock when recent mandate exists."""
        observer.record_mandate(create_mandate(direction="LONG"))

        assert observer.check_deadlock("BTCUSDT") is False

    def test_deadlock_detected_no_recent_mandate(self, observer):
        """Deadlock detected when no recent mandates."""
        observer.DEADLOCK_WINDOW_SEC = 0.0  # Immediate deadlock for test

        observer.record_mandate(create_mandate(direction="LONG"))
        # Simulate time passing by setting old timestamp
        observer._symbol_stats["BTCUSDT"].last_mandate_time = time.time() - 1.0

        assert observer.check_deadlock("BTCUSDT") is True

    def test_deadlock_no_data_returns_false(self, observer):
        """No deadlock for unknown symbol."""
        assert observer.check_deadlock("UNKNOWN") is False


# ==============================================================================
# TASK C.5: State Corruption Detection
# ==============================================================================

class TestCorruptionDetection:
    """Test state corruption detection."""

    def test_entry_without_direction_flagged(self, observer):
        """ENTRY without direction flagged as corruption."""
        mandate = create_mandate(
            mandate_type=MandateType.ENTRY,
            direction=None  # Missing direction
        )

        observer.record_mandate(mandate)

        issues = observer.get_recent_issues()
        missing_field_issues = [
            i for i in issues
            if i["issue"] == "CORRUPTION_MISSING_FIELD"
        ]
        assert len(missing_field_issues) == 1
        assert missing_field_issues[0]["details"]["missing"] == "direction"

    def test_valid_entry_not_flagged(self, observer):
        """Valid ENTRY with direction not flagged."""
        mandate = create_mandate(
            mandate_type=MandateType.ENTRY,
            direction="LONG"
        )

        observer.record_mandate(mandate)

        issues = observer.get_recent_issues()
        corruption_issues = [
            i for i in issues
            if "CORRUPTION" in i["issue"]
        ]
        assert len(corruption_issues) == 0

    def test_exit_without_direction_ok(self, observer):
        """EXIT without direction is valid (not flagged)."""
        mandate = create_mandate(
            mandate_type=MandateType.EXIT,
            direction=None
        )

        observer.record_mandate(mandate)

        issues = observer.get_recent_issues()
        corruption_issues = [
            i for i in issues
            if "CORRUPTION" in i["issue"]
        ]
        assert len(corruption_issues) == 0


# ==============================================================================
# TASK C.6: Stability Status
# ==============================================================================

class TestStabilityStatus:
    """Test overall stability status reporting."""

    def test_stable_status_no_issues(self, observer):
        """STABLE status when no issues."""
        observer.record_mandate(create_mandate(direction="LONG"))

        status = observer.get_stability_status()
        assert status["status"] == "STABLE"

    def test_caution_status_warning(self, observer):
        """CAUTION status on single warning."""
        observer._record_issue(
            StabilityIssue.OSCILLATION_ENTRY_EXIT_CYCLE,
            "BTCUSDT",
            "WARNING",
            {}
        )

        status = observer.get_stability_status()
        assert status["status"] == "CAUTION"

    def test_degraded_status_multiple_warnings(self, observer):
        """DEGRADED status on multiple warnings."""
        for _ in range(5):
            observer._record_issue(
                StabilityIssue.OSCILLATION_ENTRY_EXIT_CYCLE,
                "BTCUSDT",
                "WARNING",
                {}
            )

        status = observer.get_stability_status()
        assert status["status"] == "DEGRADED"

    def test_critical_status_critical_issue(self, observer):
        """CRITICAL status on critical issue."""
        observer._record_issue(
            StabilityIssue.STORM_EXCESSIVE_MANDATES,
            "BTCUSDT",
            "CRITICAL",
            {}
        )

        status = observer.get_stability_status()
        assert status["status"] == "CRITICAL"

    def test_status_includes_rates(self, observer):
        """Status includes mandate/action rates."""
        observer.record_mandate(create_mandate())
        observer.record_action(create_action(), "BTCUSDT")

        status = observer.get_stability_status()

        assert "mandate_rate_per_sec" in status
        assert "action_rate_per_sec" in status
        assert status["mandate_rate_per_sec"] >= 0
        assert status["action_rate_per_sec"] >= 0


# ==============================================================================
# TASK C.7: Multi-Symbol Independence
# ==============================================================================

class TestMultiSymbolIndependence:
    """Test symbol-independent tracking."""

    def test_symbols_tracked_independently(self, observer):
        """Each symbol has independent stats."""
        observer.record_mandate(create_mandate(symbol="BTCUSDT", direction="LONG"))
        observer.record_mandate(create_mandate(symbol="BTCUSDT", direction="LONG"))
        observer.record_mandate(create_mandate(symbol="ETHUSDT", direction="LONG"))

        btc_status = observer.get_symbol_status("BTCUSDT")
        eth_status = observer.get_symbol_status("ETHUSDT")

        assert btc_status["total_mandates"] == 2
        assert eth_status["total_mandates"] == 1

    def test_oscillation_per_symbol(self, observer):
        """Oscillation tracked per symbol."""
        observer.OSCILLATION_CYCLE_THRESHOLD = 2

        # Oscillation on BTC only
        for _ in range(3):
            observer.record_mandate(create_mandate(
                symbol="BTCUSDT",
                mandate_type=MandateType.EXIT
            ))
            observer.record_mandate(create_mandate(
                symbol="BTCUSDT",
                mandate_type=MandateType.ENTRY,
                direction="LONG"
            ))

        # Normal on ETH
        observer.record_mandate(create_mandate(symbol="ETHUSDT", direction="LONG"))

        btc_status = observer.get_symbol_status("BTCUSDT")
        eth_status = observer.get_symbol_status("ETHUSDT")

        assert "OSCILLATION_CYCLES" in btc_status.get("issues", [])
        assert "OSCILLATION_CYCLES" not in eth_status.get("issues", [])


# ==============================================================================
# TASK C.8: Summary and Reporting
# ==============================================================================

class TestSummaryReporting:
    """Test comprehensive summary reporting."""

    def test_summary_includes_all_sections(self, observer):
        """Summary includes all required sections."""
        observer.record_mandate(create_mandate(direction="LONG"))
        observer.record_action(create_action(), "BTCUSDT")

        summary = observer.summary()

        assert "status" in summary
        assert "runtime_sec" in summary
        assert "total_mandates" in summary
        assert "total_actions" in summary
        assert "mandate_distribution" in summary
        assert "action_distribution" in summary
        assert "symbols" in summary

    def test_summary_symbol_details(self, observer):
        """Summary includes per-symbol details."""
        observer.record_mandate(create_mandate(symbol="BTCUSDT", direction="LONG"))
        observer.record_mandate(create_mandate(symbol="ETHUSDT", direction="LONG"))

        summary = observer.summary()

        assert "BTCUSDT" in summary["symbols"]
        assert "ETHUSDT" in summary["symbols"]

    def test_issue_history_limited(self, observer):
        """Issue history respects max limit."""
        observer = StabilityObserver(max_issues=5)

        for i in range(10):
            observer._record_issue(
                StabilityIssue.OSCILLATION_ENTRY_EXIT_CYCLE,
                "BTCUSDT",
                "INFO",
                {"iteration": i}
            )

        assert len(observer._issues) == 5


# ==============================================================================
# TASK C.9: Observational Invariant
# ==============================================================================

class TestObservationalInvariant:
    """Verify observer is purely observational."""

    def test_recording_does_not_modify_mandate(self, observer):
        """Recording does not modify the mandate object."""
        mandate = create_mandate(direction="LONG")
        original_type = mandate.type
        original_symbol = mandate.symbol
        original_direction = mandate.direction

        observer.record_mandate(mandate)

        # Mandate unchanged
        assert mandate.type == original_type
        assert mandate.symbol == original_symbol
        assert mandate.direction == original_direction

    def test_recording_does_not_modify_action(self, observer):
        """Recording does not modify the action object."""
        action = create_action(action_type=ActionType.ENTRY)
        original_type = action.type
        original_symbol = action.symbol

        observer.record_action(action, "BTCUSDT")

        # Action unchanged
        assert action.type == original_type
        assert action.symbol == original_symbol

    def test_no_feedback_to_source(self, observer):
        """Observer has no methods to modify sources."""
        # Verify no methods that could affect mandate generation
        assert not hasattr(observer, "block_mandate")
        assert not hasattr(observer, "modify_mandate")
        assert not hasattr(observer, "filter_mandate")
        assert not hasattr(observer, "set_threshold")  # No runtime tuning


# ==============================================================================
# TASK C.10: Edge Cases
# ==============================================================================

class TestEdgeCases:
    """Test edge case handling."""

    def test_empty_observer_status(self, observer):
        """Empty observer returns valid status."""
        status = observer.get_stability_status()

        assert status["status"] == "STABLE"
        assert status["total_mandates"] == 0
        assert status["total_actions"] == 0

    def test_unknown_symbol_status(self, observer):
        """Unknown symbol returns NO_DATA status."""
        status = observer.get_symbol_status("UNKNOWN_SYMBOL")

        assert status["status"] == "NO_DATA"

    def test_max_history_respected(self):
        """Max history limit is respected."""
        observer = StabilityObserver(max_history=10)

        for _ in range(20):
            observer.record_mandate(create_mandate(mandate_type=MandateType.EXIT))

        assert len(observer._mandates) == 10

    def test_concurrent_symbols_no_interference(self, observer):
        """Multiple symbols don't interfere."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        for symbol in symbols:
            for _ in range(5):
                observer.record_mandate(create_mandate(symbol=symbol, direction="LONG"))

        for symbol in symbols:
            status = observer.get_symbol_status(symbol)
            assert status["total_mandates"] == 5
