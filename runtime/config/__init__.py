"""
HLP23: Configuration Package.

Provides:
- Threshold configurations with validation status
- Threshold documentation with provenance tracking
- Conservative defaults for all strategy parameters

All thresholds are HYPOTHESES until validated via:
- Grid search optimization
- Walk-forward validation
- Out-of-sample testing
"""

from .thresholds import (
    ThresholdConfig,
    OIThresholds,
    FundingThresholds,
    DepthThresholds,
    ConfidenceThresholds,
    TimingThresholds,
)
from .threshold_docs import (
    ThresholdDocumentation,
    ThresholdRegistry,
    DiscoveryMethod,
    ValidationStatus,
)

__all__ = [
    # Thresholds
    'ThresholdConfig',
    'OIThresholds',
    'FundingThresholds',
    'DepthThresholds',
    'ConfidenceThresholds',
    'TimingThresholds',
    # Documentation
    'ThresholdDocumentation',
    'ThresholdRegistry',
    'DiscoveryMethod',
    'ValidationStatus',
]
