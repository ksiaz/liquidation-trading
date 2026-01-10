"""
M2 Memory State Extensions

Adds three-state model (ACTIVE/DORMANT/ARCHIVED) with historical continuity.
"""

from enum import Enum


class MemoryState(Enum):
    """Memory node lifecycle states."""
    ACTIVE = "active"          # Recent interaction, normal decay
    DORMANT = "dormant"        # Inactive, historical evidence preserved, reduced decay
    ARCHIVED = "archived"      # Fully decayed, cold storage only
    

class MemoryStateThresholds:
    """State transition thresholds (configurable)."""
    
    # ACTIVE → DORMANT
    DORMANT_STRENGTH_THRESHOLD = 0.15      # Below this = dormant
    DORMANT_TIMEOUT_SEC = 3600.0           # 1 hour without interaction
    
    # DORMANT → ARCHIVED
    ARCHIVE_STRENGTH_THRESHOLD = 0.01      # Below this = archived
    ARCHIVE_TIMEOUT_SEC = 86400.0          # 24 hours without interaction
    
    # Decay rates
    ACTIVE_DECAY_RATE = 0.0001             # 0.01% per second
    DORMANT_DECAY_RATE = 0.00001           # 0.001% per second (10x slower)
    
    # Revival
    DORMANT_REVIVAL_STRENGTH_BOOST = 0.1   # Added when dormant node reactivates
