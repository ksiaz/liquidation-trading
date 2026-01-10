"""
M3 Sequence Buffer

Rolling window of evidence tokens with timestamp ordering.
Bounded by time window and max length to prevent unbounded growth.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Deque, List, Tuple, Optional
from memory.m3_evidence_token import EvidenceToken


@dataclass
class SequenceBuffer:
    """
    Rolling window of recent evidence tokens with timestamps.
    
    Bounded by time window and max length to prevent unbounded growth.
    Tokens stored in chronological order (FIFO - oldest first, newest last).
    
    NO automatic sorting, ranking, or importance weighting.
    Pure chronological ordering of append time.
    """
    
    # Core sequence storage (deque for O(1) append/pop)
    tokens: Deque[Tuple[EvidenceToken, float]] = field(default_factory=deque)
    # Deque of (token, timestamp) tuples
    # Chronologically ordered by append time (oldest → newest)
    # Purpose: Recent temporal context for motif extraction
    
    # Buffer bounds
    max_length: int = 100
    # Maximum number of tokens to retain
    # Purpose: Prevent unbounded memory growth
    # NOT an importance filter - purely a capacity limit
    
    time_window_sec: float = 86400.0
    # Time window for token retention (seconds)
    # Purpose: Only keep tokens from last N seconds
    # Default: 86400 = 24 hours
    # NOT a relevance filter - purely a recency bound
    
    # Metadata (cumulative counters)
    total_tokens_observed: int = 0
    # Cumulative count of all tokens ever appended
    # Purpose: Track total event activity (never decreases)
    # NOT used for prediction or importance weighting
    
    def append(self, token: EvidenceToken, timestamp: float) -> None:
        """
        Append a new token to the buffer.
        
        Tokens are appended in arrival order (NOT sorted by timestamp).
        After append, bounds are enforced (time window + max length).
        
        Args:
            token: Evidence token to append
            timestamp: Unix timestamp of event
        
        Returns:
            None (mutates buffer in place)
        """
        # Append to end (newest)
        self.tokens.append((token, timestamp))
        
        # Increment cumulative counter
        self.total_tokens_observed += 1
        
        # Enforce bounds immediately after append
        self._enforce_time_window(timestamp)
        self._enforce_max_length()
    
    def trim_old(self, current_ts: float) -> int:
        """
        Remove tokens outside the time window.
        
        This is called during append, but can also be called explicitly
        to trim stale tokens without adding new ones.
        
        Args:
            current_ts: Current timestamp for window calculation
        
        Returns:
            Number of tokens removed
        """
        return self._enforce_time_window(current_ts)
    
    def get_recent(self, n: int) -> List[Tuple[EvidenceToken, float]]:
        """
        Get N most recent tokens from buffer.
        
        Returns chronological order (oldest → newest).
        NOT sorted by importance or relevance.
        
        Args:
            n: Number of recent tokens to return
        
        Returns:
            List of (token, timestamp) tuples (may be < n if buffer smaller)
        """
        if n <= 0:
            return []
        
        # Get last N tokens (most recent)
        # Convert deque slice to list for return
        recent = list(self.tokens)[-n:] if len(self.tokens) >= n else list(self.tokens)
        return recent
    
    def get_all(self) -> List[Tuple[EvidenceToken, float]]:
        """
        Get all tokens in buffer.
        
        Returns chronological order (oldest → newest).
        
        Returns:
            List of all (token, timestamp) tuples
        """
        return list(self.tokens)
    
    def get_size(self) -> int:
        """
        Get current buffer size (number of tokens).
        
        Returns:
            Current number of tokens in buffer
        """
        return len(self.tokens)
    
    def get_oldest_timestamp(self) -> Optional[float]:
        """
        Get timestamp of oldest token in buffer.
        
        Returns:
            Timestamp of oldest token, or None if buffer empty
        """
        return self.tokens[0][1] if self.tokens else None
    
    def get_newest_timestamp(self) -> Optional[float]:
        """
        Get timestamp of newest token in buffer.
        
        Returns:
            Timestamp of newest token, or None if buffer empty
        """
        return self.tokens[-1][1] if self.tokens else None
    
    def get_time_span(self) -> Optional[float]:
        """
        Get time span covered by buffer (newest - oldest).
        
        Returns:
            Time span in seconds, or None if buffer has < 2 tokens
        """
        if len(self.tokens) < 2:
            return None
        return self.tokens[-1][1] - self.tokens[0][1]
    
    def clear(self) -> None:
        """
        Clear all tokens from buffer.
        
        Preserves total_tokens_observed counter (cumulative).
        """
        self.tokens.clear()
    
    # Private helper methods
    
    def _enforce_time_window(self, current_ts: float) -> int:
        """
        Remove tokens older than time window.
        
        Args:
            current_ts: Current timestamp for window calculation
        
        Returns:
            Number of tokens removed
        """
        removed_count = 0
        cutoff_ts = current_ts - self.time_window_sec
        
        # Remove from left (oldest) while below cutoff
        while self.tokens and self.tokens[0][1] < cutoff_ts:
            self.tokens.popleft()
            removed_count += 1
        
        return removed_count
    
    def _enforce_max_length(self) -> int:
        """
        Remove oldest tokens if buffer exceeds max length.
        
        Returns:
            Number of tokens removed
        """
        removed_count = 0
        
        # Remove from left (oldest) while over capacity
        while len(self.tokens) > self.max_length:
            self.tokens.popleft()
            removed_count += 1
        
        return removed_count
    
    def __len__(self) -> int:
        """Support len() operator."""
        return len(self.tokens)
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"SequenceBuffer("
            f"size={len(self.tokens)}, "
            f"max_length={self.max_length}, "
            f"time_window={self.time_window_sec}s, "
            f"total_observed={self.total_tokens_observed})"
        )


def create_sequence_buffer(
    max_length: int = 100,
    time_window_sec: float = 86400.0
) -> SequenceBuffer:
    """
    Factory function to create a SequenceBuffer with custom bounds.
    
    Args:
        max_length: Maximum number of tokens to retain
        time_window_sec: Time window for token retention (seconds)
    
    Returns:
        New SequenceBuffer instance
    """
    return SequenceBuffer(
        tokens=deque(),
        max_length=max_length,
        time_window_sec=time_window_sec,
        total_tokens_observed=0
    )
