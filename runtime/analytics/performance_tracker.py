"""
HLP19: Performance Tracker.

Calculates trading performance metrics:
- Win rate (overall, rolling, per-strategy)
- PnL (daily, weekly, monthly)
- Sharpe ratio
- Drawdown (current, max)
- Profit factor
- R-multiple analysis
"""

import time
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional
from threading import RLock
from collections import deque

from .types import TradeRecord, TradeOutcome, PerformanceSnapshot


@dataclass
class PerformanceConfig:
    """Configuration for performance tracking."""
    # Rolling windows
    rolling_trade_window: int = 20  # Trades for rolling win rate
    sharpe_window_30d: int = 30     # Days for 30-day Sharpe
    sharpe_window_90d: int = 90     # Days for 90-day Sharpe

    # Thresholds
    win_rate_target: float = 0.55
    win_rate_warning: float = 0.50
    win_rate_critical: float = 0.40

    sharpe_target: float = 1.5
    sharpe_warning: float = 0.5

    max_drawdown_warning: float = 0.15  # 15%
    max_drawdown_critical: float = 0.25  # 25%


class PerformanceTracker:
    """
    Tracks and calculates trading performance metrics.

    Provides:
    - Real-time performance snapshot
    - Rolling metrics (win rate, Sharpe)
    - Drawdown tracking
    - Per-strategy breakdown
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        config: PerformanceConfig = None,
        logger: logging.Logger = None
    ):
        self._initial_capital = initial_capital
        self._current_capital = initial_capital
        self._peak_capital = initial_capital
        self._config = config or PerformanceConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Trade history for calculations
        self._trades: List[TradeRecord] = []
        self._daily_returns: deque = deque(maxlen=90)  # Last 90 days

        # Strategy-specific tracking
        self._strategy_trades: Dict[str, List[TradeRecord]] = {}

        # Period tracking
        self._daily_pnl: float = 0.0
        self._weekly_pnl: float = 0.0
        self._monthly_pnl: float = 0.0
        self._day_start_capital: float = initial_capital
        self._week_start_capital: float = initial_capital
        self._month_start_capital: float = initial_capital

        # Drawdown tracking
        self._drawdown_start_time: Optional[int] = None

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def record_trade(self, trade: TradeRecord):
        """
        Record a closed trade and update metrics.

        Args:
            trade: Completed trade record
        """
        if trade.outcome == TradeOutcome.OPEN:
            return  # Only record closed trades

        with self._lock:
            self._trades.append(trade)

            # Update capital
            self._current_capital += trade.net_pnl

            # Update peak
            if self._current_capital > self._peak_capital:
                self._peak_capital = self._current_capital
                self._drawdown_start_time = None  # Exited drawdown

            # Track drawdown start
            if self._current_capital < self._peak_capital and self._drawdown_start_time is None:
                self._drawdown_start_time = self._now_ns()

            # Update period PnL
            self._daily_pnl += trade.net_pnl
            self._weekly_pnl += trade.net_pnl
            self._monthly_pnl += trade.net_pnl

            # Strategy tracking
            strategy = trade.strategy
            if strategy not in self._strategy_trades:
                self._strategy_trades[strategy] = []
            self._strategy_trades[strategy].append(trade)

            self._logger.debug(
                f"Trade recorded: {trade.outcome.name} PnL={trade.net_pnl:.2f} "
                f"Capital={self._current_capital:.2f}"
            )

    def record_daily_return(self, return_pct: float):
        """Record a daily return percentage for Sharpe calculation."""
        with self._lock:
            self._daily_returns.append(return_pct)

    def reset_daily(self):
        """Reset daily tracking (call at start of new day)."""
        with self._lock:
            # Record yesterday's return
            if self._day_start_capital > 0:
                daily_return = (self._current_capital - self._day_start_capital) / self._day_start_capital
                self._daily_returns.append(daily_return)

            self._daily_pnl = 0.0
            self._day_start_capital = self._current_capital

    def reset_weekly(self):
        """Reset weekly tracking (call at start of new week)."""
        with self._lock:
            self._weekly_pnl = 0.0
            self._week_start_capital = self._current_capital

    def reset_monthly(self):
        """Reset monthly tracking (call at start of new month)."""
        with self._lock:
            self._monthly_pnl = 0.0
            self._month_start_capital = self._current_capital

    def get_snapshot(self) -> PerformanceSnapshot:
        """Get current performance snapshot."""
        with self._lock:
            closed_trades = [t for t in self._trades if t.outcome != TradeOutcome.OPEN]
            wins = [t for t in closed_trades if t.outcome == TradeOutcome.WIN]
            losses = [t for t in closed_trades if t.outcome == TradeOutcome.LOSS]
            breakevens = [t for t in closed_trades if t.outcome == TradeOutcome.BREAKEVEN]

            # Basic counts
            total = len(closed_trades)
            win_count = len(wins)
            loss_count = len(losses)

            # Win rate
            win_rate = win_count / total if total > 0 else 0.0

            # Rolling win rate (last N trades)
            window = self._config.rolling_trade_window
            recent = closed_trades[-window:] if len(closed_trades) >= window else closed_trades
            recent_wins = sum(1 for t in recent if t.outcome == TradeOutcome.WIN)
            rolling_win_rate = recent_wins / len(recent) if recent else 0.0

            # PnL metrics
            total_pnl = sum(t.realized_pnl for t in closed_trades)
            total_fees = sum(t.fees for t in closed_trades)
            net_pnl = sum(t.net_pnl for t in closed_trades)

            # Win/loss metrics
            total_wins = sum(t.net_pnl for t in wins)
            total_losses = sum(t.net_pnl for t in losses)
            avg_win = total_wins / win_count if win_count > 0 else 0.0
            avg_loss = total_losses / loss_count if loss_count > 0 else 0.0
            largest_win = max((t.net_pnl for t in wins), default=0.0)
            largest_loss = min((t.net_pnl for t in losses), default=0.0)

            # Win/loss ratio
            win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

            # Profit factor
            profit_factor = abs(total_wins / total_losses) if total_losses != 0 else float('inf')

            # Drawdown
            current_dd = self._calculate_current_drawdown()
            max_dd = self._calculate_max_drawdown()
            days_in_dd = self._calculate_days_in_drawdown()

            # Sharpe ratios
            sharpe_30d = self._calculate_sharpe(30)
            sharpe_90d = self._calculate_sharpe(90)

            # Hold time and R-multiple
            hold_times = [t.hold_time_ms for t in closed_trades if t.hold_time_ms]
            avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0

            r_multiples = [t.r_multiple for t in closed_trades if t.r_multiple is not None]
            avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0

            # Strategy breakdown
            by_strategy = {}
            for strategy, strat_trades in self._strategy_trades.items():
                strat_closed = [t for t in strat_trades if t.outcome != TradeOutcome.OPEN]
                strat_wins = [t for t in strat_closed if t.outcome == TradeOutcome.WIN]
                strat_pnl = sum(t.net_pnl for t in strat_closed)

                by_strategy[strategy] = {
                    'trades': len(strat_closed),
                    'wins': len(strat_wins),
                    'win_rate': len(strat_wins) / len(strat_closed) if strat_closed else 0,
                    'total_pnl': strat_pnl,
                }

            return PerformanceSnapshot(
                timestamp_ns=self._now_ns(),
                total_trades=total,
                winning_trades=win_count,
                losing_trades=loss_count,
                breakeven_trades=len(breakevens),
                open_trades=0,  # Journal tracks this
                win_rate=win_rate,
                rolling_win_rate_20=rolling_win_rate,
                total_pnl=total_pnl,
                total_fees=total_fees,
                net_pnl=net_pnl,
                daily_pnl=self._daily_pnl,
                weekly_pnl=self._weekly_pnl,
                monthly_pnl=self._monthly_pnl,
                avg_win=avg_win,
                avg_loss=avg_loss,
                largest_win=largest_win,
                largest_loss=largest_loss,
                win_loss_ratio=win_loss_ratio,
                profit_factor=profit_factor,
                sharpe_ratio_30d=sharpe_30d,
                sharpe_ratio_90d=sharpe_90d,
                current_drawdown_pct=current_dd,
                max_drawdown_pct=max_dd,
                days_in_drawdown=days_in_dd,
                avg_hold_time_ms=avg_hold,
                avg_r_multiple=avg_r,
                by_strategy=by_strategy,
            )

    def _calculate_current_drawdown(self) -> float:
        """Calculate current drawdown from peak."""
        if self._peak_capital <= 0:
            return 0.0
        return (self._peak_capital - self._current_capital) / self._peak_capital

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum historical drawdown."""
        if not self._trades:
            return 0.0

        capital = self._initial_capital
        peak = capital
        max_dd = 0.0

        for trade in self._trades:
            capital += trade.net_pnl
            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_days_in_drawdown(self) -> int:
        """Calculate days in current drawdown."""
        if self._drawdown_start_time is None:
            return 0
        elapsed_ns = self._now_ns() - self._drawdown_start_time
        return int(elapsed_ns / (24 * 3600 * 1_000_000_000))

    def _calculate_sharpe(self, days: int) -> float:
        """
        Calculate Sharpe ratio over specified days.

        Sharpe = mean(returns) / std(returns) * sqrt(252)
        Assumes risk-free rate = 0
        """
        returns = list(self._daily_returns)[-days:]
        if len(returns) < 5:  # Need minimum data
            return 0.0

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_return = math.sqrt(variance) if variance > 0 else 0.0

        if std_return == 0:
            return 0.0

        # Annualize: sqrt(252 trading days)
        return (mean_return / std_return) * math.sqrt(252)

    def get_win_rate(self) -> float:
        """Get overall win rate."""
        with self._lock:
            closed = [t for t in self._trades if t.outcome != TradeOutcome.OPEN]
            if not closed:
                return 0.0
            wins = sum(1 for t in closed if t.outcome == TradeOutcome.WIN)
            return wins / len(closed)

    def get_rolling_win_rate(self, window: int = 20) -> float:
        """Get rolling win rate over last N trades."""
        with self._lock:
            closed = [t for t in self._trades if t.outcome != TradeOutcome.OPEN]
            recent = closed[-window:]
            if not recent:
                return 0.0
            wins = sum(1 for t in recent if t.outcome == TradeOutcome.WIN)
            return wins / len(recent)

    def get_expectancy(self) -> float:
        """
        Calculate expectancy (expected value per trade).

        Expectancy = (Win% * Avg Win) + (Loss% * Avg Loss)
        """
        with self._lock:
            closed = [t for t in self._trades if t.outcome != TradeOutcome.OPEN]
            if not closed:
                return 0.0

            wins = [t for t in closed if t.outcome == TradeOutcome.WIN]
            losses = [t for t in closed if t.outcome == TradeOutcome.LOSS]

            win_pct = len(wins) / len(closed)
            loss_pct = len(losses) / len(closed)

            avg_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0

            return (win_pct * avg_win) + (loss_pct * avg_loss)

    def get_current_capital(self) -> float:
        """Get current capital."""
        return self._current_capital

    def get_total_return(self) -> float:
        """Get total return percentage."""
        if self._initial_capital <= 0:
            return 0.0
        return (self._current_capital - self._initial_capital) / self._initial_capital

    def get_strategy_stats(self, strategy: str) -> Optional[Dict]:
        """Get performance stats for a specific strategy."""
        with self._lock:
            if strategy not in self._strategy_trades:
                return None

            trades = self._strategy_trades[strategy]
            closed = [t for t in trades if t.outcome != TradeOutcome.OPEN]
            if not closed:
                return {'trades': 0, 'wins': 0, 'win_rate': 0, 'pnl': 0}

            wins = [t for t in closed if t.outcome == TradeOutcome.WIN]
            total_pnl = sum(t.net_pnl for t in closed)

            return {
                'trades': len(closed),
                'wins': len(wins),
                'win_rate': len(wins) / len(closed),
                'pnl': total_pnl,
                'avg_pnl': total_pnl / len(closed),
            }

    def check_thresholds(self) -> Dict[str, str]:
        """Check performance against thresholds."""
        issues = {}

        win_rate = self.get_win_rate()
        if win_rate < self._config.win_rate_critical:
            issues['win_rate'] = 'CRITICAL'
        elif win_rate < self._config.win_rate_warning:
            issues['win_rate'] = 'WARNING'

        snapshot = self.get_snapshot()

        if snapshot.sharpe_ratio_30d < self._config.sharpe_warning:
            issues['sharpe'] = 'WARNING'

        if snapshot.current_drawdown_pct > self._config.max_drawdown_critical:
            issues['drawdown'] = 'CRITICAL'
        elif snapshot.current_drawdown_pct > self._config.max_drawdown_warning:
            issues['drawdown'] = 'WARNING'

        return issues
