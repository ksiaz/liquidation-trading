"""
EP-3 Strategy: Deviation Bounds

Stub module - not yet implemented.

Authority:
- Tier A Structural Primitives (when available)
- M5 Whitelist
- M6 Predicate Framework (Frozen)

Purpose:
Evaluates deviation from expected bounds.
Emits mandates when bounds are exceeded.

CRITICAL: This module makes no decisions. It only proposes.

Status: STUB - Awaiting implementation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DeviationBoundsConfig:
    """Configuration for deviation bounds thresholds.

    NOT predictions, NOT confidence scores - just threshold values.
    """
    # Placeholder thresholds
    max_deviation_bps: float = 100.0  # 1%
    min_samples: int = 10


# Default config
DEFAULT_DEVIATION_BOUNDS_CONFIG = DeviationBoundsConfig()


@dataclass(frozen=True)
class DeviationBoundsProposal:
    """Proposal from deviation bounds evaluation.

    Immutable proposal - no decisions made.
    """
    timestamp: float
    deviation_observed: Optional[float] = None
    bounds_exceeded: bool = False


class EP3_StrategyDeviationBounds:
    """Deviation bounds strategy stub.

    NOT IMPLEMENTED - placeholder for schema compliance.
    """

    def __init__(self, config: Optional[DeviationBoundsConfig] = None):
        """Initialize with optional config."""
        self.config = config or DEFAULT_DEVIATION_BOUNDS_CONFIG

    def evaluate(self, timestamp: float) -> Optional[DeviationBoundsProposal]:
        """Evaluate deviation bounds conditions.

        Args:
            timestamp: Current timestamp

        Returns:
            None - not implemented
        """
        # STUB: Not implemented
        return None
