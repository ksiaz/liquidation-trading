"""
Cascade Detection Module

Stub module for cascade-related types.
OrganicFlowDetector functionality disabled pending node adapter redesign.
See docs/NODE_ADAPTER_REDESIGN.md for architecture plan.
"""

from .types import CascadeDirection, OrganicFlowDetector, LiquidationEvent, AbsorptionSignal
from .capitulation import CapitulationTracker, CapitulationMetrics

__all__ = [
    'CascadeDirection', 'OrganicFlowDetector', 'LiquidationEvent', 'AbsorptionSignal',
    'CapitulationTracker', 'CapitulationMetrics',
]
