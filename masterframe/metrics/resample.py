"""
Helper function to resample 5m klines to 30m klines
"""
from typing import Optional, Tuple, List
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import Kline


def resample_klines_to_30m(klines_5m: Tuple[Kline, ...]) -> Optional[Tuple[Kline, ...]]:
    """
    Resample 5-minute klines to 30-minute klines.
    
    Args:
        klines_5m: Tuple of 5-minute klines
    
    Returns:
        Tuple of 30-minute klines, or None if insufficient data
    
    RULE: 6 x 5m klines = 1 x 30m kline.
    RULE: Groups klines by 30-minute periods.
    """
    if not klines_5m or len(klines_5m) < 6:
        return None
    
    klines_30m: List[Kline] = []
    
    # Group 5m klines into 30m periods
    # Assuming klines are in chronological order
    i = 0
    while i + 5 < len(klines_5m):
        # Take 6 consecutive 5m klines
        group = klines_5m[i:i+6]
        
        # Combine into single 30m kline
        kline_30m = Kline(
            timestamp=group[0].timestamp,  # Opening time of first 5m candle
            open=group[0].open,             # Open of first candle
            high=max(k.high for k in group),  # Highest high
            low=min(k.low for k in group),    # Lowest low
            close=group[-1].close,         # Close of last candle
            volume=sum(k.volume for k in group),  # Total volume
            interval='30m'
        )
        
        klines_30m.append(kline_30m)
        i += 6
    
    return tuple(klines_30m) if klines_30m else None
