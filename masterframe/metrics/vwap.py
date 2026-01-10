"""
Session-Anchored VWAP Calculator

VWAP = Volume-Weighted Average Price
Formula: Σ(price × volume) / Σ(volume)

RULES:
- Anchored to session start (UTC 00:00)
- Resets at session boundary
- Returns None until first trade of session
- Deterministic calculation
"""

from typing import Optional, Tuple
from datetime import datetime, timezone
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import AggressiveTrade


class VWAPCalculator:
    """
    Calculates session-anchored VWAP.
    
    INVARIANT: Resets at UTC 00:00 daily.
    INVARIANT: Returns None until first trade.
    """
    
    def __init__(self):
        """Initialize VWAP calculator."""
        self._session_date: Optional[str] = None  # YYYY-MM-DD format
        self._cum_pv: float = 0.0  # Cumulative price × volume
        self._cum_v: float = 0.0   # Cumulative volume
    
    def update(self, trades: Tuple[AggressiveTrade, ...], current_time: float) -> None:
        """
        Update VWAP with new trades.
        
        Args:
            trades: Recent trades to process
            current_time: Current timestamp
        
        RULE: Resets if new session detected.
        """
        # Get current session date (UTC)
        current_dt = datetime.fromtimestamp(current_time, tz=timezone.utc)
        current_session = current_dt.strftime('%Y-%m-%d')
        
        # Check for session boundary
        if self._session_date != current_session:
            # New session - reset
            self._session_date = current_session
            self._cum_pv = 0.0
            self._cum_v = 0.0
        
        # Accumulate trades from current session
        for trade in trades:
            trade_dt = datetime.fromtimestamp(trade.timestamp, tz=timezone.utc)
            trade_session = trade_dt.strftime('%Y-%m-%d')
            
            # Only accumulate trades from current session
            if trade_session == current_session:
                self._cum_pv += trade.price * trade.quantity
                self._cum_v += trade.quantity
    
    def get_vwap(self) -> Optional[float]:
        """
        Get current session VWAP.
        
        Returns:
            VWAP if available, None otherwise
        
        RULE: Returns None until first trade of session.
        """
        if self._cum_v == 0:
            return None
        
        return self._cum_pv / self._cum_v
    
    def reset(self) -> None:
        """
        Manually reset VWAP calculator.
        
        Used for testing or manual session resets.
        """
        self._session_date = None
        self._cum_pv = 0.0
        self._cum_v = 0.0
