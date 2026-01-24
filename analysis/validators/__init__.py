"""
HLP25 Hypothesis Validators.

Each validator tests a specific hypothesis from HLP25 against labeled cascade data.
Returns factual results about whether the hypothesis holds.
"""

from .base import HypothesisValidator, ValidationResult
from .wave_structure import WaveStructureValidator
from .absorption import AbsorptionValidator
from .oi_concentration import OIConcentrationValidator
from .cross_asset import CrossAssetValidator

__all__ = [
    'HypothesisValidator',
    'ValidationResult',
    'WaveStructureValidator',
    'AbsorptionValidator',
    'OIConcentrationValidator',
    'CrossAssetValidator'
]
