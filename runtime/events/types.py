"""
HLP14: Event Types.

Defines the types of market events the system tracks:
- CASCADE: Liquidation cascade in progress
- HUNT_FAILED: Liquidation hunt that failed (reversal)
- OI_COLLAPSE: Sudden OI reduction (post-liquidation)
- DEPTH_THIN: Order book depth thinning
- FUNDING_SPIKE: Extreme funding rate movement
- VOLUME_SPIKE: Unusual volume increase
"""

from enum import Enum, auto


class EventType(Enum):
    """Types of market events."""

    # Liquidation events
    CASCADE = "cascade"              # Liquidation cascade in progress
    HUNT_FAILED = "hunt_failed"      # Failed liquidation hunt (reversal)
    OI_COLLAPSE = "oi_collapse"      # Sudden OI reduction

    # Order book events
    DEPTH_THIN = "depth_thin"        # Significant depth reduction
    DEPTH_IMBALANCE = "depth_imbalance"  # Bid/ask imbalance

    # Funding events
    FUNDING_SPIKE = "funding_spike"  # Extreme funding rate
    FUNDING_FLIP = "funding_flip"    # Funding direction change

    # Volume events
    VOLUME_SPIKE = "volume_spike"    # Unusual volume increase
    AGGRESSION_FLIP = "aggression_flip"  # Order flow direction change

    # Price events
    RANGE_BREAKOUT = "range_breakout"    # Breaking consolidation
    SUPPORT_BREAK = "support_break"      # Support level broken
    RESISTANCE_BREAK = "resistance_break"  # Resistance level broken

    # Composite events
    SETUP_COMPLETE = "setup_complete"    # Strategy setup conditions met
    TRIGGER_READY = "trigger_ready"      # Entry trigger conditions met


class EventSeverity(Enum):
    """Severity/importance of events."""

    LOW = auto()       # Informational, no action needed
    MEDIUM = auto()    # Worth monitoring
    HIGH = auto()      # Potential trading opportunity
    CRITICAL = auto()  # Immediate action required


# Event metadata
EVENT_INFO = {
    EventType.CASCADE: {
        'typical_duration_sec': 30,
        'entry_window_pct': 0.3,  # Enter when 70% complete
        'severity': EventSeverity.CRITICAL,
    },
    EventType.HUNT_FAILED: {
        'typical_duration_sec': 10,
        'entry_window_pct': 0.5,
        'severity': EventSeverity.HIGH,
    },
    EventType.OI_COLLAPSE: {
        'typical_duration_sec': 60,
        'entry_window_pct': 0.7,
        'severity': EventSeverity.HIGH,
    },
    EventType.DEPTH_THIN: {
        'typical_duration_sec': 120,
        'entry_window_pct': 0.5,
        'severity': EventSeverity.MEDIUM,
    },
    EventType.FUNDING_SPIKE: {
        'typical_duration_sec': 300,
        'entry_window_pct': 0.6,
        'severity': EventSeverity.MEDIUM,
    },
    EventType.VOLUME_SPIKE: {
        'typical_duration_sec': 60,
        'entry_window_pct': 0.4,
        'severity': EventSeverity.MEDIUM,
    },
    EventType.RANGE_BREAKOUT: {
        'typical_duration_sec': 120,
        'entry_window_pct': 0.3,
        'severity': EventSeverity.HIGH,
    },
}


def get_event_info(event_type: EventType) -> dict:
    """Get metadata for an event type."""
    return EVENT_INFO.get(event_type, {
        'typical_duration_sec': 60,
        'entry_window_pct': 0.5,
        'severity': EventSeverity.MEDIUM,
    })
