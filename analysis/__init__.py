"""
HLP25 Validation Pipeline + HLP23 Threshold Discovery.

Analysis tools for:
- Validating cascade mechanics hypotheses using HLP24 raw data (HLP25)
- Discovering and validating thresholds from arbitrary to evidence-based (HLP23)

Following principle: "Store raw, label later" - this module labels.
"""

from .cascade_labeler import CascadeLabeler, LabeledCascade, WaveLabel
from .wave_detector import WaveDetector, DetectedWave, WaveStructure
from .threshold_discovery import (
    DiscoveryMethod,
    ThresholdCandidate,
    OptimizationResult,
    ROCPoint,
    GridSearchConfig,
    GridSearchOptimizer,
    ROCAnalyzer,
    SensitivityAnalyzer,
    OutOfSampleValidator,
    WalkForwardOptimizer,
    get_conservative_defaults,
    get_phased_thresholds,
)
from .threshold_store import (
    ThresholdStatus,
    ThresholdConfig,
    ThresholdSet,
    ThresholdStore,
    create_threshold_config,
    create_conservative_threshold_set,
)

__all__ = [
    # HLP25 Cascade Labeling
    'CascadeLabeler', 'LabeledCascade', 'WaveLabel',
    'WaveDetector', 'DetectedWave', 'WaveStructure',
    # HLP23 Threshold Discovery
    'DiscoveryMethod', 'ThresholdCandidate', 'OptimizationResult',
    'ROCPoint', 'GridSearchConfig', 'GridSearchOptimizer',
    'ROCAnalyzer', 'SensitivityAnalyzer', 'OutOfSampleValidator',
    'WalkForwardOptimizer', 'get_conservative_defaults', 'get_phased_thresholds',
    # HLP23 Threshold Store
    'ThresholdStatus', 'ThresholdConfig', 'ThresholdSet',
    'ThresholdStore', 'create_threshold_config', 'create_conservative_threshold_set',
]
