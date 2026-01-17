"""Validation module for cascade sniper data integrity and manipulation detection."""

from .data_validator import DataValidator, ValidationResult, DataSource
from .manipulation_detector import ManipulationDetector, ManipulationType, ManipulationAlert
from .stop_hunt_detector import (
    StopHuntDetector,
    StopHuntEvent,
    StopHuntPhase,
    HuntDirection,
    LiquidityCluster,
    LiquidityType
)
from .cross_validator import (
    CrossValidator,
    PositionSnapshot,
    LiquidationEvent,
    CorrelationResult,
    CrossValidationStats
)
from .entry_quality import (
    EntryQualityScorer,
    EntryScore,
    EntryQuality,
    EntryMode,
    LiquidationSide,
    LiquidationContext
)

__all__ = [
    # Data validation
    "DataValidator",
    "ValidationResult",
    "DataSource",
    # Manipulation detection
    "ManipulationDetector",
    "ManipulationType",
    "ManipulationAlert",
    # Stop hunt detection
    "StopHuntDetector",
    "StopHuntEvent",
    "StopHuntPhase",
    "HuntDirection",
    "LiquidityCluster",
    "LiquidityType",
    # Cross-validation
    "CrossValidator",
    "PositionSnapshot",
    "LiquidationEvent",
    "CorrelationResult",
    "CrossValidationStats",
    # Entry quality scoring
    "EntryQualityScorer",
    "EntryScore",
    "EntryQuality",
    "EntryMode",
    "LiquidationSide",
    "LiquidationContext",
]
