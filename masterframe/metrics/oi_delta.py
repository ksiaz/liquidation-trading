"""
Open Interest Delta Calculator

Tracks changes in open interest (if available).

RULES:
- Returns None if OI data unavailable
- Simple delta calculation: current - previous
- Deterministic
"""

from typing import Optional


class OITracker:
    """
    Tracks open interest delta.
    
    INVARIANT: Returns None if OI not available.
    INVARIANT: First update returns None (no previous value).
    """
    
    def __init__(self):
        """Initialize OI tracker."""
        self._prev_oi: Optional[float] = None
        self._current_oi: Optional[float] = None
    
    def update(self, current_oi: Optional[float]) -> None:
        """
        Update with new OI value.
        
        Args:
            current_oi: Current open interest value (None if unavailable)
        
        RULE: Stores for delta calculation on next update.
        """
        self._prev_oi = self._current_oi
        self._current_oi = current_oi
    
    def get_delta(self) -> Optional[float]:
        """
        Get OI delta (current - previous).
        
        Returns:
            Delta if both values available, None otherwise
        
        RULE: Returns None if:
        - No previous OI
        - Current OI unavailable
        - Previous OI unavailable
        """
        if self._current_oi is None or self._prev_oi is None:
            return None
        
        return self._current_oi - self._prev_oi
    
    def reset(self) -> None:
        """Reset OI tracker to initial state."""
        self._prev_oi = None
        self._current_oi = None
