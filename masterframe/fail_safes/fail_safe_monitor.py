"""
Fail-Safe Monitor

Monitors fail-safe conditions and triggers kill-switch.

RULES:
- Hard kill requires manual reset
- Fail closed (safe state = disabled)
- Check all conditions every update
"""

import time
from typing import Optional, List
from collections import deque
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.risk_management.types import PositionExit
from .types import KillSwitchReason, FailSafeConfig, KillSwitchEvent


class FailSafeMonitor:
    """
    Monitors fail-safe conditions and triggers kill-switch.
    
    INVARIANT: Hard kill requires manual reset.
    INVARIANT: Fail closed (safe state = disabled).
    """
    
    def __init__(self, config: FailSafeConfig, starting_balance: float):
        """
        Initialize fail-safe monitor.
        
        Args:
            config: Fail-safe configuration
            starting_balance: Starting account balance
        """
        self.config = config
        self.starting_balance = starting_balance
        self.current_balance = starting_balance
        
        # Session tracking (resets at UTC 00:00)
        self.session_start_balance = starting_balance
        self.session_start_time = time.time()
        
        # Kill-switch state
        self.is_killed = False
        self.kill_reason: Optional[KillSwitchReason] = None
        self.kill_time: Optional[float] = None
        self.kill_events: List[KillSwitchEvent] = []
        
        # Performance tracking
        self.consecutive_losses = 0
        self.recent_trades: deque = deque(maxlen=config.win_rate_sample_size)
    
    def update(
        self,
        current_balance: float,
        exit_record: Optional[PositionExit],
        current_time: float
    ) -> bool:
        """
        Update fail-safe monitoring.
        
        Args:
            current_balance: Current account balance
            exit_record: Latest exit record (if any)
            current_time: Current timestamp
        
        Returns:
            True if system can continue, False if killed
        
        RULE: Check all fail-safe conditions.
        RULE: Once killed, stay killed until manual reset.
        """
        # If already killed, stay killed
        if self.is_killed:
            return False
        
        # Update balance
        self.current_balance = current_balance
        
        # Reset session if new day
        self._check_new_session(current_time)
        
        # Process exit record
        if exit_record:
            self._process_exit(exit_record)
        
        # Check fail-safe conditions
        self._check_consecutive_losses(current_time)
        self._check_daily_drawdown(current_balance, current_time)
        self._check_win_rate(current_time)
        
        return not self.is_killed
    
    def _check_consecutive_losses(self, current_time: float) -> None:
        """
        Check consecutive losses condition.
        
        RULE: ≥2 consecutive losses → kill.
        """
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            self._trigger_kill_switch(
                KillSwitchReason.CONSECUTIVE_LOSSES,
                f"{self.consecutive_losses} consecutive losses",
                current_time
            )
    
    def _check_daily_drawdown(self, current_balance: float, current_time: float) -> None:
        """
        Check daily drawdown condition.
        
        RULE: ≥MAX_DD% loss from session start → kill.
        """
        drawdown = current_balance - self.session_start_balance
        drawdown_pct = (drawdown / self.session_start_balance) * 100.0
        
        if drawdown_pct <= -self.config.max_daily_drawdown_pct:
            self._trigger_kill_switch(
                KillSwitchReason.DAILY_DRAWDOWN,
                f"{drawdown_pct:.2f}% daily drawdown",
                current_time
            )
    
    def _check_win_rate(self, current_time: float) -> None:
        """
        Check win rate condition.
        
        RULE: Win rate < 35% over last 20 trades → kill.
        """
        if len(self.recent_trades) < self.config.win_rate_sample_size:
            return  # Not enough data yet
        
        wins = sum(1 for pnl in self.recent_trades if pnl > 0)
        win_rate = (wins / len(self.recent_trades)) * 100.0
        
        if win_rate < self.config.min_win_rate_pct:
            self._trigger_kill_switch(
                KillSwitchReason.LOW_WIN_RATE,
                f"{win_rate:.1f}% win rate (last {len(self.recent_trades)} trades)",
                current_time
            )
    
    def _trigger_kill_switch(
        self,
        reason: KillSwitchReason,
        details: str,
        timestamp: float
    ) -> None:
        """
        Activate kill-switch.
        
        RULE: Hard kill - stays killed until manual reset.
        """
        self.is_killed = True
        self.kill_reason = reason
        self.kill_time = timestamp
        
        # Log event
        event = KillSwitchEvent(
            reason=reason,
            timestamp=timestamp,
            details=details
        )
        self.kill_events.append(event)
    
    def _process_exit(self, exit_record: PositionExit) -> None:
        """
        Process exit record for tracking.
        
        Updates consecutive losses and recent trades.
        """
        pnl = exit_record.pnl
        self.recent_trades.append(pnl)
        
        # Track consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0  # Reset on win
    
    def _check_new_session(self, current_time: float) -> None:
        """
        Reset session tracking at UTC 00:00.
        
        RULE: Session resets daily at UTC midnight.
        """
        current_day = time.gmtime(current_time).tm_yday
        session_day = time.gmtime(self.session_start_time).tm_yday
        
        if current_day != session_day:
            # New session
            self.session_start_time = current_time
            self.session_start_balance = self.current_balance
    
    def manual_reset(self) -> None:
        """
        Manually reset kill-switch.
        
        RULE: Only way to clear hard kill.
        RULE: Requires explicit intervention.
        """
        self.is_killed = False
        self.kill_reason = None
        self.kill_time = None
        self.consecutive_losses = 0
        # Note: Keep kill_events for logging/analysis
    
    def get_kill_status(self) -> bool:
        """Check if system is killed."""
        return self.is_killed
    
    def get_kill_reason(self) -> Optional[KillSwitchReason]:
        """Get kill reason (if killed)."""
        return self.kill_reason
    
    def get_consecutive_losses(self) -> int:
        """Get consecutive loss count."""
        return self.consecutive_losses
    
    def get_win_rate(self) -> Optional[float]:
        """Get current win rate % (last N trades)."""
        if len(self.recent_trades) == 0:
            return None
        
        wins = sum(1 for pnl in self.recent_trades if pnl > 0)
        return (wins / len(self.recent_trades)) * 100.0
    
    def get_daily_drawdown_pct(self) -> float:
        """Get current daily drawdown %."""
        drawdown = self.current_balance - self.session_start_balance
        return (drawdown / self.session_start_balance) * 100.0
