"""
M4 Structural Persistence - Tier B-2 Phase 1

B2.1: Structural Persistence Duration

Per Tier B-2 Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
import math


# ==============================================================================
# B2.1: Structural Persistence Duration
# ==============================================================================

@dataclass(frozen=True)
class StructuralPersistenceDuration:
    """
    Measures total time a structure is present within observation window.
    
    Cannot imply: strength, reliability, continuation, importance
    """
    total_persistence_duration: float
    observation_window: float
    persistence_ratio: float


def compute_structural_persistence_duration(
    *,
    observation_start_ts: float,
    observation_end_ts: float,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralPersistenceDuration:
    """
    Measure total time a structure existed within an observation window.
    
    Presence intervals may overlap and will be merged.
    
    Args:
        observation_start_ts: Window start timestamp
        observation_end_ts: Window end timestamp
        presence_intervals: Intervals when structure was present (start, end) tuples
    
    Returns:
        StructuralPersistenceDuration with computed metrics
    
    Raises:
        ValueError: If timestamps invalid, intervals malformed, or non-finite values
    """
    # Validate numeric inputs
    if not math.isfinite(observation_start_ts):
        raise ValueError(f"observation_start_ts must be finite, got {observation_start_ts}")
    if not math.isfinite(observation_end_ts):
        raise ValueError(f"observation_end_ts must be finite, got {observation_end_ts}")
    
    # Validate observation window
    if observation_end_ts <= observation_start_ts:
        raise ValueError(
            f"observation_end_ts ({observation_end_ts}) must be > "
            f"observation_start_ts ({observation_start_ts})"
        )
    
    observation_window = observation_end_ts - observation_start_ts
    
    # Handle empty intervals
    if len(presence_intervals) == 0:
        return StructuralPersistenceDuration(
            total_persistence_duration=0.0,
            observation_window=observation_window,
            persistence_ratio=0.0
        )
    
    # Validate and merge presence intervals
    for start, end in presence_intervals:
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError(f"Interval timestamps must be finite: ({start}, {end})")
        if end <= start:
            raise ValueError(f"Interval end ({end}) must be > start ({start})")
        if start < observation_start_ts or end > observation_end_ts:
            raise ValueError(
                f"Interval ({start}, {end}) outside observation window "
                f"({observation_start_ts}, {observation_end_ts})"
            )
    
    # Sort intervals by start time
    sorted_intervals = sorted(presence_intervals, key=lambda x: x[0])
    
    # Merge overlapping intervals
    merged = []
    current_start, current_end = sorted_intervals[0]
    
    for start, end in sorted_intervals[1:]:
        if start <= current_end:
            # Overlapping or adjacent - merge
            current_end = max(current_end, end)
        else:
            # Non-overlapping - save current and start new
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    
    # Don't forget the last interval
    merged.append((current_start, current_end))
    
    # Sum durations of merged intervals
    total_persistence_duration = sum(end - start for start, end in merged)
    
    # Compute ratio
    persistence_ratio = total_persistence_duration / observation_window
    
    return StructuralPersistenceDuration(
        total_persistence_duration=total_persistence_duration,
        observation_window=observation_window,
        persistence_ratio=persistence_ratio
    )
