"""
Latency-Aware Trade Gating.

Execution viability filter that blocks trades when latency degrades edge.
Defensive subsystem prioritizing SURVIVABILITY over trade frequency.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import Enum, auto

from runtime.analytics.windowed_metrics import WindowedMetricsCollector, PercentileStats


class ExecutionState(Enum):
    """Execution environment classification."""
    FAST = "FAST"           # P95 < 50ms, minimal jitter
    NORMAL = "NORMAL"       # P95 < 100ms, acceptable jitter
    DEGRADED = "DEGRADED"   # P95 < 200ms, elevated jitter
    STRESSED = "STRESSED"   # P95 < 500ms, high jitter
    BROKEN = "BROKEN"       # P95 >= 500ms or failures


class GatingDecision(Enum):
    """Trade gating decision types."""
    ALLOW = "ALLOW"
    REDUCE_SIZE = "REDUCE_SIZE"
    DELAY = "DELAY"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class LatencySnapshot:
    """Point-in-time latency measurements."""
    ts_ns: int
    window_name: str
    sample_count: int

    # Detection to fill latency
    p50_ns: int
    p75_ns: int
    p95_ns: int
    p99_ns: int
    max_ns: int
    mean_ns: int

    # Derived metrics
    volatility_ns: float  # Standard deviation
    jitter_coefficient: float  # Coefficient of variation (std/mean)

    @property
    def p50_ms(self) -> float:
        return self.p50_ns / 1_000_000

    @property
    def p95_ms(self) -> float:
        return self.p95_ns / 1_000_000

    @property
    def p99_ms(self) -> float:
        return self.p99_ns / 1_000_000


@dataclass(frozen=True)
class SlippageSnapshot:
    """Point-in-time slippage measurements."""
    ts_ns: int
    window_name: str
    sample_count: int

    mean_bps: float
    p50_bps: float
    p75_bps: float
    p95_bps: float
    p99_bps: float
    max_bps: float


@dataclass(frozen=True)
class LatencyTrend:
    """Latency trend analysis."""
    ts_ns: int
    recent_window: str
    baseline_window: str

    recent_p95_ns: int
    baseline_p95_ns: int
    change_pct: float

    # Trend direction
    is_rising: bool
    slope_ns_per_hour: float  # Estimated rate of change


@dataclass(frozen=True)
class GatingResult:
    """Complete gating decision with context."""
    decision: GatingDecision
    latency_snapshot: Optional[LatencySnapshot]
    slippage_snapshot: Optional[SlippageSnapshot]
    execution_state: ExecutionState
    reason: str
    ts_ns: int

    # Size adjustment factor (1.0 = full size, 0.5 = half, etc.)
    size_factor: float = 1.0

    # Delay recommendation in nanoseconds
    delay_ns: int = 0


@dataclass
class LatencyThresholds:
    """Configurable thresholds for latency gating."""
    # P95 thresholds for state classification (nanoseconds)
    fast_p95_ns: int = 50_000_000       # 50ms
    normal_p95_ns: int = 100_000_000    # 100ms
    degraded_p95_ns: int = 200_000_000  # 200ms
    stressed_p95_ns: int = 500_000_000  # 500ms

    # Jitter thresholds (coefficient of variation)
    low_jitter: float = 0.3
    medium_jitter: float = 0.5
    high_jitter: float = 0.8

    # Slippage thresholds (basis points)
    acceptable_slippage_bps: float = 10.0
    concerning_slippage_bps: float = 25.0
    critical_slippage_bps: float = 50.0

    # Trend thresholds
    rising_trend_pct: float = 20.0  # 20% increase triggers concern

    # Minimum samples required for decisions
    min_samples: int = 10


class LatencyHealthModel:
    """
    Computes rolling health signals from latency metrics.

    Tracks:
    - Detection to fill latency percentiles
    - Submit to ack latency
    - Ack to fill latency
    - Slippage distribution
    - Latency volatility and jitter
    - Trend slope
    """

    def __init__(
        self,
        windowed_metrics: WindowedMetricsCollector,
        thresholds: Optional[LatencyThresholds] = None,
    ):
        self._metrics = windowed_metrics
        self._thresholds = thresholds or LatencyThresholds()

        # Metric names we track
        self._latency_metric = "detection_to_fill_latency_ns"
        self._submit_ack_metric = "submit_to_ack_latency_ns"
        self._ack_fill_metric = "ack_to_fill_latency_ns"
        self._slippage_metric = "slippage_bps"

    def get_latency_snapshot(
        self,
        window_name: str = "5min",
        now_ns: Optional[int] = None,
    ) -> Optional[LatencySnapshot]:
        """Get current latency snapshot for window."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        stats = self._metrics.get_stats(
            self._latency_metric,
            window_name,
            now_ns,
        )

        if stats is None or stats.sample_count < self._thresholds.min_samples:
            return None

        # Compute volatility and jitter
        volatility = self._compute_volatility(stats)
        jitter = volatility / stats.mean if stats.mean > 0 else 0.0

        return LatencySnapshot(
            ts_ns=now_ns,
            window_name=window_name,
            sample_count=stats.sample_count,
            p50_ns=int(stats.p50),
            p75_ns=int(stats.p75),
            p95_ns=int(stats.p95),
            p99_ns=int(stats.p99),
            max_ns=int(stats.max_value),
            mean_ns=int(stats.mean),
            volatility_ns=volatility,
            jitter_coefficient=jitter,
        )

    def get_slippage_snapshot(
        self,
        window_name: str = "5min",
        now_ns: Optional[int] = None,
    ) -> Optional[SlippageSnapshot]:
        """Get current slippage snapshot for window."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        stats = self._metrics.get_stats(
            self._slippage_metric,
            window_name,
            now_ns,
        )

        if stats is None or stats.sample_count < self._thresholds.min_samples:
            return None

        return SlippageSnapshot(
            ts_ns=now_ns,
            window_name=window_name,
            sample_count=stats.sample_count,
            mean_bps=stats.mean,
            p50_bps=stats.p50,
            p75_bps=stats.p75,
            p95_bps=stats.p95,
            p99_bps=stats.p99,
            max_bps=stats.max_value,
        )

    def get_latency_trend(
        self,
        recent_window: str = "5min",
        baseline_window: str = "1hour",
        now_ns: Optional[int] = None,
    ) -> Optional[LatencyTrend]:
        """Compute latency trend between windows."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        comparison = self._metrics.compare_windows(
            self._latency_metric,
            recent_window,
            baseline_window,
            stat="p95",
            now_ns=now_ns,
        )

        if comparison is None:
            return None

        recent_val, baseline_val, change_pct = comparison

        # Estimate slope (rough: assumes 1 hour baseline)
        # This is simplified - real implementation would track history
        slope_ns_per_hour = (recent_val - baseline_val)

        return LatencyTrend(
            ts_ns=now_ns,
            recent_window=recent_window,
            baseline_window=baseline_window,
            recent_p95_ns=int(recent_val),
            baseline_p95_ns=int(baseline_val),
            change_pct=change_pct,
            is_rising=change_pct > 0,
            slope_ns_per_hour=slope_ns_per_hour,
        )

    def _compute_volatility(self, stats: PercentileStats) -> float:
        """Estimate volatility from percentile spread."""
        # Use semi-IQR (p75 - p50) as proxy for standard deviation
        # For normal distribution: semi-IQR ≈ 0.67 * std, so std ≈ semi-IQR / 0.67
        semi_iqr = stats.p75 - stats.p50
        if semi_iqr <= 0:
            return 0.0
        return semi_iqr / 0.67


class ExecutionStateClassifier:
    """
    Classifies execution environment state.

    States:
    - FAST: P95 < 50ms, low jitter
    - NORMAL: P95 < 100ms, acceptable jitter
    - DEGRADED: P95 < 200ms, elevated jitter
    - STRESSED: P95 < 500ms, high jitter
    - BROKEN: P95 >= 500ms or critical failures
    """

    def __init__(self, thresholds: Optional[LatencyThresholds] = None):
        self._thresholds = thresholds or LatencyThresholds()

    def classify(
        self,
        latency_snapshot: Optional[LatencySnapshot],
        slippage_snapshot: Optional[SlippageSnapshot] = None,
        latency_trend: Optional[LatencyTrend] = None,
    ) -> Tuple[ExecutionState, str]:
        """
        Classify current execution state.

        Returns (state, reason) tuple.
        """
        # No data = BROKEN (cannot assess)
        if latency_snapshot is None:
            return ExecutionState.BROKEN, "insufficient_latency_data"

        p95_ns = latency_snapshot.p95_ns
        jitter = latency_snapshot.jitter_coefficient
        t = self._thresholds

        # Check for BROKEN state first
        if p95_ns >= t.stressed_p95_ns:
            return ExecutionState.BROKEN, f"p95_latency_{p95_ns // 1_000_000}ms_exceeds_500ms"

        if jitter > t.high_jitter:
            return ExecutionState.BROKEN, f"jitter_{jitter:.2f}_exceeds_{t.high_jitter}"

        # Check slippage for BROKEN/STRESSED
        if slippage_snapshot is not None:
            if slippage_snapshot.p95_bps > t.critical_slippage_bps:
                return ExecutionState.BROKEN, f"slippage_p95_{slippage_snapshot.p95_bps:.1f}bps_critical"

        # Check for STRESSED
        if p95_ns >= t.degraded_p95_ns:
            return ExecutionState.STRESSED, f"p95_latency_{p95_ns // 1_000_000}ms"

        if jitter > t.medium_jitter:
            return ExecutionState.STRESSED, f"jitter_{jitter:.2f}"

        # Check trend for STRESSED
        if latency_trend is not None and latency_trend.is_rising:
            if latency_trend.change_pct > t.rising_trend_pct * 2:
                return ExecutionState.STRESSED, f"latency_rising_{latency_trend.change_pct:.1f}pct"

        # Check for DEGRADED
        if p95_ns >= t.normal_p95_ns:
            return ExecutionState.DEGRADED, f"p95_latency_{p95_ns // 1_000_000}ms"

        if jitter > t.low_jitter:
            return ExecutionState.DEGRADED, f"jitter_{jitter:.2f}"

        if slippage_snapshot is not None:
            if slippage_snapshot.p95_bps > t.concerning_slippage_bps:
                return ExecutionState.DEGRADED, f"slippage_p95_{slippage_snapshot.p95_bps:.1f}bps"

        # Check for NORMAL vs FAST
        if p95_ns >= t.fast_p95_ns:
            return ExecutionState.NORMAL, "nominal"

        return ExecutionState.FAST, "optimal"


class TradeGate:
    """
    Makes gating decisions for trade execution.

    Decision hierarchy:
    - BLOCK: Hard stop, do not execute
    - DELAY: Wait for conditions to improve
    - REDUCE_SIZE: Execute with reduced size
    - ALLOW: Full execution permitted
    """

    def __init__(
        self,
        health_model: LatencyHealthModel,
        classifier: ExecutionStateClassifier,
        thresholds: Optional[LatencyThresholds] = None,
    ):
        self._health = health_model
        self._classifier = classifier
        self._thresholds = thresholds or LatencyThresholds()

        # State to decision mapping
        self._state_decisions = {
            ExecutionState.FAST: GatingDecision.ALLOW,
            ExecutionState.NORMAL: GatingDecision.ALLOW,
            ExecutionState.DEGRADED: GatingDecision.REDUCE_SIZE,
            ExecutionState.STRESSED: GatingDecision.DELAY,
            ExecutionState.BROKEN: GatingDecision.BLOCK,
        }

        # Size factors by state
        self._size_factors = {
            ExecutionState.FAST: 1.0,
            ExecutionState.NORMAL: 1.0,
            ExecutionState.DEGRADED: 0.5,
            ExecutionState.STRESSED: 0.25,
            ExecutionState.BROKEN: 0.0,
        }

        # Delay recommendations (nanoseconds)
        self._delay_ns = {
            ExecutionState.FAST: 0,
            ExecutionState.NORMAL: 0,
            ExecutionState.DEGRADED: 5_000_000_000,   # 5 seconds
            ExecutionState.STRESSED: 30_000_000_000,  # 30 seconds
            ExecutionState.BROKEN: 60_000_000_000,    # 60 seconds
        }

    def evaluate(
        self,
        window_name: str = "5min",
        now_ns: Optional[int] = None,
    ) -> GatingResult:
        """
        Evaluate current conditions and return gating decision.
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        # Gather snapshots
        latency_snapshot = self._health.get_latency_snapshot(window_name, now_ns)
        slippage_snapshot = self._health.get_slippage_snapshot(window_name, now_ns)
        latency_trend = self._health.get_latency_trend(
            recent_window=window_name,
            baseline_window="1hour",
            now_ns=now_ns,
        )

        # Classify state
        state, reason = self._classifier.classify(
            latency_snapshot,
            slippage_snapshot,
            latency_trend,
        )

        # Get base decision from state
        decision = self._state_decisions[state]
        size_factor = self._size_factors[state]
        delay_ns = self._delay_ns[state]

        # Apply additional rules for edge cases
        decision, reason = self._apply_additional_rules(
            decision,
            reason,
            latency_snapshot,
            slippage_snapshot,
            latency_trend,
        )

        return GatingResult(
            decision=decision,
            latency_snapshot=latency_snapshot,
            slippage_snapshot=slippage_snapshot,
            execution_state=state,
            reason=reason,
            ts_ns=now_ns,
            size_factor=size_factor,
            delay_ns=delay_ns,
        )

    def _apply_additional_rules(
        self,
        decision: GatingDecision,
        reason: str,
        latency_snapshot: Optional[LatencySnapshot],
        slippage_snapshot: Optional[SlippageSnapshot],
        latency_trend: Optional[LatencyTrend],
    ) -> Tuple[GatingDecision, str]:
        """Apply additional blocking rules."""
        t = self._thresholds

        # Rule: Rising latency trend with high slope
        if latency_trend is not None:
            if latency_trend.is_rising and latency_trend.change_pct > 50:
                if decision.value < GatingDecision.DELAY.value:
                    return GatingDecision.DELAY, f"latency_trend_rising_{latency_trend.change_pct:.0f}pct"

        # Rule: Slippage exceeds EV tolerance
        if slippage_snapshot is not None:
            if slippage_snapshot.mean_bps > t.concerning_slippage_bps:
                if decision == GatingDecision.ALLOW:
                    return GatingDecision.REDUCE_SIZE, f"slippage_mean_{slippage_snapshot.mean_bps:.1f}bps"

        return decision, reason

    def allows_trade(self, window_name: str = "5min") -> bool:
        """Quick check if trading is currently allowed."""
        result = self.evaluate(window_name)
        return result.decision in (GatingDecision.ALLOW, GatingDecision.REDUCE_SIZE)

    def get_size_factor(self, window_name: str = "5min") -> float:
        """Get current size adjustment factor."""
        result = self.evaluate(window_name)
        return result.size_factor
