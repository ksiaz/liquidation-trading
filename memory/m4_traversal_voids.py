"""
M4 Traversal Voids - Tier B Phase B-1

B1.2: Traversal Void Span

Per Tier B Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass


# ==============================================================================
# B1.2: Traversal Void Span
# ==============================================================================

@dataclass(frozen=True)
class TraversalVoidSpan:
    """
    Identifies continuous spans where no traversal occurred.
    
    Cannot imply: low activity, suppression, intent, buildup
    """
    max_void_duration: float
    void_intervals: tuple[tuple[float, float], ...]


def compute_traversal_void_span(
    *,
    observation_start_ts: float,
    observation_end_ts: float,
    traversal_timestamps: tuple[float, ...]
) -> TraversalVoidSpan:
    """
    Identify continuous spans where no traversal occurred across a region or path.
    
    Args:
        observation_start_ts: Window start timestamp
        observation_end_ts: Window end timestamp
        traversal_timestamps: Timestamps when traversals occurred
    
    Returns:
        TraversalVoidSpan with void intervals and maximum duration
    
    Raises:
        ValueError: If timestamps invalid or outside window
    """
    # Validate observation window
    if observation_end_ts <= observation_start_ts:
        raise ValueError(
            f"observation_end_ts ({observation_end_ts}) must be > "
            f"observation_start_ts ({observation_start_ts})"
        )
    
    # Validate all traversal timestamps within window
    for ts in traversal_timestamps:
        if ts < observation_start_ts or ts > observation_end_ts:
            raise ValueError(
                f"Traversal timestamp ({ts}) outside observation window "
                f"({observation_start_ts}, {observation_end_ts})"
            )
    
    # Sort timestamps (local copy, don't mutate input)
    sorted_timestamps = sorted(traversal_timestamps)
    
    # Compute void intervals
    void_intervals_list = []
    
    if len(sorted_timestamps) == 0:
        # No traversals - entire window is void
        void_intervals_list.append((observation_start_ts, observation_end_ts))
    else:
        # Gap from window start to first traversal
        if sorted_timestamps[0] > observation_start_ts:
            void_intervals_list.append((observation_start_ts, sorted_timestamps[0]))
        
        # Gaps between consecutive traversals
        for i in range(1, len(sorted_timestamps)):
            prev_ts = sorted_timestamps[i-1]
            curr_ts = sorted_timestamps[i]
            if curr_ts > prev_ts:  # Only add if there's a gap
                void_intervals_list.append((prev_ts, curr_ts))
        
        # Gap from last traversal to window end
        if sorted_timestamps[-1] < observation_end_ts:
            void_intervals_list.append((sorted_timestamps[-1], observation_end_ts))
    
    # Convert to tuple
    void_intervals = tuple(void_intervals_list)
    
    # Compute max void duration
    if len(void_intervals) == 0:
        max_void_duration = 0.0
    else:
        max_void_duration = max(end - start for start, end in void_intervals)
    
    return TraversalVoidSpan(
        max_void_duration=max_void_duration,
        void_intervals=void_intervals
    )
