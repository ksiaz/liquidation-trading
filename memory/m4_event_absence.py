"""
M4 Event Absence - Tier B Phase B-1

B1.3: Event Non-Occurrence Counter

Per Tier B Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass


# ==============================================================================
# B1.3: Event Non-Occurrence Counter
# ==============================================================================

@dataclass(frozen=True)
class EventNonOccurrenceCounter:
    """
    Counts expected events that did NOT occur.
    
    Cannot imply: missed opportunity, failure, invalidation, prediction error
    """
    expected_count: int
    observed_count: int
    non_occurrence_count: int


def compute_event_non_occurrence_counter(
    *,
    expected_event_ids: tuple[str, ...],
    observed_event_ids: tuple[str, ...]
) -> EventNonOccurrenceCounter:
    """
    Count how many expected events did NOT occur within an explicit sequence.
    
    Args:
        expected_event_ids: IDs of events that were expected
        observed_event_ids: IDs of events that were observed
    
    Returns:
        EventNonOccurrenceCounter with counts
    
    Raises:
        ValueError: If any ID is empty string
    """
    # Validate all IDs are non-empty
    for event_id in expected_event_ids:
        if not event_id:
            raise ValueError("Expected event ID cannot be empty string")
    
    for event_id in observed_event_ids:
        if not event_id:
            raise ValueError("Observed event ID cannot be empty string")
    
    # Compute counts
    expected_count = len(expected_event_ids)
    
    # Convert observed to set for efficient lookup
    observed_set = set(observed_event_ids)
    
    # Count how many expected events were observed
    observed_count = sum(1 for event_id in expected_event_ids if event_id in observed_set)
    
    # Non-occurrence count
    non_occurrence_count = expected_count - observed_count
    
    return EventNonOccurrenceCounter(
        expected_count=expected_count,
        observed_count=observed_count,
        non_occurrence_count=non_occurrence_count
    )
