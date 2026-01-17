"""
Regime Classification Types

Defines regime states for strategy mutual exclusion.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article VII (Regime Mutual Exclusion)
- No confidence, no quality ranking, no prediction
"""

from enum import Enum, auto


class RegimeState(Enum):
    """
    Market regime classification.

    Regimes are mutually exclusive - only one can be active at a time.
    """
    SIDEWAYS_ACTIVE = auto()  # Range conditions: VWAP containment, volatility compression
    EXPANSION_ACTIVE = auto()  # Momentum conditions: VWAP escape, volatility expansion
    DISABLED = auto()  # No regime criteria met, no trading permitted


class RegimeMetrics:
    """
    Observable metrics used for regime classification.

    All values are neutral observations - no interpretation or prediction.
    """
    def __init__(
        self,
        *,
        vwap_distance: float,  # Absolute distance: abs(price - vwap)
        atr_5m: float,  # 5-minute ATR
        atr_30m: float,  # 30-minute ATR
        orderflow_imbalance: float,  # Taker buy ratio: buy / (buy + sell)
        liquidation_zscore: float  # Z-score of liquidation rate
    ):
        self.vwap_distance = vwap_distance
        self.atr_5m = atr_5m
        self.atr_30m = atr_30m
        self.orderflow_imbalance = orderflow_imbalance
        self.liquidation_zscore = liquidation_zscore

    def __repr__(self):
        return (
            f"RegimeMetrics("
            f"vwap_dist={self.vwap_distance:.2f}, "
            f"atr_5m={self.atr_5m:.2f}, "
            f"atr_30m={self.atr_30m:.2f}, "
            f"orderflow_imb={self.orderflow_imbalance:.3f}, "
            f"liq_zscore={self.liquidation_zscore:.2f})"
        )
