"""
Event Labeling Package.

Provides mechanical event labeling for historical data:
- EventLabeler: Label cascade, hunt, and other events mechanically
- LabeledEvent: Event with ground truth label

HLP24 Components.
"""

from .event_labeler import (
    EventLabeler,
    LabeledEvent,
    LabelConfig,
    EventLabel,
)

__all__ = [
    'EventLabeler',
    'LabeledEvent',
    'LabelConfig',
    'EventLabel',
]
