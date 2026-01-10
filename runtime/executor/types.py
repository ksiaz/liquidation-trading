"""Execution Controller Types.

Data structures for execution results and logging.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from runtime.arbitration.types import ActionType
from runtime.position.types import PositionState


@dataclass(frozen=True)
class ExecutionResult:
    """Result of executing an action on a position.
    
    Used for logging and auditability per constitutional requirements.
    """
    symbol: str
    action: ActionType
    success: bool
    state_before: PositionState
    state_after: PositionState
    timestamp: float
    error: Optional[str] = None
    
    def to_log_dict(self) -> dict:
        """Convert to dict for logging."""
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "success": self.success,
            "state_before": self.state_before.value,
            "state_after": self.state_after.value,
            "timestamp": self.timestamp,
            "error": self.error,
        }


@dataclass(frozen=True)
class CycleStats:
    """Statistics for a complete execution cycle.
    
    Tracks mandate processing and execution outcomes.
    """
    mandates_received: int
    actions_executed: int
    actions_rejected: int
    symbols_processed: int
    
    def to_log_dict(self) -> dict:
        """Convert to dict for logging."""
        return {
            "mandates_received": self.mandates_received,
            "actions_executed": self.actions_executed,
            "actions_rejected": self.actions_rejected,
            "symbols_processed": self.symbols_processed,
        }
