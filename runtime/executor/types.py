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

    Equity tracking fields added for manual validation (not used by system logic).
    """
    symbol: str
    action: ActionType
    success: bool
    state_before: PositionState
    state_after: PositionState
    timestamp: float
    error: Optional[str] = None
    strategy_id: Optional[str] = None

    # Equity tracking (for manual validation only)
    price: Optional[float] = None
    position_size: Optional[float] = None
    position_value_usd: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    price_change_pct: Optional[float] = None
    realized_pnl_usd: Optional[float] = None
    equity_before: Optional[float] = None
    equity_after: Optional[float] = None

    def to_log_dict(self) -> dict:
        """Convert to dict for logging."""
        result = {
            "symbol": self.symbol,
            "action": self.action.value,
            "success": self.success,
            "state_before": self.state_before.value,
            "state_after": self.state_after.value,
            "timestamp": self.timestamp,
            "error": self.error,
        }

        # Include optional fields if present
        if self.strategy_id is not None:
            result["strategy_id"] = self.strategy_id
        if self.price is not None:
            result["price"] = self.price
        if self.position_size is not None:
            result["position_size"] = self.position_size
        if self.position_value_usd is not None:
            result["position_value_usd"] = self.position_value_usd
        if self.entry_price is not None:
            result["entry_price"] = self.entry_price
        if self.exit_price is not None:
            result["exit_price"] = self.exit_price
        if self.price_change_pct is not None:
            result["price_change_pct"] = self.price_change_pct
        if self.realized_pnl_usd is not None:
            result["realized_pnl_usd"] = self.realized_pnl_usd
        if self.equity_before is not None:
            result["equity_before"] = self.equity_before
        if self.equity_after is not None:
            result["equity_after"] = self.equity_after

        return result


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
