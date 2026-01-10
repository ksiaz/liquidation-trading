"""
Metrics Engine - Orchestrates All Metric Calculations

Computes all derived metrics from synchronized data snapshot.

RULES:
- Returns DerivedMetrics with NULLs for unavailable metrics
- No trades allowed if required metrics are NULL
- Deterministic calculations
- No lookahead bias
"""

from typing import Optional, Tuple
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import SynchronizedData
from .types import DerivedMetrics
from .vwap import VWAPCalculator
from .atr import ATRCalculator
from .volume_flow import VolumeFlowCalculator
from .liquidation_zscore import LiquidationZScoreCalculator
from .oi_delta import OITracker
from .resample import resample_klines_to_30m


class MetricsEngine:
    """
    Computes all derived metrics from synchronized data.
    
    INVARIANT: Always returns DerivedMetrics (with NULLs if needed).
    INVARIANT: Individual calculators handle their own NULL logic.
    """
    
    def __init__(self):
        """Initialize all metric calculators."""
        # VWAP
        self.vwap_calc = VWAPCalculator()
        
        # ATR for different intervals
        self.atr_1m = ATRCalculator('1m')
        self.atr_5m = ATRCalculator('5m')
        self.atr_30m = ATRCalculator('30m')
        
        # Volume flow
        self.volume_calc = VolumeFlowCalculator()
        
        # Liquidation z-score
        self.liq_zscore_calc = LiquidationZScoreCalculator()
        
        # Open interest
        self.oi_tracker = OITracker()
    
    def compute_metrics(
        self,
        snapshot: SynchronizedData,
        klines_1m: Optional[Tuple],  # All 1m klines from synchronizer
        klines_5m: Optional[Tuple],  # All 5m klines from synchronizer
        current_time: float,
        current_oi: Optional[float] = None
    ) -> DerivedMetrics:
        """
        Compute all metrics from synchronized snapshot.
        
        Args:
            snapshot: Time-aligned data snapshot
            klines_1m: All 1m klines (for ATR calculation)
            klines_5m: All 5m klines (for ATR calculation)
            current_time: Current timestamp
            current_oi: Current open interest (optional)
        
        Returns:
            DerivedMetrics with NULL for unavailable metrics
        
        RULE: Each metric calculator returns None if data insufficient.
        """
        # Update VWAP
        self.vwap_calc.update(snapshot.trades, current_time)
        vwap = self.vwap_calc.get_vwap()
        
        # Update ATR with all klines
        if klines_1m:
            self.atr_1m.update(klines_1m)
        atr_1m_val = self.atr_1m.get_atr()
        
        if klines_5m:
            self.atr_5m.update(klines_5m)
        atr_5m_val = self.atr_5m.get_atr()
        
        # For ATR 30m, resample 5m klines to 30m
        atr_30m_val = None
        if klines_5m and len(klines_5m) >= 6:
            klines_30m = resample_klines_to_30m(klines_5m)
            if klines_30m:
                self.atr_30m.update(klines_30m)
                atr_30m_val = self.atr_30m.get_atr()
        
        # Calculate volume flows
        vol_10s = self.volume_calc.calculate_volumes(snapshot.trades, 10.0, current_time)
        vol_30s = self.volume_calc.calculate_volumes(snapshot.trades, 30.0, current_time)
        
        buy_vol_10s = vol_10s[0] if vol_10s else None
        sell_vol_10s = vol_10s[1] if vol_10s else None
        buy_vol_30s = vol_30s[0] if vol_30s else None
        sell_vol_30s = vol_30s[1] if vol_30s else None
        
        # Calculate liquidation z-score
        liq_zscore = self.liq_zscore_calc.calculate_zscore(snapshot.liquidations, current_time)
        
        # Update OI tracker
        self.oi_tracker.update(current_oi)
        oi_delta = self.oi_tracker.get_delta()
        
        # Return metrics
        return DerivedMetrics(
            timestamp=current_time,
            vwap=vwap,
            atr_1m=atr_1m_val,
            atr_5m=atr_5m_val,
            atr_30m=atr_30m_val,  # TODO: Implement 30m kline resampling
            taker_buy_volume_10s=buy_vol_10s,
            taker_sell_volume_10s=sell_vol_10s,
            taker_buy_volume_30s=buy_vol_30s,
            taker_sell_volume_30s=sell_vol_30s,
            liquidation_zscore=liq_zscore,
            oi_delta=oi_delta
        )
    
    def reset_all(self) -> None:
        """
        Reset all metric calculators.
        
        Used for testing or manual resets.
        """
        self.vwap_calc.reset()
        self.atr_1m.reset()
        self.atr_5m.reset()
        self.atr_30m.reset()
        self.oi_tracker.reset()
