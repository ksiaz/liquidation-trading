"""
Generic Rolling Buffer with Explicit Warm-Up Handling

INVARIANTS:
- Returns None until buffer contains >= min_size entries
- Evicts entries older than max_age_seconds
- Never interpolates missing data
- Deterministic behavior
"""

from typing import Generic, TypeVar, Optional, Tuple, List
from collections import deque
import time

T = TypeVar('T')


class RollingBuffer(Generic[T]):
    """
    Fixed-size rolling buffer that tracks timestamped items.
    
    RULE: Returns None for all queries until warm (>=min_size entries).
    RULE: Automatically evicts entries older than max_age_seconds.
    RULE: No interpolation or data guessing.
    
    Example:
        buffer = RollingBuffer[AggressiveTrade](max_size=100, min_size=30, max_age_seconds=60.0)
        buffer.push(trade, timestamp)
        if buffer.is_warm():
            trades = buffer.get_items()
    """
    
    def __init__(self, max_size: int, min_size: int, max_age_seconds: float):
        """
        Initialize rolling buffer.
        
        Args:
            max_size: Maximum number of items to store
            min_size: Minimum items required before buffer is considered warm
            max_age_seconds: Maximum age of items before eviction
        
        RULE: min_size <= max_size
        """
        if min_size > max_size:
            raise ValueError(f"min_size ({min_size}) cannot exceed max_size ({max_size})")
        
        self._max_size = max_size
        self._min_size = min_size
        self._max_age_seconds = max_age_seconds
        
        # Use deque for efficient append/popleft operations
        # Each entry is (timestamp, item)
        self._buffer: deque[Tuple[float, T]] = deque(maxlen=max_size)
    
    def push(self, item: T, timestamp: float) -> None:
        """
        Add item with timestamp to buffer.
        
        Args:
            item: Data item to store
            timestamp: Unix epoch timestamp in seconds
        
        RULE: Evicts stale entries before adding.
        RULE: Maintains max_size automatically via deque.
        """
        # Evict stale entries first
        self._evict_stale(timestamp)
        
        # Add new item
        self._buffer.append((timestamp, item))
    
    def is_warm(self) -> bool:
        """
        Check if buffer has sufficient data.
        
        Returns:
            True if buffer contains >= min_size entries, False otherwise
        
        RULE: This is the ONLY way to determine if data is ready for use.
        """
        return len(self._buffer) >= self._min_size
    
    def get_items(self) -> Optional[Tuple[T, ...]]:
        """
        Get all items in buffer if warm.
        
        Returns:
            Tuple of all items if warm, None otherwise
        
        RULE: Returns None if not warm (explicit NULL handling).
        RULE: Returns immutable tuple to prevent external mutation.
        """
        if not self.is_warm():
            return None
        
        # Return only items, not timestamps
        return tuple(item for _, item in self._buffer)
    
    def get_latest(self) -> Optional[T]:
        """
        Get most recent item if warm.
        
        Returns:
            Latest item if warm, None otherwise
        
        RULE: Returns None if not warm.
        """
        if not self.is_warm():
            return None
        
        if not self._buffer:
            return None
        
        # Return latest item (rightmost in deque)
        _, item = self._buffer[-1]
        return item
    
    def get_items_in_window(self, window_seconds: float, reference_time: float) -> Optional[Tuple[T, ...]]:
        """
        Get all items within a time window before reference_time.
        
        Args:
            window_seconds: Size of time window (seconds)
            reference_time: End of window (typically current time)
        
        Returns:
            Tuple of items within window if warm, None otherwise
        
        RULE: Returns None if not warm.
        RULE: Only includes items with timestamp >= (reference_time - window_seconds).
        """
        if not self.is_warm():
            return None
        
        cutoff_time = reference_time - window_seconds
        items = []
        
        for timestamp, item in self._buffer:
            if timestamp >= cutoff_time and timestamp <= reference_time:
                items.append(item)
        
        return tuple(items)
    
    def clear(self) -> None:
        """
        Clear all items from buffer.
        
        RULE: After clear(), is_warm() returns False until min_size reached again.
        """
        self._buffer.clear()
    
    def _evict_stale(self, current_time: float) -> None:
        """
        Remove entries older than max_age_seconds.
        
        Args:
            current_time: Current timestamp for age calculation
        
        RULE: Evicts from left (oldest entries first).
        RULE: No forward-looking - only uses current_time and item timestamps.
        """
        cutoff_time = current_time - self._max_age_seconds
        
        # Remove old entries from left
        while self._buffer and self._buffer[0][0] < cutoff_time:
            self._buffer.popleft()
    
    def __len__(self) -> int:
        """Return current number of items in buffer."""
        return len(self._buffer)
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        warm_status = "WARM" if self.is_warm() else "NOT_WARM"
        return (f"RollingBuffer(size={len(self._buffer)}/{self._max_size}, "
                f"min={self._min_size}, status={warm_status})")
