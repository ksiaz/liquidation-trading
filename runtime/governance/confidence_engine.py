"""
Pillar 4: Capital Confidence Engine.

Computes sub-scores that feed into the Sovereign Capital Governor's
confidence score. Each sub-score is 0.0 to 1.0.

Sub-scores:
- Edge Stability: EV consistency, profit factor stability
- Market Stability: Liquidity, volatility, spread conditions
- Execution Quality: Fill time, slippage, cancel/retry rates
- Impact Containment: Slippage vs size curve slope
- Drawdown Discipline: Current drawdown, recovery speed
- Strategy Diversification: Concentration (HHI), correlation
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from enum import Enum


@dataclass(frozen=True)
class ConfidenceSubScores:
    """Individual sub-scores feeding into confidence."""
    ts_ns: int
    edge_stability: float         # 0.0 to 1.0
    market_stability: float       # 0.0 to 1.0
    execution_quality: float      # 0.0 to 1.0
    impact_containment: float     # 0.0 to 1.0
    drawdown_discipline: float    # 0.0 to 1.0
    strategy_diversification: float  # 0.0 to 1.0

    @property
    def composite_score(self) -> float:
        """Compute weighted composite confidence score."""
        return (
            0.25 * self.edge_stability +
            0.15 * self.market_stability +
            0.20 * self.execution_quality +
            0.15 * self.impact_containment +
            0.15 * self.drawdown_discipline +
            0.10 * self.strategy_diversification
        )


@dataclass
class EdgeStabilityInputs:
    """Inputs for edge stability calculation."""
    # Expectancy (bps) over different windows
    expectancy_1d_bps: float = 0.0
    expectancy_7d_bps: float = 0.0
    expectancy_30d_bps: float = 0.0
    expectancy_90d_bps: float = 0.0

    # Profit factors over different windows
    profit_factor_1d: float = 0.0
    profit_factor_7d: float = 0.0
    profit_factor_30d: float = 0.0

    # Variance metrics
    expectancy_std_bps: float = 0.0
    sample_count: int = 0


@dataclass
class MarketStabilityInputs:
    """Inputs for market stability calculation."""
    # Liquidity metrics
    current_liquidity_ratio: float = 1.0  # vs baseline
    liquidity_trend_pct: float = 0.0      # change over period

    # Volatility metrics
    current_volatility_ratio: float = 1.0  # vs baseline
    volatility_trend_pct: float = 0.0      # change over period

    # Spread metrics
    spread_current_bps: float = 0.0
    spread_baseline_bps: float = 0.0
    spread_expansion_pct: float = 0.0

    # Funding regime
    funding_rate_current: float = 0.0
    funding_rate_baseline: float = 0.0


@dataclass
class ExecutionQualityInputs:
    """Inputs for execution quality calculation."""
    # Fill time percentiles (ms)
    fill_time_p50_ms: float = 0.0
    fill_time_p95_ms: float = 0.0
    fill_time_p99_ms: float = 0.0

    # Slippage metrics (bps)
    slippage_mean_bps: float = 0.0
    slippage_p95_bps: float = 0.0

    # Cancel/retry rates
    cancel_rate_pct: float = 0.0  # canceled / total
    retry_rate_pct: float = 0.0   # retried / total

    sample_count: int = 0


@dataclass
class ImpactContainmentInputs:
    """Inputs for impact containment calculation."""
    # Slippage vs size observations: (size_usd, slippage_bps)
    size_slippage_pairs: List[Tuple[float, float]] = field(default_factory=list)

    # Computed slope (if positive and sublinear = good)
    slope_coefficient: float = 0.0  # slippage / size slope
    is_sublinear: bool = True       # slope decreasing with size


@dataclass
class DrawdownDisciplineInputs:
    """Inputs for drawdown discipline calculation."""
    # Drawdown metrics
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    drawdown_duration_hours: float = 0.0

    # Recovery metrics
    recovery_rate_pct_per_hour: float = 0.0
    last_recovery_duration_hours: float = 0.0

    # Drawdown slope (accelerating = bad)
    drawdown_slope_pct_per_hour: float = 0.0


@dataclass
class StrategyDiversificationInputs:
    """Inputs for strategy diversification calculation."""
    # Strategy weights (strategy_id -> weight fraction)
    strategy_weights: Dict[str, float] = field(default_factory=dict)

    # Strategy correlations (if available)
    max_correlation: float = 0.0  # highest pairwise correlation

    # ROI spread
    strategy_rois: Dict[str, float] = field(default_factory=dict)


@dataclass
class ConfidenceThresholds:
    """Configurable thresholds for confidence calculations."""
    # Edge stability
    min_expectancy_bps: float = 5.0           # below this = 0 score
    target_expectancy_bps: float = 20.0       # above this = 1.0 score
    max_expectancy_variance_pct: float = 50.0  # variance / mean

    # Market stability
    high_volatility_ratio: float = 2.0        # >= this = degraded
    high_spread_expansion_pct: float = 100.0  # >= this = degraded
    low_liquidity_ratio: float = 0.5          # <= this = degraded

    # Execution quality
    max_acceptable_p95_ms: float = 100.0      # p95 fill time
    max_acceptable_slippage_bps: float = 25.0
    max_acceptable_cancel_rate: float = 0.10  # 10%
    max_acceptable_retry_rate: float = 0.05   # 5%

    # Impact containment
    acceptable_slope: float = 0.5  # slippage bps per $1000 size

    # Drawdown discipline
    warning_drawdown_pct: float = 5.0
    critical_drawdown_pct: float = 15.0
    max_drawdown_duration_hours: float = 48.0

    # Strategy diversification
    max_single_strategy_weight: float = 0.50  # 50% max in one strategy
    max_correlation_threshold: float = 0.70   # above = too correlated


class EdgeStabilityCalculator:
    """Calculates edge stability sub-score."""

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def compute(self, inputs: EdgeStabilityInputs) -> float:
        """Compute edge stability score (0.0 to 1.0)."""
        t = self._thresholds

        # Need minimum samples
        if inputs.sample_count < 10:
            return 0.0

        # Score expectancy level
        avg_expectancy = self._weighted_avg_expectancy(inputs)
        expectancy_score = self._normalize(
            avg_expectancy,
            t.min_expectancy_bps,
            t.target_expectancy_bps
        )

        # Score expectancy consistency across windows
        consistency_score = self._expectancy_consistency(inputs)

        # Score profit factor stability
        pf_score = self._profit_factor_score(inputs)

        # Score variance (lower is better)
        if avg_expectancy > 0:
            variance_ratio = inputs.expectancy_std_bps / avg_expectancy
        else:
            variance_ratio = float('inf')
        variance_score = max(0.0, 1.0 - variance_ratio / (t.max_expectancy_variance_pct / 100))

        # Weighted combination
        return (
            0.35 * expectancy_score +
            0.25 * consistency_score +
            0.25 * pf_score +
            0.15 * variance_score
        )

    def _weighted_avg_expectancy(self, inputs: EdgeStabilityInputs) -> float:
        """Compute weighted average expectancy (more recent = higher weight)."""
        weights = [0.40, 0.30, 0.20, 0.10]  # 1d, 7d, 30d, 90d
        values = [
            inputs.expectancy_1d_bps,
            inputs.expectancy_7d_bps,
            inputs.expectancy_30d_bps,
            inputs.expectancy_90d_bps,
        ]
        # Filter out zero values
        valid_pairs = [(w, v) for w, v in zip(weights, values) if v != 0]
        if not valid_pairs:
            return 0.0
        total_weight = sum(w for w, _ in valid_pairs)
        return sum(w * v for w, v in valid_pairs) / total_weight if total_weight > 0 else 0.0

    def _expectancy_consistency(self, inputs: EdgeStabilityInputs) -> float:
        """Score consistency of expectancy across time windows."""
        values = [
            inputs.expectancy_1d_bps,
            inputs.expectancy_7d_bps,
            inputs.expectancy_30d_bps,
            inputs.expectancy_90d_bps,
        ]
        valid_values = [v for v in values if v != 0]
        if len(valid_values) < 2:
            return 0.5  # Not enough data

        # All positive = good, mixed signs = bad
        all_positive = all(v > 0 for v in valid_values)
        if not all_positive:
            return 0.0

        # Check variance between windows
        mean_val = sum(valid_values) / len(valid_values)
        if mean_val <= 0:
            return 0.0
        variance = sum((v - mean_val) ** 2 for v in valid_values) / len(valid_values)
        cv = (variance ** 0.5) / mean_val if mean_val > 0 else float('inf')

        # CV < 0.3 = very consistent, CV > 1.0 = inconsistent
        return max(0.0, min(1.0, 1.0 - cv / 1.0))

    def _profit_factor_score(self, inputs: EdgeStabilityInputs) -> float:
        """Score profit factor stability."""
        values = [
            inputs.profit_factor_1d,
            inputs.profit_factor_7d,
            inputs.profit_factor_30d,
        ]
        valid_values = [v for v in values if v > 0]
        if not valid_values:
            return 0.0

        avg_pf = sum(valid_values) / len(valid_values)
        # PF < 1.0 = losing, PF 1.0-1.2 = marginal, PF > 1.5 = good, PF > 2.0 = excellent
        return self._normalize(avg_pf, 1.0, 2.0)

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range."""
        if value <= min_val:
            return 0.0
        if value >= max_val:
            return 1.0
        return (value - min_val) / (max_val - min_val)


class MarketStabilityCalculator:
    """Calculates market stability sub-score."""

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def compute(self, inputs: MarketStabilityInputs) -> float:
        """Compute market stability score (0.0 to 1.0)."""
        t = self._thresholds

        # Score liquidity (higher = better)
        liquidity_score = min(1.0, inputs.current_liquidity_ratio / 1.0)
        if inputs.current_liquidity_ratio <= t.low_liquidity_ratio:
            liquidity_score = 0.0

        # Score volatility (lower ratio to baseline = better)
        if inputs.current_volatility_ratio >= t.high_volatility_ratio:
            volatility_score = 0.0
        else:
            # 1.0 ratio = 1.0 score, 2.0 ratio = 0.0 score
            volatility_score = max(0.0, 1.0 - (inputs.current_volatility_ratio - 1.0) / (t.high_volatility_ratio - 1.0))

        # Score spread (lower expansion = better)
        if inputs.spread_expansion_pct >= t.high_spread_expansion_pct:
            spread_score = 0.0
        else:
            spread_score = max(0.0, 1.0 - inputs.spread_expansion_pct / t.high_spread_expansion_pct)

        # Weighted combination
        return (
            0.40 * liquidity_score +
            0.35 * volatility_score +
            0.25 * spread_score
        )


class ExecutionQualityCalculator:
    """Calculates execution quality sub-score."""

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def compute(self, inputs: ExecutionQualityInputs) -> float:
        """Compute execution quality score (0.0 to 1.0)."""
        t = self._thresholds

        if inputs.sample_count < 5:
            return 0.5  # Not enough data, neutral score

        # Score fill time (lower = better)
        fill_time_score = max(0.0, 1.0 - inputs.fill_time_p95_ms / t.max_acceptable_p95_ms)

        # Score slippage (lower = better)
        slippage_score = max(0.0, 1.0 - inputs.slippage_mean_bps / t.max_acceptable_slippage_bps)

        # Score cancel rate (lower = better)
        cancel_score = max(0.0, 1.0 - inputs.cancel_rate_pct / t.max_acceptable_cancel_rate)

        # Score retry rate (lower = better)
        retry_score = max(0.0, 1.0 - inputs.retry_rate_pct / t.max_acceptable_retry_rate)

        # Weighted combination
        return (
            0.30 * fill_time_score +
            0.35 * slippage_score +
            0.20 * cancel_score +
            0.15 * retry_score
        )


class ImpactContainmentCalculator:
    """Calculates impact containment sub-score."""

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def compute(self, inputs: ImpactContainmentInputs) -> float:
        """Compute impact containment score (0.0 to 1.0)."""
        t = self._thresholds

        if not inputs.size_slippage_pairs or len(inputs.size_slippage_pairs) < 3:
            return 0.5  # Not enough data, neutral score

        # Compute slope if not provided
        if inputs.slope_coefficient == 0.0:
            slope = self._compute_slope(inputs.size_slippage_pairs)
        else:
            slope = inputs.slope_coefficient

        # Score based on slope (lower = better, sublinear = bonus)
        slope_score = max(0.0, 1.0 - slope / t.acceptable_slope)

        # Bonus for sublinear behavior
        if inputs.is_sublinear:
            slope_score = min(1.0, slope_score * 1.2)

        return slope_score

    def _compute_slope(self, pairs: List[Tuple[float, float]]) -> float:
        """Compute simple linear slope from pairs."""
        if len(pairs) < 2:
            return 0.0

        # Simple OLS slope
        n = len(pairs)
        sum_x = sum(p[0] for p in pairs)
        sum_y = sum(p[1] for p in pairs)
        sum_xy = sum(p[0] * p[1] for p in pairs)
        sum_xx = sum(p[0] ** 2 for p in pairs)

        denominator = n * sum_xx - sum_x ** 2
        if denominator == 0:
            return 0.0

        return (n * sum_xy - sum_x * sum_y) / denominator


class DrawdownDisciplineCalculator:
    """Calculates drawdown discipline sub-score."""

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def compute(self, inputs: DrawdownDisciplineInputs) -> float:
        """Compute drawdown discipline score (0.0 to 1.0)."""
        t = self._thresholds

        # Score current drawdown level
        if inputs.current_drawdown_pct >= t.critical_drawdown_pct:
            dd_level_score = 0.0
        elif inputs.current_drawdown_pct >= t.warning_drawdown_pct:
            # Linear interpolation between warning and critical
            dd_level_score = 0.5 * (1.0 - (inputs.current_drawdown_pct - t.warning_drawdown_pct) /
                                    (t.critical_drawdown_pct - t.warning_drawdown_pct))
        else:
            # Below warning threshold
            dd_level_score = 1.0 - 0.5 * inputs.current_drawdown_pct / t.warning_drawdown_pct

        # Score drawdown duration
        duration_score = max(0.0, 1.0 - inputs.drawdown_duration_hours / t.max_drawdown_duration_hours)

        # Score drawdown slope (accelerating = bad)
        if inputs.drawdown_slope_pct_per_hour <= 0:
            # Recovering or flat
            slope_score = 1.0
        else:
            # Accelerating drawdown
            slope_score = max(0.0, 1.0 - inputs.drawdown_slope_pct_per_hour / 0.5)

        # Weighted combination
        return (
            0.50 * dd_level_score +
            0.25 * duration_score +
            0.25 * slope_score
        )


class StrategyDiversificationCalculator:
    """Calculates strategy diversification sub-score."""

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def compute(self, inputs: StrategyDiversificationInputs) -> float:
        """Compute strategy diversification score (0.0 to 1.0)."""
        t = self._thresholds

        if not inputs.strategy_weights:
            return 0.0  # No strategies

        # Compute HHI (Herfindahl-Hirschman Index)
        hhi = sum(w ** 2 for w in inputs.strategy_weights.values())
        # HHI = 1.0 for single strategy, 0.25 for 4 equal strategies
        # Score: lower HHI = better diversification
        hhi_score = max(0.0, 1.0 - hhi)

        # Score max single strategy weight
        max_weight = max(inputs.strategy_weights.values())
        concentration_score = max(0.0, 1.0 - max_weight / t.max_single_strategy_weight)

        # Score correlation (if available)
        if inputs.max_correlation > 0:
            correlation_score = max(0.0, 1.0 - inputs.max_correlation / t.max_correlation_threshold)
        else:
            correlation_score = 0.5  # No data, neutral

        # Weighted combination
        return (
            0.35 * hhi_score +
            0.35 * concentration_score +
            0.30 * correlation_score
        )


class ConfidenceEngine:
    """
    Central engine for computing capital confidence scores.

    Aggregates all sub-score calculators and produces final confidence.
    """

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None):
        self._thresholds = thresholds or ConfidenceThresholds()

        # Initialize calculators
        self._edge_calc = EdgeStabilityCalculator(self._thresholds)
        self._market_calc = MarketStabilityCalculator(self._thresholds)
        self._execution_calc = ExecutionQualityCalculator(self._thresholds)
        self._impact_calc = ImpactContainmentCalculator(self._thresholds)
        self._drawdown_calc = DrawdownDisciplineCalculator(self._thresholds)
        self._diversification_calc = StrategyDiversificationCalculator(self._thresholds)

    def compute_sub_scores(
        self,
        edge_inputs: Optional[EdgeStabilityInputs] = None,
        market_inputs: Optional[MarketStabilityInputs] = None,
        execution_inputs: Optional[ExecutionQualityInputs] = None,
        impact_inputs: Optional[ImpactContainmentInputs] = None,
        drawdown_inputs: Optional[DrawdownDisciplineInputs] = None,
        diversification_inputs: Optional[StrategyDiversificationInputs] = None,
        now_ns: Optional[int] = None,
    ) -> ConfidenceSubScores:
        """
        Compute all sub-scores and return composite result.

        Missing inputs result in neutral (0.5) scores for that dimension.
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        # Compute each sub-score, defaulting to 0.5 if no data
        edge_score = self._edge_calc.compute(edge_inputs) if edge_inputs else 0.5
        market_score = self._market_calc.compute(market_inputs) if market_inputs else 0.5
        execution_score = self._execution_calc.compute(execution_inputs) if execution_inputs else 0.5
        impact_score = self._impact_calc.compute(impact_inputs) if impact_inputs else 0.5
        drawdown_score = self._drawdown_calc.compute(drawdown_inputs) if drawdown_inputs else 0.5
        diversification_score = self._diversification_calc.compute(diversification_inputs) if diversification_inputs else 0.5

        return ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=edge_score,
            market_stability=market_score,
            execution_quality=execution_score,
            impact_containment=impact_score,
            drawdown_discipline=drawdown_score,
            strategy_diversification=diversification_score,
        )

    def compute_confidence(
        self,
        edge_inputs: Optional[EdgeStabilityInputs] = None,
        market_inputs: Optional[MarketStabilityInputs] = None,
        execution_inputs: Optional[ExecutionQualityInputs] = None,
        impact_inputs: Optional[ImpactContainmentInputs] = None,
        drawdown_inputs: Optional[DrawdownDisciplineInputs] = None,
        diversification_inputs: Optional[StrategyDiversificationInputs] = None,
        now_ns: Optional[int] = None,
    ) -> Tuple[float, ConfidenceSubScores]:
        """
        Compute composite confidence score.

        Returns:
            Tuple of (confidence_score, sub_scores)
        """
        sub_scores = self.compute_sub_scores(
            edge_inputs=edge_inputs,
            market_inputs=market_inputs,
            execution_inputs=execution_inputs,
            impact_inputs=impact_inputs,
            drawdown_inputs=drawdown_inputs,
            diversification_inputs=diversification_inputs,
            now_ns=now_ns,
        )

        return sub_scores.composite_score, sub_scores
