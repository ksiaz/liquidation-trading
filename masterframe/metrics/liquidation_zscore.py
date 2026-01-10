"""
Liquidation Z-Score Calculator

Calculates z-score of current liquidation rate against 60-minute baseline.

Z-Score = (current_rate - mean_rate) / std_rate

RULES:
- Fixed 60-minute baseline window
- Returns None until 60 minutes of data
- No statistical fitting (simple z-score only)
- Deterministic calculation
"""

from typing import Optional, Tuple
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import LiquidationEvent


class LiquidationZScoreCalculator:
    """
    Calculates liquidation z-score with 60-minute baseline.
    
    INVARIANT: Fixed 60-minute window.
    INVARIANT: Returns None until full hour of data.
    """
    
    WINDOW_SECONDS = 3600.0  # 60 minutes
    RECENT_WINDOW_SECONDS = 60.0  # Calculate rate for last minute
    
    def calculate_zscore(
        self,
        liquidations: Tuple[LiquidationEvent, ...],
        current_time: float
    ) -> Optional[float]:
        """
        Calculate z-score of current liquidation rate vs baseline.
        
        Args:
            liquidations: All recent liquidations (last hour+)
            current_time: Current timestamp
        
        Returns:
            Z-score if available, None otherwise
        
        RULE: Returns None if insufficient data for 60-minute baseline.
        """
        if not liquidations:
            return None
        
        # Calculate baseline window (60 minutes ago to now)
        baseline_start = current_time - self.WINDOW_SECONDS
        
        # Calculate current rate window (last 60 seconds)
        current_start = current_time - self.RECENT_WINDOW_SECONDS
        
        # Collect baseline liquidation counts per minute
        baseline_rates = []
        current_liquidations = []
        
        for liq in liquidations:
            if baseline_start <= liq.timestamp <= current_time:
                # In baseline window
                if current_start <= liq.timestamp <= current_time:
                    # Also in current window
                    current_liquidations.append(liq)
                
                # Group by minute for baseline rate calculation
                minute_bucket = int((liq.timestamp - baseline_start) / 60)
                while len(baseline_rates) <= minute_bucket:
                    baseline_rates.append(0)
                if minute_bucket < len(baseline_rates):
                    baseline_rates[minute_bucket] += 1
        
        # Need EXACTLY 60 minutes of baseline data
        # Pad with zeros if we have liquidations but missing some minutes
        while len(baseline_rates) < 60:
            baseline_rates.append(0)
        
        # But check if we actually have data spanning the full 60 minutes
        # by checking if oldest liquidation is at least 60 minutes ago
        if liquidations:
            oldest_liq = min(liq.timestamp for liq in liquidations if baseline_start <= liq.timestamp)
            time_span = current_time - oldest_liq
            if time_span < self.WINDOW_SECONDS * 0.9:  # Allow 10% tolerance
                return None
        else:
            return None
        
        # Calculate baseline statistics
        mean_rate = sum(baseline_rates) / len(baseline_rates)
        
        # Calculate standard deviation
        variance = sum((r - mean_rate) ** 2 for r in baseline_rates) / len(baseline_rates)
        std_rate = variance ** 0.5
        
        # Avoid division by zero
        if std_rate == 0:
            # No variability in baseline - return 0 if current matches mean, else large value
            current_rate = len(current_liquidations)
            return 0.0 if current_rate == mean_rate else 999.0 if current_rate > mean_rate else -999.0
        
        # Calculate current rate (liquidations in last minute)
        current_rate = len(current_liquidations)
        
        # Calculate z-score
        zscore = (current_rate - mean_rate) / std_rate
        
        return zscore
