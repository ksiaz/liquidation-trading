"""
M3 Motif Decay

Motif decay logic that inherits M2 node decay rates exactly.
Motifs are bound to their parent node's lifecycle.
"""

from typing import Dict, Tuple
from memory.m3_evidence_token import EvidenceToken
from memory.m3_motif_extractor import MotifMetrics


# M2 decay rates (imported for consistency)
ACTIVE_DECAY_RATE = 0.0001  # per second
DORMANT_DECAY_RATE = 0.00001  # per second (10× slower)
ARCHIVED_DECAY_RATE = 0.0  # frozen


def apply_motif_decay(
    metrics: MotifMetrics,
    current_ts: float,
    decay_rate: float
) -> MotifMetrics:
    """
    Apply mechanical decay to a single motif's strength.
    
    Decay formula (identical to M2 node decay):
        time_elapsed = current_ts - last_seen_ts
        decay_factor = 1.0 - (decay_rate * time_elapsed)
        strength *= max(0.0, decay_factor)
    
    Args:
        metrics: Motif metrics to decay
        current_ts: Current timestamp
        decay_rate: Decay rate in 1/second (from node state)
    
    Returns:
        Updated MotifMetrics (modified in place)
    """
    time_elapsed = current_ts - metrics.last_seen_ts
    
    if time_elapsed <= 0:
        # No time elapsed or future timestamp (shouldn't happen)
        return metrics
    
    # Calculate decay factor
    decay_factor = 1.0 - (decay_rate * time_elapsed)
    
    # Apply decay (floor at 0.0)
    metrics.strength *= max(0.0, decay_factor)
    
    return metrics


def apply_decay_to_all_motifs(
    motif_metrics: Dict[Tuple[EvidenceToken, ...], MotifMetrics],
    current_ts: float,
    node_decay_rate: float
) -> Dict[Tuple[EvidenceToken, ...], MotifMetrics]:
    """
    Apply decay to all motifs using the parent node's decay rate.
    
    Motifs inherit the exact decay rate from their parent node:
    - ACTIVE node: 0.0001/sec
    - DORMANT node: 0.00001/sec (10× slower)
    - ARCHIVED node: 0 (frozen)
    
    Args:
        motif_metrics: Dict of motif metrics
        current_ts: Current timestamp
        node_decay_rate: Decay rate from parent node state
    
    Returns:
        Updated motif metrics dict (modified in place)
    """
    for motif, metrics in motif_metrics.items():
        apply_motif_decay(metrics, current_ts, node_decay_rate)
    
    return motif_metrics


def get_decay_rate_for_node_state(node_state: str) -> float:
    """
    Get decay rate for a given node state.
    
    Args:
        node_state: Node state ("ACTIVE", "DORMANT", "ARCHIVED")
    
    Returns:
        Decay rate in 1/second
    """
    if node_state == "ACTIVE":
        return ACTIVE_DECAY_RATE
    elif node_state == "DORMANT":
        return DORMANT_DECAY_RATE
    elif node_state == "ARCHIVED":
        return ARCHIVED_DECAY_RATE
    else:
        # Default to active if unknown (safety)
        return ACTIVE_DECAY_RATE


def freeze_motifs(
    motif_metrics: Dict[Tuple[EvidenceToken, ...], MotifMetrics]
) -> Dict[Tuple[EvidenceToken, ...], MotifMetrics]:
    """
    Freeze all motifs (set decay rate to 0).
    
    Called when node transitions to ARCHIVED state.
    Motif strengths are preserved at current values.
    
    Args:
        motif_metrics: Dict of motif metrics
    
    Returns:
        Motif metrics dict (no modification needed, just informational)
    """
    # No actual modification needed - decay rate comes from node
    # This function exists for explicit lifecycle documentation
    return motif_metrics


def restore_motif_decay(
    motif_metrics: Dict[Tuple[EvidenceToken, ...], MotifMetrics],
    new_decay_rate: float
) -> Dict[Tuple[EvidenceToken, ...], MotifMetrics]:
    """
    Restore motif decay when node revives from DORMANT/ARCHIVED.
    
    Motifs preserve their historical counts and timestamps.
    Only decay rate changes (comes from node state).
    
    Args:
        motif_metrics: Dict of motif metrics
        new_decay_rate: New decay rate from revived node state
    
    Returns:
        Motif metrics dict (no modification needed, informational)
    """
    # No modification needed - decay rate applied externally
    # This function exists for explicit lifecycle documentation
    return motif_metrics


def calculate_decay_between_states(
    initial_strength: float,
    time_elapsed: float,
    decay_rate: float
) -> float:
    """
    Calculate decayed strength over a time period.
    
    Primarily used for testing and validation.
    
    Args:
        initial_strength: Starting strength value
        time_elapsed: Time elapsed in seconds
        decay_rate: Decay rate in 1/second
    
    Returns:
        Decayed strength value
    """
    if time_elapsed <= 0:
        return initial_strength
    
    decay_factor = 1.0 - (decay_rate * time_elapsed)
    return initial_strength * max(0.0, decay_factor)


def verify_decay_rate_alignment(
    node_decay_rate: float,
    node_state: str
) -> bool:
    """
    Verify that node decay rate matches expected rate for state.
    
    Used for validation and debugging.
    
    Args:
        node_decay_rate: Actual decay rate being used
        node_state: Node state string
    
    Returns:
        True if decay rate matches expected rate for state
    """
    expected_rate = get_decay_rate_for_node_state(node_state)
    
    # Allow small floating-point tolerance
    tolerance = 1e-9
    return abs(node_decay_rate - expected_rate) < tolerance


# Decay lifecycle documentation

class MotifDecayLifecycle:
    """
    Documentation of motif decay lifecycle states.
    
    This is NOT executable code - purely for documentation.
    Motifs follow the exact same lifecycle as their parent M2 node.
    """
    
    # State transitions and decay rates
    ACTIVE_TO_DORMANT = {
        "trigger": "Node strength < 0.15 OR idle > 3600s",
        "decay_before": ACTIVE_DECAY_RATE,
        "decay_after": DORMANT_DECAY_RATE,
        "motif_behavior": "Continue decaying at 10× slower rate",
        "counts_preserved": True,
        "timestamps_preserved": True
    }
    
    DORMANT_TO_ARCHIVED = {
        "trigger": "Node strength < 0.01 OR idle > 86400s",
        "decay_before": DORMANT_DECAY_RATE,
        "decay_after": ARCHIVED_DECAY_RATE,
        "motif_behavior": "Freeze - no further decay",
        "counts_preserved": True,
        "timestamps_preserved": True
    }
    
    DORMANT_TO_ACTIVE = {
        "trigger": "New evidence interaction at node",
        "decay_before": DORMANT_DECAY_RATE,
        "decay_after": ACTIVE_DECAY_RATE,
        "motif_behavior": "Resume active decay rate",
        "counts_preserved": True,
        "timestamps_preserved": True,
        "requires_new_evidence": True
    }
    
    ARCHIVED_TO_ACTIVE = {
        "trigger": "New evidence interaction at archived node",
        "decay_before": ARCHIVED_DECAY_RATE,
        "decay_after": ACTIVE_DECAY_RATE,
        "motif_behavior": "Unfreeze and resume active decay",
        "counts_preserved": True,
        "timestamps_preserved": True,
        "requires_new_evidence": True
    }
