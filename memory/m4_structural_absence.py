"""
M4 Structural Absence - Tier B Phase B-1

B1.1: Structural Absence Duration

Per Tier B Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass


# ==============================================================================
# B1.1: Structural Absence Duration
# ==============================================================================

@dataclass(frozen=True)
class StructuralAbsenceDuration:
    """
    Measures duration when structural condition was NOT present.
    
    Cannot imply: rejection, failure, avoidance, inducement
    """
    absence_duration: float
    observation_window: float
    absence_ratio: float


def compute_structural_absence_duration(
    *,
    observation_start_ts: float,
    observation_end_ts: float,
    presence_intervals: tuple[tuple[float, float], ...]
) -> StructuralAbsenceDuration:
    """
    Measure how long a structural condition was NOT present within observation window.
    
    Args:
        observation_start_ts: Window start timestamp
        observation_end_ts: Window end timestamp
        presence_intervals: Intervals when condition was present (start, end) tuples
    
    Returns:
        StructuralAbsenceDuration with computed metrics
    
    Raises:
        ValueError: If timestamps invalid or intervals outside window
    """
    # Validate observation window
    if observation_end_ts <= observation_start_ts:
        raise ValueError(
            f"observation_end_ts ({observation_end_ts}) must be > "
            f"observation_start_ts ({observation_start_ts})"
        )
    
    observation_window = observation_end_ts - observation_start_ts
    
    # Validate and merge presence intervals
    for start, end in presence_intervals:
        if end <= start:
            raise ValueError(f"Interval end ({end}) must be > start ({start})")
        if start < observation_start_ts or end > observation_end_ts:
            raise ValueError(
                f"Interval ({start}, {end}) outside observation window "
                f"({observation_start_ts}, {observation_end_ts})"
            )
    
    # Compute total present duration (handle overlaps)
    if len(presence_intervals) == 0:
        present_duration = 0.0
    else:
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
        present_duration = sum(end - start for start, end in merged)
    
    # Compute absence metrics
    absence_duration = observation_window - present_duration
    absence_ratio = absence_duration / observation_window
    
    return StructuralAbsenceDuration(
        absence_duration=absence_duration,
        observation_window=observation_window,
        absence_ratio=absence_ratio
    )
