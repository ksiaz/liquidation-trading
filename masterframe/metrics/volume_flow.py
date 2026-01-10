"""
Volume Flow Calculator

Calculates rolling taker buy/sell volumes for specified time windows.

RULES:
- Fixed time windows (10s, 30s)
- Returns None until sufficient data
- No smoothing
- Deterministic calculation
"""

from typing import Optional, Tuple
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import AggressiveTrade


class VolumeFlowCalculator:
    """
    Calculates rolling taker buy/sell volumes.
    
    INVARIANT: Fixed window sizes (no adaptive).
    INVARIANT: Returns None until data available.
    """
    
    def calculate_volumes(
        self,
        trades: Tuple[AggressiveTrade, ...],
        window_seconds: float,
        current_time: float
    ) -> Optional[Tuple[float, float]]:
        """
        Calculate taker buy and sell volumes within time window.
        
        Args:
            trades: All recent trades
            window_seconds: Size of time window (10 or 30)
            current_time: Current timestamp
        
        Returns:
            (buy_volume, sell_volume) if data available, None otherwise
        
        RULE: Only counts trades within [current_time - window_seconds, current_time].
        """
        if not trades:
            return None
        
        # Calculate window boundaries
        window_start = current_time - window_seconds
        
        buy_volume = 0.0
        sell_volume = 0.0
        has_trades_in_window = False
        
        for trade in trades:
            # Only consider trades within window
            if window_start <= trade.timestamp <= current_time:
                has_trades_in_window = True
                
                if trade.is_buyer_aggressor:
                    buy_volume += trade.quantity
                else:
                    sell_volume += trade.quantity
        
        # Return None if no trades in window
        if not has_trades_in_window:
            return None
        
        return (buy_volume, sell_volume)
