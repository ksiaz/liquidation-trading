"""
Logging Type Definitions

Data structures for audit logging.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any
import json


class EventType(Enum):
    """
    Log event types.
    
    All system events that must be logged.
    """
    REGIME_CHANGE = "REGIME_CHANGE"
    SLBRS_STATE_TRANSITION = "SLBRS_STATE_TRANSITION"
    EFFCS_STATE_TRANSITION = "EFFCS_STATE_TRANSITION"
    SETUP_INVALIDATION = "SETUP_INVALIDATION"
    TRADE_ENTRY = "TRADE_ENTRY"
    TRADE_EXIT = "TRADE_EXIT"
    KILL_SWITCH = "KILL_SWITCH"


@dataclass
class LogEvent:
    """
    Base log event.
    
    INVARIANT: Structured, timestamped, JSON-serializable.
    """
    event_type: EventType
    timestamp: float
    data: Dict[str, Any]
    
    def to_json(self) -> str:
        """
        Convert to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps({
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            **self.data
        }, default=str)  # default=str handles non-serializable types
    
    def to_dict(self) -> Dict[str, Any]:
        """Get event as dictionary."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            **self.data
        }
