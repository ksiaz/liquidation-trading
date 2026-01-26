"""
HLP17: Drawdown Tracker.

Tracks drawdowns and enforces limits:
1. Daily loss limit (3%)
2. Weekly loss limit (7%)
3. Consecutive loss limit (5)
4. Maximum overall drawdown (25%)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum, auto
from datetime import datetime, timedelta
from threading import RLock


class DrawdownState(Enum):
    """Drawdown state."""
    NORMAL = auto()
    WARNING = auto()  # Approaching limit
    DAILY_COOLDOWN = auto()  # Hit daily limit
    WEEKLY_COOLDOWN = auto()  # Hit weekly limit
    REDUCED_RISK = auto()  # Consecutive losses
    MAXIMUM_DRAWDOWN = auto()  # Hit max drawdown


class CooldownReason(Enum):
    """AUDIT-P0-10: Reason for entering cooldown (affects reset validation)."""
    DAILY_LOSS = auto()      # Hit daily loss limit
    WEEKLY_LOSS = auto()     # Hit weekly loss limit
    CONSECUTIVE_LOSS = auto() # Hit consecutive loss halt


@dataclass
class DrawdownConfig:
    """Configuration for drawdown controls."""
    # Daily limits
    daily_loss_limit_pct: float = 0.03  # 3%
    daily_warning_pct: float = 0.02  # 2% warning

    # Weekly limits
    weekly_loss_limit_pct: float = 0.07  # 7%
    weekly_warning_pct: float = 0.05  # 5% warning

    # Consecutive loss limits
    consecutive_loss_warning: int = 3
    consecutive_loss_reduced: int = 5  # Enter reduced risk mode
    consecutive_loss_halt: int = 10  # Stop trading

    # Overall drawdown limits
    max_drawdown_pct: float = 0.25  # 25%
    recovery_drawdown_pct: float = 0.15  # Back to 15% to recover

    # Recovery settings
    recovery_wins_required: int = 2  # Wins to exit reduced risk

    # Size reduction
    reduced_risk_multiplier: float = 0.5  # 50% size
    max_drawdown_multiplier: float = 0.25  # 25% size


@dataclass
class DrawdownEvent:
    """Record of a drawdown event."""
    timestamp: int  # nanoseconds
    event_type: str  # 'daily_limit', 'weekly_limit', 'consecutive', 'max_dd'
    current_value: float
    peak_value: float
    drawdown_pct: float
    details: Dict = field(default_factory=dict)


class DrawdownTracker:
    """
    Tracks and enforces drawdown limits.

    Monitors:
    - Daily PnL
    - Weekly PnL
    - Consecutive losses
    - Overall drawdown from peak
    """

    def __init__(
        self,
        initial_capital: float,
        config: DrawdownConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or DrawdownConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Capital tracking
        self._initial_capital = initial_capital
        self._current_capital = initial_capital
        self._peak_capital = initial_capital

        # Period tracking
        self._daily_start_capital = initial_capital
        self._weekly_start_capital = initial_capital
        self._daily_start_ts: Optional[int] = None
        self._weekly_start_ts: Optional[int] = None

        # Streak tracking
        self._consecutive_losses = 0
        self._consecutive_wins = 0
        self._total_trades = 0
        self._total_wins = 0

        # State
        self._state = DrawdownState.NORMAL
        self._events: List[DrawdownEvent] = []

        # AUDIT-P0-10: Track reason for cooldown (affects reset validation)
        self._cooldown_reason: Optional[CooldownReason] = None

        # Callbacks
        self._callbacks: List[Callable[[DrawdownState, DrawdownState], None]] = []

        self._lock = RLock()  # Reentrant lock to allow nested calls

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    @property
    def state(self) -> DrawdownState:
        """Get current drawdown state."""
        return self._state

    @property
    def current_capital(self) -> float:
        """Get current capital."""
        return self._current_capital

    def update_capital(self, new_capital: float):
        """Update current capital value."""
        with self._lock:
            self._current_capital = new_capital

            # Update peak
            if new_capital > self._peak_capital:
                self._peak_capital = new_capital

            # Check drawdown limits
            self._check_drawdown_limits()

    def record_trade(self, pnl: float):
        """Record a trade result."""
        ts = self._now_ns()

        with self._lock:
            self._total_trades += 1

            # Update capital
            self._current_capital += pnl

            if self._current_capital > self._peak_capital:
                self._peak_capital = self._current_capital

            # Update streaks
            if pnl > 0:
                self._total_wins += 1
                self._consecutive_wins += 1
                self._consecutive_losses = 0
            elif pnl < 0:
                self._consecutive_losses += 1
                self._consecutive_wins = 0

            # Check all limits
            self._check_all_limits(ts)

    def _check_all_limits(self, ts: int):
        """Check all drawdown limits."""
        old_state = self._state

        # Check consecutive losses first (highest priority for reduced risk)
        self._check_consecutive_losses(ts)

        # Check daily limit
        self._check_daily_limit(ts)

        # Check weekly limit
        self._check_weekly_limit(ts)

        # Check overall drawdown
        self._check_drawdown_limits()

        # Notify callbacks if state changed
        if self._state != old_state:
            self._notify_state_change(old_state, self._state)

    def _check_consecutive_losses(self, ts: int):
        """Check consecutive loss limits."""
        if self._consecutive_losses >= self._config.consecutive_loss_halt:
            if self._state != DrawdownState.DAILY_COOLDOWN:
                self._state = DrawdownState.DAILY_COOLDOWN  # Halt trading
                # AUDIT-P0-10: Track that this was due to consecutive losses
                self._cooldown_reason = CooldownReason.CONSECUTIVE_LOSS
                self._record_event(ts, 'consecutive_halt', {
                    'consecutive_losses': self._consecutive_losses
                })
                self._logger.error(
                    f"TRADING HALTED: {self._consecutive_losses} consecutive losses"
                )
        elif self._consecutive_losses >= self._config.consecutive_loss_reduced:
            if self._state == DrawdownState.NORMAL:
                self._state = DrawdownState.REDUCED_RISK
                self._record_event(ts, 'consecutive_reduced', {
                    'consecutive_losses': self._consecutive_losses
                })
                self._logger.warning(
                    f"REDUCED RISK: {self._consecutive_losses} consecutive losses"
                )
        elif self._consecutive_losses >= self._config.consecutive_loss_warning:
            if self._state == DrawdownState.NORMAL:
                self._state = DrawdownState.WARNING
                self._logger.warning(
                    f"Warning: {self._consecutive_losses} consecutive losses"
                )

        # Check for recovery from reduced risk
        if self._state == DrawdownState.REDUCED_RISK:
            if self._consecutive_wins >= self._config.recovery_wins_required:
                self._state = DrawdownState.NORMAL
                self._cooldown_reason = None  # AUDIT-P0-10: Clear reason on recovery
                self._logger.info("Recovered from reduced risk mode")

        # AUDIT-P0-10: Check for recovery from consecutive loss halt
        # A win breaks the streak, allowing daily reset to work
        if (self._state == DrawdownState.DAILY_COOLDOWN and
                self._cooldown_reason == CooldownReason.CONSECUTIVE_LOSS):
            if self._consecutive_wins >= 1:
                # Streak broken by a win, allow transition to NORMAL
                self._state = DrawdownState.NORMAL
                self._cooldown_reason = None
                self._logger.info("Consecutive loss halt ended: streak broken by winning trade")

    def _check_daily_limit(self, ts: int):
        """Check daily loss limit."""
        if self._daily_start_capital <= 0:
            return

        daily_pnl = self._current_capital - self._daily_start_capital
        daily_loss_pct = abs(daily_pnl) / self._daily_start_capital if daily_pnl < 0 else 0

        if daily_loss_pct > self._config.daily_loss_limit_pct:
            if self._state not in (DrawdownState.DAILY_COOLDOWN, DrawdownState.WEEKLY_COOLDOWN):
                self._state = DrawdownState.DAILY_COOLDOWN
                # AUDIT-P0-10: Track that this was due to daily loss limit
                self._cooldown_reason = CooldownReason.DAILY_LOSS
                self._record_event(ts, 'daily_limit', {
                    'daily_loss_pct': daily_loss_pct,
                    'daily_pnl': daily_pnl
                })
                self._logger.error(
                    f"DAILY LIMIT HIT: {daily_loss_pct*100:.1f}% loss"
                )
        elif daily_loss_pct > self._config.daily_warning_pct:
            if self._state == DrawdownState.NORMAL:
                self._state = DrawdownState.WARNING
                self._logger.warning(
                    f"Daily loss warning: {daily_loss_pct*100:.1f}%"
                )

    def _check_weekly_limit(self, ts: int):
        """Check weekly loss limit."""
        if self._weekly_start_capital <= 0:
            return

        weekly_pnl = self._current_capital - self._weekly_start_capital
        weekly_loss_pct = abs(weekly_pnl) / self._weekly_start_capital if weekly_pnl < 0 else 0

        if weekly_loss_pct > self._config.weekly_loss_limit_pct:
            if self._state != DrawdownState.WEEKLY_COOLDOWN:
                self._state = DrawdownState.WEEKLY_COOLDOWN
                # AUDIT-P0-10: Track that this was due to weekly loss limit
                self._cooldown_reason = CooldownReason.WEEKLY_LOSS
                self._record_event(ts, 'weekly_limit', {
                    'weekly_loss_pct': weekly_loss_pct,
                    'weekly_pnl': weekly_pnl
                })
                self._logger.error(
                    f"WEEKLY LIMIT HIT: {weekly_loss_pct*100:.1f}% loss"
                )
        elif weekly_loss_pct > self._config.weekly_warning_pct:
            if self._state == DrawdownState.NORMAL:
                self._state = DrawdownState.WARNING
                self._logger.warning(
                    f"Weekly loss warning: {weekly_loss_pct*100:.1f}%"
                )

    def _check_drawdown_limits(self):
        """Check overall drawdown limits."""
        if self._peak_capital <= 0:
            return

        drawdown_pct = (self._peak_capital - self._current_capital) / self._peak_capital

        if drawdown_pct > self._config.max_drawdown_pct:
            if self._state != DrawdownState.MAXIMUM_DRAWDOWN:
                self._state = DrawdownState.MAXIMUM_DRAWDOWN
                self._record_event(self._now_ns(), 'max_drawdown', {
                    'drawdown_pct': drawdown_pct,
                    'peak': self._peak_capital,
                    'current': self._current_capital
                })
                self._logger.error(
                    f"MAXIMUM DRAWDOWN: {drawdown_pct*100:.1f}% from peak"
                )
        elif self._state == DrawdownState.MAXIMUM_DRAWDOWN:
            # Check for recovery
            if drawdown_pct < self._config.recovery_drawdown_pct:
                self._state = DrawdownState.NORMAL
                self._cooldown_reason = None  # AUDIT-P0-10: Clear reason on recovery
                self._logger.info(
                    f"Recovering from max drawdown: {drawdown_pct*100:.1f}%"
                )

    def _record_event(self, ts: int, event_type: str, details: Dict):
        """Record a drawdown event."""
        drawdown_pct = 0
        if self._peak_capital > 0:
            drawdown_pct = (self._peak_capital - self._current_capital) / self._peak_capital

        event = DrawdownEvent(
            timestamp=ts,
            event_type=event_type,
            current_value=self._current_capital,
            peak_value=self._peak_capital,
            drawdown_pct=drawdown_pct,
            details=details
        )
        self._events.append(event)

    def _notify_state_change(self, old_state: DrawdownState, new_state: DrawdownState):
        """Notify callbacks of state change."""
        for callback in self._callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                self._logger.error(f"Callback error: {e}")

    def register_callback(
        self,
        callback: Callable[[DrawdownState, DrawdownState], None]
    ):
        """Register callback for state changes."""
        with self._lock:
            self._callbacks.append(callback)

    def reset_daily(self):
        """Reset daily tracking (call at start of new day).

        AUDIT-P0-10: Validates cooldown reason before allowing exit.
        """
        with self._lock:
            self._daily_start_capital = self._current_capital
            self._daily_start_ts = self._now_ns()

            # Exit daily cooldown if active
            if self._state == DrawdownState.DAILY_COOLDOWN:
                # AUDIT-P0-10: Only allow exit if cooldown was from daily loss limit
                # Consecutive loss halt requires breaking the streak, not just time passing
                if self._cooldown_reason == CooldownReason.CONSECUTIVE_LOSS:
                    self._logger.warning(
                        f"reset_daily() blocked: DAILY_COOLDOWN due to consecutive losses "
                        f"({self._consecutive_losses} losses). Must break streak to recover."
                    )
                    return  # Do NOT exit cooldown

                self._state = DrawdownState.NORMAL
                self._cooldown_reason = None
                self._logger.info("Daily cooldown ended, trading resumed")

    def reset_weekly(self):
        """Reset weekly tracking (call at start of new week).

        AUDIT-P0-10: Validates cooldown reason before allowing exit.
        """
        with self._lock:
            self._weekly_start_capital = self._current_capital
            self._weekly_start_ts = self._now_ns()

            # Exit weekly cooldown if active
            if self._state == DrawdownState.WEEKLY_COOLDOWN:
                # AUDIT-P0-10: Weekly reset is allowed (new week is a natural boundary)
                # But log if we had consecutive losses so it's visible
                if self._consecutive_losses >= self._config.consecutive_loss_halt:
                    self._logger.warning(
                        f"reset_weekly(): Exiting WEEKLY_COOLDOWN despite {self._consecutive_losses} "
                        f"consecutive losses. Consider if trading should resume."
                    )
                self._state = DrawdownState.NORMAL
                self._cooldown_reason = None
                self._logger.info("Weekly cooldown ended, trading resumed")

    def get_size_multiplier(self) -> float:
        """Get position size multiplier based on drawdown state."""
        with self._lock:
            if self._state == DrawdownState.MAXIMUM_DRAWDOWN:
                return self._config.max_drawdown_multiplier
            elif self._state == DrawdownState.REDUCED_RISK:
                return self._config.reduced_risk_multiplier
            elif self._state in (DrawdownState.DAILY_COOLDOWN, DrawdownState.WEEKLY_COOLDOWN):
                return 0.0  # No trading
            else:
                return 1.0

    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed."""
        return self._state not in (
            DrawdownState.DAILY_COOLDOWN,
            DrawdownState.WEEKLY_COOLDOWN
        )

    def get_daily_pnl(self) -> float:
        """Get current daily PnL."""
        with self._lock:
            return self._current_capital - self._daily_start_capital

    def get_weekly_pnl(self) -> float:
        """Get current weekly PnL."""
        with self._lock:
            return self._current_capital - self._weekly_start_capital

    def get_overall_drawdown(self) -> float:
        """Get overall drawdown from peak."""
        with self._lock:
            if self._peak_capital <= 0:
                return 0
            return (self._peak_capital - self._current_capital) / self._peak_capital

    def get_summary(self) -> Dict:
        """Get drawdown summary."""
        with self._lock:
            daily_pnl = self._current_capital - self._daily_start_capital
            weekly_pnl = self._current_capital - self._weekly_start_capital
            overall_dd = self.get_overall_drawdown()

            return {
                'state': self._state.name,
                'cooldown_reason': self._cooldown_reason.name if self._cooldown_reason else None,
                'current_capital': self._current_capital,
                'peak_capital': self._peak_capital,
                'initial_capital': self._initial_capital,
                'daily_pnl': daily_pnl,
                'daily_pnl_pct': daily_pnl / self._daily_start_capital if self._daily_start_capital > 0 else 0,
                'weekly_pnl': weekly_pnl,
                'weekly_pnl_pct': weekly_pnl / self._weekly_start_capital if self._weekly_start_capital > 0 else 0,
                'overall_drawdown_pct': overall_dd,
                'consecutive_losses': self._consecutive_losses,
                'consecutive_wins': self._consecutive_wins,
                'total_trades': self._total_trades,
                'win_rate': self._total_wins / self._total_trades if self._total_trades > 0 else 0,
                'size_multiplier': self.get_size_multiplier(),
                'trading_allowed': self.is_trading_allowed()
            }

    def get_events(self, limit: int = 100) -> List[DrawdownEvent]:
        """Get recent drawdown events."""
        with self._lock:
            return list(self._events[-limit:])

    def force_clear_consecutive_halt(self, reason: str):
        """AUDIT-P0-10: Force clear consecutive loss halt (admin override).

        Use this when manual intervention is needed to resume trading after
        consecutive loss halt. Requires explicit reason for audit trail.

        Args:
            reason: Why this override is being applied (logged for audit)
        """
        with self._lock:
            if (self._state == DrawdownState.DAILY_COOLDOWN and
                    self._cooldown_reason == CooldownReason.CONSECUTIVE_LOSS):
                self._logger.warning(
                    f"ADMIN OVERRIDE: Clearing consecutive loss halt. "
                    f"Losses: {self._consecutive_losses}. Reason: {reason}"
                )
                self._record_event(self._now_ns(), 'admin_override', {
                    'consecutive_losses': self._consecutive_losses,
                    'reason': reason
                })
                self._consecutive_losses = 0
                self._state = DrawdownState.NORMAL
                self._cooldown_reason = None
            else:
                self._logger.info(
                    f"force_clear_consecutive_halt called but not in consecutive loss halt "
                    f"(state={self._state}, reason={self._cooldown_reason})"
                )

    def get_cooldown_reason(self) -> Optional[CooldownReason]:
        """AUDIT-P0-10: Get reason for current cooldown state."""
        with self._lock:
            return self._cooldown_reason
