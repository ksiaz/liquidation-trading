"""
HLP14: Event Lifecycle.

Provides lifecycle state management for market events.

Lifecycle States:
    DETECTED: Event preconditions met, event recognized
    TRIGGERED: Event has initiated (e.g., liquidation started)
    ACTIVE: Event is executing (cascade in progress)
    COMPLETING: Exhaustion signals appearing (safe to enter)
    COMPLETED: Event finished
    EXPIRED: Event data became stale (TTL exceeded)

Entry Rules:
    - Entry is ONLY allowed during COMPLETING state
    - COMPLETING indicates reduced risk (event nearly done)
    - All other states are observation-only

State Transitions:
    DETECTED -> TRIGGERED: Event initiates
    TRIGGERED -> ACTIVE: Event begins executing
    ACTIVE -> COMPLETING: Exhaustion signals detected
    COMPLETING -> COMPLETED: Event finishes
    * -> EXPIRED: TTL exceeded
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Tuple, Set

from .types import EventType, EventSeverity, get_event_info


class LifecycleState(Enum):
    """Event lifecycle states."""

    DETECTED = "detected"       # Preconditions met
    TRIGGERED = "triggered"     # Event initiated
    ACTIVE = "active"           # Event executing
    COMPLETING = "completing"   # Exhaustion signals
    COMPLETED = "completed"     # Event finished
    EXPIRED = "expired"         # Data stale


# Valid state transitions
VALID_TRANSITIONS: Dict[LifecycleState, Set[LifecycleState]] = {
    LifecycleState.DETECTED: {LifecycleState.TRIGGERED, LifecycleState.EXPIRED},
    LifecycleState.TRIGGERED: {LifecycleState.ACTIVE, LifecycleState.EXPIRED},
    LifecycleState.ACTIVE: {LifecycleState.COMPLETING, LifecycleState.EXPIRED},
    LifecycleState.COMPLETING: {LifecycleState.COMPLETED, LifecycleState.EXPIRED},
    LifecycleState.COMPLETED: set(),  # Terminal state
    LifecycleState.EXPIRED: set(),    # Terminal state
}


@dataclass
class LifecycleTransition:
    """Record of a lifecycle state transition."""

    from_state: LifecycleState
    to_state: LifecycleState
    timestamp: datetime
    reason: str
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class LifecycleEvent:
    """
    Market event with lifecycle state tracking.

    Tracks an event through its lifecycle from detection to completion,
    with metrics snapshots at each transition.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event (CASCADE, HUNT_FAILED, etc.)
        symbol: Trading symbol
        state: Current lifecycle state
        detected_at: When event was first detected
        triggered_at: When event was triggered (if reached)
        completed_at: When event completed (if reached)
        ttl_ms: Time to live in milliseconds
        metrics_history: Metrics at each state transition
    """

    event_id: str
    event_type: EventType
    symbol: str
    state: LifecycleState = LifecycleState.DETECTED
    detected_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    ttl_ms: int = 300_000  # 5 minutes default

    # Metrics at each transition
    metrics_history: List[Tuple[LifecycleState, datetime, Dict[str, Any]]] = field(
        default_factory=list
    )

    # Transition history
    transitions: List[LifecycleTransition] = field(default_factory=list)

    # Current metrics
    current_metrics: Dict[str, Any] = field(default_factory=dict)

    # Strategy association
    associated_strategy: Optional[str] = None
    mandate_id: Optional[str] = None

    def __post_init__(self):
        """Record initial state."""
        if not self.metrics_history:
            self.metrics_history.append((
                self.state,
                self.detected_at,
                self.current_metrics.copy(),
            ))

    @property
    def entry_window_open(self) -> bool:
        """Check if entry is allowed (only during COMPLETING)."""
        return self.state == LifecycleState.COMPLETING

    @property
    def is_active(self) -> bool:
        """Check if event is still active (not completed/expired)."""
        return self.state not in (LifecycleState.COMPLETED, LifecycleState.EXPIRED)

    @property
    def is_terminal(self) -> bool:
        """Check if event is in terminal state."""
        return self.state in (LifecycleState.COMPLETED, LifecycleState.EXPIRED)

    @property
    def age_ms(self) -> float:
        """Get event age in milliseconds."""
        return (datetime.now() - self.detected_at).total_seconds() * 1000

    @property
    def is_expired(self) -> bool:
        """Check if event has exceeded TTL."""
        return self.age_ms > self.ttl_ms

    @property
    def time_in_state_ms(self) -> float:
        """Get time in current state in milliseconds."""
        if self.transitions:
            last_transition = self.transitions[-1]
            return (datetime.now() - last_transition.timestamp).total_seconds() * 1000
        return self.age_ms

    @property
    def severity(self) -> EventSeverity:
        """Get event severity."""
        info = get_event_info(self.event_type)
        return info.get('severity', EventSeverity.MEDIUM)

    def can_transition_to(self, new_state: LifecycleState) -> bool:
        """Check if transition to new state is valid."""
        return new_state in VALID_TRANSITIONS.get(self.state, set())

    def transition_to(
        self,
        new_state: LifecycleState,
        reason: str = "",
        metrics: Dict[str, Any] = None,
        logger: logging.Logger = None,
    ) -> bool:
        """
        Transition to a new lifecycle state.

        Args:
            new_state: Target state
            reason: Why this transition is happening
            metrics: Metrics at transition time
            logger: Optional logger

        Returns:
            True if transition succeeded, False if invalid
        """
        if not self.can_transition_to(new_state):
            if logger:
                logger.warning(
                    f"Invalid transition: {self.state.value} -> {new_state.value} "
                    f"for event {self.event_id}"
                )
            return False

        old_state = self.state
        now = datetime.now()

        # Record transition
        transition = LifecycleTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=now,
            reason=reason,
            metrics=metrics or {},
        )
        self.transitions.append(transition)

        # Update state
        self.state = new_state

        # Record metrics snapshot
        self.metrics_history.append((new_state, now, (metrics or {}).copy()))
        if metrics:
            self.current_metrics.update(metrics)

        # Update timestamps
        if new_state == LifecycleState.TRIGGERED:
            self.triggered_at = now
        elif new_state == LifecycleState.COMPLETED:
            self.completed_at = now

        if logger:
            logger.info(
                f"Event {self.event_id} transitioned: "
                f"{old_state.value} -> {new_state.value} ({reason})"
            )

        return True

    def check_expiration(self, logger: logging.Logger = None) -> bool:
        """
        Check if event should expire due to TTL.

        Returns:
            True if event was expired, False otherwise
        """
        if self.is_terminal:
            return False

        if self.is_expired:
            self.transition_to(
                LifecycleState.EXPIRED,
                reason=f"TTL exceeded ({self.ttl_ms}ms)",
                logger=logger,
            )
            return True

        return False

    def get_metrics_at_state(self, state: LifecycleState) -> Optional[Dict[str, Any]]:
        """Get metrics snapshot when entering a state."""
        for s, t, m in self.metrics_history:
            if s == state:
                return m
        return None

    def get_duration_in_state(self, state: LifecycleState) -> Optional[float]:
        """Get time spent in a state (in seconds)."""
        enter_time = None
        exit_time = None

        for transition in self.transitions:
            if transition.to_state == state:
                enter_time = transition.timestamp
            elif transition.from_state == state:
                exit_time = transition.timestamp

        if enter_time is None:
            return None

        if exit_time is None:
            if self.state == state:
                exit_time = datetime.now()
            else:
                return None

        return (exit_time - enter_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'symbol': self.symbol,
            'state': self.state.value,
            'detected_at': self.detected_at.isoformat(),
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'age_ms': self.age_ms,
            'entry_window_open': self.entry_window_open,
            'is_expired': self.is_expired,
            'severity': self.severity.name,
            'current_metrics': self.current_metrics,
            'associated_strategy': self.associated_strategy,
        }

    def __repr__(self) -> str:
        return (
            f"LifecycleEvent({self.event_id}, {self.event_type.value}, "
            f"{self.state.value}, age={self.age_ms:.0f}ms)"
        )
