"""
HLP14: Event Lifecycle Package.

Provides event tracking with lifecycle states:
- DETECTED: Preconditions met, event recognized
- TRIGGERED: Event has initiated (e.g., liquidation started)
- ACTIVE: Event is executing
- COMPLETING: Exhaustion signals appearing
- COMPLETED: Event finished
- EXPIRED: Data became stale

Entry is only allowed during COMPLETING state, when the
event is nearing completion and risk is reduced.

Key components:
- EventType: Types of market events
- LifecycleState: Event lifecycle states
- LifecycleEvent: Event with lifecycle tracking
- EventRegistry: Central registry for active events
"""

from .types import EventType, EventSeverity
from .lifecycle import (
    LifecycleState,
    LifecycleEvent,
    LifecycleTransition,
)
from .registry import EventRegistry

__all__ = [
    # Types
    'EventType',
    'EventSeverity',
    # Lifecycle
    'LifecycleState',
    'LifecycleEvent',
    'LifecycleTransition',
    # Registry
    'EventRegistry',
]
