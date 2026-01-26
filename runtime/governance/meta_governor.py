"""
Pillar 5: Sovereign Meta-Governor.

Supreme authority over all system operations. Controls whether the system
trusts itself. Can override all lower governors.

Override Hierarchy (supreme to subordinate):
1. META-GOVERNOR (this) - supreme authority
2. Capital Governor - capital allocation
3. Alpha Decay Governor - strategy participation
4. Latency Gate - execution viability
5. Execution Engine - order submission

Trust Score Formula (MIN aggregation - weakest link):
- data_trust: Feed health, staleness, divergence
- execution_trust: Latency validity, retry storms
- alpha_trust: Decay severity mapping
- risk_trust: Circuit breakers, catastrophe state
- internal_consistency: Persistence match, reconciliation

Trust States:
- OPERATIONAL (>= 0.80): Full operation
- DEGRADED (>= 0.60): Reduced capital
- WARNING (>= 0.40): Minimal entries
- CRITICAL (>= 0.20): Exits only
- UNKNOWN_THREAT: Unknown anomalies detected
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
from enum import Enum

from .unknown_unknown_detector import UnknownThreatDetector, ThreatAssessment


class TrustState(Enum):
    """System trust states."""
    OPERATIONAL = "OPERATIONAL"    # Normal operation
    DEGRADED = "DEGRADED"          # Some concerns
    WARNING = "WARNING"            # Significant concerns
    CRITICAL = "CRITICAL"          # Major failure
    UNKNOWN_THREAT = "UNKNOWN_THREAT"  # Unrecognized condition


@dataclass(frozen=True)
class TrustSubScores:
    """Individual trust sub-scores."""
    ts_ns: int
    data_trust: float           # 0.0 to 1.0
    execution_trust: float      # 0.0 to 1.0
    alpha_trust: float          # 0.0 to 1.0
    risk_trust: float           # 0.0 to 1.0
    consistency_trust: float    # 0.0 to 1.0

    @property
    def min_score(self) -> float:
        """Compute MIN aggregation (weakest link)."""
        return min(
            self.data_trust,
            self.execution_trust,
            self.alpha_trust,
            self.risk_trust,
            self.consistency_trust,
        )


@dataclass(frozen=True)
class MetaGovernorDecision:
    """Output contract for meta governor."""
    ts_ns: int
    trust_score: float          # 0.0 to 1.0
    trust_state: TrustState
    allows_trading: bool
    allows_entries: bool
    allows_exits: bool
    capital_override: Optional[float]  # Overrides capital governor
    sub_scores: Optional[TrustSubScores]
    reason: str
    requires_manual_reset: bool = False
    threat_assessment: Optional[ThreatAssessment] = None


@dataclass
class DataTrustInputs:
    """Inputs for data trust calculation."""
    # Feed staleness (seconds since last update)
    feed_staleness_sec: float = 0.0
    max_acceptable_staleness_sec: float = 10.0

    # Timestamp drift (absolute difference from expected)
    timestamp_drift_sec: float = 0.0
    max_acceptable_drift_sec: float = 2.0

    # Spread anomalies
    spread_current_bps: float = 0.0
    spread_baseline_bps: float = 0.0

    # Depth health (0 = no depth, 1 = normal)
    depth_health_ratio: float = 1.0

    # Price divergence (between feeds)
    price_divergence_pct: float = 0.0
    max_acceptable_divergence_pct: float = 0.5


@dataclass
class ExecutionTrustInputs:
    """Inputs for execution trust calculation."""
    # Latency validity
    latency_p95_ms: float = 0.0
    max_acceptable_latency_ms: float = 200.0

    # Retry storm detection
    retry_rate_pct: float = 0.0
    max_acceptable_retry_rate: float = 0.10  # 10%

    # Cancel storm detection
    cancel_rate_pct: float = 0.0
    max_acceptable_cancel_rate: float = 0.20  # 20%

    # Fill mismatches
    fill_mismatch_rate_pct: float = 0.0
    max_acceptable_mismatch_rate: float = 0.05  # 5%


@dataclass
class AlphaTrustInputs:
    """Inputs for alpha trust calculation."""
    # DecaySeverity mapping (from AlphaDecayGovernor)
    # NONE=1.0, LOW=0.75, MEDIUM=0.5, HIGH=0.25, CRITICAL=0.0
    decay_severity_score: float = 1.0

    # Strategy disagreement (fraction of strategies disabled)
    strategies_disabled_pct: float = 0.0

    # Edge consistency (across time windows)
    edge_consistency_score: float = 1.0


@dataclass
class RiskTrustInputs:
    """Inputs for risk trust calculation."""
    # Circuit breaker status (0 = tripped, 1 = normal)
    circuit_breaker_status: float = 1.0

    # Catastrophe state (0 = catastrophe, 1 = normal)
    catastrophe_status: float = 1.0

    # Kill switch status (0 = triggered, 1 = normal)
    kill_switch_status: float = 1.0


@dataclass
class ConsistencyTrustInputs:
    """Inputs for internal consistency calculation."""
    # Persistence match (positions match DB)
    persistence_match_score: float = 1.0

    # Restart anomalies (0 = anomalies, 1 = clean)
    restart_health_score: float = 1.0

    # Orphan orders (0 = many orphans, 1 = none)
    orphan_order_score: float = 1.0

    # Reconciliation status (0 = mismatches, 1 = matched)
    reconciliation_score: float = 1.0


@dataclass
class MetaGovernorThresholds:
    """Configurable thresholds for meta governor."""
    # Trust state thresholds
    operational_threshold: float = 0.80
    degraded_threshold: float = 0.60
    warning_threshold: float = 0.40
    critical_threshold: float = 0.20

    # Capital overrides by state
    degraded_capital_override: float = 0.75
    warning_capital_override: float = 0.50
    critical_capital_override: float = 0.10
    unknown_threat_capital_override: float = 0.10


class TrustScoreCalculator:
    """Calculates trust sub-scores."""

    def compute_data_trust(self, inputs: DataTrustInputs) -> float:
        """Compute data trust score."""
        scores = []

        # Staleness score
        staleness_ratio = inputs.feed_staleness_sec / inputs.max_acceptable_staleness_sec
        staleness_score = max(0.0, 1.0 - staleness_ratio)
        scores.append(staleness_score)

        # Drift score
        drift_ratio = inputs.timestamp_drift_sec / inputs.max_acceptable_drift_sec
        drift_score = max(0.0, 1.0 - drift_ratio)
        scores.append(drift_score)

        # Spread score
        if inputs.spread_baseline_bps > 0:
            spread_expansion = inputs.spread_current_bps / inputs.spread_baseline_bps
            spread_score = max(0.0, min(1.0, 2.0 - spread_expansion))  # 1x = 1.0, 2x = 0.0
        else:
            spread_score = 1.0
        scores.append(spread_score)

        # Depth health
        scores.append(inputs.depth_health_ratio)

        # Divergence score
        divergence_ratio = inputs.price_divergence_pct / inputs.max_acceptable_divergence_pct
        divergence_score = max(0.0, 1.0 - divergence_ratio)
        scores.append(divergence_score)

        # Return minimum (weakest link)
        return min(scores) if scores else 0.0

    def compute_execution_trust(self, inputs: ExecutionTrustInputs) -> float:
        """Compute execution trust score."""
        scores = []

        # Latency score
        latency_ratio = inputs.latency_p95_ms / inputs.max_acceptable_latency_ms
        latency_score = max(0.0, 1.0 - latency_ratio)
        scores.append(latency_score)

        # Retry score
        retry_ratio = inputs.retry_rate_pct / inputs.max_acceptable_retry_rate
        retry_score = max(0.0, 1.0 - retry_ratio)
        scores.append(retry_score)

        # Cancel score
        cancel_ratio = inputs.cancel_rate_pct / inputs.max_acceptable_cancel_rate
        cancel_score = max(0.0, 1.0 - cancel_ratio)
        scores.append(cancel_score)

        # Mismatch score
        mismatch_ratio = inputs.fill_mismatch_rate_pct / inputs.max_acceptable_mismatch_rate
        mismatch_score = max(0.0, 1.0 - mismatch_ratio)
        scores.append(mismatch_score)

        return min(scores) if scores else 0.0

    def compute_alpha_trust(self, inputs: AlphaTrustInputs) -> float:
        """Compute alpha trust score."""
        scores = [
            inputs.decay_severity_score,
            1.0 - inputs.strategies_disabled_pct,
            inputs.edge_consistency_score,
        ]
        return min(scores)

    def compute_risk_trust(self, inputs: RiskTrustInputs) -> float:
        """Compute risk trust score."""
        scores = [
            inputs.circuit_breaker_status,
            inputs.catastrophe_status,
            inputs.kill_switch_status,
        ]
        return min(scores)

    def compute_consistency_trust(self, inputs: ConsistencyTrustInputs) -> float:
        """Compute internal consistency trust score."""
        scores = [
            inputs.persistence_match_score,
            inputs.restart_health_score,
            inputs.orphan_order_score,
            inputs.reconciliation_score,
        ]
        return min(scores)


class SovereignMetaGovernor:
    """
    Supreme authority over all system operations.

    Controls whether the system trusts itself.
    Can override all lower governors.

    State Machine:
    - OPERATIONAL: trust >= 0.80, full operation
    - DEGRADED: trust >= 0.60, reduced capital (75%)
    - WARNING: trust >= 0.40, minimal entries, reduced capital (50%)
    - CRITICAL: trust >= 0.20, exits only, minimal capital (10%)
    - UNKNOWN_THREAT: anomalies detected, exits only, minimal capital (10%)

    Actions by State:
    | State           | Trading | Entries | Exits | Capital Override |
    |-----------------|---------|---------|-------|------------------|
    | OPERATIONAL     | Yes     | Yes     | Yes   | None             |
    | DEGRADED        | Yes     | Yes     | Yes   | 0.75             |
    | WARNING         | Yes     | Reduced | Yes   | 0.50             |
    | CRITICAL        | No      | No      | Yes   | 0.10             |
    | UNKNOWN_THREAT  | No      | No      | Yes   | 0.10             |
    """

    def __init__(
        self,
        threat_detector: Optional[UnknownThreatDetector] = None,
        thresholds: Optional[MetaGovernorThresholds] = None,
    ):
        self._threat_detector = threat_detector or UnknownThreatDetector()
        self._thresholds = thresholds or MetaGovernorThresholds()
        self._trust_calculator = TrustScoreCalculator()

        # Current state
        self._trust_state: TrustState = TrustState.OPERATIONAL
        self._trust_score: float = 1.0
        self._requires_manual_reset: bool = False

    def evaluate(
        self,
        data_inputs: Optional[DataTrustInputs] = None,
        execution_inputs: Optional[ExecutionTrustInputs] = None,
        alpha_inputs: Optional[AlphaTrustInputs] = None,
        risk_inputs: Optional[RiskTrustInputs] = None,
        consistency_inputs: Optional[ConsistencyTrustInputs] = None,
        metric_observations: Optional[dict] = None,
        now_ns: Optional[int] = None,
    ) -> MetaGovernorDecision:
        """
        Evaluate system trust and return decision.

        Args:
            data_inputs: Data feed health inputs
            execution_inputs: Execution health inputs
            alpha_inputs: Alpha/strategy health inputs
            risk_inputs: Risk subsystem inputs
            consistency_inputs: Internal consistency inputs
            metric_observations: Raw metrics for unknown threat detection
            now_ns: Current timestamp

        Returns:
            Meta governor decision
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        t = self._thresholds

        # Check if manual reset is required
        if self._requires_manual_reset:
            return self._build_manual_reset_required_decision(now_ns)

        # Step 1: Check for unknown threats
        threat_assessment = None
        if metric_observations:
            threat_assessment = self._threat_detector.evaluate(metric_observations, now_ns)
            if threat_assessment.has_unknown_threats:
                return self._build_unknown_threat_decision(threat_assessment, now_ns)

        # Step 2: Compute trust sub-scores
        sub_scores = self._compute_sub_scores(
            data_inputs,
            execution_inputs,
            alpha_inputs,
            risk_inputs,
            consistency_inputs,
            now_ns,
        )

        # Step 3: Compute trust score (MIN aggregation)
        trust_score = sub_scores.min_score
        self._trust_score = trust_score

        # Step 4: Determine trust state
        trust_state = self._classify_trust_state(trust_score)
        self._trust_state = trust_state

        # Step 5: Determine actions and overrides
        allows_trading, allows_entries, allows_exits = self._get_allowed_actions(trust_state)
        capital_override = self._get_capital_override(trust_state)

        # Step 6: Check if critical requires manual reset
        if trust_state == TrustState.CRITICAL:
            self._requires_manual_reset = True

        return MetaGovernorDecision(
            ts_ns=now_ns,
            trust_score=trust_score,
            trust_state=trust_state,
            allows_trading=allows_trading,
            allows_entries=allows_entries,
            allows_exits=allows_exits,
            capital_override=capital_override,
            sub_scores=sub_scores,
            reason=self._build_reason(trust_state, sub_scores),
            requires_manual_reset=self._requires_manual_reset,
            threat_assessment=threat_assessment,
        )

    def _compute_sub_scores(
        self,
        data_inputs: Optional[DataTrustInputs],
        execution_inputs: Optional[ExecutionTrustInputs],
        alpha_inputs: Optional[AlphaTrustInputs],
        risk_inputs: Optional[RiskTrustInputs],
        consistency_inputs: Optional[ConsistencyTrustInputs],
        now_ns: int,
    ) -> TrustSubScores:
        """Compute all trust sub-scores."""
        calc = self._trust_calculator

        # Default to full trust if inputs not provided
        data_trust = calc.compute_data_trust(data_inputs) if data_inputs else 1.0
        execution_trust = calc.compute_execution_trust(execution_inputs) if execution_inputs else 1.0
        alpha_trust = calc.compute_alpha_trust(alpha_inputs) if alpha_inputs else 1.0
        risk_trust = calc.compute_risk_trust(risk_inputs) if risk_inputs else 1.0
        consistency_trust = calc.compute_consistency_trust(consistency_inputs) if consistency_inputs else 1.0

        return TrustSubScores(
            ts_ns=now_ns,
            data_trust=data_trust,
            execution_trust=execution_trust,
            alpha_trust=alpha_trust,
            risk_trust=risk_trust,
            consistency_trust=consistency_trust,
        )

    def _classify_trust_state(self, trust_score: float) -> TrustState:
        """Classify trust score into state."""
        t = self._thresholds

        if trust_score >= t.operational_threshold:
            return TrustState.OPERATIONAL
        elif trust_score >= t.degraded_threshold:
            return TrustState.DEGRADED
        elif trust_score >= t.warning_threshold:
            return TrustState.WARNING
        else:
            return TrustState.CRITICAL

    def _get_allowed_actions(self, state: TrustState) -> Tuple[bool, bool, bool]:
        """
        Get allowed actions for state.

        Returns:
            Tuple of (allows_trading, allows_entries, allows_exits)
        """
        actions = {
            TrustState.OPERATIONAL: (True, True, True),
            TrustState.DEGRADED: (True, True, True),
            TrustState.WARNING: (True, True, True),  # Entries reduced via capital override
            TrustState.CRITICAL: (False, False, True),  # Exits only
            TrustState.UNKNOWN_THREAT: (False, False, True),  # Exits only
        }
        return actions.get(state, (False, False, True))

    def _get_capital_override(self, state: TrustState) -> Optional[float]:
        """Get capital override for state."""
        t = self._thresholds

        overrides = {
            TrustState.OPERATIONAL: None,
            TrustState.DEGRADED: t.degraded_capital_override,
            TrustState.WARNING: t.warning_capital_override,
            TrustState.CRITICAL: t.critical_capital_override,
            TrustState.UNKNOWN_THREAT: t.unknown_threat_capital_override,
        }
        return overrides.get(state)

    def _build_reason(self, state: TrustState, sub_scores: TrustSubScores) -> str:
        """Build reason string."""
        min_score = min(
            sub_scores.data_trust,
            sub_scores.execution_trust,
            sub_scores.alpha_trust,
            sub_scores.risk_trust,
            sub_scores.consistency_trust,
        )

        # Find which score is the bottleneck
        bottleneck = "unknown"
        if sub_scores.data_trust == min_score:
            bottleneck = "data_trust"
        elif sub_scores.execution_trust == min_score:
            bottleneck = "execution_trust"
        elif sub_scores.alpha_trust == min_score:
            bottleneck = "alpha_trust"
        elif sub_scores.risk_trust == min_score:
            bottleneck = "risk_trust"
        elif sub_scores.consistency_trust == min_score:
            bottleneck = "consistency_trust"

        return f"trust_state={state.value}_bottleneck={bottleneck}_score={min_score:.2f}"

    def _build_unknown_threat_decision(
        self,
        threat_assessment: ThreatAssessment,
        now_ns: int,
    ) -> MetaGovernorDecision:
        """Build decision for unknown threat state."""
        t = self._thresholds

        self._trust_state = TrustState.UNKNOWN_THREAT
        self._requires_manual_reset = True

        return MetaGovernorDecision(
            ts_ns=now_ns,
            trust_score=0.0,
            trust_state=TrustState.UNKNOWN_THREAT,
            allows_trading=False,
            allows_entries=False,
            allows_exits=True,
            capital_override=t.unknown_threat_capital_override,
            sub_scores=None,
            reason=f"unknown_threat_detected_count={threat_assessment.threat_count}_max_z={threat_assessment.max_z_score:.1f}",
            requires_manual_reset=True,
            threat_assessment=threat_assessment,
        )

    def _build_manual_reset_required_decision(self, now_ns: int) -> MetaGovernorDecision:
        """Build decision when manual reset is required."""
        t = self._thresholds

        return MetaGovernorDecision(
            ts_ns=now_ns,
            trust_score=0.0,
            trust_state=self._trust_state,
            allows_trading=False,
            allows_entries=False,
            allows_exits=True,
            capital_override=t.critical_capital_override,
            sub_scores=None,
            reason="manual_reset_required",
            requires_manual_reset=True,
        )

    def manual_reset(
        self,
        confirmation_phrase: str,
        now_ns: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Manually reset the meta governor after critical state.

        Args:
            confirmation_phrase: Must be "CONFIRM RESET META GOVERNOR"
            now_ns: Current timestamp

        Returns:
            Tuple of (success, message)
        """
        expected_phrase = "CONFIRM RESET META GOVERNOR"

        if confirmation_phrase != expected_phrase:
            return False, f"Invalid confirmation phrase. Expected: {expected_phrase}"

        self._requires_manual_reset = False
        self._trust_state = TrustState.DEGRADED  # Don't go straight to OPERATIONAL
        self._trust_score = 0.65  # Start in DEGRADED

        return True, "Meta governor reset to DEGRADED state"

    def restore_state(
        self,
        trust_state: str,
        trust_score: float,
        requires_manual_reset: bool,
    ) -> None:
        """
        Restore meta governor state from persistence.

        Args:
            trust_state: Trust state string
            trust_score: Trust score
            requires_manual_reset: Whether manual reset is required
        """
        self._trust_state = TrustState(trust_state)
        self._trust_score = trust_score
        self._requires_manual_reset = requires_manual_reset

    @property
    def trust_state(self) -> TrustState:
        """Get current trust state."""
        return self._trust_state

    @property
    def trust_score(self) -> float:
        """Get current trust score."""
        return self._trust_score

    @property
    def requires_manual_reset(self) -> bool:
        """Check if manual reset is required."""
        return self._requires_manual_reset

    def allows_trading(self) -> bool:
        """Check if trading is currently allowed."""
        return self._trust_state in (TrustState.OPERATIONAL, TrustState.DEGRADED, TrustState.WARNING)

    def allows_entries(self) -> bool:
        """Check if new entries are currently allowed."""
        return self._trust_state in (TrustState.OPERATIONAL, TrustState.DEGRADED, TrustState.WARNING)

    def allows_exits(self) -> bool:
        """Check if exits are currently allowed (always true)."""
        return True

    def get_capital_override(self) -> Optional[float]:
        """Get current capital override (if any)."""
        return self._get_capital_override(self._trust_state)
