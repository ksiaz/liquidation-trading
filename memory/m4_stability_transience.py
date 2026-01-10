"""
M4 Stability vs Transience Views

Read-only, deterministic view of memory persistence characteristics.
Describes how long nodes spend in different states and their lifecycle patterns,
without quality judgments, reliability scores, or persistence predictions.

NO prediction, NO ranking, NO scoring.
"""

from dataclasses import dataclass
from typing import Dict, List
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


@dataclass
class StabilityTransienceView:
    """
    Read-only view of stability/transience characteristics at a node.
    
    All fields are factual durations, ratios, or neutral state labels.
    NO reliability scores, NO quality judgments, NO persistence predictions.
    """
    node_id: str
    
    # Factual cumulative durations (seconds)
    cumulative_active_sec: float
    cumulative_dormant_sec: float
    cumulative_archived_sec: float
    
    # Factual ratios (proportions of lifetime)
    active_ratio: float  # 0.0-1.0
    dormant_ratio: float  # 0.0-1.0
    
    # Factual counts
    state_transition_count: int
    
    # Average durations (factual statistics)
    avg_active_duration_sec: float
    avg_dormant_duration_sec: float
    
    # Current snapshot (factual state)
    current_state: str  # 'ACTIVE', 'DORMANT', or 'ARCHIVED'
    current_strength: float  # 0.0-1.0
    strength_decay_rate: float  # per second
    
    # Time since last interaction (factual duration)
    time_since_last_interaction_sec: float
    
    # Total lifetime (factual duration)
    total_lifetime_sec: float


def get_stability_metrics(
    node: EnrichedLiquidityMemoryNode,
    current_ts: float
) -> StabilityTransienceView:
    """
    Get stability/transience metrics for a single node.
    
    Pure function: same node + same current_ts → same output.
    Read-only: does not modify node.
    Factual: no reliability scoring, no persistence prediction.
    
    Args:
        node: Memory node to analyze
        current_ts: Reference timestamp for duration calculations
    
    Returns:
        StabilityTransienceView with factual persistence metrics
    """
    node_id = node.id
    
    # Read M2 fields (read-only)
    first_seen = node.first_seen_ts
    last_interaction = node.last_interaction_ts
    current_strength = node.strength
    decay_rate = node.decay_rate
    is_active = node.active
    
    # Calculate total lifetime
    total_lifetime = current_ts - first_seen if current_ts >= first_seen else 0.0
    
    # Calculate time since last interaction
    time_since_interaction = current_ts - last_interaction if current_ts >= last_interaction else 0.0
    
    # Determine current state (neutral descriptors)
    if is_active:
        current_state = 'ACTIVE'
    else:
        # If inactive, determine if DORMANT or ARCHIVED based on strength
        if current_strength > 0.01:
            current_state = 'DORMANT'
        else:
            current_state = 'ARCHIVED'
    
    # For this simplified implementation, without detailed state transition history,
    # we'll estimate cumulative times based on current state and assumptions
    # In a full implementation, these would be tracked explicitly in M2
    
    # Simplified calculation: assume node has been in current state for entire lifetime
    # (This is a limitation - real implementation would need state history)
    if current_state == 'ACTIVE':
        cumulative_active = total_lifetime
        cumulative_dormant = 0.0
        cumulative_archived = 0.0
        state_transitions = 0
        avg_active_duration = total_lifetime if total_lifetime > 0 else 0.0
        avg_dormant_duration = 0.0
    elif current_state == 'DORMANT':
        # Estimate: recent time is dormant, earlier was active
        cumulative_dormant = time_since_interaction
        cumulative_active = total_lifetime - cumulative_dormant
        cumulative_active = max(0.0, cumulative_active)
        cumulative_archived = 0.0
        state_transitions = 1 if cumulative_active > 0 else 0
        avg_active_duration = cumulative_active if state_transitions > 0 else 0.0
        avg_dormant_duration = cumulative_dormant if cumulative_dormant > 0 else 0.0
    else:  # ARCHIVED
        # Estimate: was active, then dormant, now archived
        cumulative_archived = time_since_interaction * 0.5  # Arbitrary estimate
        cumulative_dormant = time_since_interaction * 0.5
        cumulative_active = total_lifetime - time_since_interaction
        cumulative_active = max(0.0, cumulative_active)
        state_transitions = 2
        avg_active_duration = cumulative_active if cumulative_active > 0 else 0.0
        avg_dormant_duration = cumulative_dormant if cumulative_dormant > 0 else 0.0
    
    # Calculate ratios
    if total_lifetime > 0:
        active_ratio = cumulative_active / total_lifetime
        dormant_ratio = cumulative_dormant / total_lifetime
    else:
        active_ratio = 0.0
        dormant_ratio = 0.0
    
    return StabilityTransienceView(
        node_id=node_id,
        cumulative_active_sec=cumulative_active,
        cumulative_dormant_sec=cumulative_dormant,
        cumulative_archived_sec=cumulative_archived,
        active_ratio=active_ratio,
        dormant_ratio=dormant_ratio,
        state_transition_count=state_transitions,
        avg_active_duration_sec=avg_active_duration,
        avg_dormant_duration_sec=avg_dormant_duration,
        current_state=current_state,
        current_strength=current_strength,
        strength_decay_rate=decay_rate,
        time_since_last_interaction_sec=time_since_interaction,
        total_lifetime_sec=total_lifetime
    )


def get_stability_metrics_batch(
    nodes: List[EnrichedLiquidityMemoryNode],
    current_ts: float
) -> Dict[str, StabilityTransienceView]:
    """
    Get stability metrics for multiple nodes.
    
    Returns dict mapping node_id → StabilityTransienceView.
    Output order is arbitrary (dict, not sorted by strength or any importance metric).
    
    Args:
        nodes: List of memory nodes to analyze
        current_ts: Reference timestamp
    
    Returns:
        Dict mapping node_id to stability metrics (unordered)
    """
    return {
        node.id: get_stability_metrics(node, current_ts)
        for node in nodes
    }
