"""
Catastrophe Handler - State machine for failure handling.

Manages system state during exchange failures and black swan events.
Provides deterministic state transitions based on failure events.

Constitutional: State transitions are factual. No health claims.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Callable
from threading import RLock


class CatastropheState(Enum):
    """
    System catastrophe states.

    NORMAL: All operations allowed
    DEGRADED: Some functions impaired, entries blocked
    CRITICAL: Only exits allowed
    HALTED: No operations permitted
    """
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    HALTED = "HALTED"


class FailureType(Enum):
    """Enumerated failure types for consistent handling."""
    WEBSOCKET_DISCONNECT = "websocket_disconnect"
    API_RATE_LIMIT = "api_rate_limit"
    ORDER_REJECTION_STORM = "order_rejection_storm"
    POSITION_MISMATCH = "position_mismatch"
    FUNDING_SPIKE = "funding_spike"
    ORDERBOOK_VANISH = "orderbook_vanish"
    EXCHANGE_HALT = "exchange_halt"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CatastropheEvent:
    """
    Factual record of a catastrophe event.

    No interpretation of severity or impact - just facts.
    """
    ts_ns: int
    event_type: str
    details: str
    previous_state: CatastropheState
    new_state: CatastropheState


@dataclass
class FailureCounter:
    """Tracks failure counts within time windows."""
    failure_type: str
    count: int = 0
    first_ts_ns: int = 0
    last_ts_ns: int = 0
    window_ns: int = 60 * 1_000_000_000  # 60 second window

    def increment(self, ts_ns: int) -> int:
        """Increment counter, reset if outside window."""
        if ts_ns - self.first_ts_ns > self.window_ns:
            # Reset window
            self.count = 1
            self.first_ts_ns = ts_ns
        else:
            self.count += 1
        self.last_ts_ns = ts_ns
        return self.count


# State transition rules: (current_state, failure_type) -> new_state
STATE_TRANSITIONS: Dict[tuple, CatastropheState] = {
    # From NORMAL
    (CatastropheState.NORMAL, FailureType.WEBSOCKET_DISCONNECT): CatastropheState.DEGRADED,
    (CatastropheState.NORMAL, FailureType.API_RATE_LIMIT): CatastropheState.DEGRADED,
    (CatastropheState.NORMAL, FailureType.ORDER_REJECTION_STORM): CatastropheState.DEGRADED,
    (CatastropheState.NORMAL, FailureType.POSITION_MISMATCH): CatastropheState.CRITICAL,
    (CatastropheState.NORMAL, FailureType.FUNDING_SPIKE): CatastropheState.DEGRADED,
    (CatastropheState.NORMAL, FailureType.ORDERBOOK_VANISH): CatastropheState.CRITICAL,
    (CatastropheState.NORMAL, FailureType.EXCHANGE_HALT): CatastropheState.HALTED,

    # From DEGRADED
    (CatastropheState.DEGRADED, FailureType.WEBSOCKET_DISCONNECT): CatastropheState.CRITICAL,
    (CatastropheState.DEGRADED, FailureType.API_RATE_LIMIT): CatastropheState.DEGRADED,
    (CatastropheState.DEGRADED, FailureType.ORDER_REJECTION_STORM): CatastropheState.CRITICAL,
    (CatastropheState.DEGRADED, FailureType.POSITION_MISMATCH): CatastropheState.HALTED,
    (CatastropheState.DEGRADED, FailureType.FUNDING_SPIKE): CatastropheState.CRITICAL,
    (CatastropheState.DEGRADED, FailureType.ORDERBOOK_VANISH): CatastropheState.HALTED,
    (CatastropheState.DEGRADED, FailureType.EXCHANGE_HALT): CatastropheState.HALTED,

    # From CRITICAL
    (CatastropheState.CRITICAL, FailureType.WEBSOCKET_DISCONNECT): CatastropheState.HALTED,
    (CatastropheState.CRITICAL, FailureType.API_RATE_LIMIT): CatastropheState.CRITICAL,
    (CatastropheState.CRITICAL, FailureType.ORDER_REJECTION_STORM): CatastropheState.HALTED,
    (CatastropheState.CRITICAL, FailureType.POSITION_MISMATCH): CatastropheState.HALTED,
    (CatastropheState.CRITICAL, FailureType.FUNDING_SPIKE): CatastropheState.CRITICAL,
    (CatastropheState.CRITICAL, FailureType.ORDERBOOK_VANISH): CatastropheState.HALTED,
    (CatastropheState.CRITICAL, FailureType.EXCHANGE_HALT): CatastropheState.HALTED,

    # From HALTED - stays HALTED until explicit recovery
    (CatastropheState.HALTED, FailureType.WEBSOCKET_DISCONNECT): CatastropheState.HALTED,
    (CatastropheState.HALTED, FailureType.API_RATE_LIMIT): CatastropheState.HALTED,
    (CatastropheState.HALTED, FailureType.ORDER_REJECTION_STORM): CatastropheState.HALTED,
    (CatastropheState.HALTED, FailureType.POSITION_MISMATCH): CatastropheState.HALTED,
    (CatastropheState.HALTED, FailureType.FUNDING_SPIKE): CatastropheState.HALTED,
    (CatastropheState.HALTED, FailureType.ORDERBOOK_VANISH): CatastropheState.HALTED,
    (CatastropheState.HALTED, FailureType.EXCHANGE_HALT): CatastropheState.HALTED,
}


class CatastropheHandler:
    """
    Manages system state during failures.

    State machine with deterministic transitions.
    Does NOT make claims about system health.
    Does NOT automatically close positions.
    """

    # Thresholds for automatic degradation
    REJECTION_STORM_THRESHOLD = 5  # rejections in 10 seconds
    REJECTION_STORM_WINDOW_NS = 10 * 1_000_000_000

    RATE_LIMIT_THRESHOLD = 3  # rate limits in 60 seconds
    RATE_LIMIT_WINDOW_NS = 60 * 1_000_000_000

    def __init__(
        self,
        logger: logging.Logger = None,
        on_state_change: Callable[[CatastropheState, CatastropheState], None] = None,
    ):
        """
        Initialize catastrophe handler.

        Args:
            logger: Logger instance
            on_state_change: Callback for state changes (old_state, new_state)
        """
        self._state = CatastropheState.NORMAL
        self._events: List[CatastropheEvent] = []
        self._lock = RLock()
        self._logger = logger or logging.getLogger(__name__)
        self._on_state_change = on_state_change

        # Failure counters for windowed tracking
        self._failure_counters: Dict[str, FailureCounter] = {}

        # Recovery state
        self._recovery_started_ts_ns: Optional[int] = None
        self._recovery_conditions_met: Dict[str, bool] = {}

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    @property
    def state(self) -> CatastropheState:
        """Get current catastrophe state."""
        with self._lock:
            return self._state

    @property
    def events(self) -> List[CatastropheEvent]:
        """Get list of catastrophe events."""
        with self._lock:
            return list(self._events)

    def _get_failure_counter(self, failure_type: str, window_ns: int) -> FailureCounter:
        """Get or create failure counter."""
        if failure_type not in self._failure_counters:
            self._failure_counters[failure_type] = FailureCounter(
                failure_type=failure_type,
                window_ns=window_ns,
            )
        return self._failure_counters[failure_type]

    def report_failure(
        self,
        failure_type: FailureType,
        details: str = "",
        ts_ns: int = None,
    ) -> CatastropheState:
        """
        Report a failure event.

        Args:
            failure_type: Type of failure
            details: Additional details
            ts_ns: Timestamp (uses current time if None)

        Returns:
            New catastrophe state
        """
        if ts_ns is None:
            ts_ns = self._now_ns()

        with self._lock:
            previous_state = self._state

            # Look up state transition
            transition_key = (self._state, failure_type)
            if transition_key in STATE_TRANSITIONS:
                new_state = STATE_TRANSITIONS[transition_key]
            else:
                # Unknown failure type - treat as unknown
                unknown_key = (self._state, FailureType.UNKNOWN)
                new_state = STATE_TRANSITIONS.get(unknown_key, self._state)

            # Record event
            event = CatastropheEvent(
                ts_ns=ts_ns,
                event_type=failure_type.value,
                details=details,
                previous_state=previous_state,
                new_state=new_state,
            )
            self._events.append(event)

            # Keep only recent events (last 100)
            if len(self._events) > 100:
                self._events = self._events[-100:]

            # Update state
            if new_state != previous_state:
                self._state = new_state
                self._logger.warning(
                    f"Catastrophe state transition: {previous_state.value} -> {new_state.value} "
                    f"(failure_type={failure_type.value})"
                )

                if self._on_state_change:
                    try:
                        self._on_state_change(previous_state, new_state)
                    except Exception as e:
                        self._logger.error(f"State change callback error: {e}")

            return self._state

    def report_rejection(self, details: str = "", ts_ns: int = None) -> CatastropheState:
        """Report an order rejection."""
        if ts_ns is None:
            ts_ns = self._now_ns()

        counter = self._get_failure_counter(
            "rejection",
            self.REJECTION_STORM_WINDOW_NS,
        )
        count = counter.increment(ts_ns)

        if count >= self.REJECTION_STORM_THRESHOLD:
            return self.report_failure(
                FailureType.ORDER_REJECTION_STORM,
                f"Rejection storm: {count} rejections in window. {details}",
                ts_ns,
            )

        return self._state

    def report_rate_limit(self, details: str = "", ts_ns: int = None) -> CatastropheState:
        """Report an API rate limit."""
        if ts_ns is None:
            ts_ns = self._now_ns()

        counter = self._get_failure_counter(
            "rate_limit",
            self.RATE_LIMIT_WINDOW_NS,
        )
        count = counter.increment(ts_ns)

        if count >= self.RATE_LIMIT_THRESHOLD:
            return self.report_failure(
                FailureType.API_RATE_LIMIT,
                f"Rate limit storm: {count} limits in window. {details}",
                ts_ns,
            )

        return self._state

    def can_enter_position(self) -> bool:
        """
        Check if position entry is allowed.

        Returns True only in NORMAL state.
        """
        return self._state == CatastropheState.NORMAL

    def can_exit_position(self) -> bool:
        """
        Check if position exit is allowed.

        Returns True in NORMAL, DEGRADED, or CRITICAL.
        """
        return self._state != CatastropheState.HALTED

    def can_submit_order(self) -> bool:
        """
        Check if any order submission is allowed.

        Returns True in NORMAL, DEGRADED, or CRITICAL.
        Exits are still allowed in DEGRADED/CRITICAL.
        """
        return self._state != CatastropheState.HALTED

    def attempt_recovery(
        self,
        conditions_met: Dict[str, bool] = None,
        ts_ns: int = None,
    ) -> bool:
        """
        Attempt to recover to NORMAL state.

        Recovery requires:
        - All conditions_met to be True
        - Current state to be DEGRADED or CRITICAL
        - HALTED requires explicit reset with operator confirmation

        Args:
            conditions_met: Dict of condition name -> satisfied
            ts_ns: Timestamp

        Returns:
            True if recovered to NORMAL
        """
        if ts_ns is None:
            ts_ns = self._now_ns()

        with self._lock:
            # HALTED cannot auto-recover
            if self._state == CatastropheState.HALTED:
                return False

            # Already NORMAL
            if self._state == CatastropheState.NORMAL:
                return True

            # Check all conditions
            if conditions_met:
                self._recovery_conditions_met.update(conditions_met)

            all_conditions_met = all(self._recovery_conditions_met.values())
            if not all_conditions_met:
                return False

            # Record recovery event
            previous_state = self._state
            self._state = CatastropheState.NORMAL

            event = CatastropheEvent(
                ts_ns=ts_ns,
                event_type="recovery",
                details=f"Recovery from {previous_state.value}",
                previous_state=previous_state,
                new_state=CatastropheState.NORMAL,
            )
            self._events.append(event)

            # Clear recovery state
            self._recovery_conditions_met.clear()
            self._failure_counters.clear()

            self._logger.info(
                f"Catastrophe recovery: {previous_state.value} -> NORMAL"
            )

            if self._on_state_change:
                try:
                    self._on_state_change(previous_state, CatastropheState.NORMAL)
                except Exception as e:
                    self._logger.error(f"State change callback error: {e}")

            return True

    def force_reset(
        self,
        operator_confirmation: str,
        ts_ns: int = None,
    ) -> bool:
        """
        Force reset from HALTED state.

        Requires explicit operator confirmation.

        Args:
            operator_confirmation: Typed confirmation phrase
            ts_ns: Timestamp

        Returns:
            True if reset successful
        """
        REQUIRED_PHRASE = "CONFIRM RESET"

        if operator_confirmation != REQUIRED_PHRASE:
            self._logger.warning(
                f"Invalid reset confirmation: expected '{REQUIRED_PHRASE}'"
            )
            return False

        if ts_ns is None:
            ts_ns = self._now_ns()

        with self._lock:
            previous_state = self._state
            self._state = CatastropheState.NORMAL

            event = CatastropheEvent(
                ts_ns=ts_ns,
                event_type="force_reset",
                details=f"Operator force reset from {previous_state.value}",
                previous_state=previous_state,
                new_state=CatastropheState.NORMAL,
            )
            self._events.append(event)

            # Clear all state
            self._recovery_conditions_met.clear()
            self._failure_counters.clear()

            self._logger.warning(
                f"OPERATOR FORCE RESET: {previous_state.value} -> NORMAL"
            )

            if self._on_state_change:
                try:
                    self._on_state_change(previous_state, CatastropheState.NORMAL)
                except Exception as e:
                    self._logger.error(f"State change callback error: {e}")

            return True

    def get_recent_events(self, limit: int = 10) -> List[CatastropheEvent]:
        """Get recent catastrophe events."""
        with self._lock:
            return list(self._events[-limit:])

    def get_state_summary(self) -> Dict:
        """
        Get factual state summary.

        Returns dict with state facts only, no interpretation.
        """
        with self._lock:
            return {
                "state": self._state.value,
                "event_count": len(self._events),
                "last_event_ts_ns": self._events[-1].ts_ns if self._events else None,
                "last_event_type": self._events[-1].event_type if self._events else None,
                "failure_counters": {
                    k: {"count": v.count, "window_ns": v.window_ns}
                    for k, v in self._failure_counters.items()
                },
                "recovery_conditions": dict(self._recovery_conditions_met),
            }
