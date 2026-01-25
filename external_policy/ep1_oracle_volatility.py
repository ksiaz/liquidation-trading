"""
EP-1 Strategy: Oracle Volatility

Stub module - not yet implemented.

Authority:
- Tier A Structural Primitives (when available)
- M5 Whitelist
- M6 Predicate Framework (Frozen)

Purpose:
Evaluates volatility conditions from oracle data.
Emits mandates based on volatility thresholds.

CRITICAL: This module makes no decisions. It only proposes.

Status: STUB - Awaiting implementation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OracleVolatilityConfig:
    """Configuration for oracle volatility thresholds.

    NOT predictions, NOT confidence scores - just threshold values.
    """
    # Placeholder thresholds
    min_volatility: float = 0.0
    max_volatility: float = 1.0


# Default config
DEFAULT_ORACLE_VOLATILITY_CONFIG = OracleVolatilityConfig()


@dataclass(frozen=True)
class OracleVolatilityProposal:
    """Proposal from oracle volatility evaluation.

    Immutable proposal - no decisions made.
    """
    timestamp: float
    volatility_observed: Optional[float] = None
    threshold_exceeded: bool = False


class EP1_OracleVolatility:
    """Oracle volatility strategy stub.

    NOT IMPLEMENTED - placeholder for schema compliance.
    """

    def __init__(self, config: Optional[OracleVolatilityConfig] = None):
        """Initialize with optional config."""
        self.config = config or DEFAULT_ORACLE_VOLATILITY_CONFIG

    def evaluate(self, timestamp: float) -> Optional[OracleVolatilityProposal]:
        """Evaluate oracle volatility conditions.

        Args:
            timestamp: Current timestamp

        Returns:
            None - not implemented
        """
        # STUB: Not implemented
        return None
