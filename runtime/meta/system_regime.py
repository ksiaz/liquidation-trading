"""
System Regime Detector.

Detects when the system's edge is present, decaying, or gone.
Monitors performance vs expectations to identify regime changes.

Philosophy:
- An edge is not permanent; market adaptation erodes advantages
- Track performance vs expectations, not just absolute performance
- Distinguish between variance and systematic edge decay
- Trigger defensive actions before losses accumulate
"""

import time
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from threading import RLock
from collections import deque

from .types import SystemRegime, EdgeMetrics


@dataclass
class RegimeConfig:
    """Configuration for system regime detection."""
    # Expectations (should be set from historical validation)
    expected_win_rate: float = 0.55
    expected_profit_factor: float = 1.5
    expected_sharpe: float = 1.0

    # Variance bounds (for determining if performance is within normal range)
    win_rate_std: float = 0.08       # Expected standard deviation of win rate
    profit_factor_std: float = 0.3   # Expected std of profit factor

    # Detection thresholds
    edge_present_zscore: float = -1.0   # Above this = edge present
    edge_decaying_zscore: float = -2.0  # Below this = decaying
    edge_gone_zscore: float = -3.0      # Below this = edge gone

    # Windows
    min_trades_for_assessment: int = 20
    assessment_window_trades: int = 50
    regime_confirmation_trades: int = 30  # Trades needed to confirm regime change

    # Decay detection
    decay_slope_threshold: float = -0.005  # Negative slope in rolling win rate


class SystemRegimeDetector:
    """
    Detects the regime of the system's edge.

    Tracks whether the system is performing as designed (edge present),
    showing signs of degradation (edge decaying), or has lost its edge.

    This is different from market regime detection - this detects
    whether YOUR SYSTEM'S ASSUMPTIONS about the market still hold.

    Usage:
        detector = SystemRegimeDetector()

        # Record trade outcomes
        detector.record_trade(won=True, pnl=150.0)
        detector.record_trade(won=False, pnl=-80.0)

        # Check regime
        regime = detector.get_regime()
        if regime == SystemRegime.EDGE_DECAYING:
            reduce_position_sizes()
        elif regime == SystemRegime.EDGE_GONE:
            halt_trading()
    """

    def __init__(
        self,
        config: RegimeConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or RegimeConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Trade history: (timestamp_ns, won: bool, pnl: float)
        self._trades: deque = deque(maxlen=500)

        # Regime tracking
        self._current_regime = SystemRegime.UNKNOWN
        self._regime_since_ns: Optional[int] = None
        self._regime_confidence: float = 0.0

        # Metrics history
        self._metrics_history: List[EdgeMetrics] = []

        # Rolling statistics
        self._rolling_win_rates: deque = deque(maxlen=20)  # For slope calculation

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def record_trade(
        self,
        won: bool,
        pnl: float,
        timestamp_ns: int = None
    ):
        """
        Record a trade outcome.

        Args:
            won: Whether the trade was profitable
            pnl: Profit/loss amount
            timestamp_ns: Trade timestamp
        """
        timestamp_ns = timestamp_ns or self._now_ns()

        with self._lock:
            self._trades.append((timestamp_ns, won, pnl))

            # Update rolling win rate history periodically
            if len(self._trades) % 10 == 0:
                recent = list(self._trades)[-self._config.assessment_window_trades:]
                if len(recent) >= self._config.min_trades_for_assessment:
                    win_rate = sum(1 for _, w, _ in recent if w) / len(recent)
                    self._rolling_win_rates.append(win_rate)

    def get_regime(self) -> SystemRegime:
        """
        Assess current system regime.

        Returns:
            SystemRegime indicating current state
        """
        with self._lock:
            trades = list(self._trades)

            if len(trades) < self._config.min_trades_for_assessment:
                return SystemRegime.UNKNOWN

            # Get recent window
            recent = trades[-self._config.assessment_window_trades:]

            # Calculate observed metrics
            wins = sum(1 for _, w, _ in recent if w)
            losses = len(recent) - wins
            observed_win_rate = wins / len(recent)

            total_profit = sum(pnl for _, w, pnl in recent if w)
            total_loss = abs(sum(pnl for _, w, pnl in recent if not w))
            observed_pf = total_profit / total_loss if total_loss > 0 else float('inf')

            # Calculate z-scores
            win_rate_zscore = (
                (observed_win_rate - self._config.expected_win_rate) /
                self._config.win_rate_std
            )

            # Calculate edge decay slope
            decay_rate = self._calculate_decay_slope()

            # Store metrics
            metrics = EdgeMetrics(
                timestamp_ns=self._now_ns(),
                expected_win_rate=self._config.expected_win_rate,
                observed_win_rate=observed_win_rate,
                win_rate_zscore=win_rate_zscore,
                expected_profit_factor=self._config.expected_profit_factor,
                observed_profit_factor=observed_pf,
                information_ratio=0.0,  # Would need benchmark
                edge_decay_rate=decay_rate,
                trade_count=len(recent),
                period_days=self._calculate_period_days(recent),
            )
            self._metrics_history.append(metrics)

            # Determine regime
            new_regime = self._assess_regime(win_rate_zscore, decay_rate, observed_pf)

            # Update regime with confirmation logic
            self._update_regime(new_regime, len(trades))

            return self._current_regime

    def _assess_regime(
        self,
        win_rate_zscore: float,
        decay_rate: float,
        profit_factor: float
    ) -> SystemRegime:
        """Assess regime from metrics."""
        # Check for edge gone (worst case first)
        if win_rate_zscore < self._config.edge_gone_zscore:
            return SystemRegime.EDGE_GONE

        # Check for active decay
        if decay_rate < self._config.decay_slope_threshold:
            return SystemRegime.EDGE_DECAYING

        # Check for decaying based on z-score
        if win_rate_zscore < self._config.edge_decaying_zscore:
            return SystemRegime.EDGE_DECAYING

        # Check if edge is present
        if win_rate_zscore > self._config.edge_present_zscore:
            return SystemRegime.EDGE_PRESENT

        # Ambiguous - might be regime change
        return SystemRegime.REGIME_CHANGE

    def _update_regime(self, new_regime: SystemRegime, total_trades: int):
        """Update regime with confirmation logic."""
        if new_regime == self._current_regime:
            # Same regime, increase confidence
            self._regime_confidence = min(1.0, self._regime_confidence + 0.1)
            return

        # Regime change detected
        if self._current_regime == SystemRegime.UNKNOWN:
            # First assessment
            self._current_regime = new_regime
            self._regime_since_ns = self._now_ns()
            self._regime_confidence = 0.5
            self._logger.info(f"Initial regime: {new_regime.name}")
            return

        # Require confirmation before switching
        # Decay confidence in current regime
        self._regime_confidence -= 0.2

        if self._regime_confidence <= 0:
            old_regime = self._current_regime
            self._current_regime = new_regime
            self._regime_since_ns = self._now_ns()
            self._regime_confidence = 0.5

            self._logger.warning(
                f"REGIME CHANGE: {old_regime.name} -> {new_regime.name}"
            )

            if new_regime == SystemRegime.EDGE_GONE:
                self._logger.error(
                    "CRITICAL: System edge appears to be gone. "
                    "Review assumptions and consider halting."
                )
            elif new_regime == SystemRegime.EDGE_DECAYING:
                self._logger.warning(
                    "System edge is decaying. Consider reducing exposure."
                )

    def _calculate_decay_slope(self) -> float:
        """Calculate slope of rolling win rate (edge decay indicator)."""
        if len(self._rolling_win_rates) < 5:
            return 0.0

        rates = list(self._rolling_win_rates)
        n = len(rates)

        # Simple linear regression slope
        x_mean = (n - 1) / 2
        y_mean = sum(rates) / n

        numerator = sum((i - x_mean) * (r - y_mean) for i, r in enumerate(rates))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _calculate_period_days(self, trades: List[Tuple]) -> int:
        """Calculate period covered by trades in days."""
        if len(trades) < 2:
            return 0
        first_ts = trades[0][0]
        last_ts = trades[-1][0]
        return int((last_ts - first_ts) / (24 * 3600 * 1_000_000_000))

    def get_current_metrics(self) -> Optional[EdgeMetrics]:
        """Get most recent edge metrics."""
        with self._lock:
            if not self._metrics_history:
                return None
            return self._metrics_history[-1]

    def get_regime_info(self) -> Dict:
        """Get current regime information."""
        with self._lock:
            days_in_regime = 0
            if self._regime_since_ns:
                days_in_regime = int(
                    (self._now_ns() - self._regime_since_ns) /
                    (24 * 3600 * 1_000_000_000)
                )

            return {
                'regime': self._current_regime.name,
                'confidence': self._regime_confidence,
                'since_ns': self._regime_since_ns,
                'days_in_regime': days_in_regime,
                'trade_count': len(self._trades),
            }

    def get_summary(self) -> Dict:
        """Get detector summary."""
        with self._lock:
            metrics = self.get_current_metrics()
            regime_info = self.get_regime_info()

            return {
                'regime': regime_info,
                'metrics': metrics.to_dict() if metrics else None,
                'rolling_win_rates': list(self._rolling_win_rates),
                'decay_slope': self._calculate_decay_slope(),
                'total_trades': len(self._trades),
            }

    def should_halt(self) -> bool:
        """Check if trading should be halted based on regime."""
        return self._current_regime == SystemRegime.EDGE_GONE

    def should_reduce_exposure(self) -> bool:
        """Check if exposure should be reduced."""
        return self._current_regime in (
            SystemRegime.EDGE_DECAYING,
            SystemRegime.REGIME_CHANGE
        )

    def reset(self):
        """Reset detector state."""
        with self._lock:
            self._trades.clear()
            self._rolling_win_rates.clear()
            self._metrics_history.clear()
            self._current_regime = SystemRegime.UNKNOWN
            self._regime_since_ns = None
            self._regime_confidence = 0.0

    def set_expectations(
        self,
        expected_win_rate: float = None,
        expected_profit_factor: float = None,
        win_rate_std: float = None
    ):
        """Update performance expectations (e.g., from backtesting)."""
        if expected_win_rate is not None:
            self._config.expected_win_rate = expected_win_rate
        if expected_profit_factor is not None:
            self._config.expected_profit_factor = expected_profit_factor
        if win_rate_std is not None:
            self._config.win_rate_std = win_rate_std

        self._logger.info(
            f"Updated expectations: win_rate={self._config.expected_win_rate}, "
            f"pf={self._config.expected_profit_factor}"
        )
