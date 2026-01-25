"""
HLP16: Degradation Mode Manager.

Manages graceful degradation when system components fail.

Degradation levels:
1. NORMAL - Full functionality
2. REDUCED - Limit new positions, wider stops
3. EMERGENCY - Close-only mode
4. SHUTDOWN - No trading, orderly exit
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Set
from enum import Enum, auto
from threading import Lock


class DegradationLevel(Enum):
    """System degradation levels."""
    NORMAL = auto()  # Full operation
    REDUCED = auto()  # Limited new positions
    EMERGENCY = auto()  # Close-only
    SHUTDOWN = auto()  # Orderly exit


class DegradationTrigger(Enum):
    """Reasons for degradation."""
    CIRCUIT_BREAKER_TRIPPED = auto()
    DATA_QUALITY_POOR = auto()
    COMPONENT_UNHEALTHY = auto()
    HIGH_DRAWDOWN = auto()
    EXCESSIVE_ERRORS = auto()
    EXCHANGE_ISSUES = auto()
    MANUAL_INTERVENTION = auto()
    RESOURCE_EXHAUSTION = auto()


@dataclass
class DegradationConfig:
    """Configuration for degradation handling."""
    # Thresholds for automatic degradation
    error_rate_reduced: float = 0.10  # 10% error rate -> REDUCED
    error_rate_emergency: float = 0.25  # 25% error rate -> EMERGENCY
    error_rate_shutdown: float = 0.50  # 50% error rate -> SHUTDOWN

    # Recovery requirements
    min_recovery_time_ms: int = 60_000  # 1 minute minimum at each level
    require_manual_reset: bool = True  # Require manual reset from SHUTDOWN

    # Position limits by level
    max_positions_reduced: int = 2
    max_positions_emergency: int = 0  # No new positions

    # Size adjustments
    size_multiplier_reduced: float = 0.5  # Half size
    size_multiplier_emergency: float = 0.0  # No new positions


@dataclass
class DegradationEvent:
    """Record of degradation event."""
    timestamp: int  # nanoseconds
    old_level: DegradationLevel
    new_level: DegradationLevel
    trigger: DegradationTrigger
    reason: str
    details: Dict = field(default_factory=dict)


@dataclass
class DegradationState:
    """Current degradation state."""
    level: DegradationLevel
    since: int  # timestamp when entered
    triggers: Set[DegradationTrigger]
    can_open_positions: bool
    max_new_positions: int
    size_multiplier: float


class DegradationManager:
    """
    Manages system degradation levels.

    Monitors conditions and escalates/deescalates degradation level.
    Controls what operations are allowed at each level.
    """

    def __init__(
        self,
        config: DegradationConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or DegradationConfig()
        self._logger = logger or logging.getLogger(__name__)

        self._level = DegradationLevel.NORMAL
        self._level_since: int = 0
        self._active_triggers: Set[DegradationTrigger] = set()
        self._events: List[DegradationEvent] = []

        # Callbacks for level changes
        self._callbacks: List[Callable[[DegradationLevel, DegradationLevel], None]] = []

        self._lock = Lock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    @property
    def level(self) -> DegradationLevel:
        """Get current degradation level."""
        return self._level

    @property
    def state(self) -> DegradationState:
        """Get current degradation state with details."""
        with self._lock:
            return DegradationState(
                level=self._level,
                since=self._level_since,
                triggers=set(self._active_triggers),
                can_open_positions=self._can_open_positions(),
                max_new_positions=self._max_new_positions(),
                size_multiplier=self._size_multiplier()
            )

    def _can_open_positions(self) -> bool:
        """Check if new positions are allowed."""
        return self._level in (DegradationLevel.NORMAL, DegradationLevel.REDUCED)

    def _max_new_positions(self) -> int:
        """Get maximum new positions allowed."""
        if self._level == DegradationLevel.NORMAL:
            return 999  # Unlimited
        elif self._level == DegradationLevel.REDUCED:
            return self._config.max_positions_reduced
        else:
            return self._config.max_positions_emergency

    def _size_multiplier(self) -> float:
        """Get position size multiplier."""
        if self._level == DegradationLevel.NORMAL:
            return 1.0
        elif self._level == DegradationLevel.REDUCED:
            return self._config.size_multiplier_reduced
        else:
            return self._config.size_multiplier_emergency

    def add_trigger(self, trigger: DegradationTrigger, reason: str, details: Dict = None):
        """Add a degradation trigger."""
        ts = self._now_ns()

        with self._lock:
            if trigger in self._active_triggers:
                return  # Already active

            self._active_triggers.add(trigger)
            self._logger.warning(f"Degradation trigger added: {trigger.name} - {reason}")

            # Recalculate level
            self._recalculate_level(ts, reason, details)

    def remove_trigger(self, trigger: DegradationTrigger, reason: str = "Condition cleared"):
        """Remove a degradation trigger."""
        ts = self._now_ns()

        with self._lock:
            if trigger not in self._active_triggers:
                return

            self._active_triggers.discard(trigger)
            self._logger.info(f"Degradation trigger removed: {trigger.name} - {reason}")

            # Recalculate level
            self._recalculate_level(ts, reason)

    def _recalculate_level(self, ts: int, reason: str, details: Dict = None):
        """Recalculate degradation level based on active triggers."""
        old_level = self._level

        # Determine level based on triggers
        if not self._active_triggers:
            new_level = DegradationLevel.NORMAL
        elif DegradationTrigger.MANUAL_INTERVENTION in self._active_triggers:
            # Manual intervention can be at any level
            new_level = self._level  # Keep current
        elif any(t in self._active_triggers for t in [
            DegradationTrigger.EXCHANGE_ISSUES,
            DegradationTrigger.RESOURCE_EXHAUSTION
        ]):
            new_level = DegradationLevel.SHUTDOWN
        elif any(t in self._active_triggers for t in [
            DegradationTrigger.CIRCUIT_BREAKER_TRIPPED,
            DegradationTrigger.HIGH_DRAWDOWN
        ]):
            new_level = DegradationLevel.EMERGENCY
        else:
            new_level = DegradationLevel.REDUCED

        # Apply transition
        if new_level != old_level:
            self._transition_level(old_level, new_level, ts, reason, details)

    def _transition_level(
        self,
        old_level: DegradationLevel,
        new_level: DegradationLevel,
        ts: int,
        reason: str,
        details: Dict = None
    ):
        """Transition to a new degradation level."""
        # Check minimum time at current level
        time_at_level_ms = (ts - self._level_since) / 1_000_000
        if time_at_level_ms < self._config.min_recovery_time_ms:
            # Can escalate immediately, but not deescalate
            if new_level.value < old_level.value:
                return

        # Check if manual reset required
        if old_level == DegradationLevel.SHUTDOWN:
            if self._config.require_manual_reset:
                self._logger.warning("Manual reset required to exit SHUTDOWN")
                return

        self._level = new_level
        self._level_since = ts

        # Record event
        trigger = (
            list(self._active_triggers)[0]
            if self._active_triggers
            else DegradationTrigger.MANUAL_INTERVENTION
        )

        event = DegradationEvent(
            timestamp=ts,
            old_level=old_level,
            new_level=new_level,
            trigger=trigger,
            reason=reason,
            details=details or {}
        )
        self._events.append(event)

        # Log transition
        self._logger.warning(
            f"DEGRADATION: {old_level.name} -> {new_level.name}: {reason}"
        )

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(old_level, new_level)
            except Exception as e:
                self._logger.error(f"Callback error: {e}")

    def set_level(
        self,
        level: DegradationLevel,
        reason: str = "Manual override"
    ):
        """Manually set degradation level."""
        ts = self._now_ns()

        with self._lock:
            old_level = self._level

            if level == DegradationLevel.SHUTDOWN:
                self._active_triggers.add(DegradationTrigger.MANUAL_INTERVENTION)

            self._transition_level(old_level, level, ts, reason)

    def reset(self, force: bool = False):
        """Reset to normal operation."""
        ts = self._now_ns()

        with self._lock:
            if self._level == DegradationLevel.SHUTDOWN:
                if not force and self._config.require_manual_reset:
                    self._logger.warning("Use force=True to reset from SHUTDOWN")
                    return False

            self._active_triggers.clear()
            old_level = self._level
            self._level = DegradationLevel.NORMAL
            self._level_since = ts

            if old_level != DegradationLevel.NORMAL:
                event = DegradationEvent(
                    timestamp=ts,
                    old_level=old_level,
                    new_level=DegradationLevel.NORMAL,
                    trigger=DegradationTrigger.MANUAL_INTERVENTION,
                    reason="Manual reset"
                )
                self._events.append(event)
                self._logger.info("Degradation reset to NORMAL")

            return True

    def check_error_rate(self, error_rate: float):
        """Check error rate and adjust degradation."""
        if error_rate >= self._config.error_rate_shutdown:
            self.add_trigger(
                DegradationTrigger.EXCESSIVE_ERRORS,
                f"Error rate {error_rate*100:.1f}% exceeds shutdown threshold"
            )
        elif error_rate >= self._config.error_rate_emergency:
            self.add_trigger(
                DegradationTrigger.EXCESSIVE_ERRORS,
                f"Error rate {error_rate*100:.1f}% exceeds emergency threshold"
            )
        elif error_rate >= self._config.error_rate_reduced:
            self.add_trigger(
                DegradationTrigger.EXCESSIVE_ERRORS,
                f"Error rate {error_rate*100:.1f}% exceeds reduced threshold"
            )
        else:
            self.remove_trigger(
                DegradationTrigger.EXCESSIVE_ERRORS,
                f"Error rate {error_rate*100:.1f}% below threshold"
            )

    def register_callback(
        self,
        callback: Callable[[DegradationLevel, DegradationLevel], None]
    ):
        """Register callback for level changes."""
        with self._lock:
            self._callbacks.append(callback)

    def is_trading_allowed(self) -> bool:
        """Check if any trading is allowed."""
        return self._level != DegradationLevel.SHUTDOWN

    def is_opening_allowed(self) -> bool:
        """Check if opening new positions is allowed."""
        return self._level in (DegradationLevel.NORMAL, DegradationLevel.REDUCED)

    def get_events(self, limit: int = 100) -> List[DegradationEvent]:
        """Get recent degradation events."""
        with self._lock:
            return list(self._events[-limit:])

    def get_summary(self) -> Dict:
        """Get degradation summary."""
        with self._lock:
            ts = self._now_ns()
            return {
                'level': self._level.name,
                'since': self._level_since,
                'duration_ms': (ts - self._level_since) / 1_000_000,
                'active_triggers': [t.name for t in self._active_triggers],
                'can_trade': self.is_trading_allowed(),
                'can_open': self.is_opening_allowed(),
                'size_multiplier': self._size_multiplier(),
                'event_count': len(self._events)
            }
