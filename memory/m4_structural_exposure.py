"""
M4 Structural Exposure - Tier B-2 Phase 1

B2.2: Structural Exposure Count

Per Tier B-2 Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
import math


# ==============================================================================
# B2.2: Structural Exposure Count
# ==============================================================================

@dataclass(frozen=True)
class StructuralExposureCount:
    """
    Counts number of distinct exposure events.
    
    Cannot imply: intensity, frequency quality, signal validity
    """
    exposure_count: int
    observation_window: float


def compute_structural_exposure_count(
    *,
    exposure_timestamps: tuple[float, ...],
    observation_start_ts: float,
    observation_end_ts: float
) -> StructuralExposureCount:
    """
    Count how many distinct exposure events occurred within observation window.
    
    Timestamp list may be unsorted.
    
    Args:
        exposure_timestamps: Timestamps when structure was exposed
        observation_start_ts: Window start timestamp
        observation_end_ts: Window end timestamp
    
    Returns:
        StructuralExposureCount with count and window
    
    Raises:
        ValueError: If timestamps invalid, events outside window, or non-finite values
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
    
    # Validate all exposure timestamps
    for ts in exposure_timestamps:
        if not math.isfinite(ts):
            raise ValueError(f"Exposure timestamp must be finite, got {ts}")
        if ts < observation_start_ts or ts > observation_end_ts:
            raise ValueError(
                f"Exposure timestamp ({ts}) outside observation window "
                f"({observation_start_ts}, {observation_end_ts})"
            )
    
    # Count exposures
    exposure_count = len(exposure_timestamps)
    
    return StructuralExposureCount(
        exposure_count=exposure_count,
        observation_window=observation_window
    )
