"""
M3 Temporal - Schema Compliance Re-export.

The actual M3 temporal logic is in observation/internal/m3_temporal.py.
This module provides schema-compliant import path per SYSTEM_MAP_SCHEMA.yaml.

Authority: SYSTEM_MAP_SCHEMA.yaml declares memory/m3_temporal.py
"""

# Re-export from actual implementation
from observation.internal.m3_temporal import (
    M3TemporalEngine,
    BaselineCalculator,
    TradeWindow,
    PromotedEventInternal,
)

__all__ = [
    "M3TemporalEngine",
    "BaselineCalculator",
    "TradeWindow",
    "PromotedEventInternal",
]
