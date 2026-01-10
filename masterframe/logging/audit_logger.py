"""
Audit Logger

Centralized logging for all system events.

RULES:
- All events must be logged
- Structured JSON format
- Timestamped
- Append-only JSONL file
"""

from typing import List, Dict, Any, Optional
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.regime_classifier.types import RegimeType
from masterframe.slbrs import SLBRSState
from masterframe.effcs import EFFCSState
from masterframe.risk_management.types import Position, PositionExit
from masterframe.fail_safes.types import KillSwitchEvent
from .types import EventType, LogEvent


class AuditLogger:
    """
    Centralized audit logging.
    
    INVARIANT: All events must be logged.
    INVARIANT: Structured, timestamped, machine-readable.
    INVARIANT: Missing logs invalidate implementation.
    """
    
    def __init__(self, log_file: str = "masterframe_audit.jsonl"):
        """
        Initialize audit logger.
        
        Args:
            log_file: Path to JSONL log file
        """
        self.log_file = log_file
        self.events: List[LogEvent] = []
    
    def log_regime_change(
        self,
        old_regime: RegimeType,
        new_regime: RegimeType,
        conditions: Dict[str, Any],
        timestamp: float
    ) -> None:
        """
        Log regime change.
        
        RULE: Log old regime, new regime, and conditions that triggered change.
        """
        event = LogEvent(
            event_type=EventType.REGIME_CHANGE,
            timestamp=timestamp,
            data={
                "old_regime": old_regime.value,
                "new_regime": new_regime.value,
                "conditions": conditions
            }
        )
        self._write_event(event)
    
    def log_slbrs_transition(
        self,
        old_state: SLBRSState,
        new_state: SLBRSState,
        reason: str,
        timestamp: float
    ) -> None:
        """
        Log SLBRS state transition.
        
        RULE: Log state change and reason.
        """
        event = LogEvent(
            event_type=EventType.SLBRS_STATE_TRANSITION,
            timestamp=timestamp,
            data={
                "old_state": old_state.value,
                "new_state": new_state.value,
                "reason": reason
            }
        )
        self._write_event(event)
    
    def log_effcs_transition(
        self,
        old_state: EFFCSState,
        new_state: EFFCSState,
        reason: str,
        timestamp: float
    ) -> None:
        """
        Log EFFCS state transition.
        
        RULE: Log state change and reason.
        """
        event = LogEvent(
            event_type=EventType.EFFCS_STATE_TRANSITION,
            timestamp=timestamp,
            data={
                "old_state": old_state.value,
                "new_state": new_state.value,
                "reason": reason
            }
        )
        self._write_event(event)
    
    def log_setup_invalidation(
        self,
        strategy: str,
        reason: str,
        setup_id: str,
        timestamp: float
    ) -> None:
        """
        Log setup invalidation.
        
        RULE: Log why setup was invalidated.
        """
        event = LogEvent(
            event_type=EventType.SETUP_INVALIDATION,
            timestamp=timestamp,
            data={
                "strategy": strategy,
                "reason": reason,
                "setup_id": setup_id
            }
        )
        self._write_event(event)
    
    def log_trade_entry(
        self,
        position: Position,
        timestamp: float
    ) -> None:
        """
        Log trade entry.
        
        RULE: Log full position details.
        """
        event = LogEvent(
            event_type=EventType.TRADE_ENTRY,
            timestamp=timestamp,
            data={
                "strategy": position.strategy,
                "side": position.side,
                "entry_price": position.entry_price,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "size": position.size,
                "reward_risk_ratio": position.get_reward_risk_ratio()
            }
        )
        self._write_event(event)
    
    def log_trade_exit(
        self,
        exit_record: PositionExit,
        timestamp: float
    ) -> None:
        """
        Log trade exit.
        
        RULE: Log exit price, P&L, reason, and duration.
        """
        duration = timestamp - exit_record.position.entry_time
        
        event = LogEvent(
            event_type=EventType.TRADE_EXIT,
            timestamp=timestamp,
            data={
                "strategy": exit_record.position.strategy,
                "exit_price": exit_record.exit_price,
                "pnl": exit_record.pnl,
                "reason": exit_record.reason.value,
                "duration_seconds": duration
            }
        )
        self._write_event(event)
    
    def log_kill_switch(
        self,
        kill_event: KillSwitchEvent,
        account_balance: float
    ) -> None:
        """
        Log kill-switch trigger.
        
        RULE: Log reason and system state.
        """
        event = LogEvent(
            event_type=EventType.KILL_SWITCH,
            timestamp=kill_event.timestamp,
            data={
                "reason": kill_event.reason.value,
                "details": kill_event.details,
                "account_balance": account_balance
            }
        )
        self._write_event(event)
    
    def _write_event(self, event: LogEvent) -> None:
        """
        Write event to log file.
        
        RULE: Append-only JSONL format (one JSON per line).
        """
        self.events.append(event)
        
        # Write to JSONL file
        try:
            with open(self.log_file, 'a') as f:
                f.write(event.to_json() + '\n')
        except Exception as e:
            # Log to stderr if file write fails
            import sys
            print(f"ERROR: Failed to write log event: {e}", file=sys.stderr)
    
    def get_events(self) -> List[LogEvent]:
        """Get all logged events."""
        return self.events
    
    def get_events_by_type(self, event_type: EventType) -> List[LogEvent]:
        """Get events filtered by type."""
        return [e for e in self.events if e.event_type == event_type]
