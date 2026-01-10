"""
Logging & Audit Module

Structured logging for all system events.

RESPONSIBILITIES:
- Log all regime changes
- Log all state transitions
- Log all setup invalidations
- Log all entries/exits
- Log all kill-switch triggers

INVARIANTS:
- All events must be logged
- Structured, timestamped, machine-readable format
- Missing logs invalidate implementation
"""

from .types import EventType, LogEvent
from .audit_logger import AuditLogger

__all__ = [
    "EventType",
    "LogEvent",
    "AuditLogger",
]
