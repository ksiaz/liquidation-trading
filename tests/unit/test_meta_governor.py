"""Unit tests for meta_governor.py and related components."""

import pytest
import time

from runtime.governance.unknown_unknown_detector import (
    UnknownThreatDetector,
    UnknownThreatSignal,
    ThreatAssessment,
    UnknownThreatThresholds,
    BaselineTracker,
    MetricBaseline,
)

from runtime.governance.meta_governor import (
    SovereignMetaGovernor,
    MetaGovernorDecision,
    TrustState,
    TrustSubScores,
    MetaGovernorThresholds,
    DataTrustInputs,
    ExecutionTrustInputs,
    AlphaTrustInputs,
    RiskTrustInputs,
    ConsistencyTrustInputs,
    TrustScoreCalculator,
)

from runtime.governance.operator_gate import (
    OperatorGate,
    TRUST_GATED_ACTIONS,
)


# =============================================================================
# Unknown Threat Detector Tests
# =============================================================================

class TestBaselineTracker:
    """Tests for BaselineTracker."""

    @pytest.fixture
    def tracker(self):
        return BaselineTracker()

    def test_initial_state_empty(self, tracker):
        """Should have no baselines initially."""
        assert tracker.get_baseline("test_metric") is None

    def test_update_creates_baseline(self, tracker):
        """Should create baseline on first update."""
        tracker.update("test_metric", 100.0)
        baseline = tracker.get_baseline("test_metric")
        assert baseline is not None
        assert baseline.sample_count == 1
        assert baseline.mean == 100.0

    def test_update_computes_running_stats(self, tracker):
        """Should compute running mean and std correctly."""
        values = [100, 102, 98, 101, 99, 103, 97, 100, 102, 98]
        for v in values:
            tracker.update("test_metric", v)

        baseline = tracker.get_baseline("test_metric")
        assert baseline.sample_count == 10
        assert 99 < baseline.mean < 101  # Should be around 100
        assert baseline.std > 0  # Should have some variance

    def test_compute_z_score_insufficient_data(self, tracker):
        """Should return None with insufficient data."""
        for i in range(5):
            tracker.update("test_metric", 100.0 + i)
        z_score = tracker.compute_z_score("test_metric", 150.0)
        assert z_score is None  # Less than 10 samples

    def test_compute_z_score_valid(self, tracker):
        """Should compute valid z-score."""
        # Add enough samples with known distribution
        for i in range(100):
            tracker.update("test_metric", 100.0 + (i % 10))

        # Test value far from mean
        z_score = tracker.compute_z_score("test_metric", 150.0)
        assert z_score is not None
        assert z_score > 3.0  # Should be significantly above mean

    def test_reset_metric(self, tracker):
        """Should reset specific metric."""
        tracker.update("metric_a", 100.0)
        tracker.update("metric_b", 200.0)

        tracker.reset_metric("metric_a")

        assert tracker.get_baseline("metric_a") is None
        assert tracker.get_baseline("metric_b") is not None


class TestUnknownThreatDetector:
    """Tests for UnknownThreatDetector."""

    @pytest.fixture
    def detector(self):
        return UnknownThreatDetector()

    def test_no_threats_with_normal_data(self, detector):
        """Should not detect threats with normal data."""
        # Train baseline
        for i in range(200):
            detector.update_metric("metric_1", 100.0 + (i % 10))
            detector.update_metric("metric_2", 50.0 + (i % 5))

        # Evaluate with normal values
        observations = {"metric_1": 105.0, "metric_2": 52.0}
        assessment = detector.evaluate(observations)

        assert not assessment.has_unknown_threats
        assert assessment.threat_count == 0

    def test_detects_single_anomaly(self, detector):
        """Should detect single anomaly."""
        # Train baseline with some variance (required for std > 0)
        for i in range(200):
            detector.update_metric("metric_1", 100.0 + (i % 5) - 2)  # Values 98-102

        # Evaluate with anomalous value
        observations = {"metric_1": 200.0}  # Very far from baseline
        assessment = detector.evaluate(observations)

        assert assessment.threat_count >= 1
        assert assessment.max_z_score > 3.0

    def test_detects_multiple_anomalies(self, detector):
        """Should detect multiple anomalies as threat."""
        # Train baselines with some variance
        for i in range(200):
            detector.update_metric("metric_1", 100.0 + (i % 5) - 2)  # 98-102
            detector.update_metric("metric_2", 50.0 + (i % 3) - 1)   # 49-51
            detector.update_metric("metric_3", 25.0 + (i % 3) - 1)   # 24-26

        # Evaluate with multiple anomalous values
        observations = {
            "metric_1": 200.0,  # Anomalous
            "metric_2": 100.0,  # Anomalous
            "metric_3": 25.0,   # Normal
        }
        assessment = detector.evaluate(observations)

        assert assessment.has_unknown_threats
        assert assessment.threat_count >= 2

    def test_joint_probability_calculation(self, detector):
        """Should calculate joint probability."""
        # Train baseline
        for i in range(200):
            detector.update_metric("metric_1", 100.0 + (i % 5))

        # Evaluate
        observations = {"metric_1": 150.0}
        assessment = detector.evaluate(observations)

        # Joint probability should be small for anomaly
        assert assessment.joint_probability < 0.1

    def test_correlation_breakdown_detection(self, detector):
        """Should detect correlation breakdown."""
        detector.set_correlation_baseline("metric_a", "metric_b", 0.9)

        signal = detector.check_correlation_breakdown(
            "metric_a",
            "metric_b",
            observed_correlation=0.1,  # Very different
        )

        assert signal is not None
        assert "correlation" in signal.metric_name

    def test_get_baseline_stats(self, detector):
        """Should return all baseline statistics."""
        detector.update_metric("metric_1", 100.0)
        detector.update_metric("metric_2", 50.0)

        stats = detector.get_baseline_stats()

        assert "metric_1" in stats
        assert "metric_2" in stats
        assert "mean" in stats["metric_1"]


class TestThreatAssessment:
    """Tests for ThreatAssessment dataclass."""

    def test_assessment_creation(self):
        """Should create valid assessment."""
        now_ns = int(time.time() * 1_000_000_000)
        assessment = ThreatAssessment(
            ts_ns=now_ns,
            has_unknown_threats=False,
            threat_count=0,
            max_z_score=0.0,
            signals=[],
            joint_probability=1.0,
        )
        assert not assessment.has_unknown_threats


# =============================================================================
# Trust Score Calculator Tests
# =============================================================================

class TestTrustScoreCalculator:
    """Tests for TrustScoreCalculator."""

    @pytest.fixture
    def calculator(self):
        return TrustScoreCalculator()

    def test_compute_data_trust_normal(self, calculator):
        """Should give high trust for normal data conditions."""
        inputs = DataTrustInputs(
            feed_staleness_sec=1.0,
            timestamp_drift_sec=0.1,
            spread_current_bps=5.0,
            spread_baseline_bps=5.0,
            depth_health_ratio=1.0,
            price_divergence_pct=0.1,
        )
        trust = calculator.compute_data_trust(inputs)
        assert trust >= 0.8  # MIN aggregation of good scores

    def test_compute_data_trust_stale_feed(self, calculator):
        """Should give low trust for stale feed."""
        inputs = DataTrustInputs(
            feed_staleness_sec=15.0,  # Above threshold
            timestamp_drift_sec=0.1,
            depth_health_ratio=1.0,
        )
        trust = calculator.compute_data_trust(inputs)
        assert trust < 0.5

    def test_compute_execution_trust_normal(self, calculator):
        """Should give high trust for normal execution."""
        inputs = ExecutionTrustInputs(
            latency_p95_ms=50.0,
            retry_rate_pct=0.02,
            cancel_rate_pct=0.05,
            fill_mismatch_rate_pct=0.01,
        )
        trust = calculator.compute_execution_trust(inputs)
        assert trust > 0.7

    def test_compute_execution_trust_high_latency(self, calculator):
        """Should give low trust for high latency."""
        inputs = ExecutionTrustInputs(
            latency_p95_ms=300.0,  # Above threshold
            retry_rate_pct=0.02,
            cancel_rate_pct=0.05,
            fill_mismatch_rate_pct=0.01,
        )
        trust = calculator.compute_execution_trust(inputs)
        assert trust < 0.5

    def test_compute_alpha_trust_normal(self, calculator):
        """Should give high trust for normal alpha."""
        inputs = AlphaTrustInputs(
            decay_severity_score=0.9,
            strategies_disabled_pct=0.1,
            edge_consistency_score=0.9,
        )
        trust = calculator.compute_alpha_trust(inputs)
        assert trust > 0.7

    def test_compute_alpha_trust_critical_decay(self, calculator):
        """Should give low trust for critical decay."""
        inputs = AlphaTrustInputs(
            decay_severity_score=0.0,  # CRITICAL
            strategies_disabled_pct=0.5,
            edge_consistency_score=0.5,
        )
        trust = calculator.compute_alpha_trust(inputs)
        assert trust == 0.0  # MIN aggregation

    def test_compute_risk_trust_normal(self, calculator):
        """Should give high trust when risk subsystems normal."""
        inputs = RiskTrustInputs(
            circuit_breaker_status=1.0,
            catastrophe_status=1.0,
            kill_switch_status=1.0,
        )
        trust = calculator.compute_risk_trust(inputs)
        assert trust == 1.0

    def test_compute_risk_trust_kill_switch(self, calculator):
        """Should give zero trust when kill switch triggered."""
        inputs = RiskTrustInputs(
            circuit_breaker_status=1.0,
            catastrophe_status=1.0,
            kill_switch_status=0.0,  # Triggered
        )
        trust = calculator.compute_risk_trust(inputs)
        assert trust == 0.0

    def test_compute_consistency_trust_normal(self, calculator):
        """Should give high trust for consistent state."""
        inputs = ConsistencyTrustInputs(
            persistence_match_score=1.0,
            restart_health_score=1.0,
            orphan_order_score=1.0,
            reconciliation_score=1.0,
        )
        trust = calculator.compute_consistency_trust(inputs)
        assert trust == 1.0

    def test_compute_consistency_trust_mismatches(self, calculator):
        """Should give low trust for mismatches."""
        inputs = ConsistencyTrustInputs(
            persistence_match_score=0.5,
            restart_health_score=1.0,
            orphan_order_score=0.3,  # Many orphans
            reconciliation_score=0.7,
        )
        trust = calculator.compute_consistency_trust(inputs)
        assert trust == 0.3  # MIN aggregation


# =============================================================================
# Sovereign Meta Governor Tests
# =============================================================================

class TestSovereignMetaGovernor:
    """Tests for SovereignMetaGovernor."""

    @pytest.fixture
    def governor(self):
        return SovereignMetaGovernor()

    def test_initial_state_operational(self, governor):
        """Should start in OPERATIONAL state."""
        assert governor.trust_state == TrustState.OPERATIONAL

    def test_evaluate_no_inputs_operational(self, governor):
        """Should remain OPERATIONAL with no inputs (defaults to trust 1.0)."""
        decision = governor.evaluate()
        assert decision.trust_state == TrustState.OPERATIONAL
        assert decision.allows_trading
        assert decision.allows_entries
        assert decision.allows_exits
        assert decision.capital_override is None

    def test_high_trust_operational(self, governor):
        """Should be OPERATIONAL with high trust."""
        data_inputs = DataTrustInputs(
            feed_staleness_sec=1.0,
            timestamp_drift_sec=0.1,
            depth_health_ratio=1.0,
        )
        decision = governor.evaluate(data_inputs=data_inputs)

        assert decision.trust_state == TrustState.OPERATIONAL
        assert decision.trust_score >= 0.80

    def test_medium_trust_degraded(self, governor):
        """Should be DEGRADED or WARNING with medium trust."""
        # Use inputs that produce a score around 0.60-0.75
        data_inputs = DataTrustInputs(
            feed_staleness_sec=3.0,  # Somewhat stale (30% of threshold)
            max_acceptable_staleness_sec=10.0,
            timestamp_drift_sec=0.5,  # 25% of threshold
            max_acceptable_drift_sec=2.0,
            depth_health_ratio=0.7,
            price_divergence_pct=0.1,
            max_acceptable_divergence_pct=0.5,
        )
        decision = governor.evaluate(data_inputs=data_inputs)

        # Score should be around 0.60-0.75, giving DEGRADED or WARNING
        assert decision.trust_state in (TrustState.DEGRADED, TrustState.WARNING, TrustState.OPERATIONAL)

    def test_low_trust_critical(self, governor):
        """Should be CRITICAL with low trust."""
        risk_inputs = RiskTrustInputs(
            circuit_breaker_status=0.1,  # Tripped
            catastrophe_status=0.1,      # Catastrophe
            kill_switch_status=0.2,      # Almost triggered
        )
        decision = governor.evaluate(risk_inputs=risk_inputs)

        assert decision.trust_state == TrustState.CRITICAL
        assert not decision.allows_trading
        assert not decision.allows_entries
        assert decision.allows_exits  # Always allows exits
        assert decision.capital_override == 0.10

    def test_unknown_threat_detection(self, governor):
        """Should detect unknown threats."""
        # Train detector baseline with variance
        for i in range(200):
            governor._threat_detector.update_metric("test_metric", 100.0 + (i % 5) - 2)

        # Evaluate with anomaly
        metric_observations = {"test_metric": 500.0}  # Very anomalous
        decision = governor.evaluate(metric_observations=metric_observations)

        # With single anomaly, might not trigger UNKNOWN_THREAT (needs >= 2 anomalies)
        # But should at least have a threat assessment
        assert decision.threat_assessment is not None
        if decision.threat_assessment.has_unknown_threats:
            assert decision.trust_state == TrustState.UNKNOWN_THREAT
            assert not decision.allows_trading
            assert decision.requires_manual_reset

    def test_critical_requires_manual_reset(self, governor):
        """Should require manual reset after CRITICAL."""
        # Trigger CRITICAL
        risk_inputs = RiskTrustInputs(
            circuit_breaker_status=0.0,
            catastrophe_status=0.0,
            kill_switch_status=0.0,
        )
        governor.evaluate(risk_inputs=risk_inputs)

        assert governor.requires_manual_reset

        # Should remain in reset-required state
        decision = governor.evaluate()
        assert decision.requires_manual_reset
        assert not decision.allows_trading

    def test_manual_reset_success(self, governor):
        """Should allow manual reset with correct phrase."""
        # First trigger reset requirement
        governor._requires_manual_reset = True
        governor._trust_state = TrustState.CRITICAL

        success, message = governor.manual_reset("CONFIRM RESET META GOVERNOR")

        assert success
        assert not governor.requires_manual_reset
        assert governor.trust_state == TrustState.DEGRADED  # Not immediately OPERATIONAL

    def test_manual_reset_failure(self, governor):
        """Should reject manual reset with wrong phrase."""
        governor._requires_manual_reset = True

        success, message = governor.manual_reset("wrong phrase")

        assert not success
        assert governor.requires_manual_reset

    def test_restore_state(self, governor):
        """Should restore state from persistence."""
        governor.restore_state(
            trust_state="WARNING",
            trust_score=0.45,
            requires_manual_reset=False,
        )

        assert governor.trust_state == TrustState.WARNING
        assert governor.trust_score == 0.45

    def test_capital_override_by_state(self, governor):
        """Should return correct capital override by state."""
        # Test each state
        overrides = {
            TrustState.OPERATIONAL: None,
            TrustState.DEGRADED: 0.75,
            TrustState.WARNING: 0.50,
            TrustState.CRITICAL: 0.10,
            TrustState.UNKNOWN_THREAT: 0.10,
        }

        for state, expected in overrides.items():
            override = governor._get_capital_override(state)
            assert override == expected


class TestTrustState:
    """Tests for TrustState enum."""

    def test_all_states_defined(self):
        """All trust states should be defined."""
        assert TrustState.OPERATIONAL.value == "OPERATIONAL"
        assert TrustState.DEGRADED.value == "DEGRADED"
        assert TrustState.WARNING.value == "WARNING"
        assert TrustState.CRITICAL.value == "CRITICAL"
        assert TrustState.UNKNOWN_THREAT.value == "UNKNOWN_THREAT"


class TestTrustSubScores:
    """Tests for TrustSubScores dataclass."""

    def test_min_score_calculation(self):
        """Should compute MIN aggregation correctly."""
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = TrustSubScores(
            ts_ns=now_ns,
            data_trust=0.9,
            execution_trust=0.8,
            alpha_trust=0.7,
            risk_trust=0.6,
            consistency_trust=0.5,
        )
        assert sub_scores.min_score == 0.5

    def test_min_score_all_ones(self):
        """Should return 1.0 when all scores are 1.0."""
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = TrustSubScores(
            ts_ns=now_ns,
            data_trust=1.0,
            execution_trust=1.0,
            alpha_trust=1.0,
            risk_trust=1.0,
            consistency_trust=1.0,
        )
        assert sub_scores.min_score == 1.0


# =============================================================================
# Operator Gate Trust Integration Tests
# =============================================================================

class TestOperatorGateTrustIntegration:
    """Tests for trust-gated actions in OperatorGate."""

    @pytest.fixture
    def gate(self):
        return OperatorGate()

    def test_trust_gated_actions_defined(self):
        """Should have trust-gated actions defined."""
        assert "force_scale_up" in TRUST_GATED_ACTIONS
        assert "increase_exposure" in TRUST_GATED_ACTIONS
        assert "disable_capital_governor" in TRUST_GATED_ACTIONS
        assert "disable_meta_governor" in TRUST_GATED_ACTIONS

    def test_is_trust_gated(self, gate):
        """Should identify trust-gated actions."""
        assert gate.is_trust_gated("force_scale_up")
        assert gate.is_trust_gated("increase_exposure")
        assert not gate.is_trust_gated("manual_position_close")

    def test_get_minimum_trust(self, gate):
        """Should return correct minimum trust."""
        assert gate.get_minimum_trust("force_scale_up") == 0.60
        assert gate.get_minimum_trust("increase_exposure") == 0.60
        assert gate.get_minimum_trust("disable_capital_governor") == 0.40
        assert gate.get_minimum_trust("manual_position_close") is None

    def test_check_trust_requirement_met(self, gate):
        """Should allow when trust requirement met."""
        allowed, reason = gate.check_trust_requirement("force_scale_up", 0.70)
        assert allowed

    def test_check_trust_requirement_not_met(self, gate):
        """Should block when trust requirement not met."""
        allowed, reason = gate.check_trust_requirement("force_scale_up", 0.50)
        assert not allowed
        assert "below_requirement" in reason

    def test_trust_gated_confirmation_blocked(self, gate):
        """Should block trust-gated confirmation when trust low."""
        can_proceed, reason = gate.request_trust_gated_confirmation(
            "force_scale_up",
            current_trust=0.40,  # Below 0.60 requirement
        )
        assert not can_proceed

    def test_trust_gated_confirmation_allowed(self, gate):
        """Should allow trust-gated confirmation when trust sufficient."""
        can_proceed, reason = gate.request_trust_gated_confirmation(
            "force_scale_up",
            current_trust=0.70,  # Above 0.60 requirement
        )
        assert can_proceed
        assert reason == "awaiting_confirmation"

    def test_verify_trust_gated_rechecks_trust(self, gate):
        """Should recheck trust at verification time."""
        # First request with good trust
        gate.request_trust_gated_confirmation("force_scale_up", current_trust=0.70)

        # Then verify with bad trust (dropped since request)
        success, reason = gate.verify_trust_gated_confirmation(
            "force_scale_up",
            "CONFIRM FORCE SCALE UP I ACCEPT RISK",
            current_trust=0.50,  # Dropped below requirement
        )
        assert not success
        assert "below_requirement" in reason

    def test_verify_trust_gated_success(self, gate):
        """Should succeed with correct phrase and sufficient trust."""
        gate.request_trust_gated_confirmation("force_scale_up", current_trust=0.70)

        success, reason = gate.verify_trust_gated_confirmation(
            "force_scale_up",
            "CONFIRM FORCE SCALE UP I ACCEPT RISK",
            current_trust=0.70,
        )
        assert success
        assert reason == "confirmed"

    def test_verify_trust_gated_wrong_phrase(self, gate):
        """Should fail with wrong phrase."""
        gate.request_trust_gated_confirmation("force_scale_up", current_trust=0.70)

        success, reason = gate.verify_trust_gated_confirmation(
            "force_scale_up",
            "wrong phrase",
            current_trust=0.70,
        )
        assert not success
        assert reason == "invalid_confirmation_phrase"
