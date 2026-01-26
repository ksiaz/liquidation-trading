"""Unit tests for capital_governor.py and related components."""

import pytest
import time

from runtime.governance.confidence_engine import (
    ConfidenceEngine,
    ConfidenceSubScores,
    ConfidenceThresholds,
    EdgeStabilityInputs,
    MarketStabilityInputs,
    ExecutionQualityInputs,
    ImpactContainmentInputs,
    DrawdownDisciplineInputs,
    StrategyDiversificationInputs,
    EdgeStabilityCalculator,
    MarketStabilityCalculator,
    ExecutionQualityCalculator,
    ImpactContainmentCalculator,
    DrawdownDisciplineCalculator,
    StrategyDiversificationCalculator,
)

from runtime.governance.quarantine_controller import (
    QuarantineController,
    QuarantineState,
    QuarantineInputs,
    QuarantineTrigger,
    QuarantineThresholds,
)

from runtime.governance.capital_governor import (
    SovereignCapitalGovernor,
    CapitalGovernorDecision,
    CapitalGovernorInputs,
    CapitalGovernorThresholds,
    ScalingState,
    FreezeReason,
    AntiEuphoriaEngine,
)


# =============================================================================
# Confidence Engine Tests
# =============================================================================

class TestConfidenceSubScores:
    """Tests for ConfidenceSubScores dataclass."""

    def test_composite_score_calculation(self):
        """Should compute weighted composite score correctly."""
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=1.0,
            market_stability=1.0,
            execution_quality=1.0,
            impact_containment=1.0,
            drawdown_discipline=1.0,
            strategy_diversification=1.0,
        )
        # All 1.0 should give 1.0 (within floating point tolerance)
        assert sub_scores.composite_score == pytest.approx(1.0)

    def test_composite_score_weighted(self):
        """Should weight scores correctly."""
        now_ns = int(time.time() * 1_000_000_000)
        # Set all to 0 except edge_stability
        sub_scores = ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=1.0,  # 25% weight
            market_stability=0.0,
            execution_quality=0.0,
            impact_containment=0.0,
            drawdown_discipline=0.0,
            strategy_diversification=0.0,
        )
        assert sub_scores.composite_score == 0.25


class TestEdgeStabilityCalculator:
    """Tests for EdgeStabilityCalculator."""

    @pytest.fixture
    def calculator(self):
        return EdgeStabilityCalculator()

    def test_insufficient_samples_returns_zero(self, calculator):
        """Should return 0 with insufficient samples."""
        inputs = EdgeStabilityInputs(sample_count=5)
        assert calculator.compute(inputs) == 0.0

    def test_good_expectancy_high_score(self, calculator):
        """Should give high score for good expectancy."""
        inputs = EdgeStabilityInputs(
            expectancy_1d_bps=25.0,
            expectancy_7d_bps=22.0,
            expectancy_30d_bps=20.0,
            expectancy_90d_bps=18.0,
            profit_factor_1d=2.0,
            profit_factor_7d=1.8,
            profit_factor_30d=1.7,
            expectancy_std_bps=5.0,
            sample_count=100,
        )
        score = calculator.compute(inputs)
        assert score > 0.7

    def test_negative_expectancy_low_score(self, calculator):
        """Should give low score for negative expectancy."""
        inputs = EdgeStabilityInputs(
            expectancy_1d_bps=-5.0,
            expectancy_7d_bps=-3.0,
            expectancy_30d_bps=-2.0,
            sample_count=100,
        )
        score = calculator.compute(inputs)
        assert score < 0.3


class TestMarketStabilityCalculator:
    """Tests for MarketStabilityCalculator."""

    @pytest.fixture
    def calculator(self):
        return MarketStabilityCalculator()

    def test_normal_conditions_high_score(self, calculator):
        """Should give high score for normal conditions."""
        inputs = MarketStabilityInputs(
            current_liquidity_ratio=1.0,
            current_volatility_ratio=1.0,
            spread_expansion_pct=0.0,
        )
        score = calculator.compute(inputs)
        assert score >= 0.9

    def test_high_volatility_low_score(self, calculator):
        """Should give reduced score for high volatility."""
        inputs = MarketStabilityInputs(
            current_liquidity_ratio=1.0,
            current_volatility_ratio=2.5,  # Above threshold
            spread_expansion_pct=0.0,
        )
        score = calculator.compute(inputs)
        # Volatility score = 0, but liquidity and spread are normal
        # Result: 0.40 * 1.0 + 0.35 * 0.0 + 0.25 * 1.0 = 0.65
        assert score < 0.7  # Reduced from perfect score

    def test_low_liquidity_reduced_score(self, calculator):
        """Should give reduced score for very low liquidity."""
        inputs = MarketStabilityInputs(
            current_liquidity_ratio=0.3,  # Below threshold
            current_volatility_ratio=1.0,
            spread_expansion_pct=0.0,
        )
        score = calculator.compute(inputs)
        # Liquidity score = 0, but volatility and spread are normal
        # Result: 0.40 * 0.0 + 0.35 * 1.0 + 0.25 * 1.0 = 0.60
        assert score < 0.7  # Reduced from perfect score


class TestExecutionQualityCalculator:
    """Tests for ExecutionQualityCalculator."""

    @pytest.fixture
    def calculator(self):
        return ExecutionQualityCalculator()

    def test_insufficient_samples_neutral(self, calculator):
        """Should return neutral score with insufficient samples."""
        inputs = ExecutionQualityInputs(sample_count=2)
        assert calculator.compute(inputs) == 0.5

    def test_good_execution_high_score(self, calculator):
        """Should give high score for good execution."""
        inputs = ExecutionQualityInputs(
            fill_time_p95_ms=30.0,
            slippage_mean_bps=5.0,
            cancel_rate_pct=0.02,
            retry_rate_pct=0.01,
            sample_count=100,
        )
        score = calculator.compute(inputs)
        assert score > 0.7

    def test_high_latency_reduced_score(self, calculator):
        """Should give reduced score for high latency."""
        inputs = ExecutionQualityInputs(
            fill_time_p95_ms=250.0,  # Above threshold
            slippage_mean_bps=5.0,
            cancel_rate_pct=0.02,
            retry_rate_pct=0.01,
            sample_count=100,
        )
        score = calculator.compute(inputs)
        # Fill time score negative (capped at 0), other scores are good
        # Result is weighted average, not MIN
        assert score < 0.7  # Reduced from perfect score


class TestDrawdownDisciplineCalculator:
    """Tests for DrawdownDisciplineCalculator."""

    @pytest.fixture
    def calculator(self):
        return DrawdownDisciplineCalculator()

    def test_no_drawdown_perfect_score(self, calculator):
        """Should give perfect score with no drawdown."""
        inputs = DrawdownDisciplineInputs(
            current_drawdown_pct=0.0,
            max_drawdown_pct=5.0,
            drawdown_duration_hours=0.0,
            drawdown_slope_pct_per_hour=0.0,
        )
        score = calculator.compute(inputs)
        assert score == 1.0

    def test_critical_drawdown_low_score(self, calculator):
        """Should give low score for critical drawdown."""
        inputs = DrawdownDisciplineInputs(
            current_drawdown_pct=20.0,  # Above critical
            max_drawdown_pct=20.0,
            drawdown_duration_hours=24.0,
            drawdown_slope_pct_per_hour=0.5,
        )
        score = calculator.compute(inputs)
        assert score < 0.3


class TestStrategyDiversificationCalculator:
    """Tests for StrategyDiversificationCalculator."""

    @pytest.fixture
    def calculator(self):
        return StrategyDiversificationCalculator()

    def test_no_strategies_zero_score(self, calculator):
        """Should give zero with no strategies."""
        inputs = StrategyDiversificationInputs(strategy_weights={})
        assert calculator.compute(inputs) == 0.0

    def test_single_strategy_low_score(self, calculator):
        """Should give low score for single strategy."""
        inputs = StrategyDiversificationInputs(
            strategy_weights={"strategy_1": 1.0}
        )
        score = calculator.compute(inputs)
        assert score < 0.5

    def test_diversified_strategies_high_score(self, calculator):
        """Should give high score for diversified strategies."""
        inputs = StrategyDiversificationInputs(
            strategy_weights={
                "strategy_1": 0.25,
                "strategy_2": 0.25,
                "strategy_3": 0.25,
                "strategy_4": 0.25,
            },
            max_correlation=0.3,
        )
        score = calculator.compute(inputs)
        assert score > 0.6


class TestConfidenceEngine:
    """Tests for ConfidenceEngine."""

    @pytest.fixture
    def engine(self):
        return ConfidenceEngine()

    def test_compute_sub_scores_no_inputs(self, engine):
        """Should return neutral scores with no inputs."""
        sub_scores = engine.compute_sub_scores()
        assert sub_scores.edge_stability == 0.5
        assert sub_scores.market_stability == 0.5
        assert sub_scores.execution_quality == 0.5
        assert sub_scores.composite_score == pytest.approx(0.5)

    def test_compute_confidence_with_inputs(self, engine):
        """Should compute confidence with all inputs."""
        edge = EdgeStabilityInputs(
            expectancy_1d_bps=20.0,
            expectancy_7d_bps=18.0,
            profit_factor_1d=1.8,
            profit_factor_7d=1.7,
            sample_count=100,
        )
        confidence, sub_scores = engine.compute_confidence(edge_inputs=edge)
        assert 0.0 <= confidence <= 1.0
        assert sub_scores is not None


# =============================================================================
# Quarantine Controller Tests
# =============================================================================

class TestQuarantineController:
    """Tests for QuarantineController."""

    @pytest.fixture
    def controller(self):
        return QuarantineController()

    def test_normal_conditions_no_quarantine(self, controller):
        """Should not activate quarantine in normal conditions."""
        inputs = QuarantineInputs(
            drawdown_velocity_pct_per_hour=0.5,
            volatility_ratio=1.2,
            current_drawdown_pct=2.0,
        )
        state = controller.evaluate(inputs)
        assert not state.is_active
        assert state.quarantine_pct == 0.0

    def test_high_drawdown_velocity_activates_quarantine(self, controller):
        """Should activate quarantine on high drawdown velocity."""
        inputs = QuarantineInputs(
            drawdown_velocity_pct_per_hour=3.0,  # Above threshold
            volatility_ratio=1.0,
            current_drawdown_pct=5.0,
        )
        state = controller.evaluate(inputs)
        assert state.is_active
        assert state.trigger == QuarantineTrigger.DRAWDOWN_VELOCITY
        assert state.quarantine_pct == 0.25

    def test_high_volatility_activates_quarantine(self, controller):
        """Should activate quarantine on high volatility."""
        inputs = QuarantineInputs(
            drawdown_velocity_pct_per_hour=0.5,
            volatility_ratio=2.5,  # Above threshold
            current_drawdown_pct=2.0,
        )
        state = controller.evaluate(inputs)
        assert state.is_active
        assert state.trigger == QuarantineTrigger.VOLATILITY_SPIKE

    def test_quarantine_release_after_stability(self, controller):
        """Should release quarantine after stability period."""
        # First activate
        inputs_bad = QuarantineInputs(
            drawdown_velocity_pct_per_hour=3.0,
            volatility_ratio=1.0,
        )
        controller.evaluate(inputs_bad)
        assert controller.is_active

        # Then normalize
        inputs_good = QuarantineInputs(
            drawdown_velocity_pct_per_hour=0.5,
            volatility_ratio=1.0,
        )
        # Evaluate with normalized conditions - starts stability timer
        now_ns = int(time.time() * 1_000_000_000)
        controller.evaluate(inputs_good, now_ns)
        assert controller.is_active  # Still active, waiting for stability

        # Advance past stability period
        future_ns = now_ns + 3 * 60 * 60 * 1_000_000_000  # 3 hours
        state = controller.evaluate(inputs_good, future_ns)
        assert not state.is_active

    def test_force_activate(self, controller):
        """Should allow manual activation."""
        state = controller.force_activate(quarantine_pct=0.30)
        assert state.is_active
        assert state.quarantine_pct == 0.30
        assert state.trigger == QuarantineTrigger.MANUAL

    def test_force_release(self, controller):
        """Should allow manual release."""
        controller.force_activate()
        state = controller.force_release()
        assert not state.is_active


# =============================================================================
# Anti-Euphoria Engine Tests
# =============================================================================

class TestAntiEuphoriaEngine:
    """Tests for AntiEuphoriaEngine."""

    @pytest.fixture
    def engine(self):
        return AntiEuphoriaEngine()

    def test_no_euphoria_initially(self, engine):
        """Should not detect euphoria initially."""
        inputs = CapitalGovernorInputs(
            current_equity=10000.0,
            peak_equity=10000.0,
            daily_pnl_pct=1.0,
            consecutive_wins=2,
        )
        event = engine.check_euphoria(inputs)
        assert event is None

    def test_new_ath_triggers_euphoria(self, engine):
        """Should detect euphoria on new ATH."""
        # Set initial peak
        engine._last_peak_equity = 10000.0

        inputs = CapitalGovernorInputs(
            current_equity=11000.0,  # New ATH
            peak_equity=10000.0,
        )
        event = engine.check_euphoria(inputs)
        assert event is not None
        assert event.event_type == FreezeReason.NEW_ATH

    def test_win_streak_triggers_euphoria(self, engine):
        """Should detect euphoria on win streak."""
        inputs = CapitalGovernorInputs(
            current_equity=10000.0,
            consecutive_wins=5,  # At threshold
        )
        event = engine.check_euphoria(inputs)
        assert event is not None
        assert event.event_type == FreezeReason.WIN_STREAK

    def test_profit_spike_triggers_euphoria(self, engine):
        """Should detect euphoria on profit spike."""
        inputs = CapitalGovernorInputs(
            current_equity=10000.0,
            daily_pnl_pct=6.0,  # Above threshold
        )
        event = engine.check_euphoria(inputs)
        assert event is not None
        assert event.event_type == FreezeReason.DAILY_PROFIT_SPIKE

    def test_freeze_expires(self, engine):
        """Should expire freeze after duration."""
        now_ns = int(time.time() * 1_000_000_000)
        engine.set_freeze(FreezeReason.WIN_STREAK, 1_000_000_000, now_ns)  # 1 second

        # Check immediately
        is_frozen, _, _ = engine.is_frozen(now_ns)
        assert is_frozen

        # Check after expiry
        is_frozen, _, _ = engine.is_frozen(now_ns + 2_000_000_000)
        assert not is_frozen


# =============================================================================
# Sovereign Capital Governor Tests
# =============================================================================

class TestSovereignCapitalGovernor:
    """Tests for SovereignCapitalGovernor."""

    @pytest.fixture
    def governor(self):
        confidence_engine = ConfidenceEngine()
        quarantine_controller = QuarantineController()
        return SovereignCapitalGovernor(confidence_engine, quarantine_controller)

    def test_initial_state_is_hold(self, governor):
        """Should start in HOLD state."""
        assert governor.scaling_state == ScalingState.HOLD

    def test_high_confidence_allows_grow(self, governor):
        """Should allow GROW with high confidence."""
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=0.9,
            market_stability=0.9,
            execution_quality=0.9,
            impact_containment=0.9,
            drawdown_discipline=0.9,
            strategy_diversification=0.9,
        )
        inputs = CapitalGovernorInputs(current_capital_fraction=0.5)
        decision = governor.evaluate(inputs, sub_scores)

        assert decision.scaling_state == ScalingState.GROW
        assert decision.confidence_score > 0.75

    def test_low_confidence_triggers_shrink(self, governor):
        """Should trigger SHRINK with low confidence."""
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=0.2,
            market_stability=0.2,
            execution_quality=0.2,
            impact_containment=0.2,
            drawdown_discipline=0.2,
            strategy_diversification=0.2,
        )
        inputs = CapitalGovernorInputs(current_capital_fraction=1.0)
        decision = governor.evaluate(inputs, sub_scores)

        assert decision.scaling_state == ScalingState.SHRINK
        assert decision.confidence_score < 0.30

    def test_quarantine_overrides_confidence(self, governor):
        """Should enter QUARANTINE regardless of confidence."""
        inputs = CapitalGovernorInputs(
            drawdown_velocity_pct_per_hour=5.0,  # High - triggers quarantine
            volatility_ratio=1.0,
            current_capital_fraction=1.0,
        )
        # Even with good confidence...
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=0.9,
            market_stability=0.9,
            execution_quality=0.9,
            impact_containment=0.9,
            drawdown_discipline=0.9,
            strategy_diversification=0.9,
        )
        decision = governor.evaluate(inputs, sub_scores)

        assert decision.scaling_state == ScalingState.QUARANTINE

    def test_ath_triggers_freeze(self, governor):
        """Should trigger FREEZE on new ATH."""
        # Set initial peak
        governor._anti_euphoria._last_peak_equity = 10000.0

        inputs = CapitalGovernorInputs(
            current_equity=11000.0,  # New ATH
            peak_equity=10000.0,
        )
        decision = governor.evaluate(inputs)

        assert decision.scaling_state == ScalingState.FREEZE
        assert decision.freeze_reason == FreezeReason.NEW_ATH

    def test_win_streak_triggers_freeze(self, governor):
        """Should trigger FREEZE on win streak."""
        inputs = CapitalGovernorInputs(
            consecutive_wins=6,  # Above threshold
        )
        decision = governor.evaluate(inputs)

        assert decision.scaling_state == ScalingState.FREEZE
        assert decision.freeze_reason == FreezeReason.WIN_STREAK

    def test_force_freeze(self, governor):
        """Should allow manual freeze."""
        decision = governor.force_freeze(duration_ns=60_000_000_000)

        assert decision.scaling_state == ScalingState.FREEZE
        assert decision.freeze_reason == FreezeReason.MANUAL

    def test_size_multiplier_by_state(self, governor):
        """Should return correct size multiplier for each state."""
        # Test GROW state
        now_ns = int(time.time() * 1_000_000_000)
        sub_scores = ConfidenceSubScores(
            ts_ns=now_ns,
            edge_stability=0.9,
            market_stability=0.9,
            execution_quality=0.9,
            impact_containment=0.9,
            drawdown_discipline=0.9,
            strategy_diversification=0.9,
        )
        inputs = CapitalGovernorInputs()
        decision = governor.evaluate(inputs, sub_scores)
        assert decision.allowed_size_multiplier == 1.0

    def test_restore_state(self, governor):
        """Should restore state from persistence."""
        governor.restore_state(
            scaling_state="FREEZE",
            allowed_capital_fraction=0.75,
            freeze_until_ns=int(time.time() * 1_000_000_000) + 60_000_000_000,
            freeze_reason="MANUAL",
            quarantine_active=False,
            quarantine_pct=0.0,
            last_ath=15000.0,
            consecutive_wins=3,
        )

        assert governor.scaling_state == ScalingState.FREEZE
        assert governor.allowed_capital_fraction == 0.75


class TestScalingState:
    """Tests for ScalingState enum."""

    def test_all_states_defined(self):
        """All scaling states should be defined."""
        assert ScalingState.GROW.value == "GROW"
        assert ScalingState.HOLD.value == "HOLD"
        assert ScalingState.SHRINK.value == "SHRINK"
        assert ScalingState.FREEZE.value == "FREEZE"
        assert ScalingState.QUARANTINE.value == "QUARANTINE"


class TestFreezeReason:
    """Tests for FreezeReason enum."""

    def test_all_reasons_defined(self):
        """All freeze reasons should be defined."""
        assert FreezeReason.NONE.value == "NONE"
        assert FreezeReason.NEW_ATH.value == "NEW_ATH"
        assert FreezeReason.WIN_STREAK.value == "WIN_STREAK"
        assert FreezeReason.DAILY_PROFIT_SPIKE.value == "DAILY_PROFIT_SPIKE"
        assert FreezeReason.MANUAL.value == "MANUAL"
