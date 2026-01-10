"""
Derived Metrics Type Definitions

Container for all computed metrics with explicit NULL handling.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DerivedMetrics:
    """
    All derived metrics computed from synchronized data.
    
    INVARIANT: Any metric can be None if insufficient data.
    INVARIANT: Strategies must check for None before using.
    
    Metrics with None values indicate:
    - Window not fully initialized
    - Data insufficient for calculation
    - External data unavailable (e.g., OI)
    """
    timestamp: float  # Reference timestamp
    
    # VWAP
    vwap: Optional[float]  # Session-anchored VWAP
    
    # ATR (Average True Range)
    atr_1m: Optional[float]   # 14-period ATR on 1-minute klines
    atr_5m: Optional[float]   # 14-period ATR on 5-minute klines
    atr_30m: Optional[float]  # 14-period ATR on 30-minute klines
    
    # Rolling taker volumes
    taker_buy_volume_10s: Optional[float]   # Last 10 seconds
    taker_sell_volume_10s: Optional[float]  # Last 10 seconds
    taker_buy_volume_30s: Optional[float]   # Last 30 seconds
    taker_sell_volume_30s: Optional[float]  # Last 30 seconds
    
    # Liquidation metrics
    liquidation_zscore: Optional[float]  # Z-score vs 60-minute baseline
    
    # Open interest
    oi_delta: Optional[float]  # Change in OI since last update
    
    def all_required_available(self) -> bool:
        """
        Check if all required metrics for trading are available.
        
        Returns:
            True if all non-None, False if any None
        
        RULE: No trades allowed if this returns False.
        """
        # OI delta is optional (may not be available), all others required
        return (
            self.vwap is not None and
            self.atr_1m is not None and
            self.atr_5m is not None and
            self.atr_30m is not None and
            self.taker_buy_volume_10s is not None and
            self.taker_sell_volume_10s is not None and
            self.taker_buy_volume_30s is not None and
            self.taker_sell_volume_30s is not None and
            self.liquidation_zscore is not None
            # Note: oi_delta is optional
        )
