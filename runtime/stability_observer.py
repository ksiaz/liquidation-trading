"""Phase C: Stability Observer - Passive Live Observation.

Observes mandate behavior under live market conditions to verify behavioral stability.
Per DOWNSTREAM_ACTIVATION_SPEC.md Phase C requirements.

INVARIANT: This module is PURELY OBSERVATIONAL.
           It must NEVER affect control flow or business logic.
           No feedback loops, no optimization, no scoring.

Detects:
- Mandate storms (excessive mandates per time window)
- Oscillations (rapid ENTRY/EXIT cycling)
- Deadlocks (no mandates despite active observations)
- State corruption (invalid mandate types, missing fields)

Usage:
    from runtime.stability_observer import stability_observer

    # Record mandate emission
    stability_observer.record_mandate(mandate)

    # Record arbitration result
    stability_observer.record_action(action, symbol)

    # Check stability (call periodically)
    status = stability_observer.get_stability_status()
"""

import time
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Deque
from collections import defaultdict, deque
from decimal import Decimal

from runtime.arbitration.types import Mandate, MandateType, Action, ActionType


class StabilityIssue(Enum):
    """Machine-readable stability issue codes."""
    # Mandate storms
    STORM_EXCESSIVE_MANDATES = "STORM_EXCESSIVE_MANDATES"  # >N mandates in window
    STORM_BURST = "STORM_BURST"  # Sudden spike in mandate rate

    # Oscillations
    OSCILLATION_ENTRY_EXIT_CYCLE = "OSCILLATION_ENTRY_EXIT_CYCLE"  # Rapid ENTRY → EXIT
    OSCILLATION_DIRECTION_FLIP = "OSCILLATION_DIRECTION_FLIP"  # LONG → SHORT rapid flip

    # Deadlocks
    DEADLOCK_NO_MANDATES = "DEADLOCK_NO_MANDATES"  # No mandates for extended period
    DEADLOCK_BLOCK_ONLY = "DEADLOCK_BLOCK_ONLY"  # Only BLOCK mandates emitted

    # State corruption
    CORRUPTION_INVALID_TYPE = "CORRUPTION_INVALID_TYPE"  # Invalid mandate type
    CORRUPTION_MISSING_FIELD = "CORRUPTION_MISSING_FIELD"  # Required field missing
    CORRUPTION_SYMBOL_MISMATCH = "CORRUPTION_SYMBOL_MISMATCH"  # Symbol inconsistency


@dataclass
class StabilityEvent:
    """Single stability event (issue detected)."""
    timestamp: float
    issue: StabilityIssue
    symbol: Optional[str]
    severity: str  # "INFO", "WARNING", "CRITICAL"
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.timestamp,
            "issue": self.issue.value,
            "symbol": self.symbol,
            "severity": self.severity,
            "details": self.details
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class MandateRecord:
    """Record of a single mandate emission."""
    timestamp: float
    symbol: str
    mandate_type: MandateType
    authority: float
    direction: Optional[str]
    strategy_id: Optional[str]


@dataclass
class ActionRecord:
    """Record of a single action (arbitration result)."""
    timestamp: float
    symbol: str
    action_type: ActionType
    strategy_id: Optional[str]


@dataclass
class SymbolStats:
    """Statistics for a single symbol."""
    # Counts
    total_mandates: int = 0
    by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Timing
    last_mandate_time: Optional[float] = None
    last_action_time: Optional[float] = None

    # Oscillation detection
    last_entry_time: Optional[float] = None
    last_exit_time: Optional[float] = None
    last_direction: Optional[str] = None
    direction_flips: int = 0
    entry_exit_cycles: int = 0


class StabilityObserver:
    """Passive observer for mandate behavioral stability.

    INVARIANT: Observation only - no control flow modification.
    """

    # Detection thresholds
    STORM_WINDOW_SEC = 60.0  # Time window for storm detection
    STORM_THRESHOLD = 50  # Max mandates per window before storm
    STORM_BURST_MULTIPLIER = 5.0  # Spike detection (N× baseline rate)

    OSCILLATION_WINDOW_SEC = 30.0  # Time window for oscillation detection
    OSCILLATION_CYCLE_THRESHOLD = 3  # Max ENTRY→EXIT cycles before flagging
    OSCILLATION_FLIP_THRESHOLD = 3  # Max direction flips before flagging

    DEADLOCK_WINDOW_SEC = 300.0  # Time without mandates = deadlock

    def __init__(
        self,
        enabled: bool = True,
        max_history: int = 10000,
        max_issues: int = 1000
    ):
        """Initialize stability observer.

        Args:
            enabled: Whether observation is enabled
            max_history: Max mandate/action records to keep
            max_issues: Max stability issues to keep
        """
        self._enabled = enabled
        self._max_history = max_history
        self._max_issues = max_issues

        # Records
        self._mandates: Deque[MandateRecord] = deque(maxlen=max_history)
        self._actions: Deque[ActionRecord] = deque(maxlen=max_history)
        self._issues: List[StabilityEvent] = []

        # Per-symbol statistics
        self._symbol_stats: Dict[str, SymbolStats] = defaultdict(SymbolStats)

        # Global counters
        self._total_mandates = 0
        self._total_actions = 0
        self._start_time = time.time()

        # Rate tracking (for burst detection)
        self._recent_mandate_times: Deque[float] = deque(maxlen=1000)

    def record_mandate(self, mandate: Mandate) -> None:
        """Record a mandate emission.

        Args:
            mandate: The mandate that was emitted
        """
        if not self._enabled:
            return

        now = time.time()

        # Validate mandate (corruption detection)
        self._check_mandate_validity(mandate, now)

        # Record
        record = MandateRecord(
            timestamp=now,
            symbol=mandate.symbol,
            mandate_type=mandate.type,
            authority=mandate.authority,
            direction=mandate.direction,
            strategy_id=mandate.strategy_id
        )
        self._mandates.append(record)
        self._recent_mandate_times.append(now)
        self._total_mandates += 1

        # Update symbol stats
        stats = self._symbol_stats[mandate.symbol]
        stats.total_mandates += 1
        stats.by_type[mandate.type.name] += 1
        stats.last_mandate_time = now

        # Track ENTRY/EXIT for oscillation detection
        if mandate.type == MandateType.ENTRY:
            # Check for rapid cycle (EXIT followed by ENTRY)
            if stats.last_exit_time and (now - stats.last_exit_time) < self.OSCILLATION_WINDOW_SEC:
                stats.entry_exit_cycles += 1
                if stats.entry_exit_cycles >= self.OSCILLATION_CYCLE_THRESHOLD:
                    self._record_issue(
                        StabilityIssue.OSCILLATION_ENTRY_EXIT_CYCLE,
                        mandate.symbol,
                        "WARNING",
                        {"cycles": stats.entry_exit_cycles, "window_sec": self.OSCILLATION_WINDOW_SEC}
                    )
            stats.last_entry_time = now

            # Track direction flips
            if mandate.direction and stats.last_direction:
                if mandate.direction != stats.last_direction:
                    stats.direction_flips += 1
                    if stats.direction_flips >= self.OSCILLATION_FLIP_THRESHOLD:
                        self._record_issue(
                            StabilityIssue.OSCILLATION_DIRECTION_FLIP,
                            mandate.symbol,
                            "WARNING",
                            {
                                "flips": stats.direction_flips,
                                "from": stats.last_direction,
                                "to": mandate.direction
                            }
                        )
            if mandate.direction:
                stats.last_direction = mandate.direction

        elif mandate.type == MandateType.EXIT:
            stats.last_exit_time = now

        # Storm detection
        self._check_storm(mandate.symbol, now)

    def record_action(self, action: Action, symbol: str) -> None:
        """Record an arbitration result.

        Args:
            action: The action produced by arbitration
            symbol: Symbol the action applies to
        """
        if not self._enabled:
            return

        now = time.time()

        record = ActionRecord(
            timestamp=now,
            symbol=symbol,
            action_type=action.type,
            strategy_id=action.strategy_id
        )
        self._actions.append(record)
        self._total_actions += 1

        # Update symbol stats
        stats = self._symbol_stats[symbol]
        stats.last_action_time = now

    def check_deadlock(self, symbol: str) -> bool:
        """Check if symbol is in deadlock state.

        Args:
            symbol: Symbol to check

        Returns:
            True if deadlock detected
        """
        if not self._enabled:
            return False

        now = time.time()
        stats = self._symbol_stats.get(symbol)

        if stats is None:
            return False

        if stats.last_mandate_time is None:
            return False

        time_since_mandate = now - stats.last_mandate_time
        if time_since_mandate > self.DEADLOCK_WINDOW_SEC:
            self._record_issue(
                StabilityIssue.DEADLOCK_NO_MANDATES,
                symbol,
                "WARNING",
                {"time_since_last_mandate_sec": time_since_mandate}
            )
            return True

        return False

    def get_stability_status(self) -> Dict[str, Any]:
        """Get overall stability status.

        Returns:
            Structured status report
        """
        now = time.time()
        runtime = now - self._start_time

        # Count recent issues by severity
        recent_issues = [i for i in self._issues if (now - i.timestamp) < 300.0]
        by_severity = defaultdict(int)
        for issue in recent_issues:
            by_severity[issue.severity] += 1

        # Determine overall status
        if by_severity.get("CRITICAL", 0) > 0:
            overall_status = "CRITICAL"
        elif by_severity.get("WARNING", 0) > 3:
            overall_status = "DEGRADED"
        elif by_severity.get("WARNING", 0) > 0:
            overall_status = "CAUTION"
        else:
            overall_status = "STABLE"

        # Calculate rates
        mandate_rate = self._total_mandates / runtime if runtime > 0 else 0
        action_rate = self._total_actions / runtime if runtime > 0 else 0

        return {
            "status": overall_status,
            "runtime_sec": runtime,
            "total_mandates": self._total_mandates,
            "total_actions": self._total_actions,
            "mandate_rate_per_sec": round(mandate_rate, 3),
            "action_rate_per_sec": round(action_rate, 3),
            "recent_issues": {
                "INFO": by_severity.get("INFO", 0),
                "WARNING": by_severity.get("WARNING", 0),
                "CRITICAL": by_severity.get("CRITICAL", 0)
            },
            "symbols_active": len(self._symbol_stats),
            "issues_total": len(self._issues)
        }

    def get_symbol_status(self, symbol: str) -> Dict[str, Any]:
        """Get stability status for a specific symbol.

        Args:
            symbol: Symbol to check

        Returns:
            Symbol-specific status
        """
        stats = self._symbol_stats.get(symbol)
        if stats is None:
            return {"symbol": symbol, "status": "NO_DATA"}

        now = time.time()

        # Check for issues
        issues = []
        if stats.entry_exit_cycles >= self.OSCILLATION_CYCLE_THRESHOLD:
            issues.append("OSCILLATION_CYCLES")
        if stats.direction_flips >= self.OSCILLATION_FLIP_THRESHOLD:
            issues.append("DIRECTION_FLIPS")

        time_since_mandate = None
        if stats.last_mandate_time:
            time_since_mandate = now - stats.last_mandate_time
            if time_since_mandate > self.DEADLOCK_WINDOW_SEC:
                issues.append("DEADLOCK")

        return {
            "symbol": symbol,
            "status": "STABLE" if not issues else "ISSUES",
            "issues": issues,
            "total_mandates": stats.total_mandates,
            "by_type": dict(stats.by_type),
            "entry_exit_cycles": stats.entry_exit_cycles,
            "direction_flips": stats.direction_flips,
            "time_since_last_mandate_sec": time_since_mandate
        }

    def get_recent_issues(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get most recent stability issues.

        Args:
            n: Number of issues to return

        Returns:
            List of issue dictionaries
        """
        return [i.to_dict() for i in self._issues[-n:]]

    def get_mandate_distribution(self) -> Dict[str, int]:
        """Get distribution of mandate types.

        Returns:
            Dict of mandate_type -> count
        """
        dist = defaultdict(int)
        for record in self._mandates:
            dist[record.mandate_type.name] += 1
        return dict(dist)

    def get_action_distribution(self) -> Dict[str, int]:
        """Get distribution of action types.

        Returns:
            Dict of action_type -> count
        """
        dist = defaultdict(int)
        for record in self._actions:
            dist[record.action_type.name] += 1
        return dict(dist)

    def reset_symbol(self, symbol: str) -> None:
        """Reset statistics for a symbol.

        Use when position is fully closed to reset oscillation counters.

        Args:
            symbol: Symbol to reset
        """
        if symbol in self._symbol_stats:
            stats = self._symbol_stats[symbol]
            stats.entry_exit_cycles = 0
            stats.direction_flips = 0
            stats.last_direction = None

    def summary(self) -> Dict[str, Any]:
        """Get full summary of stability observations.

        Returns:
            Comprehensive summary
        """
        status = self.get_stability_status()

        # Add distributions
        status["mandate_distribution"] = self.get_mandate_distribution()
        status["action_distribution"] = self.get_action_distribution()

        # Add per-symbol summaries
        symbol_summaries = {}
        for symbol in self._symbol_stats:
            symbol_summaries[symbol] = self.get_symbol_status(symbol)
        status["symbols"] = symbol_summaries

        return status

    def _check_mandate_validity(self, mandate: Mandate, timestamp: float) -> None:
        """Check mandate for corruption indicators.

        Args:
            mandate: Mandate to validate
            timestamp: Current timestamp
        """
        # Check type validity
        if not isinstance(mandate.type, MandateType):
            self._record_issue(
                StabilityIssue.CORRUPTION_INVALID_TYPE,
                mandate.symbol,
                "CRITICAL",
                {"received_type": str(type(mandate.type))}
            )
            return

        # Check required fields for ENTRY
        if mandate.type == MandateType.ENTRY:
            if mandate.direction is None:
                self._record_issue(
                    StabilityIssue.CORRUPTION_MISSING_FIELD,
                    mandate.symbol,
                    "WARNING",
                    {"missing": "direction", "mandate_type": "ENTRY"}
                )

    def _check_storm(self, symbol: str, now: float) -> None:
        """Check for mandate storm conditions.

        Args:
            symbol: Symbol to check
            now: Current timestamp
        """
        # Count mandates in window
        cutoff = now - self.STORM_WINDOW_SEC
        recent_count = sum(1 for t in self._recent_mandate_times if t >= cutoff)

        if recent_count > self.STORM_THRESHOLD:
            self._record_issue(
                StabilityIssue.STORM_EXCESSIVE_MANDATES,
                symbol,
                "CRITICAL",
                {
                    "count": recent_count,
                    "threshold": self.STORM_THRESHOLD,
                    "window_sec": self.STORM_WINDOW_SEC
                }
            )

    def _record_issue(
        self,
        issue: StabilityIssue,
        symbol: Optional[str],
        severity: str,
        details: Dict[str, Any]
    ) -> None:
        """Record a stability issue.

        Args:
            issue: Issue type
            symbol: Affected symbol
            severity: "INFO", "WARNING", or "CRITICAL"
            details: Additional context
        """
        event = StabilityEvent(
            timestamp=time.time(),
            issue=issue,
            symbol=symbol,
            severity=severity,
            details=details
        )

        self._issues.append(event)
        if len(self._issues) > self._max_issues:
            self._issues = self._issues[-self._max_issues:]

        # Log critical issues immediately
        if severity == "CRITICAL":
            print(f"[STABILITY CRITICAL] {event.to_json()}")


# Global singleton instance
stability_observer = StabilityObserver()
