"""
Regime Classifier Type Definitions

Data structures for regime state and transitions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RegimeType(Enum):
    """
    Trading regime types.
    
    SIDEWAYS: Low volatility, range-bound → enables SLBRS
    EXPANSION: High volatility, trending → enables EFFCS
    DISABLED: Neither qualifies or insufficient data → no strategies
    """
    SIDEWAYS = "SIDEWAYS"
    EXPANSION = "EXPANSION"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class RegimeState:
    """
    Current regime state snapshot.
    
    INVARIANT: Immutable snapshot of regime at a point in time.
    INVARIANT: Contains condition values for logging/debugging.
    """
    regime: RegimeType
    timestamp: float
    
    # Metric values (for logging/debugging)
    price_vwap_distance: Optional[float]  # abs(price - VWAP)
    atr_ratio: Optional[float]            # ATR(5m) / ATR(30m)
    volume_imbalance: Optional[float]     # abs(buy - sell) / total
    liquidation_zscore: Optional[float]   # Z-score
    oi_delta: Optional[float]             # OI delta
    
    # Condition evaluation results
    condition_1_met: bool
    condition_2_met: bool
    condition_3_met: bool
    condition_4_met: bool
    
    def all_conditions_met(self) -> bool:
        """Check if all 4 conditions are met."""
        return (
            self.condition_1_met and
            self.condition_2_met and
            self.condition_3_met and
            self.condition_4_met
        )


@dataclass
class RegimeTransition:
    """
    Logged regime transition.
    
    Mutable - used for logging/analysis.
    
    INVARIANT: Records why regime changed.
    """
    timestamp: float
    from_regime: RegimeType
    to_regime: RegimeType
    reason: str  # Human-readable reason for transition
    
    def __str__(self) -> str:
        """String representation of transition."""
        return (
            f"[{self.timestamp}] {self.from_regime.value} → {self.to_regime.value}: "
            f"{self.reason}"
        )
