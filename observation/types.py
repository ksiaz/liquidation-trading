"""
Observation System Types (Immutable)

Defines the data structures for the Memory-Centric Observation System.
These types are exposed via M5 for query results.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum, auto

class SystemHaltedException(Exception):
    """Critical Failure: System Invariant Broken."""
    pass

class ObservationStatus(Enum):
    UNINITIALIZED = auto()
    FAILED = auto()

@dataclass(frozen=True)
class SystemCounters:
    intervals_processed: Optional[int]
    dropped_events: Optional[Dict[str, int]]
    
@dataclass(frozen=True)
class ObservationSnapshot:
    """Immutable snapshot of the Observation System state."""
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[Dict[str, Any]]]
