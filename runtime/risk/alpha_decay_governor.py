"""
Alpha Decay Governor.

Self-throttling strategy controller that disables trading when edge weakens.
Defensive subsystem prioritizing CAPITAL PRESERVATION over trade frequency.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from enum import Enum, auto
from collections import deque


class DecaySeverity(Enum):
    """Decay severity classification."""
    NONE = "NONE"         # No decay detected
    LOW = "LOW"           # Reduce position sizes
    MEDIUM = "MEDIUM"     # Disable specific strategy
    HIGH = "HIGH"         # Halt new entries for asset
    CRITICAL = "CRITICAL" # Halt ALL trading


class GovernorAction(Enum):
    """Actions the governor can mandate."""
    NONE = "NONE"
    REDUCE_SIZE = "REDUCE_SIZE"
    DISABLE_STRATEGY = "DISABLE_STRATEGY"
    HALT_ENTRIES = "HALT_ENTRIES"
    HALT_ALL = "HALT_ALL"


@dataclass(frozen=True)
class TradeOutcome:
    """Record of a completed trade."""
    ts_ns: int
    strategy_id: str
    symbol: str
    side: str  # "buy" or "sell"
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_bps: float
    slippage_bps: float
    hold_time_ns: int


@dataclass
class StrategyMetrics:
    """Rolling metrics for a single strategy."""
    strategy_id: str
    window_trades: int = 0
    window_wins: int = 0
    window_losses: int = 0

    total_pnl: float = 0.0
    total_pnl_bps: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    total_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0

    avg_hold_time_ns: int = 0

    @property
    def win_rate(self) -> float:
        """Win rate as fraction (0.0 to 1.0)."""
        if self.window_trades == 0:
            return 0.0
        return self.window_wins / self.window_trades

    @property
    def profit_factor(self) -> float:
        """Gross profit / gross loss."""
        if self.gross_loss == 0:
            return float('inf') if self.gross_profit > 0 else 0.0
        return self.gross_profit / abs(self.gross_loss)

    @property
    def expectancy(self) -> float:
        """Expected value per trade in basis points."""
        if self.window_trades == 0:
            return 0.0
        return self.total_pnl_bps / self.window_trades

    @property
    def avg_slippage_bps(self) -> float:
        """Average slippage in basis points."""
        if self.window_trades == 0:
            return 0.0
        return self.total_slippage_bps / self.window_trades


@dataclass(frozen=True)
class DecaySnapshot:
    """Point-in-time decay assessment for a strategy."""
    ts_ns: int
    strategy_id: str
    severity: DecaySeverity
    reason: str

    # Metrics at time of snapshot
    win_rate: float
    expectancy_bps: float
    profit_factor: float
    avg_slippage_bps: float
    sample_count: int

    # Comparison to baseline
    win_rate_change_pct: Optional[float] = None
    expectancy_change_pct: Optional[float] = None


@dataclass
class DecayThresholds:
    """Configurable thresholds for decay detection."""
    # Win rate thresholds
    min_win_rate: float = 0.40  # Below this = concerning
    critical_win_rate: float = 0.30  # Below this = critical

    # Expectancy thresholds (basis points)
    min_expectancy_bps: float = 5.0  # Below this = concerning
    critical_expectancy_bps: float = 0.0  # Below this = critical

    # Profit factor thresholds
    min_profit_factor: float = 1.2  # Below this = concerning
    critical_profit_factor: float = 1.0  # Below this = losing money

    # Slippage thresholds
    max_slippage_bps: float = 15.0  # Above this = concerning
    critical_slippage_bps: float = 30.0  # Above this = critical

    # Decay detection (comparison to baseline)
    win_rate_decay_pct: float = 20.0  # 20% drop from baseline
    expectancy_decay_pct: float = 50.0  # 50% drop from baseline

    # Sample requirements
    min_samples_for_assessment: int = 10
    min_samples_for_baseline: int = 50


class StrategyPerformanceTracker:
    """
    Tracks per-strategy performance metrics.

    Maintains rolling windows of trade outcomes and computes
    performance metrics for decay detection.
    """

    def __init__(
        self,
        window_size: int = 100,
        baseline_window_size: int = 500,
    ):
        self._window_size = window_size
        self._baseline_window_size = baseline_window_size

        # Per-strategy trade history
        self._trade_history: Dict[str, deque] = {}

        # Cached metrics
        self._current_metrics: Dict[str, StrategyMetrics] = {}
        self._baseline_metrics: Dict[str, StrategyMetrics] = {}

    def record_trade(self, outcome: TradeOutcome) -> None:
        """Record a completed trade."""
        strategy_id = outcome.strategy_id

        # Initialize if needed
        if strategy_id not in self._trade_history:
            self._trade_history[strategy_id] = deque(
                maxlen=self._baseline_window_size
            )

        self._trade_history[strategy_id].append(outcome)

        # Invalidate cached metrics
        self._current_metrics.pop(strategy_id, None)
        self._baseline_metrics.pop(strategy_id, None)

    def get_metrics(
        self,
        strategy_id: str,
        window: str = "recent",
    ) -> Optional[StrategyMetrics]:
        """
        Get metrics for a strategy.

        window: "recent" (last N trades) or "baseline" (last M trades)
        """
        if strategy_id not in self._trade_history:
            return None

        trades = self._trade_history[strategy_id]
        if len(trades) == 0:
            return None

        # Determine window
        if window == "recent":
            window_trades = list(trades)[-self._window_size:]
            cache = self._current_metrics
        else:
            window_trades = list(trades)
            cache = self._baseline_metrics

        # Check cache
        if strategy_id in cache:
            return cache[strategy_id]

        # Compute metrics
        metrics = self._compute_metrics(strategy_id, window_trades)
        cache[strategy_id] = metrics

        return metrics

    def _compute_metrics(
        self,
        strategy_id: str,
        trades: List[TradeOutcome],
    ) -> StrategyMetrics:
        """Compute metrics from trade list."""
        metrics = StrategyMetrics(strategy_id=strategy_id)
        metrics.window_trades = len(trades)

        if len(trades) == 0:
            return metrics

        total_hold_time = 0

        for trade in trades:
            if trade.pnl > 0:
                metrics.window_wins += 1
                metrics.gross_profit += trade.pnl
            else:
                metrics.window_losses += 1
                metrics.gross_loss += abs(trade.pnl)

            metrics.total_pnl += trade.pnl
            metrics.total_pnl_bps += trade.pnl_bps
            metrics.total_slippage_bps += trade.slippage_bps
            metrics.max_slippage_bps = max(
                metrics.max_slippage_bps,
                trade.slippage_bps,
            )
            total_hold_time += trade.hold_time_ns

        metrics.avg_hold_time_ns = total_hold_time // len(trades)

        return metrics

    def get_strategy_ids(self) -> List[str]:
        """Get all tracked strategy IDs."""
        return list(self._trade_history.keys())

    def get_trade_count(self, strategy_id: str) -> int:
        """Get total trade count for strategy."""
        if strategy_id not in self._trade_history:
            return 0
        return len(self._trade_history[strategy_id])


class DecaySeverityClassifier:
    """
    Classifies decay severity for strategies.

    Severity levels:
    - NONE: Performance within acceptable bounds
    - LOW: Minor degradation, reduce sizes
    - MEDIUM: Significant degradation, consider disabling
    - HIGH: Severe degradation, halt entries
    - CRITICAL: Complete breakdown, halt all trading
    """

    def __init__(self, thresholds: Optional[DecayThresholds] = None):
        self._thresholds = thresholds or DecayThresholds()

    def classify(
        self,
        current: StrategyMetrics,
        baseline: Optional[StrategyMetrics] = None,
    ) -> Tuple[DecaySeverity, str]:
        """
        Classify decay severity for a strategy.

        Returns (severity, reason) tuple.
        """
        t = self._thresholds

        # Insufficient data
        if current.window_trades < t.min_samples_for_assessment:
            return DecaySeverity.NONE, "insufficient_samples"

        # Check for CRITICAL conditions first
        if current.win_rate < t.critical_win_rate:
            return DecaySeverity.CRITICAL, f"win_rate_{current.win_rate:.2f}_below_{t.critical_win_rate}"

        if current.expectancy < t.critical_expectancy_bps:
            return DecaySeverity.CRITICAL, f"expectancy_{current.expectancy:.1f}bps_negative"

        if current.profit_factor < t.critical_profit_factor:
            return DecaySeverity.CRITICAL, f"profit_factor_{current.profit_factor:.2f}_below_1"

        if current.avg_slippage_bps > t.critical_slippage_bps:
            return DecaySeverity.CRITICAL, f"slippage_{current.avg_slippage_bps:.1f}bps_critical"

        # Check for decay compared to baseline
        if baseline is not None and baseline.window_trades >= t.min_samples_for_baseline:
            # Win rate decay
            if baseline.win_rate > 0:
                win_rate_change = (
                    (current.win_rate - baseline.win_rate) / baseline.win_rate * 100
                )
                if win_rate_change < -t.win_rate_decay_pct * 2:
                    return DecaySeverity.HIGH, f"win_rate_decay_{abs(win_rate_change):.0f}pct"
                if win_rate_change < -t.win_rate_decay_pct:
                    return DecaySeverity.MEDIUM, f"win_rate_decay_{abs(win_rate_change):.0f}pct"

            # Expectancy decay
            if baseline.expectancy > 0:
                exp_change = (
                    (current.expectancy - baseline.expectancy) / baseline.expectancy * 100
                )
                if exp_change < -t.expectancy_decay_pct * 1.5:
                    return DecaySeverity.HIGH, f"expectancy_decay_{abs(exp_change):.0f}pct"
                if exp_change < -t.expectancy_decay_pct:
                    return DecaySeverity.MEDIUM, f"expectancy_decay_{abs(exp_change):.0f}pct"

        # Check for concerning (but not critical) levels
        if current.win_rate < t.min_win_rate:
            return DecaySeverity.LOW, f"win_rate_{current.win_rate:.2f}_low"

        if current.expectancy < t.min_expectancy_bps:
            return DecaySeverity.LOW, f"expectancy_{current.expectancy:.1f}bps_low"

        if current.profit_factor < t.min_profit_factor:
            return DecaySeverity.LOW, f"profit_factor_{current.profit_factor:.2f}_low"

        if current.avg_slippage_bps > t.max_slippage_bps:
            return DecaySeverity.LOW, f"slippage_{current.avg_slippage_bps:.1f}bps_elevated"

        return DecaySeverity.NONE, "performance_acceptable"


@dataclass(frozen=True)
class GovernorDecision:
    """Decision from the Alpha Decay Governor."""
    ts_ns: int
    action: GovernorAction
    severity: DecaySeverity
    reason: str

    # Affected scope
    strategy_id: Optional[str] = None
    symbol: Optional[str] = None

    # Size adjustment (1.0 = full, 0.0 = blocked)
    size_factor: float = 1.0


class AlphaDecayGovernor:
    """
    Self-throttling strategy controller.

    Monitors strategy performance and takes defensive actions:
    - LOW: Reduce position sizes by 50%
    - MEDIUM: Disable specific strategy
    - HIGH: Halt new entries for affected symbol
    - CRITICAL: Halt ALL trading
    """

    def __init__(
        self,
        tracker: StrategyPerformanceTracker,
        classifier: DecaySeverityClassifier,
        on_action: Optional[Callable[[GovernorDecision], None]] = None,
    ):
        self._tracker = tracker
        self._classifier = classifier
        self._on_action = on_action

        # State tracking
        self._disabled_strategies: Dict[str, int] = {}  # strategy_id -> disable_ts_ns
        self._halted_symbols: Dict[str, int] = {}  # symbol -> halt_ts_ns
        self._global_halt_ts_ns: Optional[int] = None

        # Decision history
        self._decisions: deque = deque(maxlen=1000)

        # Cooldowns (nanoseconds)
        self._strategy_cooldown_ns = 300_000_000_000  # 5 minutes
        self._symbol_cooldown_ns = 600_000_000_000    # 10 minutes
        self._global_cooldown_ns = 1800_000_000_000   # 30 minutes

    def evaluate_strategy(
        self,
        strategy_id: str,
        now_ns: Optional[int] = None,
    ) -> GovernorDecision:
        """
        Evaluate a single strategy and return decision.
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        # Get metrics
        current = self._tracker.get_metrics(strategy_id, "recent")
        baseline = self._tracker.get_metrics(strategy_id, "baseline")

        if current is None:
            return GovernorDecision(
                ts_ns=now_ns,
                action=GovernorAction.NONE,
                severity=DecaySeverity.NONE,
                reason="no_data",
                strategy_id=strategy_id,
            )

        # Classify decay
        severity, reason = self._classifier.classify(current, baseline)

        # Determine action
        action, size_factor = self._severity_to_action(severity)

        decision = GovernorDecision(
            ts_ns=now_ns,
            action=action,
            severity=severity,
            reason=reason,
            strategy_id=strategy_id,
            size_factor=size_factor,
        )

        # Apply state changes
        self._apply_decision(decision)

        return decision

    def evaluate_all(
        self,
        now_ns: Optional[int] = None,
    ) -> List[GovernorDecision]:
        """
        Evaluate all tracked strategies.
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        decisions = []

        for strategy_id in self._tracker.get_strategy_ids():
            decision = self.evaluate_strategy(strategy_id, now_ns)
            decisions.append(decision)

        # Check for global halt condition
        critical_count = sum(
            1 for d in decisions
            if d.severity == DecaySeverity.CRITICAL
        )

        if critical_count >= 2:  # Multiple strategies in critical state
            global_decision = GovernorDecision(
                ts_ns=now_ns,
                action=GovernorAction.HALT_ALL,
                severity=DecaySeverity.CRITICAL,
                reason=f"multiple_strategies_critical_{critical_count}",
                size_factor=0.0,
            )
            self._apply_decision(global_decision)
            decisions.append(global_decision)

        return decisions

    def _severity_to_action(
        self,
        severity: DecaySeverity,
    ) -> Tuple[GovernorAction, float]:
        """Map severity to action and size factor."""
        mapping = {
            DecaySeverity.NONE: (GovernorAction.NONE, 1.0),
            DecaySeverity.LOW: (GovernorAction.REDUCE_SIZE, 0.5),
            DecaySeverity.MEDIUM: (GovernorAction.DISABLE_STRATEGY, 0.0),
            DecaySeverity.HIGH: (GovernorAction.HALT_ENTRIES, 0.0),
            DecaySeverity.CRITICAL: (GovernorAction.HALT_ALL, 0.0),
        }
        return mapping[severity]

    def _apply_decision(self, decision: GovernorDecision) -> None:
        """Apply decision and update state."""
        self._decisions.append(decision)

        if decision.action == GovernorAction.DISABLE_STRATEGY:
            if decision.strategy_id:
                self._disabled_strategies[decision.strategy_id] = decision.ts_ns

        elif decision.action == GovernorAction.HALT_ENTRIES:
            if decision.symbol:
                self._halted_symbols[decision.symbol] = decision.ts_ns
            elif decision.strategy_id:
                # Halt entries for all symbols this strategy trades
                self._disabled_strategies[decision.strategy_id] = decision.ts_ns

        elif decision.action == GovernorAction.HALT_ALL:
            self._global_halt_ts_ns = decision.ts_ns

        # Notify callback
        if self._on_action and decision.action != GovernorAction.NONE:
            self._on_action(decision)

    def is_strategy_enabled(
        self,
        strategy_id: str,
        now_ns: Optional[int] = None,
    ) -> bool:
        """Check if strategy is currently enabled."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        # Check global halt
        if self._global_halt_ts_ns is not None:
            if now_ns - self._global_halt_ts_ns < self._global_cooldown_ns:
                return False

        # Check strategy-specific disable
        if strategy_id in self._disabled_strategies:
            disable_ts = self._disabled_strategies[strategy_id]
            if now_ns - disable_ts < self._strategy_cooldown_ns:
                return False

        return True

    def is_symbol_allowed(
        self,
        symbol: str,
        now_ns: Optional[int] = None,
    ) -> bool:
        """Check if entries are allowed for symbol."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        # Check global halt
        if self._global_halt_ts_ns is not None:
            if now_ns - self._global_halt_ts_ns < self._global_cooldown_ns:
                return False

        # Check symbol-specific halt
        if symbol in self._halted_symbols:
            halt_ts = self._halted_symbols[symbol]
            if now_ns - halt_ts < self._symbol_cooldown_ns:
                return False

        return True

    def get_size_factor(
        self,
        strategy_id: str,
        now_ns: Optional[int] = None,
    ) -> float:
        """Get size adjustment factor for strategy."""
        if not self.is_strategy_enabled(strategy_id, now_ns):
            return 0.0

        decision = self.evaluate_strategy(strategy_id, now_ns)
        return decision.size_factor

    def allows_trading(self, now_ns: Optional[int] = None) -> bool:
        """Check if any trading is allowed."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        if self._global_halt_ts_ns is not None:
            if now_ns - self._global_halt_ts_ns < self._global_cooldown_ns:
                return False

        return True

    def get_decay_snapshot(
        self,
        strategy_id: str,
        now_ns: Optional[int] = None,
    ) -> Optional[DecaySnapshot]:
        """Get current decay snapshot for strategy."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        current = self._tracker.get_metrics(strategy_id, "recent")
        baseline = self._tracker.get_metrics(strategy_id, "baseline")

        if current is None:
            return None

        severity, reason = self._classifier.classify(current, baseline)

        # Compute change percentages
        win_rate_change = None
        exp_change = None

        if baseline is not None and baseline.window_trades > 0:
            if baseline.win_rate > 0:
                win_rate_change = (
                    (current.win_rate - baseline.win_rate) / baseline.win_rate * 100
                )
            if baseline.expectancy > 0:
                exp_change = (
                    (current.expectancy - baseline.expectancy) / baseline.expectancy * 100
                )

        return DecaySnapshot(
            ts_ns=now_ns,
            strategy_id=strategy_id,
            severity=severity,
            reason=reason,
            win_rate=current.win_rate,
            expectancy_bps=current.expectancy,
            profit_factor=current.profit_factor,
            avg_slippage_bps=current.avg_slippage_bps,
            sample_count=current.window_trades,
            win_rate_change_pct=win_rate_change,
            expectancy_change_pct=exp_change,
        )

    def get_recent_decisions(self, limit: int = 100) -> List[GovernorDecision]:
        """Get recent governor decisions."""
        return list(self._decisions)[-limit:]

    def reset_strategy(self, strategy_id: str) -> bool:
        """Reset disabled state for a strategy. Returns True if was disabled."""
        if strategy_id in self._disabled_strategies:
            del self._disabled_strategies[strategy_id]
            return True
        return False

    def reset_all(self, operator_confirmation: str) -> bool:
        """Reset all halts. Requires confirmation phrase."""
        if operator_confirmation != "CONFIRM RESET DECAY GOVERNOR":
            return False

        self._disabled_strategies.clear()
        self._halted_symbols.clear()
        self._global_halt_ts_ns = None
        return True

    def get_status(self) -> Dict:
        """Get current governor status."""
        return {
            "allows_trading": self.allows_trading(),
            "disabled_strategies": list(self._disabled_strategies.keys()),
            "halted_symbols": list(self._halted_symbols.keys()),
            "global_halt_active": self._global_halt_ts_ns is not None,
            "total_decisions": len(self._decisions),
        }
