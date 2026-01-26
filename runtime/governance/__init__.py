"""
Governance module for human oversight, capital control, and system trust.

Pillar 4: Sovereign Capital Governor
Pillar 5: Sovereign Meta-Governor
"""

from .operator_gate import OperatorGate, OperatorConfirmation, DangerousAction

from .confidence_engine import (
    ConfidenceEngine,
    ConfidenceSubScores,
    ConfidenceThresholds,
    EdgeStabilityInputs,
    MarketStabilityInputs,
    ExecutionQualityInputs,
    ImpactContainmentInputs,
    DrawdownDisciplineInputs,
    StrategyDiversificationInputs,
)

from .quarantine_controller import (
    QuarantineController,
    QuarantineState,
    QuarantineInputs,
    QuarantineTrigger,
    QuarantineThresholds,
)

from .capital_governor import (
    SovereignCapitalGovernor,
    CapitalGovernorDecision,
    CapitalGovernorInputs,
    CapitalGovernorThresholds,
    ScalingState,
    FreezeReason,
)

from .unknown_unknown_detector import (
    UnknownThreatDetector,
    UnknownThreatSignal,
    ThreatAssessment,
    UnknownThreatThresholds,
)

from .meta_governor import (
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
)

__all__ = [
    # Operator Gate
    'OperatorGate',
    'OperatorConfirmation',
    'DangerousAction',

    # Confidence Engine
    'ConfidenceEngine',
    'ConfidenceSubScores',
    'ConfidenceThresholds',
    'EdgeStabilityInputs',
    'MarketStabilityInputs',
    'ExecutionQualityInputs',
    'ImpactContainmentInputs',
    'DrawdownDisciplineInputs',
    'StrategyDiversificationInputs',

    # Quarantine Controller
    'QuarantineController',
    'QuarantineState',
    'QuarantineInputs',
    'QuarantineTrigger',
    'QuarantineThresholds',

    # Capital Governor
    'SovereignCapitalGovernor',
    'CapitalGovernorDecision',
    'CapitalGovernorInputs',
    'CapitalGovernorThresholds',
    'ScalingState',
    'FreezeReason',

    # Unknown Threat Detector
    'UnknownThreatDetector',
    'UnknownThreatSignal',
    'ThreatAssessment',
    'UnknownThreatThresholds',

    # Meta Governor
    'SovereignMetaGovernor',
    'MetaGovernorDecision',
    'TrustState',
    'TrustSubScores',
    'MetaGovernorThresholds',
    'DataTrustInputs',
    'ExecutionTrustInputs',
    'AlphaTrustInputs',
    'RiskTrustInputs',
    'ConsistencyTrustInputs',
]
