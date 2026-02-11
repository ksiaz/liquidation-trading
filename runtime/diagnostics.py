"""Diagnostics Module - Structured Observability for Silent Paths.

This module provides structured diagnostic output for silent fallbacks.
It does NOT change behavior - only adds visibility.

Usage:
    from runtime.diagnostics import diag

    # Record a silent skip
    diag.record_skip(
        component="PolicyAdapter",
        function="generate_mandates",
        reason_code=ReasonCode.MISSING_PRICE,
        symbol="BTCUSDT",
        context={"regime_state": None}
    )

INVARIANT: This module is read-only and observational.
           It must NEVER affect control flow or business logic.
"""

import time
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
from collections import defaultdict


class ReasonCode(Enum):
    """Machine-readable reason codes for silent skips.

    Each code represents a specific condition that caused
    a component to return early or use a fallback.
    """
    # M1 Ingestion
    M1_NORMALIZATION_FAILED = "M1_NORMALIZATION_FAILED"
    M1_UNKNOWN_EVENT_TYPE = "M1_UNKNOWN_EVENT_TYPE"

    # M2 Continuity
    M2_NO_VALID_PRICE = "M2_NO_VALID_PRICE"
    M2_NODE_CREATION_FAILED = "M2_NODE_CREATION_FAILED"

    # M4 Primitives
    M4_PRIMITIVE_EXCEPTION = "M4_PRIMITIVE_EXCEPTION"
    M4_CASCADE_COLLECTOR_MISSING = "M4_CASCADE_COLLECTOR_MISSING"
    M4_PROXIMITY_DATA_MISSING = "M4_PROXIMITY_DATA_MISSING"
    M4_TRACKER_MISSING = "M4_TRACKER_MISSING"
    M4_NO_POSITIONS = "M4_NO_POSITIONS"
    M4_COMPUTATION_EXCEPTION = "M4_COMPUTATION_EXCEPTION"

    # PolicyAdapter
    PA_SYMBOL_NOT_IN_SNAPSHOT = "PA_SYMBOL_NOT_IN_SNAPSHOT"
    PA_MISSING_PRICE = "PA_MISSING_PRICE"
    PA_REGIME_STATE_MISSING = "PA_REGIME_STATE_MISSING"
    PA_REGIME_METRICS_MISSING = "PA_REGIME_METRICS_MISSING"
    PA_CASCADE_DATA_MISSING = "PA_CASCADE_DATA_MISSING"
    PA_STRATEGY_NO_PROPOSAL = "PA_STRATEGY_NO_PROPOSAL"
    PA_GRACE_PERIOD_BLOCKED = "PA_GRACE_PERIOD_BLOCKED"

    # Arbitration
    ARB_NO_MANDATES = "ARB_NO_MANDATES"
    ARB_NO_ACTION = "ARB_NO_ACTION"
    ARB_BLOCKED = "ARB_BLOCKED"

    # Execution Controller
    EC_ENTRY_MISSING_QUANTITY = "EC_ENTRY_MISSING_QUANTITY"
    EC_ENTRY_MISSING_DIRECTION = "EC_ENTRY_MISSING_DIRECTION"
    EC_RISK_VALIDATION_FAILED = "EC_RISK_VALIDATION_FAILED"
    EC_INVALID_ACTION_FOR_STATE = "EC_INVALID_ACTION_FOR_STATE"

    # M6 Executor
    M6_UNINITIALIZED = "M6_UNINITIALIZED"
    M6_NO_MANDATES = "M6_NO_MANDATES"
    M6_NO_WINNING_MANDATE = "M6_NO_WINNING_MANDATE"
    M6_ACTION_INVALID = "M6_ACTION_INVALID"
    M6_SINGLE_POSITION_VIOLATED = "M6_SINGLE_POSITION_VIOLATED"

    # Ghost Tracker
    GT_DB_WRITE_FAILED = "GT_DB_WRITE_FAILED"
    GT_NO_DB_CONNECTION = "GT_NO_DB_CONNECTION"

    # General
    EXCEPTION_CAUGHT = "EXCEPTION_CAUGHT"
    GOVERNANCE_FREEZE = "GOVERNANCE_FREEZE"


@dataclass
class DiagnosticEvent:
    """Single diagnostic event recording a silent path."""
    timestamp: float
    component: str
    function: str
    reason_code: ReasonCode
    symbol: Optional[str]
    context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.timestamp,
            "component": self.component,
            "function": self.function,
            "reason": self.reason_code.value,
            "symbol": self.symbol,
            "context": self.context
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class DiagnosticsCollector:
    """Collects and exposes diagnostic events for silent paths.

    Thread-safe counter and event collection.
    Does NOT affect control flow.
    """

    def __init__(self, enabled: bool = True, max_events: int = 10000):
        self._enabled = enabled
        self._max_events = max_events
        self._events: List[DiagnosticEvent] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._last_by_symbol: Dict[str, DiagnosticEvent] = {}
        self._start_time = time.time()

        # Output control
        self._print_enabled = os.environ.get('DIAG_PRINT', '').lower() in ('1', 'true', 'yes')
        self._file_path = os.environ.get('DIAG_FILE', None)
        self._file_handle = None

        if self._file_path:
            try:
                self._file_handle = open(self._file_path, 'a')
            except Exception:
                pass  # Don't fail if we can't open log file

    def record_skip(
        self,
        component: str,
        function: str,
        reason_code: ReasonCode,
        symbol: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a silent skip event.

        This is the primary API for instrumentation.

        Args:
            component: Component name (e.g., "PolicyAdapter")
            function: Function name (e.g., "generate_mandates")
            reason_code: Machine-readable reason
            symbol: Trading symbol if applicable
            context: Additional context (data missing, values, etc.)
        """
        if not self._enabled:
            return

        event = DiagnosticEvent(
            timestamp=time.time(),
            component=component,
            function=function,
            reason_code=reason_code,
            symbol=symbol,
            context=context or {}
        )

        # Update counters
        counter_key = f"{component}.{function}.{reason_code.value}"
        self._counters[counter_key] += 1

        # Store event
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        # Track last event per symbol
        if symbol:
            self._last_by_symbol[symbol] = event

        # Output
        if self._print_enabled:
            print(f"[DIAG] {event.to_json()}")

        if self._file_handle:
            try:
                self._file_handle.write(event.to_json() + "\n")
                self._file_handle.flush()
            except Exception:
                pass

    def get_counters(self) -> Dict[str, int]:
        """Get all counters as dict."""
        return dict(self._counters)

    def get_counter(self, component: str, function: str, reason_code: ReasonCode) -> int:
        """Get specific counter value."""
        key = f"{component}.{function}.{reason_code.value}"
        return self._counters.get(key, 0)

    def get_recent_events(self, n: int = 100) -> List[DiagnosticEvent]:
        """Get most recent n events."""
        return self._events[-n:]

    def get_events_for_symbol(self, symbol: str, n: int = 50) -> List[DiagnosticEvent]:
        """Get recent events for a specific symbol."""
        return [e for e in self._events[-1000:] if e.symbol == symbol][-n:]

    def get_last_event_for_symbol(self, symbol: str) -> Optional[DiagnosticEvent]:
        """Get most recent event for a symbol."""
        return self._last_by_symbol.get(symbol)

    def explain_inactivity(self, symbol: str, window_sec: float = 60.0) -> Dict[str, Any]:
        """Answer: 'Why were zero ENTRY mandates produced for this symbol?'

        Returns structured explanation of all skips in the time window.
        """
        cutoff = time.time() - window_sec

        # Filter events for symbol in window
        relevant = [
            e for e in self._events
            if (e.symbol == symbol or e.symbol is None) and e.timestamp >= cutoff
        ]

        # Group by reason
        by_reason: Dict[str, int] = defaultdict(int)
        for e in relevant:
            by_reason[e.reason_code.value] += 1

        # Build explanation
        return {
            "symbol": symbol,
            "window_sec": window_sec,
            "total_skip_events": len(relevant),
            "reasons": dict(by_reason),
            "events": [e.to_dict() for e in relevant[-20:]]  # Last 20 events
        }

    def summary(self) -> Dict[str, Any]:
        """Get summary of all diagnostics."""
        runtime = time.time() - self._start_time
        return {
            "runtime_sec": runtime,
            "total_events": len(self._events),
            "counters": dict(self._counters),
            "symbols_with_events": list(self._last_by_symbol.keys())
        }

    def reset(self) -> None:
        """Reset all counters and events."""
        self._events.clear()
        self._counters.clear()
        self._last_by_symbol.clear()
        self._start_time = time.time()


# Global singleton instance
diag = DiagnosticsCollector(
    enabled=os.environ.get('DIAG_ENABLED', '1').lower() in ('1', 'true', 'yes')
)
