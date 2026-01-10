"""
M4 Interaction Density Views

Read-only, deterministic view of temporal interaction patterns at memory nodes.
Describes how concentrated and spaced market interactions are over time,
without interpretation, ranking, or opportunity scoring.

NO prediction, NO ranking, NO scoring.
"""

from dataclasses import dataclass
import statistics
from typing import List
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


@dataclass
class InteractionDensityView:
    """
    Read-only view of interaction density at a node.
    
    All fields are factual statistics or neutral metrics.
    NO importance scores, NO quality judgments, NO opportunity flags.
    """
    node_id: str
    
    # Factual density metrics
    interactions_per_hour: float  # Mean interaction rate
    median_gap_sec: float  # Median seconds between interactions
    min_gap_sec: float  # Minimum observed gap
    max_gap_sec: float  # Maximum observed gap
    gap_stddev_sec: float  # Standard deviation of gaps
    
    # Burstiness (statistical measure, NOT quality score)
    burstiness_coefficient: float  # (stddev - mean) / (stddev + mean), range [-1, 1]
    
    # Period durations (factual, neutral descriptors)
    longest_active_period_sec: float  # Longest continuous activity period
    longest_idle_period_sec: float  # Longest gap between interactions
    
    # Factual counts
    total_interaction_count: int
    observation_duration_sec: float  # Total time node has existed


def get_interaction_density(
    node: EnrichedLiquidityMemoryNode,
    current_ts: float
) -> InteractionDensityView:
    """
    Get interaction density view for a single node.
    
    Pure function: same node + same current_ts → same output.
    Read-only: does not modify node.
    Factual: no ranking, no opportunity scoring, no prediction.
    
    Args:
        node: Memory node to analyze
        current_ts: Reference timestamp for duration calculations
    
    Returns:
        InteractionDensityView with factual density metrics
    """
    node_id = node.id
    
    # Read M2 fields (read-only)
    timestamps = list(node.interaction_timestamps) if node.interaction_timestamps else []
    total_count = len(timestamps)
    
    # Calculate observation duration
    if total_count > 0:
        first_ts = node.first_seen_ts
        last_ts = node.last_interaction_ts
        observation_duration = current_ts - first_ts
    else:
        observation_duration = 0.0
    
    # Calculate interactions per hour
    if observation_duration > 0:
        duration_hours = observation_duration / 3600.0
        interactions_per_hour = total_count / duration_hours
    else:
        interactions_per_hour = 0.0
    
    # Calculate gaps between interactions
    if total_count >= 2:
        gaps = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        
        median_gap = statistics.median(gaps)
        min_gap = min(gaps)
        max_gap = max(gaps)
        
        # Stddev (requires at least 2 gaps)
        if len(gaps) >= 2:
            gap_stddev = statistics.stdev(gaps)
        else:
            gap_stddev = 0.0
        
        # Burstiness coefficient: (stddev - mean) / (stddev + mean)
        # Range: [-1, 1]
        # -1 = perfectly regular, 0 = Poisson, 1 = highly bursty
        mean_gap = statistics.mean(gaps)
        if gap_stddev + mean_gap > 0:
            burstiness = (gap_stddev - mean_gap) / (gap_stddev + mean_gap)
        else:
            burstiness = 0.0
        
        # Longest active/idle periods
        longest_idle = max_gap
        # Active period: find longest sequence with gaps < threshold (e.g., < 2x median)
        active_threshold = 2.0 * median_gap if median_gap > 0 else float('inf')
        longest_active = 0.0
        current_active = gaps[0]
        
        for i in range(1, len(gaps)):
            if gaps[i] < active_threshold:
                current_active += gaps[i]
            else:
                longest_active = max(longest_active, current_active)
                current_active = gaps[i]
        longest_active = max(longest_active, current_active)
        
    else:
        # Not enough data for gap statistics
        median_gap = 0.0
        min_gap = 0.0
        max_gap = 0.0
        gap_stddev = 0.0
        burstiness = 0.0
        longest_active = 0.0
        longest_idle = 0.0
    
    return InteractionDensityView(
        node_id=node_id,
        interactions_per_hour=interactions_per_hour,
        median_gap_sec=median_gap,
        min_gap_sec=min_gap,
        max_gap_sec=max_gap,
        gap_stddev_sec=gap_stddev,
        burstiness_coefficient=burstiness,
        longest_active_period_sec=longest_active,
        longest_idle_period_sec=longest_idle,
        total_interaction_count=total_count,
        observation_duration_sec=observation_duration
    )


def get_interaction_density_in_time_range(
    node: EnrichedLiquidityMemoryNode,
    start_ts: float,
    end_ts: float
) -> InteractionDensityView:
    """
    Get interaction density view filtered to a specific time range.
    
    Factual time filter - NOT an importance or relevance filter.
    
    Args:
        node: Memory node to analyze
        start_ts: Start of time range (inclusive)
        end_ts: End of time range (inclusive)
    
    Returns:
        InteractionDensityView for the specified time window
    """
    # Read timestamps (read-only)
    all_timestamps = list(node.interaction_timestamps) if node.interaction_timestamps else []
    
    # Filter to time range
    filtered_timestamps = [ts for ts in all_timestamps if start_ts <= ts <= end_ts]
    
    #  Create temporary node-like structure for filtered data
    # We'll compute stats directly without modifying original node
    
    if len(filtered_timestamps) == 0:
        # No interactions in range
        return InteractionDensityView(
            node_id=node.id,
            interactions_per_hour=0.0,
            median_gap_sec=0.0,
            min_gap_sec=0.0,
            max_gap_sec=0.0,
            gap_stddev_sec=0.0,
            burstiness_coefficient=0.0,
            longest_active_period_sec=0.0,
            longest_idle_period_sec=0.0,
            total_interaction_count=0,
            observation_duration_sec=end_ts - start_ts
        )
    
    # Calculate stats for filtered timestamps
    total_count = len(filtered_timestamps)
    observation_duration = end_ts - start_ts
    
    if observation_duration > 0:
        duration_hours = observation_duration / 3600.0
        interactions_per_hour = total_count / duration_hours
    else:
        interactions_per_hour = 0.0
    
    # Calculate gaps
    if total_count >= 2:
        gaps = [filtered_timestamps[i] - filtered_timestamps[i-1] 
                for i in range(1, len(filtered_timestamps))]
        
        median_gap = statistics.median(gaps)
        min_gap = min(gaps)
        max_gap = max(gaps)
        
        if len(gaps) >= 2:
            gap_stddev = statistics.stdev(gaps)
        else:
            gap_stddev = 0.0
        
        mean_gap = statistics.mean(gaps)
        if gap_stddev + mean_gap > 0:
            burstiness = (gap_stddev - mean_gap) / (gap_stddev + mean_gap)
        else:
            burstiness = 0.0
        
        longest_idle = max_gap
        active_threshold = 2.0 * median_gap if median_gap > 0 else float('inf')
        longest_active = 0.0
        current_active = gaps[0]
        
        for i in range(1, len(gaps)):
            if gaps[i] < active_threshold:
                current_active += gaps[i]
            else:
                longest_active = max(longest_active, current_active)
                current_active = gaps[i]
        longest_active = max(longest_active, current_active)
    else:
        median_gap = 0.0
        min_gap = 0.0
        max_gap = 0.0
        gap_stddev = 0.0
        burstiness = 0.0
        longest_active = 0.0
        longest_idle = 0.0
    
    return InteractionDensityView(
        node_id=node.id,
        interactions_per_hour=interactions_per_hour,
        median_gap_sec=median_gap,
        min_gap_sec=min_gap,
        max_gap_sec=max_gap,
        gap_stddev_sec=gap_stddev,
        burstiness_coefficient=burstiness,
        longest_active_period_sec=longest_active,
        longest_idle_period_sec=longest_idle,
        total_interaction_count=total_count,
        observation_duration_sec=observation_duration
    )
